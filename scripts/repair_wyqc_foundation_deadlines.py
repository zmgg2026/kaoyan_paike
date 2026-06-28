#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import sys
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import date as Date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scheduler
from scripts import build_camp_maintenance_schedule as maintenance
from scripts import repair_wyqc_foundation_gaps as gap_repair
from scripts.csv_utils import read_csv_rows, write_csv_rows as write_csv_rows_with_fields
from scripts.schedule_display import weekday_label
from scripts.schedule_outputs import write_day_table_html


PUBLIC_SUBJECTS = {"英语", "政治", "数学"}
TARGET_STAGES = {"基础", "强化"}
DEFAULT_DEADLINES = {
    "2720": "2026-08-16",
    "2703": "2026-08-16",
    "2704": "2026-07-26",
    "2706": "2026-07-26",
}


def clean(value: object) -> str:
    return str(value or "").strip()


def row_suite(row: dict) -> str:
    return clean(row.get("class_id"))[-4:]


def target_foundation_row(row: dict, deadlines: Dict[str, str]) -> bool:
    return (
        row_suite(row) in deadlines
        and clean(row.get("subject")) in PUBLIC_SUBJECTS
        and clean(row.get("stage")) in TARGET_STAGES
    )


def late_target_row(row: dict, deadlines: Dict[str, str]) -> bool:
    suite = row_suite(row)
    return target_foundation_row(row, deadlines) and clean(row.get("date")) > deadlines[suite]


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


def load_rows(path: Path) -> List[dict]:
    return read_csv_rows(path)


def write_rows(path: Path, rows: Sequence[dict], fieldnames: Sequence[str]) -> None:
    write_csv_rows_with_fields(path, fieldnames, rows, encoding="utf-8")


def collect_late_halfday_groups(rows: Sequence[dict], deadlines: Dict[str, str]) -> Dict[Tuple[str, ...], List[Tuple[int, dict]]]:
    groups: Dict[Tuple[str, ...], List[Tuple[int, dict]]] = defaultdict(list)
    for index, row in enumerate(rows):
        if late_target_row(row, deadlines):
            groups[halfday_group_key(row)].append((index, row))
    for key, group_rows in groups.items():
        total_hours = sum(float(row.get("duration_hours") or 0) for _index, row in group_rows)
        if total_hours != 4:
            raise ValueError(f"超截止课程不是完整 4h 半天块: {key} = {total_hours}h")
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
    return gap_repair.task_from_requirement(
        cls,
        requirement,
        task_id,
        room_ids={clean(row.get("room_id"))},
    )


def build_day_loads(assignments: Sequence[scheduler.Assignment]) -> Tuple[
    Counter[Tuple[str, str, str]],
    Counter[Tuple[str, str, str]],
    Counter[Tuple[str, str]],
    Counter[Tuple[str, str, str]],
]:
    class_teacher_day_loads: Counter[Tuple[str, str, str]] = Counter()
    class_subject_day_loads: Counter[Tuple[str, str, str]] = Counter()
    class_week_loads: Counter[Tuple[str, str]] = Counter()
    class_subject_week_loads: Counter[Tuple[str, str, str]] = Counter()
    for assignment in assignments:
        teacher_key = assignment.candidate.teacher_id or assignment.candidate.teacher_name
        for slot in assignment.candidate.slots:
            class_teacher_day_loads[(assignment.task.class_id, teacher_key, slot.date)] += slot.duration_hours
            class_subject_day_loads[(assignment.task.class_id, assignment.task.subject, slot.date)] += slot.duration_hours
            if assignment.task.subject in PUBLIC_SUBJECTS:
                week = gap_repair.week_start(slot.date)
                class_week_loads[(assignment.task.class_id, week)] += slot.duration_hours
                class_subject_week_loads[(assignment.task.class_id, assignment.task.subject, week)] += slot.duration_hours
    return class_teacher_day_loads, class_subject_day_loads, class_week_loads, class_subject_week_loads


