#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Dict, Iterable, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from openpyxl import load_workbook

from scripts.csv_utils import write_csv_rows
from scripts.field_utils import normalize_text, parse_bool as normalize_bool
from scripts.schedule_modes import (
    assignment_actual_scheduled_class_id,
    assignment_inherited_class_id,
    assignment_schedule_mode_value,
    class_schedule_mode_display_name,
    normalize_class_schedule_mode,
)


DEFAULT_WORKBOOK = ROOT / "outputs" / "ai_scheduling_sop_20260625" / "AI排课基础数据模板.xlsx"
DATA_DIR = ROOT / "data"


SHEETS = {
    "01_年度排课窗口表": ("schedule_windows", "schedule_windows"),
    "02_课节表": ("time_slots", "time_slots"),
    "03_教学区表": ("teaching_areas", "teaching_areas"),
    "04_教室表": ("rooms", "rooms"),
    "05_教师基础信息表": ("teachers", "teachers"),
    "06_教师不可排日期时段表": ("teacher_unavailability", "teacher_unavailability"),
    "07_产品管理表": ("products", "products"),
    "08_产品课程课时表": ("product_courses", "product_courses"),
    "09_产品窗口排课规则表": ("product_schedule_rules", "product_schedule_rules"),
    "10_班级基础信息表": ("classes", "classes"),
    "11_班级排课窗口表": ("class_window_boundaries", "class_window_boundaries"),
    "12_班级老师安排表": ("class_teacher_assignments", "class_teacher_assignments"),
    "13_班级排课互斥关系表": ("class_conflict_groups", "class_conflict_groups"),
    "14_锁定课表": ("locked_scheduled_lessons", "locked_scheduled_lessons"),
    "15_教学区通勤关系表": ("teaching_area_links", "teaching_area_links"),
    "16_全局停课日期表": ("global_blackout_dates", "global_blackout_dates"),
    "17_历史已排课明细表": ("historical_scheduled_lessons", "historical_scheduled_lessons"),
    "18_ERP产品对应表": ("business_product_mappings", "business_product_mappings"),
    "19_ERP标准产品清单": ("erp_standard_products", "erp_standard_products"),
}

SHEET_ALIASES = {
    "11_班级排课窗口表": ["11_班级窗口边界表"],
    "18_ERP产品对应表": ["18_业务产品映射表"],
}

LIST_FIELDS = {
    "season_window_ids",
    "applicable_stages",
    "selected_stages",
    "actual_schedule_window_ids",
    "preferred_teaching_area_ids",
    "preferred_room_ids",
    "allowed_weekdays",
    "allowed_periods",
    "weekdays",
    "periods",
    "schedule_window_ids",
    "class_ids",
    "product_ids",
    "product_name_keywords",
    "excluded_weekdays",
    "exception_weekdays",
    "teaching_area_ids",
    "stages",
    "class_name_keywords",
}

BOOL_FIELDS = {
    "is_active",
    "is_usable",
    "preferred_room_is_required",
    "is_manual_schedule_locked",
    "is_schedule_locked",
    "is_class_window_included",
    "is_conflict_group_active",
    "is_locked",
    "effective_after_class_start",
    "same_half_day_block_required",
    "same_half_day_4h_same_teacher_required",
    "is_enabled",
    "is_deleted",
}

CURRENT_TEACHER_ASSIGNMENT_FIELDS = [
    "class_id",
    "class_name",
    "product_id",
    "product_name",
    "subject",
    "stage",
    "course_group",
    "class_schedule_mode",
    "actual_scheduled_class_id",
    "teacher_id",
    "teacher_name",
    "assignment_extra_time_requirement",
    "notes",
]

