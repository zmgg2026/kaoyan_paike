#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

import data_admin_server
import scheduler
from business_class_import import BusinessDataError, convert_business_tables
from generate_time_slots import generate_time_slots, parse_weekdays


TABLES = [
    "schedule_windows",
    "time_slots",
    "teaching_areas",
    "rooms",
    "teachers",
    "teacher_unavailability",
    "products",
    "product_courses",
    "product_schedule_rules",
    "classes",
    "class_window_boundaries",
    "class_teacher_assignments",
    "class_conflict_groups",
    "locked_scheduled_lessons",
    "teaching_area_links",
    "global_blackout_dates",
    "historical_scheduled_lessons",
    "business_product_mappings",
    "erp_standard_products",
]

BUSINESS_TABLES = [
    "business_classes",
    "merge_course_details",
    "scheduled_lessons",
]

SOURCE_TABLES = [*TABLES, *BUSINESS_TABLES]
REPORT_TABLES = [*TABLES, "business_classes", "scheduled_lessons"]
COMPATIBILITY_REPORT_TABLES = ["merge_course_details"]

TABLE_ALIASES = {
    "schedulewindows": "schedule_windows",
    "schedulewindow": "schedule_windows",
    "年度排课窗口": "schedule_windows",
    "年度排课窗口表": "schedule_windows",
    "排课窗口": "schedule_windows",
    "排课窗口表": "schedule_windows",
    "timeslots": "time_slots",
    "timeslot": "time_slots",
    "time_slots": "time_slots",
    "课节": "time_slots",
    "课节表": "time_slots",
    "teachingareas": "teaching_areas",
    "teachingarea": "teaching_areas",
    "教学区": "teaching_areas",
    "教学区表": "teaching_areas",
    "rooms": "rooms",
    "room": "rooms",
    "教室": "rooms",
    "教室表": "rooms",
    "教学区与教室": "rooms",
    "teachers": "teachers",
    "teacher": "teachers",
    "教师": "teachers",
    "教师表": "teachers",
    "教师基础信息": "teachers",
    "教师基础信息表": "teachers",
    "teacherunavailability": "teacher_unavailability",
    "teacherunavailable": "teacher_unavailability",
    "教师不可排日期时段": "teacher_unavailability",
    "教师不可排日期时段表": "teacher_unavailability",
    "教师不可排时间": "teacher_unavailability",
    "教师不可排时间表": "teacher_unavailability",
    "products": "products",
    "product": "products",
    "产品": "products",
    "产品表": "products",
    "产品管理": "products",
    "产品管理表": "products",
    "productcourses": "product_courses",
    "courses": "product_courses",
    "productrequirements": "product_courses",
    "产品课程": "product_courses",
    "产品课程表": "product_courses",
    "产品课程课时": "product_courses",
    "产品课程课时表": "product_courses",
    "productschedulerules": "product_schedule_rules",
    "schedulerules": "product_schedule_rules",
    "productrules": "product_schedule_rules",
    "产品排课规则": "product_schedule_rules",
    "产品排课规则表": "product_schedule_rules",
    "产品窗口排课规则": "product_schedule_rules",
    "产品窗口排课规则表": "product_schedule_rules",
    "classes": "classes",
    "class": "classes",
    "班级": "classes",
    "班级表": "classes",
    "班级管理": "classes",
    "班级基础信息": "classes",
    "班级基础信息表": "classes",
    "classwindowboundaries": "class_window_boundaries",
    "classwindowboundary": "class_window_boundaries",
    "班级窗口边界": "class_window_boundaries",
    "班级窗口边界表": "class_window_boundaries",
    "班级排课窗口": "class_window_boundaries",
    "班级排课窗口表": "class_window_boundaries",
    "classteacherassignments": "class_teacher_assignments",
    "teacherassignments": "class_teacher_assignments",
    "classteachers": "class_teacher_assignments",
    "班级老师安排": "class_teacher_assignments",
    "班级老师安排表": "class_teacher_assignments",
    "classconflictgroups": "class_conflict_groups",
    "conflictgroups": "class_conflict_groups",
    "班级互斥关系": "class_conflict_groups",
    "班级互斥关系表": "class_conflict_groups",
    "班级排课互斥关系": "class_conflict_groups",
    "班级排课互斥关系表": "class_conflict_groups",
    "排课互斥关系": "class_conflict_groups",
    "冲突组": "class_conflict_groups",
    "冲突组表": "class_conflict_groups",
    "teachingarealinks": "teaching_area_links",
    "arealinks": "teaching_area_links",
    "教学区关联": "teaching_area_links",
    "教学区关联表": "teaching_area_links",
    "教学区通勤关系": "teaching_area_links",
    "教学区通勤关系表": "teaching_area_links",
    "globalblackoutdates": "global_blackout_dates",
    "blackoutdates": "global_blackout_dates",
    "blackouts": "global_blackout_dates",
    "全局停课日期": "global_blackout_dates",
    "全局停课日期表": "global_blackout_dates",
    "停课日期": "global_blackout_dates",
    "历史已排课明细": "historical_scheduled_lessons",
    "历史已排课明细表": "historical_scheduled_lessons",
    "erp产品对应": "business_product_mappings",
    "erp产品对应表": "business_product_mappings",
    "businessproductmappings": "business_product_mappings",
    "businessproductmapping": "business_product_mappings",
    "业务产品对应": "business_product_mappings",
    "业务产品对应表": "business_product_mappings",
    "erpstandardproducts": "erp_standard_products",
    "erpstandardproduct": "erp_standard_products",
    "erp标准产品": "erp_standard_products",
    "erp标准产品清单": "erp_standard_products",
    "erp标准产品清单表": "erp_standard_products",
    "businessclasses": "business_classes",
    "businessclassexport": "business_classes",
    "businessclassrows": "business_classes",
    "业务班级": "business_classes",
    "业务班级导出": "business_classes",
    "班级查询导出": "business_classes",
    "businessproductmap": "business_product_mappings",
    "productmap": "business_product_mappings",
    "业务产品映射": "business_product_mappings",
    "业务产品映射表": "business_product_mappings",
    "产品映射": "business_product_mappings",
    "产品映射表": "business_product_mappings",
    "mergecoursedetails": "merge_course_details",
    "merge_course_details": "merge_course_details",
    "合班课程明细": "merge_course_details",
    "合班课程明细表": "merge_course_details",
    "scheduledlessons": "scheduled_lessons",
    "scheduledlesson": "scheduled_lessons",
    "schedulehistory": "scheduled_lessons",
    "historicalschedule": "scheduled_lessons",
    "已排课明细": "scheduled_lessons",
    "历史课表": "scheduled_lessons",
    "已排课表": "scheduled_lessons",
    "已排课": "scheduled_lessons",
    "locked_scheduled_lessons": "locked_scheduled_lessons",
    "lockedlessons": "locked_scheduled_lessons",
    "lockedschedule": "locked_scheduled_lessons",
    "锁定课表": "locked_scheduled_lessons",
    "锁定课表表": "locked_scheduled_lessons",
    "已定课表": "locked_scheduled_lessons",
    "固定课表": "locked_scheduled_lessons",
}

