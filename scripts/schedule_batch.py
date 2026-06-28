#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from dataclasses import replace
from datetime import date as Date, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scheduler
from scripts.schedule_class_windows import (
    bounds_for_constraints,
    load_class_window_constraints,
    season_names_for_constraints,
)
from scripts.schedule_constraints import (
    assignment_constraint_sets,
    candidate_is_valid,
    class_teacher_day_loads,
    place_candidate,
)
from scripts.schedule_display import (
    assignment_period_key,
)
from scripts.schedule_data import (
    load_class_metadata,
    load_product_course_tags,
    load_room_names,
)
from scripts.schedule_first_lesson import (
    assignments_preserve_first_lesson_modules,
    first_lesson_candidate_allowed,
    first_lesson_module_violations,
    mark_first_lesson_anchor_done,
    replacement_preserves_first_lesson_module,
    stage_first_lesson_anchor_keys,
    stage_first_lesson_anchor_task_ids,
)
from scripts.schedule_stage_order import (
    assignments_preserve_stage_order,
    effective_task_stage_sort_rank,
    stage_order_candidate_allowed,
    stage_order_tasks_by_class,
    stage_order_violations,
)
from scripts.schedule_run_rules import (
    creates_adjacent_subject_day,
    creates_teacher_run_over_limit,
    creates_three_day_teacher_run,
    run_dates,
    run_dates_over_limit,
)
from scripts.schedule_outputs import course_text, write_batch_csv, write_day_table_html
from scripts.schedule_scope import (
    class_ids_for_suite_codes,
    date_in_range,
    filter_classes,
    filter_time_slots,
    filtered_schedule_input,
    normalize_date,
    selected_conflict_groups,
    slot_in_range,
    split_values,
)
from scripts.schedule_week_balance import (
    SubjectWeekBounds,
    average_subject_week_bounds_from_counts,
    balanced_capped_week_quotas,
    balanced_week_quotas,
    bounded_week_quotas,
    bounded_subject_week_quotas,
    effective_week_count_for_slot_blocks,
    evenly_spaced_week_subset,
    front_loaded_week_quotas,
    long_camp_subject_week_bounds,
    long_camp_subject_week_hard_max,
    max_only_subject_week_limits,
    shift_tail_week_quota_to_early,
    slot_block_key,
    summer_camp_subject_week_bounds,
    subject_target_indices,
    sum_subject_week_quotas,
    week_key,
)


add_class_teacher_day_load = scheduler.add_class_teacher_day_load
candidate_avoids_same_class_teacher_day_limit = scheduler.candidate_avoids_same_class_teacher_day_limit
candidate_teacher_key = scheduler.candidate_teacher_key
candidate_hours_by_date = scheduler.candidate_hours_by_date
task_stage_rank = scheduler.task_stage_rank_for_input

SUBJECT_ORDER = {"数学": 0, "英语": 1, "政治": 2, "语文": 3}
PUBLIC_SUBJECTS = {"英语", "政治", "数学", "语文"}
SAME_CLASS_TEACHER_DAY_LIMIT_SUBJECTS = scheduler.SAME_CLASS_TEACHER_DAY_LIMIT_SUBJECTS
MAX_SAME_CLASS_TEACHER_DAY_HOURS = scheduler.MAX_SAME_CLASS_TEACHER_DAY_HOURS
SUMMER_PREFERRED_WEEKLY_HALFDAY_MAX = 11
CORE_TEACHER_CONSECUTIVE_LIMIT_SUBJECTS = {"英语", "政治"}
CORE_TEACHER_MAX_CONSECUTIVE_DAYS = 3
TEACHER_ALTERNATION_MAX_CONSECUTIVE_LESSONS = 3
LONG_CAMP_ALTERNATING_SUBJECTS = {"英语", "政治"}
LONG_CAMP_SUB_PRODUCTS = {"全年营", "半年营"}
WUYOU_SUB_PRODUCTS = {"无忧寒", "无忧暑", "无忧秋", "无忧春"}
LONG_CAMP_MATH_MAX_CONSECUTIVE_DAYS = 3


def load_locked_csv_assignments(
    paths: Sequence[Path],
    schedule_input: scheduler.ScheduleInput,
) -> List[scheduler.Assignment]:
    if not paths:
        return []

    blocks_by_key: Dict[Tuple[str, str, int, str, str], Tuple[scheduler.TimeSlot, ...]] = {}
    for duration in {2, 4, 6, 8}:
        for slot_block in scheduler.build_contiguous_slot_blocks(schedule_input.time_slots, duration):
            start_time = slot_block[0].start_time or ""
            end_time = slot_block[-1].end_time or ""
            blocks_by_key[(slot_block[0].date, slot_block[0].period, duration, start_time, end_time)] = slot_block
            blocks_by_key[(slot_block[0].date, slot_block[0].period, duration, "", "")] = slot_block

    assignments: List[scheduler.Assignment] = []
    for path in paths:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            for index, row in enumerate(csv.DictReader(handle), start=1):
                duration = int(float(row.get("duration_hours") or 0))
                key = (
                    row.get("date") or "",
                    (row.get("period") or "").upper(),
                    duration,
                    row.get("start_time") or "",
                    row.get("end_time") or "",
                )
                slot_block = blocks_by_key.get(key) or blocks_by_key.get((key[0], key[1], key[2], "", ""))
                if not slot_block:
                    raise ValueError(f"锁定课表 {path} 第 {index} 行无法匹配课节: {key[0]} {key[1]}")
                class_id = row.get("class_id") or f"LOCKED_CLASS_{index}"
                teacher_id = row.get("teacher_id") or ""
                teacher_name = row.get("teacher_name") or teacher_id
                room_id = row.get("room_id") or ""
                task = scheduler.CourseBlock(
                    task_id=f"LOCKED_CSV:{path.name}:{index}",
                    class_id=class_id,
                    class_name=row.get("class_name") or class_id,
                    product_id=None,
                    product_name=None,
                    class_size=None,
                    subject_category="",
                    subject=row.get("subject") or "已定课程",
                    quarter=row.get("quarter") or None,
                    stage=row.get("stage") or None,
                    course_module=row.get("course_module") or None,
                    course_group=row.get("course_group") or None,
                    teacher_id=teacher_id,
                    teacher_name=teacher_name,
                    block_hours=sum(slot.duration_hours for slot in slot_block),
                    room_ids={room_id} if room_id else None,
                    start_date=slot_block[0].date,
                    end_date=slot_block[-1].date,
                    allowed_periods={slot_block[0].period},
                    allowed_weekdays=None,
                    excluded_weekdays=None,
                    schedule_rules=(),
                    is_locked=True,
                    course_code=row.get("course_code") or "",
                    course_name=row.get("course_name") or "",
                )
                assignments.append(
                    scheduler.Assignment(
                        task=task,
                        candidate=scheduler.Candidate(
                            slots=slot_block,
                            teacher_id=teacher_id,
                            teacher_name=teacher_name,
                            room_id=room_id,
                        ),
                    )
                )
    return assignments


def subject_neighbor_teacher_repeat(
    assignments: Sequence[scheduler.Assignment],
    task: scheduler.CourseBlock,
    candidate: scheduler.Candidate,
) -> bool:
    teacher_key = candidate_teacher_key(candidate)
    if not teacher_key:
        return False
    candidate_date = candidate.slots[0].date
    previous: Optional[scheduler.Assignment] = None
    next_item: Optional[scheduler.Assignment] = None
    for assignment in assignments:
        if assignment.task.class_id != task.class_id or assignment.task.subject != task.subject:
            continue
        assignment_date = assignment.candidate.slots[0].date
        if assignment_date < candidate_date and (
            previous is None or assignment_date > previous.candidate.slots[0].date
        ):
            previous = assignment
        elif assignment_date > candidate_date and (
            next_item is None or assignment_date < next_item.candidate.slots[0].date
        ):
            next_item = assignment
    return any(
        candidate_teacher_key(item.candidate) == teacher_key
        for item in (previous, next_item)
        if item is not None
    )


def alternate_teacher_tasks(tasks: Sequence[scheduler.CourseBlock]) -> List[scheduler.CourseBlock]:
    by_teacher: Dict[str, List[scheduler.CourseBlock]] = {}
    teacher_order: List[str] = []
    for task in tasks:
        teacher_key = task.teacher_id or task.teacher_name
        if teacher_key not in by_teacher:
            by_teacher[teacher_key] = []
            teacher_order.append(teacher_key)
        by_teacher[teacher_key].append(task)
    if len(by_teacher) <= 1:
        return list(tasks)

    ordered: List[scheduler.CourseBlock] = []
    last_teacher = ""
    while any(by_teacher.values()):
        options = [teacher for teacher in teacher_order if by_teacher[teacher]]
        non_repeat_options = [teacher for teacher in options if teacher != last_teacher]
        pool = non_repeat_options or options
        pool.sort(key=lambda teacher: (-len(by_teacher[teacher]), teacher_order.index(teacher)))
        teacher = pool[0]
        ordered.append(by_teacher[teacher].pop(0))
        last_teacher = teacher
    return ordered


def replacement_candidate_for_assignment_slot(
    task: scheduler.CourseBlock,
    assignment: scheduler.Assignment,
    domains: Dict[str, List[scheduler.Candidate]],
) -> Optional[scheduler.Candidate]:
    slot_ids = tuple(slot.id for slot in assignment.candidate.slots)
    return next(
        (
            candidate
            for candidate in domains.get(task.task_id, [])
            if tuple(slot.id for slot in candidate.slots) == slot_ids
            and candidate.room_id == assignment.candidate.room_id
        ),
        None,
    )


def teacher_balanced_replacements_for_slots(
    subject_assignments: Sequence[scheduler.Assignment],
    domains: Dict[str, List[scheduler.Candidate]],
    first_lesson_anchor_task_ids: Set[str],
    max_consecutive_lessons: int = TEACHER_ALTERNATION_MAX_CONSECUTIVE_LESSONS,
) -> List[scheduler.Assignment]:
    remaining = [assignment.task for assignment in subject_assignments]
    if len({task.teacher_id or task.teacher_name for task in remaining}) <= 1:
        return []

    original_order = {task.task_id: index for index, task in enumerate(remaining)}
    replacements: List[scheduler.Assignment] = []
    last_teacher = ""
    current_run = 0
    group_anchor_ids = {task.task_id for task in remaining if task.task_id in first_lesson_anchor_task_ids}

    for position, old_assignment in enumerate(subject_assignments):
        remaining_by_teacher: Dict[str, int] = defaultdict(int)
        for task in remaining:
            remaining_by_teacher[task.teacher_id or task.teacher_name] += 1

        options: List[Tuple[Tuple[int, int, int, int, str], scheduler.CourseBlock, scheduler.Candidate]] = []
        for task in remaining:
            if position == 0 and group_anchor_ids and task.task_id not in group_anchor_ids:
                continue
            candidate = replacement_candidate_for_assignment_slot(task, old_assignment, domains)
            if candidate is None:
                continue
            teacher_key = task.teacher_id or task.teacher_name
            next_run = current_run + 1 if teacher_key and teacher_key == last_teacher else 1
            exceeds_run = int(next_run > max_consecutive_lessons)
            repeats_teacher = int(bool(teacher_key and teacher_key == last_teacher))
            options.append(
                (
                    (
                        exceeds_run,
                        repeats_teacher,
                        -remaining_by_teacher.get(teacher_key, 0),
                        original_order.get(task.task_id, 0),
                        task.task_id,
                    ),
                    task,
                    candidate,
                )
            )

        if not options:
            return []

        options.sort(key=lambda item: item[0])
        _score, selected_task, selected_candidate = options[0]
        replacements.append(scheduler.Assignment(task=selected_task, candidate=selected_candidate))
        remaining = [task for task in remaining if task.task_id != selected_task.task_id]
        selected_teacher = selected_task.teacher_id or selected_task.teacher_name
        if selected_teacher and selected_teacher == last_teacher:
            current_run += 1
        else:
            last_teacher = selected_teacher
            current_run = 1

    return replacements


def rebalance_subject_teacher_alternation(
    schedule_input: scheduler.ScheduleInput,
    assignments: Sequence[scheduler.Assignment],
    domains: Dict[str, List[scheduler.Candidate]],
    subjects: Set[str],
) -> List[scheduler.Assignment]:
    result = list(assignments)
    original_has_stage_violations = bool(stage_order_violations(schedule_input, result))
    stage_tasks_by_class = stage_order_tasks_by_class(schedule_input)
    first_lesson_anchor_task_ids = stage_first_lesson_anchor_task_ids(
        [assignment.task for assignment in result]
    )
    group_keys = sorted({
        (
            assignment.task.class_id,
            assignment.task.subject,
            effective_task_stage_sort_rank(schedule_input, stage_tasks_by_class, assignment.task),
        )
        for assignment in result
        if assignment.task.subject in subjects
    })
    for class_id, subject, stage_rank in group_keys:
        subject_assignments = [
            assignment
            for assignment in result
            if assignment.task.class_id == class_id
            and assignment.task.subject == subject
            and effective_task_stage_sort_rank(schedule_input, stage_tasks_by_class, assignment.task) == stage_rank
        ]
        if len(subject_assignments) <= 2:
            continue
        subject_assignments.sort(key=lambda assignment: scheduler.slot_sort_key(assignment.candidate.slots[0]))
        replacements = teacher_balanced_replacements_for_slots(
            subject_assignments,
            domains,
            first_lesson_anchor_task_ids,
        )
        if not replacements:
            continue
        replacement_by_date_period = {
            assignment_period_key(assignment): assignment for assignment in replacements
        }
        proposed = [
            replacement_by_date_period.get(assignment_period_key(assignment), assignment)
            if assignment.task.class_id == class_id and assignment.task.subject == subject
            else assignment
            for assignment in result
        ]
        if not assignments_preserve_first_lesson_modules(proposed):
            continue
        if not original_has_stage_violations and not assignments_preserve_stage_order(schedule_input, proposed):
            continue
        if not assignments_avoid_same_class_teacher_day_limit(schedule_input, proposed):
            continue
        if assignments_have_conflicts(schedule_input, proposed):
            continue
        result = proposed
    return result


