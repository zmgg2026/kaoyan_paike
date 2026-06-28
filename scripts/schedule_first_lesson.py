#!/usr/bin/env python3
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Set, Tuple

import scheduler


FirstLessonRuleKey = Tuple[str, str, str]
FirstLessonAnchorPosition = Tuple[str, int, int, str]
FirstLessonModuleViolation = Tuple[FirstLessonRuleKey, str, scheduler.Assignment, scheduler.Assignment]

STAGE_FIRST_LESSON_MODULES = {
    ("英语", "基础"): "词汇",
    ("政治", "基础"): "马原",
}


def first_lesson_rule_key(task: scheduler.CourseBlock) -> Optional[FirstLessonRuleKey]:
    if (task.subject, task.stage or "") not in STAGE_FIRST_LESSON_MODULES:
        return None
    return task.class_id, task.subject, task.stage or ""


def is_first_lesson_module_task(task: scheduler.CourseBlock) -> bool:
    required_module = STAGE_FIRST_LESSON_MODULES.get((task.subject, task.stage or ""))
    if not required_module:
        return False
    return required_module in (task.course_module or "")


def stage_first_lesson_anchor_keys(tasks: Sequence[scheduler.CourseBlock]) -> Set[FirstLessonRuleKey]:
    return {
        key
        for task in tasks
        for key in [first_lesson_rule_key(task)]
        if key and is_first_lesson_module_task(task)
    }


def stage_first_lesson_anchor_task_ids(tasks: Sequence[scheduler.CourseBlock]) -> Set[str]:
    seen: Set[FirstLessonRuleKey] = set()
    task_ids: Set[str] = set()
    for task in tasks:
        key = first_lesson_rule_key(task)
        if not key or key in seen or not is_first_lesson_module_task(task):
            continue
        seen.add(key)
        task_ids.add(task.task_id)
    return task_ids


def first_lesson_candidate_allowed(
    task: scheduler.CourseBlock,
    candidate: scheduler.Candidate,
    anchor_keys: Set[FirstLessonRuleKey],
    anchor_positions: Dict[FirstLessonRuleKey, FirstLessonAnchorPosition],
) -> bool:
    key = first_lesson_rule_key(task)
    if not key or key not in anchor_keys:
        return True
    candidate_position = scheduler.slot_sort_key(candidate.slots[0])
    if is_first_lesson_module_task(task):
        return True
    anchor_position = anchor_positions.get(key)
    return anchor_position is not None and candidate_position > anchor_position


def mark_first_lesson_anchor_done(
    task: scheduler.CourseBlock,
    candidate: scheduler.Candidate,
    anchor_keys: Set[FirstLessonRuleKey],
    anchor_positions: Dict[FirstLessonRuleKey, FirstLessonAnchorPosition],
) -> None:
    key = first_lesson_rule_key(task)
    if key and key in anchor_keys and is_first_lesson_module_task(task):
        candidate_position = scheduler.slot_sort_key(candidate.slots[0])
        existing_position = anchor_positions.get(key)
        if existing_position is None or candidate_position < existing_position:
            anchor_positions[key] = candidate_position


def first_lesson_module_violations(
    assignments: Sequence[scheduler.Assignment],
) -> List[FirstLessonModuleViolation]:
    grouped: Dict[FirstLessonRuleKey, List[scheduler.Assignment]] = {}
    for assignment in assignments:
        key = first_lesson_rule_key(assignment.task)
        if key:
            grouped.setdefault(key, []).append(assignment)

    violations: List[FirstLessonModuleViolation] = []
    for key, group in grouped.items():
        required_module = STAGE_FIRST_LESSON_MODULES.get((key[1], key[2]), "")
        if not any(is_first_lesson_module_task(assignment.task) for assignment in group):
            continue
        ordered = sorted(group, key=lambda assignment: scheduler.slot_sort_key(assignment.candidate.slots[0]))
        first_assignment = ordered[0]
        if is_first_lesson_module_task(first_assignment.task):
            continue
        anchor_assignment = next(
            assignment for assignment in ordered if is_first_lesson_module_task(assignment.task)
        )
        violations.append((key, required_module, first_assignment, anchor_assignment))
    return violations


def assignments_preserve_first_lesson_modules(assignments: Sequence[scheduler.Assignment]) -> bool:
    return not first_lesson_module_violations(assignments)


def replacement_preserves_first_lesson_module(
    assignments: Sequence[scheduler.Assignment],
    assignment_index: int,
    task: scheduler.CourseBlock,
    candidate: scheduler.Candidate,
) -> bool:
    key = first_lesson_rule_key(task)
    if not key:
        return True

    group: List[Tuple[scheduler.CourseBlock, scheduler.Candidate]] = []
    for index, assignment in enumerate(assignments):
        if index == assignment_index:
            group.append((task, candidate))
        elif first_lesson_rule_key(assignment.task) == key:
            group.append((assignment.task, assignment.candidate))

    if not any(is_first_lesson_module_task(group_task) for group_task, _ in group):
        return True
    group.sort(key=lambda item: scheduler.slot_sort_key(item[1].slots[0]))
    return is_first_lesson_module_task(group[0][0])
