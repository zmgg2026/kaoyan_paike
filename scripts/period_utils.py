from __future__ import annotations

from typing import Any, Optional

from scripts.field_utils import normalize_text, parse_time_minutes


VALID_PERIODS = {"AM", "PM", "EVENING"}
PERIOD_ORDER = {"AM": 0, "PM": 1, "EVENING": 2}
PERIOD_ALIASES = {
    "AM": "AM",
    "上午": "AM",
    "早上": "AM",
    "PM": "PM",
    "下午": "PM",
    "EV": "EVENING",
    "EVENING": "EVENING",
    "NIGHT": "EVENING",
    "晚上": "EVENING",
    "晚间": "EVENING",
    "夜间": "EVENING",
}


def normalize_period(value: Any, default: Optional[str] = None) -> Optional[str]:
    text = normalize_text(value)
    if not text and default is not None:
        text = normalize_text(default)
    if not text:
        return None

    upper = text.upper()
    return PERIOD_ALIASES.get(text, PERIOD_ALIASES.get(upper, upper))


def period_sort_value(period: Any) -> int:
    normalized = normalize_period(period)
    return PERIOD_ORDER.get(normalized or "", 99)


def period_from_minutes(start_minutes: Optional[int], pm_end_minutes: int = 18 * 60 + 30) -> str:
    if start_minutes is None:
        return ""
    if start_minutes < 13 * 60:
        return "AM"
    if start_minutes < pm_end_minutes:
        return "PM"
    return "EVENING"


def period_from_time_text(start_time: Any, pm_end_minutes: int = 18 * 60 + 30) -> str:
    return period_from_minutes(parse_time_minutes(start_time), pm_end_minutes=pm_end_minutes)