def public_subject_sequence_score(
    assignments: Sequence[scheduler.Assignment],
    subjects: Set[str],
) -> int:
    grouped: Dict[Tuple[str, str], List[scheduler.Assignment]] = defaultdict(list)
    for assignment in assignments:
        if assignment.task.subject in subjects:
            grouped[(assignment.task.class_id, assignment.task.subject)].append(assignment)

    score = 0
    for items in grouped.values():
        items = sorted(items, key=lambda item: scheduler.slot_sort_key(item.candidate.slots[0]))
        by_date: Dict[str, int] = defaultdict(int)
        for item in items:
            by_date[item.candidate.slots[0].date] += 1
        for count in by_date.values():
            if count > 1:
                score += (count - 1) * 100_000

        dates = sorted(Date.fromisoformat(value) for value in by_date)
        for left, right in zip(dates, dates[1:]):
            if (right - left).days == 1:
                score += 12_000

        teachers = {candidate_teacher_key(item.candidate) for item in items if candidate_teacher_key(item.candidate)}
        if len(teachers) > 1:
            for left, right in zip(items, items[1:]):
                left_teacher = candidate_teacher_key(left.candidate)
                right_teacher = candidate_teacher_key(right.candidate)
                if left_teacher and left_teacher == right_teacher:
                    score += 4_000
    return score


def improve_public_subject_spacing(
    schedule_input: scheduler.ScheduleInput,
    assignments: Sequence[scheduler.Assignment],
    domains: Dict[str, List[scheduler.Candidate]],
    subjects: Set[str],
    preferred_subject_periods: Dict[str, str],
    max_subject_weekly_halfdays: Optional[object] = None,
    max_passes: int = 300,
) -> List[scheduler.Assignment]:
    result = scheduler.sorted_assignments(list(assignments))
    if not result:
        return result
    stage_tasks_by_class = stage_order_tasks_by_class(schedule_input)
    current_score = public_subject_sequence_score(result, subjects)
    if current_score <= 0:
        return result

    for _ in range(max_passes):
        improved = False
        indices = [
            index
            for index, assignment in enumerate(result)
            if assignment.task.subject in subjects
        ]
        indices.sort(
            key=lambda index: (
                result[index].candidate.slots[0].date,
                scheduler.period_sort_value(result[index].candidate.slots[0].period),
            )
        )
        for assignment_index in indices:
            assignment = result[assignment_index]
            task = assignment.task
            class_slot_used, teacher_slot_used, room_slot_used, conflict_group_slot_used = assignment_constraint_sets(
                schedule_input,
                result,
                excluded_index=assignment_index,
            )
            daily_teacher_loads = class_teacher_day_loads(
                schedule_input,
                result,
                excluded_index=assignment_index,
            )
            original_key = scheduler.slot_sort_key(assignment.candidate.slots[0])
            original_date = Date.fromisoformat(assignment.candidate.slots[0].date)
            preferred_period = preferred_subject_periods.get(task.subject)
            replacements: List[Tuple[Tuple[int, int, int, Tuple[str, int, int, str]], scheduler.Candidate]] = []

            for candidate in domains.get(task.task_id, []):
                if tuple(slot.id for slot in candidate.slots) == tuple(slot.id for slot in assignment.candidate.slots):
                    continue
                first_slot = candidate.slots[0]
                if not replacement_preserves_first_lesson_module(
                    result,
                    assignment_index,
                    task,
                    candidate,
                ):
                    continue
                if not stage_order_candidate_allowed(
                    schedule_input,
                    stage_tasks_by_class,
                    result,
                    task,
                    candidate,
                    excluded_index=assignment_index,
                ):
                    continue
                if not candidate_avoids_same_class_teacher_day_limit(
                    daily_teacher_loads,
                    task,
                    candidate,
                ):
                    continue
                if not candidate_is_valid(
                    schedule_input,
                    class_slot_used,
                    teacher_slot_used,
                    room_slot_used,
                    conflict_group_slot_used,
                    task,
                    candidate,
                ):
                    continue
                weekly_limit = (
                    max_subject_weekly_halfdays.get(task.subject)
                    if isinstance(max_subject_weekly_halfdays, dict)
                    else max_subject_weekly_halfdays
                )
                if weekly_limit is not None:
                    candidate_week = week_key(candidate.slots)
                    week_count = sum(
                        1
                        for index, item in enumerate(result)
                        if index != assignment_index
                        and item.task.class_id == task.class_id
                        and item.task.subject == task.subject
                        and week_key(item.candidate.slots) == candidate_week
                    )
                    if week_count >= weekly_limit:
                        continue
                proposed = list(result)
                proposed[assignment_index] = scheduler.Assignment(task=task, candidate=candidate)
                proposed_score = public_subject_sequence_score(proposed, subjects)
                if proposed_score >= current_score:
                    continue
                period_penalty = 0 if not preferred_period or first_slot.period == preferred_period else 1
                distance = abs((Date.fromisoformat(first_slot.date) - original_date).days)
                replacements.append(
                    (
                        (
                            proposed_score,
                            period_penalty,
                            distance,
                            scheduler.slot_sort_key(first_slot),
                        ),
                        candidate,
                    )
                )

            if not replacements:
                continue
            replacements.sort(key=lambda item: item[0])
            result[assignment_index] = scheduler.Assignment(task=task, candidate=replacements[0][1])
            result = scheduler.sorted_assignments(result)
            current_score = public_subject_sequence_score(result, subjects)
            improved = True
            break
        if not improved or current_score <= 0:
            break
    return result


def assignments_have_conflicts(
    schedule_input: scheduler.ScheduleInput,
    assignments: Sequence[scheduler.Assignment],
) -> bool:
    class_slot_used, teacher_slot_used, room_slot_used, conflict_group_slot_used = scheduler.locked_constraint_sets(schedule_input)
    for assignment in scheduler.sorted_assignments(list(assignments)):
        if not candidate_is_valid(
            schedule_input,
            class_slot_used,
            teacher_slot_used,
            room_slot_used,
            conflict_group_slot_used,
            assignment.task,
            assignment.candidate,
        ):
            return True
        place_candidate(
            schedule_input,
            class_slot_used,
            teacher_slot_used,
            room_slot_used,
            conflict_group_slot_used,
            assignment.task,
            assignment.candidate,
        )
    return False


def same_class_teacher_day_hour_violations(
    schedule_input: scheduler.ScheduleInput,
    assignments: Sequence[scheduler.Assignment],
) -> List[Tuple[str, str, str, str, float]]:
    selected_class_ids = {assignment.task.class_id for assignment in assignments}
    loads: Dict[Tuple[str, str, str], float] = {}
    labels: Dict[Tuple[str, str, str], str] = {}
    for assignment in [*schedule_input.locked_assignments, *assignments]:
        if selected_class_ids and assignment.task.class_id not in selected_class_ids:
            continue
        if assignment.task.subject not in SAME_CLASS_TEACHER_DAY_LIMIT_SUBJECTS:
            continue
        teacher_key = candidate_teacher_key(assignment.candidate)
        if not teacher_key:
            continue
        teacher_label = assignment.candidate.teacher_name or assignment.task.teacher_name or teacher_key
        for date_text, hours in candidate_hours_by_date(assignment.candidate).items():
            key = (assignment.task.class_id, teacher_key, date_text)
            loads[key] = loads.get(key, 0.0) + hours
            labels[key] = teacher_label
    return [
        (class_id, labels.get((class_id, teacher_key, date_text), teacher_key), date_text, teacher_key, hours)
        for (class_id, teacher_key, date_text), hours in sorted(loads.items())
        if hours >= MAX_SAME_CLASS_TEACHER_DAY_HOURS
    ]


def assignments_avoid_same_class_teacher_day_limit(
    schedule_input: scheduler.ScheduleInput,
    assignments: Sequence[scheduler.Assignment],
) -> bool:
    return not same_class_teacher_day_hour_violations(schedule_input, assignments)


def require_same_class_teacher_day_limit(
    schedule_input: scheduler.ScheduleInput,
    assignments: Sequence[scheduler.Assignment],
) -> List[scheduler.Assignment]:
    result = scheduler.sorted_assignments(list(assignments))
    violations = same_class_teacher_day_hour_violations(schedule_input, result)
    if violations:
        samples = [
            f"{class_id} {date_text} {teacher_label} {hours:g}小时"
            for class_id, teacher_label, date_text, _teacher_key, hours in violations[:8]
        ]
        raise ValueError("同班同师同天课时限制未满足: " + "；".join(samples))
    return result


def require_first_lesson_modules(
    assignments: Sequence[scheduler.Assignment],
) -> List[scheduler.Assignment]:
    result = scheduler.sorted_assignments(list(assignments))
    violations = first_lesson_module_violations(result)
    if violations:
        samples = []
        for key, required_module, first_assignment, anchor_assignment in violations[:8]:
            first_slot = first_assignment.candidate.slots[0]
            anchor_slot = anchor_assignment.candidate.slots[0]
            samples.append(
                f"{key[0]} {key[1]}{key[2]} 首节为 {first_assignment.task.course_module or '-'} "
                f"({first_slot.date} {first_slot.period})，需要先排 {required_module} "
                f"({anchor_slot.date} {anchor_slot.period})"
            )
        raise ValueError("基础阶段首课限制未满足: " + "；".join(samples))
    return result


def require_stage_order(
    schedule_input: scheduler.ScheduleInput,
    assignments: Sequence[scheduler.Assignment],
) -> List[scheduler.Assignment]:
    result = scheduler.sorted_assignments(list(assignments))
    violations = stage_order_violations(schedule_input, result)
    if violations:
        samples = []
        for class_id, lower_stage, higher_stage, latest_lower, earliest_higher in violations[:8]:
            lower_slot = latest_lower.candidate.slots[-1]
            higher_slot = earliest_higher.candidate.slots[0]
            samples.append(
                f"{class_id} {lower_stage} 最后一节 {lower_slot.date} {lower_slot.period} "
                f"未早于 {higher_stage} 第一节 {higher_slot.date} {higher_slot.period}"
            )
        raise ValueError("阶段顺序限制未满足: " + "；".join(samples))
    return result


def require_schedule_order(
    schedule_input: scheduler.ScheduleInput,
    assignments: Sequence[scheduler.Assignment],
) -> List[scheduler.Assignment]:
    return require_same_class_teacher_day_limit(
        schedule_input,
        require_stage_order(schedule_input, require_first_lesson_modules(assignments)),
    )


def subject_week_loads_for(
    assignments: Sequence[scheduler.Assignment],
    subject: str,
) -> Dict[Tuple[int, int], int]:
    loads: Dict[Tuple[int, int], int] = {}
    for assignment in assignments:
        if assignment.task.subject != subject:
            continue
        key = week_key(assignment.candidate.slots)
        loads[key] = loads.get(key, 0) + 1
    return loads


def week_loads_for(assignments: Sequence[scheduler.Assignment]) -> Dict[Tuple[int, int], int]:
    loads: Dict[Tuple[int, int], int] = {}
    for assignment in assignments:
        key = week_key(assignment.candidate.slots)
        loads[key] = loads.get(key, 0) + 1
    return loads


def subject_dates_for(
    assignments: Sequence[scheduler.Assignment],
    subject: str,
    excluded_index: Optional[int] = None,
) -> Set[str]:
    dates: Set[str] = set()
    for index, assignment in enumerate(assignments):
        if excluded_index is not None and index == excluded_index:
            continue
        if assignment.task.subject == subject:
            dates.add(assignment.candidate.slots[0].date)
    return dates


def improve_total_week_balance(
    schedule_input: scheduler.ScheduleInput,
    assignments: Sequence[scheduler.Assignment],
    domains: Dict[str, List[scheduler.Candidate]],
    week_quotas: Dict[Tuple[int, int], int],
    preferred_subject_periods: Dict[str, str],
) -> List[scheduler.Assignment]:
    result = scheduler.sorted_assignments(list(assignments))
    stage_tasks_by_class = stage_order_tasks_by_class(schedule_input)
    for _ in range(30):
        loads = week_loads_for(result)
        under_weeks = [
            key for key, quota in sorted(week_quotas.items()) if loads.get(key, 0) < quota
        ]
        over_weeks = [
            key for key, load in sorted(loads.items()) if load > week_quotas.get(key, load)
        ]
        if not under_weeks or not over_weeks:
            break
        moved = False
        for under_week in under_weeks:
            over_weeks.sort(key=lambda key: (loads.get(key, 0) - week_quotas.get(key, 0), key), reverse=True)
            for over_week in over_weeks:
                candidate_indices = [
                    index
                    for index, assignment in enumerate(result)
                    if week_key(assignment.candidate.slots) == over_week
                ]
                candidate_indices.sort(reverse=True)
                for assignment_index in candidate_indices:
                    assignment = result[assignment_index]
                    class_slot_used, teacher_slot_used, room_slot_used, conflict_group_slot_used = assignment_constraint_sets(
                        schedule_input,
                        result,
                        excluded_index=assignment_index,
                    )
                    daily_teacher_loads = class_teacher_day_loads(
                        schedule_input,
                        result,
                        excluded_index=assignment_index,
                    )
                    used_subject_dates = subject_dates_for(
                        result,
                        assignment.task.subject,
                        excluded_index=assignment_index,
                    )
                    used_teacher_dates = teacher_dates_for(
                        result,
                        assignment.candidate.teacher_id,
                        excluded_index=assignment_index,
                    )
                    replacements: List[scheduler.Candidate] = []
                    for candidate in domains[assignment.task.task_id]:
                        first_slot = candidate.slots[0]
                        if week_key(candidate.slots) != under_week:
                            continue
                        preferred_period = preferred_subject_periods.get(assignment.task.subject)
                        if preferred_period and first_slot.period != preferred_period:
                            continue
                        if first_slot.date in used_subject_dates:
                            continue
                        if assignment.task.subject in {"英语", "政治"} and creates_three_day_teacher_run(
                            used_teacher_dates,
                            first_slot.date,
                        ):
                            continue
                        if assignment.task.subject == "数学" and creates_three_day_teacher_run(
                            used_subject_dates,
                            first_slot.date,
                        ):
                            continue
                        if not replacement_preserves_first_lesson_module(
                            result,
                            assignment_index,
                            assignment.task,
                            candidate,
                        ):
                            continue
                        if not stage_order_candidate_allowed(
                            schedule_input,
                            stage_tasks_by_class,
                            result,
                            assignment.task,
                            candidate,
                            excluded_index=assignment_index,
                        ):
                            continue
                        if not candidate_avoids_same_class_teacher_day_limit(
                            daily_teacher_loads,
                            assignment.task,
                            candidate,
                        ):
                            continue
                        if not candidate_is_valid(
                            schedule_input,
                            class_slot_used,
                            teacher_slot_used,
                            room_slot_used,
                            conflict_group_slot_used,
                            assignment.task,
                            candidate,
                        ):
                            continue
                        replacements.append(candidate)
                    if not replacements:
                        continue
                    replacements.sort(
                        key=lambda candidate: (
                            candidate.slots[0].date,
                            scheduler.period_sort_value(candidate.slots[0].period),
                            candidate.room_id,
                        )
                    )
                    result[assignment_index] = scheduler.Assignment(
                        task=assignment.task,
                        candidate=replacements[0],
                    )
                    result = scheduler.sorted_assignments(result)
                    moved = True
                    break
                if moved:
                    break
            if moved:
                break
        if not moved:
            break
    return result


