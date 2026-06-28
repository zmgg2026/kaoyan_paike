#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import sys
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import date as Date, datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scheduler
from scripts import build_camp_maintenance_schedule as maintenance
from scripts import repair_wyqc_foundation_gaps as gap_repair
from scripts.csv_utils import read_csv_rows, write_csv_rows as write_csv_rows_with_fields
from scripts.schedule_display import week_start, weekday_label
from scripts.schedule_outputs import write_day_table_html


PUBLIC_SUBJECTS = {"英语", "政治", "数学"}
SUMMER_START = "2026-07-04"
SUMMER_END = "2026-08-31"
MAX_SAME_SUITE_SUBJECT_TEACHER_STREAK = 3

SUITE_WEEK_SUBJECT_QUOTAS: Dict[str, Dict[Tuple[str, str], int]] = {
    "2723": {
        ("2026-06-29", "英语"): 1,
        ("2026-06-29", "政治"): 0,
        ("2026-07-06", "英语"): 4,
        ("2026-07-06", "政治"): 2,
        ("2026-07-13", "英语"): 3,
        ("2026-07-13", "政治"): 2,
        ("2026-07-20", "英语"): 2,
        ("2026-07-20", "政治"): 1,
        ("2026-07-27", "英语"): 3,
        ("2026-07-27", "政治"): 2,
        ("2026-08-03", "英语"): 3,
        ("2026-08-03", "政治"): 2,
        ("2026-08-10", "英语"): 4,
        ("2026-08-10", "政治"): 1,
        ("2026-08-17", "英语"): 3,
        ("2026-08-17", "政治"): 2,
        ("2026-08-24", "英语"): 4,
        ("2026-08-24", "政治"): 2,
    },
    "2724": {
        ("2026-06-29", "数学"): 1,
        ("2026-06-29", "政治"): 1,
        ("2026-06-29", "英语"): 0,
        ("2026-07-06", "数学"): 2,
        ("2026-07-06", "政治"): 2,
        ("2026-07-06", "英语"): 4,
        ("2026-07-13", "数学"): 1,
        ("2026-07-13", "政治"): 2,
        ("2026-07-13", "英语"): 3,
        ("2026-07-20", "数学"): 2,
        ("2026-07-20", "政治"): 2,
        ("2026-07-20", "英语"): 3,
        ("2026-07-27", "数学"): 2,
        ("2026-07-27", "政治"): 2,
        ("2026-07-27", "英语"): 3,
        ("2026-08-03", "数学"): 2,
        ("2026-08-03", "政治"): 2,
        ("2026-08-03", "英语"): 4,
        ("2026-08-10", "数学"): 4,
        ("2026-08-10", "政治"): 1,
        ("2026-08-10", "英语"): 4,
        ("2026-08-17", "数学"): 3,
        ("2026-08-17", "政治"): 2,
        ("2026-08-17", "英语"): 4,
        ("2026-08-24", "数学"): 3,
        ("2026-08-24", "政治"): 2,
        ("2026-08-24", "英语"): 3,
    },
}


def clean(value: object) -> str:
    return str(value or "").strip()


def max_consecutive_days(date_values: Iterable[str]) -> int:
    days = sorted({Date.fromisoformat(value) for value in date_values if value})
    if not days:
        return 0
    longest = 1
    current = 1
    for previous, day in zip(days, days[1:]):
        if day == previous + timedelta(days=1):
            current += 1
        else:
            longest = max(longest, current)
            current = 1
    return max(longest, current)


def load_rows(path: Path) -> List[dict]:
    return read_csv_rows(path)


def write_rows(path: Path, rows: Sequence[dict], fieldnames: Sequence[str]) -> None:
    write_csv_rows_with_fields(path, fieldnames, rows, encoding="utf-8")


def is_target_row(row: dict, suite_code: str) -> bool:
    return (
        clean(row.get("class_id")).endswith(suite_code)
        and clean(row.get("subject")) in PUBLIC_SUBJECTS
        and SUMMER_START <= clean(row.get("date")) <= SUMMER_END
        and clean(row.get("period")) in {"AM", "PM"}
    )


def halfday_group_key(row: dict) -> Tuple[str, str, str, str, str, str, str, str, str, str]:
    return (
        clean(row.get("class_id")),
        clean(row.get("date")),
        clean(row.get("period")),
        clean(row.get("subject")),
        clean(row.get("stage")),
        clean(row.get("course_module")),
        clean(row.get("course_group")),
        clean(row.get("teacher_id")),
        clean(row.get("teacher_name")),
        clean(row.get("room_id")),
    )


