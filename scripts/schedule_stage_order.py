#!/usr/bin/env python3
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import scheduler


StageOrderViolation = Tuple[str, str, str, scheduler.Assignment, scheduler.Assignment]


def stage_order_tasks_by_class(
    schedule_input: scheduler.ScheduleInput,
) -> Dict[str, List[scheduler.CourseBlock]]:
    result: Dict[str, List[scheduler.CourseBlock]] = {class_id: [] for class_id in schedule_input.classes}
    for task in scheduler.build_course_blocks(schedule_input.classes):
        result.setdefault(task.class_id, []).append(task)
    return result


def effective_task_stage_sort_rank(
    schedule_input: scheduler.ScheduleInput,
    stage_tasks_by_class: Dict[str, List[scheduler.CourseBlock]],
    task: scheduler.CourseBlock,
) -> int:
    rank = scheduler.task_stage_rank_for_input(schedule_input, task)
    if rank is None:
        return 0
    ranks = {
        sibling_rank
        for sibling in stage_tasks_by_class.get(task.class_id, [])
        for sibling_rank in [scheduler.task_stage_rank_for_input(schedule_input, sibling)]
        if sibling_rank is not None
    }
    return rank if len(ranks) > 1 else 0


def stage_order_candidate_allowed(
    schedule_input: scheduler.ScheduleInput,
    stage_tasks_by_class: Dict[str, List[scheduler.CourseBlock]],
    assignments: Sequence[scheduler.Assignment],
    task: scheduler.CourseBlock,
    candidate: scheduler.Candidate,
    excluded_index: Optional[int] = None,
) -> bool:
    rank = scheduler.task_stage_rank_for_input(schedule_input, task)
    if rank is None:
        return True

    assigned_by_task = {
        assignment.task.task_id: assignment
        for index, assignment in enumerate(assignments)
        if excluded_index is None or index != excluded_index
    }
    for locked_assignment in schedule_input.locked_assignments:
        assigned_by_task.setdefault(locked_assignment.task.task_id, locked_assignment)

    candidate_start = scheduler.slot_sort_key(candidate.slots[0])
    candidate_end = scheduler.slot_sort_key(candidate.slots[-1])
    for sibling in stage_tasks_by_class.get(task.class_id, []):
        if sibling.task_id == task.task_id:
            continue
        sibling_rank = scheduler.task_stage_rank_for_input(schedule_input, sibling)
        if sibling_rank is None or sibling_rank == rank:
            continue
        sibling_assignment = assigned_by_task.get(sibling.task_id)
        if sibling_rank < rank:
            if sibling_assignment is None:
                return False
            if candidate_start <= scheduler.slot_sort_key(sibling_assignment.candidate.slots[-1]):
                return False
        elif sibling_assignment is not None:
            if candidate_end >= scheduler.slot_sort_key(sibling_assignment.candidate.slots[0]):
                return False
    return True


def stage_order_violations(
    schedule_input: scheduler.ScheduleInput,
    assignments: Sequence[scheduler.Assignment],
) -> List[StageOrderViolation]:
    grouped: Dict[Tuple[str, int], List[scheduler.Assignment]] = {}
    stage_names: Dict[Tuple[str, int], str] = {}
    for assignment in assignments:
        rank = scheduler.task_stage_rank_for_input(schedule_input, assignment.task)
        if rank is None:
            continue
        key = (assignment.task.class_id, rank)
        grouped.setdefault(key, []).append(assignment)
        stage_names[key] = assignment.task.stage or ""

    violations: List[StageOrderViolation] = []
    class_ids = sorted({class_id for class_id, _rank in grouped})
    for class_id in class_ids:
        ranks = sorted(rank for grouped_class_id, rank in grouped if grouped_class_id == class_id)
        for lower_rank, higher_rank in zip(ranks, ranks[1:]):
            lower_group = grouped[(class_id, lower_rank)]
            higher_group = grouped[(class_id, higher_rank)]
            latest_lower = max(lower_group, key=lambda item: scheduler.slot_sort_key(item.candidate.slots[-1]))
            earliest_higher = min(higher_group, key=lambda item: scheduler.slot_sort_key(item.candidate.slots[0]))
            if scheduler.slot_sort_key(latest_lower.candidate.slots[-1]) >= scheduler.slot_sort_key(earliest_higher.candidate.slots[0]):
                violations.append(
                    (
                        class_id,
                        stage_names.get((class_id, lower_rank), ""),
                        stage_names.get((class_id, higher_rank), ""),
                        latest_lower,
                        earliest_higher,
                    )
                )
    return violations


def assignments_preserve_stage_order(
    schedule_input: scheduler.ScheduleInput,
    assignments: Sequence[scheduler.Assignment],
) -> bool:
    return not stage_order_violations(schedule_input, assignments)
