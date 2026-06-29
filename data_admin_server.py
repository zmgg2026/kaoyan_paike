#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import csv
import html as html_lib
import io
import json
import mimetypes
import re
import subprocess
import sys
import threading
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import quote, unquote, urlparse

from scripts.csv_utils import csv_rows_text, serialize_csv_value, write_csv_rows
from scripts.field_utils import (
    normalize_blank_marker,
    normalize_float,
    normalize_int,
    normalize_date_text,
    normalize_text,
    normalize_time_text,
    parse_bool as normalize_bool,
    row_value,
    split_delimited_values,
    split_pipe_values as split_id_list,
)
from scripts.product_catalog import (
    DEFAULT_STAGE_ORDER,
    DEFAULT_STAGE_ORDER_INDEX,
    first_non_empty,
    infer_capacity_type,
    infer_product_line,
    infer_project,
    infer_sub_product,
    infer_unique_value,
    label_text,
    product_catalog,
    product_stage_order,
    sort_stage_values,
    stage_order_for_context,
    stage_sort_key,
    unique_non_empty,
)
from scripts.schedule_modes import (
    assignment_is_shared,
    assignment_reference_class_id,
    assignment_schedule_mode,
    class_schedule_mode_display_name,
)
from scripts.table_schema import (
    BUSINESS_PRODUCT_MAPPING_FIELDNAMES,
    CLASS_CONFLICT_GROUP_FIELDNAMES,
    CLASS_FIELDNAMES,
    CLASS_JSON_EXTRA_FIELDNAMES,
    CLASS_WINDOW_BOUNDARY_FIELDNAMES,
    ERP_STANDARD_PRODUCT_FIELDNAMES,
    GLOBAL_BLACKOUT_FIELDNAMES,
    HISTORICAL_SCHEDULED_LESSON_FIELDNAMES,
    LOCKED_SCHEDULED_LESSON_FIELDNAMES,
    PRODUCT_COURSE_FIELDNAMES,
    PRODUCT_FIELDNAMES,
    PRODUCT_RULE_FIELDNAMES,
    ROOM_FIELDNAMES,
    SCHEDULE_WINDOW_FIELDNAMES,
    STANDARD_TABLE_FIELDNAMES,
    TABLES_WITH_EMPTY_WARNINGS,
    TEACHER_ASSIGNMENT_FIELDNAMES,
    TEACHER_FIELDNAMES,
    TEACHER_UNAVAILABILITY_FIELDNAMES,
    TEACHING_AREA_FIELDNAMES,
    TEACHING_AREA_LINK_FIELDNAMES,
    TIME_SLOT_FIELDNAMES,
)
from scripts.window_utils import expanded_window_tokens


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
WEB_DIR = ROOT / "web_admin"
OUTPUT_DIR = ROOT / "outputs"
DOCS_DIR = ROOT / "docs"
SHARE_DIR = ROOT / "share"
DEFAULT_TIME_SLOTS = ROOT / "examples" / "summer_2026_time_slots.json"
PIPELINE_JOBS: Dict[str, Dict[str, Any]] = {}
PIPELINE_JOBS_LOCK = threading.Lock()
BATCH_SCHEDULE_JOBS: Dict[str, Dict[str, Any]] = {}
BATCH_SCHEDULE_JOBS_LOCK = threading.Lock()
BATCH_SCHEDULE_SCRIPT = ROOT / "scripts" / "build_camp_maintenance_schedule.py"
BATCH_SCHEDULE_PYTHON = Path(sys.executable)
ALLOWED_UPLOAD_SUFFIXES = {".csv", ".xlsx", ".xlsm"}
EMPLOYEE_ID_PATTERN = re.compile(r"^\d{6}$")
PUBLIC_TEACHER_SUBJECTS = {"英语", "政治", "数学", "语文"}
STATE_TABLE_ALIASES: Dict[str, Tuple[str, ...]] = {
    "class_conflict_groups": ("conflict_groups",),
    "locked_scheduled_lessons": ("scheduled_lessons",),
    "teaching_area_links": ("links",),
}