def collect_groups(
    rows: Sequence[dict],
    suite_code: str,
) -> Dict[Tuple[str, ...], List[Tuple[int, dict]]]:
    groups: Dict[Tuple[str, ...], List[Tuple[int, dict]]] = defaultdict(list)
    for index, row in enumerate(rows):
        if is_target_row(row, suite_code):
            groups[halfday_group_key(row)].append((index, row))
    for key, group_rows in groups.items():
        total = sum(float(row.get("duration_hours") or 0) for _index, row in group_rows)
        if total != 4:
            raise ValueError(f"{suite_code} 暑期课不是完整 4h 半天块: {key} = {total}h")
    return groups


def build_move_task(
    source: scheduler.ScheduleInput,
    row: dict,
    task_id: str,
) -> scheduler.CourseBlock:
    cls = source.classes[clean(row.get("class_id"))]
    requirement = gap_repair.find_requirement(cls, row, include_teacher=False)
    if not requirement:
        raise ValueError(f"找不到课程需求: {row}")
    task = gap_repair.task_from_requirement(
        cls,
        requirement,
        task_id,
        room_ids={clean(row.get("room_id"))},
    )
    row_teacher_id = clean(row.get("teacher_id"))
    row_teacher_name = clean(row.get("teacher_name"))
    if row_teacher_id or row_teacher_name:
        task = replace(
            task,
            teacher_id=row_teacher_id,
            teacher_name=row_teacher_name,
        )
    return task


def task_original_positions(
    tasks: Sequence[scheduler.CourseBlock],
    groups: Dict[Tuple[str, ...], List[Tuple[int, dict]]],
) -> Dict[str, Tuple[str, str]]:
    unused_keys = set(groups)
    positions: Dict[str, Tuple[str, str]] = {}
    for task in tasks:
        matching_key = next(
            key
            for key in sorted(unused_keys)
            if clean(groups[key][0][1].get("class_id")) == task.class_id
            and clean(groups[key][0][1].get("subject")) == task.subject
            and clean(groups[key][0][1].get("stage")) == clean(task.stage)
            and clean(groups[key][0][1].get("course_module")) == clean(task.course_module)
            and clean(groups[key][0][1].get("course_group")) == clean(task.course_group)
            and clean(groups[key][0][1].get("teacher_id")) == clean(task.teacher_id)
        )
        unused_keys.remove(matching_key)
        positions[task.task_id] = (matching_key[1], matching_key[2])
    return positions


def quota_weeks(quotas: Dict[Tuple[str, str], int]) -> Set[str]:
    return {week for week, _subject in quotas}


def quota_week_total(quotas: Dict[Tuple[str, str], int], week: str) -> int:
    return sum(value for (quota_week, _subject), value in quotas.items() if quota_week == week)


