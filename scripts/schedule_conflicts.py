#!/usr/bin/env python3
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import scheduler
from scripts.csv_utils import write_csv_rows
from scripts.field_utils import normalize_blank_marker as clean, parse_time_minutes


def minutes(value: str) -> Optional[int]:
    return parse_time_minutes(value)


def assignment_time_interval(assignment: scheduler.Assignment) -> Tuple[str, str, int, int]:
    first = assignment.candidate.slots[0]
    last = assignment.candidate.slots[-1]
    start = minutes(first.start_time or "") or 0
    end = minutes(last.end_time or "") or (24 * 60)
    return first.date, first.period, start, end


def assignments_overlap(left: scheduler.Assignment, right: scheduler.Assignment) -> bool:
    left_date, left_period, left_start, left_end = assignment_time_interval(left)
    right_date, right_period, right_start, right_end = assignment_time_interval(right)
    return (
        left_date == right_date
        and left_period == right_period
        and left_start < right_end
        and right_start < left_end
    )


def assignment_is_shared_merge_clone(assignment: scheduler.Assignment) -> bool:
    return (
        "合班到" in (assignment.task.class_name or "")
        or (assignment.task.product_name or "").startswith("合班到")
        or (assignment.task.product_name or "") == "共享课表"
    )


def assignments_have_same_teaching_payload(left: scheduler.Assignment, right: scheduler.Assignment) -> bool:
    fields = (
        "subject_category",
        "subject",
        "stage",
        "course_module",
        "course_group",
        "course_code",
    )
    return all(clean(getattr(left.task, field, "")) == clean(getattr(right.task, field, "")) for field in fields)


def assignments_are_same_shared_merge_event(left: scheduler.Assignment, right: scheduler.Assignment) -> bool:
    room_id = left.candidate.room_id or ""
    if not room_id or room_id != (right.candidate.room_id or ""):
        return False
    if assignment_is_shared_merge_clone(left) or assignment_is_shared_merge_clone(right):
        return True
    if scheduler.candidate_teacher_key(left.candidate) != scheduler.candidate_teacher_key(right.candidate):
        return False
    return assignment_time_interval(left) == assignment_time_interval(right) and assignments_have_same_teaching_payload(left, right)


def teacher_time_conflict_groups(assignments: Sequence[scheduler.Assignment]) -> List[List[scheduler.Assignment]]:
    grouped: Dict[Tuple[str, str, str], List[scheduler.Assignment]] = defaultdict(list)
    for assignment in assignments:
        teacher_key = scheduler.candidate_teacher_key(assignment.candidate)
        if not teacher_key:
            continue
        first = assignment.candidate.slots[0]
        grouped[(teacher_key, first.date, first.period)].append(assignment)

    conflict_groups: List[List[scheduler.Assignment]] = []
    for (_teacher_key, _date_text, _period), group in sorted(grouped.items()):
        if len(group) <= 1:
            continue
        conflict_items: Dict[str, scheduler.Assignment] = {}
        for left_index, left in enumerate(group):
            for right in group[left_index + 1 :]:
                if left.task.class_id == right.task.class_id:
                    continue
                if assignments_are_same_shared_merge_event(left, right):
                    continue
                if not assignments_overlap(left, right):
                    continue
                conflict_items[left.task.task_id] = left
                conflict_items[right.task.task_id] = right
        if not conflict_items:
            continue
        conflict_groups.append(
            sorted(
                conflict_items.values(),
                key=lambda assignment: (
                    assignment.candidate.slots[0].start_time or "",
                    assignment.task.class_id,
                ),
            )
        )
    return conflict_groups


def teacher_time_conflict_lines(assignments: Sequence[scheduler.Assignment]) -> List[str]:
    lines: List[str] = []
    for items in teacher_time_conflict_groups(assignments):
        teacher = items[0].candidate.teacher_name or items[0].candidate.teacher_id
        start_time = min(item.candidate.slots[0].start_time or "" for item in items)
        end_time = max(item.candidate.slots[-1].end_time or "" for item in items)
        first = items[0].candidate.slots[0]
        details = "；".join(
            f"{item.task.class_id} {item.task.subject}/{item.task.course_module or ''} {item.candidate.room_id}"
            for item in items
        )
        lines.append(f"{first.date} {first.period} {start_time}-{end_time} {teacher}: {details}")
    return lines[:300]


def write_teacher_time_conflicts_csv(
    assignments: Sequence[scheduler.Assignment],
    path: Path,
    room_names: Optional[Dict[str, str]] = None,
) -> None:
    room_names = room_names or {}
    fieldnames = [
        "teacher_id",
        "teacher_name",
        "date",
        "period",
        "start_time",
        "end_time",
        "class_ids",
        "class_names",
        "subjects",
        "rooms",
        "count",
    ]
    rows = []
    for items in teacher_time_conflict_groups(assignments):
        first = items[0].candidate.slots[0]
        start_time = min(item.candidate.slots[0].start_time or "" for item in items)
        end_time = max(item.candidate.slots[-1].end_time or "" for item in items)
        rows.append(
            {
                "teacher_id": items[0].candidate.teacher_id,
                "teacher_name": items[0].candidate.teacher_name,
                "date": first.date,
                "period": first.period,
                "start_time": start_time,
                "end_time": end_time,
                "class_ids": "|".join(item.task.class_id for item in items),
                "class_names": "|".join(item.task.class_name for item in items),
                "subjects": "|".join(sorted({item.task.subject for item in items if item.task.subject})),
                "rooms": "|".join(
                    room_names.get(item.candidate.room_id, item.candidate.room_id)
                    for item in items
                ),
                "count": len(items),
            }
        )
    write_csv_rows(path, fieldnames, rows, extrasaction="raise")