def solve_moves(
    source: scheduler.ScheduleInput,
    tasks: Sequence[scheduler.CourseBlock],
    deadlines: Dict[str, str],
) -> Dict[str, scheduler.Candidate]:
    class_slot_used, teacher_slot_used, room_slot_used, conflict_group_slot_used = scheduler.locked_constraint_sets(source)
    (
        class_teacher_day_loads,
        class_subject_day_loads,
        class_week_loads,
        class_subject_week_loads,
    ) = build_day_loads(source.locked_assignments)

    domains: Dict[str, List[scheduler.Candidate]] = {}
    for task in tasks:
        suite = task.class_id[-4:]
        candidates = [
            candidate
            for candidate in scheduler.candidate_assignments(task, source)
            if len(candidate.slots) == 2
            and sum(slot.duration_hours for slot in candidate.slots) == 4
            and maintenance.WYQC_SUMMER_START <= candidate.slots[0].date <= deadlines[suite]
        ]
        if not candidates:
            raise ValueError(f"{task.class_id} {task.subject}/{task.course_module or ''} 没有可用提前半天")
        domains[task.task_id] = candidates

    task_by_id = {task.task_id: task for task in tasks}
    placed: Dict[str, scheduler.Candidate] = {}

    def valid(task: scheduler.CourseBlock, candidate: scheduler.Candidate) -> bool:
        class_group_ids = source.class_conflict_groups.get(task.class_id, set())
        teacher_key = candidate.teacher_id or candidate.teacher_name
        first = candidate.slots[0]
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
        class_group_ids = source.class_conflict_groups.get(task.class_id, set())
        teacher_key = candidate.teacher_id or candidate.teacher_name
        for slot in candidate.slots:
            class_slot_used.add((task.class_id, slot.id))
            if candidate.teacher_id:
                teacher_slot_used.add((candidate.teacher_id, slot.id))
            room_slot_used.add((candidate.room_id, slot.id))
            for group_id in class_group_ids:
                conflict_group_slot_used.add((group_id, slot.id))
            class_teacher_day_loads[(task.class_id, teacher_key, slot.date)] += slot.duration_hours
            class_subject_day_loads[(task.class_id, task.subject, slot.date)] += slot.duration_hours
            week = gap_repair.week_start(slot.date)
            class_week_loads[(task.class_id, week)] += slot.duration_hours
            class_subject_week_loads[(task.class_id, task.subject, week)] += slot.duration_hours

    def unplace(task: scheduler.CourseBlock, candidate: scheduler.Candidate) -> None:
        placed.pop(task.task_id, None)
        class_group_ids = source.class_conflict_groups.get(task.class_id, set())
        teacher_key = candidate.teacher_id or candidate.teacher_name
        for slot in candidate.slots:
            class_slot_used.remove((task.class_id, slot.id))
            if candidate.teacher_id:
                teacher_slot_used.remove((candidate.teacher_id, slot.id))
            room_slot_used.remove((candidate.room_id, slot.id))
            for group_id in class_group_ids:
                conflict_group_slot_used.remove((group_id, slot.id))
            class_teacher_day_loads[(task.class_id, teacher_key, slot.date)] -= slot.duration_hours
            class_subject_day_loads[(task.class_id, task.subject, slot.date)] -= slot.duration_hours
            week = gap_repair.week_start(slot.date)
            class_week_loads[(task.class_id, week)] -= slot.duration_hours
            class_subject_week_loads[(task.class_id, task.subject, week)] -= slot.duration_hours

    def score(task: scheduler.CourseBlock, candidate: scheduler.Candidate) -> Tuple[object, ...]:
        first = candidate.slots[0]
        week = gap_repair.week_start(first.date)
        return (
            class_subject_week_loads[(task.class_id, task.subject, week)],
            class_week_loads[(task.class_id, week)],
            first.date,
            scheduler.period_sort_value(first.period),
            first.order,
        )

    def backtrack() -> bool:
        if len(placed) == len(tasks):
            return True
        best_task: Optional[scheduler.CourseBlock] = None
        best_options: Optional[List[scheduler.Candidate]] = None
        for task_id, task in task_by_id.items():
            if task_id in placed:
                continue
            options = [candidate for candidate in domains[task_id] if valid(task, candidate)]
            if not options:
                return False
            options.sort(key=lambda candidate: score(task, candidate))
            if best_options is None or len(options) < len(best_options):
                best_task = task
                best_options = options
        assert best_task is not None and best_options is not None
        for candidate in best_options:
            place(best_task, candidate)
            if backtrack():
                return True
            unplace(best_task, candidate)
        return False

    if not backtrack():
        raise ValueError("无法在目标截止日前完成基础/强化半天移动")
    return placed


