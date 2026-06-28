from __future__ import annotations

from dataclasses import replace
from datetime import date as Date
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import scheduler
from scripts.csv_utils import read_csv_rows
from scripts.field_utils import normalize_date_text
from scripts.schedule_data import infer_class_subject, infer_class_subject_category


SUBJECT_ORDER = {"数学": 0, "英语": 1, "政治": 2, "语文": 3}


def split_values(value: str) -> List[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def normalize_date(value: str) -> str:
    text = normalize_date_text(value)
    if not text:
        return ""
    return Date.fromisoformat(text).isoformat()


def date_in_range(value: str, start: Optional[str], end: Optional[str]) -> bool:
    if start and value < start:
        return False
    if end and value > end:
        return False
    return True


def slot_in_range(
    slot: scheduler.TimeSlot,
    start: Optional[str],
    end: Optional[str],
    start_period: Optional[str],
    end_period: Optional[str],
) -> bool:
    slot_key = (slot.date, scheduler.period_sort_value(slot.period))
    if start:
        start_key = (start, scheduler.period_sort_value(start_period or "AM"))
        if slot_key < start_key:
            return False
    if end:
        end_key = (end, scheduler.period_sort_value(end_period or "EVENING"))
        if slot_key > end_key:
            return False
    return True


def filter_time_slots(
    slots: Sequence[scheduler.TimeSlot],
    start: Optional[str],
    end: Optional[str],
    start_period: Optional[str],
    end_period: Optional[str],
    periods: Optional[Set[str]],
) -> List[scheduler.TimeSlot]:
    return [
        slot
        for slot in slots
        if slot_in_range(slot, start, end, start_period, end_period)
        and (not periods or slot.period in periods)
    ]


def filter_classes(
    schedule_input: scheduler.ScheduleInput,
    class_ids: Sequence[str],
    stages: Optional[Set[str]],
    subjects: Optional[Set[str]],
    quarters: Optional[Set[str]] = None,
) -> Dict[str, scheduler.SchoolClass]:
    def requirement_matches_stage_filter(requirement: scheduler.Requirement) -> bool:
        if not stages:
            return True
        return (requirement.stage or "") in stages or (requirement.quarter or "") in stages

    classes: Dict[str, scheduler.SchoolClass] = {}
    for class_id in class_ids:
        if class_id not in schedule_input.classes:
            raise ValueError(f"班级不存在: {class_id}")
        cls = schedule_input.classes[class_id]
        class_has_quarters = any(requirement.quarter for requirement in cls.requirements)
        requirements = [
            requirement
            for requirement in cls.requirements
            if (not quarters or not class_has_quarters or (requirement.quarter or "") in quarters)
            and requirement_matches_stage_filter(requirement)
            and (not subjects or requirement.subject in subjects)
        ]
        if not requirements:
            raise ValueError(f"班级 {class_id} 在当前筛选条件下没有课程需求")
        classes[class_id] = replace(cls, requirements=requirements)
    return classes


def selected_conflict_groups(
    schedule_input: scheduler.ScheduleInput,
    class_ids: Set[str],
) -> Tuple[Dict[str, Set[str]], Dict[str, Set[str]]]:
    locked_class_ids = {assignment.task.class_id for assignment in schedule_input.locked_assignments}
    active_class_ids = set(class_ids) | locked_class_ids
    groups: Dict[str, Set[str]] = {}
    by_class: Dict[str, Set[str]] = {class_id: set() for class_id in active_class_ids}
    for group_id, raw_class_ids in schedule_input.conflict_groups.items():
        selected = set(raw_class_ids) & active_class_ids
        if len(selected) < 2 or not (selected & class_ids):
            continue
        groups[group_id] = selected
        for class_id in selected:
            by_class.setdefault(class_id, set()).add(group_id)
    return groups, by_class


def filtered_schedule_input(
    source: scheduler.ScheduleInput,
    class_ids: Sequence[str],
    stages: Optional[Set[str]],
    subjects: Optional[Set[str]],
    start: Optional[str],
    end: Optional[str],
    start_period: Optional[str],
    end_period: Optional[str],
    periods: Optional[Set[str]],
    room_ids: Optional[Set[str]],
    quarters: Optional[Set[str]] = None,
    class_window_constraints: Optional[Dict[str, Any]] = None,
) -> scheduler.ScheduleInput:
    classes = filter_classes(source, class_ids, stages, subjects, quarters)
    if room_ids:
        classes = {
            class_id: replace(
                cls,
                room_ids=set(room_ids),
                requirements=[replace(requirement, room_ids=set(room_ids)) for requirement in cls.requirements],
            )
            for class_id, cls in classes.items()
        }
    if class_window_constraints:
        constrained_classes: Dict[str, scheduler.SchoolClass] = {}
        for class_id, cls in classes.items():
            constraint = class_window_constraints.get(class_id)
            if not constraint:
                constrained_classes[class_id] = cls
                continue
            raw_room_ids = getattr(constraint, "room_ids", frozenset())
            requirement_room_ids = set(raw_room_ids) if raw_room_ids else None
            constrained_classes[class_id] = replace(
                cls,
                room_ids=requirement_room_ids or cls.room_ids,
                start_date=getattr(constraint, "earliest_date", "") or cls.start_date,
                start_period=getattr(constraint, "earliest_period", "") or cls.start_period,
                end_date=getattr(constraint, "latest_date", "") or cls.end_date,
                end_period=getattr(constraint, "latest_period", "") or cls.end_period,
                requirements=[
                    replace(requirement, room_ids=requirement_room_ids or requirement.room_ids)
                    for requirement in cls.requirements
                ],
            )
        classes = constrained_classes
    conflict_groups, class_conflict_groups = selected_conflict_groups(source, set(classes))
    return scheduler.ScheduleInput(
        time_slots=filter_time_slots(source.time_slots, start, end, start_period, end_period, periods),
        rooms=source.rooms,
        classes=classes,
        conflict_groups=conflict_groups,
        class_conflict_groups=class_conflict_groups,
        locked_assignments=source.locked_assignments,
        area_travel_minutes=source.area_travel_minutes,
    )


def class_ids_for_suite_codes(
    path: Path,
    suite_codes: Sequence[str],
    subjects: Optional[Set[str]],
) -> List[str]:
    classes_path = path / "classes.csv"
    if not classes_path.exists():
        raise ValueError(f"未找到班级数据: {classes_path}")
    rows_by_suite: Dict[str, List[Dict[str, str]]] = {suite_code: [] for suite_code in suite_codes}
    for row in read_csv_rows(classes_path):
        if (row.get("is_schedule_locked") or "").strip() in {"是", "1", "true", "True", "yes", "Y", "y"}:
            continue
        suite_code = (row.get("suite_code") or "").strip()
        if suite_code not in rows_by_suite:
            continue
        subject = infer_class_subject(row)
        if subjects and subject not in subjects:
            continue
        if not subjects and infer_class_subject_category(row, subject) != "公共课":
            continue
        rows_by_suite[suite_code].append(row)

    class_ids: List[str] = []
    for suite_code in suite_codes:
        rows = rows_by_suite.get(suite_code, [])
        rows.sort(key=lambda row: (SUBJECT_ORDER.get(infer_class_subject(row), 99), row.get("id") or ""))
        class_ids.extend(row["id"] for row in rows if row.get("id"))
    if not class_ids:
        raise ValueError(f"套班 {', '.join(suite_codes)} 没有匹配到公共课班级")
    return class_ids
