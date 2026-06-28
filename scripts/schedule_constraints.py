#!/usr/bin/env python3
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Set, Tuple

import scheduler
from scripts.schedule_conflicts import assignments_overlap


ConstraintSets = Tuple[Set[Tuple[str, str]], Set[Tuple[str, str]], Set[Tuple[str, str]], Set[Tuple[str, str]]]


def assignment_date_period_keys(assignment: scheduler.Assignment) -> Set[Tuple[str, str]]:
    return {(slot.date, slot.period) for slot in assignment.candidate.slots}


def candidate_date_period_keys(candidate: scheduler.Candidate) -> Set[Tuple[str, str]]:
    return {(slot.date, slot.period) for slot in candidate.slots}


def add_assignment_to_constraint_sets(
    schedule_input: scheduler.ScheduleInput,
    assignment: scheduler.Assignment,
    constraint_sets: ConstraintSets,
) -> None:
    class_slot_used, teacher_slot_used, room_slot_used, conflict_group_slot_used = constraint_sets
    group_ids = schedule_input.class_conflict_groups.get(assignment.task.class_id, set())
    for slot in assignment.candidate.slots:
        class_slot_used.add((assignment.task.class_id, slot.id))
        if assignment.candidate.teacher_id:
            teacher_slot_used.add((assignment.candidate.teacher_id, slot.id))
        room_slot_used.add((assignment.candidate.room_id, slot.id))
        for group_id in group_ids:
            conflict_group_slot_used.add((group_id, slot.id))


def assignment_constraint_sets(
    schedule_input: scheduler.ScheduleInput,
    assignments: Sequence[scheduler.Assignment],
    excluded_index: Optional[int] = None,
) -> ConstraintSets:
    constraint_sets = scheduler.locked_constraint_sets(schedule_input)
    for index, assignment in enumerate(assignments):
        if excluded_index is not None and index == excluded_index:
            continue
        add_assignment_to_constraint_sets(schedule_input, assignment, constraint_sets)
    return constraint_sets


def class_day_rule_loads_from_used_slots(
    schedule_input: scheduler.ScheduleInput,
    class_slot_used: Set[Tuple[str, str]],
) -> Tuple[Dict[Tuple[str, str], float], Dict[Tuple[str, str], int]]:
    slot_by_id = {slot.id: slot for slot in schedule_input.time_slots}
    hour_loads: Dict[Tuple[str, str], float] = {}
    date_periods: Dict[Tuple[str, str], Set[str]] = {}
    for class_id, slot_id in class_slot_used:
        slot = slot_by_id.get(slot_id)
        if not slot:
            continue
        key = (class_id, slot.date)
        hour_loads[key] = hour_loads.get(key, 0.0) + float(slot.duration_hours or 0)
        date_periods.setdefault(key, set()).add(slot.period)
    block_loads = {key: len(periods) for key, periods in date_periods.items()}
    return hour_loads, block_loads


def candidate_is_valid(
    schedule_input: scheduler.ScheduleInput,
    class_slot_used: Set[Tuple[str, str]],
    teacher_slot_used: Set[Tuple[str, str]],
    room_slot_used: Set[Tuple[str, str]],
    conflict_group_slot_used: Set[Tuple[str, str]],
    task: scheduler.CourseBlock,
    candidate: scheduler.Candidate,
) -> bool:
    group_ids = schedule_input.class_conflict_groups.get(task.class_id, set())
    if any(
        rule.max_hours_per_class_per_day or rule.max_blocks_per_class_per_day
        for rule in task.schedule_rules
    ):
        class_day_hour_loads, class_day_block_loads = class_day_rule_loads_from_used_slots(
            schedule_input,
            class_slot_used,
        )
        if not scheduler.candidate_avoids_product_day_limits(
            class_day_hour_loads,
            class_day_block_loads,
            task,
            candidate,
        ):
            return False
    for slot in candidate.slots:
        if (task.class_id, slot.id) in class_slot_used:
            return False
        if candidate.teacher_id and (candidate.teacher_id, slot.id) in teacher_slot_used:
            return False
        if (candidate.room_id, slot.id) in room_slot_used:
            return False
        if any((group_id, slot.id) in conflict_group_slot_used for group_id in group_ids):
            return False
    return True