def apply_moves(
    rows: Sequence[dict],
    groups: Dict[Tuple[str, ...], List[Tuple[int, dict]]],
    tasks: Sequence[scheduler.CourseBlock],
    placed: Dict[str, scheduler.Candidate],
    room_names: Dict[str, str],
) -> Tuple[List[dict], List[str]]:
    move_indices = {index for group_rows in groups.values() for index, _row in group_rows}
    result = [dict(row) for index, row in enumerate(rows) if index not in move_indices]
    lines: List[str] = []
    group_by_task_id: Dict[str, List[dict]] = {}
    for task in tasks:
        for key, group_rows in groups.items():
            if clean(group_rows[0][1].get("class_id")) == task.class_id and clean(group_rows[0][1].get("course_module")) == clean(task.course_module):
                old_key = key
                break
        else:
            raise ValueError(f"找不到任务原始行: {task.task_id}")
        group_by_task_id[task.task_id] = [dict(row) for _index, row in sorted(groups[old_key], key=lambda item: clean(item[1].get("lesson_slot")))]

    used_old_keys: Set[Tuple[str, ...]] = set()
    for task in tasks:
        candidate = placed[task.task_id]
        matching_key = next(
            key
            for key, group_rows in groups.items()
            if key not in used_old_keys
            and clean(group_rows[0][1].get("class_id")) == task.class_id
            and clean(group_rows[0][1].get("subject")) == task.subject
            and clean(group_rows[0][1].get("stage")) == clean(task.stage)
            and clean(group_rows[0][1].get("course_module")) == clean(task.course_module)
            and clean(group_rows[0][1].get("course_group")) == clean(task.course_group)
            and clean(group_rows[0][1].get("teacher_id")) == clean(task.teacher_id)
        )
        used_old_keys.add(matching_key)
        original_rows = [dict(row) for _index, row in sorted(groups[matching_key], key=lambda item: clean(item[1].get("lesson_slot")))]
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
        lines.append(
            f"{task.class_id} {task.subject}/{task.stage or ''}/{task.course_module or ''}: "
            f"{matching_key[1]} {matching_key[2]} -> {candidate.slots[0].date} {candidate.slots[0].period}"
        )
    return result, lines


def singleton_halfday_count(rows: Sequence[dict], deadlines: Dict[str, str]) -> int:
    totals: Counter[Tuple[str, str, str, str]] = Counter()
    for row in rows:
        if not target_foundation_row(row, deadlines):
            continue
        if clean(row.get("period")) not in {"AM", "PM"}:
            continue
        key = (
            clean(row.get("class_id")),
            clean(row.get("date")),
            clean(row.get("period")),
            clean(row.get("subject")),
        )
        totals[key] += float(row.get("duration_hours") or 0)
    return sum(1 for hours in totals.values() if hours == 2)


