#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import date as Date
from dataclasses import dataclass, field
from pathlib import Path
from string import Template
from typing import Dict, List, Mapping, Optional, Set, Tuple

from scripts.csv_utils import write_csv_rows
from scripts.field_utils import parse_bool, parse_bool_default
from scripts.schedule_modes import assignment_is_shared


VALID_PERIODS = {"AM", "PM", "EVENING"}
PERIOD_ORDER = {"AM": 0, "PM": 1, "EVENING": 2}
SCHEDULE_CSV_FIELDNAMES = [
    "date",
    "period",
    "start_slot_id",
    "start_slot_name",
    "start_time",
    "end_slot_id",
    "end_slot_name",
    "end_time",
    "slot_ids",
    "class_id",
    "class_name",
    "product_id",
    "product_name",
    "subject_category",
    "subject",
    "quarter",
    "stage",
    "course_module",
    "course_group",
    "teacher_id",
    "teacher_name",
    "room_id",
    "room_name",
    "teaching_area_id",
    "duration_hours",
    "source",
]
SEASON_WINDOW_ID_TO_NAME = {
    "WINDOW_WINTER": "寒假",
    "WINDOW_SPRING": "春季",
    "WINDOW_SUMMER": "暑假",
    "WINDOW_AUTUMN": "秋季",
}
SEASON_WINDOW_NAME_TO_ID = {name: window_id for window_id, name in SEASON_WINDOW_ID_TO_NAME.items()}
WEEKDAY_ALIASES = {
    "0": 0,
    "1": 0,
    "MON": 0,
    "MONDAY": 0,
    "周一": 0,
    "星期一": 0,
    "一": 0,
    "2": 1,
    "TUE": 1,
    "TUESDAY": 1,
    "周二": 1,
    "星期二": 1,
    "二": 1,
    "3": 2,
    "WED": 2,
    "WEDNESDAY": 2,
    "周三": 2,
    "星期三": 2,
    "三": 2,
    "4": 3,
    "THU": 3,
    "THURSDAY": 3,
    "周四": 3,
    "星期四": 3,
    "四": 3,
    "5": 4,
    "FRI": 4,
    "FRIDAY": 4,
    "周五": 4,
    "星期五": 4,
    "五": 4,
    "6": 5,
    "SAT": 5,
    "SATURDAY": 5,
    "周六": 5,
    "星期六": 5,
    "六": 5,
    "7": 6,
    "SUN": 6,
    "SUNDAY": 6,
    "周日": 6,
    "周天": 6,
    "星期日": 6,
    "星期天": 6,
    "日": 6,
    "天": 6,
}
STAGE_ORDER_PROFILES = [
    ({"寒暑营", "无忧寒"}, ["寒假", "春季", "暑假", "秋季"]),
    ({"全年营"}, ["一轮", "二轮", "三轮", "四轮"]),
    ({"半年营", "暑假营", "无忧秋", "无忧春", "无忧暑"}, ["基础", "强化", "冲刺"]),
    ({"冲刺营"}, ["冲刺"]),
]
SAME_CLASS_TEACHER_DAY_LIMIT_SUBJECTS = {"英语", "政治", "数学"}
MAX_SAME_CLASS_TEACHER_DAY_HOURS = 8


@dataclass(frozen=True)
class TimeSlot:
    id: str
    date: str
    period: str
    name: str
    order: int
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_hours: int = 2
    schedule_window_id: Optional[str] = None
    season_window_id: Optional[str] = None
    season_name: Optional[str] = None


@dataclass(frozen=True)
class Room:
    id: str
    name: str = ""
    capacity: Optional[int] = None
    capacity_unlimited: bool = False
    teaching_area_id: str = ""
    teaching_area_name: str = ""
    region_tag: str = ""


@dataclass(frozen=True)
class ProductRequirement:
    subject_category: str
    subject: str
    quarter: Optional[str]
    stage: Optional[str]
    course_module: Optional[str]
    course_group: Optional[str]
    total_hours: int
    block_hours: int
    course_code: Optional[str] = None
    course_name: Optional[str] = None
    room_ids: Optional[Set[str]] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    allowed_periods: Optional[Set[str]] = None
    allowed_weekdays: Optional[Set[int]] = None
    excluded_weekdays: Optional[Set[int]] = None
    schedule_rules: Tuple[ScheduleRule, ...] = ()


@dataclass(frozen=True)
class ScheduleRule:
    subject: Optional[str]
    stage: Optional[str]
    course_module: Optional[str]
    course_group: Optional[str]
    start_date: Optional[str]
    end_date: Optional[str]
    allowed_periods: Optional[Set[str]]
    allowed_weekdays: Optional[Set[int]]
    excluded_weekdays: Optional[Set[int]]
    block_hours: Optional[int]
    schedule_window_ids: Optional[Set[str]] = None
    season_window_ids: Optional[Set[str]] = None
    window_names: Optional[Set[str]] = None
    max_hours_per_class_per_day: Optional[float] = None
    max_blocks_per_class_per_day: Optional[int] = None


@dataclass(frozen=True)
class Product:
    id: str
    name: str
    requirements: List[ProductRequirement]


@dataclass(frozen=True)
class TeacherAssignment:
    product_id: Optional[str]
    subject: str
    stage: Optional[str]
    course_module: Optional[str]
    course_group: Optional[str]
    teacher_id: str
    teacher_name: str


@dataclass(frozen=True)
class TeacherUnavailableRule:
    teacher_id: str
    start_date: Optional[str]
    end_date: Optional[str]
    weekdays: Optional[Set[int]]
    periods: Optional[Set[str]]
    schedule_window_ids: Optional[Set[str]]
    unavailable_id: str = ""
    reason: str = ""


@dataclass(frozen=True)
class ClassWindowConstraint:
    class_id: str
    start_date: Optional[str]
    start_period: Optional[str]
    end_date: Optional[str]
    end_period: Optional[str]
    schedule_window_id: Optional[str]
    season_window_id: Optional[str]
    season_name: Optional[str]
    room_ids: Optional[Set[str]]
    has_room_constraint: bool = False
    class_window_id: str = ""


@dataclass(frozen=True)
class ClassSchedulingBounds:
    start_date: Optional[str]
    start_period: Optional[str]
    end_date: Optional[str]
    end_period: Optional[str]
    first_lesson_date: Optional[str]
    first_lesson_period: Optional[str]


@dataclass(frozen=True)
class Requirement:
    subject_category: str
    subject: str
    quarter: Optional[str]
    stage: Optional[str]
    course_module: Optional[str]
    course_group: Optional[str]
    teacher_id: str
    teacher_name: str
    total_hours: int
    block_hours: int
    course_code: Optional[str] = None
    course_name: Optional[str] = None
    room_ids: Optional[Set[str]] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    allowed_periods: Optional[Set[str]] = None
    allowed_weekdays: Optional[Set[int]] = None
    excluded_weekdays: Optional[Set[int]] = None
    schedule_rules: Tuple[ScheduleRule, ...] = ()


@dataclass(frozen=True)
class SchoolClass:
    id: str
    name: str
    product_id: Optional[str]
    product_name: Optional[str]
    size: Optional[int]
    room_ids: Optional[Set[str]]
    start_date: Optional[str]
    start_period: Optional[str]
    end_date: Optional[str]
    end_period: Optional[str]
    first_lesson_date: Optional[str]
    first_lesson_period: Optional[str]
    stage_order: Dict[str, int]
    requirements: List[Requirement]


@dataclass(frozen=True)
class CourseBlock:
    task_id: str
    class_id: str
    class_name: str
    product_id: Optional[str]
    product_name: Optional[str]
    class_size: Optional[int]
    subject_category: str
    subject: str
    quarter: Optional[str]
    stage: Optional[str]
    course_module: Optional[str]
    course_group: Optional[str]
    teacher_id: str
    teacher_name: str
    block_hours: int
    room_ids: Optional[Set[str]]
    start_date: Optional[str]
    end_date: Optional[str]
    allowed_periods: Optional[Set[str]]
    allowed_weekdays: Optional[Set[int]]
    excluded_weekdays: Optional[Set[int]]
    schedule_rules: Tuple[ScheduleRule, ...]
    is_locked: bool = False
    course_code: Optional[str] = None
    course_name: Optional[str] = None


@dataclass(frozen=True)
class Candidate:
    slots: Tuple[TimeSlot, ...]
    teacher_id: str
    teacher_name: str
    room_id: str


@dataclass(frozen=True)
class Assignment:
    task: CourseBlock
    candidate: Candidate


@dataclass(frozen=True)
class ScheduleInput:
    time_slots: List[TimeSlot]
    rooms: Dict[str, Room]
    classes: Dict[str, SchoolClass]
    conflict_groups: Dict[str, Set[str]]
    class_conflict_groups: Dict[str, Set[str]]
    locked_assignments: List[Assignment]
    area_travel_minutes: Dict[Tuple[str, str], int] = field(default_factory=dict)
    teacher_unavailability: Dict[str, List[TeacherUnavailableRule]] = field(default_factory=dict)
    class_window_constraints: Dict[str, List[ClassWindowConstraint]] = field(default_factory=dict)


@dataclass(frozen=True)
class SchedulePlan:
    tasks: List[CourseBlock]
    task_by_id: Dict[str, CourseBlock]
    task_ids_by_class: Dict[str, List[str]]
    domains: Dict[str, List[Candidate]]


def candidate_teacher_key(candidate: Candidate) -> str:
    return candidate.teacher_id or candidate.teacher_name or ""


def candidate_hours_by_date(candidate: Candidate) -> Dict[str, float]:
    hours_by_date: Dict[str, float] = {}
    for slot in candidate.slots:
        hours_by_date[slot.date] = hours_by_date.get(slot.date, 0.0) + float(slot.duration_hours or 0)
    return hours_by_date


def add_class_teacher_day_load(
    loads: Dict[Tuple[str, str, str], float],
    task: CourseBlock,
    candidate: Candidate,
    delta: float = 1.0,
) -> None:
    if task.subject not in SAME_CLASS_TEACHER_DAY_LIMIT_SUBJECTS:
        return
    teacher_key = candidate_teacher_key(candidate)
    if not teacher_key:
        return
    for date_text, hours in candidate_hours_by_date(candidate).items():
        key = (task.class_id, teacher_key, date_text)
        next_value = loads.get(key, 0.0) + hours * delta
        if next_value <= 0:
            loads.pop(key, None)
        else:
            loads[key] = next_value


def locked_class_teacher_day_loads(schedule_input: ScheduleInput) -> Dict[Tuple[str, str, str], float]:
    loads: Dict[Tuple[str, str, str], float] = {}
    for assignment in schedule_input.locked_assignments:
        add_class_teacher_day_load(loads, assignment.task, assignment.candidate)
    return loads


def add_class_day_rule_load(
    hour_loads: Dict[Tuple[str, str], float],
    block_loads: Dict[Tuple[str, str], int],
    task: CourseBlock,
    candidate: Candidate,
    delta: int = 1,
) -> None:
    for date_text, hours in candidate_hours_by_date(candidate).items():
        key = (task.class_id, date_text)
        next_hours = hour_loads.get(key, 0.0) + hours * delta
        if next_hours <= 1e-9:
            hour_loads.pop(key, None)
        else:
            hour_loads[key] = next_hours

        next_blocks = block_loads.get(key, 0) + delta
        if next_blocks <= 0:
            block_loads.pop(key, None)
        else:
            block_loads[key] = next_blocks


def locked_class_day_rule_loads(
    schedule_input: ScheduleInput,
) -> Tuple[Dict[Tuple[str, str], float], Dict[Tuple[str, str], int]]:
    hour_loads: Dict[Tuple[str, str], float] = {}
    block_loads: Dict[Tuple[str, str], int] = {}
    for assignment in schedule_input.locked_assignments:
        add_class_day_rule_load(hour_loads, block_loads, assignment.task, assignment.candidate)
    return hour_loads, block_loads


def candidate_avoids_same_class_teacher_day_limit(
    loads: Dict[Tuple[str, str, str], float],
    task: CourseBlock,
    candidate: Candidate,
) -> bool:
    if task.subject not in SAME_CLASS_TEACHER_DAY_LIMIT_SUBJECTS:
        return True
    teacher_key = candidate_teacher_key(candidate)
    if not teacher_key:
        return True
    for date_text, hours in candidate_hours_by_date(candidate).items():
        if loads.get((task.class_id, teacher_key, date_text), 0.0) + hours >= MAX_SAME_CLASS_TEACHER_DAY_HOURS:
            return False
    return True


def region_tokens(region_tag: str) -> Set[str]:
    text = (region_tag or "").strip()
    if not text:
        return set()
    return {
        item.strip()
        for item in re.split(r"[/|,，;；、\s]+", text)
        if item.strip()
    }


def room_area_id(room: Optional[Room]) -> str:
    if not room:
        return ""
    return room.teaching_area_id or room.id


def same_region(left: Optional[Room], right: Optional[Room]) -> bool:
    left_tokens = region_tokens(left.region_tag if left else "")
    right_tokens = region_tokens(right.region_tag if right else "")
    return bool(left_tokens and right_tokens and left_tokens.intersection(right_tokens))


def is_new_station_area(room: Optional[Room]) -> bool:
    tokens = region_tokens(room.region_tag if room else "")
    return bool(tokens.intersection({"新站", "瑶海", "职教城"}))


def is_new_station_avoid_target(room: Optional[Room]) -> bool:
    tokens = region_tokens(room.region_tag if room else "")
    return bool(tokens.intersection({"滨湖", "经开", "翡翠湖"}))


def area_pair_key(left_area_id: str, right_area_id: str) -> Tuple[str, str]:
    left, right = sorted((left_area_id, right_area_id))
    return left, right


def slots_dates(slots: Tuple[TimeSlot, ...]) -> Set[str]:
    return {slot.date for slot in slots}


def slots_periods(slots: Tuple[TimeSlot, ...]) -> Set[str]:
    return {slot.period for slot in slots}


def assignment_affects_same_day_teacher_travel(
    assignment: Assignment,
    task: CourseBlock,
    teacher_key: str,
    candidate_dates: Set[str],
    candidate_periods: Set[str],
) -> bool:
    assignment_teacher = candidate_teacher_key(assignment.candidate)
    if not assignment_teacher or assignment_teacher != teacher_key:
        return False
    if assignment.task.task_id == task.task_id:
        return False
    if not candidate_dates.intersection(slots_dates(assignment.candidate.slots)):
        return False
    return candidate_periods != slots_periods(assignment.candidate.slots)


def is_new_station_avoid_pair(left_room: Optional[Room], right_room: Optional[Room]) -> bool:
    return (
        is_new_station_area(left_room)
        and is_new_station_avoid_target(right_room)
    ) or (
        is_new_station_area(right_room)
        and is_new_station_avoid_target(left_room)
    )


def room_pair_teacher_travel_penalty(
    schedule_input: ScheduleInput,
    candidate_room: Optional[Room],
    assigned_room: Optional[Room],
) -> int:
    candidate_area = room_area_id(candidate_room)
    assigned_area = room_area_id(assigned_room)
    if candidate_area and assigned_area and candidate_area == assigned_area:
        return 0
    if same_region(candidate_room, assigned_room):
        return 500

    pair_minutes = schedule_input.area_travel_minutes.get(area_pair_key(candidate_area, assigned_area), 0)
    if is_new_station_avoid_pair(candidate_room, assigned_room):
        return 50_000 + max(0, pair_minutes - 20) * 100
    return 5_000 + max(0, pair_minutes - 20) * 60