def teacher_dates_for(
    assignments: Sequence[scheduler.Assignment],
    teacher_id: str,
    excluded_index: Optional[int] = None,
) -> Set[str]:
    dates: Set[str] = set()
    for index, assignment in enumerate(assignments):
        if excluded_index is not None and index == excluded_index:
            continue
        if assignment.candidate.teacher_id == teacher_id:
            dates.add(assignment.candidate.slots[0].date)
    return dates


def improve_subject_week_balance(
    schedule_input: scheduler.ScheduleInput,
    assignments: Sequence[scheduler.Assignment],
    domains: Dict[str, List[scheduler.Candidate]],
    subject_week_quotas: Dict[str, Dict[Tuple[int, int], int]],
    preferred_subject_periods: Dict[str, str],
    subjects: Set[str],
    math_max_consecutive_days: Optional[int] = None,
) -> List[scheduler.Assignment]:
    result = scheduler.sorted_assignments(list(assignments))
    stage_tasks_by_class = stage_order_tasks_by_class(schedule_input)
    for subject in subjects:
        quotas = subject_week_quotas.get(subject, {})
        if not quotas:
            continue
        for _ in range(160):
            loads = subject_week_loads_for(result, subject)
            over_weeks = [
                key for key, load in loads.items() if load > quotas.get(key, load)
            ]
            under_weeks = [
                key for key, quota in quotas.items() if loads.get(key, 0) < quota
            ]
            if not over_weeks or not under_weeks:
                break
            over_weeks.sort(key=lambda key: (loads.get(key, 0) - quotas.get(key, 0), key), reverse=True)
            under_weeks.sort(key=lambda key: (-(quotas[key] - loads.get(key, 0)), key))
            moved = False

            for over_week in over_weeks:
                candidate_indices = [
                    index
                    for index, assignment in enumerate(result)
                    if assignment.task.subject == subject and week_key(assignment.candidate.slots) == over_week
                ]
                candidate_indices.sort(reverse=True)
                for assignment_index in candidate_indices:
                    assignment = result[assignment_index]
                    for under_week in under_weeks:
                        class_slot_used, teacher_slot_used, room_slot_used, conflict_group_slot_used = assignment_constraint_sets(
                            schedule_input,
                            result,
                            excluded_index=assignment_index,
                        )
                        daily_teacher_loads = class_teacher_day_loads(
                            schedule_input,
                            result,
                            excluded_index=assignment_index,
                        )
                        used_subject_dates = subject_dates_for(result, subject, excluded_index=assignment_index)
                        used_teacher_dates = teacher_dates_for(
                            result,
                            assignment.candidate.teacher_id,
                            excluded_index=assignment_index,
                        )
                        replacements = []
                        for candidate in domains[assignment.task.task_id]:
                            first_slot = candidate.slots[0]
                            if week_key(candidate.slots) != under_week:
                                continue
                            preferred_period = preferred_subject_periods.get(subject)
                            if preferred_period and first_slot.period != preferred_period:
                                continue
                            if first_slot.date in used_subject_dates:
                                continue
                            if assignment.task.subject in {"英语", "政治"} and creates_three_day_teacher_run(
                                used_teacher_dates,
                                first_slot.date,
                            ):
                                continue
                            if assignment.task.subject == "数学":
                                if math_max_consecutive_days is not None:
                                    if creates_teacher_run_over_limit(
                                        used_subject_dates,
                                        first_slot.date,
                                        math_max_consecutive_days,
                                    ):
                                        continue
                                elif creates_three_day_teacher_run(
                                    used_subject_dates,
                                    first_slot.date,
                                ):
                                    continue
                            if not replacement_preserves_first_lesson_module(
                                result,
                                assignment_index,
                                assignment.task,
                                candidate,
                            ):
                                continue
                            if not stage_order_candidate_allowed(
                                schedule_input,
                                stage_tasks_by_class,
                                result,
                                assignment.task,
                                candidate,
                                excluded_index=assignment_index,
                            ):
                                continue
                            if not candidate_avoids_same_class_teacher_day_limit(
                                daily_teacher_loads,
                                assignment.task,
                                candidate,
                            ):
                                continue
                            if not candidate_is_valid(
                                schedule_input,
                                class_slot_used,
                                teacher_slot_used,
                                room_slot_used,
                                conflict_group_slot_used,
                                assignment.task,
                                candidate,
                            ):
                                continue
                            replacements.append(candidate)
                        if not replacements:
                            continue
                        replacements.sort(key=lambda candidate: scheduler.slot_sort_key(candidate.slots[0]))
                        result[assignment_index] = scheduler.Assignment(
                            task=assignment.task,
                            candidate=replacements[0],
                        )
                        result = scheduler.sorted_assignments(result)
                        moved = True
                        break
                    if moved:
                        break
                if moved:
                    break
            if not moved:
                break
    return result


