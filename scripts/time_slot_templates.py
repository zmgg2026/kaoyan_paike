from __future__ import annotations

from typing import Any


DEFAULT_LESSON_TEMPLATES = (
    {
        "period": "AM",
        "suffix": "1",
        "name": "上午一",
        "order": 1,
        "start_time": "08:00",
        "end_time": "10:00",
        "duration_hours": 2,
    },
    {
        "period": "AM",
        "suffix": "2",
        "name": "上午二",
        "order": 2,
        "start_time": "10:20",
        "end_time": "12:20",
        "duration_hours": 2,
    },
    {
        "period": "PM",
        "suffix": "1",
        "name": "下午一",
        "order": 1,
        "start_time": "14:00",
        "end_time": "16:00",
        "duration_hours": 2,
    },
    {
        "period": "PM",
        "suffix": "2",
        "name": "下午二",
        "order": 2,
        "start_time": "16:20",
        "end_time": "18:20",
        "duration_hours": 2,
    },
    {
        "period": "EVENING",
        "suffix": "1",
        "name": "晚上",
        "order": 1,
        "start_time": "19:00",
        "end_time": "21:00",
        "duration_hours": 2,
    },
)


def default_lesson_template_rows() -> list[dict[str, Any]]:
    return [dict(template) for template in DEFAULT_LESSON_TEMPLATES]


def lesson_slot_code(template: dict[str, Any]) -> str:
    return f"{template['period']}{template['suffix']}"


def lesson_templates_for_periods(periods: tuple[str, ...] | None = None) -> tuple[dict[str, Any], ...]:
    allowed = set(periods) if periods is not None else None
    return tuple(
        template
        for template in DEFAULT_LESSON_TEMPLATES
        if allowed is None or str(template["period"]) in allowed
    )


def standard_slot_specs_by_period(
    periods: tuple[str, ...] | None = None,
) -> dict[str, tuple[tuple[int, str, str, str, int], ...]]:
    specs: dict[str, list[tuple[int, str, str, str, int]]] = {}
    for template in lesson_templates_for_periods(periods):
        specs.setdefault(str(template["period"]), []).append(
            (
                int(template["order"]),
                str(template["name"]),
                str(template["start_time"]),
                str(template["end_time"]),
                int(template["duration_hours"]),
            )
        )
    return {period: tuple(values) for period, values in specs.items()}


def period_slot_specs(periods: tuple[str, ...] | None = None) -> dict[str, tuple[tuple[str, str, str, str], ...]]:
    specs: dict[str, list[tuple[str, str, str, str]]] = {}
    for template in lesson_templates_for_periods(periods):
        specs.setdefault(str(template["period"]), []).append(
            (
                lesson_slot_code(template),
                str(template["name"]),
                str(template["start_time"]),
                str(template["end_time"]),
            )
        )
    return {period: tuple(values) for period, values in specs.items()}


def lesson_slot_order() -> dict[str, int]:
    return {lesson_slot_code(template): index for index, template in enumerate(DEFAULT_LESSON_TEMPLATES)}


def adjacent_halfday_slot_map() -> dict[str, tuple[str, str, str, str]]:
    result: dict[str, tuple[str, str, str, str]] = {}
    for specs in period_slot_specs(("AM", "PM")).values():
        if len(specs) != 2:
            continue
        first, second = specs
        result[first[0]] = second
        result[second[0]] = first
    return result