def candidate_same_day_teacher_travel_penalty(
    schedule_input: ScheduleInput,
    existing_assignments: List[Assignment],
    task: CourseBlock,
    candidate: Candidate,
) -> int:
    teacher_key = candidate_teacher_key(candidate)
    if not teacher_key:
        return 0
    candidate_room = schedule_input.rooms.get(candidate.room_id)
    candidate_dates = slots_dates(candidate.slots)
    candidate_periods = slots_periods(candidate.slots)
    penalty = 0

    for assignment in existing_assignments:
        if not assignment_affects_same_day_teacher_travel(
            assignment,
            task,
            teacher_key,
            candidate_dates,
            candidate_periods,
        ):
            continue
        assigned_room = schedule_input.rooms.get(assignment.candidate.room_id)
        penalty += room_pair_teacher_travel_penalty(schedule_input, candidate_room, assigned_room)
    return penalty


def load_input(path: Path) -> ScheduleInput:
    return load_input_data(json.loads(path.read_text(encoding="utf-8")))


def load_input_data(data: dict) -> ScheduleInput:
    time_slots = parse_time_slots(data["time_slots"])
    rooms, has_explicit_rooms = parse_rooms(data)

    product_schedule_rules = group_schedule_rules_by_product(data.get("product_schedule_rules", []))
    products = parse_products(data.get("products", []), product_schedule_rules)
    classes = parse_classes(data["classes"], products, allow_area_field_as_room_ids=not has_explicit_rooms)
    locked_assignments = parse_locked_lessons(data.get("locked_lessons", data.get("locked_scheduled_lessons", [])), time_slots, rooms)
    locked_class_ids = {assignment.task.class_id for assignment in locked_assignments}
    conflict_groups, class_conflict_groups = parse_conflict_groups(data.get("conflict_groups", []), classes, locked_class_ids)

    return ScheduleInput(
        time_slots=time_slots,
        rooms=rooms,
        classes=classes,
        conflict_groups=conflict_groups,
        class_conflict_groups=class_conflict_groups,
        locked_assignments=locked_assignments,
        area_travel_minutes=parse_area_travel_minutes(data.get("teaching_area_links", data.get("area_links", []))),
        teacher_unavailability=parse_teacher_unavailability(data.get("teacher_unavailability", [])),
        class_window_constraints=parse_class_window_constraints(data.get("class_window_boundaries", []), rooms),
    )


def area_metadata_by_id(raw_area_rows: List[dict]) -> Dict[object, dict]:
    return {
        row.get("id"): row
        for row in raw_area_rows
        if row.get("id")
    }


def parse_rooms(data: dict) -> Tuple[Dict[str, Room], bool]:
    raw_area_rows = data.get("teaching_areas", [])
    area_meta = area_metadata_by_id(raw_area_rows)
    raw_room_rows = data.get("rooms") or raw_area_rows
    has_explicit_rooms = bool(data.get("rooms"))
    rooms = {
        row["id"]: room_from_row(row, area_meta, has_explicit_rooms)
        for row in raw_room_rows
    }
    return rooms, has_explicit_rooms


def room_from_row(raw_room: dict, area_meta_by_id: Mapping[object, dict], has_explicit_rooms: bool) -> Room:
    area_key = raw_room.get("teaching_area_id") or raw_room.get("id")
    area_meta = area_meta_by_id.get(area_key, {})
    room_id = raw_room["id"]
    return Room(
        id=room_id,
        name=raw_room.get("name") or room_id,
        capacity=raw_room.get("capacity"),
        capacity_unlimited=parse_bool(raw_room.get("capacity_unlimited")),
        teaching_area_id=raw_room.get("teaching_area_id") or ("" if has_explicit_rooms else room_id),
        teaching_area_name=(
            raw_room.get("teaching_area_name")
            or area_meta.get("short_name")
            or area_meta.get("name")
            or ""
        ),
        region_tag=raw_room.get("region_tag") or area_meta.get("region_tag") or "",
    )


def time_slot_row(raw: object) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("time_slots 现在需要使用对象格式，包含 id/date/period/name/order")
    return raw


def time_slot_id(raw: dict, seen: Set[str]) -> str:
    slot_id = raw["id"]
    if slot_id in seen:
        raise ValueError(f"重复的课节 id: {slot_id}")
    seen.add(slot_id)
    return slot_id


def time_slot_duration(raw: dict, slot_id: str) -> int:
    duration_hours = int(raw.get("duration_hours", 2))
    if duration_hours <= 0:
        raise ValueError(f"课节 {slot_id} 的 duration_hours 必须大于 0")
    return duration_hours


def time_slot_from_row(raw: object, seen: Set[str]) -> TimeSlot:
    row = time_slot_row(raw)
    slot_id = time_slot_id(row, seen)
    return TimeSlot(
        id=slot_id,
        date=row["date"],
        period=row["period"],
        name=row.get("name", slot_id),
        order=int(row["order"]),
        start_time=row.get("start_time"),
        end_time=row.get("end_time"),
        duration_hours=time_slot_duration(row, slot_id),
        schedule_window_id=row.get("schedule_window_id") or row.get("window_id"),
        season_window_id=row.get("season_window_id"),
        season_name=row.get("season_name") or row.get("window_name"),
    )


def parse_time_slots(raw_slots: List[dict]) -> List[TimeSlot]:
    seen: Set[str] = set()
    slots = [time_slot_from_row(raw, seen) for raw in raw_slots]
    slots.sort(key=slot_sort_key)
    return slots


def class_window_room_constraint(raw: dict, rooms: Mapping[str, Room]) -> Tuple[Optional[Set[str]], bool]:
    room_ids = parse_id_set(raw, "room_ids", "preferred_room_ids")
    if room_ids:
        return room_ids, True

    teaching_area_ids = parse_id_set(raw, "preferred_teaching_area_ids", "teaching_area_ids")
    if teaching_area_ids:
        expanded = {
            room.id
            for room in rooms.values()
            if room.teaching_area_id in teaching_area_ids
        }
        return expanded or None, True

    explicit_empty_room_constraint = parse_bool(raw.get("has_room_constraint"))
    return None, explicit_empty_room_constraint


def parse_class_window_period(
    raw: dict,
    class_id: str,
    primary_field: str,
    legacy_field: str,
    default: str,
) -> str:
    period = str(raw.get(primary_field) or raw.get(legacy_field) or default).strip().upper()
    if period and period not in VALID_PERIODS:
        raise ValueError(f"班级窗口 {class_id} 的 {primary_field} 只能填写 AM、PM 或 EVENING")
    return period


def parse_class_window_constraint(
    raw: dict,
    rooms: Mapping[str, Room],
) -> Optional[ClassWindowConstraint]:
    if not parse_bool_default(raw.get("is_class_window_included"), True):
        return None
    class_id = str(raw.get("class_id") or "").strip()
    if not class_id:
        return None
    room_ids, has_room_constraint = class_window_room_constraint(raw, rooms)
    return ClassWindowConstraint(
        class_id=class_id,
        class_window_id=str(raw.get("class_window_id") or "").strip(),
        start_date=validate_date(
            raw.get("earliest_date") or raw.get("start_date"),
            f"班级窗口 {class_id}/earliest_date",
        ),
        start_period=parse_class_window_period(raw, class_id, "earliest_period", "start_period", "AM"),
        end_date=validate_date(
            raw.get("latest_date") or raw.get("end_date"),
            f"班级窗口 {class_id}/latest_date",
        ),
        end_period=parse_class_window_period(raw, class_id, "latest_period", "end_period", "EVENING"),
        schedule_window_id=str(raw.get("schedule_window_id") or "").strip() or None,
        season_window_id=str(raw.get("season_window_id") or "").strip() or None,
        season_name=str(raw.get("season_name") or raw.get("schedule_window_name") or "").strip() or None,
        room_ids=room_ids,
        has_room_constraint=has_room_constraint,
    )


def sort_class_window_constraints(by_class: Dict[str, List[ClassWindowConstraint]]) -> None:
    for constraints in by_class.values():
        constraints.sort(
            key=lambda constraint: (
                constraint.start_date or "9999-12-31",
                period_sort_value(constraint.start_period or "AM"),
                constraint.end_date or "9999-12-31",
                constraint.class_window_id,
            )
        )


def parse_class_window_constraints(raw_constraints: List[dict], rooms: Mapping[str, Room]) -> Dict[str, List[ClassWindowConstraint]]:
    by_class: Dict[str, List[ClassWindowConstraint]] = {}
    for raw in raw_constraints:
        constraint = parse_class_window_constraint(raw, rooms)
        if not constraint:
            continue
        by_class.setdefault(constraint.class_id, []).append(constraint)

    sort_class_window_constraints(by_class)
    return by_class


def parse_teacher_unavailability(raw_rules: List[dict]) -> Dict[str, List[TeacherUnavailableRule]]:
    rules_by_teacher: Dict[str, List[TeacherUnavailableRule]] = {}
    for index, raw_rule in enumerate(raw_rules, start=1):
        rule = parse_teacher_unavailability_rule(raw_rule, index)
        if not rule:
            continue
        rules_by_teacher.setdefault(rule.teacher_id, []).append(rule)
    return rules_by_teacher


def parse_teacher_unavailability_rule(raw_rule: object, index: int) -> Optional[TeacherUnavailableRule]:
    if not isinstance(raw_rule, dict):
        return None
    if not parse_bool_default(raw_rule.get("is_active"), True):
        return None
    teacher_id = teacher_unavailability_teacher_id(raw_rule)
    if not teacher_id:
        return None
    label = teacher_unavailability_label(raw_rule, index)
    start_date, end_date = teacher_unavailability_date_range(raw_rule, label)
    weekdays, periods, schedule_window_ids = teacher_unavailability_scope(raw_rule, label)
    if not any((start_date, end_date, weekdays, periods, schedule_window_ids)):
        return None
    return TeacherUnavailableRule(
        teacher_id=teacher_id,
        start_date=start_date,
        end_date=end_date,
        weekdays=weekdays,
        periods=periods,
        schedule_window_ids=schedule_window_ids,
        unavailable_id=str(raw_rule.get("unavailable_id") or "").strip(),
        reason=str(raw_rule.get("reason") or raw_rule.get("notes") or "").strip(),
    )


def teacher_unavailability_label(raw_rule: dict, index: int) -> str:
    return f"教师不可排规则 {raw_rule.get('unavailable_id') or index}"


def teacher_unavailability_teacher_id(raw_rule: dict) -> str:
    return str(raw_rule.get("teacher_id") or raw_rule.get("employee_id") or raw_rule.get("id") or "").strip()


def teacher_unavailability_date_range(raw_rule: dict, label: str) -> Tuple[Optional[str], Optional[str]]:
    start_date = validate_date(raw_rule.get("start_date"), f"{label}/start_date")
    end_date = validate_date(raw_rule.get("end_date"), f"{label}/end_date")
    if start_date and end_date and end_date < start_date:
        raise ValueError(f"{label} 的 end_date 不能早于 start_date")
    return start_date, end_date


def teacher_unavailability_scope(
    raw_rule: dict,
    label: str,
) -> Tuple[Optional[Set[int]], Optional[Set[str]], Optional[Set[str]]]:
    return (
        parse_weekday_set(raw_rule.get("weekdays"), f"{label}/weekdays"),
        parse_period_set(raw_rule.get("periods"), f"{label}/periods"),
        parse_string_set(raw_rule.get("schedule_window_ids") or raw_rule.get("schedule_window_id")),
    )


def parse_area_travel_minutes(raw_links: List[dict]) -> Dict[Tuple[str, str], int]:
    result: Dict[Tuple[str, str], int] = {}
    for raw in raw_links:
        from_id = str(raw.get("from_teaching_area_id") or raw.get("from_area_id") or "").strip()
        to_id = str(raw.get("to_teaching_area_id") or raw.get("to_area_id") or "").strip()
        if not from_id or not to_id or from_id == to_id:
            continue
        try:
            minutes = int(float(raw.get("travel_minutes") or raw.get("driving_duration_minutes") or 0))
        except (TypeError, ValueError):
            minutes = 0
        if minutes <= 0:
            continue
        result[area_pair_key(from_id, to_id)] = minutes
    return result


def parse_locked_lessons(raw_lessons: List[dict], time_slots: List[TimeSlot], rooms: Dict[str, Room]) -> List[Assignment]:
    assignments: List[Assignment] = []
    slot_dates, slot_by_id, day_slots_by_date = locked_lesson_slot_indexes(time_slots)
    for index, raw in enumerate(raw_lessons, start=1):
        lesson_id = raw.get("id") or f"LOCKED_{index}"
        class_id, room_id = locked_lesson_required_fields(raw, lesson_id, rooms)
        slots = locked_lesson_slots(raw, time_slots, slot_dates, slot_by_id, day_slots_by_date)
        if not slots:
            continue
        assignments.append(
            Assignment(
                task=locked_lesson_task(raw, str(lesson_id), str(class_id), str(room_id), slots),
                candidate=locked_lesson_candidate(raw, str(room_id), slots),
            )
        )
    return assignments


def locked_lesson_slot_indexes(
    time_slots: List[TimeSlot],
) -> Tuple[Set[str], Dict[str, TimeSlot], Dict[str, List[TimeSlot]]]:
    slot_dates = {slot.date for slot in time_slots}
    slot_by_id = {slot.id: slot for slot in time_slots}
    day_slots_by_date: Dict[str, List[TimeSlot]] = {}
    for slot in time_slots:
        day_slots_by_date.setdefault(slot.date, []).append(slot)
    for day_slots in day_slots_by_date.values():
        day_slots.sort(key=slot_sort_key)
    return slot_dates, slot_by_id, day_slots_by_date


def locked_lesson_required_fields(raw: dict, lesson_id: object, rooms: Dict[str, Room]) -> Tuple[object, object]:
    class_id = raw.get("class_id")
    lesson_date = raw.get("date")
    room_id = raw.get("room_id")
    if not class_id or not lesson_date or not room_id:
        raise ValueError(f"锁定课表 {lesson_id} 需要填写 class_id、date 和 room_id")
    if room_id not in rooms:
        raise ValueError(f"锁定课表 {lesson_id} 使用了不存在的教室 {room_id}")
    return class_id, room_id


def locked_lesson_teacher(raw: dict) -> Tuple[str, str]:
    return blank_marker_to_empty(raw.get("teacher_id")), blank_marker_to_empty(raw.get("teacher_name"))


def locked_lesson_base_fields(
    raw: dict,
    lesson_id: str,
    class_id: str,
    room_id: str,
) -> Dict[str, object]:
    return {
        "task_id": f"LOCKED:{lesson_id}",
        "class_id": class_id,
        "class_name": raw.get("class_name") or class_id,
        "product_id": raw.get("business_product_id"),
        "product_name": raw.get("business_product_name"),
        "class_size": None,
        "room_ids": {room_id},
        "is_locked": True,
    }