def assign_target_weeks(
    tasks: Sequence[scheduler.CourseBlock],
    quotas: Dict[Tuple[str, str], int],
    original_positions: Dict[str, Tuple[str, str]],
    allowed_weeks_by_task: Optional[Dict[str, Set[str]]] = None,
    teacher_week_capacity: Optional[Dict[Tuple[str, str, str], int]] = None,
) -> Dict[str, str]:
    assignments: Dict[str, str] = {}
    tasks_by_subject: Dict[str, List[scheduler.CourseBlock]] = defaultdict(list)
    for task in tasks:
        tasks_by_subject[task.subject].append(task)

    for subject, subject_tasks in tasks_by_subject.items():
        remaining: Counter[str] = Counter()
        for (week, quota_subject), quota in sorted(quotas.items()):
            if quota_subject == subject:
                remaining[week] += quota
        if sum(remaining.values()) != len(subject_tasks):
            raise ValueError(
                f"{subject} 任务数 {len(subject_tasks)} 与目标周课量 {sum(remaining.values())} 不一致"
            )
        ordered_tasks = sorted(
            subject_tasks,
            key=lambda task: (
                len(allowed_weeks_by_task.get(task.task_id, set(remaining)) if allowed_weeks_by_task else set(remaining)),
                original_positions.get(task.task_id, ("9999-12-31", ""))[0],
                scheduler.period_sort_value(original_positions.get(task.task_id, ("", "EVENING"))[1] or "EVENING"),
                task.stage or "",
                task.course_group or "",
                task.course_module or "",
                task.teacher_id or task.teacher_name,
                task.task_id,
            ),
        )

        def original_week(task: scheduler.CourseBlock) -> str:
            original_date = original_positions.get(task.task_id, ("", ""))[0]
            return week_start(original_date) if original_date else ""

        def week_cost_value(task: scheduler.CourseBlock, week: str) -> int:
            source_week = original_week(task)
            if not source_week:
                return 9999
            return (0 if week == source_week else 1000) + abs(
                (Date.fromisoformat(week) - Date.fromisoformat(source_week)).days
            )

        def teacher_key(task: scheduler.CourseBlock) -> str:
            return task.teacher_id or task.teacher_name

        class Edge:
            def __init__(self, to: int, rev: int, cap: int, cost: int) -> None:
                self.to = to
                self.rev = rev
                self.cap = cap
                self.cost = cost

        graph: List[List[Edge]] = []

        def new_node() -> int:
            graph.append([])
            return len(graph) - 1

        def add_edge(left: int, right: int, cap: int, cost: int) -> Edge:
            forward = Edge(right, len(graph[right]), cap, cost)
            backward = Edge(left, len(graph[left]), 0, -cost)
            graph[left].append(forward)
            graph[right].append(backward)
            return forward

        source_node = new_node()
        sink_node = new_node()
        task_nodes = {task.task_id: new_node() for task in ordered_tasks}
        teacher_week_nodes: Dict[Tuple[str, str], int] = {}
        week_nodes = {week: new_node() for week in sorted(remaining)}
        task_week_edges: List[Tuple[Edge, scheduler.CourseBlock, str]] = []

        for task in ordered_tasks:
            add_edge(source_node, task_nodes[task.task_id], 1, 0)
            allowed_weeks = allowed_weeks_by_task.get(task.task_id, set(remaining)) if allowed_weeks_by_task else set(remaining)
            for week in sorted(allowed_weeks):
                if remaining.get(week, 0) <= 0:
                    continue
                capacity = (
                    teacher_week_capacity.get((subject, teacher_key(task), week), 0)
                    if teacher_week_capacity
                    else remaining[week]
                )
                if capacity <= 0:
                    continue
                teacher_week_key = (teacher_key(task), week)
                if teacher_week_key not in teacher_week_nodes:
                    teacher_week_nodes[teacher_week_key] = new_node()
                teacher_week_node = teacher_week_nodes[teacher_week_key]
                edge = add_edge(
                    task_nodes[task.task_id],
                    teacher_week_node,
                    1,
                    week_cost_value(task, week),
                )
                task_week_edges.append((edge, task, week))

        for (teacher_id, week), node in teacher_week_nodes.items():
            capacity = (
                teacher_week_capacity.get((subject, teacher_id, week), 0)
                if teacher_week_capacity
                else remaining[week]
            )
            add_edge(node, week_nodes[week], capacity, 0)
        for week, count in remaining.items():
            add_edge(week_nodes[week], sink_node, count, 0)

        flow = 0
        needed_flow = len(ordered_tasks)
        while flow < needed_flow:
            distance = [10**12] * len(graph)
            previous_node = [-1] * len(graph)
            previous_edge = [-1] * len(graph)
            in_queue = [False] * len(graph)
            queue = [source_node]
            distance[source_node] = 0
            in_queue[source_node] = True
            for node in queue:
                in_queue[node] = False
                for edge_index, edge in enumerate(graph[node]):
                    if edge.cap <= 0:
                        continue
                    next_distance = distance[node] + edge.cost
                    if next_distance < distance[edge.to]:
                        distance[edge.to] = next_distance
                        previous_node[edge.to] = node
                        previous_edge[edge.to] = edge_index
                        if not in_queue[edge.to]:
                            queue.append(edge.to)
                            in_queue[edge.to] = True
            if previous_node[sink_node] == -1:
                break
            add_flow = needed_flow - flow
            node = sink_node
            while node != source_node:
                edge = graph[previous_node[node]][previous_edge[node]]
                add_flow = min(add_flow, edge.cap)
                node = previous_node[node]
            node = sink_node
            while node != source_node:
                edge = graph[previous_node[node]][previous_edge[node]]
                edge.cap -= add_flow
                graph[node][edge.rev].cap += add_flow
                node = previous_node[node]
            flow += add_flow

        if flow != needed_flow:
            raise ValueError(f"{subject} 无法按真实可用周分配目标周课量")
        for edge, task, week in task_week_edges:
            if edge.cap == 0:
                assignments[task.task_id] = week
    return assignments


