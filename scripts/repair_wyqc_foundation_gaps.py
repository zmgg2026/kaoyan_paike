#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
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
from scripts import audit_schedule_coverage as coverage
from scripts import build_camp_maintenance_schedule as maintenance
from scripts.schedule_display import assignment_standard_lesson_count
from scripts.schedule_outputs import write_batch_csv, write_day_table_html


PUBLIC_SUBJECTS = maintenance.SUMMER_PUBLIC_SUBJECTS
TARGET_STAGES = {"基础", "强化"}
TARGET_PRODUCTS = maintenance.WYQC_PRODUCTS
PUBLIC_HALFDAY_HOURS = 4


def clean(value: object) -> str:
    return str(value or "").strip()


def suite_window(suite_code: str) -> Tuple[str, str]:
    return (
        maintenance.WYQC_SUMMER_START,
        maintenance.WYQC_FOUNDATION_END_BY_SUITE.get(
            suite_code,
            maintenance.WYQC_FOUNDATION_END,
        ),
    )


def class_sub_product(class_metadata: Dict[str, Dict[str, str]], class_id: str) -> str:
    return clean(class_metadata.get(class_id, {}).get("sub_product"))


def class_is_movable_public(class_metadata: Dict[str, Dict[str, str]], class_id: str) -> bool:
    meta = class_metadata.get(class_id, {})
    locked = clean(meta.get("is_schedule_locked")).lower()
    return (
        clean(meta.get("subject_category")) == "公共课"
        and locked not in {"是", "1", "true", "yes", "y"}
    )


def build_module_gap_rows(data_dir: Path, schedule_csv: Path) -> List[dict]:
    schedule_input = scheduler.load_input(data_dir / "scheduler_input_draft.json")
    class_metadata = coverage.load_class_metadata(data_dir)
    expected = coverage.expected_hours(schedule_input, ignore_teacher=True)
    scheduled = coverage.scheduled_hours(schedule_csv, ignore_teacher=True)
    expected_totals = coverage.class_totals(expected)
    scheduled_totals = coverage.class_totals(scheduled)

    missing_class_ids = {
        class_id
        for class_id, expected_value in expected_totals.items()
        if expected_value > scheduled_totals[class_id]
        and class_metadata.get(class_id)
        and class_metadata[class_id].sub_product in TARGET_PRODUCTS
    }
    rows: List[dict] = []
    for key in sorted(set(expected) | set(scheduled)):
        class_id, subject, quarter, stage, course_module, course_group, _teacher_id = key
        if class_id not in missing_class_ids or stage not in TARGET_STAGES:
            continue
        diff = float(expected[key]) - float(scheduled[key])
        if diff <= 0:
            continue
        meta = class_metadata[class_id]
        rows.append(
            {
                "class_id": class_id,
                "class_name": meta.class_name,
                "sub_product": meta.sub_product,
                "subject_category": meta.subject_category,
                "class_subject": meta.subject,
                "suite_code": meta.suite_code,
                "subject": subject,
                "quarter": quarter,
                "stage": stage,
                "course_module": course_module,
                "course_group": course_group,
                "diff_hours": diff,
            }
        )
    return rows


