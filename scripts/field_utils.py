from __future__ import annotations

import re
from datetime import date as Date, datetime, time as Time
from typing import Any, Iterable, List, Optional, Tuple


TRUE_VALUES = {"1", "true", "yes", "y", "是", "对", "启用", "可用", "纳入", "锁定"}
FALSE_VALUES = {"0", "false", "no", "n", "否", "错", "停用", "禁用", "不可用", "不纳入"}
BLANK_MARKERS = {"", "-", "—", "无", "暂无", "NULL", "N/A", "None"}
LIST_VALUE_SEPARATOR_RE = re.compile(r"[|,，;；]+")


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_excel_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return normalize_text(value)


def is_blank_marker(value: Any) -> bool:
    return normalize_text(value) in BLANK_MARKERS


def normalize_blank_marker(value: Any) -> str:
    text = normalize_text(value)
    return "" if text in BLANK_MARKERS else text


def normalize_int(value: Any, default: int = 0) -> int:
    try:
        if value in ("", None):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def normalize_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in ("", None):
            return default
        return round(float(value), 3)
    except (TypeError, ValueError):
        return default


def normalize_date_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, Date):
        return value.isoformat()

    text = normalize_excel_text(value)
    if not text:
        return ""

    candidates = [text]
    if " " in text:
        candidates.append(text.split(" ", 1)[0])
    if "T" in text:
        candidates.append(text.split("T", 1)[0])

    for candidate in candidates:
        for fmt in (
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%Y.%m.%d",
            "%Y%m%d",
            "%Y-%m-%d %H:%M:%S",
            "%Y/%m/%d %H:%M:%S",
            "%Y.%m.%d %H:%M:%S",
        ):
            try:
                return datetime.strptime(candidate, fmt).date().isoformat()
            except ValueError:
                pass
        match = re.fullmatch(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", candidate)
        if match:
            year, month, day = (int(part) for part in match.groups())
            return Date(year, month, day).isoformat()

    return text


def display_date_text(value: Any, separator: str = "/") -> str:
    text = normalize_date_text(value)
    try:
        normalized = Date.fromisoformat(text).isoformat()
    except ValueError:
        return normalize_excel_text(value).replace("-", separator)
    return normalized.replace("-", separator)


def normalize_iso_date_text(value: Any, label: str = "日期") -> str:
    text = normalize_date_text(value)
    if not text:
        return ""
    try:
        return Date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise ValueError(f"{label} 日期格式无法识别: {normalize_text(value)}") from exc


def parse_datetime_value(value: Any, label: str = "日期时间", allow_date: bool = False) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, Date):
        if allow_date:
            return datetime.combine(value, Time.min)
        raise ValueError(f"无法解析{label}: {value!r}")

    text = normalize_excel_text(value)
    candidates = [text]
    if "T" in text:
        candidates.append(text.replace("T", " ", 1))

    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y.%m.%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M",
        "%Y.%m.%d %H:%M",
    ]
    if allow_date:
        formats.extend(("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d"))

    for candidate in candidates:
        for fmt in formats:
            try:
                return datetime.strptime(candidate, fmt)
            except ValueError:
                pass

    raise ValueError(f"无法解析{label}: {value!r}")


def parse_date_value(value: Any, label: str = "日期") -> Date:
    text = normalize_date_text(value)
    try:
        return Date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{label} 日期格式无法识别: {normalize_text(value)}") from exc


def normalize_time_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%H:%M")
    if isinstance(value, Time):
        return value.strftime("%H:%M")

    text = normalize_excel_text(value)
    match = re.search(r"(\d{1,2}):(\d{2})", text)
    if not match:
        return text
    return f"{int(match.group(1)):02d}:{match.group(2)}"


def parse_time_minutes(value: Any) -> Optional[int]:
    text = normalize_time_text(value)
    if not text:
        return None
    match = re.search(r"(\d{1,2}):(\d{2})", text)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return hour * 60 + minute


def split_time_range_text(value: Any) -> Tuple[str, str]:
    text = normalize_text(value).replace("－", "~").replace("—", "~").replace("-", "~")
    if "~" not in text:
        return normalize_time_text(text), ""
    start, end = text.split("~", 1)
    return normalize_time_text(start), normalize_time_text(end)


def split_delimited_values(values: Any) -> List[str]:
    if values is None:
        return []
    if isinstance(values, str):
        items: Iterable[Any] = LIST_VALUE_SEPARATOR_RE.split(values)
    else:
        items = values
    return [normalize_text(item) for item in items if normalize_text(item)]


def split_pipe_values(values: Any) -> List[str]:
    return split_delimited_values(values)


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return normalize_text(value).lower() in TRUE_VALUES


def parse_bool_default(value: Any, default: bool) -> bool:
    if value in ("", None):
        return default
    return parse_bool(value)


def parse_enabled(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = normalize_text(value).lower()
    if not text:
        return default
    return text not in FALSE_VALUES