def solve_balance(
    source: scheduler.ScheduleInput,
    tasks: Sequence[scheduler.CourseBlock],
    suite_code: str,
    quotas: Dict[Tuple[str, str], int],
    original_positions: Dict[str, Tuple[str, str]],
    enforce_streak_limit: bool = True,
) -> Dict[str, scheduler.Candidate]:
    class_slot_used, teacher_slot_used, room_slot_used, conflict_group_slot_used = scheduler.locked_constraint_sets(source)
    class_teacher_day_loads: Counter[Tuple[str, str, str]] = Counter()
    class_subject_day_loads: Counter[Tuple[str, str, str]] = Counter()
    used_subject_week: Counter[Tuple[str, str]] = Counter()
    used_week: Counter[str] = Counter()
    suite_subject_teacher_dates: Dict[Tuple[str, str, str], Counter[str]] = defaultdict(Counter)
    allowed_weeks = quota_weeks(quotas)

    for assignment in source.locked_assignments:
        teacher_key = assignment.candidate.teacher_id or assignment.candidate.teacher_name
        seen_dates = set()
        for slot in assignment.candidate.slots:
            class_teacher_day_loads[(assignment.task.class_id, teacher_key, slot.date)] += slot.duration_hours
            class_subject_day_loads[(assignment.task.class_id, assignment.task.subject, slot.date)] += slot.duration_hours
            seen_dates.add(slot.date)
        for slot_date in seen_dates:
            if assignment.task.class_id.endswith(suite_code):
                suite_subject_teacher_dates[(suite_code, assignment.task.subject, teacher_key)][slot_date] += 1

    def base_valid(task: scheduler.CourseBlock, candidate: scheduler.Candidate) -> bool:
        class_group_ids = source.class_conflict_groups.get(task.class_id, set())
        for slot in candidate.slots:
            if (task.class_id, slot.id) in class_slot_used:
                return False
            if candidate.teacher_id and (candidate.teacher_id, slot.id) in teacher_slot_used:
                return False
            if (candidate.room_id, slot.id) in room_slot_used:
                return False
            if any((group_id, slot.id) in conflict_group_slot_used for group_id in class_group_ids):
                return False
        return True

    candidate_pool: Dict[str, List[scheduler.Candidate]] = {}
    allowed_weeks_by_task: Dict[str, Set[str]] = defaultdict(set)
    teacher_week_slots: Dict[Tuple[str, str, str], Set[Tuple[str, str]]] = defaultdict(set)
    for task in tasks:
        candidates = []
        for candidate in scheduler.candidate_assignments(task, source):
            if len(candidate.slots) != 2 or sum(slot.duration_hours for slot in candidate.slots) != 4:
                continue
            first = candidate.slots[0]
            if not (SUMMER_START <= first.date <= SUMMER_END):
                continue
            week = week_start(first.date)
            if week not in allowed_weeks or quotas.get((week, task.subject), 0) <= 0:
                continue
            if not base_valid(task, candidate):
                continue
            candidates.append(candidate)
            allowed_weeks_by_task[task.task_id].add(week)
            teacher_key = candidate.teacher_id or candidate.teacher_name
            teacher_week_slots[(task.subject, teacher_key, week)].add((first.date, first.period))
        if not candidates:
            raise ValueError(f"{task.class_id} {task.subject}/{task.course_module or ''} 没有可用暑期半天")
        candidate_pool[task.task_id] = candidates

    target_week_by_task = assign_target_weeks(
        tasks,
        quotas,
        original_positions,
        allowed_weeks_by_task=allowed_weeks_by_task,
        teacher_week_capacity={key: len(value) for key, value in teacher_week_slots.items()},
    )
    domains: Dict[str, List[scheduler.Candidate]] = {
        task.task_id: [
            candidate
            for candidate in candidate_pool[task.task_id]
            if week_start(candidate.slots[0].date) == target_week_by_task[task.task_id]
        ]
        for task in tasks
    }

    task_by_id = {task.task_id: task for task in tasks}
    placed: Dict[str, scheduler.Candidate] = {}

    def teacher_streak_after(task: scheduler.CourseBlock, candidate: scheduler.Candidate) -> int:
        first = candidate.slots[0]
        teacher_key = candidate.teacher_id or candidate.teacher_name
        dates = suite_subject_teacher_dates[(suite_code, task.subject, teacher_key)].copy()
        dates[first.date] += 1
        return max_consecutive_days(dates)

    def valid(task: scheduler.CourseBlock, candidate: scheduler.Candidate) -> bool:
        first = candidate.slots[0]
        week = week_start(first.date)
        if week != target_week_by_task[task.task_id]:
            return False
        if enforce_streak_limit and teacher_streak_after(task, candidate) > MAX_SAME_SUITE_SUBJECT_TEACHER_STREAK:
            return False
        class_group_ids = source.class_conflict_groups.get(task.class_id, set())
        teacher_key = candidate.teacher_id or candidate.teacher_name
        if class_subject_day_loads[(task.class_id, task.subject, first.date)] + task.block_hours > 4:
            return False
        if class_teacher_day_loads[(task.class_id, teacher_key, first.date)] + task.block_hours > 8:
            return False
        for slot in candidate.slots:
            if (task.class_id, slot.id) in class_slot_used:
                return False
            if candidate.teacher_id and (candidate.teacher_id, slot.id) in teacher_slot_used:
                return False
            if (candidate.room_id, slot.id) in room_slot_used:
                return False
            if any((group_id, slot.id) in conflict_group_slot_used for group_id in class_group_ids):
                return False
        return True

    def place(task: scheduler.CourseBlock, candidate: scheduler.Candidate) -> None:
        placed[task.task_id] = candidate
        first = candidate.slots[0]
        week = week_start(first.date)
        used_subject_week[(week, task.subject)] += 1
        used_week[week] += 1
        class_group_ids = source.class_conflict_groups.get(task.class_id, set())
        teacher_key = candidate.teacher_id or candidate.teacher_name
        suite_subject_teacher_dates[(suite_code, task.subject, teacher_key)][first.date] += 1
        for slot in candidate.slots:
            class_slot_used.add((task.class_id, slot.id))
            if candidate.teacher_id:
                teacher_slot_used.add((candidate.teacher_id, slot.id))
            room_slot_used.add((candidate.room_id, slot.id))
            for group_id in class_group_ids:
                conflict_group_slot_used.add((group_id, slot.id))
            class_teacher_day_loads[(task.class_id, teacher_key, slot.date)] += slot.duration_hours
            class_subject_day_loads[(task.class_id, task.subject, slot.date)] += slot.duration_hours

    def unplace(task: scheduler.CourseBlock, candidate: scheduler.Candidate) -> None:
        placed.pop(task.task_id, None)
        first = candidate.slots[0]
        week = week_start(first.date)
        used_subject_week[(week, task.subject)] -= 1
        used_week[week] -= 1
        class_group_ids = source.class_conflict_groups.get(task.class_id, set())
        teacher_key = candidate.teacher_id or candidate.teacher_name
        suite_subject_teacher_dates[(suite_code, task.subject, teacher_key)][first.date] -= 1
        if suite_subject_teacher_dates[(suite_code, task.subject, teacher_key)][first.date] <= 0:
            del suite_subject_teacher_dates[(suite_code, task.subject, teacher_key)][first.date]
        for slot in candidate.slots:
            class_slot_used.remove((task.class_id, slot.id))
            if candidate.teacher_id:
                teacher_slot_used.remove((candidate.teacher_id, slot.id))
            room_slot_used.remove((candidate.room_id, slot.id))
            for group_id in class_group_ids:
                conflict_group_slot_used.remove((group_id, slot.id))
            class_teacher_day_loads[(task.class_id, teacher_key, slot.date)] -= slot.duration_hours
            class_subject_day_loads[(task.class_id, task.subject, slot.date)] -= slot.duration_hours

    def candidate_score(task: scheduler.CourseBlock, candidate: scheduler.Candidate) -> Tuple[object, ...]:
        first = candidate.slots[0]
        week = week_start(first.date)
        original_date, original_period = original_positions.get(task.task_id, ("", ""))
        original_week = week_start(original_date) if original_date else ""
        streak = teacher_streak_after(task, candidate)
        return (
            max(0, streak - 2),
            0 if week == original_week else 1,
            used_subject_week[(week, task.subject)],
            used_week[week],
            abs((Date.fromisoformat(first.date) - Date.fromisoformat(original_date)).days) if original_date else 999,
            0 if first.period == original_period else 1,
            first.date,
            scheduler.period_sort_value(first.period),
            first.order,
        )

    sys.setrecursionlimit(max(10000, len(tasks) * 5))

    def backtrack_week(week_tasks: Sequence[scheduler.CourseBlock]) -> bool:
        if all(task.task_id in placed for task in week_tasks):
            return True
        best_task: Optional[scheduler.CourseBlock] = None
        best_options: Optional[List[scheduler.Candidate]] = None
        for task in week_tasks:
            if task.task_id in placed:
                continue
            options = [candidate for candidate in domains[task.task_id] if valid(task, candidate)]
            if not options:
                return False
            options.sort(key=lambda candidate: candidate_score(task, candidate))
            if best_options is None or len(options) < len(best_options):
                best_task = task
                best_options = options

        assert best_task is not None and best_options is not None
        for candidate in best_options:
            place(best_task, candidate)
            if backtrack_week(week_tasks):
                return True
            unplace(best_task, candidate)
        return False

    tasks_by_week: Dict[str, List[scheduler.CourseBlock]] = defaultdict(list)
    for task in task_by_id.values():
        tasks_by_week[target_week_by_task[task.task_id]].append(task)
    for week in sorted(tasks_by_week):
        before_week = set(placed)
        if not backtrack_week(tasks_by_week[week]):
            for task_id in list(set(placed) - before_week):
                candidate = placed[task_id]
                unplace(task_by_id[task_id], candidate)
            raise ValueError(f"{suite_code} {week} 暑期周课量均衡未能求解")
    return placed


