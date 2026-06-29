from __future__ import annotations

import json
from datetime import date as Date, timedelta
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import scheduler
from scripts.csv_utils import clean_cell, read_csv_rows
from scripts.field_utils import row_value


def _data_file(path: Path, file_name: str) -> Path:
    return path if path.is_file() else path / file_name


def load_room_names(path: Path) -> Dict[str, str]:
    return {
        room_id: clean_cell(room.get("name")) or room_id
        for room_id, room in load_room_metadata(path).items()
    }


def load_room_metadata(path: Path) -> Dict[str, Dict[str, str]]:
    rooms_path = _data_file(path, "rooms.json")
    if rooms_path.suffix.lower() == ".csv":
        return _load_room_metadata_from_csv(rooms_path)
    if not rooms_path.exists():
        return _load_room_metadata_from_csv(_data_file(path, "rooms.csv"))
    doc = json.loads(rooms_path.read_text(encoding="utf-8"))
    result: Dict[str, Dict[str, str]] = {}
    for room in doc.get("rooms", []):
        room_id = clean_cell(room.get("id"))
        if room_id:
            result[room_id] = {key: clean_cell(value) for key, value in room.items()}
    return result


def _load_room_metadata_from_csv(rooms_path: Path) -> Dict[str, Dict[str, str]]:
    if not rooms_path.exists():
        return {}
    lookup: Dict[str, Dict[str, str]] = {}
    for row in read_csv_rows(rooms_path):
        room_id = clean_cell(row.get("id"))
        if room_id:
            lookup[room_id] = {key: clean_cell(value) for key, value in row.items()}
    return lookup


def load_area_metadata(path: Path) -> Dict[str, Dict[str, str]]:
    areas_path = _data_file(path, "teaching_areas.csv")
    if not areas_path.exists():
        return {}
    result: Dict[str, Dict[str, str]] = {}
    for row in read_csv_rows(areas_path):
        area_id = clean_cell(row.get("id"))
        if area_id:
            result[area_id] = {key: clean_cell(value) for key, value in row.items()}
    return result


def load_area_links(path: Path) -> Dict[Tuple[str, str], Dict[str, str]]:
    links_path = _data_file(path, "teaching_area_links.csv")
    if not links_path.exists():
        return {}
    links: Dict[Tuple[str, str], Dict[str, str]] = {}
    for row in read_csv_rows(links_path):
        left = clean_cell(row.get("from_teaching_area_id"))
        right = clean_cell(row.get("to_teaching_area_id"))
        if not left or not right:
            continue
        cleaned = {key: clean_cell(value) for key, value in row.items()}
        links[(left, right)] = cleaned
        links[(right, left)] = cleaned
    return links


def load_class_metadata(path: Path) -> Dict[str, Dict[str, str]]:
    classes_path = _data_file(path, "classes.csv")
    if not classes_path.exists():
        return {}
    result: Dict[str, Dict[str, str]] = {}
    for row in read_csv_rows(classes_path):
        class_id = row.get("id", "")
        if not class_id:
            continue
        subject = infer_class_subject(row)
        lock_value = row_value(row, "is_manual_schedule_locked", "is_schedule_locked")
        result[class_id] = {
            "id": row.get("id", ""),
            "name": row.get("name", ""),
            "product_id": row.get("product_id", ""),
            "project": row.get("project", ""),
            "suite_code": row.get("suite_code", ""),
            "sub_product": row.get("sub_product", ""),
            "product_line": row.get("product_line", ""),
            "product_system": row.get("product_system", ""),
            "course_nature": row.get("course_nature", ""),
            "subject_category": infer_class_subject_category(row, subject),
            "subject": subject,
            "stages": row.get("stages", ""),
            "start_date": row.get("start_date", ""),
            "start_period": row.get("start_period", ""),
            "first_lesson_date": row.get("first_lesson_date", ""),
            "first_lesson_period": row.get("first_lesson_period", ""),
            "end_date": row.get("end_date", ""),
            "end_period": row.get("end_period", ""),
            "preferred_room_ids": row.get("preferred_room_ids", ""),
            "preferred_room_is_required": row.get("preferred_room_is_required", ""),
            "is_manual_schedule_locked": lock_value,
        }
    return result


def load_room_name_to_id(path: Path) -> Dict[str, str]:
    rooms_path = _data_file(path, "rooms.csv")
    if not rooms_path.exists():
        return {}
    lookup: Dict[str, str] = {}
    for row in read_csv_rows(rooms_path):
        room_id = clean_cell(row.get("id"))
        name = clean_cell(row.get("name"))
        if name and room_id:
            lookup.setdefault(name, room_id)
    return lookup