def locked_lesson_course_fields(raw: dict) -> Dict[str, object]:
    return {
        "subject_category": raw.get("subject_category", ""),
        "subject": raw.get("subject", "已定课程"),
        "quarter": raw.get("quarter"),
        "stage": raw.get("stage"),
        "course_module": raw.get("course_module"),
        "course_group": raw.get("course_group"),
        "course_code": blank_marker_to_empty(raw.get("course_code")),
        "course_name": blank_marker_to_empty(raw.get("course_name")),
    }


def locked_lesson_time_fields(slots: Tuple[TimeSlot, ...]) -> Dict[str, object]:
    return {
        "block_hours": sum(slot.duration_hours for slot in slots),
        "start_date": slots[0].date,
        "end_date": slots[-1].date,
        "allowed_periods": {slots[0].period},
        "allowed_weekdays": None,
        "excluded_weekdays": None,
        "schedule_rules": (),
    }


def locked_lesson_task(
    raw: dict,
    lesson_id: str,
    class_id: str,
    room_id: str,
    slots: Tuple[TimeSlot, ...],
) -> CourseBlock:
    teacher_id, teacher_name = locked_lesson_teacher(raw)
    return CourseBlock(
        **locked_lesson_base_fields(raw, lesson_id, class_id, room_id),
        **locked_lesson_course_fields(raw),
        teacher_id=teacher_id,
        teacher_name=teacher_name,
        **locked_lesson_time_fields(slots),
    )


def locked_lesson_candidate(raw: dict, room_id: str, slots: Tuple[TimeSlot, ...]) -> Candidate:
    teacher_id, teacher_name = locked_lesson_teacher(raw)
    return Candidate(
        slots=slots,
        teacher_id=teacher_id,
        teacher_name=teacher_name,
        room_id=room_id,
    )


def locked_lesson_slots(
    raw: dict,
    time_slots: List[TimeSlot],
    slot_dates: Set[str],
    slot_by_id: Optional[Dict[str, TimeSlot]] = None,
    day_slots_by_date: Optional[Dict[str, List[TimeSlot]]] = None,
) -> Tuple[TimeSlot, ...]:
    slot_ids = parse_string_set(raw.get("slot_ids"))
    slot_by_id = slot_by_id or {slot.id: slot for slot in time_slots}
    if slot_ids:
        return locked_lesson_slots_by_ids(raw, slot_ids, slot_by_id)

    lesson_date = raw.get("date")
    if lesson_date not in slot_dates:
        return ()
    start_time, end_time = locked_lesson_time_range(raw)
    day_slots = locked_lesson_day_slots(time_slots, str(lesson_date), day_slots_by_date)
    matched_slots = contiguous_slots_matching_time_range(day_slots, start_time, end_time)
    if matched_slots:
        return matched_slots
    raise ValueError(f"锁定课表 {raw.get('id', '')} 无法匹配当前课节: {lesson_date} {start_time}-{end_time}")


def locked_lesson_slots_by_ids(
    raw: dict,
    slot_ids: Set[str],
    slot_by_id: Dict[str, TimeSlot],
) -> Tuple[TimeSlot, ...]:
    unknown = slot_ids - set(slot_by_id)
    if unknown:
        raise ValueError(f"锁定课表 {raw.get('id', '')} 包含不存在的课节: {sorted(unknown)}")
    return tuple(sorted((slot_by_id[slot_id] for slot_id in slot_ids), key=slot_sort_key))


def locked_lesson_time_range(raw: dict) -> Tuple[str, str]:
    start_time = normalize_time_value(raw.get("start_time"))
    end_time = normalize_time_value(raw.get("end_time"))
    if not start_time or not end_time:
        raise ValueError(f"锁定课表 {raw.get('id', '')} 在当前课节范围内，需要填写 start_time 和 end_time")
    return start_time, end_time


def locked_lesson_day_slots(
    time_slots: List[TimeSlot],
    lesson_date: str,
    day_slots_by_date: Optional[Dict[str, List[TimeSlot]]] = None,
) -> List[TimeSlot]:
    if day_slots_by_date is None:
        day_slots = [slot for slot in time_slots if slot.date == lesson_date]
        day_slots.sort(key=slot_sort_key)
        return day_slots
    return day_slots_by_date.get(lesson_date, [])


def contiguous_slots_matching_time_range(
    day_slots: List[TimeSlot],
    start_time: str,
    end_time: str,
) -> Tuple[TimeSlot, ...]:
    for start_index, slot in enumerate(day_slots):
        if normalize_time_value(slot.start_time) != start_time:
            continue
        current: List[TimeSlot] = []
        previous_order: Optional[int] = None
        for candidate in day_slots[start_index:]:
            if previous_order is not None and candidate.order != previous_order + 1:
                break
            current.append(candidate)
            previous_order = candidate.order
            if normalize_time_value(candidate.end_time) == end_time:
                return tuple(current)
    return ()


def normalize_time_value(value: object) -> str:
    text = str(value or "").strip()
    match = re.search(r"(\d{1,2}):(\d{2})", text)
    if not match:
        return text
    return f"{int(match.group(1)):02d}:{match.group(2)}"


def blank_marker_to_empty(value: object) -> str:
    text = str(value or "").strip()
    return "" if text in {"-", "—", "无", "暂无", "NULL", "N/A"} else text


def parse_id_set(data: dict, preferred_key: str, fallback_key: Optional[str] = None) -> Optional[Set[str]]:
    values = data.get(preferred_key)
    if values is None and fallback_key:
        values = data.get(fallback_key)
    return parse_string_set(values)


def parse_room_id_fields(
    data: dict,
    allow_area_field_as_room_ids: bool,
    *field_pairs: Tuple[str, str],
) -> Optional[Set[str]]:
    for room_key, area_key in field_pairs:
        values = parse_id_set(data, room_key)
        if values:
            return values
        if allow_area_field_as_room_ids:
            values = parse_id_set(data, area_key)
            if values:
                return values
    return None


def parse_string_set(values: object) -> Optional[Set[str]]:
    if values is None:
        return None
    if isinstance(values, str):
        items = [item.strip() for item in values.split("|")]
    else:
        items = [str(item).strip() for item in values]  # type: ignore[union-attr]
    result = {item for item in items if item}
    return result or None


def expanded_window_tokens(*values: object) -> Set[str]:
    tokens: Set[str] = set()
    for value in values:
        items = parse_string_set(value) or set()
        for item in items:
            token = item.strip()
            if not token:
                continue
            tokens.add(token)
            if token in SEASON_WINDOW_ID_TO_NAME:
                tokens.add(SEASON_WINDOW_ID_TO_NAME[token])
            if token in SEASON_WINDOW_NAME_TO_ID:
                tokens.add(SEASON_WINDOW_NAME_TO_ID[token])
    return tokens


def rule_window_tokens(rule: ScheduleRule) -> Set[str]:
    return expanded_window_tokens(rule.schedule_window_ids, rule.season_window_ids, rule.window_names)


def requirement_window_tokens(raw_req: dict) -> Set[str]:
    return expanded_window_tokens(
        raw_req.get("schedule_window_ids"),
        raw_req.get("schedule_window_id"),
        raw_req.get("season_window_ids"),
        raw_req.get("season_window_id"),
        raw_req.get("window_name"),
        raw_req.get("quarter"),
        raw_req.get("season_name"),
    )


def slot_window_tokens(slot: TimeSlot) -> Set[str]:
    return expanded_window_tokens(slot.schedule_window_id, slot.season_window_id, slot.season_name)


def parse_period_set(values: object, label: str) -> Optional[Set[str]]:
    periods = parse_string_set(values)
    if not periods:
        return None

    normalized: Set[str] = set()
    aliases = {"EV": "EVENING", "NIGHT": "EVENING", "晚上": "EVENING", "晚间": "EVENING", "夜间": "EVENING"}
    for period in periods:
        upper = period.upper()
        value = aliases.get(period, aliases.get(upper, upper))
        if value not in VALID_PERIODS:
            raise ValueError(f"{label} 包含不支持的时段 {period}，可用 AM/PM/EVENING")
        normalized.add(value)
    return normalized


def parse_weekday_set(values: object, label: str) -> Optional[Set[int]]:
    weekdays = parse_string_set(values)
    if not weekdays:
        return None

    normalized: Set[int] = set()
    for weekday in weekdays:
        key = weekday.strip().upper()
        if key not in WEEKDAY_ALIASES:
            raise ValueError(f"{label} 包含不支持的星期 {weekday}")
        normalized.add(WEEKDAY_ALIASES[key])
    return normalized


def validate_date(value: Optional[str], label: str) -> Optional[str]:
    if not value:
        return None
    try:
        Date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} 需要使用 YYYY-MM-DD 格式: {value}") from exc
    return value


def group_schedule_rules_by_product(raw_rules: List[dict]) -> Dict[str, List[ScheduleRule]]:
    rules: Dict[str, List[ScheduleRule]] = {}
    for raw_rule in raw_rules:
        product_id = raw_rule["product_id"]
        rules.setdefault(product_id, []).append(parse_schedule_rule(raw_rule, f"产品 {product_id} 的排课规则"))
    return rules


def parse_schedule_rule(raw_rule: dict, label: str) -> ScheduleRule:
    block_hours = raw_rule.get("block_hours", raw_rule.get("block_hours_override"))
    return ScheduleRule(
        subject=raw_rule.get("subject") or None,
        stage=raw_rule.get("stage") or None,
        course_module=raw_rule.get("course_module") or None,
        course_group=raw_rule.get("course_group", raw_rule.get("teacher_group")) or None,
        start_date=validate_date(raw_rule.get("start_date"), f"{label}/start_date"),
        end_date=validate_date(raw_rule.get("end_date"), f"{label}/end_date"),
        allowed_periods=parse_period_set(raw_rule.get("allowed_periods"), f"{label}/allowed_periods"),
        allowed_weekdays=parse_weekday_set(raw_rule.get("allowed_weekdays"), f"{label}/allowed_weekdays"),
        excluded_weekdays=parse_weekday_set(raw_rule.get("excluded_weekdays"), f"{label}/excluded_weekdays"),
        block_hours=int(block_hours) if block_hours else None,
        schedule_window_ids=parse_string_set(raw_rule.get("schedule_window_ids") or raw_rule.get("schedule_window_id")),
        season_window_ids=parse_string_set(raw_rule.get("season_window_ids") or raw_rule.get("season_window_id")),
        window_names=parse_string_set(raw_rule.get("window_names") or raw_rule.get("window_name") or raw_rule.get("quarter")),
        max_hours_per_class_per_day=positive_float(raw_rule.get("max_hours_per_class_per_day")) or None,
        max_blocks_per_class_per_day=positive_int(raw_rule.get("max_blocks_per_class_per_day")) or None,
    )


def parse_products(
    raw_products: List[dict],
    top_level_schedule_rules: Optional[Dict[str, List[ScheduleRule]]] = None,
) -> Dict[str, Product]:
    products: Dict[str, Product] = {}
    top_level_schedule_rules = top_level_schedule_rules or {}

    for raw_product in raw_products:
        product_id = raw_product["id"]
        if product_id in products:
            raise ValueError(f"重复的产品 id: {product_id}")

        schedule_rules = parse_product_schedule_rules(product_id, raw_product, top_level_schedule_rules)
        requirements = parse_product_requirements(product_id, raw_product.get("requirements", []), schedule_rules)
        if not requirements:
            raise ValueError(f"产品 {product_id} 至少需要配置一条课程需求")

        products[product_id] = Product(
            id=product_id,
            name=raw_product.get("name", product_id),
            requirements=requirements,
        )

    return products


def parse_product_schedule_rules(
    product_id: str,
    raw_product: dict,
    top_level_schedule_rules: Mapping[str, List[ScheduleRule]],
) -> List[ScheduleRule]:
    inline_rules = [
        parse_schedule_rule(raw_rule, f"产品 {product_id} 的排课规则")
        for raw_rule in raw_product.get("schedule_rules", [])
    ]
    return [*top_level_schedule_rules.get(product_id, []), *inline_rules]


def parse_product_requirements(
    product_id: str,
    raw_requirements: List[dict],
    schedule_rules: List[ScheduleRule],
) -> List[ProductRequirement]:
    return [
        parse_product_requirement(product_id, raw_req, schedule_rules)
        for raw_req in raw_requirements
    ]


def parse_product_requirement(
    product_id: str,
    raw_req: dict,
    schedule_rules: List[ScheduleRule],
) -> ProductRequirement:
    common_fields = requirement_common_fields(raw_req)
    schedule_filter_fields = requirement_schedule_filter_fields(raw_req, f"产品 {product_id}")
    total_hours = int(raw_req["total_hours"])
    matching_schedule_rules = find_schedule_rules(product_id, raw_req, schedule_rules)
    block_hours = infer_requirement_block_hours(raw_req, total_hours, matching_schedule_rules)
    validate_positive_hours(
        total_hours,
        block_hours,
        f"产品 {product_id}/{common_fields['subject']}/{common_fields.get('course_module', '')}",
    )
    return ProductRequirement(
        **common_fields,
        total_hours=total_hours,
        block_hours=block_hours,
        room_ids=parse_id_set(raw_req, "room_ids"),
        **schedule_filter_fields,
        schedule_rules=tuple(matching_schedule_rules),
    )


def requirement_common_fields(raw_req: dict) -> dict:
    return {
        "subject_category": raw_req.get("subject_category", ""),
        "subject": raw_req["subject"],
        "quarter": raw_req.get("quarter"),
        "stage": raw_req.get("stage"),
        "course_module": raw_req.get("course_module"),
        "course_group": raw_req.get("course_group", raw_req.get("teacher_group")),
        "course_code": blank_marker_to_empty(raw_req.get("course_code")),
        "course_name": blank_marker_to_empty(raw_req.get("course_name")),
    }


def requirement_schedule_filter_fields(raw_req: dict, label: str) -> dict:
    return {
        "start_date": validate_date(raw_req.get("start_date"), f"{label}/start_date"),
        "end_date": validate_date(raw_req.get("end_date"), f"{label}/end_date"),
        "allowed_periods": parse_period_set(raw_req.get("allowed_periods"), f"{label}/allowed_periods"),
        "allowed_weekdays": parse_weekday_set(raw_req.get("allowed_weekdays"), f"{label}/allowed_weekdays"),
        "excluded_weekdays": parse_weekday_set(raw_req.get("excluded_weekdays"), f"{label}/excluded_weekdays"),
    }


def positive_int(value: object) -> int:
    try:
        parsed = int(float(str(value).strip()))
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0


def positive_float(value: object) -> float:
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError):
        return 0.0
    return parsed if parsed > 0 else 0.0


def infer_requirement_block_hours(
    raw_req: dict,
    total_hours: int,
    matching_schedule_rules: List[ScheduleRule],
) -> int:
    explicit_override = positive_int(raw_req.get("block_hours_override"))
    if explicit_override:
        return explicit_override
    explicit_block = positive_int(raw_req.get("block_hours"))
    if explicit_block:
        return explicit_block

    rule_block_hours = sorted({rule.block_hours for rule in matching_schedule_rules if rule.block_hours})
    if len(rule_block_hours) == 1:
        return rule_block_hours[0]

    divisible = [block_hours for block_hours in rule_block_hours if total_hours % block_hours == 0]
    if divisible:
        return min(divisible)
    return min(rule_block_hours) if rule_block_hours else 0


