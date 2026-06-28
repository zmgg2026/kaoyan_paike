#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date as Date, datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_camp_maintenance_schedule import (  # noqa: E402
    assignments_from_rows,
    load_class_metadata,
)
from scripts.csv_utils import clean_cell as clean, read_csv_rows, write_csv_rows as write_csv_rows_with_fields  # noqa: E402
from scripts.schedule_class_windows import (  # noqa: E402
    ClassWindowConstraint,
    load_class_window_constraint_items,
    merge_constraints,
)
from scripts.schedule_conflicts import write_teacher_time_conflicts_csv  # noqa: E402
from scripts.schedule_data import load_room_metadata as load_raw_room_metadata, load_room_names  # noqa: E402
from scripts.schedule_outputs import write_day_table_html  # noqa: E402


FIELDNAMES = [
    "date",
    "weekday",
    "period",
    "lesson_slot",
    "slot_label",
    "start_time",
    "end_time",
    "class_id",
    "class_name",
    "subject",
    "quarter",
    "stage",
    "course_module",
    "course_group",
    "course_code",
    "course_name",
    "teacher_id",
    "teacher_name",
    "room_id",
    "room_name",
    "duration_hours",
]

PUBLIC_SUBJECTS = {"英语", "政治", "数学", "语文"}
PERIOD_ORDER = {"AM": 0, "PM": 1, "EVENING": 2}
PERIOD_SLOTS = {
    "AM": [("AM1", "上午一", "08:00", "10:00"), ("AM2", "上午二", "10:20", "12:20")],
    "PM": [("PM1", "下午一", "14:00", "16:00"), ("PM2", "下午二", "16:20", "18:20")],
    "EVENING": [("EVENING1", "晚上一", "19:00", "21:00")],
}
WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
FAR_REGION_PAIRS = {
    ("新站", "滨湖"),
    ("滨湖", "新站"),
    ("新站", "经开"),
    ("经开", "新站"),
    ("新站", "翡翠湖"),
    ("翡翠湖", "新站"),
}

STAGE_ORDERS = {
    "寒暑营": {"寒假": 0, "春季": 1, "暑假": 2, "秋季": 3, "基础": 0, "强化": 1, "冲刺": 2},
    "无忧寒": {"寒假": 0, "春季": 1, "暑假": 2, "秋季": 3, "基础": 0, "强化": 1, "冲刺": 2},
    "全年营": {"导学1": 0, "导学2": 1, "一轮": 2, "二轮": 3, "三轮": 4, "四轮": 5},
    "半年营": {"基础": 0, "强化": 1, "冲刺": 2},
    "暑假营": {"基础": 0, "强化": 1, "冲刺": 2},
    "无忧秋": {"基础": 0, "强化": 1, "冲刺": 2},
    "无忧春": {"基础": 0, "强化": 1, "冲刺": 2},
    "无忧暑": {"基础": 0, "强化": 1, "冲刺": 2},
    "冲刺营": {"冲刺": 0},
}


@dataclass(frozen=True)
class Block:
    key: Tuple[str, str, str, str, str, str]
    indices: Tuple[int, ...]
    class_id: str
    suite_code: str
    sub_product: str
    subject: str
    stage: str
    date: str
    week: str
    period: str
    teacher_key: str
    teacher_name: str
    room_id: str
    room_name: str
    hours: float


def load_window_constraints(data_dir: Path) -> Dict[str, List[ClassWindowConstraint]]:
    return load_class_window_constraint_items(data_dir / "class_window_boundaries.csv")


def write_csv_rows(path: Path, rows: Sequence[dict]) -> None:
    write_csv_rows_with_fields(path, FIELDNAMES, rows)


def weekday_label(date_text: str) -> str:
    return WEEKDAYS[Date.fromisoformat(date_text).weekday()]


def week_start(date_text: str) -> str:
    day = Date.fromisoformat(date_text)
    return (day - timedelta(days=day.weekday())).isoformat()


def date_range(start: str, end: str) -> Iterable[str]:
    current = Date.fromisoformat(start)
    final = Date.fromisoformat(end)
    while current <= final:
        yield current.isoformat()
        current += timedelta(days=1)


def week_dates(week: str) -> List[str]:
    start = Date.fromisoformat(week)
    return [(start + timedelta(days=offset)).isoformat() for offset in range(7)]


def sort_rows(rows: Iterable[dict]) -> List[dict]:
    return sorted(
        rows,
        key=lambda row: (
            clean(row.get("date")),
            PERIOD_ORDER.get(clean(row.get("period")), 9),
            clean(row.get("start_time")),
            clean(row.get("class_id")),
            clean(row.get("subject")),
            clean(row.get("course_code")),
        ),
    )


def load_class_conflicts(path: Path) -> Dict[str, Set[str]]:
    lookup: Dict[str, Set[str]] = defaultdict(set)
    if not path.exists():
        return {}
    for row in read_csv_rows(path):
        if clean(row.get("is_active")) not in {"是", "1", "true", "True", "yes"}:
            continue
        group_id = clean(row.get("id"))
        class_ids = [item.strip() for item in clean(row.get("class_ids")).split("|") if item.strip()]
        if len(class_ids) < 2:
            continue
        for class_id in class_ids:
            lookup[class_id].add(group_id)
    return lookup


def load_blackout_dates(path: Path) -> Set[str]:
    dates: Set[str] = set()
    if not path.exists():
        return dates
    for row in read_csv_rows(path):
        if clean(row.get("is_active")) not in {"是", "1", "true", "True", "yes"}:
            continue
        start = clean(row.get("start_date"))
        end = clean(row.get("end_date")) or start
        if start and end:
            dates.update(date_range(start, end))
    # 考研无忧产品公共规则：10/10 按不可排处理。
    dates.add("2026-10-10")
    return dates


def load_room_meta(data_dir: Path) -> Dict[str, dict]:
    return load_raw_room_metadata(data_dir)


def load_area_meta(data_dir: Path) -> Dict[str, dict]:
    path = data_dir / "teaching_areas.csv"
    if not path.exists():
        return {}
    return {clean(row.get("id")): row for row in read_csv_rows(path) if clean(row.get("id"))}