def load_room_maps(path: Path) -> Tuple[Dict[str, str], Dict[str, str]]:
    rooms_path = _data_file(path, "rooms.csv")
    if not rooms_path.exists():
        return {}, {}
    by_id: Dict[str, str] = {}
    by_name_candidates: Dict[str, List[str]] = defaultdict(list)
    for row in read_csv_rows(rooms_path):
        room_id = clean_cell(row.get("id"))
        room_name = clean_cell(row.get("name"))
        if not room_id or not room_name:
            continue
        by_id[room_id] = room_name
        by_name_candidates[room_name].append(room_id)
    by_name = {
        room_name: ids[0]
        for room_name, ids in by_name_candidates.items()
        if len(ids) == 1
    }
    return by_id, by_name


def load_teacher_name_to_id(path: Path, require_six_digit: bool = True) -> Dict[str, str]:
    teachers_path = _data_file(path, "teachers.csv")
    if not teachers_path.exists():
        return {}
    lookup: Dict[str, str] = {}
    for row in read_csv_rows(teachers_path):
        employee_id = clean_cell(row.get("employee_id"))
        name = clean_cell(row.get("name"))
        if not name or not employee_id:
            continue
        if require_six_digit and not (employee_id.isdigit() and len(employee_id) == 6):
            continue
        lookup.setdefault(name, employee_id)
    return lookup


def load_teacher_maps(path: Path) -> Tuple[Dict[str, str], Dict[str, str]]:
    data_dir = path if path.is_dir() else path.parent
    by_id: Dict[str, str] = {}
    by_name: Dict[str, str] = {}
    for file_name in ("teachers.csv", "class_teacher_assignments.csv"):
        source = data_dir / file_name
        if not source.exists():
            continue
        for row in read_csv_rows(source):
            teacher_id = clean_cell(row.get("id") or row.get("employee_id") or row.get("teacher_id"))
            teacher_name = clean_cell(row.get("name") or row.get("teacher_name"))
            if teacher_id and teacher_name:
                by_id.setdefault(teacher_id, teacher_name)
                by_name.setdefault(teacher_name, teacher_id)
    return by_id, by_name


def date_range_values(start: str, end: str = "") -> Set[str]:
    start = clean_cell(start)
    end = clean_cell(end) or start
    if not start:
        return set()
    current = Date.fromisoformat(start)
    last = Date.fromisoformat(end)
    values: Set[str] = set()
    while current <= last:
        values.add(current.isoformat())
        current += timedelta(days=1)
    return values


def blackout_row_is_active(value: object) -> bool:
    text = clean_cell(value).lower()
    return text in {"", "1", "true", "yes", "y", "是", "对"}


def load_active_blackout_dates(path: Path) -> Set[str]:
    data_dir = path if path.is_dir() else path.parent
    source = data_dir / "global_blackout_dates.csv"
    if not source.exists():
        return set()
    dates: Set[str] = set()
    for row in read_csv_rows(source):
        if not blackout_row_is_active(row.get("is_active", True)):
            continue
        start = clean_cell(row.get("start_date"))
        end = clean_cell(row.get("end_date")) or start
        dates.update(date_range_values(start, end))
    return dates


SUBJECT_SUFFIXES = {
    "YY": "英语",
    "ZZ": "政治",
    "SX": "数学",
    "GZ": "管综",
    "JSJ": "计算机",
    "XY": "西医",
}

PUBLIC_SUBJECTS = {"英语", "政治", "数学"}


def infer_class_subject(row: Dict[str, str]) -> str:
    subject = clean_cell(row.get("subject"))
    if subject:
        return subject

    product_id = clean_cell(row.get("product_id")).upper()
    for token in reversed(product_id.split("_")):
        inferred = SUBJECT_SUFFIXES.get(token)
        if inferred:
            return inferred

    text = " ".join(
        clean_cell(row.get(field))
        for field in ("name", "product_name", "notes")
    )
    for keyword in ("计算机", "管综", "西医", "数学", "英语", "政治"):
        if keyword in text:
            return keyword
    return ""


def infer_class_subject_category(row: Dict[str, str], subject: str = "") -> str:
    explicit = clean_cell(row.get("subject_category"))
    if explicit:
        return explicit
    return "公共课" if (subject or infer_class_subject(row)) in PUBLIC_SUBJECTS else ""