def find_schedule_rules(product_id: str, raw_req: dict, rules: List[ScheduleRule]) -> List[ScheduleRule]:
    matches = [rule for rule in rules if schedule_rule_matches(rule, raw_req)]
    matches.sort(key=schedule_rule_specificity, reverse=True)
    return matches


def schedule_rule_matches(rule: ScheduleRule, raw_req: dict) -> bool:
    rule_tokens = rule_window_tokens(rule)
    req_tokens = requirement_window_tokens(raw_req)
    if rule_tokens and req_tokens and not (rule_tokens & req_tokens):
        return False
    for field in ("subject", "stage", "course_module", "course_group"):
        rule_value = getattr(rule, field)
        req_value = raw_req.get(field)
        if field == "course_group":
            req_value = raw_req.get("course_group", raw_req.get("teacher_group"))
        if rule_value and not rule_field_matches(rule_value, req_value):
            return False
    return True


def rule_field_matches(rule_value: str, req_value: object) -> bool:
    req_text = str(req_value or "").strip()
    if not req_text:
        return False
    choices = [
        item.strip()
        for item in rule_value.replace("，", "|").replace(",", "|").replace("；", "|").replace(";", "|").split("|")
        if item.strip()
    ]
    return req_text in choices if choices else rule_value == req_text


def schedule_rule_specificity(rule: ScheduleRule) -> int:
    return sum(1 for value in (rule.subject, rule.stage, rule.course_module, rule.course_group) if value)


def parse_classes(
    raw_classes: List[dict],
    products: Dict[str, Product],
    allow_area_field_as_room_ids: bool = False,
) -> Dict[str, SchoolClass]:
    classes: Dict[str, SchoolClass] = {}
    errors: List[str] = []

    for raw_class in raw_classes:
        class_id = str(raw_class.get("id", "")).strip()
        if not class_id:
            errors.append("班级基础信息缺少 id")
            continue
        if class_id in classes:
            errors.append(f"重复的班级 id: {class_id}")
            continue
        try:
            parsed_class = parse_class_row(raw_class, products, allow_area_field_as_room_ids)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if parsed_class:
            classes[class_id] = parsed_class

    if errors:
        visible_errors = errors[:80]
        suffix = f"\n...另有 {len(errors) - len(visible_errors)} 条班级错误" if len(errors) > len(visible_errors) else ""
        raise ValueError("班级数据校验失败:\n" + "\n".join(visible_errors) + suffix)

    return classes


def parse_class_row(
    raw_class: dict,
    products: Dict[str, Product],
    allow_area_field_as_room_ids: bool = False,
) -> Optional[SchoolClass]:
    class_id = str(raw_class.get("id", "")).strip()
    bounds = parse_class_scheduling_bounds(class_id, raw_class)
    product = parse_class_product(class_id, raw_class, products)
    class_room_ids = parse_class_room_ids(raw_class, allow_area_field_as_room_ids)
    requirements = class_requirements_or_none(
        class_id,
        raw_class,
        product,
        class_room_ids,
        allow_area_field_as_room_ids,
    )
    if requirements is None:
        return None
    stage_order = build_stage_order(raw_class, product, requirements)
    return school_class_from_row(raw_class, class_id, product, class_room_ids, bounds, stage_order, requirements)


def school_class_from_row(
    raw_class: dict,
    class_id: str,
    product: Optional[Product],
    class_room_ids: Optional[Set[str]],
    bounds: ClassSchedulingBounds,
    stage_order: Dict[str, int],
    requirements: List[Requirement],
) -> SchoolClass:
    return SchoolClass(
        id=class_id,
        name=raw_class.get("name", class_id),
        product_id=product.id if product else None,
        product_name=product.name if product else None,
        size=raw_class.get("size"),
        room_ids=class_room_ids,
        start_date=bounds.start_date,
        start_period=bounds.start_period,
        end_date=bounds.end_date,
        end_period=bounds.end_period,
        first_lesson_date=bounds.first_lesson_date,
        first_lesson_period=bounds.first_lesson_period,
        stage_order=stage_order,
        requirements=requirements,
    )


def parse_class_scheduling_bounds(class_id: str, raw_class: dict) -> ClassSchedulingBounds:
    start_date, start_period = parse_class_date_period(raw_class, class_id, "start_date", "start_period", "AM")
    end_date, end_period = parse_class_date_period(raw_class, class_id, "end_date", "end_period", "EVENING")
    first_lesson_date, first_lesson_period = parse_class_date_period(
        raw_class,
        class_id,
        "first_lesson_date",
        "first_lesson_period",
        "AM",
    )
    return ClassSchedulingBounds(
        start_date=start_date,
        start_period=start_period,
        end_date=end_date,
        end_period=end_period,
        first_lesson_date=first_lesson_date,
        first_lesson_period=first_lesson_period,
    )


def parse_class_date_period(
    raw_class: dict,
    class_id: str,
    date_field: str,
    period_field: str,
    default_period: str,
) -> Tuple[Optional[str], Optional[str]]:
    date_value = validate_date(raw_class.get(date_field), f"班级 {class_id}/{date_field}")
    period = normalize_class_period(raw_class.get(period_field), default_period if date_value else None)
    validate_class_period_pair(class_id, period_field, period, date_field, date_value)
    return date_value, period


def normalize_class_period(value: object, default: Optional[str] = None) -> Optional[str]:
    period = str(value or default or "").strip().upper()
    return period or None


def validate_class_period_pair(
    class_id: str,
    period_label: str,
    period: Optional[str],
    date_label: str,
    date_value: Optional[str],
) -> None:
    if period and not date_value:
        raise ValueError(f"班级 {class_id} 填写 {period_label} 时也需要填写 {date_label}")
    if period and period not in VALID_PERIODS:
        raise ValueError(f"班级 {class_id} 的 {period_label} 只能填写 AM、PM 或 EVENING")


def parse_class_product(class_id: str, raw_class: dict, products: Dict[str, Product]) -> Optional[Product]:
    product_id = raw_class.get("product_id")
    product = products.get(product_id) if product_id else None
    if product_id and not product:
        raise ValueError(f"班级 {class_id} 引用了不存在的产品 {product_id}")
    return product


def parse_class_room_ids(raw_class: dict, allow_area_field_as_room_ids: bool) -> Optional[Set[str]]:
    return parse_room_id_fields(
        raw_class,
        allow_area_field_as_room_ids,
        ("room_ids", "teaching_area_ids"),
        ("preferred_room_ids", "preferred_teaching_area_ids"),
    )


def class_requirements_or_none(
    class_id: str,
    raw_class: dict,
    product: Optional[Product],
    class_room_ids: Optional[Set[str]],
    allow_area_field_as_room_ids: bool,
) -> Optional[List[Requirement]]:
    requirements = build_class_requirements(
        class_id,
        raw_class,
        product,
        class_room_ids,
        allow_area_field_as_room_ids,
    )
    if requirements:
        return requirements
    if class_has_shared_schedule_markers(raw_class):
        return None
    raise ValueError(f"班级 {class_id} 需要填写 product_id 或 requirements")


def build_class_requirements(
    class_id: str,
    raw_class: dict,
    product: Optional[Product],
    class_room_ids: Optional[Set[str]],
    allow_area_field_as_room_ids: bool,
) -> List[Requirement]:
    if raw_class.get("requirements"):
        return parse_direct_requirements(
            class_id,
            raw_class.get("requirements", []),
            class_room_ids,
            allow_area_field_as_room_ids,
        )
    if product:
        return build_requirements_from_product(class_id, product, raw_class, class_room_ids)
    return parse_direct_requirements(
        class_id,
        raw_class.get("requirements", []),
        class_room_ids,
        allow_area_field_as_room_ids,
    )


def ordered_stage_names(values: object) -> List[str]:
    if values is None:
        return []
    if isinstance(values, str):
        raw_items = re.split(r"[|,，;；/、]+", values)
    else:
        raw_items = [str(item) for item in values]  # type: ignore[union-attr]
    result: List[str] = []
    seen: Set[str] = set()
    for item in raw_items:
        stage = item.strip()
        if stage and stage not in seen:
            result.append(stage)
            seen.add(stage)
    return result


def inferred_stage_order(raw_class: dict, product: Optional[Product]) -> List[str]:
    text = " ".join(
        str(value or "").strip()
        for value in (
            raw_class.get("sub_product"),
            raw_class.get("product_line"),
            raw_class.get("name"),
            raw_class.get("product_name"),
            product.name if product else "",
        )
        if str(value or "").strip()
    )
    for keywords, order in STAGE_ORDER_PROFILES:
        if any(keyword in text for keyword in keywords):
            return list(order)
    return []


def build_stage_order(raw_class: dict, product: Optional[Product], requirements: List[Requirement]) -> Dict[str, int]:
    ordered = ordered_stage_names(raw_class.get("stage_order")) or inferred_stage_order(raw_class, product)
    if not ordered:
        return {}
    seen = set(ordered)
    for requirement in requirements:
        stage = requirement.stage or ""
        if stage and stage not in seen:
            ordered.append(stage)
            seen.add(stage)
    return {stage: index for index, stage in enumerate(ordered)}


def assignment_matches_product_requirement(raw_assignment: dict, requirement: ProductRequirement, product_id: str) -> bool:
    assignment_product = str(raw_assignment.get("product_id") or raw_assignment.get("canonical_product_id") or "").strip()
    if assignment_product and assignment_product != product_id:
        return False
    subject_value = str(raw_assignment.get("subject", "") or "").strip()
    if subject_value and subject_value != requirement.subject:
        return False
    assignment_stage = str(raw_assignment.get("stage", "") or "").strip()
    if assignment_stage and assignment_stage not in {requirement.stage or "", requirement.quarter or ""}:
        return False
    comparisons = (
        (str(raw_assignment.get("course_module", "") or "").strip(), requirement.course_module or ""),
        (str(raw_assignment.get("course_group") or raw_assignment.get("teacher_group") or "").strip(), requirement.course_group or ""),
    )
    for assignment_value, requirement_value in comparisons:
        if assignment_value and assignment_value != requirement_value:
            return False
    return True


def requirement_is_shared_by_class(raw_class: dict, requirement: ProductRequirement, product_id: str) -> bool:
    return any(
        assignment_is_shared(raw_assignment, class_id=raw_class.get("id"))
        and assignment_matches_product_requirement(raw_assignment, requirement, product_id)
        for raw_assignment in raw_class.get("teacher_assignments", [])
    )


def class_has_shared_schedule_markers(raw_class: dict) -> bool:
    return any(assignment_is_shared(raw_assignment, class_id=raw_class.get("id")) for raw_assignment in raw_class.get("teacher_assignments", []))


def select_product_requirements_for_class(
    class_id: str,
    product: Product,
    raw_class: dict,
) -> List[ProductRequirement]:
    class_subject = raw_class.get("subject")
    class_stages = parse_string_set(raw_class.get("stages", raw_class.get("stage")))
    subject_requirements = [
        product_req for product_req in product.requirements
        if not class_subject or product_req.subject == class_subject
    ]
    if class_subject and not subject_requirements:
        raise ValueError(f"班级 {class_id} 的科目 {class_subject} 不在产品 {product.id} 的课程中")
    product_requirements = [
        product_req for product_req in subject_requirements
        if not class_stages or (product_req.stage or "") in class_stages
    ]
    product_requirements = [
        product_req for product_req in product_requirements
        if not requirement_is_shared_by_class(raw_class, product_req, product.id)
    ]
    if class_stages and not product_requirements:
        if class_has_shared_schedule_markers(raw_class):
            return []
        raise ValueError(f"班级 {class_id} 的阶段 {sorted(class_stages)} 不在产品 {product.id} 的课程中")
    return product_requirements


def resolve_product_requirement_teachers(
    class_id: str,
    product_id: str,
    product_requirements: List[ProductRequirement],
    teacher_assignments: Dict[Tuple[str, str, str, str], TeacherAssignment],
) -> List[Tuple[ProductRequirement, TeacherAssignment]]:
    resolved_requirements: List[Tuple[ProductRequirement, TeacherAssignment]] = []
    missing_teacher_labels: List[str] = []
    missing_teacher_seen: Set[str] = set()
    for product_req in product_requirements:
        teacher_assignment = resolve_teacher_assignment_for_requirement(
            product_req,
            teacher_assignments,
            product_requirements,
        )
        if not teacher_assignment:
            detail_text = teacher_assignment_key_text(product_req.subject, product_req.stage, product_req.course_group)
            if detail_text not in missing_teacher_seen:
                missing_teacher_labels.append(detail_text)
                missing_teacher_seen.add(detail_text)
            continue
        resolved_requirements.append((product_req, teacher_assignment))

    if missing_teacher_labels:
        raise ValueError(
            f"班级 {class_id} 的产品 {product_id} 缺少课程老师安排: "
            + "、".join(missing_teacher_labels)
        )
    return resolved_requirements


def class_requirement_from_product_requirement(
    class_id: str,
    product_req: ProductRequirement,
    teacher_assignment: TeacherAssignment,
    class_room_ids: Optional[Set[str]],
) -> Requirement:
    return Requirement(
        subject_category=product_req.subject_category,
        subject=product_req.subject,
        quarter=product_req.quarter,
        stage=product_req.stage,
        course_module=product_req.course_module,
        course_group=product_req.course_group,
        teacher_id=teacher_assignment.teacher_id,
        teacher_name=teacher_assignment.teacher_name,
        total_hours=product_req.total_hours,
        block_hours=product_req.block_hours,
        course_code=product_req.course_code,
        course_name=product_req.course_name,
        room_ids=merge_room_constraints(
            product_req.room_ids,
            class_room_ids,
            f"班级 {class_id}/{product_req.subject}/{product_req.course_module or ''}",
        ),
        start_date=product_req.start_date,
        end_date=product_req.end_date,
        allowed_periods=product_req.allowed_periods,
        allowed_weekdays=product_req.allowed_weekdays,
        excluded_weekdays=product_req.excluded_weekdays,
        schedule_rules=product_req.schedule_rules,
    )


def build_requirements_from_product(
    class_id: str,
    product: Product,
    raw_class: dict,
    class_room_ids: Optional[Set[str]],
) -> List[Requirement]:
    teacher_assignments = parse_teacher_assignments(
        class_id,
        raw_class.get("teacher_assignments", []),
        product.id,
    )
    product_requirements = select_product_requirements_for_class(class_id, product, raw_class)
    resolved_requirements = resolve_product_requirement_teachers(
        class_id,
        product.id,
        product_requirements,
        teacher_assignments,
    )
    requirements = [
        class_requirement_from_product_requirement(class_id, product_req, teacher_assignment, class_room_ids)
        for product_req, teacher_assignment in resolved_requirements
    ]
    return aggregate_class_requirements(class_id, product.id, requirements)