def apply_solution(
    rows: Sequence[dict],
    groups: Dict[Tuple[str, ...], List[Tuple[int, dict]]],
    tasks: Sequence[scheduler.CourseBlock],
    placed: Dict[str, scheduler.Candidate],
    room_names: Dict[str, str],
) -> Tuple[List[dict], List[str]]:
    move_indices = {index for group_rows in groups.values() for index, _row in group_rows}
    result = [dict(row) for index, row in enumerate(rows) if index not in move_indices]
    unused_keys = set(groups)
    lines: List[str] = []
    for task in tasks:
        matching_key = next(
            key
            for key in sorted(unused_keys)
            if clean(groups[key][0][1].get("class_id")) == task.class_id
            and clean(groups[key][0][1].get("subject")) == task.subject
            and clean(groups[key][0][1].get("stage")) == clean(task.stage)
            and clean(groups[key][0][1].get("course_module")) == clean(task.course_module)
            and clean(groups[key][0][1].get("course_group")) == clean(task.course_group)
            and clean(groups[key][0][1].get("teacher_id")) == clean(task.teacher_id)
        )
        unused_keys.remove(matching_key)
        candidate = placed[task.task_id]
        original_rows = [
            dict(row)
            for _index, row in sorted(groups[matching_key], key=lambda item: clean(item[1].get("lesson_slot")))
        ]
        for row, slot in zip(original_rows, candidate.slots):
            row.update(
                {
                    "date": slot.date,
                    "weekday": weekday_label(slot.date),
                    "period": slot.period,
                    "lesson_slot": slot.id,
                    "slot_label": slot.name,
                    "start_time": slot.start_time or "",
                    "end_time": slot.end_time or "",
                    "room_id": candidate.room_id,
                    "room_name": room_names.get(candidate.room_id, candidate.room_id),
                    "duration_hours": str(slot.duration_hours),
                }
            )
            result.append(row)
        if (matching_key[1], matching_key[2]) != (candidate.slots[0].date, candidate.slots[0].period):
            lines.append(
                f"{task.class_id} {task.subject}/{task.stage or ''}/{task.course_module or ''}: "
                f"{matching_key[1]} {matching_key[2]} -> {candidate.slots[0].date} {candidate.slots[0].period}"
            )
    return result, lines


