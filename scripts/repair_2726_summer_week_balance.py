#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import sys
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import date as Date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scheduler
from scripts import build_camp_maintenance_schedule as maintenance
from scripts import repair_wyqc_foundation_gaps as gap_repair
from scripts.csv_utils import read_csv_rows, write_csv_rows as write_csv_rows_with_fields
from scripts.schedule_display import week_start, weekday_label
from scripts.schedule_outputs import write_day_table_html


SUITE_CODE = "2726"
PUBLIC_SUBJECTS = {"英语", "政治", "数学"}
SUMMER_START = "2026-07-04"
SUMMER_END = "2026-08-31"
WEEK_SUBJECT_QUOTAS: Dict[Tuple[str, str], int] = {
    ("2026-06-29", "数学"): 1,
    ("2026-06-29", "政治"): 0,
    ("2026-06-29", "英语"): 1,
    ("2026-07-06", "数学"): 1,
    ("2026-07-06", "政治"): 1,
    ("2026-07-06", "英语"): 3,
    ("2026-07-13", "数学"): 2,
    ("2026-07-13", "政治"): 1,
    ("2026-07-13", "英语"): 2,
    ("2026-07-20", "数学"): 1,
    ("2026-07-20", "政治"): 1,
    ("2026-07-20", "英语"): 3,
    ("2026-07-27", "数学"): 1,
    ("2026-07-27", "政治"): 2,
    ("2026-07-27", "英语"): 2,
    ("2026-08-03", "数学"): 2,
    ("2026-08-03", "政治"): 1,
    ("2026-08-03", "英语"): 2,
    ("2026-08-10", "数学"): 1,
    ("2026-08-10", "政治"): 1,
    ("2026-08-10", "英语"): 3,
    ("2026-08-17", "数学"): 1,
    ("2026-08-17", "政治"): 1,
    ("2026-08-17", "英语"): 3,
    ("2026-08-24", "数学"): 2,
    ("2026-08-24", "政治"): 2,
    ("2026-08-24", "英语"): 2,
}


def clean(value: object) -> str:
    return str(value or "").strip()


def load_rows(path: Path) -> List[dict]:
    return read_csv_rows(path)


def write_rows(path: Path, rows: Sequence[dict], fieldnames: Sequence[str]) -> None:
    write_csv_rows_with_fields(path, fieldnames, rows, encoding="utf-8")