def aggregate_class_requirements(
    class_id: str,
    product_id: str,
    requirements: List[Requirement],
) -> List[Requirement]:
    grouped: Dict[Tuple, List[Requirement]] = {}
    for requirement in requirements:
        if requirement.total_hours % requirement.block_hours == 0:
            validate_hours(requirement.total_hours, requirement.block_hours, requirement_label(class_id, product_id, requirement))
            continue
        grouped.setdefault(aggregation_key(requirement), []).append(requirement)

    consumed: Set[int] = set()
    aggregated: List[Requirement] = []
    for group in grouped.values():
        if len(group) < 2:
            requirement = group[0]
            raise ValueError(f"{requirement_label(class_id, product_id, requirement)} 的 total_hours 必须能被 block_hours 整除")
        total_hours = sum(requirement.total_hours for requirement in group)
        block_hours = group[0].block_hours
        label = f"班级 {class_id}/产品 {product_id}/{group[0].subject}/{group[0].stage or ''}/{group[0].course_group or ''}"
        validate_hours(total_hours, block_hours, label)
        for requirement in group:
            consumed.add(id(requirement))
        aggregated.append(merge_requirements_for_group(group, total_hours))

    result = [requirement for requirement in requirements if id(requirement) not in consumed]
    result.extend(aggregated)
    return result


def requirement_label(class_id: str, product_id: str, requirement: Requirement) -> str:
    return f"班级 {class_id}/产品 {product_id}/{requirement.subject}/{requirement.course_module or ''}"


def aggregation_key(requirement: Requirement) -> Tuple:
    return (
        requirement.subject_category,
        requirement.subject,
        requirement.quarter or "",
        requirement.stage or "",
        requirement.course_group or "",
        requirement.teacher_id,
        requirement.teacher_name,
        requirement.block_hours,
        frozenset(requirement.room_ids or set()),
        requirement.start_date or "",
        requirement.end_date or "",
        frozenset(requirement.allowed_periods or set()),
        frozenset(requirement.allowed_weekdays or set()),
        frozenset(requirement.excluded_weekdays or set()),
        tuple(schedule_rule_key(rule) for rule in requirement.schedule_rules),
    )


def schedule_rule_key(rule: ScheduleRule) -> Tuple:
    return (
        rule.subject or "",
        rule.stage or "",
        rule.course_module or "",
        rule.course_group or "",
        frozenset(rule.schedule_window_ids or set()),
        frozenset(rule.season_window_ids or set()),
        frozenset(rule.window_names or set()),
        rule.start_date or "",
        rule.end_date or "",
        frozenset(rule.allowed_periods or set()),
        frozenset(rule.allowed_weekdays or set()),
        frozenset(rule.excluded_weekdays or set()),
        rule.block_hours or 0,
        rule.max_hours_per_class_per_day or 0,
        rule.max_blocks_per_class_per_day or 0,
    )


def merge_requirements_for_group(group: List[Requirement], total_hours: int) -> Requirement:
    base = group[0]
    modules = [requirement.course_module for requirement in group if requirement.course_module]
    return Requirement(
        subject_category=base.subject_category,
        subject=base.subject,
        quarter=base.quarter,
        stage=base.stage,
        course_module="+".join(modules) if modules else base.course_module,
        course_group=base.course_group,
        teacher_id=base.teacher_id,
        teacher_name=base.teacher_name,
        total_hours=total_hours,
        block_hours=base.block_hours,
        course_code="|".join(sorted({requirement.course_code for requirement in group if requirement.course_code})) or None,
        course_name="|".join(sorted({requirement.course_name for requirement in group if requirement.course_name})) or None,
        room_ids=base.room_ids,
        start_date=base.start_date,
        end_date=base.end_date,
        allowed_periods=base.allowed_periods,
        allowed_weekdays=base.allowed_weekdays,
        excluded_weekdays=base.excluded_weekdays,
        schedule_rules=base.schedule_rules,
    )


def parse_direct_requirements(
    class_id: str,
    raw_requirements: List[dict],
    class_room_ids: Optional[Set[str]],
    allow_area_field_as_room_ids: bool = False,
) -> List[Requirement]:
    return [
        parse_direct_requirement(class_id, raw_req, class_room_ids, allow_area_field_as_room_ids)
        for raw_req in raw_requirements
    ]


def parse_direct_requirement(
    class_id: str,
    raw_req: dict,
    class_room_ids: Optional[Set[str]],
    allow_area_field_as_room_ids: bool = False,
) -> Requirement:
    common_fields = requirement_common_fields(raw_req)
    subject = common_fields["subject"]
    schedule_filter_fields = requirement_schedule_filter_fields(raw_req, f"班级 {class_id}/{subject}")
    total_hours = int(raw_req["total_hours"])
    block_hours = int(raw_req["block_hours"])
    validate_hours(total_hours, block_hours, f"班级 {class_id}/{subject}")
    teacher_assignment = parse_teacher_assignment(raw_req)

    return Requirement(
        **common_fields,
        teacher_id=teacher_assignment.teacher_id,
        teacher_name=teacher_assignment.teacher_name,
        total_hours=total_hours,
        block_hours=block_hours,
        room_ids=direct_requirement_room_ids(
            class_id,
            subject,
            raw_req,
            class_room_ids,
            allow_area_field_as_room_ids,
        ),
        **schedule_filter_fields,
        schedule_rules=(),
    )


def direct_requirement_room_ids(
    class_id: str,
    subject: str,
    raw_req: dict,
    class_room_ids: Optional[Set[str]],
    allow_area_field_as_room_ids: bool,
) -> Optional[Set[str]]:
    requirement_room_ids = parse_room_id_fields(
        raw_req,
        allow_area_field_as_room_ids,
        ("room_ids", "teaching_area_ids"),
    )
    return merge_room_constraints(requirement_room_ids, class_room_ids, f"班级 {class_id}/{subject}")


def merge_room_constraints(
    requirement_room_ids: Optional[Set[str]],
    class_room_ids: Optional[Set[str]],
    label: str,
) -> Optional[Set[str]]:
    if requirement_room_ids and class_room_ids:
        merged = requirement_room_ids & class_room_ids
        if not merged:
            raise ValueError(f"{label} 的班级教室限制与产品/课程教室限制没有交集")
        return merged
    return class_room_ids or requirement_room_ids


def parse_teacher_assignments(
    class_id: str,
    raw_assignments: List[dict],
    product_id: Optional[str] = None,
) -> Dict[Tuple[str, str, str, str], TeacherAssignment]:
    assignments: Dict[Tuple[str, str, str, str], TeacherAssignment] = {}

    for raw_assignment in raw_assignments:
        if assignment_is_shared(raw_assignment, class_id=class_id):
            continue
        if not str(raw_assignment.get("teacher_id", "")).strip() and not str(raw_assignment.get("teacher_name", "")).strip():
            continue
        assignment = parse_teacher_assignment(raw_assignment)
        if assignment.product_id and product_id and assignment.product_id != product_id:
            continue
        key = requirement_key(assignment.subject, assignment.stage, assignment.course_module, assignment.course_group)
        if key in assignments:
            detail_text = course_key_text(assignment.subject, assignment.stage, assignment.course_module, assignment.course_group)
            raise ValueError(f"班级 {class_id} 重复填写了 {detail_text} 的老师安排")
        assignments[key] = assignment

    return assignments


def parse_teacher_assignment(raw_assignment: dict) -> TeacherAssignment:
    teacher_id = raw_assignment.get("teacher_id", "")
    subject = raw_assignment.get("subject", "")
    return TeacherAssignment(
        product_id=raw_assignment.get("product_id") or raw_assignment.get("canonical_product_id") or None,
        subject=subject,
        stage=raw_assignment.get("stage"),
        course_module=raw_assignment.get("course_module"),
        course_group=raw_assignment.get("course_group", raw_assignment.get("teacher_group")),
        teacher_id=teacher_id,
        teacher_name=raw_assignment.get("teacher_name", teacher_id),
    )


def validate_hours(total_hours: int, block_hours: int, label: str) -> None:
    validate_positive_hours(total_hours, block_hours, label)
    if total_hours % block_hours != 0:
        raise ValueError(f"{label} 的 total_hours 必须能被 block_hours 整除")


def validate_positive_hours(total_hours: int, block_hours: int, label: str) -> None:
    if total_hours <= 0 or block_hours <= 0:
        raise ValueError(f"{label} 的 total_hours 和 block_hours 必须大于 0")


def requirement_key(
    subject: str,
    stage: Optional[str],
    course_module: Optional[str],
    course_group: Optional[str],
) -> Tuple[str, str, str, str]:
    return (subject, stage or "", course_module or "", course_group or "")


def requirement_object_key(requirement: object) -> Tuple[str, str, str, str]:
    return requirement_key(
        str(getattr(requirement, "subject", "") or ""),
        getattr(requirement, "stage", None),
        getattr(requirement, "course_module", None),
        getattr(requirement, "course_group", None),
    )


def requirement_mapping_key(row: Mapping[str, object]) -> Tuple[str, str, str, str]:
    return requirement_key(
        str(row.get("subject") or ""),
        str(row.get("stage") or ""),
        str(row.get("course_module") or ""),
        str(row.get("course_group") or ""),
    )


def resolve_teacher_assignment_for_requirement(
    requirement: ProductRequirement,
    assignments: Dict[Tuple[str, str, str, str], TeacherAssignment],
    product_requirements: List[ProductRequirement],
) -> Optional[TeacherAssignment]:
    for key in teacher_assignment_exact_keys(requirement):
        assignment = assignments.get(key)
        if assignment:
            return assignment
    return fallback_teacher_assignment_from_prior_stage(requirement, assignments, product_requirements)


def teacher_assignment_stage_keys(requirement: ProductRequirement) -> List[str]:
    stage_keys: List[str] = []
    for value in (requirement.stage or "", requirement.quarter or "", ""):
        if value not in stage_keys:
            stage_keys.append(value)
    return stage_keys


def teacher_assignment_exact_keys(requirement: ProductRequirement) -> List[Tuple[str, str, str, str]]:
    subject = requirement.subject
    module = requirement.course_module or ""
    group = requirement.course_group or ""
    exact_keys: List[Tuple[str, str, str, str]] = []
    seen: Set[Tuple[str, str, str, str]] = set()
    for stage_key in teacher_assignment_stage_keys(requirement):
        for key in (
            (subject, stage_key, module, group),
            (subject, stage_key, "", group),
            ("", stage_key, module, group),
            ("", stage_key, "", group),
            (subject, stage_key, module, ""),
            (subject, stage_key, "", ""),
            ("", stage_key, "", ""),
        ):
            if key not in seen:
                exact_keys.append(key)
                seen.add(key)
    return exact_keys


def fallback_teacher_assignment_from_prior_stage(
    requirement: ProductRequirement,
    assignments: Dict[Tuple[str, str, str, str], TeacherAssignment],
    product_requirements: List[ProductRequirement],
) -> Optional[TeacherAssignment]:
    stage_rank = stage_rank_for_requirements(product_requirements)
    subject = requirement.subject
    stage = requirement.stage or ""
    group = requirement.course_group or ""
    current_rank = stage_rank.get(stage, len(stage_rank))
    fallback_candidates: List[Tuple[int, int, int, TeacherAssignment]] = []
    for (assignment_subject, assignment_stage, assignment_module, assignment_group), assignment in assignments.items():
        assignment_rank = stage_rank.get(assignment_stage)
        if assignment_rank is None or assignment_rank >= current_rank:
            continue
        if assignment_subject and assignment_subject != subject:
            continue
        if assignment_group != group:
            continue
        fallback_candidates.append(
            (
                assignment_rank,
                0 if not assignment_module else 1,
                0 if assignment_subject == subject else 1,
                assignment,
            )
        )
    if not fallback_candidates:
        return None
    return min(fallback_candidates, key=lambda item: item[:3])[3]


def stage_rank_for_requirements(requirements: List[ProductRequirement]) -> Dict[str, int]:
    rank: Dict[str, int] = {}
    for requirement in requirements:
        stage = requirement.stage or ""
        if stage not in rank:
            rank[stage] = len(rank)
    return rank


def course_key_text(
    subject: str,
    stage: Optional[str],
    course_module: Optional[str],
    course_group: Optional[str],
) -> str:
    parts = [subject]
    if stage:
        parts.append(stage)
    if course_module:
        parts.append(course_module)
    if course_group:
        parts.append(course_group)
    return "/".join(parts)


def teacher_assignment_key_text(subject: str, stage: Optional[str], course_group: Optional[str]) -> str:
    parts = [subject]
    if stage:
        parts.append(stage)
    if course_group:
        parts.append(course_group)
    return "/".join(parts)


def parse_conflict_groups(
    raw_groups: List[dict],
    classes: Dict[str, SchoolClass],
    extra_class_ids: Optional[Set[str]] = None,
) -> Tuple[Dict[str, Set[str]], Dict[str, Set[str]]]:
    conflict_groups: Dict[str, Set[str]] = {}
    known_class_ids = set(classes) | set(extra_class_ids or set())
    class_conflict_groups: Dict[str, Set[str]] = {class_id: set() for class_id in known_class_ids}

    for raw_group in raw_groups:
        group_id = raw_group["id"]
        class_ids = set(raw_group.get("class_ids", []))
        if group_id in conflict_groups:
            raise ValueError(f"重复的冲突组 id: {group_id}")

        class_ids &= known_class_ids
        if len(class_ids) < 2:
            continue

        conflict_groups[group_id] = class_ids
        for class_id in class_ids:
            class_conflict_groups[class_id].add(group_id)

    return conflict_groups, class_conflict_groups


def slot_sort_key(slot: TimeSlot) -> Tuple[str, int, int, str]:
    period_order = PERIOD_ORDER.get(slot.period, 99)
    return (slot.date, period_order, slot.order, slot.id)


def period_sort_value(period: str) -> int:
    return PERIOD_ORDER.get(period, 99)


def slot_in_class_window(slot: TimeSlot, cls: SchoolClass) -> bool:
    slot_day_key = (slot.date, period_sort_value(slot.period))
    if cls.start_date and cls.start_period:
        start_key = (cls.start_date, period_sort_value(cls.start_period))
        if slot_day_key < start_key:
            return False
    if cls.end_date and cls.end_period:
        end_key = (cls.end_date, period_sort_value(cls.end_period))
        if slot_day_key > end_key:
            return False
    return True


def class_has_start_anchor(cls: SchoolClass) -> bool:
    return bool(cls.first_lesson_date and cls.first_lesson_period)


def allowed_start_periods(cls: SchoolClass) -> Set[str]:
    if not cls.first_lesson_period:
        return set()
    start_value = period_sort_value(cls.first_lesson_period)
    return {period for period, value in PERIOD_ORDER.items() if value >= start_value}


def candidate_matches_start_anchor(cls: SchoolClass, candidate: Candidate) -> bool:
    if not class_has_start_anchor(cls):
        return True
    first_slot = candidate.slots[0]
    return first_slot.date == cls.first_lesson_date and first_slot.period in allowed_start_periods(cls)


def build_course_blocks(classes: Dict[str, SchoolClass]) -> List[CourseBlock]:
    tasks: List[CourseBlock] = []
    for cls in classes.values():
        tasks.extend(course_blocks_for_class(cls))
    return tasks


def course_blocks_for_class(cls: SchoolClass) -> List[CourseBlock]:
    tasks: List[CourseBlock] = []
    for req_index, req in enumerate(cls.requirements, start=1):
        tasks.extend(course_blocks_for_requirement(cls, req, req_index))
    return tasks