def write_report(path: Path, moved_lines: Sequence[str], deadlines: Dict[str, str], output_csv: Path, output_html: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "# 无忧秋/无忧春基础强化截止日调整报告",
                "",
                f"- 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                f"- 输出 CSV: {output_csv}",
                f"- 输出 HTML: {output_html}",
                "",
                "## 截止日",
                "",
                *[f"- {suite}: {deadline}" for suite, deadline in sorted(deadlines.items())],
                "",
                "## 移动明细",
                "",
                *[f"- {line}" for line in moved_lines],
                "",
            ]
        ),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="将指定无忧秋/无忧春套班基础+强化公共课提前到截止日前")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--schedule-csv", default=str(maintenance.OUTPUT_CSV))
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    schedule_csv = Path(args.schedule_csv)
    deadlines = dict(DEFAULT_DEADLINES)
    rows = load_rows(schedule_csv)
    if not rows:
        raise ValueError(f"课表为空: {schedule_csv}")
    fieldnames = list(rows[0].keys())
    groups = collect_late_halfday_groups(rows, deadlines)
    if not groups:
        print("没有发现超出截止日的基础/强化公共课。")
        return

    move_indices = {index for group_rows in groups.values() for index, _row in group_rows}
    locked_rows = [row for index, row in enumerate(rows) if index not in move_indices]
    class_ids = {clean(group_rows[0][1].get("class_id")) for group_rows in groups.values()}
    class_metadata = maintenance.load_class_metadata(data_dir)
    source = gap_repair.transformed_schedule_input(data_dir, class_ids, class_metadata)
    source = replace(source, locked_assignments=maintenance.assignments_from_rows(locked_rows, "DEADLINE_LOCK"))
    source = maintenance.with_conflict_groups_for_locked(data_dir, source, source.locked_assignments)

    tasks: List[scheduler.CourseBlock] = []
    for index, (_key, group_rows) in enumerate(sorted(groups.items()), start=1):
        tasks.append(build_move_task(source, group_rows[0][1], f"DEADLINE_MOVE:{index}"))
    placed = solve_moves(source, tasks, deadlines)

    room_names = maintenance.load_room_names(data_dir)
    moved_rows, moved_lines = apply_moves(rows, groups, tasks, placed, room_names)
    assignments = maintenance.assignments_from_rows(moved_rows, "DEADLINE_OUT")
    teacher_conflicts = maintenance.teacher_time_conflict_lines(assignments)
    if teacher_conflicts:
        raise ValueError("调整后仍有老师硬冲突: " + "；".join(teacher_conflicts[:5]))
    singleton_count = singleton_halfday_count(moved_rows, deadlines)
    if singleton_count:
        raise ValueError(f"调整后仍有同班同科半天 2h 孤块: {singleton_count}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.publish:
        backup_stem = f"before_wyqc_deadline_adjust_{timestamp}"
        for path in (maintenance.OUTPUT_CSV, maintenance.OUTPUT_HTML, maintenance.OUTPUT_REPORT):
            if path.exists():
                shutil.copyfile(path, path.with_name(f"{path.stem}.{backup_stem}{path.suffix}"))
        output_csv = maintenance.OUTPUT_CSV
        output_html = maintenance.OUTPUT_HTML
        output_report = Path("outputs") / f"wyqc_foundation_deadline_adjust_report_{timestamp}.md"
    else:
        output_csv = Path("outputs") / f"wyqc_foundation_deadline_adjust_{timestamp}.csv"
        output_html = Path("outputs") / f"wyqc_foundation_deadline_adjust_{timestamp}.html"
        output_report = Path("outputs") / f"wyqc_foundation_deadline_adjust_report_{timestamp}.md"

    write_rows(output_csv, moved_rows, fieldnames)
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
    write_report(output_report, moved_lines, deadlines, output_csv, output_html)

    if args.publish:
        shutil.copyfile(maintenance.OUTPUT_CSV, maintenance.LEGACY_OUTPUT_CSV)
        shutil.copyfile(maintenance.OUTPUT_HTML, maintenance.LEGACY_OUTPUT_HTML)
        shutil.copyfile(output_report, maintenance.LEGACY_OUTPUT_REPORT)
        with maintenance.OUTPUT_REPORT.open("a", encoding="utf-8") as handle:
            handle.write("\n\n## 无忧秋/无忧春基础强化截止日调整\n\n")
            handle.write(f"- 专项报告: {output_report}\n")
            for suite, deadline in sorted(deadlines.items()):
                handle.write(f"- {suite}: 基础+强化公共课已控制在 {deadline} 前。\n")
            handle.write(f"- 移动完整半天数: {len(moved_lines)}\n")

    print(f"已写出: {output_csv}")
    print(f"已写出: {output_html}")
    print(f"专项报告: {output_report}")
    print(f"移动完整半天数: {len(moved_lines)}")


if __name__ == "__main__":
    main()