def load_product_course_tags(path: Path) -> List[Dict[str, str]]:
    product_courses_path = path / "product_courses.csv"
    if not product_courses_path.exists():
        return []
    tags: List[Dict[str, str]] = []
    for row in read_csv_rows(product_courses_path):
        course_code = clean_cell(row.get("course_code"))
        course_name = clean_cell(row.get("course_name"))
        if not course_code and not course_name:
            continue
        tags.append(
            {
                "product_id": clean_cell(row.get("product_id")),
                "subject": clean_cell(row.get("subject")),
                "quarter": clean_cell(row.get("quarter")),
                "stage": clean_cell(row.get("stage")),
                "course_module": clean_cell(row.get("course_module")),
                "course_group": clean_cell(row.get("course_group")),
                "course_code": course_code,
                "course_name": course_name,
            }
        )
    return tags


def assignment_course_tag(
    assignment: scheduler.Assignment,
    class_metadata: Optional[Dict[str, Dict[str, str]]] = None,
    product_course_tags: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, str]:
    task = assignment.task
    course_code = clean_cell(getattr(task, "course_code", ""))
    course_name = clean_cell(getattr(task, "course_name", ""))
    if course_code or course_name:
        return {"course_code": course_code, "course_name": course_name}

    class_metadata = class_metadata or {}
    product_course_tags = product_course_tags or []
    class_meta = class_metadata.get(task.class_id, {})
    product_id = clean_cell(task.product_id) or clean_cell(class_meta.get("product_id"))
    if not product_id:
        return {"course_code": "", "course_name": ""}

    expected = {
        "product_id": product_id,
        "subject": clean_cell(task.subject),
        "quarter": clean_cell(task.quarter),
        "stage": clean_cell(task.stage),
        "course_module": clean_cell(task.course_module),
        "course_group": clean_cell(task.course_group),
    }
    seasonal_phases = {"寒假", "春季", "暑假", "秋季"}
    expected_variants = [expected]
    if not expected["quarter"] and expected["stage"] in seasonal_phases:
        variant = dict(expected)
        variant["quarter"] = expected["stage"]
        variant["stage"] = ""
        expected_variants.append(variant)
    search_orders = (
        ("product_id", "subject", "quarter", "stage", "course_module", "course_group"),
        ("product_id", "subject", "quarter", "stage", "course_module"),
        ("product_id", "subject", "quarter", "stage", "course_group"),
        ("product_id", "subject", "quarter", "course_module", "course_group"),
        ("product_id", "subject", "quarter", "course_module"),
        ("product_id", "subject", "quarter", "course_group"),
        ("product_id", "subject", "stage", "course_module", "course_group"),
        ("product_id", "subject", "stage", "course_module"),
        ("product_id", "subject", "stage", "course_group"),
    )

    def find_unique_tag(expected_item: Dict[str, str]) -> Dict[str, str]:
        for keys in search_orders:
            matches = [
                tag
                for tag in product_course_tags
                if all(clean_cell(tag.get(key)) == expected_item[key] for key in keys)
            ]
            unique_tags = {
                (tag.get("course_code", ""), tag.get("course_name", ""))
                for tag in matches
                if tag.get("course_code") or tag.get("course_name")
            }
            if len(unique_tags) == 1:
                course_code, course_name = next(iter(unique_tags))
                return {"course_code": course_code, "course_name": course_name}
        return {"course_code": "", "course_name": ""}

    for expected_item in expected_variants:
        tag = find_unique_tag(expected_item)
        if tag["course_code"] or tag["course_name"]:
            return tag

    if "+" in expected["course_module"]:
        split_tags = []
        for module in [part.strip() for part in expected["course_module"].split("+") if part.strip()]:
            module_variants = []
            for expected_item in expected_variants:
                variant = dict(expected_item)
                variant["course_module"] = module
                module_variants.append(variant)
            tag = {"course_code": "", "course_name": ""}
            for expected_item in module_variants:
                tag = find_unique_tag(expected_item)
                if tag["course_code"] or tag["course_name"]:
                    break
            if not (tag["course_code"] or tag["course_name"]):
                split_tags = []
                break
            split_tags.append(tag)
        if split_tags:
            return {
                "course_code": "|".join(tag["course_code"] for tag in split_tags if tag["course_code"]),
                "course_name": "|".join(tag["course_name"] for tag in split_tags if tag["course_name"]),
            }
    return {"course_code": "", "course_name": ""}