def course_blocks_for_requirement(cls: SchoolClass, req: Requirement, req_index: int) -> List[CourseBlock]:
    return [
        course_block_from_requirement(cls, req, req_index, block_index)
        for block_index in range(1, requirement_block_count(req) + 1)
    ]


def requirement_block_count(req: Requirement) -> int:
    return req.total_hours // req.block_hours


def course_block_task_id(cls: SchoolClass, req: Requirement, req_index: int, block_index: int) -> str:
    return f"{cls.id}:{req.subject}:{req_index}:{block_index}"


def course_block_from_requirement(
    cls: SchoolClass,
    req: Requirement,
    req_index: int,
    block_index: int,
) -> CourseBlock:
    return CourseBlock(
        task_id=course_block_task_id(cls, req, req_index, block_index),
        **course_block_class_fields(cls),
        **course_block_requirement_fields(req),
    )


def course_block_class_fields(cls: SchoolClass) -> dict:
    return {
        "class_id": cls.id,
        "class_name": cls.name,
        "product_id": cls.product_id,
        "product_name": cls.product_name,
        "class_size": cls.size,
    }


def course_block_requirement_fields(req: Requirement) -> dict:
    return {
        "subject_category": req.subject_category,
        "subject": req.subject,
        "quarter": req.quarter,
        "stage": req.stage,
        "course_module": req.course_module,
        "course_group": req.course_group,
        "teacher_id": req.teacher_id,
        "teacher_name": req.teacher_name,
        "block_hours": req.block_hours,
        "course_code": req.course_code,
        "course_name": req.course_name,
        "room_ids": req.room_ids,
        "start_date": req.start_date,
        "end_date": req.end_date,
        "allowed_periods": req.allowed_periods,
        "allowed_weekdays": req.allowed_weekdays,
        "excluded_weekdays": req.excluded_weekdays,
        "schedule_rules": req.schedule_rules,
    }


def task_stage_rank(cls: SchoolClass, task: CourseBlock) -> Optional[int]:
    if not cls.stage_order or not task.stage:
        return None
    return cls.stage_order.get(task.stage)


def task_stage_rank_for_input(schedule_input: ScheduleInput, task: CourseBlock) -> Optional[int]:
    cls = schedule_input.classes.get(task.class_id)
    if not cls:
        return None
    return task_stage_rank(cls, task)


def task_stage_ready(
    task: CourseBlock,
    cls: SchoolClass,
    task_by_id: Dict[str, CourseBlock],
    task_ids_by_class: Dict[str, List[str]],
    assignments: Dict[str, Assignment],
) -> bool:
    rank = task_stage_rank(cls, task)
    if rank is None:
        return True
    for sibling_id in task_ids_by_class.get(cls.id, []):
        if sibling_id in assignments:
            continue
        sibling = task_by_id[sibling_id]
        sibling_rank = task_stage_rank(cls, sibling)
        if sibling_rank is not None and sibling_rank < rank:
            return False
    return True


def candidate_respects_stage_order(
    task: CourseBlock,
    candidate: Candidate,
    cls: SchoolClass,
    task_by_id: Dict[str, CourseBlock],
    task_ids_by_class: Dict[str, List[str]],
    assignments: Dict[str, Assignment],
) -> bool:
    rank = task_stage_rank(cls, task)
    if rank is None:
        return True
    candidate_start = slot_sort_key(candidate.slots[0])
    candidate_end = slot_sort_key(candidate.slots[-1])
    for sibling_id in task_ids_by_class.get(cls.id, []):
        if sibling_id == task.task_id or sibling_id not in assignments:
            continue
        sibling = task_by_id[sibling_id]
        sibling_rank = task_stage_rank(cls, sibling)
        if sibling_rank is None:
            continue
        sibling_assignment = assignments[sibling_id]
        sibling_start = slot_sort_key(sibling_assignment.candidate.slots[0])
        sibling_end = slot_sort_key(sibling_assignment.candidate.slots[-1])
        if sibling_rank < rank and candidate_start <= sibling_end:
            return False
        if sibling_rank > rank and candidate_end >= sibling_start:
            return False
    return True


def build_contiguous_slot_blocks(time_slots: List[TimeSlot], block_hours: int) -> List[Tuple[TimeSlot, ...]]:
    grouped_slots: Dict[Tuple[str, str], List[TimeSlot]] = {}
    for slot in time_slots:
        grouped_slots.setdefault((slot.date, slot.period), []).append(slot)

    blocks: List[Tuple[TimeSlot, ...]] = []
    for slots in grouped_slots.values():
        slots.sort(key=lambda slot: (slot.order, slot.id))
        for start in range(len(slots)):
            total_hours = 0
            current: List[TimeSlot] = []
            previous_order: Optional[int] = None

            for slot in slots[start:]:
                if previous_order is not None and slot.order != previous_order + 1:
                    break

                current.append(slot)
                total_hours += slot.duration_hours
                previous_order = slot.order

                if total_hours == block_hours:
                    blocks.append(tuple(current))
                    break
                if total_hours > block_hours:
                    break

    blocks.sort(key=lambda block: slot_sort_key(block[0]))
    return blocks


def slot_matches_task_constraints(slot: TimeSlot, task: CourseBlock) -> bool:
    if task.start_date and slot.date < task.start_date:
        return False
    if task.end_date and slot.date > task.end_date:
        return False
    if task.allowed_periods and slot.period not in task.allowed_periods:
        return False

    weekday = Date.fromisoformat(slot.date).weekday()
    if task.allowed_weekdays and weekday not in task.allowed_weekdays:
        return False
    if task.excluded_weekdays and weekday in task.excluded_weekdays:
        return False
    if task.schedule_rules and not any(slot_matches_schedule_rule(slot, rule) for rule in task.schedule_rules):
        return False
    return True


def slot_matches_class_window_constraint(slot: TimeSlot, constraint: ClassWindowConstraint) -> bool:
    constraint_tokens = {
        value
        for value in (constraint.schedule_window_id, constraint.season_window_id, constraint.season_name)
        if value
    }
    if constraint_tokens:
        slot_tokens = slot_window_tokens(slot)
        if not slot_tokens or not (constraint_tokens & slot_tokens):
            return False
    if constraint.start_date and constraint.start_period:
        start_key = (constraint.start_date, period_sort_value(constraint.start_period))
        if (slot.date, period_sort_value(slot.period)) < start_key:
            return False
    if constraint.end_date and constraint.end_period:
        end_key = (constraint.end_date, period_sort_value(constraint.end_period))
        if (slot.date, period_sort_value(slot.period)) > end_key:
            return False
    return True


def class_window_room_ids_for_slots(
    constraints: List[ClassWindowConstraint],
    slot_block: Tuple[TimeSlot, ...],
) -> Optional[Set[str]]:
    if not constraints:
        return None
    matching = [
        constraint
        for constraint in constraints
        if all(slot_matches_class_window_constraint(slot, constraint) for slot in slot_block)
    ]
    if not matching:
        return set()
    constrained_sets = [
        constraint.room_ids
        for constraint in matching
        if constraint.has_room_constraint and constraint.room_ids
    ]
    if not constrained_sets:
        if any(constraint.has_room_constraint for constraint in matching):
            return set()
        return None
    room_ids: Set[str] = set()
    for values in constrained_sets:
        room_ids.update(values)
    return room_ids


def slot_matches_schedule_rule(slot: TimeSlot, rule: ScheduleRule) -> bool:
    rule_tokens = rule_window_tokens(rule)
    if rule_tokens:
        slot_tokens = slot_window_tokens(slot)
        if not slot_tokens or not (rule_tokens & slot_tokens):
            return False
    if rule.start_date and slot.date < rule.start_date:
        return False
    if rule.end_date and slot.date > rule.end_date:
        return False
    if rule.allowed_periods and slot.period not in rule.allowed_periods:
        return False

    weekday = Date.fromisoformat(slot.date).weekday()
    if rule.allowed_weekdays and weekday not in rule.allowed_weekdays:
        return False
    if rule.excluded_weekdays and weekday in rule.excluded_weekdays:
        return False
    return True


def schedule_rules_for_candidate(task: CourseBlock, candidate: Candidate) -> List[ScheduleRule]:
    return [
        rule
        for rule in task.schedule_rules
        if all(slot_matches_schedule_rule(slot, rule) for slot in candidate.slots)
    ]


def product_day_limits_for_candidate(
    task: CourseBlock,
    candidate: Candidate,
) -> Tuple[Optional[float], Optional[int]]:
    matching_rules = schedule_rules_for_candidate(task, candidate)
    max_hour_values = [
        rule.max_hours_per_class_per_day
        for rule in matching_rules
        if rule.max_hours_per_class_per_day
    ]
    max_block_values = [
        rule.max_blocks_per_class_per_day
        for rule in matching_rules
        if rule.max_blocks_per_class_per_day
    ]
    return (
        min(max_hour_values) if max_hour_values else None,
        min(max_block_values) if max_block_values else None,
    )


def candidate_avoids_product_day_limits(
    hour_loads: Dict[Tuple[str, str], float],
    block_loads: Dict[Tuple[str, str], int],
    task: CourseBlock,
    candidate: Candidate,
) -> bool:
    max_hours, max_blocks = product_day_limits_for_candidate(task, candidate)
    if max_hours is None and max_blocks is None:
        return True
    for date_text, hours in candidate_hours_by_date(candidate).items():
        key = (task.class_id, date_text)
        if max_hours is not None and hour_loads.get(key, 0.0) + hours > max_hours + 1e-9:
            return False
        if max_blocks is not None and block_loads.get(key, 0) + 1 > max_blocks:
            return False
    return True


def slot_matches_teacher_unavailability(slot: TimeSlot, rule: TeacherUnavailableRule) -> bool:
    if rule.start_date and slot.date < rule.start_date:
        return False
    if rule.end_date and slot.date > rule.end_date:
        return False
    if rule.periods and slot.period not in rule.periods:
        return False
    if rule.schedule_window_ids:
        slot_window_ids = {
            value
            for value in (slot.schedule_window_id, slot.season_window_id)
            if value
        }
        if not slot_window_ids or not (slot_window_ids & rule.schedule_window_ids):
            return False

    weekday = Date.fromisoformat(slot.date).weekday()
    if rule.weekdays and weekday not in rule.weekdays:
        return False
    return True


def candidate_hits_teacher_unavailability(
    task: CourseBlock,
    slot_block: Tuple[TimeSlot, ...],
    schedule_input: ScheduleInput,
) -> bool:
    teacher_id = str(task.teacher_id or "").strip()
    if not teacher_id:
        return False
    rules = schedule_input.teacher_unavailability.get(teacher_id, [])
    if not rules:
        return False
    return any(
        slot_matches_teacher_unavailability(slot, rule)
        for rule in rules
        for slot in slot_block
    )


def candidate_slot_block_matches_task(
    task: CourseBlock,
    cls: SchoolClass,
    slot_block: Tuple[TimeSlot, ...],
    schedule_input: ScheduleInput,
) -> bool:
    if not all(slot_in_class_window(slot, cls) for slot in slot_block):
        return False
    if not all(slot_matches_task_constraints(slot, task) for slot in slot_block):
        return False
    return not candidate_hits_teacher_unavailability(task, slot_block, schedule_input)


def task_possible_room_ids(task: CourseBlock, schedule_input: ScheduleInput) -> Set[str]:
    if task.room_ids:
        return set(task.room_ids)
    return set(schedule_input.rooms.keys())


def candidate_room_ids_for_slot_block(
    possible_rooms: Set[str],
    class_window_constraints: List[ClassWindowConstraint],
    slot_block: Tuple[TimeSlot, ...],
) -> Set[str]:
    window_room_ids = class_window_room_ids_for_slots(class_window_constraints, slot_block)
    if window_room_ids is None:
        return set(possible_rooms)
    if not window_room_ids:
        return set()
    return possible_rooms & window_room_ids


def sorted_candidate_room_ids(
    room_ids: Set[str],
    schedule_input: ScheduleInput,
    class_size: Optional[int],
) -> List[str]:
    return sorted(
        room_ids,
        key=lambda room_id: (
            room_capacity_shortfall(schedule_input.rooms.get(room_id), class_size) > 0,
            room_capacity_shortfall(schedule_input.rooms.get(room_id), class_size),
            room_id,
        ),
    )


def candidate_slot_blocks_for_task(
    task: CourseBlock,
    schedule_input: ScheduleInput,
    slot_blocks: Optional[List[Tuple[TimeSlot, ...]]] = None,
) -> List[Tuple[TimeSlot, ...]]:
    if slot_blocks is not None:
        return slot_blocks
    return build_contiguous_slot_blocks(schedule_input.time_slots, task.block_hours)


def candidate_room_order_for_slot_block(
    task: CourseBlock,
    schedule_input: ScheduleInput,
    possible_rooms: Set[str],
    class_window_constraints: List[ClassWindowConstraint],
    slot_block: Tuple[TimeSlot, ...],
) -> List[str]:
    room_ids = candidate_room_ids_for_slot_block(
        possible_rooms,
        class_window_constraints,
        slot_block,
    )
    return sorted_candidate_room_ids(room_ids, schedule_input, task.class_size)


def candidate_from_room(task: CourseBlock, slot_block: Tuple[TimeSlot, ...], room: Room) -> Candidate:
    return Candidate(
        slots=slot_block,
        teacher_id=task.teacher_id,
        teacher_name=task.teacher_name,
        room_id=room.id,
    )


def candidates_for_slot_block(
    task: CourseBlock,
    cls: SchoolClass,
    schedule_input: ScheduleInput,
    possible_rooms: Set[str],
    class_window_constraints: List[ClassWindowConstraint],
    slot_block: Tuple[TimeSlot, ...],
) -> List[Candidate]:
    if not candidate_slot_block_matches_task(task, cls, slot_block, schedule_input):
        return []
    candidates: List[Candidate] = []
    room_order = candidate_room_order_for_slot_block(
        task,
        schedule_input,
        possible_rooms,
        class_window_constraints,
        slot_block,
    )
    for room_id in room_order:
        room = schedule_input.rooms.get(room_id)
        if room:
            candidates.append(candidate_from_room(task, slot_block, room))
    return candidates


def candidate_assignments(
    task: CourseBlock,
    schedule_input: ScheduleInput,
    slot_blocks: Optional[List[Tuple[TimeSlot, ...]]] = None,
) -> List[Candidate]:
    cls = schedule_input.classes[task.class_id]
    possible_rooms = task_possible_room_ids(task, schedule_input)
    class_window_constraints = schedule_input.class_window_constraints.get(task.class_id, [])
    candidates: List[Candidate] = []

    for slot_block in candidate_slot_blocks_for_task(task, schedule_input, slot_blocks):
        candidates.extend(
            candidates_for_slot_block(
                task,
                cls,
                schedule_input,
                possible_rooms,
                class_window_constraints,
                slot_block,
            )
        )

    return candidates


