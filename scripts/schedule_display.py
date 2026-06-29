from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import scheduler
from scripts.calendar_utils import date_range as shared_date_range
from scripts.calendar_utils import week_dates as shared_week_dates
from scripts.calendar_utils import week_start as shared_week_start
from scripts.field_utils import parse_time_minutes
from scripts.period_utils import PERIOD_LABELS
from scripts.time_slot_templates import display_lesson_slot_rows
from scripts.weekday_utils import WEEKDAY_LABELS, weekday_label_for_date


SUBJECT_COLORS = {
    "数学": "#2f6f73",
    "英语": "#3d6fa8",
    "政治": "#bc5b2c",
    "语文": "#8a6a22",
}
FALLBACK_COLORS = ["#6f5aa7", "#557a35", "#b0445c", "#4f7d68"]


def assignment_period_key(assignment: scheduler.Assignment) -> Tuple[str, str]:
    first_slot = assignment.candidate.slots[0]
    return first_slot.date, first_slot.period


def weekday_label(date_text: str) -> str:
    return weekday_label_for_date(date_text)


def date_range(start: str, end: str) -> List[str]:
    return shared_date_range(start, end)


def week_start(date_text: str) -> str:
    return shared_week_start(date_text)


def week_dates(week: str) -> List[str]:
    return shared_week_dates(week)


def subject_colors(subjects: Iterable[str]) -> Dict[str, str]:
    colors: Dict[str, str] = {}
    fallback_index = 0
    for subject in sorted({subject for subject in subjects if subject}):
        if subject in SUBJECT_COLORS:
            colors[subject] = SUBJECT_COLORS[subject]
        else:
            colors[subject] = FALLBACK_COLORS[fallback_index % len(FALLBACK_COLORS)]
            fallback_index += 1
    return colors


def time_to_minutes(value: str) -> Optional[int]:
    return parse_time_minutes(value)


def standard_display_slots(periods: Sequence[str]) -> List[Dict[str, str]]:
    return display_lesson_slot_rows(tuple(periods))


def assignment_display_slot_ids(slots: Tuple[scheduler.TimeSlot, ...], periods: Sequence[str]) -> List[str]:
    if not slots:
        return []
    display_slots = standard_display_slots(periods)
    period = slots[0].period
    start = time_to_minutes(slots[0].start_time or "")
    end = time_to_minutes(slots[-1].end_time or "")
    if start is None or end is None:
        return [slot["id"] for slot in display_slots if slot["period"] == period]

    result: List[str] = []
    for slot in display_slots:
        if slot["period"] != period:
            continue
        slot_start = time_to_minutes(slot["start_time"])
        slot_end = time_to_minutes(slot["end_time"])
        if slot_start is None or slot_end is None:
            continue
        if start < slot_end and end > slot_start:
            result.append(slot["id"])
    return result or [slot["id"] for slot in display_slots if slot["period"] == period]


def standard_slot_duration_hours(slot: Dict[str, str]) -> int:
    start = time_to_minutes(slot.get("start_time", ""))
    end = time_to_minutes(slot.get("end_time", ""))
    if start is None or end is None or end <= start:
        return 2
    return max(1, int(round((end - start) / 60)))


def assignment_standard_lesson_slots(
    slots: Tuple[scheduler.TimeSlot, ...],
    periods: Sequence[str],
) -> List[Dict[str, object]]:
    """Expand an assignment block into display/download lessons of about 2 hours."""
    display_by_period: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for display_slot in standard_display_slots(periods):
        display_by_period[display_slot["period"]].append(display_slot)

    lessons: List[Dict[str, object]] = []
    seen: Set[Tuple[str, str, str, str]] = set()
    for slot in slots:
        start = time_to_minutes(slot.start_time or "")
        end = time_to_minutes(slot.end_time or "")
        matched: List[Dict[str, str]] = []
        if start is not None and end is not None:
            period_slots = display_by_period.get(slot.period, [])
            matched = [
                display_slot
                for display_slot in period_slots
                if (time_to_minutes(display_slot["start_time"]) or 0) >= start
                and (time_to_minutes(display_slot["end_time"]) or 0) <= end
            ]
            if not matched and float(slot.duration_hours or 0) <= 2 and period_slots:
                overlaps: List[Tuple[int, Dict[str, str]]] = []
                for display_slot in period_slots:
                    display_start = time_to_minutes(display_slot["start_time"])
                    display_end = time_to_minutes(display_slot["end_time"])
                    if display_start is None or display_end is None:
                        continue
                    overlap = min(end, display_end) - max(start, display_start)
                    if overlap > 0:
                        overlaps.append((overlap, display_slot))
                if overlaps:
                    matched = [max(overlaps, key=lambda item: item[0])[1]]

        if matched:
            for display_slot in matched:
                key = (
                    slot.date,
                    display_slot["id"],
                    display_slot["start_time"],
                    display_slot["end_time"],
                )
                if key in seen:
                    continue
                seen.add(key)
                lessons.append(
                    {
                        "slot_id": display_slot["id"],
                        "slot_label": display_slot["label"],
                        "date": slot.date,
                        "period": display_slot["period"],
                        "start_time": display_slot["start_time"],
                        "end_time": display_slot["end_time"],
                        "duration_hours": standard_slot_duration_hours(display_slot),
                    }
                )
            continue

        key = (slot.date, slot.id, slot.start_time or "", slot.end_time or "")
        if key in seen:
            continue
        seen.add(key)
        lessons.append(
            {
                "slot_id": slot.id,
                "slot_label": slot.name or PERIOD_LABELS.get(slot.period, slot.period),
                "date": slot.date,
                "period": slot.period,
                "start_time": slot.start_time or "",
                "end_time": slot.end_time or "",
                "duration_hours": slot.duration_hours,
            }
        )
    return lessons


def assignment_standard_lesson_count(assignments: Sequence[scheduler.Assignment]) -> int:
    return sum(
        len(assignment_standard_lesson_slots(assignment.candidate.slots, ["AM", "PM", "EVENING"]))
        for assignment in assignments
    )