def write_rows(path: Path, rows: Sequence[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def module_key_from_row(row: dict) -> Tuple[str, str, str, str, str, str]:
    return (
        clean(row.get("class_id")),
        clean(row.get("subject")),
        clean(row.get("quarter")),
        clean(row.get("stage")),
        clean(row.get("course_module")),
        clean(row.get("course_group")),
    )


def module_key_without_module(key: Tuple[str, str, str, str, str, str]) -> Tuple[str, str, str, str, str]:
    class_id, subject, quarter, stage, _module, group = key
    return class_id, subject, quarter, stage, group


def build_module_diffs(
    data_dir: Path,
    schedule_csv: Path,
) -> Tuple[Counter[Tuple[str, str, str, str, str, str]], Counter[Tuple[str, str, str, str, str, str]]]:
    schedule_input = scheduler.load_input(data_dir / "scheduler_input_draft.json")
    class_metadata = coverage.load_class_metadata(data_dir)
    expected = coverage.expected_hours(schedule_input, ignore_teacher=True)
    scheduled = coverage.scheduled_hours(schedule_csv, ignore_teacher=True)
    gaps: Counter[Tuple[str, str, str, str, str, str]] = Counter()
    overages: Counter[Tuple[str, str, str, str, str, str]] = Counter()
    for key in sorted(set(expected) | set(scheduled)):
        class_id, subject, quarter, stage, module, group, _teacher_id = key
        meta = class_metadata.get(class_id)
        if (
            not meta
            or meta.sub_product not in TARGET_PRODUCTS
            or stage not in TARGET_STAGES
            or subject not in PUBLIC_SUBJECTS
        ):
            continue
        diff = float(expected[key]) - float(scheduled[key])
        module_key = (class_id, subject, quarter, stage, module, group)
        if diff > 0:
            gaps[module_key] += diff
        elif diff < 0:
            overages[module_key] += -diff
    return gaps, overages


def relabel_public_halfday_overages(
    rows: Sequence[dict],
    data_dir: Path,
) -> Tuple[List[dict], List[str], Path]:
    """Use exact 4h overage half-days to fill matching module gaps before adding new lessons."""
    working_rows = [dict(row) for row in rows]
    temp_path = Path("/tmp") / f"wyqc_relabel_source_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    write_rows(temp_path, working_rows)
    gaps, overages = build_module_diffs(data_dir, temp_path)
    if not gaps or not overages:
        return working_rows, [], temp_path

    gaps_by_context: Dict[Tuple[str, str, str, str, str], List[Tuple[str, str, str, str, str, str]]] = defaultdict(list)
    for key, hours in gaps.items():
        if hours >= PUBLIC_HALFDAY_HOURS:
            gaps_by_context[module_key_without_module(key)].append(key)
    for keys in gaps_by_context.values():
        keys.sort()

    grouped_indices: Dict[Tuple[str, str, str, str, str, str, str, str, str, str], List[int]] = defaultdict(list)
    for index, row in enumerate(working_rows):
        if clean(row.get("period")) not in {"AM", "PM"} or clean(row.get("subject")) not in PUBLIC_SUBJECTS:
            continue
        module_key = module_key_from_row(row)
        block_key = (
            *module_key,
            clean(row.get("teacher_id")),
            clean(row.get("room_id")),
            clean(row.get("date")),
            clean(row.get("period")),
        )
        grouped_indices[block_key].append(index)

    report_lines: List[str] = []
    for block_key, indices in sorted(grouped_indices.items(), key=lambda item: (item[0][-2], item[0][-1], item[0][0])):
        source_key = block_key[:6]
        if overages[source_key] < PUBLIC_HALFDAY_HOURS:
            continue
        total_hours = sum(float(working_rows[index].get("duration_hours") or 0) for index in indices)
        if total_hours != PUBLIC_HALFDAY_HOURS:
            continue
        context = module_key_without_module(source_key)
        target_key = next((key for key in gaps_by_context.get(context, []) if gaps[key] >= PUBLIC_HALFDAY_HOURS), None)
        if not target_key:
            continue
        if target_key == source_key:
            continue

        target_module = target_key[4]
        for index in indices:
            working_rows[index]["course_module"] = target_module
            working_rows[index]["course_code"] = ""
            working_rows[index]["course_name"] = ""
        gaps[target_key] -= PUBLIC_HALFDAY_HOURS
        overages[source_key] -= PUBLIC_HALFDAY_HOURS
        report_lines.append(
            f"{source_key[0]} {source_key[1]} {source_key[3]} {source_key[4]} -> {target_module} "
            f"{working_rows[indices[0]].get('date')} {working_rows[indices[0]].get('period')}"
        )

    write_rows(temp_path, working_rows)
    return working_rows, report_lines, temp_path


def transformed_schedule_input(
    data_dir: Path,
    class_ids: Iterable[str],
    class_metadata: Dict[str, Dict[str, str]],
) -> scheduler.ScheduleInput:
    source = maintenance.load_schedule_input_for_classes(data_dir, class_ids)
    wyqc_source = maintenance.with_wuyou_qc_stage_windows(source)
    wys_source = maintenance.with_wuyou_summer_stage_windows(source)
    classes: Dict[str, scheduler.SchoolClass] = {}
    for class_id, cls in source.classes.items():
        sub_product = class_sub_product(class_metadata, class_id)
        if sub_product in maintenance.WYQC_PRODUCTS:
            classes[class_id] = wyqc_source.classes.get(class_id, cls)
        elif sub_product == maintenance.WYS_PRODUCT:
            classes[class_id] = wys_source.classes.get(class_id, cls)
        else:
            classes[class_id] = cls
    source = replace(source, classes=classes)
    source = maintenance.with_preferred_class_rooms(source, class_metadata)
    source = maintenance.without_blackout_dates(
        source,
        maintenance.load_active_blackout_dates(data_dir),
    )
    source = maintenance.without_dates(source, maintenance.WUYOU_PRODUCT_BLACKOUT_DATES)
    return source


def requirement_matches_row(requirement: scheduler.Requirement, row: dict, include_teacher: bool = False) -> bool:
    if requirement.subject != clean(row.get("subject")):
        return False
    if clean(requirement.quarter) != clean(row.get("quarter")):
        return False
    if clean(requirement.stage) != clean(row.get("stage")):
        return False
    if clean(requirement.course_module) != clean(row.get("course_module")):
        return False
    if clean(requirement.course_group) != clean(row.get("course_group")):
        return False
    if include_teacher and clean(requirement.teacher_id) != clean(row.get("teacher_id")):
        return False
    return True


def find_requirement(cls: scheduler.SchoolClass, row: dict, include_teacher: bool = False) -> Optional[scheduler.Requirement]:
    for requirement in cls.requirements:
        if requirement_matches_row(requirement, row, include_teacher=include_teacher):
            return requirement
    return None


def task_from_requirement(
    cls: scheduler.SchoolClass,
    requirement: scheduler.Requirement,
    task_id: str,
    room_ids: Optional[Set[str]] = None,
) -> scheduler.CourseBlock:
    return scheduler.CourseBlock(
        task_id=task_id,
        class_id=cls.id,
        class_name=cls.name,
        product_id=cls.product_id,
        product_name=cls.product_name,
        class_size=cls.size,
        subject_category=requirement.subject_category,
        subject=requirement.subject,
        quarter=requirement.quarter,
        stage=requirement.stage,
        course_module=requirement.course_module,
        course_group=requirement.course_group,
        teacher_id=requirement.teacher_id,
        teacher_name=requirement.teacher_name,
        block_hours=PUBLIC_HALFDAY_HOURS,
        course_code=requirement.course_code,
        course_name=requirement.course_name,
        room_ids=room_ids if room_ids is not None else requirement.room_ids,
        start_date=requirement.start_date,
        end_date=requirement.end_date,
        allowed_periods=requirement.allowed_periods,
        allowed_weekdays=requirement.allowed_weekdays,
        excluded_weekdays=requirement.excluded_weekdays,
        schedule_rules=requirement.schedule_rules,
    )


def task_from_existing_row(
    row: dict,
    source: scheduler.ScheduleInput,
    task_id: str,
    window_start: str,
    window_end: str,
) -> scheduler.CourseBlock:
    cls = source.classes.get(clean(row.get("class_id")))
    requirement = find_requirement(cls, row, include_teacher=True) if cls else None
    if cls and requirement:
        return task_from_requirement(
            cls,
            requirement,
            task_id,
            room_ids={clean(row.get("room_id"))},
        )
    return scheduler.CourseBlock(
        task_id=task_id,
        class_id=clean(row.get("class_id")),
        class_name=clean(row.get("class_name")) or clean(row.get("class_id")),
        product_id=None,
        product_name=None,
        class_size=None,
        subject_category=clean(row.get("subject_category")) or "公共课",
        subject=clean(row.get("subject")),
        quarter=clean(row.get("quarter")) or None,
        stage=clean(row.get("stage")) or None,
        course_module=clean(row.get("course_module")) or None,
        course_group=clean(row.get("course_group")) or None,
        teacher_id=clean(row.get("teacher_id")),
        teacher_name=clean(row.get("teacher_name")),
        block_hours=2,
        course_code=clean(row.get("course_code")),
        course_name=clean(row.get("course_name")),
        room_ids={clean(row.get("room_id"))},
        start_date=window_start,
        end_date=window_end,
        allowed_periods={"AM", "PM"},
        allowed_weekdays={0, 1, 2, 3, 4, 5},
        excluded_weekdays=None,
        schedule_rules=(),
    )


def candidate_date(candidate: scheduler.Candidate) -> str:
    return candidate.slots[0].date if candidate.slots else ""


def solve_suite(
    data_dir: Path,
    current_rows: Sequence[dict],
    suite_code: str,
    gap_rows: Sequence[dict],
    class_metadata: Dict[str, Dict[str, str]],
) -> Tuple[List[dict], List[scheduler.Assignment], List[str]]:
    window_start, window_end = suite_window(suite_code)
    target_class_ids = {clean(row.get("class_id")) for row in gap_rows}

    probe_source = transformed_schedule_input(data_dir, target_class_ids, class_metadata)
    for row in gap_rows:
        cls = probe_source.classes[clean(row.get("class_id"))]
        requirement = find_requirement(cls, row, include_teacher=False)
        if not requirement:
            raise ValueError(f"{suite_code} 找不到缺口课程需求: {row}")

    source = transformed_schedule_input(data_dir, target_class_ids, class_metadata)
    source = replace(
        source,
        locked_assignments=maintenance.assignments_from_rows(current_rows, f"LOCKED:{suite_code}"),
    )
    source = maintenance.with_conflict_groups_for_locked(
        data_dir,
        source,
        source.locked_assignments,
    )

    tasks: List[scheduler.CourseBlock] = []
    for row in gap_rows:
        cls = source.classes[clean(row.get("class_id"))]
        requirement = find_requirement(cls, row, include_teacher=False)
        if not requirement:
            raise ValueError(f"{suite_code} 找不到缺口课程需求: {row}")
        if float(row["diff_hours"]) % PUBLIC_HALFDAY_HOURS:
            raise ValueError(f"{suite_code} 缺口不是 4h 半天整块: {row}")
        lesson_count = int(round(float(row["diff_hours"]) / PUBLIC_HALFDAY_HOURS))
        for index in range(lesson_count):
            tasks.append(
                task_from_requirement(
                    cls,
                    requirement,
                    f"MISS:{suite_code}:{len(tasks) + 1}:{index + 1}",
                )
            )

    assignments = solve_half_day_tasks(
        source,
        tasks,
        window_start,
        window_end,
    )
    lines = [
        f"{suite_code}: 缺口 {sum(float(row['diff_hours']) for row in gap_rows):.1f}h，"
        f"新增 {len(assignments)} 个 4h 完整半天课节。"
    ]
    return list(current_rows), assignments, lines


def week_start(date_text: str) -> str:
    day = Date.fromisoformat(date_text)
    return (day - timedelta(days=day.weekday())).isoformat()


def solve_half_day_tasks(
    source: scheduler.ScheduleInput,
    tasks: Sequence[scheduler.CourseBlock],
    window_start: str,
    window_end: str,
) -> List[scheduler.Assignment]:
    class_slot_used, teacher_slot_used, room_slot_used, conflict_group_slot_used = scheduler.locked_constraint_sets(source)
    class_teacher_day_loads: Counter[Tuple[str, str, str]] = Counter()
    class_subject_day_loads: Counter[Tuple[str, str, str]] = Counter()
    class_week_loads: Counter[Tuple[str, str]] = Counter()
    class_subject_week_loads: Counter[Tuple[str, str, str]] = Counter()

    for assignment in source.locked_assignments:
        teacher_key = assignment.candidate.teacher_id or assignment.candidate.teacher_name
        for slot in assignment.candidate.slots:
            class_teacher_day_loads[(assignment.task.class_id, teacher_key, slot.date)] += slot.duration_hours
            class_subject_day_loads[(assignment.task.class_id, assignment.task.subject, slot.date)] += slot.duration_hours
            if assignment.task.subject in PUBLIC_SUBJECTS:
                week = week_start(slot.date)
                class_week_loads[(assignment.task.class_id, week)] += slot.duration_hours
                class_subject_week_loads[(assignment.task.class_id, assignment.task.subject, week)] += slot.duration_hours

    domains: Dict[str, List[scheduler.Candidate]] = {}
    for task in tasks:
        candidates = [
            candidate
            for candidate in scheduler.candidate_assignments(task, source)
            if len(candidate.slots) == 2
            and sum(slot.duration_hours for slot in candidate.slots) == PUBLIC_HALFDAY_HOURS
            and window_start <= candidate_date(candidate) <= window_end
        ]
        if not candidates:
            raise ValueError(f"{task.task_id} 没有可用 4h 候选半天")
        domains[task.task_id] = candidates

    task_by_id = {task.task_id: task for task in tasks}
    placed: Dict[str, scheduler.Assignment] = {}

    def valid(task: scheduler.CourseBlock, candidate: scheduler.Candidate) -> bool:
        class_group_ids = source.class_conflict_groups.get(task.class_id, set())
        teacher_key = candidate.teacher_id or candidate.teacher_name
        for slot in candidate.slots:
            if (task.class_id, slot.id) in class_slot_used:
                return False
            if candidate.teacher_id and (candidate.teacher_id, slot.id) in teacher_slot_used:
                return False
            if (candidate.room_id, slot.id) in room_slot_used:
                return False
            if any((group_id, slot.id) in conflict_group_slot_used for group_id in class_group_ids):
                return False
            if class_teacher_day_loads[(task.class_id, teacher_key, slot.date)] + task.block_hours > 8:
                return False
            if class_subject_day_loads[(task.class_id, task.subject, slot.date)] + task.block_hours > PUBLIC_HALFDAY_HOURS:
                return False
        return True

    def place(task: scheduler.CourseBlock, candidate: scheduler.Candidate) -> None:
        placed[task.task_id] = scheduler.Assignment(task=task, candidate=candidate)
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
            week = week_start(slot.date)
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
            week = week_start(slot.date)
            class_week_loads[(task.class_id, week)] -= slot.duration_hours
            class_subject_week_loads[(task.class_id, task.subject, week)] -= slot.duration_hours

    def candidate_score(task: scheduler.CourseBlock, candidate: scheduler.Candidate) -> Tuple[object, ...]:
        slot = candidate.slots[0]
        week = week_start(slot.date)
        return (
            class_subject_week_loads[(task.class_id, task.subject, week)],
            class_week_loads[(task.class_id, week)],
            slot.date,
            scheduler.period_sort_value(slot.period),
            slot.order,
            candidate.room_id,
        )

    sys.setrecursionlimit(max(10000, len(tasks) * 5))
    call_count = 0
    max_calls = max(200000, len(tasks) * 2000)

    def backtrack() -> bool:
        nonlocal call_count
        call_count += 1
        if call_count > max_calls:
            return False
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
        remaining = [task_id for task_id in task_by_id if task_id not in placed]
        raise ValueError(f"4h 半天补课时未能排完，剩余 {len(remaining)} 个: {', '.join(remaining[:10])}")
    return scheduler.sorted_assignments(placed.values())


def write_repair_report(path: Path, lines: Sequence[str], output_csv: Path, output_html: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "# 无忧秋/无忧春基础强化段课时补齐报告",
                "",
                f"- 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                f"- 输出 CSV: {output_csv}",
                f"- 输出 HTML: {output_html}",
                "",
                "## 执行明细",
                "",
                *[f"- {line}" for line in lines],
                "",
            ]
        ),
        encoding="utf-8",
    )