TEACHER_FIELDNAMES = [
    "employee_id",
    "name",
    "gender",
    "project",
    "primary_subject",
    "subject_type",
    "teacher_role",
    "employment_type",
    "contract_status",
    "employment_status",
    "notes",
]
BLACKOUT_FIELDNAMES = ["id", "name", "start_date", "end_date", "is_active", "notes"]

TABLE_FIELDNAMES = {
    "schedule_windows": data_admin_server.SCHEDULE_WINDOW_FIELDNAMES,
    "time_slots": data_admin_server.TIME_SLOT_FIELDNAMES,
    "teaching_areas": data_admin_server.TEACHING_AREA_FIELDNAMES,
    "rooms": data_admin_server.ROOM_FIELDNAMES,
    "teachers": TEACHER_FIELDNAMES,
    "teacher_unavailability": data_admin_server.TEACHER_UNAVAILABILITY_FIELDNAMES,
    "products": data_admin_server.PRODUCT_FIELDNAMES,
    "product_courses": data_admin_server.PRODUCT_COURSE_FIELDNAMES,
    "product_schedule_rules": data_admin_server.PRODUCT_RULE_FIELDNAMES,
    "classes": data_admin_server.CLASS_FIELDNAMES,
    "class_window_boundaries": data_admin_server.CLASS_WINDOW_BOUNDARY_FIELDNAMES,
    "class_teacher_assignments": data_admin_server.TEACHER_ASSIGNMENT_FIELDNAMES,
    "class_conflict_groups": data_admin_server.CLASS_CONFLICT_GROUP_FIELDNAMES,
    "locked_scheduled_lessons": data_admin_server.LOCKED_SCHEDULED_LESSON_FIELDNAMES,
    "teaching_area_links": data_admin_server.TEACHING_AREA_LINK_FIELDNAMES,
    "global_blackout_dates": BLACKOUT_FIELDNAMES,
    "historical_scheduled_lessons": data_admin_server.LOCKED_SCHEDULED_LESSON_FIELDNAMES,
    "business_product_mappings": data_admin_server.BUSINESS_PRODUCT_MAPPING_FIELDNAMES,
    "erp_standard_products": data_admin_server.ERP_STANDARD_PRODUCT_FIELDNAMES,
}


@dataclass
class LoadedTable:
    name: str
    source: str
    rows: List[Dict[str, Any]]


@dataclass
class PipelineResult:
    scheduler_input_path: Path
    schedule_csv_path: Path
    schedule_html_path: Path
    report_path: Path
    backup_path: Optional[Path]
    row_counts: Dict[str, int]
    warnings: List[str]
    generated_files: List[Path]


@dataclass
class PreflightResult:
    passed: bool
    report_path: Path
    row_counts: Dict[str, int]
    warnings: List[str]
    generated_files: List[Path]
    missing_teacher_requirements: List[MissingTeacherRequirement]
    missing_teacher_rows: List[Dict[str, str]]
    error: str = ""


@dataclass(frozen=True)
class MissingTeacherRequirement:
    class_id: str
    product_id: str
    subject: str
    stage: str
    course_group: str


class PipelineError(RuntimeError):
    pass


def normalize_table_name(value: str) -> str:
    text = Path(value).stem if "." in value else value
    return (
        text.strip()
        .lower()
        .replace(" ", "")
        .replace("_", "")
        .replace("-", "")
        .replace("/", "")
        .replace("\\", "")
        .replace("（", "")
        .replace("）", "")
        .replace("(", "")
        .replace(")", "")
    )