def place_candidate(
    schedule_input: scheduler.ScheduleInput,
    class_slot_used: Set[Tuple[str, str]],
    teacher_slot_used: Set[Tuple[str, str]],
    room_slot_used: Set[Tuple[str, str]],
    conflict_group_slot_used: Set[Tuple[str, str]],
    task: scheduler.CourseBlock,
    candidate: scheduler.Candidate,
) -> scheduler.Assignment:
    assignment = scheduler.Assignment(task=task, candidate=candidate)
    add_assignment_to_constraint_sets(
        schedule_input,
        assignment,
        (class_slot_used, teacher_slot_used, room_slot_used, conflict_group_slot_used),
    )
    return assignment


def class_teacher_day_loads(
    schedule_input: scheduler.ScheduleInput,
    assignments: Sequence[scheduler.Assignment],
    excluded_index: Optional[int] = None,
) -> Dict[Tuple[str, str, str], float]:
    loads: Dict[Tuple[str, str, str], float] = {}
    for locked_assignment in schedule_input.locked_assignments:
        scheduler.add_class_teacher_day_load(loads, locked_assignment.task, locked_assignment.candidate)
    for index, assignment in enumerate(assignments):
        if excluded_index is not None and index == excluded_index:
            continue
        scheduler.add_class_teacher_day_load(loads, assignment.task, assignment.candidate)
    return loads


def assignments_conflicting_with_candidate(
    candidate_assignment: scheduler.Assignment,
    assignments: Sequence[scheduler.Assignment],
    class_conflict_groups: Dict[str, Set[str]],
) -> List[scheduler.Assignment]:
    result: List[scheduler.Assignment] = []
    candidate_slots = {slot.id for slot in candidate_assignment.candidate.slots}
    candidate_teacher = scheduler.candidate_teacher_key(candidate_assignment.candidate)
    candidate_groups = class_conflict_groups.get(candidate_assignment.task.class_id, set())
    for assignment in assignments:
        if assignment.task.task_id == candidate_assignment.task.task_id:
            continue
        slot_overlap = candidate_slots.intersection(slot.id for slot in assignment.candidate.slots)
        if not slot_overlap and not assignments_overlap(candidate_assignment, assignment):
            continue
        if assignment.task.class_id == candidate_assignment.task.class_id:
            result.append(assignment)
            continue
        assignment_teacher = scheduler.candidate_teacher_key(assignment.candidate)
        if candidate_teacher and assignment_teacher and candidate_teacher == assignment_teacher:
            result.append(assignment)
            continue
        if assignment.candidate.room_id == candidate_assignment.candidate.room_id:
            result.append(assignment)
            continue
        if candidate_groups & class_conflict_groups.get(assignment.task.class_id, set()):
            result.append(assignment)
            continue
    return result


def candidate_conflicts_for_repair(
    candidate_assignment: scheduler.Assignment,
    other_by_date_period: Dict[Tuple[str, str], List[scheduler.Assignment]],
    class_conflict_groups: Dict[str, Set[str]],
) -> List[scheduler.Assignment]:
    relevant: List[scheduler.Assignment] = []
    seen_task_ids: Set[str] = set()
    for key in candidate_date_period_keys(candidate_assignment.candidate):
        for assignment in other_by_date_period.get(key, []):
            if assignment.task.task_id in seen_task_ids:
                continue
            seen_task_ids.add(assignment.task.task_id)
            relevant.append(assignment)
    return assignments_conflicting_with_candidate(
        candidate_assignment,
        relevant,
        class_conflict_groups,
    )