def schedule_balanced_camp(
    schedule_input: scheduler.ScheduleInput,
    class_order: Sequence[str],
    preferred_subject_periods: Optional[Dict[str, str]] = None,
    weekly_halfday_min: Optional[int] = None,
    subject_week_bounds: Optional[SubjectWeekBounds] = None,
    preferred_weekly_total_max: Optional[int] = None,
    balance_public_subject_weeks: bool = False,
    avoid_public_subject_consecutive_days: bool = False,
    prefer_public_teacher_alternation: bool = False,
    teacher_alternation_subjects: Optional[Set[str]] = None,
    require_all_subject_weeks: bool = False,
    use_average_subject_week_bounds: bool = False,
    subject_week_hard_max: Optional[Dict[str, int]] = None,
) -> List[scheduler.Assignment]:
    preferred_subject_periods = preferred_subject_periods or {"数学": "AM", "英语": "PM", "政治": "PM"}
    effective_teacher_alternation_subjects = teacher_alternation_subjects or LONG_CAMP_ALTERNATING_SUBJECTS
    tasks_by_class: Dict[str, List[scheduler.CourseBlock]] = {class_id: [] for class_id in class_order}
    for task in scheduler.build_course_blocks(schedule_input.classes):
        if task.class_id in tasks_by_class:
            tasks_by_class[task.class_id].append(task)

    tasks = [task for class_id in class_order for task in tasks_by_class[class_id]]
    domains = scheduler.candidate_domains(tasks, schedule_input)
    missing = [task.task_id for task in tasks if not domains[task.task_id]]
    if missing:
        raise ValueError(f"以下任务没有候选课节: {', '.join(missing[:20])}")
    first_lesson_anchor_keys = stage_first_lesson_anchor_keys(tasks)
    first_lesson_anchor_task_ids = stage_first_lesson_anchor_task_ids(tasks)
    first_lesson_anchor_positions: Dict[Tuple[str, str, str], Tuple[str, int, int, str]] = {}
    stage_tasks_by_class = stage_order_tasks_by_class(schedule_input)

    max_block_hours = max((task.block_hours for task in tasks), default=4)
    slot_blocks = scheduler.build_contiguous_slot_blocks(schedule_input.time_slots, max_block_hours)
    if not slot_blocks:
        raise ValueError("当前筛选条件下没有可用课节")

    block_index = {
        tuple(slot.id for slot in slot_block): index
        for index, slot_block in enumerate(slot_blocks)
    }
    class_slot_used, teacher_slot_used, room_slot_used, conflict_group_slot_used = scheduler.locked_constraint_sets(schedule_input)
    subject_date_used: Set[Tuple[str, str]] = set()
    week_loads: Dict[Tuple[int, int], int] = {}
    week_subjects: Dict[Tuple[int, int], Set[str]] = {}
    subject_week_loads: Dict[Tuple[str, Tuple[int, int]], int] = {}
    teacher_dates: Dict[str, Set[str]] = {}
    subject_dates: Dict[str, Set[str]] = {}
    subject_last_date: Dict[str, str] = {}
    assignments: List[scheduler.Assignment] = []
    daily_teacher_loads = class_teacher_day_loads(schedule_input, assignments)
    for locked_assignment in schedule_input.locked_assignments:
        teacher_key = candidate_teacher_key(locked_assignment.candidate)
        if teacher_key:
            teacher_dates.setdefault(teacher_key, set()).add(
                locked_assignment.candidate.slots[0].date
            )

    subject_counts: Dict[str, int] = {}
    subject_seen: Dict[str, int] = {}
    for task in tasks:
        subject_counts[task.subject] = subject_counts.get(task.subject, 0) + 1
    week_quotas = (
        balanced_capped_week_quotas(slot_blocks, len(tasks), None, weekly_halfday_min)
        if weekly_halfday_min
        else balanced_week_quotas(slot_blocks, len(tasks))
    )
    subject_slot_blocks: Dict[str, List[Tuple[scheduler.TimeSlot, ...]]] = {}
    for subject in subject_counts:
        seen_slot_blocks: Set[Tuple[str, ...]] = set()
        blocks: List[Tuple[scheduler.TimeSlot, ...]] = []
        for task in tasks:
            if task.subject != subject:
                continue
            for candidate in domains[task.task_id]:
                slot_key = tuple(slot.id for slot in candidate.slots)
                if slot_key in seen_slot_blocks:
                    continue
                seen_slot_blocks.add(slot_key)
                blocks.append(candidate.slots)
        subject_slot_blocks[subject] = sorted(blocks, key=slot_block_key)
    effective_subject_week_bounds = subject_week_bounds
    if use_average_subject_week_bounds:
        effective_subject_week_bounds = average_subject_week_bounds_from_counts(
            subject_slot_blocks,
            subject_counts,
            subject_week_hard_max,
        )
    elif effective_subject_week_bounds is None and balance_public_subject_weeks:
        effective_subject_week_bounds = average_subject_week_bounds_from_counts(
            subject_slot_blocks,
            subject_counts,
            long_camp_subject_week_hard_max(set(subject_counts)),
        )
    if effective_subject_week_bounds:
        subject_week_quotas = bounded_subject_week_quotas(
            slot_blocks,
            subject_slot_blocks,
            subject_counts,
            effective_subject_week_bounds,
            preferred_weekly_total_max,
            require_all_subject_weeks,
        )
    else:
        subject_week_quotas = {
            subject: (
                balanced_week_quotas
                if balance_public_subject_weeks and subject in PUBLIC_SUBJECTS
                else front_loaded_week_quotas if subject in {"英语", "政治"} else balanced_week_quotas
            )(subject_slot_blocks[subject], count)
            for subject, count in subject_counts.items()
        }
    subject_week_limits = max_only_subject_week_limits(
        subject_slot_blocks,
        effective_subject_week_bounds,
    )
    if effective_subject_week_bounds:
        week_quotas = sum_subject_week_quotas(subject_week_quotas, week_quotas)
    for period in sorted({preferred_subject_periods.get(subject) for subject in {"英语", "政治"}} - {None}):
        if effective_subject_week_bounds:
            break
        period_subjects = [
            subject
            for subject in {"英语", "政治"}
            if subject in subject_week_quotas and preferred_subject_periods.get(subject) == period
        ]
        if len(period_subjects) <= 1:
            continue
        period_week_capacity: Dict[Tuple[int, int], int] = {}
        for slot_block in slot_blocks:
            if slot_block[0].period != period:
                continue
            key = week_key(slot_block)
            period_week_capacity[key] = period_week_capacity.get(key, 0) + 1
        if not period_week_capacity:
            continue
        tail_week = max(period_week_capacity)
        if period_week_capacity[tail_week] > 1:
            continue
        keep_tail_subject = max(period_subjects, key=lambda subject: (subject_counts.get(subject, 0), subject))
        for subject in period_subjects:
            if subject == keep_tail_subject:
                continue
            tail_quota = subject_week_quotas[subject].get(tail_week, 0)
            if tail_quota <= 0:
                continue
            subject_week_quotas[subject][tail_week] = tail_quota - 1
            shift_tail_week_quota_to_early(
                subject_week_quotas[subject],
                subject_slot_blocks[subject],
                tail_week,
                1,
            )
    subject_targets = {
        subject: subject_target_indices(
            subject_slot_blocks[subject],
            block_index,
            subject_week_quotas.get(subject, {}),
            count,
        )
        for subject, count in subject_counts.items()
    }

    subject_tasks: Dict[str, List[scheduler.CourseBlock]] = {}
    subject_order: List[str] = []
    for task in tasks:
        if task.subject not in subject_tasks:
            subject_tasks[task.subject] = []
            subject_order.append(task.subject)
        subject_tasks[task.subject].append(task)
    for subject in subject_tasks:
        subject_tasks[subject].sort(
            key=lambda task: (
                effective_task_stage_sort_rank(schedule_input, stage_tasks_by_class, task),
                0 if task.task_id in first_lesson_anchor_task_ids else 1,
            )
        )
        if subject in effective_teacher_alternation_subjects:
            grouped_by_rank: Dict[int, List[scheduler.CourseBlock]] = defaultdict(list)
            for task in subject_tasks[subject]:
                rank = effective_task_stage_sort_rank(schedule_input, stage_tasks_by_class, task)
                grouped_by_rank[rank].append(task)
            subject_tasks[subject] = [
                task
                for rank in sorted(grouped_by_rank)
                for task in alternate_teacher_tasks(grouped_by_rank[rank])
            ]
            subject_tasks[subject].sort(
                key=lambda task: (
                    effective_task_stage_sort_rank(schedule_input, stage_tasks_by_class, task),
                    0 if task.task_id in first_lesson_anchor_task_ids else 1,
                )
            )
    subject_task_position = {
        task.task_id: index
        for subject in subject_tasks
        for index, task in enumerate(subject_tasks[subject])
    }

    weighted_tasks: List[Tuple[int, float, int, scheduler.CourseBlock]] = []
    sequence = 0
    for subject in subject_order:
        for task in subject_tasks[subject]:
            seen = subject_seen.get(task.subject, 0)
            targets = subject_targets.get(task.subject, [])
            target = targets[seen] if seen < len(targets) else float(seen)
            if task.task_id in first_lesson_anchor_task_ids:
                target -= 1_000_000
            subject_seen[task.subject] = seen + 1
            weighted_tasks.append((
                effective_task_stage_sort_rank(schedule_input, stage_tasks_by_class, task),
                target,
                sequence,
                task,
            ))
            sequence += 1
    weighted_tasks.sort(key=lambda item: (item[0], item[1], item[2]))

    def is_valid(
        task: scheduler.CourseBlock,
        candidate: scheduler.Candidate,
        avoid_same_subject_day: bool = True,
        avoid_subject_adjacent_day: bool = True,
        enforce_subject_quota: bool = True,
    ) -> bool:
        slot_date = candidate.slots[0].date
        if not first_lesson_candidate_allowed(task, candidate, first_lesson_anchor_keys, first_lesson_anchor_positions):
            return False
        if not stage_order_candidate_allowed(schedule_input, stage_tasks_by_class, assignments, task, candidate):
            return False
        if not candidate_avoids_same_class_teacher_day_limit(daily_teacher_loads, task, candidate):
            return False
        if (
            task.subject in CORE_TEACHER_CONSECUTIVE_LIMIT_SUBJECTS
            and candidate_teacher_key(candidate)
            and creates_teacher_run_over_limit(
                teacher_dates.get(candidate_teacher_key(candidate), set()),
                slot_date,
                CORE_TEACHER_MAX_CONSECUTIVE_DAYS,
            )
        ):
            return False
        if enforce_subject_quota and task.subject in subject_week_limits:
            limit = subject_week_limits[task.subject].get(week_key(candidate.slots), 0)
            if subject_week_loads.get((task.subject, week_key(candidate.slots)), 0) >= limit:
                return False
        elif enforce_subject_quota and effective_subject_week_bounds and task.subject in subject_week_quotas:
            quota = subject_week_quotas[task.subject].get(week_key(candidate.slots), 0)
            if subject_week_loads.get((task.subject, week_key(candidate.slots)), 0) >= quota:
                return False
        if avoid_same_subject_day and (task.subject, slot_date) in subject_date_used:
            return False
        if (
            avoid_public_subject_consecutive_days
            and avoid_subject_adjacent_day
            and task.subject in LONG_CAMP_ALTERNATING_SUBJECTS
            and creates_adjacent_subject_day(subject_dates.get(task.subject, set()), slot_date)
        ):
            return False
        return candidate_is_valid(
            schedule_input,
            class_slot_used,
            teacher_slot_used,
            room_slot_used,
            conflict_group_slot_used,
            task,
            candidate,
        )

    def candidate_score(task: scheduler.CourseBlock, candidate: scheduler.Candidate, target: float) -> Tuple[float, str, int, str]:
        slot_ids = tuple(slot.id for slot in candidate.slots)
        index = block_index.get(slot_ids, 10_000)
        slot_block = candidate.slots
        first_slot = slot_block[0]
        key = week_key(slot_block)
        quota = week_quotas.get(key, len(slot_blocks))
        load = week_loads.get(key, 0)
        subject_quota = subject_week_quotas.get(task.subject, {}).get(key, len(slot_blocks))
        subject_load = subject_week_loads.get((task.subject, key), 0)
        subjects_this_week = week_subjects.get(key, set())
        preferred_period = preferred_subject_periods.get(task.subject)
        preferred_penalty = 0 if not preferred_period or first_slot.period == preferred_period else 5_000
        overflow_penalty = max(0, load + 1 - quota) * 4_000
        subject_overflow_penalty = max(0, subject_load + 1 - subject_quota) * 3_000
        week_load_penalty = load * 80
        subject_mix_penalty = (
            2_500
            if len(subject_counts) > 1
            and subjects_this_week
            and task.subject in subjects_this_week
            and len(subjects_this_week) < min(2, len(subject_counts))
            else 0
        )
        teacher_run_penalty = (
            20_000
            if task.subject in {"英语", "政治"}
            and candidate.teacher_id
            and creates_three_day_teacher_run(teacher_dates.get(candidate.teacher_id, set()), first_slot.date)
            else 0
        )
        subject_run_penalty = (
            12_000
            if task.subject == "数学"
            and (
                creates_teacher_run_over_limit(
                    subject_dates.get(task.subject, set()),
                    first_slot.date,
                    LONG_CAMP_MATH_MAX_CONSECUTIVE_DAYS,
                )
                if balance_public_subject_weeks
                else creates_three_day_teacher_run(subject_dates.get(task.subject, set()), first_slot.date)
            )
            else 0
        )
        subject_adjacent_penalty = (
            18_000
            if avoid_public_subject_consecutive_days
            and task.subject in LONG_CAMP_ALTERNATING_SUBJECTS
            and creates_adjacent_subject_day(subject_dates.get(task.subject, set()), first_slot.date)
            else 0
        )
        teacher_repeat_penalty = (
            9_000
            if prefer_public_teacher_alternation
            and task.subject in effective_teacher_alternation_subjects
            and subject_neighbor_teacher_repeat(assignments, task, candidate)
            else 0
        )
        teacher_travel_penalty = scheduler.candidate_same_day_teacher_travel_penalty(
            schedule_input,
            [*schedule_input.locked_assignments, *assignments],
            task,
            candidate,
        )
        same_day_load = sum(1 for assignment in assignments if assignment.candidate.slots[0].date == first_slot.date)
        day_penalty = same_day_load * 8
        return (
            abs(index - target)
            + preferred_penalty
            + overflow_penalty
            + subject_overflow_penalty
            + week_load_penalty
            + subject_mix_penalty
            + teacher_run_penalty
            + subject_run_penalty
            + subject_adjacent_penalty
            + teacher_repeat_penalty
            + teacher_travel_penalty
            + day_penalty,
            first_slot.date,
            scheduler.period_sort_value(first_slot.period),
            candidate.room_id,
        )

    def preserves_future_subject_space(task: scheduler.CourseBlock, candidate: scheduler.Candidate) -> bool:
        if task.subject not in {"英语", "政治"}:
            return True
        subject_sequence = subject_tasks.get(task.subject, [])
        position = subject_task_position.get(task.task_id, -1)
        future_tasks = subject_sequence[position + 1 :]
        if not future_tasks:
            return True
        candidate_date = candidate.slots[0].date
        preferred_period = preferred_subject_periods.get(task.subject)
        possible_dates: Set[str] = set()
        for future_task in future_tasks:
            future_has_candidate = False
            for future_candidate in domains[future_task.task_id]:
                future_date = future_candidate.slots[0].date
                if future_date <= candidate_date:
                    continue
                if preferred_period and future_candidate.slots[0].period != preferred_period:
                    continue
                if (future_task.subject, future_date) in subject_date_used:
                    continue
                if not candidate_is_valid(
                    schedule_input,
                    class_slot_used,
                    teacher_slot_used,
                    room_slot_used,
                    conflict_group_slot_used,
                    future_task,
                    future_candidate,
                ):
                    continue
                future_has_candidate = True
                possible_dates.add(future_date)
            if not future_has_candidate:
                return False
        return len(possible_dates) >= len(future_tasks)

    for _, target, _, task in weighted_tasks:
        candidates = [candidate for candidate in domains[task.task_id] if is_valid(task, candidate)]
        if not candidates and avoid_public_subject_consecutive_days and task.subject in LONG_CAMP_ALTERNATING_SUBJECTS:
            candidates = [
                candidate
                for candidate in domains[task.task_id]
                if is_valid(task, candidate, avoid_subject_adjacent_day=False)
            ]
        if not candidates and effective_subject_week_bounds:
            candidates = [
                candidate
                for candidate in domains[task.task_id]
                if is_valid(task, candidate, enforce_subject_quota=False)
            ]
        if not candidates:
            candidates = [
                candidate
                for candidate in domains[task.task_id]
                if is_valid(
                    task,
                    candidate,
                    avoid_same_subject_day=False,
                    avoid_subject_adjacent_day=False,
                    enforce_subject_quota=False,
                )
            ]
        last_subject_date = subject_last_date.get(task.subject)
        if last_subject_date and task.subject in {"英语", "政治"}:
            chronological_candidates = [
                candidate for candidate in candidates if candidate.slots[0].date > last_subject_date
            ]
            if chronological_candidates:
                candidates = chronological_candidates
        preferred_period = preferred_subject_periods.get(task.subject)
        if preferred_period:
            preferred_candidates = [
                candidate for candidate in candidates if candidate.slots[0].period == preferred_period
            ]
            if preferred_candidates:
                candidates = preferred_candidates
        week_quota_candidates = [
            candidate
            for candidate in candidates
            if week_loads.get(week_key(candidate.slots), 0) < week_quotas.get(week_key(candidate.slots), len(slot_blocks))
        ]
        if week_quota_candidates:
            candidates = week_quota_candidates
        if task.subject in PUBLIC_SUBJECTS:
            quota_candidates = [
                candidate
                for candidate in candidates
                if subject_week_loads.get((task.subject, week_key(candidate.slots)), 0)
                < subject_week_quotas.get(task.subject, {}).get(week_key(candidate.slots), len(slot_blocks))
            ]
            if quota_candidates:
                candidates = quota_candidates
        if task.subject == "数学":
            if balance_public_subject_weeks:
                non_three_day_subject_candidates = [
                    candidate
                    for candidate in candidates
                    if not creates_teacher_run_over_limit(
                        subject_dates.get(task.subject, set()),
                        candidate.slots[0].date,
                        LONG_CAMP_MATH_MAX_CONSECUTIVE_DAYS,
                    )
                ]
            else:
                non_three_day_subject_candidates = [
                    candidate
                    for candidate in candidates
                    if not creates_three_day_teacher_run(
                        subject_dates.get(task.subject, set()),
                        candidate.slots[0].date,
                    )
                ]
            if non_three_day_subject_candidates:
                candidates = non_three_day_subject_candidates
        if task.subject in {"英语", "政治"} and task.teacher_id:
            non_three_day_candidates = [
                candidate
                for candidate in candidates
                if not creates_three_day_teacher_run(
                    teacher_dates.get(task.teacher_id, set()),
                    candidate.slots[0].date,
                )
            ]
            if non_three_day_candidates:
                candidates = non_three_day_candidates
        if prefer_public_teacher_alternation and task.subject in effective_teacher_alternation_subjects:
            teacher_alternation_candidates = [
                candidate for candidate in candidates
                if not subject_neighbor_teacher_repeat(assignments, task, candidate)
            ]
            if teacher_alternation_candidates:
                candidates = teacher_alternation_candidates
        if task.subject in {"英语", "政治"}:
            future_safe_candidates = [
                candidate for candidate in candidates if preserves_future_subject_space(task, candidate)
            ]
            if future_safe_candidates:
                candidates = future_safe_candidates
        if not candidates:
            raise ValueError(f"集训营均衡策略未能为任务 {task.task_id} 找到可用课节")
        candidates.sort(key=lambda candidate: candidate_score(task, candidate, target))
        candidate = candidates[0]
        assignments.append(
            place_candidate(
                schedule_input,
                class_slot_used,
                teacher_slot_used,
                room_slot_used,
                conflict_group_slot_used,
                task,
                candidate,
            )
        )
        subject_date_used.add((task.subject, candidate.slots[0].date))
        subject_dates.setdefault(task.subject, set()).add(candidate.slots[0].date)
        subject_last_date[task.subject] = candidate.slots[0].date
        key = week_key(candidate.slots)
        week_loads[key] = week_loads.get(key, 0) + 1
        week_subjects.setdefault(key, set()).add(task.subject)
        subject_week_loads[(task.subject, key)] = subject_week_loads.get((task.subject, key), 0) + 1
        teacher_key = candidate_teacher_key(candidate)
        if teacher_key:
            teacher_dates.setdefault(teacher_key, set()).add(candidate.slots[0].date)
        add_class_teacher_day_load(daily_teacher_loads, task, candidate)
        mark_first_lesson_anchor_done(task, candidate, first_lesson_anchor_keys, first_lesson_anchor_positions)

    if prefer_public_teacher_alternation:
        assignments = rebalance_subject_teacher_alternation(
            schedule_input,
            assignments,
            domains,
            effective_teacher_alternation_subjects,
        )
    assignments = improve_subject_week_balance(
        schedule_input,
        assignments,
        domains,
        subject_week_quotas,
        preferred_subject_periods,
        (set(subject_counts) & PUBLIC_SUBJECTS) if balance_public_subject_weeks else {"英语", "政治"},
        LONG_CAMP_MATH_MAX_CONSECUTIVE_DAYS if balance_public_subject_weeks else None,
    )
    if balance_public_subject_weeks:
        assignments = improve_total_week_balance(
            schedule_input,
            assignments,
            domains,
            week_quotas,
            preferred_subject_periods,
        )
    if weekly_halfday_min:
        assignments = improve_total_week_balance(
            schedule_input,
            assignments,
            domains,
            week_quotas,
            preferred_subject_periods,
        )
    if avoid_public_subject_consecutive_days or prefer_public_teacher_alternation:
        subject_weekly_max_limits = {
            subject: weekly_max
            for subject, (_weekly_min, weekly_max) in (effective_subject_week_bounds or {}).items()
            if weekly_max is not None
        }
        assignments = improve_public_subject_spacing(
            schedule_input,
            assignments,
            domains,
            LONG_CAMP_ALTERNATING_SUBJECTS,
            preferred_subject_periods,
            subject_weekly_max_limits if balance_public_subject_weeks else None,
        )
    if prefer_public_teacher_alternation:
        assignments = rebalance_subject_teacher_alternation(
            schedule_input,
            assignments,
            domains,
            effective_teacher_alternation_subjects,
        )
    return require_schedule_order(schedule_input, assignments)


def is_english_politics_without_math_suite(classes: Dict[str, scheduler.SchoolClass]) -> bool:
    subjects = {requirement.subject for cls in classes.values() for requirement in cls.requirements}
    return bool(subjects & {"英语"}) and bool(subjects & {"政治"}) and subjects <= {"英语", "政治"}