def load_area_links(data_dir: Path) -> Dict[Tuple[str, str], dict]:
    path = data_dir / "teaching_area_links.csv"
    if not path.exists():
        return {}
    links: Dict[Tuple[str, str], dict] = {}
    for row in read_csv_rows(path):
        left = clean(row.get("from_teaching_area_id"))
        right = clean(row.get("to_teaching_area_id"))
        if left and right:
            links[(left, right)] = row
            links[(right, left)] = row
    return links


def row_teacher_key(row: dict) -> str:
    return clean(row.get("teacher_id")) or clean(row.get("teacher_name"))


def block_key(row: dict) -> Tuple[str, str, str, str, str, str]:
    return (
        clean(row.get("class_id")),
        clean(row.get("date")),
        clean(row.get("period")),
        clean(row.get("subject")),
        row_teacher_key(row),
        clean(row.get("room_id")),
    )


def build_blocks(rows: Sequence[dict], class_meta: Dict[str, dict]) -> List[Block]:
    grouped: Dict[Tuple[str, str, str, str, str, str], List[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        if clean(row.get("subject")) not in PUBLIC_SUBJECTS:
            continue
        if clean(row.get("period")) not in {"AM", "PM", "EVENING"}:
            continue
        grouped[block_key(row)].append(index)

    blocks: List[Block] = []
    for key, indices in grouped.items():
        indices = sorted(indices, key=lambda idx: (clean(rows[idx].get("lesson_slot")), clean(rows[idx].get("start_time"))))
        first = rows[indices[0]]
        class_id = clean(first.get("class_id"))
        meta = class_meta.get(class_id, {})
        blocks.append(
            Block(
                key=key,
                indices=tuple(indices),
                class_id=class_id,
                suite_code=clean(meta.get("suite_code")),
                sub_product=clean(meta.get("sub_product")),
                subject=clean(first.get("subject")),
                stage=clean(first.get("stage")),
                date=clean(first.get("date")),
                week=week_start(clean(first.get("date"))),
                period=clean(first.get("period")),
                teacher_key=row_teacher_key(first),
                teacher_name=clean(first.get("teacher_name")),
                room_id=clean(first.get("room_id")),
                room_name=clean(first.get("room_name")),
                hours=sum(float(rows[idx].get("duration_hours") or 0) for idx in indices),
            )
        )
    return blocks


def period_window_key(date_text: str, period: str) -> Tuple[str, int]:
    return date_text, PERIOD_ORDER.get(period, 9)


def target_period_in_constraint(date_text: str, period: str, start: str, start_period: str, end: str, end_period: str) -> bool:
    if start and period_window_key(date_text, period) < period_window_key(start, start_period or "AM"):
        return False
    if end and period_window_key(date_text, period) > period_window_key(end, end_period or "EVENING"):
        return False
    return True


def constraint_matches_date(constraint: ClassWindowConstraint, date_text: str) -> bool:
    if constraint.earliest_date and date_text < constraint.earliest_date:
        return False
    if constraint.latest_date and date_text > constraint.latest_date:
        return False
    return True


def window_constraint_for_block(
    block: Block,
    window_constraints: Dict[str, object],
) -> Optional[ClassWindowConstraint]:
    raw_constraints = window_constraints.get(block.class_id)
    if not raw_constraints:
        raw_constraints = window_constraints.get(block.suite_code)
    if not raw_constraints:
        return None
    constraints = raw_constraints if isinstance(raw_constraints, list) else [raw_constraints]
    matching = [constraint for constraint in constraints if constraint_matches_date(constraint, block.date)]
    if matching:
        return matching[0] if len(matching) == 1 else merge_constraints(matching)
    return constraints[0] if len(constraints) == 1 else merge_constraints(constraints)


def block_window(block: Block, class_meta: Dict[str, dict], window_constraints: Dict[str, object]) -> Tuple[str, str, str, str]:
    meta = class_meta.get(block.class_id, {})
    start = clean(meta.get("start_date")) or "2026-06-25"
    start_period = clean(meta.get("start_period")) or "AM"
    end = clean(meta.get("end_date")) or "2026-12-13"
    end_period = clean(meta.get("end_period")) or "EVENING"
    constraint = window_constraint_for_block(block, window_constraints)
    if constraint:
        start = max(start, clean(getattr(constraint, "earliest_date", "")) or start)
        start_period = clean(getattr(constraint, "earliest_period", "")) or start_period
        end = min(end, clean(getattr(constraint, "latest_date", "")) or end)
        end_period = clean(getattr(constraint, "latest_period", "")) or end_period
    if "2026-07-01" <= block.date <= "2026-08-31":
        if not constraint:
            start = max(start, "2026-07-01")
            end = min(end, "2026-08-31")
        if block.sub_product in {"无忧秋", "无忧春"}:
            start = max(start, "2026-07-04")
            start_period = "AM"
        if block.sub_product == "无忧暑":
            start = max(start, "2026-07-01")
    return start, start_period, end, end_period


def stage_rank(block: Block, class_meta: Dict[str, dict]) -> Optional[int]:
    order = STAGE_ORDERS.get(block.sub_product, {})
    if block.stage in order:
        return order[block.stage]
    quarter = clean(class_meta.get(block.class_id, {}).get("quarter"))
    if quarter in order:
        return order[quarter]
    return None


def preserves_stage_order(rows: Sequence[dict], block: Block, target_date: str, class_meta: Dict[str, dict]) -> bool:
    rank = stage_rank(block, class_meta)
    if rank is None:
        return True
    ignored = set(block.indices)
    order = STAGE_ORDERS.get(block.sub_product, {})
    for index, row in enumerate(rows):
        if index in ignored:
            continue
        if clean(row.get("class_id")) != block.class_id or clean(row.get("subject")) != block.subject:
            continue
        other_stage = clean(row.get("stage"))
        if other_stage not in order:
            continue
        other_rank = order[other_stage]
        other_date = clean(row.get("date"))
        if other_rank < rank and target_date < other_date:
            return False
        if other_rank > rank and target_date > other_date:
            return False
    return True


def target_slots_for_block(block: Block, target_period: str) -> Optional[List[Tuple[str, str, str, str]]]:
    slots = PERIOD_SLOTS.get(target_period, [])
    if len(block.indices) > len(slots):
        return None
    return slots[: len(block.indices)]


def build_occupancy(
    rows: Sequence[dict],
    class_conflicts: Dict[str, Set[str]],
    ignore_indices: Set[int],
) -> dict:
    class_period: Set[Tuple[str, str, str]] = set()
    group_period: Set[Tuple[str, str, str]] = set()
    teacher_period_rooms: Dict[Tuple[str, str, str], Set[str]] = defaultdict(set)
    room_period_rows: Dict[Tuple[str, str, str], List[dict]] = defaultdict(list)
    class_subject_dates: Set[Tuple[str, str, str]] = set()
    for index, row in enumerate(rows):
        if index in ignore_indices:
            continue
        class_id = clean(row.get("class_id"))
        date_text = clean(row.get("date"))
        period = clean(row.get("period"))
        subject = clean(row.get("subject"))
        if not class_id or not date_text or not period:
            continue
        class_period.add((class_id, date_text, period))
        if subject:
            class_subject_dates.add((class_id, subject, date_text))
        for group_id in class_conflicts.get(class_id, set()):
            group_period.add((group_id, date_text, period))
        teacher = row_teacher_key(row)
        if teacher:
            teacher_period_rooms[(teacher, date_text, period)].add(clean(row.get("room_id")))
        room_id = clean(row.get("room_id"))
        if room_id:
            room_period_rows[(room_id, date_text, period)].append(row)
    return {
        "class_period": class_period,
        "group_period": group_period,
        "teacher_period_rooms": teacher_period_rooms,
        "room_period_rows": room_period_rows,
        "class_subject_dates": class_subject_dates,
    }


def valid_target(
    rows: Sequence[dict],
    block: Block,
    target_date: str,
    target_period: str,
    class_meta: Dict[str, dict],
    class_conflicts: Dict[str, Set[str]],
    window_constraints: Dict[str, object],
    blackout_dates: Set[str],
) -> bool:
    if target_slots_for_block(block, target_period) is None:
        return False
    if target_date in blackout_dates:
        return False
    if "2026-07-01" <= target_date <= "2026-08-31" and Date.fromisoformat(target_date).weekday() == 6:
        return False
    start, start_period, end, end_period = block_window(block, class_meta, window_constraints)
    if not target_period_in_constraint(target_date, target_period, start, start_period, end, end_period):
        return False
    meta = class_meta.get(block.class_id, {})
    if clean(meta.get("start_date")) and period_window_key(target_date, target_period) < period_window_key(clean(meta.get("start_date")), clean(meta.get("start_period")) or "AM"):
        return False
    if clean(meta.get("end_date")) and period_window_key(target_date, target_period) > period_window_key(clean(meta.get("end_date")), clean(meta.get("end_period")) or "EVENING"):
        return False
    if not preserves_stage_order(rows, block, target_date, class_meta):
        return False

    occupancy = build_occupancy(rows, class_conflicts, set(block.indices))
    if (block.class_id, target_date, target_period) in occupancy["class_period"]:
        return False
    if (block.class_id, block.subject, target_date) in occupancy["class_subject_dates"]:
        return False
    for group_id in class_conflicts.get(block.class_id, set()):
        if (group_id, target_date, target_period) in occupancy["group_period"]:
            return False
    if block.teacher_key:
        existing_rooms = occupancy["teacher_period_rooms"].get((block.teacher_key, target_date, target_period), set())
        if existing_rooms and (len(existing_rooms) > 1 or block.room_id not in existing_rooms):
            return False
    if block.room_id:
        if occupancy["room_period_rows"].get((block.room_id, target_date, target_period)):
            return False
    return True


def move_block(rows: List[dict], block: Block, target_date: str, target_period: str) -> None:
    slots = target_slots_for_block(block, target_period)
    if slots is None:
        raise ValueError(f"目标时段 {target_period} 容纳不了 {len(block.indices)} 条 2h 课")
    sorted_indices = sorted(block.indices, key=lambda idx: (clean(rows[idx].get("lesson_slot")), clean(rows[idx].get("start_time"))))
    for index, (slot_id, slot_label, start_time, end_time) in zip(sorted_indices, slots):
        rows[index]["date"] = target_date
        rows[index]["weekday"] = weekday_label(target_date)
        rows[index]["period"] = target_period
        rows[index]["lesson_slot"] = slot_id
        rows[index]["slot_label"] = slot_label
        rows[index]["start_time"] = start_time
        rows[index]["end_time"] = end_time


def suite_subject_week_counts(blocks: Sequence[Block]) -> Counter[Tuple[str, str, str]]:
    counts: Counter[Tuple[str, str, str]] = Counter()
    for block in blocks:
        if block.subject in PUBLIC_SUBJECTS and block.suite_code:
            counts[(block.suite_code, block.subject, block.week)] += 1
    return counts


def suite_week_counts(blocks: Sequence[Block]) -> Counter[Tuple[str, str]]:
    counts: Counter[Tuple[str, str]] = Counter()
    for block in blocks:
        if block.subject in PUBLIC_SUBJECTS and block.suite_code:
            counts[(block.suite_code, block.week)] += 1
    return counts


def active_weeks_for_suite(blocks: Sequence[Block], suite_code: str, start: str, end: str) -> List[str]:
    weeks = sorted({block.week for block in blocks if block.suite_code == suite_code and start <= block.date <= end})
    return weeks


def suite_subject_values(blocks: Sequence[Block], suite_code: str, subject: str, start: str, end: str) -> Dict[str, int]:
    weeks = active_weeks_for_suite(blocks, suite_code, start, end)
    counts = suite_subject_week_counts([block for block in blocks if start <= block.date <= end])
    return {week: counts.get((suite_code, subject, week), 0) for week in weeks}


def room_area(room_id: str, room_meta: Dict[str, dict], area_meta: Dict[str, dict]) -> Tuple[str, str, str]:
    room = room_meta.get(room_id, {})
    area_id = clean(room.get("teaching_area_id"))
    area = area_meta.get(area_id, {})
    return area_id, clean(area.get("short_name")) or clean(room.get("teaching_area_name")) or area_id, clean(area.get("region_tag"))


def travel_risk_between(
    left_room: str,
    right_room: str,
    room_meta: Dict[str, dict],
    area_meta: Dict[str, dict],
    area_links: Dict[Tuple[str, str], dict],
) -> Tuple[int, float, str]:
    left_area, _left_name, left_region = room_area(left_room, room_meta, area_meta)
    right_area, _right_name, right_region = room_area(right_room, room_meta, area_meta)
    if not left_area or not right_area or left_area == right_area:
        return 0, 0, "same_area"
    link = area_links.get((left_area, right_area), {})
    relation = clean(link.get("relation_type"))
    try:
        minutes = float(clean(link.get("travel_minutes")) or 0)
    except ValueError:
        minutes = 0
    if (left_region, right_region) in FAR_REGION_PAIRS or "不建议" in relation or minutes >= 35:
        return 3, minutes, relation or "far"
    if left_region and right_region and left_region != right_region:
        return 2, minutes, relation or "cross_region"
    if minutes > 0:
        return 1, minutes, relation or "near"
    return 0, minutes, relation or ""


def teacher_day_travel_score(
    rows: Sequence[dict],
    teacher_key: str,
    date_text: str,
    room_meta: Dict[str, dict],
    area_meta: Dict[str, dict],
    area_links: Dict[Tuple[str, str], dict],
) -> int:
    by_period: Dict[str, Set[str]] = defaultdict(set)
    for row in rows:
        if row_teacher_key(row) != teacher_key or clean(row.get("date")) != date_text:
            continue
        room_id = clean(row.get("room_id"))
        if room_id:
            by_period[clean(row.get("period"))].add(room_id)
    periods = sorted(by_period, key=lambda item: PERIOD_ORDER.get(item, 9))
    score = 0
    for left, right in zip(periods, periods[1:]):
        if PERIOD_ORDER.get(right, 9) - PERIOD_ORDER.get(left, 9) != 1:
            continue
        for left_room in by_period[left]:
            for right_room in by_period[right]:
                risk, minutes, _relation = travel_risk_between(left_room, right_room, room_meta, area_meta, area_links)
                if risk >= 3:
                    score += 10 + int(minutes)
                elif risk == 2:
                    score += 4 + int(minutes // 10)
                elif risk == 1:
                    score += 1
    return score


def candidate_score(
    rows: Sequence[dict],
    block: Block,
    target_date: str,
    target_period: str,
    class_meta: Dict[str, dict],
    room_meta: Dict[str, dict],
    area_meta: Dict[str, dict],
    area_links: Dict[Tuple[str, str], dict],
) -> int:
    blocks = build_blocks(rows, class_meta)
    subject_values = suite_subject_values(blocks, block.suite_code, block.subject, "2026-07-01", "2026-12-13")
    target_week = week_start(target_date)
    target_subject_count = subject_values.get(target_week, 0)
    suite_totals = suite_week_counts(blocks)
    target_total_count = suite_totals.get((block.suite_code, target_week), 0)
    travel_after = teacher_day_travel_score(rows, block.teacher_key, target_date, room_meta, area_meta, area_links)
    original_date = Date.fromisoformat(block.date)
    distance_days = abs((Date.fromisoformat(target_date) - original_date).days)
    preferred_period = {"数学": "AM", "英语": "PM", "政治": "PM"}.get(block.subject)
    return (
        target_subject_count * 20
        + target_total_count * 8
        + travel_after * 2
        + (4 if preferred_period and target_period != preferred_period else 0)
        + distance_days
    )


def try_move_to_best_target(
    rows: List[dict],
    block: Block,
    target_weeks: Sequence[str],
    class_meta: Dict[str, dict],
    class_conflicts: Dict[str, Set[str]],
    window_constraints: Dict[str, object],
    blackout_dates: Set[str],
    room_meta: Dict[str, dict],
    area_meta: Dict[str, dict],
    area_links: Dict[Tuple[str, str], dict],
    periods: Sequence[str] = ("AM", "PM"),
) -> Optional[Tuple[str, str, int]]:
    candidates: List[Tuple[int, str, str]] = []
    for week in target_weeks:
        for date_text in week_dates(week):
            for period in periods:
                if not valid_target(rows, block, date_text, period, class_meta, class_conflicts, window_constraints, blackout_dates):
                    continue
                score = candidate_score(rows, block, date_text, period, class_meta, room_meta, area_meta, area_links)
                candidates.append((score, date_text, period))
    if not candidates:
        return None
    candidates.sort()
    score, date_text, period = candidates[0]
    move_block(rows, block, date_text, period)
    return date_text, period, score


def same_teacher_8h_hotspots(rows: Sequence[dict], class_meta: Dict[str, dict]) -> List[Tuple[float, Tuple[str, str, str, str], List[Block]]]:
    blocks = build_blocks(rows, class_meta)
    by_day: Dict[Tuple[str, str, str, str], List[Block]] = defaultdict(list)
    for block in blocks:
        if block.teacher_key and block.subject in PUBLIC_SUBJECTS:
            by_day[(block.class_id, block.subject, block.teacher_key, block.date)].append(block)
    hot = [
        (sum(block.hours for block in items), key, items)
        for key, items in by_day.items()
        if sum(block.hours for block in items) >= 8
    ]
    hot.sort(reverse=True, key=lambda item: (item[0], item[1][3], item[1][0], item[1][1]))
    return hot


def repair_chain_same_teacher_8h(
    rows: List[dict],
    class_meta: Dict[str, dict],
    class_conflicts: Dict[str, Set[str]],
    window_constraints: Dict[str, object],
    blackout_dates: Set[str],
    room_meta: Dict[str, dict],
    area_meta: Dict[str, dict],
    area_links: Dict[Tuple[str, str], dict],
    max_moves: int,
) -> List[str]:
    """Free a same-suite slot first, then move one halfday from an 8h hotspot into it."""
    lines: List[str] = []
    failed_hotspots: Set[Tuple[str, str, str, str]] = set()
    for _ in range(max_moves):
        hot = same_teacher_8h_hotspots(rows, class_meta)
        if not hot:
            break
        moved = False
        for _hours, (class_id, subject, teacher_key, date_text), items in hot:
            hot_key = (class_id, subject, teacher_key, date_text)
            if hot_key in failed_hotspots:
                continue
            hot_blocks = sorted(
                items,
                key=lambda block: (PERIOD_ORDER.get(block.period, 9), block.stage, block.date),
                reverse=True,
            )
            all_blocks = build_blocks(rows, class_meta)
            for hot_block in hot_blocks:
                start, start_period, end, end_period = block_window(hot_block, class_meta, window_constraints)
                candidate_blockers = [
                    block
                    for block in all_blocks
                    if block.suite_code == hot_block.suite_code
                    and block.class_id != hot_block.class_id
                    and block.subject in PUBLIC_SUBJECTS
                    and block.subject != hot_block.subject
                    and block.period in {"AM", "PM"}
                    and target_period_in_constraint(block.date, block.period, start, start_period, end, end_period)
                    and block.date != hot_block.date
                ]
                candidate_blockers.sort(
                    key=lambda block: (
                        abs((Date.fromisoformat(block.date) - Date.fromisoformat(hot_block.date)).days),
                        PERIOD_ORDER.get(block.period, 9),
                        block.subject,
                        block.class_id,
                    )
                )
                for blocker in candidate_blockers:
                    snapshot = [dict(row) for row in rows]
                    active_weeks = active_weeks_for_suite(all_blocks, blocker.suite_code, "2026-07-01", "2026-12-13")
                    current_week = blocker.week
                    target_weeks = sorted(
                        [week for week in active_weeks if week != current_week],
                        key=lambda week: (
                            suite_subject_values(all_blocks, blocker.suite_code, blocker.subject, "2026-07-01", "2026-12-13").get(week, 0),
                            abs((Date.fromisoformat(week) - Date.fromisoformat(current_week)).days),
                            week,
                        ),
                    )
                    if not target_weeks:
                        continue
                    blocker_move = try_move_to_best_target(
                        rows,
                        blocker,
                        target_weeks[:8],
                        class_meta,
                        class_conflicts,
                        window_constraints,
                        blackout_dates,
                        room_meta,
                        area_meta,
                        area_links,
                    )
                    if not blocker_move:
                        rows[:] = snapshot
                        continue
                    if not valid_target(
                        rows,
                        hot_block,
                        blocker.date,
                        blocker.period,
                        class_meta,
                        class_conflicts,
                        window_constraints,
                        blackout_dates,
                    ):
                        rows[:] = snapshot
                        continue
                    move_block(rows, hot_block, blocker.date, blocker.period)
                    target_date, target_period, _score = blocker_move
                    lines.append(
                        f"同班同科同老师同日8小时连锁修复: 先挪 {blocker.class_id} {blocker.subject} "
                        f"{blocker.teacher_name or blocker.teacher_key} {blocker.date} {blocker.period} -> "
                        f"{target_date} {target_period}；再挪 {hot_block.class_id} {subject} "
                        f"{hot_block.teacher_name or hot_block.teacher_key} {hot_block.date} {hot_block.period} -> "
                        f"{blocker.date} {blocker.period}"
                    )
                    moved = True
                    break
                if moved:
                    break
            if moved:
                break
            failed_hotspots.add(hot_key)
        if not moved:
            break
    return lines


def repair_same_teacher_8h(
    rows: List[dict],
    class_meta: Dict[str, dict],
    class_conflicts: Dict[str, Set[str]],
    window_constraints: Dict[str, object],
    blackout_dates: Set[str],
    room_meta: Dict[str, dict],
    area_meta: Dict[str, dict],
    area_links: Dict[Tuple[str, str], dict],
    max_moves: int,
) -> List[str]:
    lines: List[str] = []
    for _ in range(max_moves):
        blocks = build_blocks(rows, class_meta)
        hot = same_teacher_8h_hotspots(rows, class_meta)
        if not hot:
            break
        moved = False
        for _hours, (_class_id, subject, _teacher, date_text), items in hot:
            items = sorted(items, key=lambda block: (PERIOD_ORDER.get(block.period, 9), block.stage), reverse=True)
            suite_code = items[0].suite_code
            subject_counts = suite_subject_values(blocks, suite_code, subject, "2026-07-01", "2026-12-13")
            current_week = week_start(date_text)
            target_weeks = [
                week
                for week, count in sorted(subject_counts.items(), key=lambda pair: (pair[1], pair[0]))
                if week != current_week and count <= max(1, min(subject_counts.values() or [0]) + 1)
            ]
            if not target_weeks:
                target_weeks = [week for week in sorted(subject_counts) if week != current_week]
            for block in items:
                result = try_move_to_best_target(
                    rows,
                    block,
                    target_weeks,
                    class_meta,
                    class_conflicts,
                    window_constraints,
                    blackout_dates,
                    room_meta,
                    area_meta,
                    area_links,
                )
                if result:
                    target_date, target_period, _score = result
                    lines.append(
                        f"同班同科同老师同日8小时修复: {block.class_id} {subject} {block.teacher_name or block.teacher_key} "
                        f"{block.date} {block.period} -> {target_date} {target_period}"
                    )
                    moved = True
                    break
            if moved:
                break
        if not moved:
            break
    return lines


def repair_week_balance(
    rows: List[dict],
    class_meta: Dict[str, dict],
    class_conflicts: Dict[str, Set[str]],
    window_constraints: Dict[str, object],
    blackout_dates: Set[str],
    room_meta: Dict[str, dict],
    area_meta: Dict[str, dict],
    area_links: Dict[Tuple[str, str], dict],
    target_suites: Set[str],
    max_moves: int,
) -> List[str]:
    lines: List[str] = []
    for _ in range(max_moves):
        blocks = [
            block
            for block in build_blocks(rows, class_meta)
            if block.suite_code in target_suites
            and block.subject in PUBLIC_SUBJECTS
            and "2026-07-01" <= block.date <= "2026-08-31"
            and block.period in {"AM", "PM"}
        ]
        by_suite_subject: Dict[Tuple[str, str], Dict[str, int]] = defaultdict(dict)
        for block in blocks:
            by_suite_subject[(block.suite_code, block.subject)][block.week] = by_suite_subject[(block.suite_code, block.subject)].get(block.week, 0) + 1
        problems: List[Tuple[int, str, str, str, str, int, int]] = []
        for (suite_code, subject), counts in by_suite_subject.items():
            if len(counts) < 3:
                continue
            max_week, max_value = max(counts.items(), key=lambda item: (item[1], item[0]))
            min_week, min_value = min(counts.items(), key=lambda item: (item[1], item[0]))
            diff = max_value - min_value
            if diff >= 3:
                problems.append((diff, suite_code, subject, max_week, min_week, max_value, min_value))
        if not problems:
            break
        problems.sort(reverse=True)
        moved = False
        for diff, suite_code, subject, over_week, under_week, max_value, min_value in problems:
            source_blocks = [
                block
                for block in blocks
                if block.suite_code == suite_code and block.subject == subject and block.week == over_week
            ]
            source_blocks.sort(
                key=lambda block: (
                    block.date,
                    PERIOD_ORDER.get(block.period, 9),
                    block.class_id,
                ),
                reverse=True,
            )
            for block in source_blocks:
                result = try_move_to_best_target(
                    rows,
                    block,
                    [under_week],
                    class_meta,
                    class_conflicts,
                    window_constraints,
                    blackout_dates,
                    room_meta,
                    area_meta,
                    area_links,
                )
                if result:
                    target_date, target_period, _score = result
                    lines.append(
                        f"周课量均衡修复: 套班{suite_code} {subject} "
                        f"{block.date} {block.period}({over_week}周 {max_value}) -> "
                        f"{target_date} {target_period}({under_week}周 {min_value})，原差值 {diff}"
                    )
                    moved = True
                    break
            if moved:
                break
        if not moved:
            break
    return lines


def repair_teacher_same_region_packing(
    rows: List[dict],
    class_meta: Dict[str, dict],
    class_conflicts: Dict[str, Set[str]],
    window_constraints: Dict[str, object],
    blackout_dates: Set[str],
    room_meta: Dict[str, dict],
    area_meta: Dict[str, dict],
    target_teachers: Set[str],
    start_date: str,
    end_date: str,
    max_moves: int,
) -> List[str]:
    lines: List[str] = []
    if not target_teachers or max_moves <= 0:
        return lines
    for _ in range(max_moves):
        blocks = build_blocks(rows, class_meta)
        by_teacher_day: Dict[Tuple[str, str], List[Block]] = defaultdict(list)
        teacher_names: Dict[str, str] = {}
        for block in blocks:
            if block.subject not in PUBLIC_SUBJECTS or block.period not in {"AM", "PM"}:
                continue
            if not (start_date <= block.date <= end_date):
                continue
            if block.teacher_key not in target_teachers and block.teacher_name not in target_teachers:
                continue
            by_teacher_day[(block.teacher_key, block.date)].append(block)
            teacher_names.setdefault(block.teacher_key, block.teacher_name or block.teacher_key)

        candidates: List[Tuple[int, int, int, str, str, str, Block, str, str, str, str]] = []
        for (teacher_key, source_date), source_day_blocks in by_teacher_day.items():
            source_periods = {block.period for block in source_day_blocks}
            if len(source_periods) != 1:
                continue
            for source in source_day_blocks:
                source_area, source_area_name, source_region = room_area(source.room_id, room_meta, area_meta)
                if not source_area:
                    continue
                for (target_teacher, target_date), target_day_blocks in by_teacher_day.items():
                    if target_teacher != teacher_key or target_date == source_date:
                        continue
                    target_periods = {block.period for block in target_day_blocks}
                    for target_period in ("AM", "PM"):
                        if target_period in target_periods:
                            continue
                        same_area = False
                        same_region = False
                        target_area_name = ""
                        target_region = ""
                        for target_block in target_day_blocks:
                            target_area, area_name, region = room_area(target_block.room_id, room_meta, area_meta)
                            if target_area and target_area == source_area:
                                same_area = True
                                target_area_name = area_name
                                target_region = region
                            if region and source_region and region == source_region:
                                same_region = True
                                target_area_name = target_area_name or area_name
                                target_region = target_region or region
                        if not (same_area or same_region):
                            continue
                        if not valid_target(
                            rows,
                            source,
                            target_date,
                            target_period,
                            class_meta,
                            class_conflicts,
                            window_constraints,
                            blackout_dates,
                        ):
                            continue
                        distance = abs((Date.fromisoformat(target_date) - Date.fromisoformat(source.date)).days)
                        candidates.append(
                            (
                                0 if same_area else 1,
                                distance,
                                PERIOD_ORDER.get(target_period, 9),
                                teacher_names.get(teacher_key, teacher_key),
                                source.date,
                                source.period,
                                source,
                                target_date,
                                target_period,
                                source_area_name,
                                target_area_name or source_area_name,
                                target_region or source_region,
                            )
                        )
        if not candidates:
            break
        candidates.sort()
        relation_rank, _distance, _period_rank, teacher_name, source_date, source_period, source, target_date, target_period, source_area_name, target_area_name, target_region = candidates[0]
        move_block(rows, source, target_date, target_period)
        relation = "同校区" if relation_rank == 0 else "同区域"
        lines.append(
            f"老师同区域合并: {teacher_name} {source.class_id} {source.subject} "
            f"{source_date} {source_period}({source_area_name}) -> {target_date} {target_period}({target_area_name}/{target_region})，{relation}合并"
        )
    return lines


def travel_events(
    rows: Sequence[dict],
    room_meta: Dict[str, dict],
    area_meta: Dict[str, dict],
    area_links: Dict[Tuple[str, str], dict],
) -> List[dict]:
    by_teacher_day_period: Dict[Tuple[str, str, str], Set[str]] = defaultdict(set)
    teacher_names: Dict[str, str] = {}
    for row in rows:
        teacher = row_teacher_key(row)
        if not teacher:
            continue
        date_text = clean(row.get("date"))
        period = clean(row.get("period"))
        room_id = clean(row.get("room_id"))
        if not date_text or not period or not room_id:
            continue
        by_teacher_day_period[(teacher, date_text, period)].add(room_id)
        teacher_names.setdefault(teacher, clean(row.get("teacher_name")) or teacher)
    events: List[dict] = []
    teacher_days = sorted({(teacher, date_text) for teacher, date_text, _period in by_teacher_day_period})
    for teacher, date_text in teacher_days:
        periods = sorted(
            [period for key_teacher, key_date, period in by_teacher_day_period if key_teacher == teacher and key_date == date_text],
            key=lambda item: PERIOD_ORDER.get(item, 9),
        )
        for left, right in zip(periods, periods[1:]):
            if PERIOD_ORDER.get(right, 9) - PERIOD_ORDER.get(left, 9) != 1:
                continue
            worst = (0, 0.0, "", "", "")
            for left_room in by_teacher_day_period[(teacher, date_text, left)]:
                for right_room in by_teacher_day_period[(teacher, date_text, right)]:
                    risk, minutes, relation = travel_risk_between(left_room, right_room, room_meta, area_meta, area_links)
                    if risk > worst[0] or (risk == worst[0] and minutes > worst[1]):
                        worst = (risk, minutes, relation, left_room, right_room)
            if worst[0] >= 3:
                events.append(
                    {
                        "teacher": teacher,
                        "teacher_name": teacher_names.get(teacher, teacher),
                        "date": date_text,
                        "left_period": left,
                        "right_period": right,
                        "risk": worst[0],
                        "minutes": worst[1],
                        "left_room": worst[3],
                        "right_room": worst[4],
                    }
                )
    teacher_high_risk_counts = Counter(row["teacher"] for row in events if row["risk"] >= 3)
    events.sort(
        key=lambda row: (
            -teacher_high_risk_counts[row["teacher"]],
            -row["risk"],
            -row["minutes"],
            row["teacher_name"],
            row["date"],
        )
    )
    return events


def repair_teacher_travel(
    rows: List[dict],
    class_meta: Dict[str, dict],
    class_conflicts: Dict[str, Set[str]],
    window_constraints: Dict[str, object],
    blackout_dates: Set[str],
    room_meta: Dict[str, dict],
    area_meta: Dict[str, dict],
    area_links: Dict[Tuple[str, str], dict],
    max_moves: int,
    target_teachers: Optional[Set[str]] = None,
) -> List[str]:
    lines: List[str] = []
    for _ in range(max_moves):
        events = travel_events(rows, room_meta, area_meta, area_links)
        if target_teachers:
            events = [
                event
                for event in events
                if event["teacher"] in target_teachers or event["teacher_name"] in target_teachers
            ]
        if not events:
            break
        moved = False
        for event in events[:60]:
            teacher = event["teacher"]
            date_text = event["date"]
            periods = [event["right_period"], event["left_period"]]
            blocks = [
                block
                for block in build_blocks(rows, class_meta)
                if block.teacher_key == teacher
                and block.date == date_text
                and block.period in periods
                and block.subject in PUBLIC_SUBJECTS
                and block.sub_product not in {"无忧秋", "无忧春"}  # 秋季周末课先不自动挪，避免破坏 ERP 手调节奏。
            ]
            blocks.sort(key=lambda block: (block.period != event["right_period"], block.sub_product, block.suite_code))
            before_score = teacher_day_travel_score(rows, teacher, date_text, room_meta, area_meta, area_links)
            for block in blocks:
                active_weeks = active_weeks_for_suite(build_blocks(rows, class_meta), block.suite_code, "2026-07-01", "2026-12-13")
                if not active_weeks:
                    continue
                current_week = block.week
                nearby_weeks = sorted(
                    [week for week in active_weeks if week != current_week],
                    key=lambda week: abs((Date.fromisoformat(week) - Date.fromisoformat(current_week)).days),
                )[:4]
                trial_targets = nearby_weeks or [current_week]
                snapshot = [dict(row) for row in rows]
                result = try_move_to_best_target(
                    rows,
                    block,
                    trial_targets,
                    class_meta,
                    class_conflicts,
                    window_constraints,
                    blackout_dates,
                    room_meta,
                    area_meta,
                    area_links,
                )
                if not result:
                    rows[:] = snapshot
                    continue
                target_date, target_period, _score = result
                after_original_day = teacher_day_travel_score(rows, teacher, date_text, room_meta, area_meta, area_links)
                after_target_day = teacher_day_travel_score(rows, teacher, target_date, room_meta, area_meta, area_links)
                if after_original_day + after_target_day >= before_score:
                    rows[:] = snapshot
                    continue
                lines.append(
                    f"老师跨区域优化: {event['teacher_name']} {block.class_id} {block.subject} "
                    f"{block.date} {block.period} -> {target_date} {target_period}，"
                    f"原日跨区评分 {before_score} -> {after_original_day}+{after_target_day}"
                )
                moved = True
                break
            if moved:
                break
        if not moved:
            break
    return lines


def target_suites_from_quality(path: Path) -> Set[str]:
    suites: Set[str] = set()
    if not path.exists():
        return suites
    for row in read_csv_rows(path):
        if clean(row.get("severity")) not in {"high", "medium"}:
            continue
        if clean(row.get("scope_type")) == "suite":
            suites.add(clean(row.get("scope_id")))
    return suites


def regenerate_outputs(rows: Sequence[dict], data_dir: Path, output_dir: Path) -> None:
    class_metadata = load_class_metadata(data_dir)
    window_constraints = load_window_constraints(data_dir)
    room_names = load_room_names(data_dir)
    assignments = assignments_from_rows(rows, "QUALITY_REPAIR")
    write_day_table_html(
        assignments,
        output_dir / "batch_schedule_maintenance.html",
        "27考研公共课课表维护页",
        ["AM", "PM", "EVENING"],
        room_names,
        "2026-06-25",
        "2026-12-13",
        class_metadata,
        window_constraints,
    )
    shutil.copy2(output_dir / "batch_schedule_maintenance.html", output_dir / "summer_camp_schedule.html")
    write_teacher_time_conflicts_csv(assignments, output_dir / "teacher_time_conflicts.csv", room_names)


def append_report(report_path: Path, lines: Sequence[str], timestamp: str) -> None:
    with report_path.open("a", encoding="utf-8") as handle:
        handle.write("\n\n")
        handle.write(f"## 质量热点局部优化 {timestamp}\n")
        for line in lines:
            handle.write(f"- {line}\n")


def parse_name_set(value: str) -> Set[str]:
    return {item.strip() for item in value.split(",") if item.strip()}


def main() -> None:
    parser = argparse.ArgumentParser(description="针对低分和高优先级排课质量问题做局部优化")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--schedule-csv", type=Path, default=Path("outputs/batch_schedule_maintenance.csv"))
    parser.add_argument("--quality-issues", type=Path, default=Path("outputs/schedule_quality_issues_20260526_2102.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--timestamp", default="")
    parser.add_argument("--chain-moves", type=int, default=6)
    parser.add_argument("--same-day-moves", type=int, default=12)
    parser.add_argument("--same-region-teachers", default="", help="逗号分隔，只对这些老师做同校区/同区域合并")
    parser.add_argument("--same-region-moves", type=int, default=0)
    parser.add_argument("--travel-teachers", default="", help="逗号分隔，只对这些老师做跨区域优化")
    parser.add_argument("--target-suites", default="", help="逗号分隔，只对这些套班做周课量均衡")
    parser.add_argument("--week-balance-moves", type=int, default=80)
    parser.add_argument("--travel-moves", type=int, default=24)
    parser.add_argument("--date-start", default="2026-07-01")
    parser.add_argument("--date-end", default="2026-12-13")
    args = parser.parse_args()

    timestamp = args.timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    rows = read_csv_rows(args.schedule_csv)
    original_rows = [dict(row) for row in rows]
    class_meta = load_class_metadata(args.data_dir)
    class_conflicts = load_class_conflicts(args.data_dir / "class_conflict_groups.csv")
    window_constraints = load_window_constraints(args.data_dir)
    blackout_dates = load_blackout_dates(args.data_dir / "global_blackout_dates.csv")
    room_meta = load_room_meta(args.data_dir)
    area_meta = load_area_meta(args.data_dir)
    area_links = load_area_links(args.data_dir)

    target_suites = parse_name_set(args.target_suites)
    if not target_suites:
        target_suites = target_suites_from_quality(args.quality_issues)
        target_suites.update({"2712", "2754", "2791", "2792", "2793", "2731", "2774"})
    same_region_teachers = parse_name_set(args.same_region_teachers)
    travel_teachers = parse_name_set(args.travel_teachers)

    report_lines: List[str] = []
    report_lines.extend(
        repair_teacher_same_region_packing(
            rows,
            class_meta,
            class_conflicts,
            window_constraints,
            blackout_dates,
            room_meta,
            area_meta,
            same_region_teachers,
            args.date_start,
            args.date_end,
            args.same_region_moves,
        )
    )
    report_lines.extend(
        repair_chain_same_teacher_8h(
            rows,
            class_meta,
            class_conflicts,
            window_constraints,
            blackout_dates,
            room_meta,
            area_meta,
            area_links,
            args.chain_moves,
        )
    )
    report_lines.extend(
        repair_same_teacher_8h(
            rows,
            class_meta,
            class_conflicts,
            window_constraints,
            blackout_dates,
            room_meta,
            area_meta,
            area_links,
            args.same_day_moves,
        )
    )
    report_lines.extend(
        repair_week_balance(
            rows,
            class_meta,
            class_conflicts,
            window_constraints,
            blackout_dates,
            room_meta,
            area_meta,
            area_links,
            target_suites,
            args.week_balance_moves,
        )
    )
    report_lines.extend(
        repair_teacher_travel(
            rows,
            class_meta,
            class_conflicts,
            window_constraints,
            blackout_dates,
            room_meta,
            area_meta,
            area_links,
            args.travel_moves,
            travel_teachers,
        )
    )

    rows = sort_rows(rows)
    backup_dir = args.output_dir / "backups" / f"before_quality_hotspot_repair_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    for path in [
        args.schedule_csv,
        args.output_dir / "batch_schedule_maintenance.html",
        args.output_dir / "batch_schedule_maintenance_report.md",
        args.output_dir / "teacher_time_conflicts.csv",
        args.output_dir / "summer_camp_schedule.csv",
        args.output_dir / "summer_camp_schedule.html",
    ]:
        if path.exists():
            shutil.copy2(path, backup_dir / path.name)

    write_csv_rows(args.schedule_csv, rows)
    shutil.copy2(args.schedule_csv, args.output_dir / "summer_camp_schedule.csv")
    regenerate_outputs(rows, args.data_dir, args.output_dir)

    changed = sum(1 for before, after in zip(original_rows, rows) if before != after)
    summary = [
        f"备份目录: {backup_dir}",
        f"目标套班: {','.join(sorted(target_suites))}",
        f"移动/调整记录: {len(report_lines)} 条",
        f"排序后与原行位比较变化行: {changed}（实际以调整记录为准）",
    ]
    repair_report = args.output_dir / f"quality_hotspot_repair_report_{timestamp}.md"
    repair_report.write_text(
        "\n".join(
            [
                f"# 质量热点局部优化报告 {timestamp}",
                "",
                *[f"- {line}" for line in summary],
                "",
                "## 调整明细",
                *[f"- {line}" for line in report_lines],
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    append_report(args.output_dir / "batch_schedule_maintenance_report.md", [*summary, *report_lines[:80]], timestamp)
    print(repair_report)
    print(f"moves={len(report_lines)}")


if __name__ == "__main__":
    main()