def candidate_domains(
    tasks: List[CourseBlock],
    schedule_input: ScheduleInput,
) -> Dict[str, List[Candidate]]:
    slot_blocks_by_hours: Dict[int, List[Tuple[TimeSlot, ...]]] = {}
    for task in tasks:
        if task.block_hours not in slot_blocks_by_hours:
            slot_blocks_by_hours[task.block_hours] = build_contiguous_slot_blocks(
                schedule_input.time_slots,
                task.block_hours,
            )
    return {
        task.task_id: candidate_assignments(
            task,
            schedule_input,
            slot_blocks_by_hours[task.block_hours],
        )
        for task in tasks
    }


def build_schedule_plan(schedule_input: ScheduleInput) -> SchedulePlan:
    tasks = build_course_blocks(schedule_input.classes)
    task_by_id: Dict[str, CourseBlock] = {task.task_id: task for task in tasks}
    task_ids_by_class: Dict[str, List[str]] = {class_id: [] for class_id in schedule_input.classes}
    for task in tasks:
        task_ids_by_class[task.class_id].append(task.task_id)
    return SchedulePlan(
        tasks=tasks,
        task_by_id=task_by_id,
        task_ids_by_class=task_ids_by_class,
        domains=candidate_domains(tasks, schedule_input),
    )


def validate_schedule_plan(schedule_input: ScheduleInput, plan: SchedulePlan) -> None:
    for task in plan.tasks:
        if not plan.domains[task.task_id]:
            raise ValueError(f"任务 {task.task_id} 没有可行的连续课节/老师/教学区组合")
    validate_start_anchor_candidates(schedule_input, plan)


def validate_start_anchor_candidates(schedule_input: ScheduleInput, plan: SchedulePlan) -> None:
    for cls in schedule_input.classes.values():
        if not class_has_start_anchor(cls) or not plan.task_ids_by_class[cls.id]:
            continue
        has_anchor_candidate = any(
            candidate_matches_start_anchor(cls, candidate)
            for task_id in plan.task_ids_by_class[cls.id]
            for candidate in plan.domains[task_id]
        )
        if not has_anchor_candidate:
            allowed = "、".join(sorted(allowed_start_periods(cls), key=period_sort_value))
            raise ValueError(f"班级 {cls.id} 的首课无法排在 {cls.first_lesson_date} {allowed}")


def room_capacity_shortfall(room: Optional[Room], class_size: Optional[int]) -> int:
    if not room or room.capacity_unlimited or not class_size or not room.capacity:
        return 0
    return max(0, class_size - room.capacity)


def locked_constraint_sets(
    schedule_input: ScheduleInput,
) -> Tuple[Set[Tuple[str, str]], Set[Tuple[str, str]], Set[Tuple[str, str]], Set[Tuple[str, str]]]:
    class_slot_used: Set[Tuple[str, str]] = set()
    teacher_slot_used: Set[Tuple[str, str]] = set()
    room_slot_used: Set[Tuple[str, str]] = set()
    conflict_group_slot_used: Set[Tuple[str, str]] = set()

    for assignment in schedule_input.locked_assignments:
        class_group_ids = schedule_input.class_conflict_groups.get(assignment.task.class_id, set())
        for slot in assignment.candidate.slots:
            class_slot_used.add((assignment.task.class_id, slot.id))
            if assignment.candidate.teacher_id:
                teacher_slot_used.add((assignment.candidate.teacher_id, slot.id))
            room_slot_used.add((assignment.candidate.room_id, slot.id))
            for group_id in class_group_ids:
                conflict_group_slot_used.add((group_id, slot.id))
    return class_slot_used, teacher_slot_used, room_slot_used, conflict_group_slot_used


@dataclass
class ScheduleSearchState:
    schedule_input: ScheduleInput
    task_by_id: Dict[str, CourseBlock]
    task_ids_by_class: Dict[str, List[str]]
    assignments: Dict[str, Assignment] = field(default_factory=dict)

    def __post_init__(self) -> None:
        (
            self.class_slot_used,
            self.teacher_slot_used,
            self.room_slot_used,
            self.conflict_group_slot_used,
        ) = locked_constraint_sets(self.schedule_input)
        self.class_teacher_day_loads = locked_class_teacher_day_loads(self.schedule_input)
        self.class_day_hour_loads, self.class_day_block_loads = locked_class_day_rule_loads(
            self.schedule_input
        )

    def is_valid(self, task: CourseBlock, candidate: Candidate) -> bool:
        cls = self.schedule_input.classes[task.class_id]
        if not task_stage_ready(task, cls, self.task_by_id, self.task_ids_by_class, self.assignments):
            return False
        if not candidate_respects_stage_order(
            task,
            candidate,
            cls,
            self.task_by_id,
            self.task_ids_by_class,
            self.assignments,
        ):
            return False
        if not candidate_avoids_same_class_teacher_day_limit(self.class_teacher_day_loads, task, candidate):
            return False
        if not candidate_avoids_product_day_limits(self.class_day_hour_loads, self.class_day_block_loads, task, candidate):
            return False
        class_group_ids = self.schedule_input.class_conflict_groups.get(task.class_id, set())

        for slot in candidate.slots:
            if (task.class_id, slot.id) in self.class_slot_used:
                return False
            if candidate.teacher_id and (candidate.teacher_id, slot.id) in self.teacher_slot_used:
                return False
            if (candidate.room_id, slot.id) in self.room_slot_used:
                return False
            if any((group_id, slot.id) in self.conflict_group_slot_used for group_id in class_group_ids):
                return False
        return True

    def place(self, task: CourseBlock, candidate: Candidate) -> None:
        self.assignments[task.task_id] = Assignment(task=task, candidate=candidate)
        class_group_ids = self.schedule_input.class_conflict_groups.get(task.class_id, set())

        for slot in candidate.slots:
            self.class_slot_used.add((task.class_id, slot.id))
            if candidate.teacher_id:
                self.teacher_slot_used.add((candidate.teacher_id, slot.id))
            self.room_slot_used.add((candidate.room_id, slot.id))
            for group_id in class_group_ids:
                self.conflict_group_slot_used.add((group_id, slot.id))
        add_class_teacher_day_load(self.class_teacher_day_loads, task, candidate)
        add_class_day_rule_load(self.class_day_hour_loads, self.class_day_block_loads, task, candidate)

    def unplace(self, task: CourseBlock, candidate: Candidate) -> None:
        self.assignments.pop(task.task_id, None)
        class_group_ids = self.schedule_input.class_conflict_groups.get(task.class_id, set())

        for slot in candidate.slots:
            self.class_slot_used.remove((task.class_id, slot.id))
            if candidate.teacher_id:
                self.teacher_slot_used.remove((candidate.teacher_id, slot.id))
            self.room_slot_used.remove((candidate.room_id, slot.id))
            for group_id in class_group_ids:
                self.conflict_group_slot_used.remove((group_id, slot.id))
        add_class_teacher_day_load(self.class_teacher_day_loads, task, candidate, delta=-1.0)
        add_class_day_rule_load(self.class_day_hour_loads, self.class_day_block_loads, task, candidate, delta=-1)

    def remaining_task_ids(self) -> List[str]:
        return [task_id for task_id in self.task_by_id if task_id not in self.assignments]

    def class_anchor_satisfied(self, cls: SchoolClass) -> bool:
        if not class_has_start_anchor(cls) or not self.task_ids_by_class[cls.id]:
            return True
        return any(
            candidate_matches_start_anchor(cls, self.assignments[task_id].candidate)
            for task_id in self.task_ids_by_class[cls.id]
            if task_id in self.assignments
        )

    def start_anchors_satisfied(self) -> bool:
        return all(self.class_anchor_satisfied(cls) for cls in self.schedule_input.classes.values())

    def domain_size_after_filter(
        self,
        task_id: str,
        domains: Dict[str, List[Candidate]],
        anchor_only: bool = False,
    ) -> int:
        task = self.task_by_id[task_id]
        cls = self.schedule_input.classes[task.class_id]
        if not task_stage_ready(task, cls, self.task_by_id, self.task_ids_by_class, self.assignments):
            return 0
        return sum(
            1
            for candidate in domains[task_id]
            if self.is_valid(task, candidate)
            and (not anchor_only or candidate_matches_start_anchor(cls, candidate))
        )

    def valid_options(
        self,
        task_id: str,
        domains: Dict[str, List[Candidate]],
        anchor_only: bool = False,
    ) -> List[Candidate]:
        task = self.task_by_id[task_id]
        cls = self.schedule_input.classes[task.class_id]
        if not task_stage_ready(task, cls, self.task_by_id, self.task_ids_by_class, self.assignments):
            return []
        options = [
            candidate
            for candidate in domains[task_id]
            if self.is_valid(task, candidate)
            and (not anchor_only or candidate_matches_start_anchor(cls, candidate))
        ]
        options.sort(key=lambda candidate: self.candidate_sort_key(task, candidate))
        return options

    def candidate_sort_key(
        self,
        task: CourseBlock,
        candidate: Candidate,
    ) -> Tuple[float, Tuple[str, int, int, str], str]:
        return (
            candidate_same_day_teacher_travel_penalty(
                self.schedule_input,
                [*self.schedule_input.locked_assignments, *self.assignments.values()],
                task,
                candidate,
            ),
            slot_sort_key(candidate.slots[0]),
            candidate.room_id,
        )


def schedule(schedule_input: ScheduleInput) -> List[Assignment]:
    plan = build_schedule_plan(schedule_input)
    validate_schedule_plan(schedule_input, plan)
    greedy_result = greedy_schedule(
        schedule_input,
        plan.task_by_id,
        plan.task_ids_by_class,
        plan.domains,
    )
    if greedy_result is not None:
        return sorted_assignments([*schedule_input.locked_assignments, *greedy_result])

    backtracking_result = backtracking_schedule(schedule_input, plan)
    if backtracking_result is None:
        raise ValueError("无法找到满足约束的排课方案，请检查教师不可排日期时段、班级排课窗口、教室资源或互斥关系")

    return sorted_assignments([*schedule_input.locked_assignments, *backtracking_result])


def choose_backtracking_task(
    schedule_input: ScheduleInput,
    plan: SchedulePlan,
    search_state: ScheduleSearchState,
) -> str:
    anchor_task_id = choose_anchor_backtracking_task(schedule_input, plan, search_state)
    if anchor_task_id:
        return anchor_task_id
    return choose_ready_backtracking_task(schedule_input, plan, search_state)


def choose_anchor_backtracking_task(
    schedule_input: ScheduleInput,
    plan: SchedulePlan,
    search_state: ScheduleSearchState,
) -> Optional[str]:
    for cls in schedule_input.classes.values():
        if search_state.class_anchor_satisfied(cls):
            continue
        anchor_candidates = [
            task_id
            for task_id in plan.task_ids_by_class[cls.id]
            if task_id not in search_state.assignments
            and search_state.domain_size_after_filter(task_id, plan.domains, anchor_only=True) > 0
        ]
        if anchor_candidates:
            anchor_candidates.sort(
                key=lambda task_id: (
                    search_state.domain_size_after_filter(task_id, plan.domains, anchor_only=True),
                    len(plan.domains[task_id]),
                )
            )
            return anchor_candidates[0]
        remaining_for_class = [
            task_id
            for task_id in plan.task_ids_by_class[cls.id]
            if task_id not in search_state.assignments
        ]
        if remaining_for_class:
            return remaining_for_class[0]
    return None


def choose_ready_backtracking_task(
    schedule_input: ScheduleInput,
    plan: SchedulePlan,
    search_state: ScheduleSearchState,
) -> str:
    candidates = search_state.remaining_task_ids()
    ready_candidates = [
        task_id
        for task_id in candidates
        if task_stage_ready(
            plan.task_by_id[task_id],
            schedule_input.classes[plan.task_by_id[task_id].class_id],
            plan.task_by_id,
            plan.task_ids_by_class,
            search_state.assignments,
        )
    ]
    if ready_candidates:
        candidates = ready_candidates
    candidates.sort(
        key=lambda task_id: (
            search_state.domain_size_after_filter(task_id, plan.domains),
            len(plan.domains[task_id]),
        )
    )
    return candidates[0]


def backtracking_schedule(schedule_input: ScheduleInput, plan: SchedulePlan) -> Optional[List[Assignment]]:
    search_state = ScheduleSearchState(schedule_input, plan.task_by_id, plan.task_ids_by_class)

    def start_anchors_satisfied() -> bool:
        return search_state.start_anchors_satisfied()

    def backtrack() -> bool:
        if len(search_state.assignments) == len(plan.task_by_id):
            return start_anchors_satisfied()

        task_id = choose_backtracking_task(schedule_input, plan, search_state)
        task = plan.task_by_id[task_id]
        cls = schedule_input.classes[task.class_id]
        options = search_state.valid_options(
            task_id,
            plan.domains,
            anchor_only=not search_state.class_anchor_satisfied(cls),
        )

        for candidate in options:
            search_state.place(task, candidate)
            if backtrack():
                return True
            search_state.unplace(task, candidate)

        return False

    if not backtrack():
        return None
    return list(search_state.assignments.values())


def sorted_assignments(assignments: List[Assignment]) -> List[Assignment]:
    result = list(assignments)
    result.sort(
        key=lambda assignment: (
            slot_sort_key(assignment.candidate.slots[0]),
            assignment.task.class_id,
            assignment.task.subject,
            assignment.task.task_id,
        )
    )
    return result


def greedy_schedule(
    schedule_input: ScheduleInput,
    task_by_id: Dict[str, CourseBlock],
    task_ids_by_class: Dict[str, List[str]],
    domains: Dict[str, List[Candidate]],
) -> Optional[List[Assignment]]:
    search_state = ScheduleSearchState(schedule_input, task_by_id, task_ids_by_class)

    while len(search_state.assignments) < len(task_by_id):
        choice = choose_greedy_task(schedule_input, task_by_id, task_ids_by_class, domains, search_state)
        if choice is None:
            return None
        task_id, options = choice
        if not options:
            return None
        search_state.place(task_by_id[task_id], options[0])

    if not search_state.start_anchors_satisfied():
        return None
    return list(search_state.assignments.values())


def choose_greedy_task(
    schedule_input: ScheduleInput,
    task_by_id: Dict[str, CourseBlock],
    task_ids_by_class: Dict[str, List[str]],
    domains: Dict[str, List[Candidate]],
    search_state: ScheduleSearchState,
) -> Optional[Tuple[str, List[Candidate]]]:
    anchor_choice = choose_greedy_anchor_task(schedule_input, task_ids_by_class, domains, search_state)
    if anchor_choice is not None:
        return anchor_choice
    return choose_greedy_ready_task(schedule_input, task_by_id, task_ids_by_class, domains, search_state)


def choose_greedy_anchor_task(
    schedule_input: ScheduleInput,
    task_ids_by_class: Dict[str, List[str]],
    domains: Dict[str, List[Candidate]],
    search_state: ScheduleSearchState,
) -> Optional[Tuple[str, List[Candidate]]]:
    for cls in schedule_input.classes.values():
        if search_state.class_anchor_satisfied(cls):
            continue
        anchor_choices = [
            (task_id, search_state.valid_options(task_id, domains, anchor_only=True))
            for task_id in task_ids_by_class[cls.id]
            if task_id not in search_state.assignments
        ]
        anchor_choices = [(task_id, options) for task_id, options in anchor_choices if options]
        if not anchor_choices:
            return None
        anchor_choices.sort(key=lambda item: (len(item[1]), len(domains[item[0]])))
        return anchor_choices[0]
    return None