def is_target_row(row: dict) -> bool:
    return (
        clean(row.get("class_id")).endswith(SUITE_CODE)
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


def collect_groups(rows: Sequence[dict]) -> Dict[Tuple[str, ...], List[Tuple[int, dict]]]:
    groups: Dict[Tuple[str, ...], List[Tuple[int, dict]]] = defaultdict(list)
    for index, row in enumerate(rows):
        if is_target_row(row):
            groups[halfday_group_key(row)].append((index, row))
    for key, group_rows in groups.items():
        total = sum(float(row.get("duration_hours") or 0) for _index, row in group_rows)
        if total != 4:
            raise ValueError(f"2726 暑期课不是完整 4h 半天块: {key} = {total}h")
    return groups


def build_move_task(source: scheduler.ScheduleInput, row: dict, task_id: str) -> scheduler.CourseBlock:
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


def solve_balance(
    source: scheduler.ScheduleInput,
    tasks: Sequence[scheduler.CourseBlock],
) -> Dict[str, scheduler.Candidate]:
    class_slot_used, teacher_slot_used, room_slot_used, conflict_group_slot_used = scheduler.locked_constraint_sets(source)
    class_teacher_day_loads: Counter[Tuple[str, str, str]] = Counter()
    class_subject_day_loads: Counter[Tuple[str, str, str]] = Counter()
    used_subject_week: Counter[Tuple[str, str]] = Counter()
    used_week: Counter[str] = Counter()

    for assignment in source.locked_assignments:
        teacher_key = assignment.candidate.teacher_id or assignment.candidate.teacher_name
        for slot in assignment.candidate.slots:
            class_teacher_day_loads[(assignment.task.class_id, teacher_key, slot.date)] += slot.duration_hours
            class_subject_day_loads[(assignment.task.class_id, assignment.task.subject, slot.date)] += slot.duration_hours

    domains: Dict[str, List[scheduler.Candidate]] = {}
    for task in tasks:
        candidates = []
        for candidate in scheduler.candidate_assignments(task, source):
            if len(candidate.slots) != 2 or sum(slot.duration_hours for slot in candidate.slots) != 4:
                continue
            first = candidate.slots[0]
            if not (SUMMER_START <= first.date <= SUMMER_END):
                continue
            week = week_start(first.date)
            if WEEK_SUBJECT_QUOTAS.get((week, task.subject), 0) <= 0:
                continue
            candidates.append(candidate)
        if not candidates:
            raise ValueError(f"{task.class_id} {task.subject}/{task.course_module or ''} 没有可用暑期半天")
        domains[task.task_id] = candidates

    task_by_id = {task.task_id: task for task in tasks}
    placed: Dict[str, scheduler.Candidate] = {}

    def valid(task: scheduler.CourseBlock, candidate: scheduler.Candidate) -> bool:
        first = candidate.slots[0]
        week = week_start(first.date)
        subject_week_key = (week, task.subject)
        if used_subject_week[subject_week_key] >= WEEK_SUBJECT_QUOTAS[subject_week_key]:
            return False
        if used_week[week] >= sum(WEEK_SUBJECT_QUOTAS.get((week, subject), 0) for subject in PUBLIC_SUBJECTS):
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
        return (
            used_week[week],
            used_subject_week[(week, task.subject)],
            first.date,
            scheduler.period_sort_value(first.period),
            first.order,
        )

    def backtrack() -> bool:
        if len(placed) == len(tasks):
            return all(
                used_subject_week[(week, subject)] == quota
                for (week, subject), quota in WEEK_SUBJECT_QUOTAS.items()
            )
        best_task: Optional[scheduler.CourseBlock] = None
        best_options: Optional[List[scheduler.Candidate]] = None
        for task_id, task in task_by_id.items():
            if task_id in placed:
                continue
            options = [candidate for candidate in domains[task_id] if valid(task, candidate)]
            if not options:
                return False
            options.sort(key=lambda candidate: candidate_score(task, candidate))
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
        raise ValueError("2726 暑期周课量均衡未能求解")
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


def weekly_summary(rows: Sequence[dict]) -> List[dict]:
    loads: Counter[Tuple[str, str]] = Counter()
    for row in rows:
        if is_target_row(row):
            loads[(week_start(clean(row.get("date"))), clean(row.get("subject")))] += float(row.get("duration_hours") or 0) / 4
    weeks = sorted({week for week, _subject in loads} | {week for week, _subject in WEEK_SUBJECT_QUOTAS})
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


def singleton_halfday_count(rows: Sequence[dict]) -> int:
    totals: Counter[Tuple[str, str, str, str]] = Counter()
    for row in rows:
        if is_target_row(row):
            totals[(clean(row.get("class_id")), clean(row.get("date")), clean(row.get("period")), clean(row.get("subject")))] += float(row.get("duration_hours") or 0)
    return sum(1 for hours in totals.values() if hours == 2)


def write_report(path: Path, output_csv: Path, output_html: Path, moved_lines: Sequence[str], rows: Sequence[dict]) -> None:
    summary = weekly_summary(rows)
    lines = [
        "# 2726 暑期周课量均衡调整报告",
        "",
        f"- 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 输出 CSV: {output_csv}",
        f"- 输出 HTML: {output_html}",
        f"- 移动完整半天数: {len(moved_lines)}",
        "",
        "## 周课量",
        "",
        "| 周一日期 | 总半天 | 数学 | 政治 | 英语 |",
        "|---|---:|---:|---:|---:|",
    ]
    for item in summary:
        lines.append(
            f"| {item['week']} | {item['total']:.0f} | {item['数学']:.0f} | {item['政治']:.0f} | {item['英语']:.0f} |"
        )
    lines.extend(["", "## 移动明细", ""])
    lines.extend(f"- {line}" for line in moved_lines)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="均衡 2726 套班 7-8 月公共课周课量")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--schedule-csv", default=str(maintenance.OUTPUT_CSV))
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    schedule_csv = Path(args.schedule_csv)
    rows = load_rows(schedule_csv)
    if not rows:
        raise ValueError(f"课表为空: {schedule_csv}")
    fieldnames = list(rows[0].keys())
    groups = collect_groups(rows)
    move_indices = {index for group_rows in groups.values() for index, _row in group_rows}
    locked_rows = [row for index, row in enumerate(rows) if index not in move_indices]
    class_ids = {clean(group_rows[0][1].get("class_id")) for group_rows in groups.values()}
    class_metadata = maintenance.load_class_metadata(data_dir)
    source = gap_repair.transformed_schedule_input(data_dir, class_ids, class_metadata)
    source = replace(source, locked_assignments=maintenance.assignments_from_rows(locked_rows, "2726_BAL_LOCK"))
    source = maintenance.with_conflict_groups_for_locked(data_dir, source, source.locked_assignments)
    tasks = [
        build_move_task(source, group_rows[0][1], f"2726_SUMMER_BALANCE:{index}")
        for index, (_key, group_rows) in enumerate(sorted(groups.items()), start=1)
    ]
    placed = solve_balance(source, tasks)
    room_names = maintenance.load_room_names(data_dir)
    balanced_rows, moved_lines = apply_solution(rows, groups, tasks, placed, room_names)
    assignments = maintenance.assignments_from_rows(balanced_rows, "2726_BAL_OUT")
    teacher_conflicts = maintenance.teacher_time_conflict_lines(assignments)
    if teacher_conflicts:
        raise ValueError("2726 均衡后仍有老师硬冲突: " + "；".join(teacher_conflicts[:5]))
    singletons = singleton_halfday_count(balanced_rows)
    if singletons:
        raise ValueError(f"2726 均衡后仍有同班同科半天 2h 孤块: {singletons}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.publish:
        backup_stem = f"before_2726_summer_balance_{timestamp}"
        for path in (maintenance.OUTPUT_CSV, maintenance.OUTPUT_HTML, maintenance.OUTPUT_REPORT):
            if path.exists():
                shutil.copyfile(path, path.with_name(f"{path.stem}.{backup_stem}{path.suffix}"))
        output_csv = maintenance.OUTPUT_CSV
        output_html = maintenance.OUTPUT_HTML
        output_report = Path("outputs") / f"2726_summer_week_balance_report_{timestamp}.md"
    else:
        output_csv = Path("outputs") / f"2726_summer_week_balance_{timestamp}.csv"
        output_html = Path("outputs") / f"2726_summer_week_balance_{timestamp}.html"
        output_report = Path("outputs") / f"2726_summer_week_balance_report_{timestamp}.md"

    write_rows(output_csv, balanced_rows, fieldnames)
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
    write_report(output_report, output_csv, output_html, moved_lines, balanced_rows)

    if args.publish:
        shutil.copyfile(maintenance.OUTPUT_CSV, maintenance.LEGACY_OUTPUT_CSV)
        shutil.copyfile(maintenance.OUTPUT_HTML, maintenance.LEGACY_OUTPUT_HTML)
        shutil.copyfile(output_report, maintenance.LEGACY_OUTPUT_REPORT)
        with maintenance.OUTPUT_REPORT.open("a", encoding="utf-8") as handle:
            handle.write("\n\n## 2726 暑期周课量均衡调整\n\n")
            handle.write(f"- 专项报告: {output_report}\n")
            handle.write(f"- 移动完整半天数: {len(moved_lines)}\n")
            for item in weekly_summary(balanced_rows):
                handle.write(
                    f"- {item['week']}: 总{item['total']:.0f}，数学{item['数学']:.0f}，"
                    f"政治{item['政治']:.0f}，英语{item['英语']:.0f}\n"
                )

    print(f"已写出: {output_csv}")
    print(f"已写出: {output_html}")
    print(f"专项报告: {output_report}")
    print(f"移动完整半天数: {len(moved_lines)}")


if __name__ == "__main__":
    main()
