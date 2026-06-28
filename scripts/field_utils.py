from __future__ import annotations

from typing import Any, Iterable, List


TRUE_VALUES = {"1", "true", "yes", "y", "是", "对", "启用", "可用", "纳入", "锁定"}
FALSE_VALUES = {"0", "false", "no", "n", "否", "错", "停用", "禁用", "不可用", "不纳入"}


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


def split_pipe_values(values: Any) -> List[str]:
    if values is None:
        return []
    if isinstance(values, str):
        items: Iterable[Any] = values.split("|")
    else:
        items = values
    return [normalize_text(item) for item in items if normalize_text(item)]


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