INT_FIELDS = {
    "calendar_year",
    "window_year",
    "window_order",
    "order",
    "window_sequence",
    "stage_priority",
    "module_priority",
    "module_priority_in_group",
    "lessons_per_block",
    "max_blocks_per_class_per_day",
    "standard_capacity",
    "scheduling_capacity",
    "room_count",
    "active_room_count",
    "capacity",
    "size",
    "erp_duration_minutes",
    "erp_lesson_count",
    "erp_single_lesson_minutes",
    "duration_minutes",
    "lesson_count",
    "single_lesson_minutes",
}

FLOAT_FIELDS = {
    "duration_hours",
    "total_hours",
    "block_hours",
    "block_hours_override",
    "max_hours_per_class_per_day",
    "min_weekly_hours",
    "max_weekly_hours",
    "driving_distance_km",
    "travel_minutes",
}

DATE_FIELDS = {
    "date",
    "start_date",
    "end_date",
    "first_lesson_date",
    "earliest_date",
    "latest_date",
}
TIME_FIELDS = {"start_time", "end_time"}


def normalize_number(value: Any, *, integer: bool) -> int | float | str:
    if value in (None, ""):
        return 0 if integer else ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return normalize_text(value)
    return int(number) if integer else number


def normalize_date(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = normalize_text(value)
    if "T00:00:00" in text:
        return text.split("T", 1)[0]
    return text


def normalize_time(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, datetime):
        return value.time().strftime("%H:%M")
    if isinstance(value, time):
        return value.strftime("%H:%M")
    text = normalize_text(value)
    return text[:5] if len(text) >= 5 and text[2:3] == ":" else text


def normalize_list(value: Any) -> List[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        values = value
    else:
        values = normalize_text(value).split("|")
    return [normalize_text(item) for item in values if normalize_text(item)]


def cell_value(field: str, value: Any) -> Any:
    if field in LIST_FIELDS:
        return normalize_list(value)
    if field in BOOL_FIELDS:
        return normalize_bool(value)
    if field in INT_FIELDS:
        return normalize_number(value, integer=True)
    if field in FLOAT_FIELDS:
        return normalize_number(value, integer=False)
    if field in DATE_FIELDS:
        return normalize_date(value)
    if field in TIME_FIELDS:
        return normalize_time(value)
    return normalize_text(value)


def read_sheet(workbook_path: Path, sheet_name: str) -> List[Dict[str, Any]]:
    wb = load_workbook(workbook_path, read_only=True, data_only=True)
    actual_sheet_name = sheet_name
    if actual_sheet_name not in wb.sheetnames:
        for alias in SHEET_ALIASES.get(sheet_name, []):
            if alias in wb.sheetnames:
                actual_sheet_name = alias
                break
    if actual_sheet_name not in wb.sheetnames:
        return []
    ws = wb[actual_sheet_name]
    headers = [normalize_text(value) for value in next(ws.iter_rows(min_row=6, max_row=6, values_only=True))]
    rows: List[Dict[str, Any]] = []
    for raw in ws.iter_rows(min_row=7, values_only=True):
        if not any(value not in (None, "") for value in raw):
            continue
        row = {
            field: cell_value(field, raw[index] if index < len(raw) else "")
            for index, field in enumerate(headers)
            if field
        }
        rows.append(row)
    return rows


def current_teacher_assignment_template_row(row: Dict[str, Any]) -> Dict[str, Any]:
    class_id = normalize_text(row.get("class_id"))
    inherited_class_id = assignment_inherited_class_id(row)
    actual_class_id = assignment_actual_scheduled_class_id(row) or inherited_class_id
    mode = normalize_class_schedule_mode(
        assignment_schedule_mode_value(row),
        inherit_from_class_id=inherited_class_id,
        actual_scheduled_class_id=actual_class_id,
        class_id=class_id,
    )
    is_shared = mode == "共享课表"
    actual_scheduled_class_id = actual_class_id if is_shared else class_id or actual_class_id
    result = {
        "class_id": class_id,
        "class_name": normalize_text(row.get("class_name")),
        "product_id": normalize_text(row.get("product_id") or row.get("canonical_product_id")),
        "product_name": normalize_text(row.get("product_name")),
        "subject": normalize_text(row.get("subject")),
        "stage": normalize_text(row.get("stage")),
        "course_group": normalize_text(row.get("course_group")),
        "class_schedule_mode": class_schedule_mode_display_name(mode),
        "actual_scheduled_class_id": actual_scheduled_class_id,
        "teacher_id": "" if is_shared else normalize_text(row.get("teacher_id")),
        "teacher_name": "" if is_shared else normalize_text(row.get("teacher_name")),
        "assignment_extra_time_requirement": normalize_text(row.get("assignment_extra_time_requirement")),
        "notes": normalize_text(row.get("notes")),
    }
    return {field: result.get(field, "") for field in CURRENT_TEACHER_ASSIGNMENT_FIELDS}


def enrich_rows(key: str, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    enriched: List[Dict[str, Any]] = []
    for row in rows:
        if key == "teachers":
            row["id"] = row.get("employee_id", "")
            row["identity"] = row.get("teacher_role", "")
            row["teacher_type"] = row.get("employment_type", "")
        elif key == "product_courses":
            row["quarter"] = row.get("window_name", "")
            row["module_priority"] = row.get("module_priority_in_group", 0)
            row.setdefault("block_hours", 0)
            row.pop("teaching_area_ids", None)
        elif key == "product_schedule_rules":
            product_id = normalize_text(row.get("product_id"))
            row["rule_name"] = row.get("rule_name") or " / ".join(
                item for item in (row.get("product_name"), row.get("window_name")) if item
            ) or row.get("rule_id", "")
            row["scope_type"] = "product_ids" if product_id else "all"
            row["product_ids"] = [product_id] if product_id else []
            row["product_name_keywords"] = []
            row["subject"] = ""
            row["stage"] = ""
            row["course_module"] = ""
            row["course_group"] = ""
            row["start_date"] = ""
            row["end_date"] = ""
            row["excluded_weekdays"] = []
            row["exception_weekdays"] = []
            row["block_hours_override"] = row.get("block_hours", 0)
        elif key == "products":
            row.setdefault("season_window_ids", [])
            row.setdefault("applicable_stages", [])
        elif key == "classes":
            row["stages"] = row.get("selected_stages", [])
            row["is_schedule_locked"] = row.get("is_manual_schedule_locked", False)
            row.pop("actual_schedule_window_ids", None)
        elif key == "business_product_mappings":
            if not normalize_text(row.get("local_product_id")):
                row["local_product_id"] = normalize_text(row.get("canonical_product_id"))
            row.pop("canonical_product_id", None)
        elif key == "class_conflict_groups":
            row["is_active"] = row.get("is_conflict_group_active", True)
            row["source"] = row.get("conflict_source", "")
        elif key == "class_teacher_assignments":
            enriched.append(current_teacher_assignment_template_row(row))
            continue
        enriched.append(row)
    return enriched


def merge_assignments_into_classes(classes: List[Dict[str, Any]], assignments: List[Dict[str, Any]]) -> None:
    by_class: Dict[str, List[Dict[str, Any]]] = {}
    for assignment in assignments:
        class_id = normalize_text(assignment.get("class_id"))
        if not class_id:
            continue
        payload = {
            key: value
            for key, value in assignment.items()
            if key not in {"class_id", "class_name"}
        }
        by_class.setdefault(class_id, []).append(payload)
    for cls in classes:
        cls["teacher_assignments"] = by_class.get(normalize_text(cls.get("id")), [])
        cls.setdefault("requirements", [])


def add_missing_preferred_room_placeholders(tables: Dict[str, List[Dict[str, Any]]]) -> None:
    """Keep required class room references visible when ERP room export is missing them."""
    rooms = tables.get("rooms", [])
    room_ids = {normalize_text(room.get("id")) for room in rooms if normalize_text(room.get("id"))}
    areas = {
        normalize_text(area.get("id")): area
        for area in tables.get("teaching_areas", [])
        if normalize_text(area.get("id"))
    }
    missing: Dict[str, Dict[str, Any]] = {}

    def remember(room_id: str, area_ids: List[str], source: str) -> None:
        room_id = normalize_text(room_id)
        if not room_id or room_id in room_ids:
            return
        area_id = area_ids[0] if area_ids else ""
        missing.setdefault(
            room_id,
            {
                "room_id": room_id,
                "teaching_area_id": area_id,
                "sources": set(),
            },
        )
        if area_id and not missing[room_id]["teaching_area_id"]:
            missing[room_id]["teaching_area_id"] = area_id
        missing[room_id]["sources"].add(source)

    for cls in tables.get("classes", []):
        area_ids = normalize_list(cls.get("preferred_teaching_area_ids"))
        for room_id in normalize_list(cls.get("preferred_room_ids")):
            remember(room_id, area_ids, f"班级 {normalize_text(cls.get('id'))}")

    for boundary in tables.get("class_window_boundaries", []):
        area_ids = normalize_list(boundary.get("preferred_teaching_area_ids"))
        for room_id in normalize_list(boundary.get("preferred_room_ids")):
            remember(room_id, area_ids, f"班级窗口 {normalize_text(boundary.get('class_window_id'))}")

    for room_id in sorted(missing):
        item = missing[room_id]
        area = areas.get(item["teaching_area_id"], {})
        area_name = normalize_text(area.get("short_name") or area.get("name") or item["teaching_area_id"])
        rooms.append(
            {
                "id": room_id,
                "name": f"{area_name} 待核对教室 {room_id}",
                "teaching_area_id": item["teaching_area_id"],
                "teaching_area_name": area_name,
                "campus": normalize_text(area.get("campus")),
                "capacity": 0,
                "room_type": "待核对",
                "is_active": False,
                "data_source": "班级/窗口指定教室补齐占位",
                "notes": "该教室ID出现在班级或班级窗口指定教室中，但04_教室表未找到；需人工核对ERP教室导出。引用来源："
                + "；".join(sorted(item["sources"])),
            }
        )
        room_ids.add(room_id)


def json_doc(key: str, rows: List[Dict[str, Any]], workbook_path: Path) -> Dict[str, Any]:
    return {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": str(workbook_path),
        "record_count": len(rows),
        key: rows,
    }


def csv_value(value: Any) -> str:
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, list):
        return "|".join(str(item) for item in value)
    return "" if value is None else str(value)


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    fields: List[str] = []
    seen = set()
    for row in rows:
        for field in row:
            if field not in seen:
                seen.add(field)
                fields.append(field)
    write_csv_rows(path, fields, rows, value_formatter=csv_value)


def sync(workbook_path: Path) -> Dict[str, int]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tables: Dict[str, List[Dict[str, Any]]] = {}
    stems: Dict[str, str] = {}
    for sheet_name, (key, stem) in SHEETS.items():
        rows = enrich_rows(key, read_sheet(workbook_path, sheet_name))
        tables[key] = rows
        stems[key] = stem

    merge_assignments_into_classes(tables["classes"], tables["class_teacher_assignments"])
    add_missing_preferred_room_placeholders(tables)

    for key, rows in tables.items():
        stem = stems[key]
        (DATA_DIR / f"{stem}.json").write_text(
            json.dumps(json_doc(key, rows, workbook_path), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        write_csv(DATA_DIR / f"{stem}.csv", rows)

    return {key: len(rows) for key, rows in tables.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync AI scheduling template workbook into web admin data files.")
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    args = parser.parse_args()
    counts = sync(args.workbook)
    for key in sorted(counts):
        print(f"{key}: {counts[key]}")


if __name__ == "__main__":
    main()