def inferred_base_report(schedule_csv: Path) -> Optional[Path]:
    if schedule_csv.suffix.lower() != ".csv":
        return None
    prefix = "batch_schedule_maintenance."
    if not schedule_csv.name.startswith(prefix):
        return None
    marker = schedule_csv.stem.removeprefix("batch_schedule_maintenance.")
    candidate = schedule_csv.with_name(f"batch_schedule_maintenance_report.{marker}.md")
    return candidate if candidate.exists() else None


def main() -> None:
    parser = argparse.ArgumentParser(description="专项补齐无忧秋/无忧春基础强化段缺口课时")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--schedule-csv", default=str(maintenance.OUTPUT_CSV))
    parser.add_argument("--base-report", default="", help="发布时用于重建主报告的底稿报告")
    parser.add_argument("--publish", action="store_true", help="覆盖正式 batch_schedule_maintenance 输出")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    schedule_csv = Path(args.schedule_csv)
    base_report = Path(args.base_report) if args.base_report else inferred_base_report(schedule_csv)
    class_metadata = maintenance.load_class_metadata(data_dir)
    room_names = maintenance.load_room_names(data_dir)
    current_rows = maintenance.load_output_rows(schedule_csv)
    relabeled_rows, relabel_lines, relabel_csv = relabel_public_halfday_overages(
        current_rows,
        data_dir,
    )
    gap_rows = build_module_gap_rows(data_dir, relabel_csv)
    if not gap_rows and not relabel_lines:
        print("没有发现无忧秋/无忧春基础强化段总课时缺口。")
        return

    by_suite: Dict[str, List[dict]] = defaultdict(list)
    for row in gap_rows:
        by_suite[clean(row.get("suite_code"))].append(row)

    report_lines: List[str] = []
    if relabel_lines:
        report_lines.append(f"先将 {len(relabel_lines)} 个 4h 模块超排半天改标到同组缺口模块。")
        report_lines.extend(f"改标: {line}" for line in relabel_lines)
    working_rows = relabeled_rows
    for suite_code in sorted(by_suite):
        print(f"专项补齐 {suite_code}", flush=True)
        reused_rows, repaired_assignments, lines = solve_suite(
            data_dir,
            working_rows,
            suite_code,
            by_suite[suite_code],
            class_metadata,
        )
        report_lines.extend(lines)
        combined_assignments = maintenance.deduplicate_assignments(
            [
                *maintenance.assignments_from_rows(reused_rows, f"REUSED:{suite_code}"),
                *repaired_assignments,
            ]
        )
        temp_csv = Path("/tmp") / f"wyqc_foundation_repair_{suite_code}.csv"
        write_batch_csv(combined_assignments, temp_csv, room_names, class_metadata)
        working_rows = maintenance.load_output_rows(temp_csv)

    final_assignments = maintenance.deduplicate_assignments(
        maintenance.assignments_from_rows(working_rows, "WYQC_REPAIRED")
    )
    teacher_conflicts = maintenance.teacher_time_conflict_lines(final_assignments)
    if teacher_conflicts:
        raise ValueError("专项补课时后仍有老师硬冲突: " + "；".join(teacher_conflicts[:5]))

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.publish:
        backup_stem = f"before_wyqc_foundation_repair_{timestamp}"
        for path in (maintenance.OUTPUT_CSV, maintenance.OUTPUT_HTML, maintenance.OUTPUT_REPORT):
            if path.exists():
                shutil.copyfile(path, path.with_name(f"{path.stem}.{backup_stem}{path.suffix}"))
        if base_report and base_report.exists():
            shutil.copyfile(base_report, maintenance.OUTPUT_REPORT)
        output_csv = maintenance.OUTPUT_CSV
        output_html = maintenance.OUTPUT_HTML
        output_report = Path("outputs") / f"wyqc_foundation_gap_repair_report_{timestamp}.md"
    else:
        output_csv = Path("outputs") / f"wyqc_foundation_gap_repair_{timestamp}.csv"
        output_html = Path("outputs") / f"wyqc_foundation_gap_repair_{timestamp}.html"
        output_report = Path("outputs") / f"wyqc_foundation_gap_repair_report_{timestamp}.md"

    write_batch_csv(final_assignments, output_csv, room_names, class_metadata)
    write_day_table_html(
        final_assignments,
        output_html,
        "课表维护总表",
        ["AM", "PM", "EVENING"],
        room_names,
        final_assignments[0].candidate.slots[0].date if final_assignments else None,
        final_assignments[-1].candidate.slots[0].date if final_assignments else None,
        class_metadata,
        maintenance.load_all_class_window_constraint_items(data_dir),
    )
    maintenance.write_teacher_time_conflicts_csv(final_assignments, maintenance.TEACHER_CONFLICT_CSV, room_names)
    write_repair_report(output_report, report_lines, output_csv, output_html)

    if args.publish:
        shutil.copyfile(maintenance.OUTPUT_CSV, maintenance.LEGACY_OUTPUT_CSV)
        shutil.copyfile(maintenance.OUTPUT_HTML, maintenance.LEGACY_OUTPUT_HTML)
        shutil.copyfile(output_report, maintenance.LEGACY_OUTPUT_REPORT)
        with maintenance.OUTPUT_REPORT.open("a", encoding="utf-8") as handle:
            handle.write("\n\n## 无忧秋/无忧春基础强化段课时补齐\n\n")
            handle.write(f"- 专项报告: {output_report}\n")
            for line in report_lines:
                handle.write(f"- {line}\n")

    print(f"已写出: {output_csv}")
    print(f"已写出: {output_html}")
    print(f"专项报告: {output_report}")
    print(f"输出课节数: {assignment_standard_lesson_count(final_assignments)}")


if __name__ == "__main__":
    main()
