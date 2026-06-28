from __future__ import annotations

from typing import Any, Mapping


SHARED_SCHEDULE_MODES = {"共享课表", "shared", "inherit", "inherited", "合班共享"}
SHARED_KEYWORDS = ("共享", "继承")
MERGE_PRIMARY_KEYWORDS = ("合班", "主班")
INDEPENDENT_KEYWORDS = ("本班", "独立")


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def normalize_class_schedule_mode(
    value: Any,
    inherit_from_class_id: Any = "",
    actual_scheduled_class_id: Any = "",
    class_id: Any = "",
) -> str:
    text = normalize_text(value)
    compact = text.replace(" ", "").lower()
    actual_class = normalize_text(actual_scheduled_class_id)
    current_class = normalize_text(class_id)
    inherited_class = normalize_text(inherit_from_class_id)
    if any(keyword in text for keyword in MERGE_PRIMARY_KEYWORDS):
        return "合班主班"
    if any(keyword in text for keyword in INDEPENDENT_KEYWORDS):
        return "独立排课"
    if current_class:
        if inherited_class and inherited_class != current_class:
            return "共享课表"
        if actual_class and actual_class != current_class:
            return "共享课表"
        if inherited_class == current_class or actual_class == current_class:
            return "独立排课"

    if compact in {"shared", "inherit", "inherited"} or any(keyword in text for keyword in SHARED_KEYWORDS):
        return "共享课表"
    if inherited_class:
        return "共享课表"

    if actual_class and current_class and actual_class != current_class:
        return "共享课表"
    return text


def is_shared_class_schedule(
    value: Any,
    inherit_from_class_id: Any = "",
    actual_scheduled_class_id: Any = "",
    class_id: Any = "",
) -> bool:
    return (
        normalize_class_schedule_mode(
            value,
            inherit_from_class_id=inherit_from_class_id,
            actual_scheduled_class_id=actual_scheduled_class_id,
            class_id=class_id,
        )
        == "共享课表"
    )


def class_schedule_mode_display_name(mode: str) -> str:
    if mode == "共享课表":
        return "共享实际排课班级"
    if mode == "合班主班":
        return "合班主班"
    return "本班实际排课"


def assignment_schedule_mode(row: Mapping[str, Any], class_id: Any = "") -> str:
    return normalize_class_schedule_mode(
        row.get("class_schedule_mode")
        or row.get("schedule_mode")
        or row.get("assignment_mode")
        or row.get("排课方式")
        or row.get("合班方式"),
        inherit_from_class_id=assignment_inherited_class_id(row),
        actual_scheduled_class_id=assignment_actual_scheduled_class_id(row),
        class_id=class_id or row.get("class_id") or row.get("班级编码"),
    )


def assignment_actual_scheduled_class_id(row: Mapping[str, Any]) -> str:
    return normalize_text(
        row.get("actual_scheduled_class_id")
        or row.get("scheduled_class_id")
        or row.get("actual_class_id")
        or row.get("实际排课班级")
    )


def assignment_inherited_class_id(row: Mapping[str, Any]) -> str:
    return normalize_text(
        row.get("inherit_from_class_id")
        or row.get("继承自主班")
        or row.get("主班编码")
    )


def assignment_reference_class_id(row: Mapping[str, Any]) -> str:
    return assignment_actual_scheduled_class_id(row) or assignment_inherited_class_id(row)


def assignment_is_shared(row: Mapping[str, Any], class_id: Any = "") -> bool:
    return assignment_schedule_mode(row, class_id=class_id) == "共享课表"