def weekly_summary(rows: Sequence[dict], suite_code: str) -> List[dict]:
    loads: Counter[Tuple[str, str]] = Counter()
    quotas = SUITE_WEEK_SUBJECT_QUOTAS[suite_code]
    for row in rows:
        if is_target_row(row, suite_code):
            loads[(week_start(clean(row.get("date"))), clean(row.get("subject")))] += float(row.get("duration_hours") or 0) / 4
    weeks = sorted({week for week, _subject in loads} | {week for week, _subject in quotas})
    result = []
    for week in weeks:
        item = {
            "week": week,
            "数学": loads[(week, "数学")],
            "政治": loads[(week, "政治")],
            "英语": loads[(week, "英语")],
        }
        item["total"] = item["数学"] + item["政治"] + item["英语"]
        result.append(item)
    return result


def teacher_streaks(rows: Sequence[dict], suite_code: str, minimum: int = 3) -> List[str]:
    dates_by_key: Dict[Tuple[str, str, str], Set[str]] = defaultdict(set)
    for row in rows:
        if not is_target_row(row, suite_code):
            continue
        key = (clean(row.get("subject")), clean(row.get("teacher_id")) or clean(row.get("teacher_name")), clean(row.get("teacher_name")))
        dates_by_key[key].add(clean(row.get("date")))
    lines = []
    for (subject, teacher_id, teacher_name), dates in sorted(dates_by_key.items()):
        longest = max_consecutive_days(dates)
        if longest >= minimum:
            lines.append(f"{subject} {teacher_name or teacher_id}: 最长连续 {longest} 天")
    return lines