def table_name_for(value: str) -> Optional[str]:
    normalized = normalize_table_name(value)
    candidates = [normalized]
    unnumbered = re.sub(r"^\d+", "", normalized)
    if unnumbered and unnumbered != normalized:
        candidates.append(unnumbered)
    if "班级查询导出" in normalized:
        return "business_classes"
    if "配课明细" in normalized:
        return "scheduled_lessons"
    for candidate in candidates:
        table_name = TABLE_ALIASES.get(candidate)
        if table_name:
            return table_name
    return None


def source_files(source: Path) -> List[Path]:
    if source.is_file():
        return [source]
    if not source.exists():
        raise PipelineError(f"源数据路径不存在: {source}")
    files = [
        path for path in sorted(source.iterdir())
        if path.suffix.lower() in {".csv", ".xlsx", ".xlsm"} and not path.name.startswith("~$")
    ]
    if not files:
        raise PipelineError(f"源数据目录中没有找到 CSV/XLSX 文件: {source}")
    return files


def read_csv_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise PipelineError(f"无法识别 CSV 编码: {path}")


def read_csv_rows(path: Path) -> List[Dict[str, Any]]:
    text = read_csv_text(path)
    reader = csv.DictReader(text.splitlines())
    if not reader.fieldnames:
        return []
    validate_headers([header or "" for header in reader.fieldnames], str(path))
    return clean_rows(list(reader))


def cell_text(cell: Any) -> str:
    value = cell.value
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not value.is_integer():
            return str(value)
        number = str(int(value))
        number_format = str(getattr(cell, "number_format", "") or "")
        if number_format and set(number_format) == {"0"} and len(number_format) > len(number):
            return number.zfill(len(number_format))
        return number
    return str(value).strip()


def read_xlsx_tables(path: Path) -> List[LoadedTable]:
    try:
        from openpyxl import load_workbook
    except ModuleNotFoundError as exc:
        raise PipelineError("读取 Excel 需要先安装 openpyxl: pip install -r requirements.txt") from exc

    workbook = load_workbook(path, data_only=True, read_only=True)
    tables: List[LoadedTable] = []
    for sheet in workbook.worksheets:
        if sheet.max_row == 1 and sheet.max_column == 1:
            try:
                sheet.reset_dimensions()
            except AttributeError:
                pass
        rows = list(sheet.iter_rows())
        if not rows:
            continue
        header_row_index = first_non_empty_row_index(rows)
        if header_row_index is None:
            continue
        table_name = table_name_for(sheet.title)
        if not table_name:
            data_rows = rows[header_row_index + 1 :]
            if any(any(cell_text(cell) for cell in row) for row in data_rows):
                print(f"跳过未识别的 Excel sheet: {path.name}/{sheet.title}", file=sys.stderr)
            continue
        header_row_index = header_row_index_for_table(rows, table_name, header_row_index)
        headers = [cell_text(cell) for cell in rows[header_row_index]]
        validate_headers(headers, f"{path.name}/{sheet.title}")
        records = []
        for row in rows[header_row_index + 1 :]:
            record = {
                header: cell_text(cell)
                for header, cell in zip(headers, row)
                if header
            }
            records.append(record)
        tables.append(LoadedTable(table_name, f"{path.name}/{sheet.title}", clean_rows(records)))
    return tables


def first_non_empty_row_index(rows: Sequence[Sequence[Any]]) -> Optional[int]:
    for index, row in enumerate(rows):
        if any(cell_text(cell) for cell in row):
            return index
    return None


def header_row_index_for_table(
    rows: Sequence[Sequence[Any]],
    table_name: str,
    fallback_index: int,
) -> int:
    expected = set(TABLE_FIELDNAMES.get(table_name, []))
    if not expected:
        return fallback_index
    for index, row in enumerate(rows[:20]):
        values = [cell_text(cell) for cell in row if cell_text(cell)]
        if not values:
            continue
        matching = [value for value in values if value in expected]
        if len(matching) >= min(2, len(expected)):
            return index
    return fallback_index


def validate_headers(headers: Sequence[str], label: str) -> None:
    seen: Set[str] = set()
    for header in headers:
        if not header:
            continue
        if header in seen:
            raise PipelineError(f"{label} 存在重复表头: {header}")
        seen.add(header)