def schedule_weekly_balanced_english_politics_suite(
    schedule_input: scheduler.ScheduleInput,
    class_order: Sequence[str],
    weekly_halfday_limit: Optional[int] = None,
    weekly_halfday_min: Optional[int] = None,
    subject_week_bounds: Optional[SubjectWeekBounds] = None,
    preferred_weekly_total_max: Optional[int] = None,
    require_all_subject_weeks: bool = False,
    use_average_subject_week_bounds: bool = False,
) -> List[scheduler.Assignment]:
    tasks_by_subject: Dict[str, List[scheduler.CourseBlock]] = {"英语": [], "政治": []}
    for task in scheduler.build_course_blocks(schedule_input.classes):
        if task.class_id not in class_order:
            continue
        if task.subject not in tasks_by_subject:
            raise ValueError(f"无数学套班周均衡策略不支持科目: {task.subject}")
        tasks_by_subject[task.subject].append(task)

    if not tasks_by_subject["英语"] or not tasks_by_subject["政治"]:
        return schedule_balanced_camp(
            schedule_input,
            class_order,
            None,
            subject_week_bounds=subject_week_bounds,
            preferred_weekly_total_max=preferred_weekly_total_max,
            require_all_subject_weeks=require_all_subject_weeks,
            use_average_subject_week_bounds=use_average_subject_week_bounds,
        )

    for subject in tasks_by_subject:
        tasks_by_subject[subject] = alternate_teacher_tasks(tasks_by_subject[subject])

    tasks = [*tasks_by_subject["英语"], *tasks_by_subject["政治"]]
    first_lesson_anchor_keys = stage_first_lesson_anchor_keys(tasks)
    first_lesson_anchor_task_ids = stage_first_lesson_anchor_task_ids(tasks)
    first_lesson_anchor_positions: Dict[Tuple[str, str, str], Tuple[str, int, int, str]] = {}
    stage_tasks_by_class = stage_order_tasks_by_class(schedule_input)
    for subject in tasks_by_subject:
        tasks_by_subject[subject].sort(
            key=lambda task: (
                effective_task_stage_sort_rank(schedule_input, stage_tasks_by_class, task),
                0 if task.task_id in first_lesson_anchor_task_ids else 1,
            )
        )
    domains = scheduler.candidate_domains(tasks, schedule_input)
    missing = [task.task_id for task in tasks if not domains[task.task_id]]
    if missing:
        raise ValueError(f"以下任务没有候选课节: {', '.join(missing[:20])}")

    class_slot_used, teacher_slot_used, room_slot_used, conflict_group_slot_used = scheduler.locked_constraint_sets(schedule_input)
    teacher_dates: Dict[str, Set[str]] = {}
    for locked_assignment in schedule_input.locked_assignments:
        teacher_key = candidate_teacher_key(locked_assignment.candidate)
        if teacher_key:
            teacher_dates.setdefault(teacher_key, set()).add(
                locked_assignment.candidate.slots[0].date
            )
    max_block_hours = max((task.block_hours for task in tasks), default=4)
    slot_blocks = scheduler.build_contiguous_slot_blocks(schedule_input.time_slots, max_block_hours)
    if not slot_blocks:
        raise ValueError("当前筛选条件下没有可用课节")
    preferred_subject_periods = {"英语": "AM", "政治": "PM"}
    effective_subject_week_bounds = subject_week_bounds
    if use_average_subject_week_bounds:
        effective_subject_week_bounds = average_subject_week_bounds_from_counts(
            {subject: list(slot_blocks) for subject in tasks_by_subject},
            {subject: len(subject_tasks) for subject, subject_tasks in tasks_by_subject.items()},
        )
    week_quotas = balanced_capped_week_quotas(
        slot_blocks,
        len(tasks),
        weekly_halfday_limit,
        weekly_halfday_min,
    )
    subject_week_quotas: Dict[str, Dict[Tuple[int, int], int]] = {}
    if effective_subject_week_bounds:
        subject_week_quotas = bounded_subject_week_quotas(
            slot_blocks,
            {subject: list(slot_blocks) for subject in tasks_by_subject},
            {subject: len(subject_tasks) for subject, subject_tasks in tasks_by_subject.items()},
            effective_subject_week_bounds,
            preferred_weekly_total_max,
            require_all_subject_weeks,
        )
        if subject_week_quotas:
            week_quotas = sum_subject_week_quotas(subject_week_quotas, week_quotas)
    week_capacities = {
        key: weekly_halfday_limit or sum(1 for slot_block in slot_blocks if week_key(slot_block) == key)
        for key in week_quotas
    }
    week_index = {key: index for index, key in enumerate(sorted(week_quotas))}
    target_weeks = [
        key
        for key in sorted(week_quotas)
        for _ in range(week_quotas[key])
    ]
    latest_slot_date = max((slot_block[0].date for slot_block in slot_blocks), default="")

    subject_date_used: Set[Tuple[str, str]] = set()
    week_loads: Dict[Tuple[int, int], int] = {}
    subject_week_loads: Dict[Tuple[str, Tuple[int, int]], int] = {}
    assignments: List[scheduler.Assignment] = []
    daily_teacher_loads = class_teacher_day_loads(schedule_input, assignments)

    def task_candidates(
        task: scheduler.CourseBlock,
        *,
        enforce_week_quota: bool = True,
        enforce_subject_quota: bool = True,
        class_used: Optional[Set[Tuple[str, str]]] = None,
        teacher_used: Optional[Set[Tuple[str, str]]] = None,
        room_used: Optional[Set[Tuple[str, str]]] = None,
        conflict_used: Optional[Set[Tuple[str, str]]] = None,
    ) -> List[scheduler.Candidate]:
        current_class_used = class_used if class_used is not None else class_slot_used
        current_teacher_used = teacher_used if teacher_used is not None else teacher_slot_used
        current_room_used = room_used if room_used is not None else room_slot_used
        current_conflict_used = conflict_used if conflict_used is not None else conflict_group_slot_used
        result = []
        for candidate in domains[task.task_id]:
            first = candidate.slots[0]
            if not first_lesson_candidate_allowed(task, candidate, first_lesson_anchor_keys, first_lesson_anchor_positions):
                continue
            if not stage_order_candidate_allowed(schedule_input, stage_tasks_by_class, assignments, task, candidate):
                continue
            if not candidate_avoids_same_class_teacher_day_limit(daily_teacher_loads, task, candidate):
                continue
            if (
                task.subject in CORE_TEACHER_CONSECUTIVE_LIMIT_SUBJECTS
                and candidate_teacher_key(candidate)
                and creates_teacher_run_over_limit(
                    teacher_dates.get(candidate_teacher_key(candidate), set()),
                    first.date,
                    CORE_TEACHER_MAX_CONSECUTIVE_DAYS,
                )
            ):
                continue
            if (task.subject, first.date) in subject_date_used:
                continue
            key = week_key(candidate.slots)
            if enforce_subject_quota and effective_subject_week_bounds and task.subject in subject_week_quotas:
                subject_quota = subject_week_quotas[task.subject].get(key, 0)
                if subject_week_loads.get((task.subject, key), 0) >= subject_quota:
                    continue
            if week_loads.get(key, 0) >= week_capacities.get(key, len(slot_blocks)):
                continue
            if enforce_week_quota and week_loads.get(key, 0) >= week_quotas.get(key, 0):
                continue
            if not candidate_is_valid(
                schedule_input,
                current_class_used,
                current_teacher_used,
                current_room_used,
                current_conflict_used,
                task,
                candidate,
            ):
                continue
            result.append(candidate)
        return result

    def teacher_run_penalty(task: scheduler.CourseBlock, candidate: scheduler.Candidate) -> int:
        teacher_key = candidate_teacher_key(candidate)
        if not teacher_key:
            return 0
        return 1 if creates_three_day_teacher_run(teacher_dates.get(teacher_key, set()), candidate.slots[0].date) else 0

    def place(task: scheduler.CourseBlock, candidate: scheduler.Candidate) -> None:
        assignment = place_candidate(
            schedule_input,
            class_slot_used,
            teacher_slot_used,
            room_slot_used,
            conflict_group_slot_used,
            task,
            candidate,
        )
        assignments.append(assignment)
        first = candidate.slots[0]
        subject_date_used.add((task.subject, first.date))
        key = week_key(candidate.slots)
        week_loads[key] = week_loads.get(key, 0) + 1
        subject_week_loads[(task.subject, key)] = subject_week_loads.get((task.subject, key), 0) + 1
        teacher_key = candidate_teacher_key(candidate)
        if teacher_key:
            teacher_dates.setdefault(teacher_key, set()).add(first.date)
        add_class_teacher_day_load(daily_teacher_loads, task, candidate)
        mark_first_lesson_anchor_done(task, candidate, first_lesson_anchor_keys, first_lesson_anchor_positions)

    sequence: List[scheduler.CourseBlock] = []
    subject_progress = {subject: 0 for subject in tasks_by_subject}
    while any(tasks_by_subject.values()):
        options = [subject for subject, subject_tasks in tasks_by_subject.items() if subject_tasks]
        options.sort(key=lambda subject: (subject_progress[subject] / max(1, subject_progress[subject] + len(tasks_by_subject[subject])), subject))
        subject = options[0]
        sequence.append(tasks_by_subject[subject].pop(0))
        subject_progress[subject] += 1

    placed_subject_counts: Dict[str, int] = {}
    subject_target_weeks = {
        subject: [
            key
            for key in sorted(quotas)
            for _ in range(quotas[key])
        ]
        for subject, quotas in subject_week_quotas.items()
    }
    for index, task in enumerate(sequence):
        if task.subject in subject_target_weeks:
            subject_index = placed_subject_counts.get(task.subject, 0)
            targets = subject_target_weeks[task.subject]
            target_week = targets[min(subject_index, len(targets) - 1)] if targets else None
        else:
            target_week = target_weeks[min(index, len(target_weeks) - 1)] if target_weeks else None
        candidates = task_candidates(task)
        if not candidates:
            candidates = task_candidates(task, enforce_week_quota=False)
        if not candidates:
            candidates = task_candidates(task, enforce_week_quota=False, enforce_subject_quota=False)
        if not candidates:
            raise ValueError(f"无数学套班周均衡策略未能为任务 {task.task_id} 找到可用课节")
        if task.subject in CORE_TEACHER_CONSECUTIVE_LIMIT_SUBJECTS:
            non_three_day_candidates = [
                candidate
                for candidate in candidates
                if not candidate_teacher_key(candidate)
                or not creates_three_day_teacher_run(
                    teacher_dates.get(candidate_teacher_key(candidate), set()),
                    candidate.slots[0].date,
                )
            ]
            if non_three_day_candidates:
                candidates = non_three_day_candidates
        preferred_period = preferred_subject_periods.get(task.subject)
        if preferred_period:
            preferred_candidates = [
                candidate for candidate in candidates if candidate.slots[0].period == preferred_period
            ]
            if preferred_candidates:
                candidates = preferred_candidates
        remaining_subjects = {future_task.subject for future_task in sequence[index + 1 :]}
        candidates.sort(
            key=lambda candidate: (
                abs(week_index.get(week_key(candidate.slots), 999) - week_index.get(target_week, 0)) if target_week else 0,
                max(0, week_loads.get(week_key(candidate.slots), 0) + 1 - week_quotas.get(week_key(candidate.slots), 0)),
                1
                if task.subject == "英语"
                and "政治" in remaining_subjects
                and candidate.slots[0].date == latest_slot_date
                else 0,
                sum(1 for assignment in assignments if assignment.candidate.slots[0].date == candidate.slots[0].date),
                teacher_run_penalty(task, candidate),
                scheduler.candidate_same_day_teacher_travel_penalty(
                    schedule_input,
                    [*schedule_input.locked_assignments, *assignments],
                    task,
                    candidate,
                ),
                candidate.slots[0].date,
                scheduler.period_sort_value(candidate.slots[0].period),
                candidate.room_id,
            )
        )
        place(task, candidates[0])
        placed_subject_counts[task.subject] = placed_subject_counts.get(task.subject, 0) + 1

    return require_schedule_order(schedule_input, assignments)