def singleton_halfday_count(rows: Sequence[dict], suite_codes: Sequence[str]) -> int:
    totals: Counter[Tuple[str, str, str, str]] = Counter()
    for row in rows:
        if any(is_target_row(row, suite_code) for suite_code in suite_codes):
            totals[(clean(row.get("class_id")), clean(row.get("date")), clean(row.get("period")), clean(row.get("subject")))] += float(row.get("duration_hours") or 0)
    return sum(1 for hours in totals.values() if hours == 2)


def solve_suite(
    rows: Sequence[dict],
    suite_code: str,
    data_dir: Path,
    class_metadata: Dict[str, Dict[str, str]],
    room_names: Dict[str, str],
) -> Tuple[List[dict], List[str]]:
    groups = collect_groups(rows, suite_code)
    if not groups:
        raise ValueError(f"{suite_code} 没有找到 7-8 月公共课课表")
    move_indices = {index for group_rows in groups.values() for index, _row in group_rows}
    locked_rows = [row for index, row in enumerate(rows) if index not in move_indices]
    class_ids = {clean(group_rows[0][1].get("class_id")) for group_rows in groups.values()}
    source = gap_repair.transformed_schedule_input(data_dir, class_ids, class_metadata)
    source = replace(source, locked_assignments=maintenance.assignments_from_rows(locked_rows, f"{suite_code}_SUM_BAL_LOCK"))
    source = maintenance.with_conflict_groups_for_locked(data_dir, source, source.locked_assignments)
    tasks = [
        build_move_task(source, group_rows[0][1], f"{suite_code}_SUMMER_BALANCE:{index}")
        for index, (_key, group_rows) in enumerate(sorted(groups.items()), start=1)
    ]
    quotas = SUITE_WEEK_SUBJECT_QUOTAS[suite_code]
    expected_halfdays = sum(quotas.values())
    if len(tasks) != expected_halfdays:
        raise ValueError(f"{suite_code} 现有半天数 {len(tasks)} 与目标周课量 {expected_halfdays} 不一致")
    original_positions = task_original_positions(tasks, groups)
    try:
        placed = solve_balance(source, tasks, suite_code, quotas, original_positions)
    except ValueError:
        placed = solve_balance(
            source,
            tasks,
            suite_code,
            quotas,
            original_positions,
            enforce_streak_limit=False,
        )
    return apply_solution(rows, groups, tasks, placed, room_names)


def write_report(
    path: Path,
    output_csv: Path,
    output_html: Path,
    moved_by_suite: Dict[str, Sequence[str]],
    rows: Sequence[dict],
) -> None:
    lines = [
        "# 无忧春暑期周课量均衡调整报告",
        "",
        f"- 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 输出 CSV: {output_csv}",
        f"- 输出 HTML: {output_html}",
        "",
    ]
    for suite_code in moved_by_suite:
        lines.extend(
            [
                f"## {suite_code} 周课量",
                "",
                "| 周一日期 | 总半天 | 数学 | 政治 | 英语 |",
                "|---|---:|---:|---:|---:|",
            ]
        )
        for item in weekly_summary(rows, suite_code):
            lines.append(
                f"| {item['week']} | {item['total']:.0f} | {item['数学']:.0f} | "
                f"{item['政治']:.0f} | {item['英语']:.0f} |"
            )
        streak_lines = teacher_streaks(rows, suite_code)
        lines.extend(["", "### 老师连续天数提醒", ""])
        if streak_lines:
            lines.extend(f"- {line}" for line in streak_lines)
        else:
            lines.append("- 无 3 天及以上连续排课")
        lines.extend(["", "### 移动明细", ""])
        lines.append(f"- 移动完整半天数: {len(moved_by_suite[suite_code])}")
        lines.extend(f"- {line}" for line in moved_by_suite[suite_code])
        lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_suite_codes(values: Sequence[str]) -> List[str]:
    if not values:
        return sorted(SUITE_WEEK_SUBJECT_QUOTAS)
    suite_codes: List[str] = []
    for value in values:
        for item in value.split(","):
            suite_code = item.strip()
            if suite_code:
                suite_codes.append(suite_code)
    unknown = sorted(set(suite_codes) - set(SUITE_WEEK_SUBJECT_QUOTAS))
    if unknown:
        raise ValueError(f"未配置目标周课量的套班: {', '.join(unknown)}")
    return suite_codes