def choose_greedy_ready_task(
    schedule_input: ScheduleInput,
    task_by_id: Dict[str, CourseBlock],
    task_ids_by_class: Dict[str, List[str]],
    domains: Dict[str, List[Candidate]],
    search_state: ScheduleSearchState,
) -> Optional[Tuple[str, List[Candidate]]]:
    choices = [
        (task_id, search_state.valid_options(task_id, domains))
        for task_id in task_by_id
        if task_id not in search_state.assignments
        and task_stage_ready(
            task_by_id[task_id],
            schedule_input.classes[task_by_id[task_id].class_id],
            task_by_id,
            task_ids_by_class,
            search_state.assignments,
        )
    ]
    if not choices or any(not options for _, options in choices):
        return None
    choices.sort(key=lambda item: (len(item[1]), len(domains[item[0]])))
    return choices[0]


def write_csv(assignments: List[Assignment], out_path: Path, schedule_input: Optional[ScheduleInput] = None) -> None:
    rows = []
    for assignment in assignments:
        slots = assignment.candidate.slots
        room = schedule_input.rooms.get(assignment.candidate.room_id) if schedule_input else None
        rows.append(
            {
                "date": slots[0].date,
                "period": slots[0].period,
                "start_slot_id": slots[0].id,
                "start_slot_name": slots[0].name,
                "start_time": slots[0].start_time or "",
                "end_slot_id": slots[-1].id,
                "end_slot_name": slots[-1].name,
                "end_time": slots[-1].end_time or "",
                "slot_ids": "|".join(slot.id for slot in slots),
                "class_id": assignment.task.class_id,
                "class_name": assignment.task.class_name,
                "product_id": assignment.task.product_id or "",
                "product_name": assignment.task.product_name or "",
                "subject_category": assignment.task.subject_category,
                "subject": assignment.task.subject,
                "quarter": assignment.task.quarter or "",
                "stage": assignment.task.stage or "",
                "course_module": assignment.task.course_module or "",
                "course_group": assignment.task.course_group or "",
                "teacher_id": assignment.candidate.teacher_id,
                "teacher_name": assignment.candidate.teacher_name,
                "room_id": assignment.candidate.room_id,
                "room_name": room.name if room else "",
                "teaching_area_id": room.teaching_area_id if room else "",
                "duration_hours": sum(slot.duration_hours for slot in slots),
                "source": "locked" if assignment.task.is_locked else "generated",
            }
        )
    write_csv_rows(out_path, SCHEDULE_CSV_FIELDNAMES, rows, encoding="utf-8", extrasaction="raise")


@dataclass(frozen=True)
class ScheduleHtmlView:
    slots: List[TimeSlot]
    classes: List[SchoolClass]
    slot_index: Dict[str, int]
    assignments_by_class: Dict[str, List[Assignment]]
    subjects: List[str]
    colors: Dict[str, str]


SCHEDULE_HTML_CSS_TEMPLATE = Template(
    """
    :root {
      --grid-columns: repeat($slot_count, minmax(132px, 1fr));
      --border: #d7dce2;
      --muted: #607086;
      --text: #1b2636;
      --bg: #f6f7f9;
      --panel: #ffffff;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    header {
      padding: 24px 28px 14px;
      border-bottom: 1px solid var(--border);
      background: var(--panel);
    }
    h1 {
      margin: 0 0 8px;
      font-size: 24px;
      font-weight: 700;
      letter-spacing: 0;
    }
    .summary {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      color: var(--muted);
      font-size: 14px;
    }
    main { padding: 20px 28px 28px; }
    .legend {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin-bottom: 14px;
      font-size: 14px;
    }
    .legend-item {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      color: var(--muted);
    }
    .legend-item i {
      width: 12px;
      height: 12px;
      border-radius: 3px;
      display: inline-block;
    }
    .timeline {
      overflow-x: auto;
      border: 1px solid var(--border);
      background: var(--panel);
    }
    .grid {
      min-width: ${grid_min_width}px;
      display: grid;
      grid-template-columns: 168px var(--grid-columns);
    }
    .corner,
    .slot-header,
    .class-label {
      border-bottom: 1px solid var(--border);
      background: #fbfcfd;
    }
    .corner,
    .class-label {
      position: sticky;
      left: 0;
      z-index: 3;
      border-right: 1px solid var(--border);
    }
    .corner {
      top: 0;
      min-height: 64px;
      padding: 16px;
      font-weight: 700;
    }
    .slot-header {
      min-height: 64px;
      padding: 10px 8px;
      border-right: 1px solid var(--border);
      font-size: 13px;
      text-align: center;
    }
    .slot-header span {
      display: block;
      margin-top: 4px;
      color: var(--muted);
    }
    .slot-header em {
      display: block;
      margin-top: 3px;
      color: #344256;
      font-size: 12px;
      font-style: normal;
    }
    .class-label {
      min-height: 76px;
      padding: 14px 12px;
      font-weight: 700;
    }
    .class-label small {
      display: block;
      margin-top: 4px;
      color: var(--muted);
      font-weight: 500;
    }
    .class-track {
      position: relative;
      min-height: 76px;
      display: grid;
      grid-template-columns: var(--grid-columns);
      grid-column: 2 / -1;
      border-bottom: 1px solid var(--border);
      background:
        repeating-linear-gradient(
          to right,
          transparent 0,
          transparent calc(100% / $safe_slot_count - 1px),
          var(--border) calc(100% / $safe_slot_count - 1px),
          var(--border) calc(100% / $safe_slot_count)
        );
    }
    .bar {
      align-self: center;
      min-height: 52px;
      margin: 8px 6px;
      padding: 8px 10px;
      border-radius: 6px;
      color: #fff;
      box-shadow: 0 2px 8px rgba(27, 38, 54, 0.12);
      overflow: hidden;
    }
    .bar strong,
    .bar span {
      display: block;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .bar strong { font-size: 14px; }
    .bar span {
      margin-top: 4px;
      font-size: 12px;
      opacity: 0.92;
    }
    .table-wrap {
      margin-top: 18px;
      overflow-x: auto;
      border: 1px solid var(--border);
      background: var(--panel);
    }
    table {
      width: 100%;
      border-collapse: collapse;
      min-width: 860px;
    }
    th,
    td {
      padding: 10px 12px;
      border-bottom: 1px solid var(--border);
      text-align: left;
      font-size: 14px;
    }
    th {
      background: #fbfcfd;
      color: var(--muted);
      font-weight: 700;
    }
"""
)


def build_schedule_html_view(assignments: List[Assignment], schedule_input: ScheduleInput) -> ScheduleHtmlView:
    slots = list(schedule_input.time_slots)
    slot_index = {slot.id: index + 1 for index, slot in enumerate(slots)}
    classes = list(schedule_input.classes.values())
    known_class_ids = {cls.id for cls in classes}
    for assignment in assignments:
        if assignment.task.class_id in known_class_ids:
            continue
        classes.append(
            SchoolClass(
                id=assignment.task.class_id,
                name=assignment.task.class_name,
                product_id=assignment.task.product_id,
                product_name=assignment.task.product_name,
                size=assignment.task.class_size,
                room_ids=assignment.task.room_ids,
                start_date=None,
                start_period=None,
                end_date=None,
                end_period=None,
                first_lesson_date=None,
                first_lesson_period=None,
                stage_order={},
                requirements=[],
            )
        )
        known_class_ids.add(assignment.task.class_id)
    subjects = sorted({assignment.task.subject for assignment in assignments})
    colors = build_subject_colors(subjects)
    assignments_by_class: Dict[str, List[Assignment]] = {cls.id: [] for cls in classes}
    for assignment in assignments:
        assignments_by_class[assignment.task.class_id].append(assignment)
    return ScheduleHtmlView(
        slots=slots,
        classes=classes,
        slot_index=slot_index,
        assignments_by_class=assignments_by_class,
        subjects=subjects,
        colors=colors,
    )


def render_schedule_html_styles(view: ScheduleHtmlView) -> str:
    return SCHEDULE_HTML_CSS_TEMPLATE.substitute(
        slot_count=len(view.slots),
        grid_min_width=max(760, len(view.slots) * 132 + 168),
        safe_slot_count=max(len(view.slots), 1),
    )


def render_slot_headers(slots: List[TimeSlot]) -> str:
    return "\n".join(
        (
            f'<div class="slot-header"><strong>{escape(slot.date)}</strong>'
            f'<span>{escape(slot.name)}</span>'
            f'<em>{escape(format_slot_time(slot))}</em></div>'
        )
        for slot in slots
    )


def render_schedule_legend(view: ScheduleHtmlView) -> str:
    return "\n".join(
        f'<span class="legend-item"><i style="background:{escape(view.colors[subject])}"></i>{escape(subject)}</span>'
        for subject in view.subjects
    )


def render_schedule_timeline(view: ScheduleHtmlView) -> str:
    slot_columns = render_slot_headers(view.slots)
    rows = "\n".join(
        render_class_row(cls, view.assignments_by_class[cls.id], view.slot_index, view.colors)
        for cls in view.classes
    )
    return f"""
    <section class="timeline">
      <div class="grid">
        <div class="corner">班级 / 课节</div>
        {slot_columns}
        {rows}
      </div>
    </section>
"""


def render_schedule_html_document(view: ScheduleHtmlView, assignments: List[Assignment]) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>班级课表甘特图</title>
  <style>
{render_schedule_html_styles(view)}
  </style>
</head>
<body>
  <header>
    <h1>班级课表甘特图</h1>
    <div class="summary">
      <span>班级 {len(view.classes)} 个</span>
      <span>课程块 {len(assignments)} 个</span>
      <span>课节 {len(view.slots)} 个</span>
    </div>
  </header>
  <main>
    <div class="legend">{render_schedule_legend(view)}</div>
    {render_schedule_timeline(view)}
    {render_assignment_table(assignments)}
  </main>
</body>
</html>
"""


def write_html(assignments: List[Assignment], schedule_input: ScheduleInput, out_path: Path) -> None:
    view = build_schedule_html_view(assignments, schedule_input)
    out_path.write_text(render_schedule_html_document(view, assignments), encoding="utf-8")


def build_subject_colors(subjects: List[str]) -> Dict[str, str]:
    palette = [
        "#2f6f73",
        "#bc5b2c",
        "#6f5aa7",
        "#557a35",
        "#b0445c",
        "#3d6fa8",
        "#8a6a22",
        "#4f7d68",
    ]
    return {subject: palette[index % len(palette)] for index, subject in enumerate(subjects)}


def course_display_name(task: CourseBlock) -> str:
    parts = [task.subject]
    if task.quarter:
        parts.append(task.quarter)
    if task.stage:
        parts.append(task.stage)
    if task.course_module:
        parts.append(task.course_module)
    return " / ".join(parts)


def render_class_row(
    cls: SchoolClass,
    assignments: List[Assignment],
    slot_index: Dict[str, int],
    colors: Dict[str, str],
) -> str:
    bars = "\n".join(render_assignment_bar(assignment, slot_index, colors) for assignment in assignments)
    size_text = f"{cls.size} 人" if cls.size else "未填写人数"
    return f"""
        <div class="class-label">{escape(cls.name)}<small>{escape(cls.id)} · {escape(size_text)}</small></div>
        <div class="class-track">{bars}</div>
"""


def render_assignment_bar(
    assignment: Assignment,
    slot_index: Dict[str, int],
    colors: Dict[str, str],
) -> str:
    slots = assignment.candidate.slots
    start = slot_index[slots[0].id]
    end = slot_index[slots[-1].id] + 1
    category = f"{assignment.task.subject_category} · " if assignment.task.subject_category else ""
    course_name = course_display_name(assignment.task)
    title = (
        f"{assignment.task.class_name} {course_name} "
        f"{slots[0].date} {slots[0].name}-{slots[-1].name} {format_time_range(slots)}"
    )

    return f"""
          <div
            class="bar"
            title="{escape(title)}"
            style="grid-column: {start} / {end}; background: {escape(colors[assignment.task.subject])};"
          >
            <strong>{escape(category + course_name)}</strong>
            <span>{escape(format_time_range(slots))}</span>
            <span>{escape(assignment.candidate.teacher_name)} · {escape(assignment.candidate.room_id)}</span>
          </div>
"""


def render_assignment_table(assignments: List[Assignment]) -> str:
    rows = "\n".join(render_assignment_table_row(assignment) for assignment in assignments)
    return f"""
    <section class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>日期</th>
            <th>时段</th>
            <th>课节</th>
            <th>时间</th>
            <th>班级</th>
            <th>产品</th>
            <th>类别</th>
            <th>科目</th>
            <th>季度</th>
            <th>阶段</th>
            <th>模块</th>
            <th>师资组</th>
            <th>老师</th>
            <th>教学区</th>
            <th>小时</th>
          </tr>
        </thead>
        <tbody>
          {rows}
        </tbody>
      </table>
    </section>
"""


def render_assignment_table_row(assignment: Assignment) -> str:
    slots = assignment.candidate.slots
    return f"""
          <tr>
            <td>{escape(slots[0].date)}</td>
            <td>{escape(slots[0].period)}</td>
            <td>{escape(slots[0].name)} - {escape(slots[-1].name)}</td>
            <td>{escape(format_time_range(slots))}</td>
            <td>{escape(assignment.task.class_name)}</td>
            <td>{escape(assignment.task.product_name or "")}</td>
            <td>{escape(assignment.task.subject_category)}</td>
            <td>{escape(assignment.task.subject)}</td>
            <td>{escape(assignment.task.quarter or "")}</td>
            <td>{escape(assignment.task.stage or "")}</td>
            <td>{escape(assignment.task.course_module or "")}</td>
            <td>{escape(assignment.task.course_group or "")}</td>
            <td>{escape(assignment.candidate.teacher_name)}</td>
            <td>{escape(assignment.candidate.room_id)}</td>
            <td>{sum(slot.duration_hours for slot in slots)}</td>
          </tr>
"""


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def format_slot_time(slot: TimeSlot) -> str:
    if slot.start_time and slot.end_time:
        return f"{slot.start_time} - {slot.end_time}"
    return ""


def format_time_range(slots: Tuple[TimeSlot, ...]) -> str:
    start = slots[0].start_time
    end = slots[-1].end_time
    if start and end:
        return f"{start} - {end}"
    return ""


def main() -> None:
    parser = argparse.ArgumentParser(description="班级自动化排课")
    parser.add_argument("--input", required=True, type=Path, help="输入 JSON 文件")
    parser.add_argument("--output", required=True, type=Path, help="输出 CSV 文件")
    parser.add_argument("--html-output", type=Path, help="可选：输出班级课表甘特图 HTML 文件")
    args = parser.parse_args()

    try:
        schedule_input = load_input(args.input)
        assignments = schedule(schedule_input)
        write_csv(assignments, args.output, schedule_input)
        if args.html_output:
            write_html(assignments, schedule_input, args.html_output)
    except ValueError as exc:
        print(f"排课失败: {exc}", file=sys.stderr)
        raise SystemExit(1) from None

    print(f"排课成功，共生成 {len(assignments)} 条记录: {args.output}")
    if args.html_output:
        print(f"甘特图已生成: {args.html_output}")


if __name__ == "__main__":
    main()