def class_window_bounds(
    classes: Iterable[scheduler.SchoolClass],
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    start_key: Optional[Tuple[str, int]] = None
    end_key: Optional[Tuple[str, int]] = None
    start_period: Optional[str] = None
    end_period: Optional[str] = None
    for cls in classes:
        if cls.start_date:
            candidate_start = (cls.start_date, scheduler.period_sort_value(cls.start_period or "AM"))
            if start_key is None or candidate_start < start_key:
                start_key = candidate_start
                start_period = cls.start_period or "AM"
        if cls.end_date:
            candidate_end = (cls.end_date, scheduler.period_sort_value(cls.end_period or "EVENING"))
            if end_key is None or candidate_end > end_key:
                end_key = candidate_end
                end_period = cls.end_period or "EVENING"
    return (
        start_key[0] if start_key else None,
        start_period,
        end_key[0] if end_key else None,
        end_period,
    )


def schedule_balanced_camp_by_suite(
    schedule_input: scheduler.ScheduleInput,
    class_order: Sequence[str],
    class_metadata: Dict[str, Dict[str, str]],
    preferred_subject_periods: Optional[Dict[str, str]] = None,
    lock_previous_assignments: bool = True,
    compact_english_politics_without_math: bool = False,
    balance_public_subject_weeks: bool = False,
    require_all_subject_weeks: bool = False,
) -> List[scheduler.Assignment]:
    preferred_subject_periods = preferred_subject_periods or {"数学": "AM", "英语": "PM", "政治": "PM"}
    grouped_class_ids: List[Tuple[str, List[str]]] = []
    by_suite: Dict[str, List[str]] = {}
    for class_id in class_order:
        if class_id not in schedule_input.classes:
            continue
        suite_code = class_metadata.get(class_id, {}).get("suite_code") or class_id
        if suite_code not in by_suite:
            by_suite[suite_code] = []
            grouped_class_ids.append((suite_code, by_suite[suite_code]))
        by_suite[suite_code].append(class_id)

    assignments: List[scheduler.Assignment] = []
    for _, suite_class_ids in grouped_class_ids:
        suite_classes = {
            class_id: schedule_input.classes[class_id]
            for class_id in suite_class_ids
        }
        conflict_groups, class_conflict_groups = selected_conflict_groups(schedule_input, set(suite_classes))
        start_date, start_period, end_date, end_period = class_window_bounds(suite_classes.values())
        suite_input = scheduler.ScheduleInput(
            time_slots=filter_time_slots(
                schedule_input.time_slots,
                start_date,
                end_date,
                start_period,
                end_period,
                None,
            ),
            rooms=schedule_input.rooms,
            classes=suite_classes,
            conflict_groups=conflict_groups,
            class_conflict_groups=class_conflict_groups,
            locked_assignments=(
                [*schedule_input.locked_assignments, *assignments]
                if lock_previous_assignments
                else list(schedule_input.locked_assignments)
            ),
            area_travel_minutes=schedule_input.area_travel_minutes,
        )
        if compact_english_politics_without_math and is_english_politics_without_math_suite(suite_classes):
            sub_products = {
                class_metadata.get(class_id, {}).get("sub_product", "")
                for class_id in suite_class_ids
            }
            suite_subjects = {
                requirement.subject
                for cls in suite_classes.values()
                for requirement in cls.requirements
            }
            suite_stages = {
                requirement.stage or ""
                for cls in suite_classes.values()
                for requirement in cls.requirements
            }
            is_wuyou_han = "无忧寒" in sub_products
            is_summer_average_product = bool(sub_products & {"寒暑营", "暑假营"})
            is_summer_preplan = is_summer_average_product and bool(suite_stages & {"暑假", "基础", "强化"})
            weekly_halfday_limit = None if is_summer_average_product else (8 if is_wuyou_han else 9)
            weekly_halfday_min = 6 if is_wuyou_han else None
            subject_week_bounds = None
            preferred_weekly_total_max = SUMMER_PREFERRED_WEEKLY_HALFDAY_MAX if is_summer_preplan else None
            assignments.extend(
                schedule_weekly_balanced_english_politics_suite(
                    suite_input,
                    suite_class_ids,
                    weekly_halfday_limit,
                    weekly_halfday_min,
                    subject_week_bounds,
                    preferred_weekly_total_max,
                    require_all_subject_weeks=is_summer_preplan or require_all_subject_weeks,
                    use_average_subject_week_bounds=is_summer_preplan,
                )
            )
        else:
            sub_products = {
                class_metadata.get(class_id, {}).get("sub_product", "")
                for class_id in suite_class_ids
            }
            is_long_camp = balance_public_subject_weeks or bool(sub_products & LONG_CAMP_SUB_PRODUCTS)
            suite_subjects = {
                requirement.subject
                for cls in suite_classes.values()
                for requirement in cls.requirements
            }
            is_public_suite = bool(suite_subjects & PUBLIC_SUBJECTS)
            suite_stages = {
                requirement.stage or ""
                for cls in suite_classes.values()
                for requirement in cls.requirements
            }
            weekly_halfday_min = 7 if "无忧寒" in sub_products and "数学" in suite_subjects else None
            is_summer_preplan = bool(sub_products & {"寒暑营", "暑假营"}) and bool(suite_stages & {"暑假", "基础", "强化"})
            subject_week_bounds = None
            preferred_weekly_total_max = (
                SUMMER_PREFERRED_WEEKLY_HALFDAY_MAX
                if is_summer_preplan
                else None
            )
            assignments.extend(
                schedule_balanced_camp(
                    suite_input,
                    suite_class_ids,
                    preferred_subject_periods,
                    weekly_halfday_min,
                    subject_week_bounds,
                    preferred_weekly_total_max,
                    is_long_camp,
                    is_public_suite,
                    is_public_suite,
                    PUBLIC_SUBJECTS if is_public_suite else None,
                    require_all_subject_weeks=is_long_camp or is_summer_preplan or require_all_subject_weeks,
                    use_average_subject_week_bounds=is_summer_preplan,
                )
            )

    domains = scheduler.candidate_domains(
        scheduler.build_course_blocks(schedule_input.classes),
        schedule_input,
    )
    assignments = improve_three_day_run_balance(
        schedule_input,
        scheduler.sorted_assignments(assignments),
        domains,
        class_metadata,
        preferred_subject_periods,
    )
    return require_schedule_order(schedule_input, assignments)
def suite_code_for_assignment(
    assignment: scheduler.Assignment,
    class_metadata: Dict[str, Dict[str, str]],
) -> str:
    return class_metadata.get(assignment.task.class_id, {}).get("suite_code") or assignment.task.class_id


def is_long_camp_assignment(
    assignment: scheduler.Assignment,
    class_metadata: Dict[str, Dict[str, str]],
) -> bool:
    meta = class_metadata.get(assignment.task.class_id, {})
    sub_product = meta.get("sub_product", "")
    return sub_product in LONG_CAMP_SUB_PRODUCTS or any(
        label in assignment.task.class_name for label in LONG_CAMP_SUB_PRODUCTS
    )


def math_max_consecutive_days_for_suite(
    schedule_input: scheduler.ScheduleInput,
    assignments: Sequence[scheduler.Assignment],
    class_metadata: Dict[str, Dict[str, str]],
    suite_code: str,
) -> int:
    for assignment in [*schedule_input.locked_assignments, *assignments]:
        if assignment.task.subject != "数学":
            continue
        if suite_code_for_assignment(assignment, class_metadata) != suite_code:
            continue
        if is_long_camp_assignment(assignment, class_metadata):
            return LONG_CAMP_MATH_MAX_CONSECUTIVE_DAYS
    return 2


def assignment_dates_for_suite_subject(
    schedule_input: scheduler.ScheduleInput,
    assignments: Sequence[scheduler.Assignment],
    class_metadata: Dict[str, Dict[str, str]],
    suite_code: str,
    subject: str,
    excluded_index: Optional[int] = None,
) -> Set[str]:
    dates = {
        assignment.candidate.slots[0].date
        for assignment in schedule_input.locked_assignments
        if suite_code_for_assignment(assignment, class_metadata) == suite_code
        and assignment.task.subject == subject
    }
    for index, assignment in enumerate(assignments):
        if excluded_index is not None and index == excluded_index:
            continue
        if suite_code_for_assignment(assignment, class_metadata) == suite_code and assignment.task.subject == subject:
            dates.add(assignment.candidate.slots[0].date)
    return dates


def assignment_week_load_for_suite_subject(
    schedule_input: scheduler.ScheduleInput,
    assignments: Sequence[scheduler.Assignment],
    class_metadata: Dict[str, Dict[str, str]],
    suite_code: str,
    subject: str,
    week: Tuple[int, int],
    excluded_index: Optional[int] = None,
) -> int:
    count = 0
    for assignment in schedule_input.locked_assignments:
        if (
            suite_code_for_assignment(assignment, class_metadata) == suite_code
            and assignment.task.subject == subject
            and week_key(assignment.candidate.slots) == week
        ):
            count += 1
    for index, assignment in enumerate(assignments):
        if excluded_index is not None and index == excluded_index:
            continue
        if (
            suite_code_for_assignment(assignment, class_metadata) == suite_code
            and assignment.task.subject == subject
            and week_key(assignment.candidate.slots) == week
        ):
            count += 1
    return count


def assignment_dates_for_teacher(
    schedule_input: scheduler.ScheduleInput,
    assignments: Sequence[scheduler.Assignment],
    teacher_id: str,
    excluded_index: Optional[int] = None,
) -> Set[str]:
    dates = {
        assignment.candidate.slots[0].date
        for assignment in schedule_input.locked_assignments
        if assignment.candidate.teacher_id == teacher_id
    }
    for index, assignment in enumerate(assignments):
        if excluded_index is not None and index == excluded_index:
            continue
        if assignment.candidate.teacher_id == teacher_id:
            dates.add(assignment.candidate.slots[0].date)
    return dates


def find_three_day_violation_index(
    schedule_input: scheduler.ScheduleInput,
    assignments: Sequence[scheduler.Assignment],
    class_metadata: Dict[str, Dict[str, str]],
    blocked_indices: Optional[Set[int]] = None,
) -> Optional[int]:
    blocked_indices = blocked_indices or set()
    suite_subject_dates: Dict[Tuple[str, str], Set[str]] = {}
    for assignment in [*schedule_input.locked_assignments, *assignments]:
        suite_code = suite_code_for_assignment(assignment, class_metadata)
        suite_subject_dates.setdefault((suite_code, assignment.task.subject), set()).add(assignment.candidate.slots[0].date)
    for (suite_code, subject), dates in sorted(suite_subject_dates.items()):
        if subject != "数学":
            continue
        max_consecutive_days = math_max_consecutive_days_for_suite(
            schedule_input,
            assignments,
            class_metadata,
            suite_code,
        )
        for run in run_dates_over_limit(dates, max_consecutive_days):
            for date_text in (*run[1:], run[0]):
                for index, assignment in enumerate(assignments):
                    if index in blocked_indices:
                        continue
                    if (
                        assignment.task.subject == subject
                        and suite_code_for_assignment(assignment, class_metadata) == suite_code
                        and assignment.candidate.slots[0].date == date_text
                    ):
                        return index

    teacher_dates: Dict[str, Set[str]] = {}
    for assignment in [*schedule_input.locked_assignments, *assignments]:
        if assignment.task.subject not in {"英语", "政治"} or not assignment.candidate.teacher_id:
            continue
        teacher_dates.setdefault(assignment.candidate.teacher_id, set()).add(assignment.candidate.slots[0].date)
    for teacher_id, dates in sorted(teacher_dates.items()):
        for run in run_dates(dates):
            for date_text in (run[1], run[2], run[0]):
                for index, assignment in enumerate(assignments):
                    if index in blocked_indices:
                        continue
                    if (
                        assignment.task.subject in {"英语", "政治"}
                        and assignment.candidate.teacher_id == teacher_id
                        and assignment.candidate.slots[0].date == date_text
                    ):
                        return index
    return None


def improve_three_day_run_balance(
    schedule_input: scheduler.ScheduleInput,
    assignments: Sequence[scheduler.Assignment],
    domains: Dict[str, List[scheduler.Candidate]],
    class_metadata: Dict[str, Dict[str, str]],
    preferred_subject_periods: Dict[str, str],
) -> List[scheduler.Assignment]:
    result = scheduler.sorted_assignments(list(assignments))
    stage_tasks_by_class = stage_order_tasks_by_class(schedule_input)
    blocked_indices: Set[int] = set()
    for _ in range(500):
        assignment_index = find_three_day_violation_index(schedule_input, result, class_metadata, blocked_indices)
        if assignment_index is None:
            break
        assignment = result[assignment_index]
        task = assignment.task
        suite_code = suite_code_for_assignment(assignment, class_metadata)
        class_slot_used, teacher_slot_used, room_slot_used, conflict_group_slot_used = assignment_constraint_sets(
            schedule_input,
            result,
            excluded_index=assignment_index,
        )
        daily_teacher_loads = class_teacher_day_loads(
            schedule_input,
            result,
            excluded_index=assignment_index,
        )
        used_suite_subject_dates = assignment_dates_for_suite_subject(
            schedule_input,
            result,
            class_metadata,
            suite_code,
            task.subject,
            excluded_index=assignment_index,
        )
        used_teacher_dates = assignment_dates_for_teacher(
            schedule_input,
            result,
            assignment.candidate.teacher_id,
            excluded_index=assignment_index,
        )
        replacements: List[scheduler.Candidate] = []
        for candidate in domains.get(task.task_id, []):
            if tuple(slot.id for slot in candidate.slots) == tuple(slot.id for slot in assignment.candidate.slots):
                continue
            first_slot = candidate.slots[0]
            if first_slot.date in used_suite_subject_dates:
                continue
            if task.subject == "数学":
                max_consecutive_days = math_max_consecutive_days_for_suite(
                    schedule_input,
                    result,
                    class_metadata,
                    suite_code,
                )
                if creates_teacher_run_over_limit(
                    used_suite_subject_dates,
                    first_slot.date,
                    max_consecutive_days,
                ):
                    continue
            if task.subject in {"英语", "政治"} and creates_three_day_teacher_run(used_teacher_dates, first_slot.date):
                continue
            if (
                is_long_camp_assignment(assignment, class_metadata)
                and task.subject in {"英语", "政治", "数学"}
                and assignment_week_load_for_suite_subject(
                    schedule_input,
                    result,
                    class_metadata,
                    suite_code,
                    task.subject,
                    week_key(candidate.slots),
                    excluded_index=assignment_index,
                )
                >= 4
            ):
                continue
            if not replacement_preserves_first_lesson_module(
                result,
                assignment_index,
                task,
                candidate,
            ):
                continue
            if not stage_order_candidate_allowed(
                schedule_input,
                stage_tasks_by_class,
                result,
                task,
                candidate,
                excluded_index=assignment_index,
            ):
                continue
            if not candidate_avoids_same_class_teacher_day_limit(
                daily_teacher_loads,
                task,
                candidate,
            ):
                continue
            if not candidate_is_valid(
                schedule_input,
                class_slot_used,
                teacher_slot_used,
                room_slot_used,
                conflict_group_slot_used,
                task,
                candidate,
            ):
                continue
            replacements.append(candidate)
        if not replacements:
            blocked_indices.add(assignment_index)
            continue
        preferred_period = preferred_subject_periods.get(task.subject)
        original_key = scheduler.slot_sort_key(assignment.candidate.slots[0])
        replacements.sort(
            key=lambda candidate: (
                0 if not preferred_period or candidate.slots[0].period == preferred_period else 1,
                abs(
                    (
                        Date.fromisoformat(candidate.slots[0].date)
                        - Date.fromisoformat(assignment.candidate.slots[0].date)
                    ).days
                ),
                scheduler.slot_sort_key(candidate.slots[0]) < original_key,
                scheduler.slot_sort_key(candidate.slots[0]),
            )
        )
        result[assignment_index] = scheduler.Assignment(task=task, candidate=replacements[0])
        result = scheduler.sorted_assignments(result)
        blocked_indices.clear()
    return result


def schedule_round_robin(
    schedule_input: scheduler.ScheduleInput,
    class_order: Sequence[str],
    subject_week_bounds: Optional[SubjectWeekBounds] = None,
    preferred_weekly_total_max: Optional[int] = None,
    hard_weekly_total_max: Optional[int] = None,
    balance_public_subject_weeks: bool = False,
    avoid_public_subject_consecutive_days: bool = False,
    prefer_public_teacher_alternation: bool = False,
    subject_max_consecutive_days: Optional[int] = None,
    allow_same_subject_day_fallback: bool = True,
    teacher_alternation_subjects: Optional[Set[str]] = None,
    spacing_improvement_passes: int = 300,
    require_all_subject_weeks: bool = False,
    strict_subject_week_quotas: bool = False,
    use_average_subject_week_bounds: bool = False,
    subject_week_hard_max: Optional[Dict[str, int]] = None,
) -> List[scheduler.Assignment]:
    avoid_public_subject_consecutive_days = avoid_public_subject_consecutive_days or balance_public_subject_weeks
    prefer_public_teacher_alternation = prefer_public_teacher_alternation or balance_public_subject_weeks
    effective_teacher_alternation_subjects = teacher_alternation_subjects or LONG_CAMP_ALTERNATING_SUBJECTS
    tasks_by_class: Dict[str, List[scheduler.CourseBlock]] = {class_id: [] for class_id in class_order}
    for task in scheduler.build_course_blocks(schedule_input.classes):
        if task.class_id in tasks_by_class:
            tasks_by_class[task.class_id].append(task)

    all_tasks = [task for tasks in tasks_by_class.values() for task in tasks]
    domains = scheduler.candidate_domains(all_tasks, schedule_input)
    domains_by_slot_key: Dict[str, Dict[Tuple[str, ...], List[scheduler.Candidate]]] = {}
    for task_id, candidates in domains.items():
        by_slot_key: Dict[Tuple[str, ...], List[scheduler.Candidate]] = defaultdict(list)
        for candidate in candidates:
            by_slot_key[tuple(slot.id for slot in candidate.slots)].append(candidate)
        domains_by_slot_key[task_id] = by_slot_key
    missing = [task_id for task_id, candidates in domains.items() if not candidates]
    if missing:
        raise ValueError(f"以下任务没有候选课节: {', '.join(missing[:20])}")
    first_lesson_anchor_keys = stage_first_lesson_anchor_keys(all_tasks)
    first_lesson_anchor_task_ids = stage_first_lesson_anchor_task_ids(all_tasks)
    first_lesson_anchor_positions: Dict[Tuple[str, str, str], Tuple[str, int, int, str]] = {}
    stage_tasks_by_class = stage_order_tasks_by_class(schedule_input)
    for class_id in tasks_by_class:
        tasks_by_class[class_id].sort(
            key=lambda task: (
                effective_task_stage_sort_rank(schedule_input, stage_tasks_by_class, task),
                0 if task.task_id in first_lesson_anchor_task_ids else 1,
            )
        )
        if prefer_public_teacher_alternation and any(task.subject in effective_teacher_alternation_subjects for task in tasks_by_class[class_id]):
            grouped_by_rank: Dict[int, List[scheduler.CourseBlock]] = defaultdict(list)
            for task in tasks_by_class[class_id]:
                rank = effective_task_stage_sort_rank(schedule_input, stage_tasks_by_class, task)
                grouped_by_rank[rank].append(task)
            tasks_by_class[class_id] = [
                task
                for rank in sorted(grouped_by_rank)
                for task in alternate_teacher_tasks(grouped_by_rank[rank])
            ]

    class_slot_used, teacher_slot_used, room_slot_used, conflict_group_slot_used = scheduler.locked_constraint_sets(schedule_input)
    assignments: List[scheduler.Assignment] = []
    next_index = {class_id: 0 for class_id in class_order}
    cursor = 0
    max_block_hours = max((task.block_hours for tasks in tasks_by_class.values() for task in tasks), default=4)
    slot_blocks = scheduler.build_contiguous_slot_blocks(schedule_input.time_slots, max_block_hours)
    subject_counts: Dict[str, int] = {}
    for task in all_tasks:
        subject_counts[task.subject] = subject_counts.get(task.subject, 0) + 1
    subject_slot_blocks: Dict[str, List[Tuple[scheduler.TimeSlot, ...]]] = {}
    for subject in subject_counts:
        seen_slot_blocks: Set[Tuple[str, ...]] = set()
        blocks: List[Tuple[scheduler.TimeSlot, ...]] = []
        for task in all_tasks:
            if task.subject != subject:
                continue
            for candidate in domains[task.task_id]:
                slot_key = tuple(slot.id for slot in candidate.slots)
                if slot_key in seen_slot_blocks:
                    continue
                seen_slot_blocks.add(slot_key)
                blocks.append(candidate.slots)
        subject_slot_blocks[subject] = sorted(blocks, key=slot_block_key)
    effective_subject_week_bounds = subject_week_bounds
    if use_average_subject_week_bounds:
        effective_subject_week_bounds = average_subject_week_bounds_from_counts(
            subject_slot_blocks,
            subject_counts,
            subject_week_hard_max,
        )
    elif effective_subject_week_bounds is None and balance_public_subject_weeks:
        effective_subject_week_bounds = average_subject_week_bounds_from_counts(
            subject_slot_blocks,
            subject_counts,
            long_camp_subject_week_hard_max(set(subject_counts)),
        )
    subject_week_quotas = (
        bounded_subject_week_quotas(
            slot_blocks,
            subject_slot_blocks,
            subject_counts,
            effective_subject_week_bounds,
            preferred_weekly_total_max,
            require_all_subject_weeks,
        )
        if effective_subject_week_bounds
        else {}
    )
    subject_week_limits = max_only_subject_week_limits(
        subject_slot_blocks,
        effective_subject_week_bounds,
    )
    if not subject_week_quotas and balance_public_subject_weeks:
        subject_week_quotas = {
            subject: balanced_week_quotas(list(slot_blocks), count)
            for subject, count in subject_counts.items()
            if subject in PUBLIC_SUBJECTS
        }
    subject_week_loads: Dict[Tuple[str, Tuple[int, int]], int] = {}
    week_total_loads: Dict[Tuple[int, int], int] = {}
    week_subjects: Dict[Tuple[int, int], Set[str]] = {}
    subject_date_used: Set[Tuple[str, str]] = set()
    subject_dates: Dict[str, Set[str]] = {}
    class_subject_dates: Dict[Tuple[str, str], Set[str]] = {}
    teacher_dates: Dict[str, Set[str]] = {}
    daily_teacher_loads = class_teacher_day_loads(schedule_input, assignments)
    for locked_assignment in schedule_input.locked_assignments:
        first = locked_assignment.candidate.slots[0]
        if locked_assignment.task.subject:
            subject_dates.setdefault(locked_assignment.task.subject, set()).add(first.date)
            if locked_assignment.task.class_id in tasks_by_class:
                class_subject_dates.setdefault(
                    (locked_assignment.task.class_id, locked_assignment.task.subject),
                    set(),
                ).add(first.date)
        teacher_key = candidate_teacher_key(locked_assignment.candidate)
        if teacher_key:
            teacher_dates.setdefault(teacher_key, set()).add(first.date)

    def remaining_count() -> int:
        return sum(len(tasks_by_class[class_id]) - next_index[class_id] for class_id in class_order)

    def candidate_for_block(
        task: scheduler.CourseBlock,
        slot_block: Tuple[scheduler.TimeSlot, ...],
        avoid_same_subject_day: bool,
        avoid_three_day_run: bool,
        enforce_subject_quota: bool = False,
    ) -> Optional[scheduler.Candidate]:
        slot_ids = tuple(slot.id for slot in slot_block)
        first = slot_block[0]
        if avoid_same_subject_day and (task.subject, first.date) in subject_date_used:
            return None
        if (
            subject_max_consecutive_days is not None
            and creates_teacher_run_over_limit(
                class_subject_dates.get((task.class_id, task.subject), set()),
                first.date,
                subject_max_consecutive_days,
            )
        ):
            return None
        if (
            avoid_same_subject_day
            and first.date in class_subject_dates.get((task.class_id, task.subject), set())
        ):
            return None
        if (
            avoid_public_subject_consecutive_days
            and avoid_same_subject_day
            and task.subject in LONG_CAMP_ALTERNATING_SUBJECTS
            and creates_adjacent_subject_day(subject_dates.get(task.subject, set()), first.date)
        ):
            return None
        if avoid_three_day_run and task.subject == "数学":
            if balance_public_subject_weeks:
                if creates_teacher_run_over_limit(
                    subject_dates.get(task.subject, set()),
                    first.date,
                    LONG_CAMP_MATH_MAX_CONSECUTIVE_DAYS,
                ):
                    return None
            elif creates_three_day_teacher_run(subject_dates.get(task.subject, set()), first.date):
                return None
        if (
            avoid_three_day_run
            and task.subject in {"英语", "政治"}
            and (task.teacher_id or task.teacher_name)
            and creates_three_day_teacher_run(teacher_dates.get(task.teacher_id or task.teacher_name, set()), first.date)
        ):
            return None
        if (
            task.subject in CORE_TEACHER_CONSECUTIVE_LIMIT_SUBJECTS
            and (task.teacher_id or task.teacher_name)
            and creates_teacher_run_over_limit(
                teacher_dates.get(task.teacher_id or task.teacher_name, set()),
                first.date,
                CORE_TEACHER_MAX_CONSECUTIVE_DAYS,
            )
        ):
            return None
        key = week_key(slot_block)
        if hard_weekly_total_max is not None and week_total_loads.get(key, 0) >= hard_weekly_total_max:
            return None
        if enforce_subject_quota and strict_subject_week_quotas and task.subject in subject_week_quotas:
            if subject_week_loads.get((task.subject, key), 0) >= subject_week_quotas[task.subject].get(key, 0):
                return None
        elif enforce_subject_quota and task.subject in subject_week_limits:
            if subject_week_loads.get((task.subject, key), 0) >= subject_week_limits[task.subject].get(key, 0):
                return None
        elif enforce_subject_quota and task.subject in subject_week_quotas:
            if subject_week_loads.get((task.subject, key), 0) >= subject_week_quotas[task.subject].get(key, 0):
                return None
        candidates = [
            candidate
            for candidate in domains_by_slot_key[task.task_id].get(slot_ids, [])
            if first_lesson_candidate_allowed(task, candidate, first_lesson_anchor_keys, first_lesson_anchor_positions)
            and stage_order_candidate_allowed(schedule_input, stage_tasks_by_class, assignments, task, candidate)
            and candidate_avoids_same_class_teacher_day_limit(daily_teacher_loads, task, candidate)
            and candidate_is_valid(
                schedule_input,
                class_slot_used,
                teacher_slot_used,
                room_slot_used,
                conflict_group_slot_used,
                task,
                candidate,
            )
        ]
        if task.subject in CORE_TEACHER_CONSECUTIVE_LIMIT_SUBJECTS:
            candidates = [
                candidate
                for candidate in candidates
                if not candidate_teacher_key(candidate)
                or not creates_teacher_run_over_limit(
                    teacher_dates.get(candidate_teacher_key(candidate), set()),
                    first.date,
                    CORE_TEACHER_MAX_CONSECUTIVE_DAYS,
                )
            ]
        candidates.sort(
            key=lambda candidate: (
                scheduler.candidate_same_day_teacher_travel_penalty(
                    schedule_input,
                    [*schedule_input.locked_assignments, *assignments],
                    task,
                    candidate,
                ),
                candidate.room_id,
            )
        )
        return candidates[0] if candidates else None

    def quota_candidate_for_block(
        slot_block: Tuple[scheduler.TimeSlot, ...],
        avoid_same_subject_day: bool,
        avoid_three_day_run: bool,
    ) -> Optional[Tuple[str, scheduler.CourseBlock, scheduler.Candidate]]:
        first = slot_block[0]
        preferred_periods = {"数学": "AM", "英语": "PM", "政治": "PM"} if "数学" in subject_counts else {}
        options: List[Tuple[Tuple[int, int, int, int, str], str, scheduler.CourseBlock, scheduler.Candidate]] = []
        for class_position, class_id in enumerate(class_order):
            if next_index[class_id] >= len(tasks_by_class[class_id]):
                continue
            task = tasks_by_class[class_id][next_index[class_id]]
            if task.subject in subject_week_quotas:
                quota = subject_week_quotas[task.subject].get(week_key(slot_block), 0)
                load = subject_week_loads.get((task.subject, week_key(slot_block)), 0)
                if load >= quota:
                    continue
                remaining = quota - load
            else:
                remaining = 0
            candidate = candidate_for_block(
                task,
                slot_block,
                avoid_same_subject_day,
                avoid_three_day_run,
                enforce_subject_quota=True,
            )
            if not candidate:
                continue
            preferred_period = preferred_periods.get(task.subject)
            period_penalty = 0 if not preferred_period or first.period == preferred_period else 1
            subjects_this_week = week_subjects.get(week_key(slot_block), set())
            subject_mix_penalty = (
                2
                if len(subject_counts) > 1
                and subjects_this_week
                and task.subject in subjects_this_week
                and len(subjects_this_week) < min(2, len(subject_counts))
                else 0
            )
            teacher_repeat_penalty = (
                1
                if prefer_public_teacher_alternation
                and task.subject in effective_teacher_alternation_subjects
                and subject_neighbor_teacher_repeat(assignments, task, candidate)
                else 0
            )
            travel_penalty = scheduler.candidate_same_day_teacher_travel_penalty(
                schedule_input,
                [*schedule_input.locked_assignments, *assignments],
                task,
                candidate,
            )
            options.append((
                (
                    travel_penalty,
                    teacher_repeat_penalty,
                    subject_mix_penalty,
                    week_total_loads.get(week_key(slot_block), 0),
                    period_penalty,
                    -remaining,
                    SUBJECT_ORDER.get(task.subject, 99),
                    class_position,
                    task.task_id,
                ),
                class_id,
                task,
                candidate,
            ))
        if not options:
            return None
        options.sort(key=lambda item: item[0])
        _score, class_id, task, candidate = options[0]
        return class_id, task, candidate

    def fallback_candidate_for_block(
        slot_block: Tuple[scheduler.TimeSlot, ...],
        avoid_same_subject_day: bool,
        avoid_three_day_run: bool,
    ) -> Optional[Tuple[str, scheduler.CourseBlock, scheduler.Candidate]]:
        first = slot_block[0]
        key = week_key(slot_block)
        preferred_periods = {"数学": "AM", "英语": "PM", "政治": "PM"} if "数学" in subject_counts else {}
        options: List[Tuple[Tuple[int, int, int, int, str], str, scheduler.CourseBlock, scheduler.Candidate]] = []
        for class_position, class_id in enumerate(class_order):
            if next_index[class_id] >= len(tasks_by_class[class_id]):
                continue
            task = tasks_by_class[class_id][next_index[class_id]]
            candidate = candidate_for_block(
                task,
                slot_block,
                avoid_same_subject_day,
                avoid_three_day_run,
                enforce_subject_quota=bool(subject_week_quotas),
            )
            if not candidate:
                continue
            quota = subject_week_quotas.get(task.subject, {}).get(key)
            load = subject_week_loads.get((task.subject, key), 0)
            subject_overflow_penalty = max(0, load + 1 - quota) if quota is not None else 0
            total_quota = preferred_weekly_total_max or week_total_loads.get(key, 0) + 1
            week_overflow_penalty = max(0, week_total_loads.get(key, 0) + 1 - total_quota)
            subjects_this_week = week_subjects.get(key, set())
            subject_mix_penalty = (
                2
                if len(subject_counts) > 1
                and subjects_this_week
                and task.subject in subjects_this_week
                and len(subjects_this_week) < min(2, len(subject_counts))
                else 0
            )
            preferred_period = preferred_periods.get(task.subject)
            period_penalty = 0 if not preferred_period or first.period == preferred_period else 1
            teacher_repeat_penalty = (
                1
                if prefer_public_teacher_alternation
                and task.subject in effective_teacher_alternation_subjects
                and subject_neighbor_teacher_repeat(assignments, task, candidate)
                else 0
            )
            travel_penalty = scheduler.candidate_same_day_teacher_travel_penalty(
                schedule_input,
                [*schedule_input.locked_assignments, *assignments],
                task,
                candidate,
            )
            options.append((
                (
                    travel_penalty,
                    teacher_repeat_penalty,
                    week_overflow_penalty,
                    subject_mix_penalty,
                    subject_overflow_penalty,
                    load,
                    period_penalty,
                    class_position,
                    task.task_id,
                ),
                class_id,
                task,
                candidate,
            ))
        if not options:
            return None
        options.sort(key=lambda item: item[0])
        _score, class_id, task, candidate = options[0]
        return class_id, task, candidate

    fallback_modes = (
        ((True, True), (True, False), (False, True), (False, False))
        if allow_same_subject_day_fallback
        else ((True, True), (True, False))
    )
    for slot_block in slot_blocks:
        if remaining_count() == 0:
            break
        placed = False
        for avoid_same_subject_day, avoid_three_day_run in fallback_modes:
            quota_choice = (
                quota_candidate_for_block(slot_block, avoid_same_subject_day, avoid_three_day_run)
                if subject_week_quotas
                else None
            )
            if quota_choice:
                class_id, task, candidate = quota_choice
                assignments.append(
                    place_candidate(
                        schedule_input,
                        class_slot_used,
                        teacher_slot_used,
                        room_slot_used,
                        conflict_group_slot_used,
                        task,
                        candidate,
                    )
                )
                first = candidate.slots[0]
                subject_date_used.add((task.subject, first.date))
                key = week_key(candidate.slots)
                subject_week_loads[(task.subject, key)] = subject_week_loads.get((task.subject, key), 0) + 1
                week_total_loads[key] = week_total_loads.get(key, 0) + 1
                week_subjects.setdefault(key, set()).add(task.subject)
                subject_dates.setdefault(task.subject, set()).add(first.date)
                class_subject_dates.setdefault((task.class_id, task.subject), set()).add(first.date)
                teacher_key = candidate_teacher_key(candidate)
                if teacher_key:
                    teacher_dates.setdefault(teacher_key, set()).add(first.date)
                add_class_teacher_day_load(daily_teacher_loads, task, candidate)
                mark_first_lesson_anchor_done(task, candidate, first_lesson_anchor_keys, first_lesson_anchor_positions)
                next_index[class_id] += 1
                placed = True
                break
            if subject_week_quotas:
                fallback_choice = fallback_candidate_for_block(
                    slot_block,
                    avoid_same_subject_day,
                    avoid_three_day_run,
                )
                if fallback_choice:
                    class_id, task, candidate = fallback_choice
                    assignments.append(
                        place_candidate(
                            schedule_input,
                            class_slot_used,
                            teacher_slot_used,
                            room_slot_used,
                            conflict_group_slot_used,
                            task,
                            candidate,
                        )
                    )
                    first = candidate.slots[0]
                    subject_date_used.add((task.subject, first.date))
                    key = week_key(candidate.slots)
                    subject_week_loads[(task.subject, key)] = subject_week_loads.get((task.subject, key), 0) + 1
                    week_total_loads[key] = week_total_loads.get(key, 0) + 1
                    week_subjects.setdefault(key, set()).add(task.subject)
                    subject_dates.setdefault(task.subject, set()).add(first.date)
                    class_subject_dates.setdefault((task.class_id, task.subject), set()).add(first.date)
                    teacher_key = candidate_teacher_key(candidate)
                    if teacher_key:
                        teacher_dates.setdefault(teacher_key, set()).add(first.date)
                    add_class_teacher_day_load(daily_teacher_loads, task, candidate)
                    mark_first_lesson_anchor_done(task, candidate, first_lesson_anchor_keys, first_lesson_anchor_positions)
                    next_index[class_id] += 1
                    placed = True
                    break
                continue
            for offset in range(len(class_order)):
                class_id = class_order[(cursor + offset) % len(class_order)]
                if next_index[class_id] >= len(tasks_by_class[class_id]):
                    continue
                task = tasks_by_class[class_id][next_index[class_id]]
                candidate = candidate_for_block(task, slot_block, avoid_same_subject_day, avoid_three_day_run)
                if not candidate:
                    continue
                assignments.append(
                    place_candidate(
                        schedule_input,
                        class_slot_used,
                        teacher_slot_used,
                        room_slot_used,
                        conflict_group_slot_used,
                        task,
                        candidate,
                    )
                )
                first = candidate.slots[0]
                subject_date_used.add((task.subject, first.date))
                key = week_key(candidate.slots)
                subject_week_loads[(task.subject, key)] = subject_week_loads.get((task.subject, key), 0) + 1
                week_total_loads[key] = week_total_loads.get(key, 0) + 1
                week_subjects.setdefault(key, set()).add(task.subject)
                subject_dates.setdefault(task.subject, set()).add(first.date)
                class_subject_dates.setdefault((task.class_id, task.subject), set()).add(first.date)
                teacher_key = candidate_teacher_key(candidate)
                if teacher_key:
                    teacher_dates.setdefault(teacher_key, set()).add(first.date)
                add_class_teacher_day_load(daily_teacher_loads, task, candidate)
                mark_first_lesson_anchor_done(task, candidate, first_lesson_anchor_keys, first_lesson_anchor_positions)
                next_index[class_id] += 1
                cursor = (cursor + offset + 1) % len(class_order)
                placed = True
                break
            if placed:
                break

    if remaining_count() != 0:
        remaining = [
            tasks_by_class[class_id][index].task_id
            for class_id in class_order
            for index in range(next_index[class_id], len(tasks_by_class[class_id]))
        ]
        raise ValueError(f"轮排策略未能排完全部任务，剩余 {len(remaining)} 个: {', '.join(remaining[:20])}")

    if subject_week_quotas and hard_weekly_total_max is None:
        domains = scheduler.candidate_domains(all_tasks, schedule_input)
        assignments = improve_subject_week_balance(
            schedule_input,
            assignments,
            domains,
            subject_week_quotas,
            {"数学": "AM", "英语": "PM", "政治": "PM"} if "数学" in subject_counts else {},
            set(subject_week_quotas),
            LONG_CAMP_MATH_MAX_CONSECUTIVE_DAYS if balance_public_subject_weeks else None,
        )
        if balance_public_subject_weeks:
            assignments = improve_total_week_balance(
                schedule_input,
                assignments,
                domains,
                sum_subject_week_quotas(subject_week_quotas, ()),
                {"数学": "AM", "英语": "PM", "政治": "PM"} if "数学" in subject_counts else {},
            )

    if (avoid_public_subject_consecutive_days or prefer_public_teacher_alternation) and hard_weekly_total_max is None:
        subject_weekly_max_limits = {
            subject: weekly_max
            for subject, (_weekly_min, weekly_max) in (effective_subject_week_bounds or {}).items()
            if weekly_max is not None
        }
        assignments = improve_public_subject_spacing(
            schedule_input,
            assignments,
            domains,
            LONG_CAMP_ALTERNATING_SUBJECTS,
            {"数学": "AM", "英语": "PM", "政治": "PM"} if "数学" in subject_counts else {},
            subject_weekly_max_limits if balance_public_subject_weeks else None,
            max_passes=spacing_improvement_passes,
        )
    if prefer_public_teacher_alternation:
        assignments = rebalance_subject_teacher_alternation(
            schedule_input,
            assignments,
            domains,
            effective_teacher_alternation_subjects,
        )
    return require_schedule_order(schedule_input, assignments)


def main() -> None:
    parser = argparse.ArgumentParser(description="按班级/阶段生成课表维护结果和每日表格")
    parser.add_argument("--input", type=Path, default=Path("data/scheduler_input_draft.json"))
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--class-ids", default="", help="班级 ID，逗号分隔")
    parser.add_argument("--stages", default="", help="阶段，逗号分隔；留空表示全部")
    parser.add_argument("--subjects", default="", help="科目，逗号分隔；留空表示全部")
    parser.add_argument("--suite-code", default="", help="套班编码，用于页面分组")
    parser.add_argument("--suite-codes", default="", help="多个套班编码，逗号分隔；未传 class-ids 时自动选择公共课班级")
    parser.add_argument("--schedule-window-ids", default="", help="年度排课窗口 ID，逗号分隔，例如 2026暑假；会同步读取班级排课窗口")
    parser.add_argument("--season-window-ids", default="", help="季节窗口 ID 或名称，逗号分隔，例如 WINDOW_SUMMER 或 暑假；会同步读取班级排课窗口")
    parser.add_argument("--class-window-boundaries", type=Path, default=Path("data/class_window_boundaries.csv"), help="班级排课窗口 CSV")
    parser.add_argument("--ignore-class-window-boundaries", action="store_true", help="不使用班级排课窗口，仅按命令行日期/时段和班级基础信息过滤")
    parser.add_argument("--start-date", default="")
    parser.add_argument("--start-period", default="")
    parser.add_argument("--end-date", default="")
    parser.add_argument("--end-period", default="")
    parser.add_argument("--periods", default="AM,PM")
    parser.add_argument("--room-ids", default="", help="强制使用的教室 ID，逗号分隔")
    parser.add_argument("--locked-csvs", default="", help="已确认课表 CSV，逗号分隔；作为锁定课表参与冲突检查")
    parser.add_argument("--include-locked-csvs-in-output", action="store_true", help="把 locked-csvs 一并写入当前 CSV/HTML")
    parser.add_argument("--title", default="课表维护预览")
    parser.add_argument("--strategy", choices=["scheduler", "round-robin", "camp-balanced"], default="scheduler")
    parser.add_argument("--output-csv", required=True, type=Path)
    parser.add_argument("--output-html", required=True, type=Path)
    args = parser.parse_args()

    suite_codes = split_values(args.suite_codes)
    stages = set(split_values(args.stages)) or None
    subjects = set(split_values(args.subjects)) or None
    class_ids = split_values(args.class_ids)
    if not class_ids and suite_codes:
        class_ids = class_ids_for_suite_codes(args.data_dir, suite_codes, subjects)
    if not class_ids:
        raise ValueError("需要传入 --class-ids，或传入 --suite-codes 自动选择公共课班级")
    schedule_window_ids = set(split_values(args.schedule_window_ids))
    season_window_ids = set(split_values(args.season_window_ids))
    periods = set(split_values(args.periods)) or None
    room_ids = set(split_values(args.room_ids)) or None
    start_date = args.start_date or None
    end_date = args.end_date or None
    start_period = (args.start_period or "").upper() or None
    end_period = (args.end_period or "").upper() or None
    class_metadata = load_class_metadata(args.data_dir)
    class_window_constraints = {}
    quarters = None

    if not args.ignore_class_window_boundaries and (schedule_window_ids or season_window_ids):
        class_window_constraints = load_class_window_constraints(
            args.class_window_boundaries,
            class_ids=set(class_ids),
            schedule_window_ids=schedule_window_ids or None,
            season_window_ids=season_window_ids or None,
        )
        if not class_window_constraints:
            raise ValueError("当前班级没有匹配的班级排课窗口记录")
        boundary_start_date, boundary_start_period, boundary_end_date, boundary_end_period = bounds_for_constraints(
            class_window_constraints.values()
        )
        start_date = start_date or boundary_start_date
        start_period = start_period or boundary_start_period
        end_date = end_date or boundary_end_date
        end_period = end_period or boundary_end_period
        quarters = season_names_for_constraints(class_window_constraints.values()) or None

    source = scheduler.load_input(args.input)
    locked_csv_paths = [Path(path) for path in split_values(args.locked_csvs)]
    locked_csv_assignments = load_locked_csv_assignments(locked_csv_paths, source)
    if locked_csv_assignments:
        source = replace(source, locked_assignments=[*source.locked_assignments, *locked_csv_assignments])
    batch_input = filtered_schedule_input(
        source,
        class_ids=class_ids,
        stages=stages,
        subjects=subjects,
        start=start_date,
        end=end_date,
        start_period=start_period,
        end_period=end_period,
        periods=periods,
        room_ids=room_ids,
        quarters=quarters,
        class_window_constraints=class_window_constraints,
    )
    if args.strategy == "camp-balanced":
        selected_class_ids = [class_id for class_id in class_ids if class_id in batch_input.classes]
        selected_suites = {
            class_metadata.get(class_id, {}).get("suite_code", "")
            for class_id in selected_class_ids
        } - {""}
        if len(selected_suites) > 1:
            assignments = schedule_balanced_camp_by_suite(batch_input, selected_class_ids, class_metadata)
        else:
            assignments = schedule_balanced_camp(batch_input, selected_class_ids)
    elif args.strategy == "round-robin":
        assignments = schedule_round_robin(batch_input, [class_id for class_id in class_ids if class_id in batch_input.classes])
    else:
        assignments = [
            assignment
            for assignment in scheduler.schedule(batch_input)
            if assignment.task.class_id in batch_input.classes
        ]
        assignments = scheduler.sorted_assignments(assignments)
    room_names = load_room_names(args.data_dir)
    if args.include_locked_csvs_in_output:
        assignments = scheduler.sorted_assignments([*locked_csv_assignments, *assignments])
    write_batch_csv(assignments, args.output_csv, room_names, class_metadata, load_product_course_tags(args.data_dir))
    write_day_table_html(
        assignments,
        args.output_html,
        args.title,
        sorted(periods or {"AM", "PM"}, key=scheduler.period_sort_value),
        room_names,
        start_date,
        end_date,
        class_metadata,
        class_window_constraints,
        load_product_course_tags(args.data_dir),
    )
    print(f"已生成 {len(assignments)} 条课表维护结果")
    print(args.output_csv)
    print(args.output_html)


if __name__ == "__main__":
    main()