def today_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_json(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def csv_escape(value: Any) -> str:
    return serialize_csv_value(value)


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    write_csv_rows(path, fieldnames, rows, encoding="utf-8", value_formatter=csv_escape)


def csv_text(rows: List[Dict[str, Any]], fieldnames: List[str]) -> str:
    return csv_rows_text(fieldnames, rows, bom=True, value_formatter=csv_escape)


def unique_list(values: Iterable[str]) -> List[str]:
    seen: Set[str] = set()
    result: List[str] = []
    for value in values:
        text = normalize_text(value)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def is_employee_id(value: Any) -> bool:
    return bool(EMPLOYEE_ID_PATTERN.match(normalize_text(value)))


def teacher_subject_type(primary_subject: Any) -> str:
    subject = normalize_text(primary_subject)
    if not subject:
        return ""
    return "公共课" if subject in PUBLIC_TEACHER_SUBJECTS else "专业课"


def normalize_teacher_identity_label(value: Any) -> str:
    text = normalize_text(value)
    if text in {"教学管理者", "管理者"}:
        return "管理者"
    if text in {"普通教师", "教师"}:
        return "教师"
    return ""


def looks_like_exam_month(value: str) -> bool:
    text = normalize_text(value)
    return len(text) == 7 and text[4] == "-" and text[:4].isdigit() and text[5:7].isdigit()


def exam_season_from_month(value: str) -> str:
    text = normalize_text(value)
    if not looks_like_exam_month(text):
        return ""
    year = int(text[:4])
    month = int(text[5:7])
    exam_year = year + 1 if month == 12 else year
    return f"{exam_year % 100:02d}考研"


def normalize_exam_season(value: Any) -> str:
    text = normalize_text(value)
    if looks_like_exam_month(text):
        return exam_season_from_month(text)
    return text.replace("考季", "考研")


def infer_suite_code_from_class_name(value: Any) -> str:
    text = normalize_text(value)
    match = re.search(r"(\d{2})届\s*(\d{1,2})班", text)
    if not match:
        return ""
    return f"{match.group(1)}{int(match.group(2)):02d}"


def is_shared_teacher_assignment(assignment: Dict[str, Any]) -> bool:
    return assignment_is_shared(assignment)


def infer_teaching_area_short_name(*values: Any) -> str:
    text = first_non_empty(values)
    if not text:
        return ""
    short = text.split("-")[-1].strip()
    short = re.sub(r"[（(].*?[）)]", "", short).strip()
    for suffix in ("校区", "基地", "教学区", "教室"):
        if short.endswith(suffix) and len(short) > len(suffix):
            short = short[: -len(suffix)].strip()
    return short or text


def infer_teaching_area_region_tag(*values: Any) -> str:
    text = first_non_empty(values)
    if not text:
        return ""
    if text.startswith("蜀山-") or "蜀山" in text:
        return "蜀山"
    if text.startswith("经开-") or any(keyword in text for keyword in ("经开", "翡翠湖", "大学城", "三创园", "磬苑", "迎宾馆", "始信路")):
        return "经开/翡翠湖"
    if text.startswith("新站-") or "新站" in text:
        return "新站"
    if "芜湖" in text:
        return "芜湖"
    if "线上" in text or "网络教学区" in text:
        return "线上"
    if "未划分" in text:
        return "未划分"
    if "集训营" in text:
        return "集训营基地"
    return ""


def state_table_doc_default(table_name: str) -> Dict[str, Any]:
    return {table_name: []}


def state_table_rows_from_doc(table_name: str, document: Dict[str, Any]) -> List[Dict[str, Any]]:
    for key in (table_name, *STATE_TABLE_ALIASES.get(table_name, ())):
        rows = document.get(key)
        if isinstance(rows, list):
            return rows
    return []


def read_state_table_rows(table_name: str) -> List[Dict[str, Any]]:
    document = read_json(DATA_DIR / f"{table_name}.json", state_table_doc_default(table_name))
    return state_table_rows_from_doc(table_name, document)


def load_standard_table_rows() -> Dict[str, List[Dict[str, Any]]]:
    return {table_name: read_state_table_rows(table_name) for table_name in STANDARD_TABLE_FIELDNAMES}


def attach_class_teacher_assignment_table(
    classes: List[Dict[str, Any]],
    assignment_rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if not assignment_rows:
        return classes

    assignments_by_class: Dict[str, List[Dict[str, Any]]] = {}
    for assignment in assignment_rows:
        class_id = normalize_text(assignment.get("class_id"))
        if not class_id:
            continue
        assignments_by_class.setdefault(class_id, []).append(
            normalize_teacher_assignment({"class_id": class_id, **assignment})
        )

    updated_classes = []
    for cls in classes:
        class_id = normalize_text(cls.get("id") or cls.get("class_id"))
        if class_id in assignments_by_class:
            updated_classes.append({**cls, "teacher_assignments": assignments_by_class[class_id]})
        else:
            updated_classes.append(cls)
    return updated_classes


def load_state() -> Dict[str, Any]:
    table_rows = load_standard_table_rows()
    product_courses = table_rows["product_courses"]
    products = merge_products(table_rows["products"], product_courses)
    classes = attach_class_teacher_assignment_table(
        table_rows["classes"],
        table_rows["class_teacher_assignments"],
    )
    class_teacher_assignments = class_teacher_assignment_rows({"classes": classes})

    return {
        "updated_at": today_text(),
        "schedule_windows": table_rows["schedule_windows"],
        "time_slots": table_rows["time_slots"],
        "teaching_areas": table_rows["teaching_areas"],
        "rooms": table_rows["rooms"],
        "teachers": table_rows["teachers"],
        "teacher_unavailability": table_rows["teacher_unavailability"],
        "products": products,
        "product_courses": product_courses,
        "product_schedule_rules": table_rows["product_schedule_rules"],
        "classes": classes,
        "class_window_boundaries": table_rows["class_window_boundaries"],
        "class_teacher_assignments": class_teacher_assignments,
        "class_conflict_groups": table_rows["class_conflict_groups"],
        "locked_scheduled_lessons": table_rows["locked_scheduled_lessons"],
        "teaching_area_links": table_rows["teaching_area_links"],
        "global_blackout_dates": table_rows["global_blackout_dates"],
        "historical_scheduled_lessons": table_rows["historical_scheduled_lessons"],
        "business_product_mappings": table_rows["business_product_mappings"],
        "erp_standard_products": table_rows["erp_standard_products"],
        "lookups": build_lookups(
            table_rows["teaching_areas"],
            table_rows["rooms"],
            products,
            table_rows["teachers"],
            product_courses,
            classes,
        ),
    }


def build_lookups(
    teaching_areas: List[Dict[str, Any]],
    rooms: List[Dict[str, Any]],
    products: List[Dict[str, Any]],
    teachers: List[Dict[str, Any]],
    product_courses: List[Dict[str, Any]],
    classes: List[Dict[str, Any]],
) -> Dict[str, Any]:
    product_map = product_lookup_map(products, product_courses)
    subjects, quarters, stages, modules, groups = course_lookup_sets(product_courses)
    teacher_map = teacher_lookup_map(teachers, classes)

    return {
        "products": product_lookup_rows(product_map),
        "product_lines": ["考研复试", "考研集训营", "考研无忧", "考研个性化", "考研其他", "专升本", "四六级"],
        "subjects": sorted(subjects),
        "quarters": sorted(quarters),
        "stages": sort_stage_values(stages),
        "course_modules": sorted(modules),
        "course_groups": sorted(groups),
        "course_name_tags": load_course_name_tags(product_courses),
        "teachers": [teacher_map[teacher_id] for teacher_id in sorted(teacher_map)],
        "teaching_area_regions": sorted(
            {
                normalize_text(area.get("region_tag"))
                for area in teaching_areas
                if normalize_text(area.get("region_tag"))
            }
        ),
        "active_teaching_area_count": sum(1 for area in teaching_areas if normalize_bool(area.get("is_active"))),
        "active_room_count": sum(1 for room in rooms if normalize_bool(room.get("is_active"))),
    }


def product_lookup_map(
    products: List[Dict[str, Any]],
    product_courses: List[Dict[str, Any]],
) -> Dict[str, Dict[str, str]]:
    product_map: Dict[str, Dict[str, str]] = {}
    for product in products:
        product_id = normalize_text(product.get("id"))
        if product_id:
            name = normalize_text(product.get("name")) or product_id
            product_map[product_id] = {
                "name": name,
                "project": normalize_text(product.get("project")) or infer_project(name),
                "product_line": normalize_text(product.get("product_line")) or infer_product_line(name),
                "sub_product": normalize_text(product.get("sub_product")),
                "product_system": normalize_text(product.get("product_system")),
                "course_nature": normalize_text(product.get("course_nature")),
                "subject": normalize_text(product.get("subject")),
                "subject_category": normalize_text(product.get("subject_category")),
                "standard_capacity": normalize_text(product.get("standard_capacity")),
                "capacity_type": normalize_text(product.get("capacity_type")),
            }

    for course in product_courses:
        product_id = normalize_text(course.get("product_id"))
        if product_id and product_id not in product_map:
            product_map[product_id] = product_lookup_from_course(course, product_id)
    return product_map


def product_lookup_from_course(course: Dict[str, Any], product_id: str) -> Dict[str, str]:
    name = normalize_text(course.get("product_name")) or product_id
    return {
        "name": name,
        "project": normalize_text(course.get("project")) or infer_project(name),
        "product_line": normalize_text(course.get("product_line")) or infer_product_line(name),
        "sub_product": normalize_text(course.get("sub_product")),
        "product_system": normalize_text(course.get("product_system")),
        "course_nature": normalize_text(course.get("course_nature")),
        "subject": "",
        "subject_category": "",
        "standard_capacity": normalize_text(course.get("standard_capacity")),
        "capacity_type": normalize_text(course.get("capacity_type")),
    }


def course_lookup_sets(product_courses: List[Dict[str, Any]]) -> Tuple[Set[str], Set[str], Set[str], Set[str], Set[str]]:
    subjects: Set[str] = set()
    quarters: Set[str] = set()
    stages: Set[str] = set()
    modules: Set[str] = set()
    groups: Set[str] = set()
    for course in product_courses:
        for key, bucket in (
            ("subject", subjects),
            ("window_name", quarters),
            ("stage", stages),
            ("course_module", modules),
            ("course_group", groups),
        ):
            value = normalize_text(course.get(key))
            if key == "window_name" and not value:
                value = normalize_text(course.get("quarter"))
            if value:
                bucket.add(value)
    return subjects, quarters, stages, modules, groups


def teacher_lookup_map(teachers: List[Dict[str, Any]], classes: List[Dict[str, Any]]) -> Dict[str, Dict[str, str]]:
    teacher_map: Dict[str, Dict[str, str]] = {}
    for teacher in teachers:
        teacher_id = normalize_text(teacher.get("id") or teacher.get("employee_id"))
        if teacher_id:
            teacher_map[teacher_id] = {
                "id": teacher_id,
                "name": normalize_text(teacher.get("name")) or teacher_id,
                "project": normalize_text(teacher.get("project")),
                "primary_subject": normalize_text(teacher.get("primary_subject")),
            }

    for cls in classes:
        for assignment in cls.get("teacher_assignments", []):
            teacher_id = normalize_text(assignment.get("teacher_id"))
            if teacher_id and teacher_id not in teacher_map:
                teacher_map[teacher_id] = {
                    "id": teacher_id,
                    "name": normalize_text(assignment.get("teacher_name")) or teacher_id,
                    "project": "",
                    "primary_subject": "",
                }
    return teacher_map


def product_lookup_rows(product_map: Dict[str, Dict[str, str]]) -> List[Dict[str, str]]:
    return [
        {
            "id": product_id,
            "name": product["name"],
            "project": product["project"],
            "product_line": product["product_line"],
            "sub_product": product["sub_product"],
            "product_system": product["product_system"],
            "course_nature": product["course_nature"],
            "subject": product["subject"],
            "subject_category": product["subject_category"],
            "standard_capacity": product["standard_capacity"],
            "capacity_type": product["capacity_type"],
        }
        for product_id, product in sorted(product_map.items())
    ]


def load_course_name_tags(product_courses: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    tags_by_code: Dict[str, Dict[str, str]] = {}
    mapping_path = DATA_DIR / "course_name_product_course_map_draft.csv"
    if mapping_path.exists():
        with mapping_path.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                course_code = normalize_text(row.get("course_code"))
                course_name = normalize_text(row.get("course_name"))
                if not course_code or not course_name:
                    continue
                tags_by_code.setdefault(
                    course_code,
                    {
                        "course_code": course_code,
                        "course_name": course_name,
                        "subject": normalize_text(row.get("mapped_subject")),
                        "stage": normalize_text(row.get("mapped_stage")),
                        "course_module": normalize_text(row.get("mapped_course_module")),
                        "course_group": normalize_text(row.get("mapped_course_group_suggestion")),
                        "status": normalize_text(row.get("status")),
                    },
                )

    for course in product_courses:
        course_code = normalize_text(course.get("course_code"))
        course_name = normalize_text(course.get("course_name"))
        if not course_code or not course_name:
            continue
        tags_by_code[course_code] = {
            "course_code": course_code,
            "course_name": course_name,
            "subject": normalize_text(course.get("subject")),
            "stage": normalize_text(course.get("stage")),
            "course_module": normalize_text(course.get("course_module")),
            "course_group": normalize_text(course.get("course_group")),
            "status": "产品课程当前使用",
        }

    return sorted(
        tags_by_code.values(),
        key=lambda item: (
            item.get("subject", ""),
            item.get("course_module", ""),
            item.get("course_name", ""),
            item.get("course_code", ""),
        ),
    )


def derive_products_from_courses(product_courses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for course in product_courses:
        product_id = normalize_text(course.get("product_id"))
        if product_id:
            grouped.setdefault(product_id, []).append(course)

    products: List[Dict[str, Any]] = []
    for product_id, courses in sorted(grouped.items()):
        product_name = first_non_empty(course.get("product_name") for course in courses) or product_id
        project = first_non_empty(course.get("project") for course in courses) or infer_project(product_name)
        product_line = first_non_empty(course.get("product_line") for course in courses) or infer_product_line(product_name, project=project)
        standard_capacity = normalize_int(first_non_empty(course.get("standard_capacity") for course in courses))
        products.append(
            {
                "id": product_id,
                "name": product_name,
                "project": project,
                "product_line": product_line,
                "sub_product": first_non_empty(course.get("sub_product") for course in courses)
                or infer_sub_product(product_line, product_name),
                "product_system": first_non_empty(course.get("product_system") for course in courses),
                "standard_capacity": standard_capacity,
                "capacity_type": first_non_empty(course.get("capacity_type") for course in courses)
                or infer_capacity_type(standard_capacity),
                "subject": infer_unique_value(course.get("subject") for course in courses),
                "subject_category": infer_unique_value(course.get("subject_category") for course in courses),
                "course_nature": first_non_empty(course.get("course_nature") for course in courses),
                "notes": "",
            }
        )
    return products


def merge_products(products: List[Dict[str, Any]], product_courses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    derived = {product["id"]: product for product in derive_products_from_courses(product_courses)}
    merged: Dict[str, Dict[str, Any]] = {}
    for product in products:
        normalized = normalize_product(product)
        product_id = normalized["id"]
        if not product_id:
            continue
        fallback = derived.get(product_id, {})
        for key, value in fallback.items():
            if key not in normalized or normalized[key] in ("", 0, []):
                normalized[key] = value
        normalized["capacity_type"] = normalize_text(normalized.get("capacity_type")) or infer_capacity_type(
            normalize_int(normalized.get("standard_capacity"))
        )
        merged[product_id] = normalized

    for product_id, product in derived.items():
        if product_id not in merged:
            merged[product_id] = normalize_product(product)

    return sorted(merged.values(), key=lambda product: product["id"])


def normalize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized = normalized_payload_tables(payload)
    enrich_room_area_metadata(normalized["rooms"], normalized["teaching_areas"])
    enrich_class_teacher_assignments(normalized["classes"], normalized["teachers"])
    recompute_area_capacity(normalized["teaching_areas"], normalized["rooms"])
    assign_normalized_row_numbers(normalized)
    sync_course_product_names(normalized["product_courses"], normalized["products"])
    apply_class_product_label_defaults(
        normalized["classes"],
        normalized["products"],
        normalized["product_courses"],
    )
    validate_state(normalized)
    return normalized


def normalized_resource_tables(payload: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    return {
        "schedule_windows": [normalize_schedule_window(item) for item in payload.get("schedule_windows", [])],
        "time_slots": [normalize_time_slot(item) for item in payload.get("time_slots", [])],
        "teaching_areas": [normalize_teaching_area(area) for area in payload.get("teaching_areas", [])],
        "rooms": [normalize_room(room) for room in payload.get("rooms", [])],
        "teachers": [normalize_teacher(teacher) for teacher in payload.get("teachers", [])],
        "teacher_unavailability": [
            normalize_teacher_unavailability(item)
            for item in payload.get("teacher_unavailability", [])
        ],
    }


def normalized_product_tables(payload: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    raw_product_courses = list(payload.get("product_courses", []))
    product_courses = [normalize_product_course(course) for course in raw_product_courses]
    product_schedule_rules = [
        normalize_product_rule(rule)
        for rule in payload.get("product_schedule_rules", [])
    ]
    product_schedule_rules.extend(legacy_product_course_block_rules(raw_product_courses, product_schedule_rules))
    return {
        "products": merge_products(payload.get("products", []), product_courses),
        "product_courses": product_courses,
        "product_schedule_rules": product_schedule_rules,
    }


def legacy_product_course_block_rules(
    product_courses: List[Dict[str, Any]],
    existing_rules: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    generated: List[Dict[str, Any]] = []
    coverage_rules = list(existing_rules)
    for course in product_courses:
        block_hours = normalize_float(course.get("block_hours"))
        product_id = normalize_text(course.get("product_id"))
        if not product_id or block_hours <= 0:
            continue
        window_name = product_course_window_name(course)
        key = (
            product_id,
            window_name,
            normalize_text(course.get("subject")),
            normalize_text(course.get("stage")),
            normalize_text(course.get("course_module")),
            normalize_text(course.get("course_group")),
        )
        if fill_existing_product_course_block_rule(key, block_hours, coverage_rules):
            continue
        if product_course_block_rule_exists(key, coverage_rules):
            continue
        generated_rule = normalize_product_rule(
            {
                "rule_id": f"LEGACY_COURSE_BLOCK_{len(generated) + 1}",
                "product_id": product_id,
                "product_name": normalize_text(course.get("product_name")),
                "window_name": window_name,
                "subject": normalize_text(course.get("subject")),
                "stage": normalize_text(course.get("stage")),
                "course_module": normalize_text(course.get("course_module")),
                "course_group": normalize_text(course.get("course_group")),
                "block_hours": block_hours,
                "notes": "由旧产品课程课时表 block_hours 自动迁移；新模板请维护 09_产品窗口排课规则表。",
            }
        )
        generated.append(generated_rule)
        coverage_rules.append(generated_rule)
    return generated


def fill_existing_product_course_block_rule(
    course_key: Tuple[str, str, str, str, str, str],
    block_hours: float,
    rules: List[Dict[str, Any]],
) -> bool:
    for rule in rules:
        if normalize_float(rule.get("block_hours")) > 0:
            continue
        if not product_course_rule_covers_key(rule, course_key):
            continue
        rule["block_hours"] = block_hours
        note = normalize_text(rule.get("notes"))
        migration_note = "旧产品课程课时表 block_hours 已迁移到本规则。"
        rule["notes"] = f"{note}；{migration_note}" if note else migration_note
        return True
    return False


def product_course_block_rule_exists(
    course_key: Tuple[str, str, str, str, str, str],
    rules: List[Dict[str, Any]],
) -> bool:
    for rule in rules:
        if normalize_float(rule.get("block_hours")) <= 0:
            continue
        if product_course_rule_covers_key(rule, course_key):
            return True
    return False


def product_course_rule_covers_key(
    rule: Dict[str, Any],
    course_key: Tuple[str, str, str, str, str, str],
) -> bool:
    product_id, window_name, subject, stage, course_module, course_group = course_key
    if normalize_text(rule.get("product_id")) != product_id:
        return False
    rule_window_tokens = expanded_window_tokens(
        rule.get("window_name"),
        rule.get("season_window_id"),
        rule.get("schedule_window_id"),
    )
    course_window_tokens = expanded_window_tokens(window_name)
    if rule_window_tokens and course_window_tokens and not (rule_window_tokens & course_window_tokens):
        return False
    for rule_value, course_value in (
        (normalize_text(rule.get("subject")), subject),
        (normalize_text(rule.get("stage")), stage),
        (normalize_text(rule.get("course_module")), course_module),
        (normalize_text(rule.get("course_group")), course_group),
    ):
        if rule_value and rule_value != course_value:
            return False
    return True


def product_course_window_name(course: Dict[str, Any]) -> str:
    return normalize_text(
        course.get("window_name")
        or course.get("quarter")
        or course.get("排课窗口期")
        or course.get("窗口期")
        or course.get("season")
        or course.get("季度")
        or course.get("季度标签")
    )


def normalized_class_tables(payload: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    class_rows = attach_class_teacher_assignment_table(
        list(payload.get("classes", [])),
        list(payload.get("class_teacher_assignments", [])),
    )
    classes = [normalize_class(cls) for cls in class_rows]
    return {
        "classes": classes,
        "class_window_boundaries": [
            normalize_class_window_boundary(item)
            for item in payload.get("class_window_boundaries", [])
        ],
        "class_teacher_assignments": class_teacher_assignment_rows({"classes": classes}),
        "class_conflict_groups": [
            normalize_class_conflict_group(group)
            for group in payload.get("class_conflict_groups", [])
        ],
    }


def normalized_auxiliary_tables(payload: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    return {
        "locked_scheduled_lessons": [
            normalize_locked_scheduled_lesson(lesson)
            for lesson in payload.get("locked_scheduled_lessons", payload.get("scheduled_lessons", []))
        ],
        "teaching_area_links": [normalize_area_link(link) for link in payload.get("teaching_area_links", [])],
        "global_blackout_dates": [
            normalize_blackout_date(item)
            for item in payload.get("global_blackout_dates", [])
        ],
        "historical_scheduled_lessons": [
            normalize_locked_scheduled_lesson(lesson)
            for lesson in payload.get("historical_scheduled_lessons", [])
        ],
        "business_product_mappings": [
            normalize_business_product_mapping(item)
            for item in payload.get("business_product_mappings", [])
        ],
        "erp_standard_products": [
            normalize_erp_standard_product(item)
            for item in payload.get("erp_standard_products", [])
        ],
    }


def normalized_payload_tables(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        **normalized_resource_tables(payload),
        **normalized_product_tables(payload),
        **normalized_class_tables(payload),
        **normalized_auxiliary_tables(payload),
    }


def enrich_room_area_metadata(rooms: List[Dict[str, Any]], teaching_areas: List[Dict[str, Any]]) -> None:
    area_by_id = {area["id"]: area for area in teaching_areas if area["id"]}
    for index, room in enumerate(rooms, start=2):
        room["row"] = index
        area = area_by_id.get(room.get("teaching_area_id", ""))
        if area:
            room["teaching_area_name"] = area.get("short_name") or area.get("name", "")
            room["campus"] = area.get("campus", "")


def teacher_id_lookups(
    teachers: List[Dict[str, Any]],
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, List[str]], Dict[str, List[str]]]:
    teacher_by_id = {teacher["employee_id"]: teacher for teacher in teachers if teacher["employee_id"]}
    teacher_ids_by_name: Dict[str, List[str]] = {}
    numeric_teacher_ids_by_name: Dict[str, List[str]] = {}
    for teacher in teachers:
        teacher_name = normalize_text(teacher.get("name"))
        teacher_id = normalize_text(teacher.get("employee_id"))
        if teacher_name and teacher_id:
            teacher_ids_by_name.setdefault(teacher_name, []).append(teacher_id)
            if is_employee_id(teacher_id):
                numeric_teacher_ids_by_name.setdefault(teacher_name, []).append(teacher_id)
    return teacher_by_id, teacher_ids_by_name, numeric_teacher_ids_by_name


def enrich_class_teacher_assignments(classes: List[Dict[str, Any]], teachers: List[Dict[str, Any]]) -> None:
    teacher_by_id, teacher_ids_by_name, numeric_teacher_ids_by_name = teacher_id_lookups(teachers)
    for cls in classes:
        for assignment in cls.get("teacher_assignments", []):
            if assignment.get("teacher_id") and not is_employee_id(assignment.get("teacher_id")):
                numeric_ids = numeric_teacher_ids_by_name.get(assignment.get("teacher_name", ""), [])
                if len(numeric_ids) == 1:
                    assignment["teacher_id"] = numeric_ids[0]
            if not assignment.get("teacher_id") and assignment.get("teacher_name"):
                matching_ids = teacher_ids_by_name.get(assignment["teacher_name"], [])
                if len(matching_ids) == 1:
                    assignment["teacher_id"] = matching_ids[0]
            teacher = teacher_by_id.get(assignment.get("teacher_id", ""))
            if teacher and not assignment.get("teacher_name"):
                assignment["teacher_name"] = teacher.get("name", "")


def assign_normalized_row_numbers(normalized: Dict[str, Any]) -> None:
    for table_name in (
        "teacher_unavailability",
        "products",
        "product_courses",
        "product_schedule_rules",
        "class_conflict_groups",
        "class_window_boundaries",
        "locked_scheduled_lessons",
        "global_blackout_dates",
    ):
        for index, row in enumerate(normalized[table_name], start=2):
            row["row"] = index


def sync_course_product_names(product_courses: List[Dict[str, Any]], products: List[Dict[str, Any]]) -> None:
    product_by_id = {product["id"]: product for product in products if product["id"]}
    for course in product_courses:
        product = product_by_id.get(course.get("product_id", ""))
        if product:
            course["product_name"] = product["name"]


def apply_class_product_label_defaults(
    classes: List[Dict[str, Any]],
    products: List[Dict[str, Any]],
    product_courses: List[Dict[str, Any]],
) -> None:
    product_meta = product_catalog(products, product_courses)
    for cls in classes:
        apply_class_label_defaults(cls, product_meta, product_courses)


def normalize_teaching_area(area: Dict[str, Any]) -> Dict[str, Any]:
    name = normalize_text(area.get("name"))
    campus = normalize_text(area.get("campus"))
    short_name = normalize_text(area.get("short_name") or area.get("教学区简称") or area.get("简称"))
    region_tag = normalize_text(area.get("region_tag") or area.get("区域标签") or area.get("区域") or area.get("area_tag"))
    address = normalize_text(area.get("address") or area.get("校区地址") or area.get("地址"))
    longitude = normalize_text(area.get("longitude") or area.get("lng") or area.get("经度"))
    latitude = normalize_text(area.get("latitude") or area.get("lat") or area.get("纬度"))
    return {
        "id": normalize_text(area.get("id")),
        "name": name,
        "short_name": short_name or infer_teaching_area_short_name(name, campus, area.get("id")),
        "region_tag": region_tag or infer_teaching_area_region_tag(campus, name, short_name, area.get("id")),
        "address": address,
        "longitude": longitude,
        "latitude": latitude,
        "campus": campus,
        "scheduling_capacity": normalize_int(area.get("scheduling_capacity")),
        "capacity_check": normalize_text(area.get("capacity_check")) or "OK",
        "is_active": normalize_bool(area.get("is_active")),
        "room_count": normalize_int(area.get("room_count")),
        "active_room_count": normalize_int(area.get("active_room_count")),
        "data_source": normalize_text(area.get("data_source")),
        "notes": normalize_text(area.get("notes")),
    }


def normalize_room(room: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "row": normalize_int(room.get("row")),
        "id": normalize_text(room.get("id")),
        "name": normalize_text(room.get("name")),
        "teaching_area_id": normalize_text(room.get("teaching_area_id")),
        "teaching_area_name": normalize_text(room.get("teaching_area_name")),
        "campus": normalize_text(room.get("campus")),
        "capacity": normalize_int(room.get("capacity")),
        "room_type": normalize_text(room.get("room_type")),
        "is_active": normalize_bool(room.get("is_active")),
        "data_source": normalize_text(room.get("data_source")),
        "notes": normalize_text(room.get("notes")),
    }


def normalize_teacher(teacher: Dict[str, Any]) -> Dict[str, Any]:
    teacher_id = normalize_text(teacher.get("employee_id") or teacher.get("id") or teacher.get("teacher_id"))
    primary_subject = normalize_text(teacher.get("primary_subject"))
    teacher_type_values = {"全职", "兼职", "外聘", "内部"}
    raw_teacher_role = normalize_text(teacher.get("teacher_role") or teacher.get("identity") or teacher.get("教师角色"))
    raw_teacher_type = normalize_text(teacher.get("employment_type") or teacher.get("teacher_type") or teacher.get("教师类型"))
    raw_contract_status = normalize_text(teacher.get("contract_status"))
    teacher_type = raw_teacher_type or (raw_contract_status if raw_contract_status in teacher_type_values else "")
    contract_status = "" if not raw_teacher_type and raw_contract_status in teacher_type_values else raw_contract_status
    derived_subject_type = teacher_subject_type(primary_subject)
    return {
        "employee_id": teacher_id,
        "name": normalize_text(teacher.get("name") or teacher.get("teacher_name")),
        "gender": normalize_text(teacher.get("gender")),
        "project": normalize_text(teacher.get("project")),
        "teacher_role": normalize_teacher_identity_label(raw_teacher_role),
        "employment_type": teacher_type,
        "primary_subject": primary_subject,
        "subject_type": derived_subject_type or normalize_text(teacher.get("subject_type")),
        "contract_status": contract_status,
        "employment_status": normalize_text(teacher.get("employment_status")),
        "notes": normalize_text(teacher.get("notes")),
    }


def normalize_product(product: Dict[str, Any]) -> Dict[str, Any]:
    product_id = normalize_text(product.get("id") or product.get("product_id"))
    product_name = normalize_text(product.get("name") or product.get("product_name")) or product_id
    project = normalize_text(product.get("project")) or infer_project(product_name)
    product_line = normalize_text(product.get("product_line")) or infer_product_line(product_name, project=project)
    standard_capacity = normalize_int(product.get("standard_capacity"))
    return {
        "row": normalize_int(product.get("row")),
        "id": product_id,
        "name": product_name,
        "project": project,
        "product_line": product_line,
        "sub_product": normalize_text(product.get("sub_product")) or infer_sub_product(product_line, product_name),
        "product_system": normalize_text(product.get("product_system")),
        "season_window_ids": split_id_list(product.get("season_window_ids")),
        "applicable_stages": split_id_list(product.get("applicable_stages")),
        "standard_capacity": standard_capacity,
        "capacity_type": normalize_text(product.get("capacity_type")) or infer_capacity_type(standard_capacity),
        "subject": normalize_text(product.get("subject")),
        "subject_category": normalize_text(product.get("subject_category")),
        "course_nature": normalize_text(product.get("course_nature")),
        "notes": normalize_text(product.get("notes")),
    }


def normalize_product_course(course: Dict[str, Any]) -> Dict[str, Any]:
    product_name = normalize_text(course.get("product_name"))
    window_name = product_course_window_name(course)
    module_priority = normalize_int(
        course.get("module_priority_in_group")
        or course.get("module_priority")
        or course.get("模块优先级")
        or course.get("course_module_priority")
    )
    return {
        "row": normalize_int(course.get("row")),
        "product_id": normalize_text(course.get("product_id")),
        "product_name": product_name,
        "subject_category": normalize_text(course.get("subject_category")),
        "subject": normalize_text(course.get("subject")),
        "window_name": window_name,
        "stage": normalize_text(course.get("stage")),
        "stage_priority": normalize_int(course.get("stage_priority") or course.get("阶段优先级")),
        "course_group": normalize_text(course.get("course_group")),
        "course_module": normalize_text(course.get("course_module")),
        "module_priority_in_group": module_priority,
        "course_code": normalize_text(
            course.get("course_code")
            or course.get("课程编码")
            or course.get("课程名称编码")
        ),
        "course_name": normalize_text(
            course.get("course_name")
            or course.get("course_name_tag")
            or course.get("课程名称标签")
            or course.get("课程名称")
        ),
        "total_hours": normalize_int(course.get("total_hours")),
        "notes": normalize_text(course.get("notes")),
    }


def normalize_product_rule(rule: Dict[str, Any]) -> Dict[str, Any]:
    product_id = normalize_text(rule.get("product_id"))
    product_ids = split_id_list(rule.get("product_ids"))
    if not product_id and len(product_ids) == 1:
        product_id = product_ids[0]
    block_hours = normalize_float(rule.get("block_hours"))
    if block_hours <= 0:
        block_hours = normalize_float(rule.get("block_hours_override"))
    rule_id = normalize_text(rule.get("rule_id"))
    return {
        "row": normalize_int(rule.get("row")),
        "rule_id": rule_id,
        "product_id": product_id,
        "product_name": normalize_text(rule.get("product_name")),
        "sub_product": normalize_text(rule.get("sub_product")),
        "season_window_id": normalize_text(rule.get("season_window_id")),
        "window_name": normalize_text(rule.get("window_name")),
        "effective_after_class_start": normalize_bool(rule.get("effective_after_class_start", True)),
        "subject": normalize_text(rule.get("subject")),
        "stage": normalize_text(rule.get("stage")),
        "course_module": normalize_text(rule.get("course_module")),
        "course_group": normalize_text(rule.get("course_group")),
        "start_date": normalize_date_text(rule.get("start_date")),
        "end_date": normalize_date_text(rule.get("end_date")),
        "allowed_periods": split_id_list(rule.get("allowed_periods")),
        "allowed_weekdays": split_id_list(rule.get("allowed_weekdays")),
        "excluded_weekdays": split_id_list(rule.get("excluded_weekdays")),
        "exception_weekdays": split_id_list(rule.get("exception_weekdays")),
        "block_hours": block_hours,
        "lessons_per_block": normalize_int(rule.get("lessons_per_block")),
        "max_hours_per_class_per_day": normalize_float(rule.get("max_hours_per_class_per_day")),
        "max_blocks_per_class_per_day": normalize_int(rule.get("max_blocks_per_class_per_day")),
        "min_weekly_hours": normalize_float(rule.get("min_weekly_hours")),
        "max_weekly_hours": normalize_float(rule.get("max_weekly_hours")),
        "same_half_day_block_required": normalize_bool(rule.get("same_half_day_block_required")),
        "same_half_day_4h_same_teacher_required": normalize_bool(rule.get("same_half_day_4h_same_teacher_required")),
        "delivery_mode": normalize_text(rule.get("delivery_mode")),
        "notes": normalize_text(rule.get("notes")),
    }


def normalized_class_stage_fields(cls: Dict[str, Any]) -> Dict[str, List[str]]:
    selected_stages = split_id_list(cls.get("selected_stages"))
    if not selected_stages:
        selected_stages = split_id_list(cls.get("stages", cls.get("stage")))
    return {
        "selected_stages": selected_stages,
    }


def normalized_class_exam_fields(cls: Dict[str, Any]) -> Dict[str, str]:
    raw_exam_season = normalize_text(cls.get("exam_season"))
    exam_season = normalize_exam_season(raw_exam_season)
    exam_month = normalize_text(cls.get("exam_month") or cls.get("考试月份"))
    if not exam_month and looks_like_exam_month(raw_exam_season):
        exam_month = raw_exam_season
        exam_season = exam_season_from_month(exam_month)
    elif not exam_season and exam_month:
        exam_season = exam_season_from_month(exam_month)
    return {"exam_season": exam_season, "exam_month": exam_month}


def normalized_class_capacity_fields(cls: Dict[str, Any]) -> Dict[str, Any]:
    standard_capacity = normalize_int(cls.get("standard_capacity") or cls.get("standard_size"))
    return {
        "standard_capacity": standard_capacity,
        "capacity_type": normalize_text(cls.get("capacity_type")) or infer_capacity_type(standard_capacity),
        "size": normalize_int(cls.get("size")),
    }


def normalized_class_date_fields(cls: Dict[str, Any]) -> Dict[str, str]:
    return {
        "start_date": normalize_date_text(cls.get("start_date")),
        "start_period": normalize_text(cls.get("start_period")),
        "first_lesson_date": normalize_date_text(cls.get("first_lesson_date") or cls.get("首课日期")),
        "first_lesson_period": normalize_text(cls.get("first_lesson_period") or cls.get("首课时段")),
        "end_date": normalize_date_text(cls.get("end_date")),
        "end_period": normalize_text(cls.get("end_period")),
    }


def normalized_class_resource_fields(cls: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "preferred_teaching_area_ids": split_id_list(cls.get("preferred_teaching_area_ids")),
        "preferred_room_ids": split_id_list(cls.get("preferred_room_ids")),
        "preferred_room_is_required": normalize_bool(
            cls.get("preferred_room_is_required")
            or cls.get("must_use_preferred_room")
            or cls.get("必须指定教室")
            or cls.get("指定教室必排")
        ),
    }


def normalized_class_lock_fields(cls: Dict[str, Any]) -> Dict[str, bool]:
    lock_value = row_value(
        cls,
        "is_manual_schedule_locked",
        "is_schedule_locked",
        "schedule_locked",
        "课表已定",
        "不自动排课",
    )
    is_locked = normalize_bool(lock_value)
    return {
        "is_manual_schedule_locked": is_locked,
    }


def normalized_class_nested_rows(cls: Dict[str, Any], class_id: str) -> Dict[str, List[Dict[str, Any]]]:
    return {
        "requirements": [
            normalize_class_requirement(requirement)
            for requirement in cls.get("requirements", [])
            if has_requirement_content(requirement)
        ],
        "teacher_assignments": [
            current_teacher_assignment_row(assignment, class_id=class_id)
            for assignment in cls.get("teacher_assignments", [])
            if has_assignment_content(assignment)
        ],
    }


def normalize_class(cls: Dict[str, Any]) -> Dict[str, Any]:
    class_id = normalize_text(cls.get("id") or cls.get("class_id"))
    class_name = normalize_text(cls.get("name") or cls.get("class_name"))
    return {
        "id": class_id,
        "name": class_name,
        "product_id": normalize_text(cls.get("product_id")),
        "project": normalize_text(cls.get("project")),
        "product_line": normalize_text(cls.get("product_line")),
        "sub_product": normalize_text(cls.get("sub_product")),
        "product_system": normalize_text(cls.get("product_system")),
        "course_nature": normalize_text(cls.get("course_nature")),
        "subject_category": normalize_text(cls.get("subject_category")),
        "subject": normalize_text(cls.get("subject")),
        **normalized_class_stage_fields(cls),
        **normalized_class_exam_fields(cls),
        "suite_code": normalize_text(cls.get("suite_code") or cls.get("package_code") or cls.get("套班编码")) or infer_suite_code_from_class_name(class_name),
        **normalized_class_capacity_fields(cls),
        **normalized_class_date_fields(cls),
        **normalized_class_resource_fields(cls),
        **normalized_class_lock_fields(cls),
        "notes": normalize_text(cls.get("notes")),
        **normalized_class_nested_rows(cls, class_id),
    }


def normalize_class_requirement(requirement: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "subject_category": normalize_text(requirement.get("subject_category")),
        "subject": normalize_text(requirement.get("subject")),
        "window_name": normalize_text(
            requirement.get("window_name")
            or requirement.get("quarter")
            or requirement.get("season")
            or requirement.get("季度")
            or requirement.get("季度标签")
        ),
        "stage": normalize_text(requirement.get("stage")),
        "course_module": normalize_text(requirement.get("course_module")),
        "course_group": normalize_text(requirement.get("course_group")),
        "teacher_id": normalize_text(requirement.get("teacher_id")),
        "teacher_name": normalize_text(requirement.get("teacher_name")),
        "total_hours": normalize_int(requirement.get("total_hours")),
        "block_hours": normalize_int(requirement.get("block_hours")),
        "room_ids": split_id_list(requirement.get("room_ids")),
        "start_date": normalize_date_text(requirement.get("start_date")),
        "end_date": normalize_date_text(requirement.get("end_date")),
        "allowed_periods": split_id_list(requirement.get("allowed_periods")),
        "allowed_weekdays": split_id_list(requirement.get("allowed_weekdays")),
        "excluded_weekdays": split_id_list(requirement.get("excluded_weekdays")),
        "notes": normalize_text(requirement.get("notes")),
    }


def normalize_teacher_assignment(assignment: Dict[str, Any]) -> Dict[str, Any]:
    current_class_id = normalize_text(assignment.get("class_id"))
    schedule_mode = assignment_schedule_mode(assignment, class_id=current_class_id)
    is_shared = schedule_mode == "共享课表"
    actual_scheduled_class_id = assignment_reference_class_id(assignment) if is_shared else current_class_id
    return {
        "product_id": normalize_text(assignment.get("product_id") or assignment.get("canonical_product_id")),
        "product_name": normalize_text(assignment.get("product_name")),
        "subject": normalize_text(assignment.get("subject")),
        "stage": normalize_text(assignment.get("stage")),
        "course_group": normalize_text(assignment.get("course_group")),
        "class_schedule_mode": class_schedule_mode_display_name(schedule_mode),
        "actual_scheduled_class_id": actual_scheduled_class_id,
        "teacher_id": "" if is_shared else normalize_text(assignment.get("teacher_id")),
        "teacher_name": "" if is_shared else normalize_text(assignment.get("teacher_name")),
        "assignment_extra_time_requirement": normalize_text(assignment.get("assignment_extra_time_requirement")),
        "notes": normalize_text(assignment.get("notes")),
    }


def current_teacher_assignment_row(
    assignment: Dict[str, Any],
    class_id: str = "",
    class_name: str = "",
    include_class_fields: bool = False,
) -> Dict[str, Any]:
    normalized = normalize_teacher_assignment({"class_id": class_id, **assignment})
    row = {
        "product_id": normalized.get("product_id"),
        "product_name": normalized.get("product_name"),
        "subject": normalized.get("subject"),
        "stage": normalized.get("stage"),
        "course_group": normalized.get("course_group"),
        "class_schedule_mode": normalized.get("class_schedule_mode"),
        "actual_scheduled_class_id": normalized.get("actual_scheduled_class_id") or class_id,
        "teacher_id": normalized.get("teacher_id"),
        "teacher_name": normalized.get("teacher_name"),
        "assignment_extra_time_requirement": normalized.get("assignment_extra_time_requirement"),
        "notes": normalized.get("notes"),
    }
    if include_class_fields:
        row = {"class_id": class_id, "class_name": class_name, **row}
    return {key: value for key, value in row.items() if value not in ("", None, [])}


def class_teacher_assignment_rows(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for cls in state.get("classes", []):
        class_id = normalize_text(cls.get("id"))
        class_name = normalize_text(cls.get("name"))
        for assignment in cls.get("teacher_assignments", []):
            rows.append(current_teacher_assignment_row(assignment, class_id, class_name, include_class_fields=True))
    return rows


def class_conflict_group_is_active(group: Dict[str, Any]) -> bool:
    value = group.get("is_conflict_group_active")
    if value in ("", None):
        value = group.get("is_active", True)
    return normalize_bool(value)


def normalize_class_conflict_group(group: Dict[str, Any]) -> Dict[str, Any]:
    group_id = normalize_text(group.get("id") or group.get("group_id"))
    is_active = class_conflict_group_is_active(group)
    conflict_source = normalize_text(group.get("conflict_source") or group.get("source")) or "手动"
    return {
        "row": normalize_int(group.get("row")),
        "id": group_id,
        "name": normalize_text(group.get("name") or group.get("group_name")) or group_id,
        "exam_season": normalize_exam_season(group.get("exam_season")),
        "suite_code": normalize_text(group.get("suite_code")),
        "class_ids": split_id_list(group.get("class_ids")),
        "is_conflict_group_active": is_active,
        "conflict_source": conflict_source,
        "notes": normalize_text(group.get("notes")),
    }


def normalize_locked_scheduled_lesson(lesson: Dict[str, Any]) -> Dict[str, Any]:
    class_id = normalize_text(lesson.get("class_id") or lesson.get("班级编码"))
    lesson_date = normalize_date_text(lesson.get("date") or lesson.get("上课日期") or lesson.get("日期"))
    start_time = normalize_time_text(lesson.get("start_time") or lesson.get("起始时间") or lesson.get("开始时间"))
    end_time = normalize_time_text(lesson.get("end_time") or lesson.get("结束时间") or lesson.get("下课时间"))
    lesson_id = normalize_text(lesson.get("id"))
    if not lesson_id:
        lesson_id = "_".join(item for item in (class_id, lesson_date, start_time.replace(":", ""), end_time.replace(":", "")) if item)
    return {
        "row": normalize_int(lesson.get("row")),
        "id": lesson_id,
        "class_id": class_id,
        "class_name": normalize_text(lesson.get("class_name") or lesson.get("班级名称")),
        "date": lesson_date,
        "period": normalize_text(lesson.get("period") or lesson.get("时段")),
        "start_time": start_time,
        "end_time": end_time,
        "duration_hours": normalize_text(lesson.get("duration_hours") or lesson.get("课时") or lesson.get("小时数")),
        "teacher_id": normalize_blank_marker(lesson.get("teacher_id") or lesson.get("教师编码")),
        "teacher_name": normalize_blank_marker(lesson.get("teacher_name") or lesson.get("教师姓名")),
        "room_id": normalize_text(lesson.get("room_id") or lesson.get("教室编码")),
        "room_name": normalize_text(lesson.get("room_name") or lesson.get("教室名称")),
        "teaching_area_id": normalize_text(lesson.get("teaching_area_id") or lesson.get("教学区编码")),
        "business_product_id": normalize_text(lesson.get("business_product_id") or lesson.get("课程产品编码") or lesson.get("课程产品编号")),
        "business_product_name": normalize_text(lesson.get("business_product_name") or lesson.get("课程产品名称") or lesson.get("课程产品(内)")),
        "subject": normalize_text(lesson.get("subject") or lesson.get("科目")),
        "quarter": normalize_text(lesson.get("quarter") or lesson.get("季度") or lesson.get("季度标签")),
        "stage": normalize_text(lesson.get("stage") or lesson.get("阶段")),
        "course_module": normalize_text(lesson.get("course_module") or lesson.get("课程模块") or lesson.get("模块")),
        "course_group": normalize_text(lesson.get("course_group") or lesson.get("课程组") or lesson.get("课程类别")),
        "course_code": normalize_text(lesson.get("course_code") or lesson.get("课程编码") or lesson.get("课程编号")),
        "course_name": normalize_text(lesson.get("course_name") or lesson.get("课程名称") or lesson.get("课程内容")),
        "source": normalize_text(lesson.get("source")) or "locked_schedule",
        "is_locked": normalize_bool(lesson.get("is_locked")) if "is_locked" in lesson else True,
        "notes": normalize_text(lesson.get("notes")),
    }


def has_assignment_content(assignment: Dict[str, Any]) -> bool:
    return any(
        normalize_text(assignment.get(key))
        for key in (
            "product_id",
            "subject",
            "stage",
            "course_group",
            "class_schedule_mode",
            "actual_scheduled_class_id",
            "schedule_mode",
            "inherit_from_class_id",
            "teacher_id",
            "teacher_name",
        )
    )


AssignmentKey = Tuple[str, str, str, str]


def teacher_assignment_key(item: Dict[str, Any], product_id: str = "") -> AssignmentKey:
    return (
        normalize_text(item.get("product_id") or product_id),
        normalize_text(item.get("subject")),
        normalize_text(item.get("stage")) or normalize_text(item.get("quarter")),
        normalize_text(item.get("course_group")),
    )


def stage_rank_for_courses(courses: List[Dict[str, Any]]) -> Dict[str, int]:
    ranks: Dict[str, int] = {}
    for stage in sort_stage_values(course.get("stage") for course in courses):
        ranks[stage] = len(ranks)
    return ranks


def choose_current_assignment(
    current: Dict[AssignmentKey, Dict[str, Any]],
    key: AssignmentKey,
    assignment: Dict[str, Any],
) -> None:
    existing = current.get(key)
    if existing is None or not normalize_text(assignment.get("course_module")):
        current[key] = assignment


def resolve_synced_teacher_assignment(
    course: Dict[str, Any],
    product_id: str,
    current: Dict[AssignmentKey, Dict[str, Any]],
    courses: List[Dict[str, Any]],
) -> Dict[str, Any]:
    product_key, subject, stage, course_group = teacher_assignment_key(course, product_id)
    candidates = [
        (product_key, subject, stage, course_group),
        ("", subject, stage, course_group),
        (product_key, "", stage, course_group),
        ("", "", stage, course_group),
    ]
    for candidate in candidates:
        assignment = current.get(candidate)
        if assignment:
            return assignment

    ranks = stage_rank_for_courses(courses)
    current_rank = ranks.get(stage, 10_000)
    fallback: List[Tuple[int, Dict[str, Any]]] = []
    for candidate_key, assignment in current.items():
        candidate_product, candidate_subject, candidate_stage, candidate_group = candidate_key
        if candidate_group != course_group:
            continue
        if candidate_product and candidate_product != product_key:
            continue
        if candidate_subject and candidate_subject != subject:
            continue
        if not candidate_stage or candidate_stage == stage:
            continue
        candidate_rank = ranks.get(candidate_stage, 10_000)
        if candidate_rank >= current_rank:
            continue
        fallback.append((candidate_rank, assignment))
    if fallback:
        fallback.sort(key=lambda item: item[0])
        return fallback[0][1]
    return {}


def resolve_exact_teacher_assignment(
    course: Dict[str, Any],
    product_id: str,
    current: Dict[AssignmentKey, Dict[str, Any]],
) -> Dict[str, Any]:
    product_key, subject, stage, course_group = teacher_assignment_key(course, product_id)
    candidates = [
        (product_key, subject, stage, course_group),
        ("", subject, stage, course_group),
        (product_key, "", stage, course_group),
        ("", "", stage, course_group),
    ]
    for candidate in candidates:
        assignment = current.get(candidate)
        if assignment:
            return assignment
    return {}


def sync_class_teacher_assignments(state: Dict[str, Any], class_ids: Optional[Set[str]] = None) -> Dict[str, int]:
    courses_by_product = product_courses_by_product(state)
    stats = {"classes": 0, "assignments": 0}
    for cls in state.get("classes", []):
        if class_ids is not None and normalize_text(cls.get("id")) not in class_ids:
            continue
        if sync_class_teacher_assignment_rows(state, cls, courses_by_product):
            stats["classes"] += 1
            stats["assignments"] += len(cls.get("teacher_assignments", []))
    return stats


def product_courses_by_product(state: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    courses_by_product: Dict[str, List[Dict[str, Any]]] = {}
    for course in state.get("product_courses", []):
        product_id = normalize_text(course.get("product_id"))
        if product_id:
            courses_by_product.setdefault(product_id, []).append(course)
    return courses_by_product


def sync_class_teacher_assignment_rows(
    state: Dict[str, Any],
    cls: Dict[str, Any],
    courses_by_product: Dict[str, List[Dict[str, Any]]],
) -> bool:
    class_id = normalize_text(cls.get("id"))
    product_id = normalize_text(cls.get("product_id"))
    if not product_id:
        return False

    product_courses = product_courses_for_class(cls, courses_by_product.get(product_id, []))
    if not product_courses:
        return False

    current = current_teacher_assignment_map(cls, product_id)
    cls["teacher_assignments"] = [
        synced_teacher_assignment_row(state, class_id, product_id, course, current, product_courses)
        for course in grouped_product_courses(product_courses, product_id).values()
    ]
    return True


def product_courses_for_class(cls: Dict[str, Any], product_courses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    class_subject = normalize_text(cls.get("subject"))
    selected_stages = set(split_id_list(cls.get("selected_stages") or cls.get("stages")))
    return [
        course
        for course in product_courses
        if (not class_subject or normalize_text(course.get("subject")) == class_subject)
        and (not selected_stages or normalize_text(course.get("stage")) in selected_stages)
    ]


def current_teacher_assignment_map(cls: Dict[str, Any], product_id: str) -> Dict[AssignmentKey, Dict[str, Any]]:
    current: Dict[AssignmentKey, Dict[str, Any]] = {}
    for raw_assignment in cls.get("teacher_assignments", []):
        assignment = normalize_teacher_assignment(raw_assignment)
        choose_current_assignment(current, teacher_assignment_key(assignment, product_id), assignment)
        raw_key = teacher_assignment_key(assignment)
        if raw_key[0] != product_id:
            choose_current_assignment(current, raw_key, assignment)
            choose_current_assignment(current, ("", raw_key[1], raw_key[2], raw_key[3]), assignment)
    return current


def grouped_product_courses(product_courses: List[Dict[str, Any]], product_id: str) -> Dict[AssignmentKey, Dict[str, Any]]:
    grouped_courses: Dict[AssignmentKey, Dict[str, Any]] = {}
    for course in product_courses:
        grouped_courses.setdefault(teacher_assignment_key(course, product_id), course)
    return grouped_courses


def synced_teacher_assignment_row(
    state: Dict[str, Any],
    class_id: str,
    product_id: str,
    course: Dict[str, Any],
    current: Dict[AssignmentKey, Dict[str, Any]],
    product_courses: List[Dict[str, Any]],
) -> Dict[str, Any]:
    existing = resolve_synced_teacher_assignment(course, product_id, current, product_courses)
    exact_existing = resolve_exact_teacher_assignment(course, product_id, current)
    schedule_mode = assignment_schedule_mode(exact_existing, class_id=class_id)
    is_shared = schedule_mode == "共享课表"
    reference_class_id = assignment_reference_class_id(exact_existing) if is_shared else ""
    return current_teacher_assignment_row(
        {
            "class_id": class_id,
            "product_id": product_id,
            "product_name": normalize_text(course.get("product_name")) or product_name_from_state(state, product_id),
            "subject": normalize_text(course.get("subject")),
            "stage": normalize_text(course.get("stage")),
            "course_group": normalize_text(course.get("course_group")),
            "class_schedule_mode": class_schedule_mode_display_name(schedule_mode),
            "actual_scheduled_class_id": reference_class_id if is_shared else class_id,
            "teacher_id": "" if is_shared else normalize_text(existing.get("teacher_id")),
            "teacher_name": "" if is_shared else normalize_text(existing.get("teacher_name")),
            "assignment_extra_time_requirement": ""
            if is_shared
            else normalize_text(existing.get("assignment_extra_time_requirement")),
            "notes": normalize_text(exact_existing.get("notes") or existing.get("notes")),
        },
        class_id=class_id,
    )


def product_name_from_state(state: Dict[str, Any], product_id: str) -> str:
    for product in state.get("products", []):
        if normalize_text(product.get("id")) == product_id:
            return normalize_text(product.get("name")) or product_id
    return product_id


def has_requirement_content(requirement: Dict[str, Any]) -> bool:
    return any(
        normalize_text(requirement.get(key))
        for key in ("subject", "teacher_id", "teacher_name", "total_hours", "block_hours")
    )


def subject_category_for_class(
    cls: Dict[str, Any],
    product_courses: List[Dict[str, Any]],
) -> str:
    categories = {
        normalize_text(course.get("subject_category"))
        for course in product_courses
        if course.get("product_id") == cls.get("product_id")
        and (not cls.get("subject") or course.get("subject") == cls.get("subject"))
        and normalize_text(course.get("subject_category"))
    }
    return sorted(categories)[0] if len(categories) == 1 else ""


def apply_class_label_defaults(
    cls: Dict[str, Any],
    product_meta: Dict[str, Dict[str, Any]],
    product_courses: List[Dict[str, Any]],
) -> None:
    product = product_meta.get(cls.get("product_id", ""), {})
    product_name = normalize_text(product.get("name"))
    class_name = normalize_text(cls.get("name"))
    project = normalize_text(product.get("project")) or infer_project(product_name or class_name)
    product_line = normalize_text(product.get("product_line")) or infer_product_line(product_name, class_name, project)
    standard_capacity = normalize_int(product.get("standard_capacity"))
    cls["project"] = project
    cls["product_line"] = product_line
    cls["sub_product"] = normalize_text(product.get("sub_product")) or infer_sub_product(product_line, product_name, class_name)
    cls["product_system"] = normalize_text(product.get("product_system"))
    cls["course_nature"] = normalize_text(product.get("course_nature"))
    cls["subject"] = normalize_text(product.get("subject")) or normalize_text(cls.get("subject"))
    cls["subject_category"] = normalize_text(product.get("subject_category")) or subject_category_for_class(cls, product_courses)
    cls["exam_season"] = normalize_exam_season(cls.get("exam_season"))
    cls["suite_code"] = normalize_text(cls.get("suite_code")) or infer_suite_code_from_class_name(class_name)
    cls["standard_capacity"] = standard_capacity
    cls["capacity_type"] = normalize_text(product.get("capacity_type")) or infer_capacity_type(standard_capacity)


def normalize_area_link(link: Dict[str, Any]) -> Dict[str, Any]:
    from_id = normalize_text(link.get("from_teaching_area_id"))
    to_id = normalize_text(link.get("to_teaching_area_id"))
    link_id = normalize_text(link.get("id")) or f"{from_id}__{to_id}"
    travel_minutes = normalize_int(
        link.get("travel_minutes") or link.get("driving_duration_minutes") or link.get("驾车时长分钟")
    )
    return {
        "id": link_id,
        "from_teaching_area_id": from_id,
        "to_teaching_area_id": to_id,
        "relation_type": normalize_text(link.get("relation_type")) or "可联排",
        "driving_distance_km": normalize_float(
            link.get("driving_distance_km") or link.get("distance_km") or link.get("驾车距离公里")
        ),
        "travel_minutes": travel_minutes,
        "notes": normalize_text(link.get("notes")),
    }


def normalize_blackout_date(item: Dict[str, Any]) -> Dict[str, Any]:
    start_date = normalize_date_text(item.get("start_date") or item.get("date"))
    end_date = normalize_date_text(item.get("end_date")) or start_date
    item_id = normalize_text(item.get("id")) or start_date
    return {
        "row": normalize_int(item.get("row")),
        "id": item_id,
        "name": normalize_text(item.get("name")) or "全局停课",
        "start_date": start_date,
        "end_date": end_date,
        "is_active": normalize_bool(item.get("is_active", True)),
        "notes": normalize_text(item.get("notes")),
    }


GENERIC_LIST_FIELDS = {
    "default_allowed_periods",
    "default_allowed_weekdays",
    "weekdays",
    "periods",
    "schedule_window_ids",
    "preferred_teaching_area_ids",
    "preferred_room_ids",
    "class_name_keywords",
}
GENERIC_BOOL_FIELDS = {
    "is_active",
    "is_usable",
    "preferred_room_is_required",
    "is_class_window_included",
    "is_locked",
    "effective_after_class_start",
}
GENERIC_INT_FIELDS = {
    "calendar_year",
    "window_year",
    "window_order",
    "order",
    "window_sequence",
}
GENERIC_FLOAT_FIELDS = {"duration_hours", "driving_distance_km", "travel_minutes"}
GENERIC_DATE_FIELDS = {"date", "start_date", "end_date", "earliest_date", "latest_date"}
GENERIC_TIME_FIELDS = {"start_time", "end_time"}


def normalize_generic_record(record: Dict[str, Any], fieldnames: List[str]) -> Dict[str, Any]:
    row: Dict[str, Any] = {}
    for field in fieldnames:
        value = record.get(field)
        if field in GENERIC_LIST_FIELDS:
            row[field] = split_id_list(value)
        elif field in GENERIC_BOOL_FIELDS:
            row[field] = normalize_bool(value)
        elif field in GENERIC_INT_FIELDS:
            row[field] = normalize_int(value)
        elif field in GENERIC_FLOAT_FIELDS:
            row[field] = normalize_float(value)
        elif field in GENERIC_DATE_FIELDS:
            row[field] = normalize_date_text(value)
        elif field in GENERIC_TIME_FIELDS:
            row[field] = normalize_time_text(value)
        else:
            row[field] = normalize_text(value)
    return row


def normalize_schedule_window(record: Dict[str, Any]) -> Dict[str, Any]:
    return normalize_generic_record(record, SCHEDULE_WINDOW_FIELDNAMES)


def normalize_time_slot(record: Dict[str, Any]) -> Dict[str, Any]:
    return normalize_generic_record(record, TIME_SLOT_FIELDNAMES)


def normalize_teacher_unavailability(record: Dict[str, Any]) -> Dict[str, Any]:
    return normalize_generic_record(record, TEACHER_UNAVAILABILITY_FIELDNAMES)


def normalize_class_window_boundary(record: Dict[str, Any]) -> Dict[str, Any]:
    return normalize_generic_record(record, CLASS_WINDOW_BOUNDARY_FIELDNAMES)


def normalize_business_product_mapping(record: Dict[str, Any]) -> Dict[str, Any]:
    current = dict(record)
    if not normalize_text(current.get("local_product_id")):
        current["local_product_id"] = normalize_text(
            current.get("canonical_product_id")
            or current.get("系统产品ID")
            or current.get("标准产品ID")
            or current.get("canonical_id")
        )
    return normalize_generic_record(current, BUSINESS_PRODUCT_MAPPING_FIELDNAMES)


def normalize_erp_standard_product(record: Dict[str, Any]) -> Dict[str, Any]:
    return normalize_generic_record(record, ERP_STANDARD_PRODUCT_FIELDNAMES)


def recompute_area_capacity(teaching_areas: List[Dict[str, Any]], rooms: List[Dict[str, Any]]) -> None:
    rooms_by_area: Dict[str, List[Dict[str, Any]]] = {}
    for room in rooms:
        rooms_by_area.setdefault(room.get("teaching_area_id", ""), []).append(room)

    for area in teaching_areas:
        area_rooms = rooms_by_area.get(area["id"], [])
        active_rooms = [room for room in area_rooms if normalize_bool(room.get("is_active"))]
        area["room_count"] = len(area_rooms)
        area["active_room_count"] = len(active_rooms)
        area["scheduling_capacity"] = sum(normalize_int(room.get("capacity")) for room in active_rooms)
        area["is_active"] = len(active_rooms) > 0
        area["capacity_check"] = "OK" if area["scheduling_capacity"] > 0 else "请补可用教室"


def validate_unique(rows: Iterable[Dict[str, Any]], key: str, label: str, errors: List[str]) -> None:
    seen: Set[str] = set()
    for row in rows:
        value = normalize_text(row.get(key))
        if not value:
            continue
        if value in seen:
            errors.append(f"{label} 存在重复 ID: {value}")
        seen.add(value)


def class_window_label(boundary: Dict[str, Any]) -> str:
    return (
        normalize_text(boundary.get("class_window_id"))
        or "/".join(
            value
            for value in (
                normalize_text(boundary.get("class_id")),
                normalize_text(boundary.get("schedule_window_id")),
                normalize_text(boundary.get("season_name")),
            )
            if value
        )
        or "未命名窗口"
    )


def validation_references(state: Dict[str, Any]) -> Dict[str, Any]:
    active_room_ids_by_area: Dict[str, Set[str]] = {}
    for room in state["rooms"]:
        room_id = normalize_text(room.get("id"))
        area_id = normalize_text(room.get("teaching_area_id"))
        if not room_id or not area_id or not normalize_bool(room.get("is_active")):
            continue
        active_room_ids_by_area.setdefault(area_id, set()).add(room_id)
    return {
        "teaching_area_ids": {area["id"] for area in state["teaching_areas"] if area["id"]},
        "room_ids": {room["id"] for room in state["rooms"] if room["id"]},
        "active_room_ids": {room["id"] for room in state["rooms"] if room["id"] and normalize_bool(room.get("is_active"))},
        "active_room_ids_by_area": active_room_ids_by_area,
        "product_ids": {product["id"] for product in state["products"] if product["id"]},
        "class_ids": {cls["id"] for cls in state["classes"] if cls["id"]},
    }


def validate_state_uniques(state: Dict[str, Any], errors: List[str]) -> None:
    validate_unique(state["teaching_areas"], "id", "教学区", errors)
    validate_unique(state["rooms"], "id", "教室", errors)
    validate_unique(state["teachers"], "employee_id", "教师", errors)
    validate_unique(state["products"], "id", "产品", errors)
    validate_unique(state["classes"], "id", "班级", errors)
    validate_unique(state["class_conflict_groups"], "id", "班级互斥关系", errors)
    validate_unique(state["product_schedule_rules"], "rule_id", "产品排课规则", errors)
    validate_unique(state["global_blackout_dates"], "id", "全局停课日期", errors)


def validate_room_references(state: Dict[str, Any], refs: Dict[str, Any], errors: List[str]) -> None:
    teaching_area_ids = refs["teaching_area_ids"]
    for room in state["rooms"]:
        if room["teaching_area_id"] and room["teaching_area_id"] not in teaching_area_ids:
            errors.append(f"教室 {room['name'] or room['id']} 关联了不存在的教学区 {room['teaching_area_id']}")


def validate_product_references(state: Dict[str, Any], refs: Dict[str, Any], errors: List[str]) -> None:
    product_ids = refs["product_ids"]
    for course in state["product_courses"]:
        if course["product_id"] and course["product_id"] not in product_ids:
            errors.append(f"产品课程 {course['product_id']}/{course['subject']}/{course['course_module']} 关联了不存在的产品 {course['product_id']}")
    for rule in state["product_schedule_rules"]:
        product_id = rule.get("product_id")
        if product_id and product_id not in product_ids:
            errors.append(f"排课规则 {rule['rule_id']} 关联了不存在的产品 {product_id}")
        if not product_id:
            errors.append(f"排课规则 {rule['rule_id']} 需要选择产品")


def validate_class_references(state: Dict[str, Any], refs: Dict[str, Any], errors: List[str]) -> None:
    product_ids = refs["product_ids"]
    teaching_area_ids = refs["teaching_area_ids"]
    room_ids = refs["room_ids"]
    for cls in state["classes"]:
        if cls["product_id"] and cls["product_id"] not in product_ids:
            errors.append(f"班级 {cls['name'] or cls['id']} 关联了不存在的产品 {cls['product_id']}")
        for area_id in cls["preferred_teaching_area_ids"]:
            if area_id not in teaching_area_ids:
                errors.append(f"班级 {cls['name'] or cls['id']} 关联了不存在的教学区 {area_id}")
        for room_id in cls["preferred_room_ids"]:
            if room_id not in room_ids and normalize_bool(cls.get("preferred_room_is_required")):
                errors.append(f"班级 {cls['name'] or cls['id']} 关联了不存在的教室 {room_id}")
        for requirement in cls.get("requirements", []):
            for room_id in requirement.get("room_ids", []):
                if room_id not in room_ids:
                    errors.append(f"班级 {cls['name'] or cls['id']} 的课程需求关联了不存在的教室 {room_id}")


def validate_class_window_references(state: Dict[str, Any], refs: Dict[str, Any], errors: List[str]) -> None:
    class_ids = refs["class_ids"]
    teaching_area_ids = refs["teaching_area_ids"]
    room_ids = refs["room_ids"]
    active_room_ids = refs["active_room_ids"]
    active_room_ids_by_area = refs["active_room_ids_by_area"]
    for boundary in state.get("class_window_boundaries", []):
        if not class_window_is_included(boundary):
            continue
        label = class_window_label(boundary)
        class_id = normalize_text(boundary.get("class_id"))
        if class_id and class_id not in class_ids:
            errors.append(f"班级排课窗口 {label} 关联了不存在的班级 {class_id}")
        area_ids = boundary.get("preferred_teaching_area_ids") or []
        room_ids_in_boundary = boundary.get("preferred_room_ids") or []
        for area_id in area_ids:
            if area_id not in teaching_area_ids:
                errors.append(f"班级排课窗口 {label} 关联了不存在的教学区 {area_id}")
        for room_id in room_ids_in_boundary:
            if room_id not in room_ids:
                errors.append(f"班级排课窗口 {label} 关联了不存在的教室 {room_id}")
            elif room_id not in active_room_ids:
                errors.append(f"班级排课窗口 {label} 关联的教室 {room_id} 未启用，不能用于自动排课")
        if area_ids and not room_ids_in_boundary:
            expanded_room_ids: Set[str] = set()
            for area_id in area_ids:
                expanded_room_ids.update(active_room_ids_by_area.get(area_id, set()))
            if not expanded_room_ids:
                errors.append(f"班级排课窗口 {label} 已填写教学区，但这些教学区下没有启用教室: {'|'.join(area_ids)}")
        if room_ids_in_boundary and not any(room_id in active_room_ids for room_id in room_ids_in_boundary):
            errors.append(f"班级排课窗口 {label} 已填写教室，但没有任何启用教室可用于自动排课: {'|'.join(room_ids_in_boundary)}")


def validate_conflict_group_references(state: Dict[str, Any], refs: Dict[str, Any], errors: List[str]) -> None:
    class_ids = refs["class_ids"]
    for group in state["class_conflict_groups"]:
        if class_conflict_group_is_active(group) and len(group.get("class_ids", [])) < 2:
            errors.append(f"班级互斥关系 {group['name'] or group['id']} 至少需要选择 2 个班级")
        for class_id in group.get("class_ids", []):
            if class_id not in class_ids:
                errors.append(f"班级互斥关系 {group['name'] or group['id']} 包含不存在的班级 {class_id}")


def validate_locked_lesson_references(state: Dict[str, Any], refs: Dict[str, Any], errors: List[str]) -> None:
    class_ids = refs["class_ids"]
    room_ids = refs["room_ids"]
    for lesson in state.get("locked_scheduled_lessons", []):
        if lesson.get("class_id") and lesson["class_id"] not in class_ids:
            errors.append(f"锁定课表 {lesson['id']} 关联了不存在的班级 {lesson['class_id']}")
        if lesson.get("room_id") and lesson["room_id"] not in room_ids:
            errors.append(f"锁定课表 {lesson['id']} 关联了不存在的教室 {lesson['room_id']}")


def validate_teaching_area_link_references(state: Dict[str, Any], refs: Dict[str, Any], errors: List[str]) -> None:
    teaching_area_ids = refs["teaching_area_ids"]
    for link in state["teaching_area_links"]:
        for field in ("from_teaching_area_id", "to_teaching_area_id"):
            if link[field] and link[field] not in teaching_area_ids:
                errors.append(f"教学区通勤关系 {link['id']} 包含不存在的教学区 {link[field]}")


def validate_state(state: Dict[str, Any]) -> None:
    errors: List[str] = []
    refs = validation_references(state)

    validate_state_uniques(state, errors)
    validate_room_references(state, refs, errors)
    validate_product_references(state, refs, errors)
    validate_class_references(state, refs, errors)
    validate_class_window_references(state, refs, errors)
    validate_conflict_group_references(state, refs, errors)
    validate_locked_lesson_references(state, refs, errors)
    validate_teaching_area_link_references(state, refs, errors)

    if errors:
        raise ValueError("\n".join(errors))


def save_state(payload: Dict[str, Any]) -> Dict[str, Any]:
    state = normalize_payload(payload)
    updated_at = today_text()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for table_name, rows in standard_table_rows(state).items():
        document: Dict[str, Any] = {
            "updated_at": updated_at,
            "source": "data_admin_server.py",
            "record_count": len(rows),
            table_name: rows,
        }
        if table_name in TABLES_WITH_EMPTY_WARNINGS:
            document["warnings"] = []
        write_json(DATA_DIR / f"{table_name}.json", document)
    write_csvs(state)
    return {"ok": True, "updated_at": updated_at, "counts": {key: len(value) for key, value in state.items()}}


def standard_row(row: Dict[str, Any], fieldnames: List[str], extra_fieldnames: Iterable[str] = ()) -> Dict[str, Any]:
    output = {field: row[field] for field in fieldnames if field in row}
    for field in extra_fieldnames:
        if field in row:
            output[field] = row[field]
    return output


def standard_rows(rows: List[Dict[str, Any]], fieldnames: List[str], extra_fieldnames: Iterable[str] = ()) -> List[Dict[str, Any]]:
    return [standard_row(row, fieldnames, extra_fieldnames) for row in rows]


def standard_table_rows(state: Dict[str, Any], *, csv_export: bool = False) -> Dict[str, List[Dict[str, Any]]]:
    class_extra_fieldnames: Iterable[str] = () if csv_export else CLASS_JSON_EXTRA_FIELDNAMES
    source_rows = {table_name: list(state.get(table_name, [])) for table_name in STANDARD_TABLE_FIELDNAMES}
    source_rows["class_teacher_assignments"] = class_teacher_assignment_rows(state)

    output: Dict[str, List[Dict[str, Any]]] = {}
    for table_name, fieldnames in STANDARD_TABLE_FIELDNAMES.items():
        extra_fieldnames = class_extra_fieldnames if table_name == "classes" else ()
        output[table_name] = standard_rows(source_rows[table_name], fieldnames, extra_fieldnames)
    return output


def write_csvs(state: Dict[str, Any]) -> None:
    for table_name, rows in standard_table_rows(state, csv_export=True).items():
        write_csv(DATA_DIR / f"{table_name}.csv", rows, STANDARD_TABLE_FIELDNAMES[table_name])

def build_suite_conflict_groups(classes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups: Dict[str, Dict[str, Any]] = {}
    for cls in classes:
        suite_code = normalize_text(cls.get("suite_code"))
        if not suite_code:
            continue
        exam_season = normalize_text(cls.get("exam_season"))
        group_key = f"{exam_season}__{suite_code}" if exam_season else suite_code
        group = groups.setdefault(
            group_key,
            {
                "id": f"SUITE_{group_key}",
                "name": f"{exam_season + ' ' if exam_season else ''}{suite_code} 套班互斥",
                "exam_season": exam_season,
                "suite_code": suite_code,
                "class_ids": [],
                "is_conflict_group_active": True,
                "conflict_source": "套班编码",
                "notes": "按套班编码自动生成",
            },
        )
        group["class_ids"].append(cls["id"])

    result = []
    for group in sorted(groups.values(), key=lambda item: item["id"]):
        unique_class_ids = unique_list(group["class_ids"])
        if len(unique_class_ids) < 2:
            continue
        group["class_ids"] = unique_class_ids
        result.append(group)
    return result


def scheduler_conflict_groups(
    state: Dict[str, Any],
    classes: List[Dict[str, Any]],
    locked_scheduled_lessons: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    groups = state.get("class_conflict_groups") or build_suite_conflict_groups(classes)
    result: List[Dict[str, Any]] = []
    class_ids = {cls["id"] for cls in classes}
    class_ids.update(lesson.get("class_id", "") for lesson in locked_scheduled_lessons or [])
    class_ids.discard("")
    for group in groups:
        if not class_conflict_group_is_active(group):
            continue
        group_class_ids = [class_id for class_id in unique_list(group.get("class_ids", [])) if class_id in class_ids]
        if len(group_class_ids) < 2:
            continue
        result.append({"id": normalize_text(group.get("id")) or f"CONFLICT_{len(result) + 1}", "class_ids": group_class_ids})
    return result


def scheduler_locked_lessons(lessons: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for lesson in lessons:
        if not normalize_bool(lesson.get("is_locked")):
            continue
        row = {
            "id": lesson.get("id", ""),
            "class_id": lesson.get("class_id", ""),
            "class_name": lesson.get("class_name", ""),
            "date": lesson.get("date", ""),
            "period": lesson.get("period", ""),
            "start_time": lesson.get("start_time", ""),
            "end_time": lesson.get("end_time", ""),
            "teacher_id": lesson.get("teacher_id", ""),
            "teacher_name": lesson.get("teacher_name", ""),
            "room_id": lesson.get("room_id", ""),
            "subject": lesson.get("subject", ""),
            "quarter": lesson.get("quarter", ""),
            "stage": lesson.get("stage", ""),
            "course_module": lesson.get("course_module", ""),
            "course_group": lesson.get("course_group", ""),
            "course_code": lesson.get("course_code", ""),
            "course_name": lesson.get("course_name", ""),
            "business_product_id": lesson.get("business_product_id", ""),
            "business_product_name": lesson.get("business_product_name", ""),
        }
        if row["class_id"] and row["date"] and row["room_id"]:
            result.append({key: value for key, value in row.items() if value not in ("", None, [])})
    return result


def scheduler_teacher_unavailability(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for row in rows:
        if not normalize_bool(row.get("is_active")):
            continue
        teacher_id = normalize_text(row.get("teacher_id") or row.get("employee_id") or row.get("id"))
        if not teacher_id:
            continue
        start_date = normalize_date_text(row.get("start_date"))
        end_date = normalize_date_text(row.get("end_date"))
        weekdays = split_id_list(row.get("weekdays"))
        periods = split_id_list(row.get("periods"))
        schedule_window_ids = split_id_list(row.get("schedule_window_ids"))
        if not any((start_date, end_date, weekdays, periods, schedule_window_ids)):
            continue
        item = {
            "unavailable_id": normalize_text(row.get("unavailable_id")),
            "teacher_id": teacher_id,
            "employee_id": teacher_id,
            "teacher_name": normalize_text(row.get("teacher_name")),
            "unavailable_type": normalize_text(row.get("unavailable_type")),
            "start_date": start_date,
            "end_date": end_date,
            "weekdays": weekdays,
            "periods": periods,
            "schedule_window_ids": schedule_window_ids,
            "is_active": True,
            "reason": normalize_text(row.get("reason")),
            "notes": normalize_text(row.get("notes")),
        }
        result.append({key: value for key, value in item.items() if value not in ("", None, [])})
    return result


def scheduler_teacher_assignments(cls: Dict[str, Any]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    class_id = normalize_text(cls.get("id"))
    for raw_assignment in cls.get("teacher_assignments", []):
        assignment = normalize_teacher_assignment({"class_id": class_id, **raw_assignment})
        item = {
            "product_id": assignment.get("product_id"),
            "product_name": assignment.get("product_name"),
            "subject": assignment.get("subject"),
            "stage": assignment.get("stage"),
            "course_group": assignment.get("course_group"),
            "class_schedule_mode": assignment.get("class_schedule_mode"),
            "actual_scheduled_class_id": assignment.get("actual_scheduled_class_id") or class_id,
            "teacher_id": assignment.get("teacher_id"),
            "teacher_name": assignment.get("teacher_name"),
            "assignment_extra_time_requirement": assignment.get("assignment_extra_time_requirement"),
            "notes": assignment.get("notes"),
        }
        result.append({key: value for key, value in item.items() if value not in ("", None, [])})
    return result


def class_window_is_included(record: Dict[str, Any]) -> bool:
    value = normalize_text(record.get("is_class_window_included"))
    return not value or normalize_bool(value)


def class_window_has_room_constraint(boundary: Dict[str, Any]) -> bool:
    return bool(boundary.get("preferred_teaching_area_ids") or boundary.get("preferred_room_ids"))


def class_window_room_ids(
    boundary: Dict[str, Any],
    rooms_by_area: Dict[str, List[Dict[str, Any]]],
) -> List[str]:
    preferred_room_ids = list(boundary.get("preferred_room_ids") or [])
    if preferred_room_ids:
        return sorted(set(preferred_room_ids))
    room_ids: Set[str] = set()
    for area_id in boundary.get("preferred_teaching_area_ids") or []:
        room_ids.update(room["id"] for room in rooms_by_area.get(area_id, []))
    return sorted(room_ids)


def scheduler_class_window_boundaries(
    state: Dict[str, Any],
    rooms_by_area: Dict[str, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for boundary in state.get("class_window_boundaries", []):
        class_id = normalize_text(boundary.get("class_id"))
        if not class_id or not class_window_is_included(boundary):
            continue
        row = {
            "class_window_id": boundary.get("class_window_id", ""),
            "class_id": class_id,
            "schedule_window_id": boundary.get("schedule_window_id", ""),
            "season_window_id": boundary.get("season_window_id", ""),
            "season_name": boundary.get("season_name", ""),
            "schedule_window_name": boundary.get("schedule_window_name", ""),
            "earliest_date": boundary.get("earliest_date", ""),
            "earliest_period": boundary.get("earliest_period", ""),
            "latest_date": boundary.get("latest_date", ""),
            "latest_period": boundary.get("latest_period", ""),
            "room_ids": class_window_room_ids(boundary, rooms_by_area),
            "is_class_window_included": True,
        }
        if class_window_has_room_constraint(boundary):
            row["has_room_constraint"] = True
        rows.append({key: value for key, value in row.items() if value not in ("", None, [])})
    return rows


def class_ids_with_window_boundaries(state: Dict[str, Any]) -> Set[str]:
    return {
        normalize_text(boundary.get("class_id"))
        for boundary in state.get("class_window_boundaries", [])
        if normalize_text(boundary.get("class_id")) and class_window_is_included(boundary)
    }


def scheduler_time_slots(
    state: Dict[str, Any],
    raw_time_slots: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    return [
        slot for slot in raw_time_slots
        if slot_is_usable(slot)
        and not slot_is_blackout(slot, state["global_blackout_dates"])
    ]


def active_scheduler_rooms(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [room for room in state["rooms"] if normalize_bool(room.get("is_active"))]


def rooms_by_teaching_area(rooms: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for room in rooms:
        grouped.setdefault(room["teaching_area_id"], []).append(room)
    return grouped


def scheduler_product_payloads(
    product_courses: List[Dict[str, Any]],
    product_meta: Dict[str, Dict[str, Any]],
    referenced_product_ids: Set[str],
) -> List[Dict[str, Any]]:
    products: Dict[str, Dict[str, Any]] = {}
    for course in product_courses:
        product_id = course["product_id"]
        if not product_id or product_id not in referenced_product_ids:
            continue
        meta = product_meta.get(product_id, {})
        product = products.setdefault(
            product_id,
            {
                "id": product_id,
                "name": meta.get("name") or course["product_name"] or product_id,
                "project": meta.get("project", ""),
                "product_line": meta.get("product_line", ""),
                "sub_product": meta.get("sub_product", ""),
                "product_system": meta.get("product_system", ""),
                "standard_capacity": meta.get("standard_capacity", 0),
                "capacity_type": meta.get("capacity_type", ""),
                "subject": meta.get("subject", ""),
                "subject_category": meta.get("subject_category", ""),
                "course_nature": meta.get("course_nature", ""),
                "requirements": [],
            },
        )
        product["requirements"].append(
            {
                "subject_category": course["subject_category"],
                "subject": course["subject"],
                "window_name": course.get("window_name") or course.get("quarter", ""),
                "stage": course["stage"],
                "course_module": course["course_module"],
                "course_group": course["course_group"],
                "course_code": course.get("course_code", ""),
                "course_name": course.get("course_name", ""),
                "total_hours": course["total_hours"],
            }
        )
        legacy_block_hours = normalize_int(course.get("block_hours"))
        if legacy_block_hours:
            product["requirements"][-1]["block_hours"] = legacy_block_hours
    return list(products.values())


def scheduler_class_payloads(
    classes: List[Dict[str, Any]],
    product_meta: Dict[str, Dict[str, Any]],
    classes_with_window_boundaries: Set[str],
    rooms_by_area: Dict[str, List[Dict[str, Any]]],
    active_rooms: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    result = []
    for cls in classes:
        meta = product_meta.get(cls.get("product_id", ""), {})
        class_row = {
            "id": cls["id"],
            "name": cls["name"],
            "product_id": cls["product_id"],
            "project": cls.get("project", ""),
            "product_line": cls.get("product_line", ""),
            "sub_product": cls.get("sub_product", ""),
            "product_system": cls.get("product_system", ""),
            "course_nature": cls.get("course_nature", ""),
            "subject_category": cls.get("subject_category", ""),
            "subject": cls["subject"],
            "selected_stages": split_id_list(cls.get("selected_stages") or cls.get("stages")),
            "exam_season": cls.get("exam_season", ""),
            "exam_month": cls.get("exam_month", ""),
            "suite_code": cls.get("suite_code", ""),
            "standard_capacity": cls.get("standard_capacity", 0),
            "capacity_type": cls.get("capacity_type", ""),
            "size": cls["size"],
            "start_date": cls["start_date"] or None,
            "start_period": cls["start_period"] or None,
            "first_lesson_date": cls.get("first_lesson_date") or None,
            "first_lesson_period": cls.get("first_lesson_period") or None,
            "end_date": cls["end_date"] or None,
            "end_period": cls["end_period"] or None,
            "teacher_assignments": scheduler_teacher_assignments(cls),
        }
        stage_order = product_stage_order(meta, cls)
        if stage_order:
            class_row["stage_order"] = stage_order
        if cls["id"] not in classes_with_window_boundaries:
            class_room_ids = class_room_constraint(cls, rooms_by_area, active_rooms)
            if class_room_ids:
                class_row["room_ids"] = class_room_ids
        requirements = scheduler_class_requirements(cls)
        if requirements:
            class_row["requirements"] = requirements
        result.append({key: value for key, value in class_row.items() if value not in ("", None, [])})
    return result


def scheduler_room_payloads(
    rooms: List[Dict[str, Any]],
    area_by_id: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    return [
        {
            "id": room["id"],
            "name": room.get("name", ""),
            "capacity": room.get("capacity", 0),
            "capacity_unlimited": room_capacity_unlimited(room),
            "teaching_area_id": room.get("teaching_area_id", ""),
            "teaching_area_name": room.get("teaching_area_name", ""),
            "region_tag": area_by_id.get(room.get("teaching_area_id", ""), {}).get("region_tag", ""),
        }
        for room in rooms
    ]


def scheduler_teaching_area_payloads(teaching_areas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "id": area["id"],
            "name": area.get("name", ""),
            "short_name": area.get("short_name", ""),
            "region_tag": area.get("region_tag", ""),
        }
        for area in teaching_areas
        if area.get("id")
    ]


def build_scheduler_input(
    payload: Optional[Dict[str, Any]] = None,
    time_slots: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    state = normalize_payload(payload) if payload else normalize_payload(load_state())
    if time_slots is None:
        time_slots_doc = read_json(DEFAULT_TIME_SLOTS, {"time_slots": []})
        raw_time_slots = time_slots_doc.get("time_slots", [])
    else:
        raw_time_slots = time_slots
    filtered_time_slots = scheduler_time_slots(state, raw_time_slots)
    rooms = active_scheduler_rooms(state)
    room_groups = rooms_by_teaching_area(rooms)
    area_by_id = {area["id"]: area for area in state["teaching_areas"] if area.get("id")}
    class_window_rows = scheduler_class_window_boundaries(state, room_groups)

    schedulable_classes = [cls for cls in state["classes"] if not normalize_bool(cls.get("is_manual_schedule_locked"))]
    classes_with_window_boundaries = class_ids_with_window_boundaries(state)
    referenced_product_ids = {cls["product_id"] for cls in schedulable_classes if cls.get("product_id")}
    product_meta = product_catalog(state["products"], state["product_courses"])
    products = scheduler_product_payloads(state["product_courses"], product_meta, referenced_product_ids)
    classes = scheduler_class_payloads(
        schedulable_classes,
        product_meta,
        classes_with_window_boundaries,
        room_groups,
        rooms,
    )

    return {
        "time_slots": filtered_time_slots,
        "rooms": scheduler_room_payloads(rooms, area_by_id),
        "teaching_areas": scheduler_teaching_area_payloads(state["teaching_areas"]),
        "teaching_area_links": list(state.get("teaching_area_links", [])),
        "products": products,
        "product_schedule_rules": scheduler_rules(state["product_schedule_rules"], referenced_product_ids),
        "classes": classes,
        "conflict_groups": scheduler_conflict_groups(state, classes, state.get("locked_scheduled_lessons", [])),
        "locked_lessons": scheduler_locked_lessons(state.get("locked_scheduled_lessons", [])),
        "teacher_unavailability": scheduler_teacher_unavailability(state.get("teacher_unavailability", [])),
        "class_window_boundaries": class_window_rows,
    }


def export_scheduler_input(
    payload: Optional[Dict[str, Any]] = None,
    time_slots: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    scheduler_input = build_scheduler_input(payload, time_slots)
    out_path = DATA_DIR / "scheduler_input_draft.json"
    write_json(out_path, scheduler_input)
    return {
        "ok": True,
        "path": str(out_path),
        "counts": {
            "time_slots": len(scheduler_input["time_slots"]),
            "rooms": len(scheduler_input["rooms"]),
            "products": len(scheduler_input["products"]),
            "classes": len(scheduler_input["classes"]),
            "conflict_groups": len(scheduler_input["conflict_groups"]),
            "locked_lessons": len(scheduler_input["locked_lessons"]),
            "teacher_unavailability": len(scheduler_input["teacher_unavailability"]),
        },
    }


def products_csv_download_text() -> str:
    state = normalize_payload(load_state())
    return csv_text(state["products"], PRODUCT_FIELDNAMES)


def classes_csv_download_text() -> str:
    state = normalize_payload(load_state())
    rows = [{key: value for key, value in cls.items() if key != "teacher_assignments"} for cls in state["classes"]]
    return csv_text(rows, CLASS_FIELDNAMES)


def import_products_csv(payload: Dict[str, Any]) -> Dict[str, Any]:
    content = payload.get("csv", payload.get("content", ""))
    if not isinstance(content, str) or not content.strip():
        raise ValueError("请上传产品 CSV 文件")

    reader = csv.DictReader(io.StringIO(content.lstrip("\ufeff")))
    if not reader.fieldnames:
        raise ValueError("产品 CSV 缺少表头")

    state = load_state()
    existing_by_id = {
        normalize_text(product.get("id")): normalize_product(product)
        for product in state.get("products", [])
        if normalize_text(product.get("id"))
    }
    imported_ids: Set[str] = set()

    for row_number, row in enumerate(reader, start=2):
        if not any(normalize_text(value) for value in row.values()):
            continue
        product_id = normalize_text(row.get("id") or row.get("product_id"))
        if not product_id:
            raise ValueError(f"产品 CSV 第 {row_number} 行缺少 id")
        if product_id in imported_ids:
            raise ValueError(f"产品 CSV 中存在重复产品 ID: {product_id}")

        base = dict(existing_by_id.get(product_id, {}))
        for field in reader.fieldnames:
            if field:
                base[field] = row.get(field, "")
        normalized = normalize_product(base)
        existing_by_id[normalized["id"]] = normalized
        imported_ids.add(normalized["id"])

    if not imported_ids:
        raise ValueError("产品 CSV 中没有可导入的数据行")

    state["products"] = sorted(existing_by_id.values(), key=lambda product: product["id"])
    result = save_state(state)
    result["imported"] = len(imported_ids)
    result["total_products"] = len(state["products"])
    return result


def import_classes_csv(payload: Dict[str, Any]) -> Dict[str, Any]:
    content = payload.get("csv", payload.get("content", ""))
    if not isinstance(content, str) or not content.strip():
        raise ValueError("请上传班级 CSV 文件")

    reader = csv.DictReader(io.StringIO(content.lstrip("\ufeff")))
    if not reader.fieldnames:
        raise ValueError("班级 CSV 缺少表头")

    state = load_state()
    existing_by_id = {
        normalize_text(cls.get("id")): normalize_class(cls)
        for cls in state.get("classes", [])
        if normalize_text(cls.get("id"))
    }
    imported_ids: Set[str] = set()

    for row_number, row in enumerate(reader, start=2):
        if not any(normalize_text(value) for value in row.values()):
            continue
        class_id = normalize_text(row.get("id") or row.get("class_id"))
        if not class_id:
            raise ValueError(f"班级 CSV 第 {row_number} 行缺少 id")
        if class_id in imported_ids:
            raise ValueError(f"班级 CSV 中存在重复班级 ID: {class_id}")

        base = dict(existing_by_id.get(class_id, {}))
        teacher_assignments = base.get("teacher_assignments", [])
        for field in reader.fieldnames:
            if field:
                base[field] = row.get(field, "")
        base["id"] = class_id
        base["teacher_assignments"] = teacher_assignments
        normalized = normalize_class(base)
        existing_by_id[normalized["id"]] = normalized
        imported_ids.add(normalized["id"])

    if not imported_ids:
        raise ValueError("班级 CSV 中没有可导入的数据行")

    state["classes"] = sorted(existing_by_id.values(), key=lambda cls: cls["id"])
    result = save_state(state)
    result["imported"] = len(imported_ids)
    result["total_classes"] = len(state["classes"])
    return result


def class_room_constraint(
    cls: Dict[str, Any],
    rooms_by_area: Dict[str, List[Dict[str, Any]]],
    active_rooms: List[Dict[str, Any]],
) -> List[str]:
    preferred_room_ids = set(cls.get("preferred_room_ids") or [])
    preferred_area_ids = set(cls.get("preferred_teaching_area_ids") or [])
    if preferred_room_ids and normalize_bool(cls.get("preferred_room_is_required")):
        room_ids = set(preferred_room_ids)
        if preferred_area_ids:
            area_room_ids: Set[str] = set()
            for area_id in preferred_area_ids:
                area_room_ids.update(room["id"] for room in rooms_by_area.get(area_id, []))
            room_ids &= area_room_ids
        return sorted(room_ids)

    room_area_ids = {
        room.get("teaching_area_id", "")
        for room in active_rooms
        if room.get("id") in preferred_room_ids and room.get("teaching_area_id")
    }
    area_ids = preferred_area_ids | room_area_ids
    if area_ids:
        result: List[str] = []
        for area_id in area_ids:
            result.extend(room["id"] for room in rooms_by_area.get(area_id, []))
        return sorted(set(result))
    return []


def room_capacity_unlimited(room: Dict[str, Any]) -> bool:
    text = " ".join(
        normalize_text(room.get(key))
        for key in ("id", "name", "teaching_area_id", "teaching_area_name", "campus", "room_type", "notes")
    )
    return "线上" in text or "网络" in text


def scheduler_class_requirements(cls: Dict[str, Any]) -> List[Dict[str, Any]]:
    requirements: List[Dict[str, Any]] = []
    for requirement in cls.get("requirements", []):
        row = {
            "subject_category": requirement.get("subject_category", ""),
            "subject": requirement.get("subject", ""),
            "window_name": requirement.get("window_name") or requirement.get("quarter", ""),
            "stage": requirement.get("stage", ""),
            "course_module": requirement.get("course_module", ""),
            "course_group": requirement.get("course_group", ""),
            "course_code": requirement.get("course_code", ""),
            "course_name": requirement.get("course_name", ""),
            "teacher_id": requirement.get("teacher_id", ""),
            "teacher_name": requirement.get("teacher_name", ""),
            "total_hours": requirement.get("total_hours", 0),
            "block_hours": requirement.get("block_hours", 0),
            "room_ids": requirement.get("room_ids") or [],
            "start_date": requirement.get("start_date", ""),
            "end_date": requirement.get("end_date", ""),
            "allowed_periods": requirement.get("allowed_periods", []),
            "allowed_weekdays": requirement.get("allowed_weekdays", []),
            "excluded_weekdays": requirement.get("excluded_weekdays", []),
        }
        requirements.append({key: value for key, value in row.items() if value not in ("", None, [])})
    return requirements


def scheduler_rules(
    rules: List[Dict[str, Any]],
    referenced_product_ids: Set[str],
) -> List[Dict[str, Any]]:
    result = []
    for rule in rules:
        product_id = normalize_text(rule.get("product_id"))
        if not product_id or product_id not in referenced_product_ids:
            continue
        block_hours = normalize_float(rule.get("block_hours"))
        max_hours_per_class_per_day = normalize_float(rule.get("max_hours_per_class_per_day"))
        max_blocks_per_class_per_day = normalize_int(rule.get("max_blocks_per_class_per_day"))
        min_weekly_hours = normalize_float(rule.get("min_weekly_hours"))
        max_weekly_hours = normalize_float(rule.get("max_weekly_hours"))
        item = {
            "product_id": product_id,
            "subject": rule.get("subject") or None,
            "stage": rule.get("stage") or None,
            "course_module": rule.get("course_module") or None,
            "course_group": rule.get("course_group") or None,
            "season_window_id": rule.get("season_window_id") or None,
            "window_name": rule.get("window_name") or None,
            "schedule_window_id": rule.get("schedule_window_id") or None,
            "start_date": rule.get("start_date") or None,
            "end_date": rule.get("end_date") or None,
            "allowed_periods": rule.get("allowed_periods", []),
            "allowed_weekdays": rule.get("allowed_weekdays", []),
            "excluded_weekdays": rule.get("excluded_weekdays", []),
        }
        if block_hours > 0:
            item["block_hours"] = block_hours
        if max_hours_per_class_per_day > 0:
            item["max_hours_per_class_per_day"] = max_hours_per_class_per_day
        if max_blocks_per_class_per_day > 0:
            item["max_blocks_per_class_per_day"] = max_blocks_per_class_per_day
        if min_weekly_hours > 0:
            item["min_weekly_hours"] = min_weekly_hours
        if max_weekly_hours > 0:
            item["max_weekly_hours"] = max_weekly_hours
        result.append({key: value for key, value in item.items() if value not in ("", None, [])})
    return result


def slot_is_blackout(slot: Dict[str, Any], blackouts: List[Dict[str, Any]]) -> bool:
    slot_date = normalize_text(slot.get("date"))
    if not slot_date:
        return False
    for blackout in blackouts:
        if not normalize_bool(blackout.get("is_active", True)):
            continue
        start_date = normalize_text(blackout.get("start_date"))
        end_date = normalize_text(blackout.get("end_date")) or start_date
        if start_date and start_date <= slot_date <= end_date:
            return True
    return False


def slot_is_usable(slot: Dict[str, Any]) -> bool:
    if "is_usable" not in slot or slot.get("is_usable") in ("", None):
        return True
    return normalize_bool(slot.get("is_usable"))


def safe_upload_filename(name: str) -> str:
    cleaned = Path(name).name.strip()
    if not cleaned:
        raise ValueError("上传文件缺少文件名")
    suffix = Path(cleaned).suffix.lower()
    if suffix not in ALLOWED_UPLOAD_SUFFIXES:
        raise ValueError(f"不支持的上传文件类型: {cleaned}")
    safe = "".join(char if char.isalnum() or char in ".-_()（）[]【】 " else "_" for char in cleaned)
    return safe or f"upload{suffix}"


def path_url(path: Optional[Path]) -> str:
    if not path:
        return ""
    try:
        relative_output = path.resolve().relative_to(OUTPUT_DIR.resolve())
        return "/outputs/" + relative_output.as_posix()
    except ValueError:
        pass
    try:
        relative = path.resolve().relative_to(ROOT)
    except ValueError:
        return ""
    return "/" + relative.as_posix()


def file_status_entry(key: str, label: str, detail: str, path: Path, *, preview_url: str = "") -> Dict[str, Any]:
    exists = path.exists() and path.is_file()
    updated_at = ""
    size_bytes = 0
    if exists:
        stat = path.stat()
        updated_at = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
        size_bytes = stat.st_size
    return {
        "key": key,
        "label": label,
        "detail": detail,
        "path": str(path),
        "url": path_url(path),
        "preview_url": preview_url,
        "exists": exists,
        "updated_at": updated_at,
        "size_bytes": size_bytes,
    }


def current_results_status() -> Dict[str, Any]:
    template_path = OUTPUT_DIR / "ai_scheduling_sop_20260625" / "AI排课基础数据模板.xlsx"
    return {
        "ok": True,
        "template": file_status_entry(
            "data_template",
            "AI排课基础数据模板",
            "下载后填写基础数据；如果文件缺失，可用原始导出生成预填模板。",
            template_path,
        ),
        "results": [
            file_status_entry(
                "schedule_html",
                "课表总表",
                "按班级、课次、老师、教室和锁定状态核对排课结果。",
                OUTPUT_DIR / "batch_schedule_maintenance.html",
            ),
            file_status_entry(
                "schedule_report",
                "排课报告",
                "查看覆盖、冲突、缺口和生成过程摘要。",
                OUTPUT_DIR / "batch_schedule_maintenance_report.md",
                preview_url="/preview/outputs/batch_schedule_maintenance_report.md",
            ),
            file_status_entry(
                "schedule_csv",
                "CSV 明细",
                "用于 ERP 对齐、二次分析或导入核对。",
                OUTPUT_DIR / "batch_schedule_maintenance.csv",
            ),
        ],
    }


def output_path_from_url(path_text: str) -> Path:
    normalized = unquote(path_text)
    if normalized == "/outputs":
        relative_text = ""
    elif normalized.startswith("/outputs/"):
        relative_text = normalized[len("/outputs/"):]
    else:
        raise ValueError("只能访问 outputs 目录下的文件")
    path = (OUTPUT_DIR / relative_text).resolve()
    output_root = OUTPUT_DIR.resolve()
    if path != output_root and output_root not in path.parents:
        raise ValueError("只能访问 outputs 目录下的文件")
    return path


def project_file_from_url(path_text: str, prefix: str, root_dir: Path) -> Path:
    normalized = unquote(path_text)
    if normalized == prefix:
        relative_text = ""
    elif normalized.startswith(prefix + "/"):
        relative_text = normalized[len(prefix) + 1:]
    else:
        raise ValueError(f"只能访问 {prefix} 目录下的文件")
    path = (root_dir / relative_text).resolve()
    root = root_dir.resolve()
    if path != root and root not in path.parents:
        raise ValueError(f"只能访问 {prefix} 目录下的文件")
    return path


def mime_type_for(path: Path) -> str:
    suffix = path.suffix.lower()
    explicit_types = {
        ".css": "text/css",
        ".csv": "text/csv",
        ".html": "text/html",
        ".js": "application/javascript",
        ".json": "application/json",
        ".md": "text/markdown",
        ".mjs": "application/javascript",
        ".svg": "image/svg+xml",
        ".txt": "text/plain",
    }
    mime_type = explicit_types.get(suffix) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    text_suffixes = set(explicit_types)
    if path.suffix.lower() in text_suffixes or mime_type.startswith("text/"):
        if "charset=" not in mime_type:
            return f"{mime_type}; charset=utf-8"
    return mime_type


def content_disposition_value(disposition: str, filename: str) -> str:
    ascii_filename = filename.encode("ascii", "ignore").decode("ascii").replace('"', "")
    if not ascii_filename:
        suffix = Path(filename).suffix or ".dat"
        ascii_filename = f"download{suffix}"
    encoded_filename = quote(filename)
    return f'{disposition}; filename="{ascii_filename}"; filename*=UTF-8\'\'{encoded_filename}'


def read_utf8_text(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


MARKDOWN_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
MARKDOWN_UNORDERED_LIST_RE = re.compile(r"^\s*[-*]\s+(.+)$")
MARKDOWN_ORDERED_LIST_RE = re.compile(r"^\s*\d+[.)]\s+(.+)$")
MARKDOWN_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")


def markdown_preview_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or fallback
    return fallback


def markdown_table_cells(line: str) -> List[str]:
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|"):
        text = text[:-1]
    return [cell.strip() for cell in text.split("|")]


def is_markdown_table_start(lines: List[str], index: int) -> bool:
    return (
        index + 1 < len(lines)
        and "|" in lines[index]
        and bool(MARKDOWN_TABLE_SEPARATOR_RE.match(lines[index + 1].strip()))
    )


def render_markdown_table(headers: List[str], rows: List[List[str]]) -> str:
    header_html = "".join(f"<th>{html_lib.escape(header)}</th>" for header in headers)
    body_rows = []
    width = len(headers)
    for row in rows:
        padded = [*row, *([""] * max(0, width - len(row)))]
        cells = "".join(f"<td>{html_lib.escape(cell)}</td>" for cell in padded[:width])
        body_rows.append(f"<tr>{cells}</tr>")
    body_html = "\n".join(body_rows)
    return f"<table><thead><tr>{header_html}</tr></thead><tbody>{body_html}</tbody></table>"


def render_markdown_table_at(lines: List[str], index: int) -> Tuple[str, int]:
    headers = markdown_table_cells(lines[index])
    index += 2
    rows = []
    while index < len(lines) and lines[index].strip().startswith("|"):
        if MARKDOWN_TABLE_SEPARATOR_RE.match(lines[index].strip()):
            index += 1
            continue
        rows.append(markdown_table_cells(lines[index]))
        index += 1
    return render_markdown_table(headers, rows), index


def render_markdown_list_at(lines: List[str], index: int, ordered: bool) -> Tuple[str, int]:
    pattern = MARKDOWN_ORDERED_LIST_RE if ordered else MARKDOWN_UNORDERED_LIST_RE
    tag = "ol" if ordered else "ul"
    items = []
    while index < len(lines):
        match = pattern.match(lines[index])
        if not match:
            break
        items.append(f"<li>{html_lib.escape(match.group(1).strip())}</li>")
        index += 1
    return f"<{tag}>\n{''.join(items)}\n</{tag}>", index


def render_markdown_code_block_at(lines: List[str], index: int) -> Tuple[str, int]:
    code_lines = []
    index += 1
    while index < len(lines):
        if lines[index].strip().startswith("```"):
            index += 1
            break
        code_lines.append(lines[index])
        index += 1
    code = html_lib.escape("\n".join(code_lines))
    return f"<pre><code>{code}</code></pre>", index


def is_markdown_block_start(lines: List[str], index: int) -> bool:
    stripped = lines[index].strip()
    return (
        not stripped
        or stripped.startswith("```")
        or bool(MARKDOWN_HEADING_RE.match(stripped))
        or bool(MARKDOWN_UNORDERED_LIST_RE.match(stripped))
        or bool(MARKDOWN_ORDERED_LIST_RE.match(stripped))
        or is_markdown_table_start(lines, index)
    )


def render_markdown_paragraph_at(lines: List[str], index: int) -> Tuple[str, int]:
    paragraph_lines = []
    while index < len(lines) and not is_markdown_block_start(lines, index):
        paragraph_lines.append(lines[index].strip())
        index += 1
    paragraph = "<br>".join(html_lib.escape(line) for line in paragraph_lines)
    return f"<p>{paragraph}</p>", index


def render_markdown_preview_body(text: str) -> str:
    lines = text.splitlines()
    rendered = []
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if not stripped:
            index += 1
            continue
        if stripped.startswith("```"):
            html, index = render_markdown_code_block_at(lines, index)
        elif is_markdown_table_start(lines, index):
            html, index = render_markdown_table_at(lines, index)
        elif MARKDOWN_UNORDERED_LIST_RE.match(stripped):
            html, index = render_markdown_list_at(lines, index, ordered=False)
        elif MARKDOWN_ORDERED_LIST_RE.match(stripped):
            html, index = render_markdown_list_at(lines, index, ordered=True)
        elif heading := MARKDOWN_HEADING_RE.match(stripped):
            level = min(len(heading.group(1)), 4)
            html = f"<h{level}>{html_lib.escape(heading.group(2).strip())}</h{level}>"
            index += 1
        else:
            html, index = render_markdown_paragraph_at(lines, index)
        rendered.append(html)
    return "\n".join(rendered) if rendered else '<p class="empty-state">这个 Markdown 文件暂无内容。</p>'


MARKDOWN_PREVIEW_CSS = """
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: #1e2937;
      background: #f5f7fb;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    main {
      width: min(1120px, calc(100vw - 32px));
      margin: 24px auto 40px;
    }
    header {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: flex-start;
      margin-bottom: 14px;
      padding: 18px 20px;
      border: 1px solid #d9e2ec;
      border-radius: 8px;
      background: #fff;
    }
    h1 {
      margin: 0 0 6px;
      font-size: 22px;
      line-height: 1.35;
    }
    p {
      margin: 0;
      color: #475569;
      line-height: 1.7;
    }
    a {
      flex: 0 0 auto;
      color: #0f766e;
      font-weight: 700;
      text-decoration: none;
    }
    .markdown-body {
      padding: 22px;
      border: 1px solid #d9e2ec;
      border-radius: 8px;
      background: #fff;
    }
    .markdown-body h1, .markdown-body h2, .markdown-body h3, .markdown-body h4 {
      margin: 22px 0 10px;
      color: #0f172a;
      line-height: 1.35;
    }
    .markdown-body h1:first-child, .markdown-body h2:first-child {
      margin-top: 0;
    }
    .markdown-body h1 { font-size: 24px; }
    .markdown-body h2 { font-size: 20px; border-bottom: 1px solid #e2e8f0; padding-bottom: 8px; }
    .markdown-body h3 { font-size: 17px; }
    .markdown-body h4 { font-size: 15px; }
    .markdown-body p, .markdown-body ul, .markdown-body ol, .markdown-body table, .markdown-body pre {
      margin: 0 0 14px;
    }
    .markdown-body ul, .markdown-body ol {
      padding-left: 22px;
      color: #334155;
      line-height: 1.7;
    }
    .markdown-body table {
      width: 100%;
      border-collapse: collapse;
      overflow: hidden;
      font-size: 14px;
    }
    .markdown-body th, .markdown-body td {
      padding: 8px 10px;
      border: 1px solid #d9e2ec;
      text-align: left;
      vertical-align: top;
    }
    .markdown-body th {
      background: #eef6f5;
      color: #0f172a;
      font-weight: 700;
    }
    .markdown-body pre {
      padding: 14px;
      overflow: auto;
      white-space: pre-wrap;
      word-break: break-word;
      border: 1px solid #d9e2ec;
      border-radius: 8px;
      background: #f8fafc;
      color: #334155;
      font: 13px/1.6 ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
    }
"""


def markdown_preview_html(path: Path, source_url: str) -> str:
    text = read_utf8_text(path)
    title = markdown_preview_title(text, path.stem)
    escaped_title = html_lib.escape(title)
    body_html = render_markdown_preview_body(text)
    escaped_source_url = html_lib.escape(source_url, quote=True)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escaped_title}</title>
  <style>{MARKDOWN_PREVIEW_CSS}</style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>{escaped_title}</h1>
        <p>已按 UTF-8 读取原始 Markdown，适合在后台直接核对报告内容。</p>
      </div>
      <a href="{escaped_source_url}" target="_blank" rel="noreferrer">打开原始文件</a>
    </header>
    <article class="markdown-body">
      {body_html}
    </article>
  </main>
</body>
</html>
"""


def public_job(job: Dict[str, Any]) -> Dict[str, Any]:
    result = {
        "ok": True,
        "job_id": job["job_id"],
        "status": job["status"],
        "progress": job.get("progress", ""),
        "error": job.get("error", ""),
        "created_at": job.get("created_at", ""),
        "started_at": job.get("started_at", ""),
        "finished_at": job.get("finished_at", ""),
    }
    for key in ("report_path", "schedule_csv_path", "schedule_html_path", "upload_dir", "backup_path"):
        value = job.get(key)
        result[key] = str(value) if value else ""
        url_key = f"{key}_url" if not key.endswith("_path") else key.replace("_path", "_url")
        result[url_key] = path_url(value) if isinstance(value, Path) else ""
    generated_files = [path for path in job.get("generated_files", []) if isinstance(path, Path)]
    result["generated_files"] = [str(path) for path in generated_files]
    result["generated_file_urls"] = [
        {"name": path.name, "url": path_url(path)}
        for path in generated_files
    ]
    return result


def get_pipeline_job(job_id: str) -> Dict[str, Any]:
    with PIPELINE_JOBS_LOCK:
        job = PIPELINE_JOBS.get(job_id)
        if not job:
            raise ValueError(f"排课任务不存在: {job_id}")
        return public_job(dict(job))


def set_pipeline_job(job_id: str, **updates: Any) -> None:
    with PIPELINE_JOBS_LOCK:
        if job_id in PIPELINE_JOBS:
            PIPELINE_JOBS[job_id].update(updates)


def run_pipeline_job(job_id: str, source_dir: Path, timestamp: str) -> None:
    try:
        import run_scheduling_pipeline

        set_pipeline_job(job_id, status="running", progress="正在导入数据并排课...", started_at=today_text())
        args = SimpleNamespace(
            source=str(source_dir),
            data_dir=str(DATA_DIR),
            output_dir=str(OUTPUT_DIR),
            timestamp=timestamp,
            exclude_weekdays="Sun",
            slot_set="all",
            sunday_policy="summer-only",
        )
        result = run_scheduling_pipeline.run_pipeline(args)
        set_pipeline_job(
            job_id,
            status="succeeded",
            progress="排课完成。",
            finished_at=today_text(),
            report_path=result.report_path,
            schedule_csv_path=result.schedule_csv_path,
            schedule_html_path=result.schedule_html_path,
            backup_path=result.backup_path,
            generated_files=result.generated_files,
        )
    except Exception as exc:
        report_path = OUTPUT_DIR / f"import_report_{timestamp}.md"
        set_pipeline_job(
            job_id,
            status="failed",
            progress="排课失败。",
            error=str(exc),
            finished_at=today_text(),
            report_path=report_path if report_path.exists() else None,
        )


def get_batch_schedule_job(job_id: str) -> Dict[str, Any]:
    with BATCH_SCHEDULE_JOBS_LOCK:
        job = BATCH_SCHEDULE_JOBS.get(job_id)
        if not job:
            raise ValueError(f"课表维护任务不存在: {job_id}")
        return public_job(dict(job))


def set_batch_schedule_job(job_id: str, **updates: Any) -> None:
    with BATCH_SCHEDULE_JOBS_LOCK:
        if job_id in BATCH_SCHEDULE_JOBS:
            BATCH_SCHEDULE_JOBS[job_id].update(updates)


def run_batch_schedule_job(job_id: str, mode: str, suite_codes: List[str], class_ids: List[str], sub_products: List[str]) -> None:
    try:
        set_batch_schedule_job(job_id, status="running", progress="正在更新课表维护结果...", started_at=today_text())
        python_path = BATCH_SCHEDULE_PYTHON if BATCH_SCHEDULE_PYTHON.exists() else Path(sys.executable)
        command = [
            str(python_path),
            str(BATCH_SCHEDULE_SCRIPT),
            "--mode",
            mode,
            "--data-dir",
            str(DATA_DIR),
        ]
        for value in suite_codes:
            command.extend(["--suite-code", value])
        for value in class_ids:
            command.extend(["--class-id", value])
        for value in sub_products:
            command.extend(["--sub-product", value])
        completed = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=3600,
            check=False,
        )
        if completed.returncode != 0:
            detail = "\n".join(part for part in [completed.stdout, completed.stderr] if part).strip()
            raise RuntimeError(detail or f"排课脚本退出码 {completed.returncode}")
        set_batch_schedule_job(
            job_id,
            status="succeeded",
            progress="课表维护结果已更新。",
            finished_at=today_text(),
            report_path=OUTPUT_DIR / "batch_schedule_maintenance_report.md",
            schedule_csv_path=OUTPUT_DIR / "batch_schedule_maintenance.csv",
            schedule_html_path=OUTPUT_DIR / "batch_schedule_maintenance.html",
        )
    except Exception as exc:
        set_batch_schedule_job(
            job_id,
            status="failed",
            progress="课表维护更新失败。",
            error=str(exc),
            finished_at=today_text(),
            report_path=OUTPUT_DIR / "batch_schedule_maintenance_report.md",
        )


def normalize_payload_list(payload: Dict[str, Any], key: str) -> List[str]:
    value = payload.get(key, [])
    if isinstance(value, list):
        raw_items = []
        for item in value:
            raw_items.extend(split_delimited_values(item, include_whitespace=True))
    else:
        raw_items = split_delimited_values(value, include_whitespace=True)
    result: List[str] = []
    seen: Set[str] = set()
    for item in raw_items:
        cleaned = normalize_text(item)
        if cleaned and cleaned not in seen:
            result.append(cleaned)
            seen.add(cleaned)
    return result


def start_batch_schedule_job(payload: Dict[str, Any]) -> Dict[str, Any]:
    mode = normalize_text(payload.get("mode")) or "fast"
    if mode not in {"fast", "full"}:
        raise ValueError("课表维护模式只能是 fast 或 full")
    suite_codes = normalize_payload_list(payload, "suite_codes")
    class_ids = normalize_payload_list(payload, "class_ids")
    sub_products = normalize_payload_list(payload, "sub_products")
    if mode == "fast" and not (suite_codes or class_ids or sub_products):
        raise ValueError("快速更新需要至少填写一个套班编码、班级编码或子产品")
    job_id = uuid.uuid4().hex[:12]
    job = {
        "job_id": job_id,
        "status": "queued",
        "progress": "等待课表维护任务启动。",
        "error": "",
        "created_at": today_text(),
        "report_path": OUTPUT_DIR / "batch_schedule_maintenance_report.md",
        "schedule_csv_path": OUTPUT_DIR / "batch_schedule_maintenance.csv",
        "schedule_html_path": OUTPUT_DIR / "batch_schedule_maintenance.html",
    }
    with BATCH_SCHEDULE_JOBS_LOCK:
        BATCH_SCHEDULE_JOBS[job_id] = job
    thread = threading.Thread(
        target=run_batch_schedule_job,
        args=(job_id, mode, suite_codes, class_ids, sub_products),
        daemon=True,
    )
    thread.start()
    return public_job(job)


def save_uploaded_files(payload: Dict[str, Any], parent: str, timestamp: str) -> Path:
    files = payload.get("files", [])
    if not isinstance(files, list) or not files:
        raise ValueError("请上传至少一个 Excel 或 CSV 文件")

    upload_dir = OUTPUT_DIR / parent / timestamp
    upload_dir.mkdir(parents=True, exist_ok=True)
    used_names: Set[str] = set()

    for index, item in enumerate(files, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"第 {index} 个上传文件格式不正确")
        filename = safe_upload_filename(normalize_text(item.get("name")))
        if filename in used_names:
            raise ValueError(f"上传文件名重复: {filename}")
        content_base64 = normalize_text(item.get("content_base64"))
        if not content_base64:
            raise ValueError(f"上传文件 {filename} 内容为空")
        try:
            content = base64.b64decode(content_base64, validate=True)
        except Exception as exc:
            raise ValueError(f"上传文件 {filename} 不是有效的 base64 内容") from exc
        if not content:
            raise ValueError(f"上传文件 {filename} 内容为空")
        (upload_dir / filename).write_bytes(content)
        used_names.add(filename)
    return upload_dir


def start_uploaded_pipeline(payload: Dict[str, Any]) -> Dict[str, Any]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    job_id = uuid.uuid4().hex[:12]
    upload_dir = save_uploaded_files(payload, "uploads", timestamp)

    job = {
        "job_id": job_id,
        "status": "queued",
        "progress": "文件已上传，等待排课任务启动。",
        "error": "",
        "created_at": today_text(),
        "upload_dir": upload_dir,
    }
    with PIPELINE_JOBS_LOCK:
        PIPELINE_JOBS[job_id] = job

    thread = threading.Thread(target=run_pipeline_job, args=(job_id, upload_dir, timestamp), daemon=True)
    thread.start()
    return public_job(job)


def generate_formal_templates(payload: Dict[str, Any]) -> Dict[str, Any]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    upload_dir = save_uploaded_files(payload, "template_uploads", timestamp)
    import formal_template

    result = formal_template.generate_formal_launch_template(upload_dir, OUTPUT_DIR, timestamp)
    return {
        "ok": True,
        "timestamp": timestamp,
        "upload_dir": str(upload_dir),
        "upload_dir_url": path_url(upload_dir),
        "xlsx_path": str(result.xlsx_path),
        "xlsx_url": path_url(result.xlsx_path),
        "zip_path": str(result.zip_path),
        "zip_url": path_url(result.zip_path),
        "report_path": str(result.report_path),
        "report_url": path_url(result.report_path),
        "row_counts": result.row_counts,
        "warnings": result.warnings,
    }


def run_pipeline_preflight(payload: Dict[str, Any]) -> Dict[str, Any]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    upload_dir = save_uploaded_files(payload, "preflight_uploads", timestamp)
    import run_scheduling_pipeline

    args = SimpleNamespace(
        source=str(upload_dir),
        data_dir=str(DATA_DIR),
        output_dir=str(OUTPUT_DIR),
        timestamp=timestamp,
        exclude_weekdays="Sun",
        slot_set="all",
        sunday_policy="summer-only",
    )
    result = run_scheduling_pipeline.run_preflight(args)
    return {
        "ok": True,
        "passed": result.passed,
        "error": result.error,
        "timestamp": timestamp,
        "upload_dir": str(upload_dir),
        "report_path": str(result.report_path),
        "report_url": path_url(result.report_path),
        "row_counts": result.row_counts,
        "warnings": result.warnings,
        "generated_files": [str(path) for path in result.generated_files],
        "generated_file_urls": [{"name": path.name, "url": path_url(path)} for path in result.generated_files],
        "missing_teacher_requirements": [vars(item) for item in result.missing_teacher_requirements],
        "missing_teacher_rows": result.missing_teacher_rows,
    }


class AdminHandler(BaseHTTPRequestHandler):
    server_version = "SchedulerDataAdmin/1.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/data":
            self.send_json(load_state())
            return
        if parsed.path.startswith("/api/pipeline/jobs/"):
            job_id = parsed.path.rsplit("/", 1)[-1]
            self.send_json(get_pipeline_job(job_id))
            return
        if parsed.path.startswith("/api/batch-schedule/jobs/"):
            job_id = parsed.path.rsplit("/", 1)[-1]
            self.send_json(get_batch_schedule_job(job_id))
            return
        if parsed.path == "/api/results/status":
            self.send_json(current_results_status())
            return
        if parsed.path == "/api/products/download":
            self.send_download(
                products_csv_download_text().encode("utf-8"),
                "products.csv",
                "text/csv; charset=utf-8",
            )
            return
        if parsed.path == "/api/classes/download":
            self.send_download(
                classes_csv_download_text().encode("utf-8"),
                "classes.csv",
                "text/csv; charset=utf-8",
            )
            return
        if parsed.path == "/":
            self.send_file(WEB_DIR / "index.html")
            return
        if parsed.path.startswith("/preview/outputs/"):
            self.send_markdown_preview(parsed.path, "/preview/outputs", OUTPUT_DIR, "/outputs")
            return
        if parsed.path.startswith("/preview/docs/"):
            self.send_markdown_preview(parsed.path, "/preview/docs", DOCS_DIR, "/docs")
            return
        if parsed.path.startswith("/outputs/"):
            self.send_output_file(parsed.path)
            return
        if parsed.path.startswith("/docs/"):
            self.send_project_file(parsed.path, "/docs", DOCS_DIR)
            return
        if parsed.path.startswith("/share/"):
            self.send_project_file(parsed.path, "/share", SHARE_DIR)
            return
        self.send_file(WEB_DIR / unquote(parsed.path.lstrip("/")))

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_POST(self) -> None:
        try:
            payload = self.read_json_body()
            if self.path == "/api/save":
                self.send_json(save_state(payload))
                return
            if self.path == "/api/export-scheduler-input":
                self.send_json(export_scheduler_input(payload))
                return
            if self.path == "/api/products/import":
                self.send_json(import_products_csv(payload))
                return
            if self.path == "/api/classes/import":
                self.send_json(import_classes_csv(payload))
                return
            if self.path == "/api/templates/generate":
                self.send_json(generate_formal_templates(payload))
                return
            if self.path == "/api/pipeline/preflight":
                self.send_json(run_pipeline_preflight(payload))
                return
            if self.path == "/api/pipeline/upload-run":
                self.send_json(start_uploaded_pipeline(payload))
                return
            if self.path == "/api/batch-schedule/run":
                self.send_json(start_batch_schedule_job(payload))
                return
            self.send_error(404, "Not Found")
        except ValueError as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=400)
        except Exception as exc:  # pragma: no cover - server safety net
            self.send_json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, status=500)

    def read_json_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("content-length", "0"))
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def send_json(self, data: Dict[str, Any], status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.write_body(body)

    def send_download(self, body: bytes, filename: str, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", content_disposition_value("attachment", filename))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.write_body(body)

    def send_output_file(self, path_text: str) -> None:
        try:
            path = output_path_from_url(path_text)
        except ValueError:
            self.send_error(404, "Not Found")
            return
        if not path.exists() or not path.is_file():
            self.send_error(404, "Not Found")
            return
        mime_type = mime_type_for(path)
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime_type)
        self.send_header("Content-Disposition", content_disposition_value("inline", path.name))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.write_body(body)

    def send_markdown_preview(self, path_text: str, prefix: str, root_dir: Path, source_prefix: str) -> None:
        try:
            path = project_file_from_url(path_text, prefix, root_dir)
            relative = path.resolve().relative_to(root_dir.resolve()).as_posix()
        except ValueError:
            self.send_error(404, "Not Found")
            return
        if not path.exists() or not path.is_file() or path.suffix.lower() != ".md":
            self.send_error(404, "Not Found")
            return
        body = markdown_preview_html(path, f"{source_prefix}/{relative}").encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Disposition", content_disposition_value("inline", f"{path.stem}.html"))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.write_body(body)

    def send_project_file(self, path_text: str, prefix: str, root_dir: Path) -> None:
        try:
            path = project_file_from_url(path_text, prefix, root_dir)
        except ValueError:
            self.send_error(404, "Not Found")
            return
        if not path.exists() or not path.is_file():
            self.send_error(404, "Not Found")
            return
        mime_type = mime_type_for(path)
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime_type)
        self.send_header("Content-Disposition", content_disposition_value("inline", path.name))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.write_body(body)

    def send_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file() or WEB_DIR not in path.resolve().parents and path.resolve() != WEB_DIR / "index.html":
            self.send_error(404, "Not Found")
            return
        mime_type = mime_type_for(path)
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.write_body(body)

    def write_body(self, body: bytes) -> None:
        if self.command != "HEAD":
            self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}")


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


def main() -> None:
    parser = argparse.ArgumentParser(description="本地排课数据管理网站")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    args = parser.parse_args()

    server = ReusableThreadingHTTPServer((args.host, args.port), AdminHandler)
    print(f"本地数据管理网站已启动: http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