def main() -> None:
    parser = argparse.ArgumentParser(description="均衡无忧春 2723/2724 套班 7-8 月公共课周课量")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--schedule-csv", default=str(maintenance.OUTPUT_CSV))
    parser.add_argument("--suite-code", action="append", default=[])
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    schedule_csv = Path(args.schedule_csv)
    suite_codes = parse_suite_codes(args.suite_code)
    rows = load_rows(schedule_csv)
    if not rows:
        raise ValueError(f"课表为空: {schedule_csv}")
    fieldnames = list(rows[0].keys())
    class_metadata = maintenance.load_class_metadata(data_dir)
    room_names = maintenance.load_room_names(data_dir)

    working_rows = rows
    moved_by_suite: Dict[str, Sequence[str]] = {}
    for suite_code in suite_codes:
        print(f"均衡 {suite_code}", flush=True)
        working_rows, moved_lines = solve_suite(
            working_rows,
            suite_code,
            data_dir,
            class_metadata,
            room_names,
        )
        moved_by_suite[suite_code] = moved_lines

    assignments = maintenance.assignments_from_rows(working_rows, "WYQC_SUM_BAL_OUT")
    teacher_conflicts = maintenance.teacher_time_conflict_lines(assignments)
    if teacher_conflicts:
        raise ValueError("均衡后仍有老师硬冲突: " + "；".join(teacher_conflicts[:5]))
    singletons = singleton_halfday_count(working_rows, suite_codes)
    if singletons:
        raise ValueError(f"均衡后仍有同班同科半天 2h 孤块: {singletons}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.publish:
        backup_stem = f"before_wyqc_summer_balance_{timestamp}"
        for path in (maintenance.OUTPUT_CSV, maintenance.OUTPUT_HTML, maintenance.OUTPUT_REPORT):
            if path.exists():
                shutil.copyfile(path, path.with_name(f"{path.stem}.{backup_stem}{path.suffix}"))
        output_csv = maintenance.OUTPUT_CSV
        output_html = maintenance.OUTPUT_HTML
        output_report = Path("outputs") / f"wyqc_summer_week_balance_report_{timestamp}.md"
    else:
        output_csv = Path("outputs") / f"wyqc_summer_week_balance_{timestamp}.csv"
        output_html = Path("outputs") / f"wyqc_summer_week_balance_{timestamp}.html"
        output_report = Path("outputs") / f"wyqc_summer_week_balance_report_{timestamp}.md"

    write_rows(output_csv, working_rows, fieldnames)
    write_day_table_html(
        assignments,
        output_html,
        "课表维护总表",
        ["AM", "PM", "EVENING"],
        room_names,
        assignments[0].candidate.slots[0].date if assignments else None,
        assignments[-1].candidate.slots[0].date if assignments else None,
        class_metadata,
        maintenance.load_all_class_window_constraint_items(data_dir),
    )
    maintenance.write_teacher_time_conflicts_csv(assignments, maintenance.TEACHER_CONFLICT_CSV, room_names)
    write_report(output_report, output_csv, output_html, moved_by_suite, working_rows)

    if args.publish:
        shutil.copyfile(maintenance.OUTPUT_CSV, maintenance.LEGACY_OUTPUT_CSV)
        shutil.copyfile(maintenance.OUTPUT_HTML, maintenance.LEGACY_OUTPUT_HTML)
        shutil.copyfile(output_report, maintenance.LEGACY_OUTPUT_REPORT)
        with maintenance.OUTPUT_REPORT.open("a", encoding="utf-8") as handle:
            handle.write("\n\n## 2723/2724 暑期周课量均衡调整\n\n")
            handle.write(f"- 专项报告: {output_report}\n")
            for suite_code, moved_lines in moved_by_suite.items():
                handle.write(f"- {suite_code} 移动完整半天数: {len(moved_lines)}\n")
                for item in weekly_summary(working_rows, suite_code):
                    handle.write(
                        f"  - {item['week']}: 总{item['total']:.0f}，数学{item['数学']:.0f}，"
                        f"政治{item['政治']:.0f}，英语{item['英语']:.0f}\n"
                    )

    print(f"已写出: {output_csv}")
    print(f"已写出: {output_html}")
    print(f"专项报告: {output_report}")
    print(f"移动完整半天数: {sum(len(lines) for lines in moved_by_suite.values())}")


if __name__ == "__main__":
    main()