def clean_rows(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result = []
    for row in rows:
        cleaned = {
            str(key).strip(): ("" if value is None else str(value).strip())
            for key, value in row.items()
            if key is not None and str(key).strip()
        }
        if any(value for value in cleaned.values()):
            result.append(cleaned)
    return result


def load_source_tables(source: Path) -> Dict[str, LoadedTable]:
    loaded: Dict[str, LoadedTable] = {}
    for path in source_files(source):
        suffix = path.suffix.lower()
        if suffix == ".csv":
            table_name = table_name_for(path.name)
            if not table_name:
                print(f"跳过未识别的 CSV 文件: {path.name}", file=sys.stderr)
                continue
            tables = [LoadedTable(table_name, path.name, read_csv_rows(path))]
        else:
            tables = read_xlsx_tables(path)

        for table in tables:
            if table.name in loaded:
                first = loaded[table.name].source
                raise PipelineError(f"重复的数据表 {table.name}: {first} 和 {table.source}")
            loaded[table.name] = table

    if not loaded:
        raise PipelineError("没有识别到任何标准数据表")
    return loaded


def tables_with_business_aliases(tables: Dict[str, LoadedTable]) -> Dict[str, LoadedTable]:
    aliased = dict(tables)
    if "scheduled_lessons" not in aliased and "historical_scheduled_lessons" in tables:
        source = tables["historical_scheduled_lessons"]
        aliased["scheduled_lessons"] = LoadedTable(
            "scheduled_lessons",
            source.source,
            list(source.rows),
        )
    return aliased


def payload_from_tables(tables: Dict[str, LoadedTable]) -> Dict[str, Any]:
    payload = {table: list(tables.get(table, LoadedTable(table, "", [])).rows) for table in TABLES}
    assignments_by_class: Dict[str, List[Dict[str, Any]]] = {}
    known_class_ids = {
        data_admin_server.normalize_text(row.get("id") or row.get("class_id"))
        for row in payload["classes"]
    }

    for assignment in payload["class_teacher_assignments"]:
        class_id = data_admin_server.normalize_text(assignment.get("class_id"))
        if not class_id:
            raise PipelineError("班级老师安排表存在缺少 class_id 的行")
        if known_class_ids and class_id not in known_class_ids:
            raise PipelineError(f"班级老师安排引用了不存在的班级: {class_id}")
        assignments_by_class.setdefault(class_id, []).append(assignment)

    for row in payload["classes"]:
        class_id = data_admin_server.normalize_text(row.get("id") or row.get("class_id"))
        row["teacher_assignments"] = assignments_by_class.get(class_id, [])

    payload.pop("class_teacher_assignments", None)
    return payload


def overlay_standard_tables_on_state(tables: Dict[str, LoadedTable]) -> Dict[str, Any]:
    state = data_admin_server.load_state()
    payload = {
        "schedule_windows": list(state.get("schedule_windows", [])),
        "time_slots": list(state.get("time_slots", [])),
        "teaching_areas": list(state.get("teaching_areas", [])),
        "rooms": list(state.get("rooms", [])),
        "teachers": list(state.get("teachers", [])),
        "teacher_unavailability": list(state.get("teacher_unavailability", [])),
        "products": list(state.get("products", [])),
        "product_courses": list(state.get("product_courses", [])),
        "product_schedule_rules": list(state.get("product_schedule_rules", [])),
        "classes": [],
        "class_window_boundaries": list(state.get("class_window_boundaries", [])),
        "class_teacher_assignments": [],
        "class_conflict_groups": list(state.get("class_conflict_groups", [])),
        "locked_scheduled_lessons": list(state.get("locked_scheduled_lessons", [])),
        "teaching_area_links": list(state.get("teaching_area_links", [])),
        "global_blackout_dates": list(state.get("global_blackout_dates", [])),
        "historical_scheduled_lessons": list(state.get("historical_scheduled_lessons", [])),
        "business_product_mappings": list(state.get("business_product_mappings", [])),
        "erp_standard_products": list(state.get("erp_standard_products", [])),
    }
    for table in TABLES:
        if table in tables:
            payload[table] = list(tables[table].rows)
    payload["classes"] = []
    return payload


def build_payload_from_tables(
    tables: Dict[str, LoadedTable],
    output_dir: Optional[Path] = None,
    timestamp: Optional[str] = None,
) -> tuple[Dict[str, Any], List[str], List[Path]]:
    if "business_classes" in tables:
        conversion_tables = tables_with_business_aliases(tables)
        base_payload = overlay_standard_tables_on_state(conversion_tables)
        result = convert_business_tables(conversion_tables, base_payload, output_dir=output_dir, timestamp=timestamp)
        return result.payload, result.warnings, result.generated_files
    return payload_from_tables(tables), [], []


def backup_data_dir(data_dir: Path, output_dir: Path, timestamp: str) -> Optional[Path]:
    if not data_dir.exists():
        return None
    backup_path = output_dir / "backups" / f"data_{timestamp}"
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(data_dir, backup_path)
    return backup_path


def validate_required_data(state: Dict[str, Any]) -> None:
    if not state["classes"]:
        raise PipelineError("缺少班级基础信息表，无法排课")
    if not state["rooms"]:
        raise PipelineError("缺少教室表，无法排课")
    if any(cls.get("product_id") for cls in state["classes"]) and not state["product_courses"]:
        raise PipelineError("班级引用了产品，但缺少产品课程课时表")


def validate_scheduler_input(state: Dict[str, Any], time_slots: List[Dict[str, Any]]) -> None:
    try:
        scheduler.load_input_data(data_admin_server.build_scheduler_input(state, time_slots=time_slots))
    except ValueError as exc:
        raise PipelineError(str(exc)) from exc


def parse_iso_date(value: str, label: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise PipelineError(f"{label} 需要使用 YYYY-MM-DD 格式: {value}") from exc


def expanded_rules_for_state(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    referenced_product_ids = {
        cls["product_id"] for cls in state["classes"] if cls.get("product_id")
    }
    catalog = data_admin_server.product_catalog(state["products"], state["product_courses"])
    return data_admin_server.scheduler_rules(
        state["product_schedule_rules"],
        referenced_product_ids,
        catalog,
    )


def latest_rule_end_date(product_id: str, expanded_rules: List[Dict[str, Any]]) -> str:
    candidates = [
        rule["end_date"]
        for rule in expanded_rules
        if rule.get("product_id") == product_id and rule.get("end_date")
    ]
    return max(candidates) if candidates else ""


def prepare_class_windows(state: Dict[str, Any], expanded_rules: List[Dict[str, Any]]) -> List[str]:
    warnings: List[str] = []
    for cls in state["classes"]:
        class_label = cls.get("name") or cls["id"]
        if not cls.get("start_date"):
            raise PipelineError(f"班级 {class_label} 缺少 start_date")
        parse_iso_date(cls["start_date"], f"班级 {class_label}/start_date")
        if not cls.get("start_period"):
            cls["start_period"] = "AM"
            warnings.append(f"班级 {class_label} 缺少 start_period，已按 AM 处理。")

        if not cls.get("end_date"):
            inferred_end_date = latest_rule_end_date(cls.get("product_id", ""), expanded_rules)
            if not inferred_end_date:
                raise PipelineError(f"班级 {class_label} 缺少 end_date，且没有可用的产品排课规则 end_date")
            cls["end_date"] = inferred_end_date
            warnings.append(f"班级 {class_label} 缺少 end_date，已按产品排课规则最晚日期 {inferred_end_date} 处理。")
        parse_iso_date(cls["end_date"], f"班级 {class_label}/end_date")
        if cls["end_date"] < cls["start_date"]:
            raise PipelineError(f"班级 {class_label} 的 end_date 早于 start_date")
        if not cls.get("end_period"):
            cls["end_period"] = "EVENING"
            warnings.append(f"班级 {class_label} 缺少 end_period，已按 EVENING 处理。")
    return warnings


def build_time_slots(
    state: Dict[str, Any],
    excluded_weekdays: Set[int],
    slot_set: str,
    sunday_policy: str = "summer-only",
) -> List[Dict[str, Any]]:
    start = min(parse_iso_date(cls["start_date"], f"班级 {cls['id']}/start_date") for cls in state["classes"])
    end = max(parse_iso_date(cls["end_date"], f"班级 {cls['id']}/end_date") for cls in state["classes"])
    return generate_time_slots(start, end, excluded_weekdays, slot_set, sunday_policy)


def time_slots_for_state(
    state: Dict[str, Any],
    excluded_weekdays: Set[int],
    slot_set: str,
    sunday_policy: str = "summer-only",
) -> tuple[List[Dict[str, Any]], Optional[str]]:
    if state.get("time_slots"):
        return list(state["time_slots"]), f"已使用上传/后台课节表 {len(state['time_slots'])} 行。"
    return build_time_slots(state, excluded_weekdays, slot_set, sunday_policy), None


def available_time_slots(
    state: Dict[str, Any],
    time_slots: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    return [
        slot for slot in time_slots
        if data_admin_server.slot_is_usable(slot)
        and not data_admin_server.slot_is_blackout(slot, state["global_blackout_dates"])
    ]


def report_table_names(tables: Dict[str, LoadedTable]) -> List[str]:
    names = list(REPORT_TABLES)
    names.extend(table for table in COMPATIBILITY_REPORT_TABLES if table in tables)
    return names


def sanitize_markdown_table_cell(value: object) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip()


def write_report(
    path: Path,
    *,
    source: Path,
    tables: Dict[str, LoadedTable],
    row_counts: Dict[str, int],
    warnings: List[str],
    backup_path: Optional[Path],
    scheduler_input_path: Optional[Path],
    schedule_csv_path: Optional[Path],
    schedule_html_path: Optional[Path],
    generated_files: Optional[List[Path]] = None,
    missing_teacher_rows: Optional[List[Dict[str, str]]] = None,
    error: Optional[str] = None,
) -> None:
    lines = [
        "# 排课导入报告",
        "",
        f"- 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 源数据: {source}",
    ]
    if backup_path:
        lines.append(f"- 数据备份: {backup_path}")
    if error:
        lines.append(f"- 状态: 失败")
        lines.append(f"- 错误: {error}")
    else:
        lines.append("- 状态: 成功")
    lines.extend(["", "## 数据表"])
    for table in report_table_names(tables):
        loaded = tables.get(table)
        source_text = loaded.source if loaded else "未提供"
        lines.append(f"- {table}: {row_counts.get(table, 0)} 行 ({source_text})")
    if warnings:
        lines.extend(["", "## 提示"])
        lines.extend(f"- {warning}" for warning in warnings)
    if missing_teacher_rows:
        lines.extend(["", "## 缺老师补录摘要"])
        lines.append(f"- 缺口数量: {len(missing_teacher_rows)}")
        lines.append("- 请下载 `missing_class_teacher_assignments_*.csv` 补齐老师后重新校验。")
        lines.extend(["", "| 班级 | 产品 | 科目 | 阶段 | 课程组 |", "| --- | --- | --- | --- | --- |"])
        for row in missing_teacher_rows[:30]:
            lines.append(
                "| "
                + " | ".join(
                    sanitize_markdown_table_cell(
                        row.get(field, "")
                    )
                    for field in ("class_name", "product_name", "subject", "stage", "course_group")
                )
                + " |"
            )
        if len(missing_teacher_rows) > 30:
            lines.append(f"- 仅展示前 30 条，另有 {len(missing_teacher_rows) - 30} 条请查看补录 CSV。")
    if scheduler_input_path or schedule_csv_path or schedule_html_path:
        lines.extend(["", "## 输出"])
        if scheduler_input_path:
            lines.append(f"- 排课输入: {scheduler_input_path}")
        if schedule_csv_path:
            lines.append(f"- CSV 明细: {schedule_csv_path}")
        if schedule_html_path:
            lines.append(f"- HTML 甘特图: {schedule_html_path}")
    if generated_files:
        lines.extend(["", "## 生成参考文件"])
        lines.extend(f"- {path}" for path in generated_files)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def class_teacher_template_context(state: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, str]]:
    if not state:
        return {}
    product_meta = data_admin_server.product_catalog(state.get("products", []), state.get("product_courses", []))
    context: Dict[str, Dict[str, str]] = {}
    for cls in state.get("classes", []):
        class_id = str(cls.get("id") or "").strip()
        if not class_id:
            continue
        product_id = str(cls.get("product_id") or "").strip()
        meta = product_meta.get(product_id, {})
        context[class_id] = {
            "class_name": str(cls.get("name") or "").strip(),
            "product_id": product_id,
            "product_name": str(meta.get("name") or cls.get("product_name") or "").strip(),
        }
    return context


def parse_missing_teacher_requirements(error: str) -> List[MissingTeacherRequirement]:
    requirements: List[MissingTeacherRequirement] = []
    seen: Set[tuple[str, str, str, str, str]] = set()
    for line in error.splitlines():
        line = line.strip()
        class_id = ""
        product_id = ""
        labels_text = ""
        if line.startswith("班级 ") and "缺少课程老师安排:" in line:
            class_text, _, labels_text = line.partition("缺少课程老师安排:")
            class_text = class_text.removeprefix("班级 ").strip()
        elif line.startswith("班级 ") and " 缺少 " in line and " 的老师安排" in line:
            class_text, _, labels_text = line.partition(" 缺少 ")
            class_text = class_text.removeprefix("班级 ").strip()
            labels_text = labels_text.removesuffix(" 的老师安排")
        else:
            continue
        if " 的产品 " in class_text:
            class_id, _, product_id = class_text.partition(" 的产品 ")
            class_id = class_id.strip()
            product_id = product_id.strip()
        else:
            class_id = class_text.strip()
        for label in re.split(r"[、，,；;]+", labels_text):
            parts = [part.strip() for part in label.strip().split("/") if part.strip()]
            if len(parts) < 3:
                continue
            subject, stage = parts[0], parts[1]
            course_group = "/".join(parts[2:])
            key = (class_id, product_id, subject, stage, course_group)
            if key in seen:
                continue
            seen.add(key)
            requirements.append(
                MissingTeacherRequirement(
                    class_id=class_id,
                    product_id=product_id,
                    subject=subject,
                    stage=stage,
                    course_group=course_group,
                )
            )
    return requirements


def missing_teacher_template_rows(
    error: str,
    state: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, str]]:
    return missing_teacher_rows_for_requirements(
        parse_missing_teacher_requirements(error),
        state,
    )


def missing_teacher_rows_for_requirements(
    requirements: Sequence[MissingTeacherRequirement],
    state: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, str]]:
    context = class_teacher_template_context(state)
    product_names = {
        product_id: str(meta.get("name") or "").strip()
        for product_id, meta in data_admin_server.product_catalog(
            state.get("products", []),
            state.get("product_courses", []),
        ).items()
    } if state else {}
    rows: List[Dict[str, str]] = []
    for requirement in requirements:
        class_context = context.get(requirement.class_id, {})
        class_product_id = class_context.get("product_id", "")
        product_id = requirement.product_id or class_product_id
        if requirement.product_id:
            product_name = product_names.get(product_id, "")
            if not product_name and product_id == class_product_id:
                product_name = class_context.get("product_name", "")
        else:
            product_name = class_context.get("product_name", "") or product_names.get(product_id, "")
        rows.append(
            {
                "class_id": requirement.class_id,
                "class_name": class_context.get("class_name", ""),
                "product_id": product_id,
                "product_name": product_name,
                "subject": requirement.subject,
                "stage": requirement.stage,
                "course_group": requirement.course_group,
                "class_schedule_mode": "本班实际排课",
                "actual_scheduled_class_id": requirement.class_id,
                "teacher_id": "",
                "teacher_name": "",
                "assignment_extra_time_requirement": "",
                "notes": "上传前校验自动生成，请补齐老师后重新上传",
            }
        )
    return rows


def write_missing_teacher_template(
    output_dir: Path,
    timestamp: str,
    error: str,
    state: Optional[Dict[str, Any]] = None,
) -> Optional[Path]:
    return write_missing_teacher_rows_template(
        output_dir,
        timestamp,
        missing_teacher_template_rows(error, state),
    )


def write_missing_teacher_rows_template(
    output_dir: Path,
    timestamp: str,
    rows: List[Dict[str, str]],
) -> Optional[Path]:
    if not rows:
        return None

    path = output_dir / f"missing_class_teacher_assignments_{timestamp}.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=data_admin_server.TEACHER_ASSIGNMENT_FIELDNAMES,
        )
        writer.writeheader()
        writer.writerows(rows)
    return path


def run_pipeline(args: argparse.Namespace) -> PipelineResult:
    timestamp = args.timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    source = Path(args.source).resolve()
    data_dir = Path(args.data_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"import_report_{timestamp}.md"

    data_admin_server.DATA_DIR = data_dir

    tables: Dict[str, LoadedTable] = {}
    row_counts = {table: 0 for table in SOURCE_TABLES}
    warnings: List[str] = []
    backup_path: Optional[Path] = None
    scheduler_input_path: Optional[Path] = None
    schedule_csv_path: Optional[Path] = None
    schedule_html_path: Optional[Path] = None
    generated_files: List[Path] = []
    state: Optional[Dict[str, Any]] = None
    missing_teacher_rows: List[Dict[str, str]] = []

    try:
        tables = load_source_tables(source)
        row_counts = {table: len(loaded.rows) for table, loaded in tables.items()}
        for table in SOURCE_TABLES:
            row_counts.setdefault(table, 0)

        payload, conversion_warnings, generated_files = build_payload_from_tables(tables, output_dir, timestamp)
        warnings.extend(conversion_warnings)
        state = data_admin_server.normalize_payload(payload)
        validate_required_data(state)

        expanded_rules = expanded_rules_for_state(state)
        warnings.extend(prepare_class_windows(state, expanded_rules))
        time_slots, time_slot_warning = time_slots_for_state(
            state,
            parse_weekdays(args.exclude_weekdays),
            args.slot_set,
            getattr(args, "sunday_policy", "summer-only"),
        )
        if time_slot_warning:
            warnings.append(time_slot_warning)
        if not available_time_slots(state, time_slots):
            raise PipelineError("没有可用课节，请检查 02_课节表 is_usable 或 16_全局停课日期表。")
        validate_scheduler_input(state, time_slots)
        backup_path = backup_data_dir(data_dir, output_dir, timestamp)

        data_admin_server.save_state(state)
        export_result = data_admin_server.export_scheduler_input(state, time_slots=time_slots)
        scheduler_input_path = Path(export_result["path"])
        pending_schedule_csv_path = output_dir / f"schedule_{timestamp}.csv"
        pending_schedule_html_path = output_dir / f"schedule_{timestamp}.html"

        schedule_input = scheduler.load_input(scheduler_input_path)
        assignments = scheduler.schedule(schedule_input)
        scheduler.write_csv(assignments, pending_schedule_csv_path, schedule_input)
        scheduler.write_html(assignments, schedule_input, pending_schedule_html_path)
        schedule_csv_path = pending_schedule_csv_path
        schedule_html_path = pending_schedule_html_path

        write_report(
            report_path,
            source=source,
            tables=tables,
            row_counts=row_counts,
            warnings=warnings,
            backup_path=backup_path,
            scheduler_input_path=scheduler_input_path,
            schedule_csv_path=schedule_csv_path,
            schedule_html_path=schedule_html_path,
            generated_files=generated_files,
        )
    except Exception as exc:
        if isinstance(exc, BusinessDataError):
            warnings.extend(warning for warning in exc.warnings if warning not in warnings)
        missing_teacher_requirements = parse_missing_teacher_requirements(str(exc))
        missing_teacher_rows = missing_teacher_rows_for_requirements(missing_teacher_requirements, state)
        if missing_teacher_rows:
            missing_teacher_path = write_missing_teacher_rows_template(
                output_dir,
                timestamp,
                missing_teacher_rows,
            )
            generated_files.append(missing_teacher_path)
        write_report(
            report_path,
            source=source,
            tables=tables,
            row_counts=row_counts,
            warnings=warnings,
            backup_path=backup_path,
            scheduler_input_path=scheduler_input_path,
            schedule_csv_path=schedule_csv_path,
            schedule_html_path=schedule_html_path,
            generated_files=generated_files,
            missing_teacher_rows=missing_teacher_rows,
            error=str(exc),
        )
        raise

    return PipelineResult(
        scheduler_input_path=scheduler_input_path,
        schedule_csv_path=schedule_csv_path,
        schedule_html_path=schedule_html_path,
        report_path=report_path,
        backup_path=backup_path,
        row_counts=row_counts,
        warnings=warnings,
        generated_files=generated_files,
    )


def run_preflight(args: argparse.Namespace) -> PreflightResult:
    timestamp = args.timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    source = Path(args.source).resolve()
    data_dir = Path(args.data_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"preflight_report_{timestamp}.md"

    data_admin_server.DATA_DIR = data_dir
    tables: Dict[str, LoadedTable] = {}
    row_counts = {table: 0 for table in SOURCE_TABLES}
    warnings: List[str] = []
    generated_files: List[Path] = []
    state: Optional[Dict[str, Any]] = None
    error = ""
    passed = False
    missing_teacher_requirements: List[MissingTeacherRequirement] = []
    missing_teacher_rows: List[Dict[str, str]] = []

    try:
        tables = load_source_tables(source)
        row_counts = {table: len(loaded.rows) for table, loaded in tables.items()}
        for table in SOURCE_TABLES:
            row_counts.setdefault(table, 0)
        payload, conversion_warnings, generated_files = build_payload_from_tables(tables, output_dir, timestamp)
        warnings.extend(conversion_warnings)
        state = data_admin_server.normalize_payload(payload)
        validate_required_data(state)
        expanded_rules = expanded_rules_for_state(state)
        warnings.extend(prepare_class_windows(state, expanded_rules))
        time_slots, time_slot_warning = time_slots_for_state(
            state,
            parse_weekdays(args.exclude_weekdays),
            args.slot_set,
            getattr(args, "sunday_policy", "summer-only"),
        )
        if time_slot_warning:
            warnings.append(time_slot_warning)
        if not available_time_slots(state, time_slots):
            raise PipelineError("上传前校验未找到任何可用课节，请检查 02_课节表 is_usable 或 16_全局停课日期表。")
        validate_scheduler_input(state, time_slots)
        passed = True
    except Exception as exc:
        if isinstance(exc, BusinessDataError):
            warnings.extend(warning for warning in exc.warnings if warning not in warnings)
        error = str(exc)

    if error:
        missing_teacher_requirements = parse_missing_teacher_requirements(error)
        missing_teacher_rows = missing_teacher_rows_for_requirements(missing_teacher_requirements, state)
        if missing_teacher_rows:
            missing_teacher_path = write_missing_teacher_rows_template(
                output_dir,
                timestamp,
                missing_teacher_rows,
            )
            generated_files.append(missing_teacher_path)

    write_report(
        report_path,
        source=source,
        tables=tables,
        row_counts=row_counts,
        warnings=warnings,
        backup_path=None,
        scheduler_input_path=None,
        schedule_csv_path=None,
        schedule_html_path=None,
        generated_files=generated_files,
        missing_teacher_rows=missing_teacher_rows,
        error=None if passed else error,
    )
    return PreflightResult(
        passed=passed,
        report_path=report_path,
        row_counts=row_counts,
        warnings=warnings,
        generated_files=generated_files,
        missing_teacher_requirements=missing_teacher_requirements,
        missing_teacher_rows=missing_teacher_rows,
        error=error,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="从混合 Excel/CSV 源数据导入并生成排课结果")
    parser.add_argument("--source", required=True, help="源数据目录或单个 Excel/CSV 文件")
    parser.add_argument("--data-dir", default="data", help="写入的数据目录，默认 data")
    parser.add_argument("--output-dir", default="outputs", help="输出目录，默认 outputs")
    parser.add_argument("--timestamp", help="可选：固定输出时间戳，便于测试")
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="只执行上传前校验并生成预检报告，不写入 data/，不正式排课",
    )
    parser.add_argument(
        "--exclude-weekdays",
        default="Sun",
        help="生成课节时排除的星期，用逗号分隔，默认 Sun",
    )
    parser.add_argument(
        "--slot-set",
        choices=["all", "day", "evening"],
        default="all",
        help="生成课节范围，默认 all",
    )
    parser.add_argument(
        "--sunday-policy",
        choices=["always", "summer-only"],
        default="summer-only",
        help="周日课节策略：always=全程排除周日，summer-only=仅 7-8 月排除周日，默认 summer-only",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    timestamp = args.timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    args.timestamp = timestamp
    output_dir = Path(args.output_dir).resolve()
    report_path = output_dir / f"preflight_report_{timestamp}.md" if args.preflight else output_dir / f"import_report_{timestamp}.md"
    if args.preflight:
        try:
            result = run_preflight(args)
        except Exception as exc:
            if not report_path.exists():
                write_report(
                    report_path,
                    source=Path(args.source).resolve(),
                    tables={},
                    row_counts={table: 0 for table in SOURCE_TABLES},
                    warnings=[],
                    backup_path=None,
                    scheduler_input_path=None,
                    schedule_csv_path=None,
                    schedule_html_path=None,
                    generated_files=[],
                    error=str(exc),
                )
            print(f"上传前校验失败: {exc}", file=sys.stderr)
            print(f"预检报告: {report_path}", file=sys.stderr)
            raise SystemExit(1) from None

        if result.passed:
            print("上传前校验通过")
        else:
            print("上传前校验未通过", file=sys.stderr)
        print(f"预检报告: {result.report_path}")
        if result.generated_files:
            print("参考文件:")
            for path in result.generated_files:
                print(f"- {path}")
        if result.missing_teacher_rows:
            print(f"缺老师补录: {len(result.missing_teacher_rows)} 条")
        if result.error:
            print(f"错误摘要: {result.error.splitlines()[0]}", file=sys.stderr)
        raise SystemExit(0 if result.passed else 1)

    try:
        result = run_pipeline(args)
    except Exception as exc:
        if not report_path.exists():
            write_report(
                report_path,
                source=Path(args.source).resolve(),
                tables={},
                row_counts={table: 0 for table in SOURCE_TABLES},
                warnings=[],
                backup_path=None,
                scheduler_input_path=None,
                schedule_csv_path=None,
                schedule_html_path=None,
                generated_files=[],
                error=str(exc),
            )
        print(f"排课闭环失败: {exc}", file=sys.stderr)
        print(f"失败报告: {report_path}", file=sys.stderr)
        raise SystemExit(1) from None

    print(f"排课输入: {result.scheduler_input_path}")
    print(f"CSV 明细: {result.schedule_csv_path}")
    print(f"HTML 甘特图: {result.schedule_html_path}")
    print(f"导入报告: {result.report_path}")
    if result.backup_path:
        print(f"数据备份: {result.backup_path}")


if __name__ == "__main__":
    main()
