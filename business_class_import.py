#!/usr/bin/env python3
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

import data_admin_server
from scripts.csv_utils import write_csv_rows
from scripts.field_utils import normalize_int, normalize_text, parse_date_value
from scripts.product_catalog import product_catalog as shared_product_catalog


BUSINESS_PROJECT = "考研/考博"
BUSINESS_EXAM_MONTH = "2026-12"
BUSINESS_EXAM_SEASON = "27考研"
WINDOW_START = date(2026, 7, 1)
WINDOW_END = date(2026, 12, 31)
HISTORICAL_LOCK_END = date(2026, 6, 30)
EMPLOYEE_ID_RE = re.compile(r"^\d{6}$")

PRODUCT_SYSTEM_REGULAR = "常规体系"
PRODUCT_SYSTEM_SPECIAL = "专项体系"
PRODUCT_SYSTEM_BILLING = "计费体系"


@dataclass
class BusinessConversionResult:
    payload: Dict[str, Any]
    warnings: List[str]
    generated_files: List[Path] = field(default_factory=list)


@dataclass
class ScheduledLesson:
    class_id: str
    class_name: str
    lesson_date: date
    start_time: str
    end_time: str
    period: str
    duration_hours: float
    teacher_id: str
    teacher_name: str
    room_id: str
    business_product_id: str
    business_product_name: str
    subject: str
    quarter: str
    stage: str
    course_module: str
    course_group: str
    merge_group: List[str]


class BusinessDataError(ValueError):
    def __init__(self, errors: Sequence[str], warnings: Sequence[str] = ()) -> None:
        self.errors = list(errors)
        self.warnings = list(warnings)
        super().__init__("\n".join(self.errors))


def compact_text(value: Any) -> str:
    return "".join(normalize_text(value).split())


def row_value(row: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = normalize_text(row.get(key))
        if value:
            return value
    return ""


def empty_rows(tables: Mapping[str, Any], table_name: str) -> List[Dict[str, Any]]:
    table = tables.get(table_name)
    return list(table.rows) if table else []


def first_non_empty_rows(tables: Mapping[str, Any], *table_names: str) -> List[Dict[str, Any]]:
    for table_name in table_names:
        rows = empty_rows(tables, table_name)
        if rows:
            return rows
    return []


def business_product_mapping_rows(tables: Mapping[str, Any]) -> List[Dict[str, Any]]:
    return first_non_empty_rows(tables, "business_product_mappings", "business_product_map")


def parse_business_date(value: Any, label: str) -> date:
    return parse_date_value(value, label)


def clamp_date(value: date, lower: date, upper: date) -> date:
    return max(lower, min(upper, value))


def split_codes(value: Any) -> List[str]:
    blank_values = {"", "-", "—", "无", "暂无", "NULL", "N/A"}
    return [
        item.strip()
        for item in re.split(r"[,，;；、|]+", normalize_text(value))
        if item.strip() and item.strip() not in blank_values
    ]


def is_blank_marker(value: Any) -> bool:
    return normalize_text(value) in {"", "-", "—", "无", "暂无", "NULL", "N/A"}


def infer_history_stage(course_text: Any) -> str:
    text = normalize_text(course_text)
    if not text or text == "-" or "自习" in text:
        return ""
    stage_keywords = [
        ("导学3", "导学3"),
        ("导学2", "导学2"),
        ("导学1", "导学1"),
        ("导学", "导学1"),
        ("基础3", "基础3"),
        ("基础2", "基础2"),
        ("基础1", "基础1"),
        ("基础", "基础"),
        ("强化2", "强化2"),
        ("强化1", "强化1"),
        ("强化", "强化"),
        ("冲点", "冲刺"),
        ("冲刺", "冲刺"),
        ("复试", "复试"),
        ("专项2", "专项2"),
        ("专项1", "专项1"),
        ("专项", "专项1"),
        ("一轮", "一轮"),
        ("二轮", "二轮"),
        ("三轮", "三轮"),
        ("四轮", "四轮"),
    ]
    for keyword, stage in stage_keywords:
        if keyword in text:
            return stage
    return ""


def normalize_history_module(course_text: Any, subject: str) -> str:
    text = normalize_text(course_text)
    if not text or text == "-" or "自习" in text:
        return ""
    module_keywords = [
        ("语境词汇", "词汇"),
        ("词汇", "词汇"),
        ("语法", "语法"),
        ("阅读", "阅读"),
        ("写作", "写作"),
        ("翻译", "翻译"),
        ("完形填空", "完形"),
        ("完型", "完形"),
        ("完形", "完形"),
        ("新题型", "新题型"),
        ("高等数学", "高数"),
        ("高数", "高数"),
        ("线性代数", "线代"),
        ("线代", "线代"),
        ("概率论与数理统计", "概率论"),
        ("概率", "概率论"),
        ("马原", "马原"),
        ("史纲", "史纲"),
        ("毛中特", "毛中特"),
        ("习思想", "新思想"),
        ("新思想", "新思想"),
        ("思修法基", "思修"),
        ("思修法治", "思修"),
        ("思修", "思修"),
        ("时政", "时政"),
        ("真题精讲", "真题精讲"),
        ("真题试卷精讲", "真题试卷精讲"),
        ("模拟试卷精讲", "模拟试卷精讲"),
        ("拔高专题", "拔高专题"),
        ("专项突破", "拔高专题"),
        ("管综数学", "数学"),
        ("管综逻辑", "逻辑"),
        ("管综写作", "写作"),
        ("计算机", "计算机"),
        ("生理学", "生理学"),
        ("生物化学", "生物化学"),
        ("病理学", "病理学"),
        ("内科学", "内科学"),
        ("外科学", "外科学"),
        ("复试口语", "复试口语"),
        ("口语", "复试口语"),
        ("模拟面试", "复试模拟面试"),
        ("通识技巧", "复试通识技巧"),
    ]
    for keyword, module in module_keywords:
        if keyword in text:
            return module
    return text.replace("考研", "").replace(subject, "").strip(" -_/")


def infer_history_course_group(subject: str, module: str) -> str:
    if subject == "英语":
        if module in {"语法", "写作", "翻译", "复试口语", "复试模拟面试", "复试通识技巧"}:
            return "写作类"
        return "阅读类"
    if subject == "数学":
        return "数学类"
    if subject == "政治":
        if module in {"马原", "思修", "时政"}:
            return "马原类"
        return "毛史类"
    if subject == "管综":
        return "管综类"
    if subject == "计算机":
        return "计算机类"
    if subject == "西医":
        return "西医A类"
    return ""


def first_merge_code(row: Mapping[str, Any]) -> str:
    codes = split_codes(row.get("合班详情"))
    return codes[0] if codes else ""


def parse_int(value: Any) -> int:
    return normalize_int(value)


def parse_time_minutes(value: Any) -> Optional[int]:
    text = normalize_text(value)
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


def infer_period(value: Any, start_time: str) -> str:
    raw = normalize_text(value).upper()
    aliases = {
        "上午": "AM",
        "早上": "AM",
        "AM": "AM",
        "下午": "PM",
        "PM": "PM",
        "晚上": "EVENING",
        "晚间": "EVENING",
        "EVENING": "EVENING",
        "NIGHT": "EVENING",
    }
    if raw in aliases:
        return aliases[raw]
    if normalize_text(value) in aliases:
        return aliases[normalize_text(value)]
    start_minutes = parse_time_minutes(start_time)
    if start_minutes is None:
        return ""
    if start_minutes < 13 * 60:
        return "AM"
    if start_minutes < 18 * 60 + 30:
        return "PM"
    return "EVENING"


def parse_duration_hours(row: Mapping[str, Any], start_time: str, end_time: str) -> float:
    text = row_value(row, "duration_hours", "课时", "课程时长", "单次课时长", "上课课时", "小时", "小时数", "实际时长")
    if text:
        try:
            return float(text)
        except ValueError:
            pass
    start_minutes = parse_time_minutes(start_time)
    end_minutes = parse_time_minutes(end_time)
    if start_minutes is None or end_minutes is None or end_minutes <= start_minutes:
        return 0
    return round((end_minutes - start_minutes) / 60, 2)


def lesson_key(lesson: ScheduledLesson) -> CourseKey:
    return (lesson.subject, lesson.quarter, lesson.stage, lesson.course_module, lesson.course_group)


def weekday_name(value: date) -> str:
    names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    return names[value.weekday()]


def local_product_entries(value: Any) -> List[Dict[str, str]]:
    ids: List[str] = []
    entries: List[Dict[str, str]] = []
    for item in split_codes(value):
        parts = re.split(r"[:：]", item, maxsplit=1)
        token = parts[0].strip()
        label = parts[1].strip() if len(parts) > 1 else ""
        if token and token not in ids:
            ids.append(token)
            entries.append({"id": token, "label": label})
    return entries


def product_map_from_rows(rows: Iterable[Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    mapping: Dict[str, Dict[str, Any]] = {}
    errors: List[str] = []
    for row in rows:
        business_id = row_value(row, "business_product_id", "erp_course_code", "课程产品编号", "product_id")
        business_name = row_value(row, "business_product_name", "erp_course_name", "课程产品名称", "product_name")
        local_product_text = row_value(row, "local_product_id", "canonical_product_id", "系统产品ID", "标准产品ID", "canonical_id")
        product_system = row_value(row, "product_system", "产品体系")
        product_entries = local_product_entries(local_product_text)
        product_ids = [entry["id"] for entry in product_entries]
        class_name_keywords = split_codes(row_value(row, "class_name_keywords", "class_name_keyword", "班级名称关键词", "班级关键词"))
        if business_id and not product_ids and product_system == PRODUCT_SYSTEM_BILLING:
            continue
        if not business_id and not product_ids:
            continue
        if not business_id or not product_ids:
            errors.append(f"产品映射缺少 business_product_id 或 local_product_id: {dict(row)}")
            continue
        local_product_id = product_ids[0] if len(product_ids) == 1 else "|".join(product_ids)
        rule = {
            "business_product_id": business_id,
            "business_product_name": business_name,
            "local_product_id": local_product_id,
            "local_product_ids": product_ids,
            "local_product_entries": product_entries,
            "class_name_keywords": class_name_keywords,
            "notes": row_value(row, "notes", "备注"),
        }
        existing = mapping.get(business_id)
        if existing and not class_name_keywords and not any(item.get("class_name_keywords") for item in existing.get("rules", [])) and existing["local_product_ids"] != product_ids:
            errors.append(
                f"业务产品 {business_id} 存在多个本地产品映射: "
                f"{existing['local_product_id']} / {local_product_id}"
            )
            continue
        if existing:
            existing.setdefault("rules", []).append(rule)
            if not existing.get("local_product_entries"):
                existing["local_product_entries"] = product_entries
            continue
        mapping[business_id] = {
            "business_product_id": business_id,
            "business_product_name": business_name,
            "local_product_id": local_product_id,
            "local_product_ids": product_ids,
            "local_product_entries": product_entries,
            "rules": [rule],
            "notes": row_value(row, "notes", "备注"),
        }
    if errors:
        raise BusinessDataError(errors)
    return mapping


def select_product_mapping_for_class(row: Mapping[str, Any], product_mapping: Mapping[str, Dict[str, Any]]) -> Dict[str, Any]:
    business_product_id = row_value(row, "课程产品编号")
    mapping = product_mapping.get(business_product_id, {})
    if not mapping:
        return {}

    class_name = row_value(row, "班级名称（外）", "class_name")
    rules = list(mapping.get("rules", []))
    keyword_matches = [
        rule for rule in rules
        if any(keyword and keyword in class_name for keyword in rule.get("class_name_keywords", []))
    ]
    if len(keyword_matches) == 1:
        return keyword_matches[0]
    if len(keyword_matches) > 1:
        keyword_matches.sort(key=lambda rule: max((len(keyword) for keyword in rule.get("class_name_keywords", []) if keyword in class_name), default=0), reverse=True)
        if keyword_matches[0].get("local_product_ids") != keyword_matches[1].get("local_product_ids"):
            return keyword_matches[0]

    entries = list(mapping.get("local_product_entries", []))
    product_keyword_pairs = [
        ("无忧秋", ("无忧秋",)),
        ("无忧春", ("无忧春",)),
        ("无忧寒", ("无忧寒",)),
        ("无忧暑", ("无忧暑",)),
        ("寒暑", ("寒暑",)),
        ("暑假", ("暑假", "暑期")),
        ("暑期", ("暑假", "暑期")),
    ]
    matched = [
        entry for entry in entries
        if any(
            class_keyword in class_name
            and any(label_keyword in entry.get("label", "") for label_keyword in label_keywords)
            for class_keyword, label_keywords in product_keyword_pairs
        )
    ]
    if not matched and "无忧" in class_name:
        season_pairs = [
            ("秋", "无忧秋"),
            ("春", "无忧春"),
            ("寒", "无忧寒"),
            ("暑", "无忧暑"),
        ]
        matched = [
            entry for entry in entries
            if any(season in class_name and label_keyword in entry.get("label", "") for season, label_keyword in season_pairs)
        ]
    if len(matched) == 1:
        entry = matched[0]
        return {
            **mapping,
            "local_product_id": entry["id"],
            "local_product_ids": [entry["id"]],
            "local_product_entries": [entry],
        }
    return mapping


def apply_default_full_merge_details(
    merge_details: Dict[str, List[Dict[str, Any]]],
    selected_rows: Mapping[str, Mapping[str, Any]],
    warnings: List[str],
) -> None:
    for class_id, row in selected_rows.items():
        merge_codes = split_codes(row_value(row, "合班详情"))
        if len(merge_codes) < 2:
            continue
        missing_codes = [code for code in merge_codes if code not in selected_rows]
        if missing_codes:
            warnings.append(
                f"合班详情引用的班级未进入本轮排课范围: {class_id} -> "
                + "、".join(missing_codes[:20])
            )
        if class_id in merge_details:
            continue
        scheduled_id = merge_codes[0]
        if class_id == scheduled_id:
            continue
        merge_details.setdefault(class_id, []).append(
            {
                "source_class_id": class_id,
                "scheduled_class_id": scheduled_id,
                "merge_type": "full",
                "subject": "",
                "stage": "",
                "course_module": "",
                "course_group": "",
                "start_date": "",
                "end_date": "",
                "notes": "根据业务导出合班详情自动生成全量共享课表关系",
            }
        )


def shared_assignments_for_full_merges(
    full_sources: Mapping[str, str],
    selected_rows: Mapping[str, Mapping[str, Any]],
    selected_product_ids: Mapping[str, str],
    courses_by_product: Mapping[str, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    seen: Set[Tuple[str, str, str, str, str]] = set()
    for source_id, scheduled_id in sorted(full_sources.items()):
        product_id = selected_product_ids.get(source_id, "")
        for course in courses_by_product.get(product_id, []):
            subject = normalize_text(course.get("subject"))
            stage = normalize_text(course.get("quarter")) or normalize_text(course.get("stage"))
            course_group = normalize_text(course.get("course_group"))
            key = (source_id, product_id, subject, stage, course_group)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "class_id": source_id,
                    "class_name": row_value(selected_rows.get(source_id, {}), "班级名称（外）"),
                    "product_id": product_id,
                    "product_name": normalize_text(course.get("product_name")) or row_value(selected_rows.get(source_id, {}), "课程产品名称"),
                    "subject": subject,
                    "stage": stage,
                    "course_group": course_group,
                    "class_schedule_mode": "共享实际排课班级",
                    "actual_scheduled_class_id": scheduled_id,
                    "teacher_id": "",
                    "teacher_name": "",
                    "assignment_extra_time_requirement": "",
                    "notes": "根据业务导出合班详情自动生成",
                }
            )
    return rows


def teacher_parts(value: Any) -> List[Tuple[str, str]]:
    result: List[Tuple[str, str]] = []
    for part in split_codes(value):
        match = re.match(r"^(.*)[(（]([^()（）]+)[)）]$", part)
        if match:
            result.append((match.group(2).strip(), match.group(1).strip()))
        else:
            result.append(("", part))
    return result


def is_employee_id(value: Any) -> bool:
    return bool(EMPLOYEE_ID_RE.match(normalize_text(value)))


def teacher_employee_ids_from_business_rows(rows: Iterable[Mapping[str, Any]]) -> Dict[str, str]:
    candidates: Dict[str, Set[str]] = {}
    for row in rows:
        for teacher_id, teacher_name in teacher_parts(row.get("授课教师")):
            if teacher_name and is_employee_id(teacher_id):
                candidates.setdefault(teacher_name, set()).add(teacher_id)
    return {
        teacher_name: next(iter(ids))
        for teacher_name, ids in candidates.items()
        if len(ids) == 1
    }


def normalize_teacher_identity(
    teacher_id: Any,
    teacher_name: Any,
    employee_ids_by_name: Mapping[str, str],
) -> Tuple[str, str]:
    normalized_id = normalize_text(teacher_id)
    normalized_name = normalize_text(teacher_name)
    if is_employee_id(normalized_id):
        return normalized_id, normalized_name or normalized_id
    if normalized_name and employee_ids_by_name.get(normalized_name):
        return employee_ids_by_name[normalized_name], normalized_name
    return normalized_id, normalized_name or normalized_id


def normalize_assignment_teacher_ids(
    rows: Iterable[Mapping[str, Any]],
    employee_ids_by_name: Mapping[str, str],
) -> List[Dict[str, Any]]:
    normalized_rows: List[Dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        teacher_id, teacher_name = normalize_teacher_identity(
            row_value(row, "teacher_id", "employee_id"),
            row_value(row, "teacher_name", "name"),
            employee_ids_by_name,
        )
        row["teacher_id"] = teacher_id
        row["teacher_name"] = teacher_name
        normalized_rows.append(row)
    return normalized_rows


def infer_subject(*values: Any) -> str:
    text = " ".join(normalize_text(value) for value in values)
    for subject in ("管综", "计算机", "西医", "英语", "政治", "数学"):
        if subject in text:
            return subject
    return ""


def subject_category(subject: str) -> str:
    return "公共课" if subject in {"英语", "政治", "数学"} else ("专业课" if subject else "")


def product_catalog(payload: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    return shared_product_catalog(
        list(payload.get("products", [])),
        list(payload.get("product_courses", [])),
    )


def product_courses_by_id(payload: Mapping[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    courses: Dict[str, List[Dict[str, Any]]] = {}
    for raw in payload.get("product_courses", []):
        course = data_admin_server.normalize_product_course(dict(raw))
        if course["product_id"]:
            courses.setdefault(course["product_id"], []).append(course)
    return courses


def effective_product_id(business_product_id: str, product_ids: Sequence[str]) -> str:
    if len(product_ids) == 1:
        return product_ids[0]
    return f"BIZ_{business_product_id}"


def aggregate_product_meta(
    aggregate_id: str,
    business_product_name: str,
    product_ids: Sequence[str],
    product_meta: Mapping[str, Mapping[str, Any]],
) -> Dict[str, Any]:
    first = dict(product_meta.get(product_ids[0], {})) if product_ids else {}
    subjects = {
        normalize_text(product_meta.get(product_id, {}).get("subject"))
        for product_id in product_ids
        if normalize_text(product_meta.get(product_id, {}).get("subject"))
    }
    categories = {
        normalize_text(product_meta.get(product_id, {}).get("subject_category"))
        for product_id in product_ids
        if normalize_text(product_meta.get(product_id, {}).get("subject_category"))
    }
    first["id"] = aggregate_id
    first["name"] = business_product_name or aggregate_id
    first["subject"] = sorted(subjects)[0] if len(subjects) == 1 else ""
    first["subject_category"] = sorted(categories)[0] if len(categories) == 1 else ""
    first["notes"] = f"业务产品映射聚合: {'|'.join(product_ids)}"
    return first


def aggregate_product_courses(
    aggregate_id: str,
    aggregate_name: str,
    product_ids: Sequence[str],
    courses_by_product: Mapping[str, Sequence[Mapping[str, Any]]],
) -> List[Dict[str, Any]]:
    grouped: Dict[Tuple[str, str, str, str, str], Dict[str, Any]] = {}
    for product_id in product_ids:
        for course in courses_by_product.get(product_id, []):
            key = course_key(course)
            item = grouped.setdefault(
                key,
                {
                    "product_id": aggregate_id,
                    "product_name": aggregate_name,
                    "subject_category": normalize_text(course.get("subject_category")),
                    "subject": normalize_text(course.get("subject")),
                    "quarter": normalize_text(course.get("quarter")),
                    "stage": normalize_text(course.get("stage")),
                    "course_module": normalize_text(course.get("course_module")),
                    "course_group": normalize_text(course.get("course_group")),
                    "total_hours": 0,
                    "block_hours": 0,
                    "source_product_ids": [],
                },
            )
            item["total_hours"] += normalize_int(course.get("total_hours"))
            item["block_hours"] = max(item["block_hours"], normalize_int(course.get("block_hours")))
            item["source_product_ids"] = data_admin_server.unique_list([*item["source_product_ids"], product_id])
    rows: List[Dict[str, Any]] = []
    for item in grouped.values():
        rows.append(
            {
                "product_id": item["product_id"],
                "product_name": item["product_name"],
                "subject_category": item["subject_category"],
                "subject": item["subject"],
                "quarter": item["quarter"],
                "stage": item["stage"],
                "course_module": item["course_module"],
                "course_group": item["course_group"],
                "total_hours": item["total_hours"],
                "block_hours": item["block_hours"] or 2,
                "notes": "聚合来源: " + "|".join(item["source_product_ids"]),
            }
        )
    return sorted(rows, key=lambda row: (row["subject"], row["quarter"], row["stage"], row["course_module"], row["course_group"]))


CourseKey = Tuple[str, str, str, str, str]
AssignmentKey = Tuple[str, str, str, str]


def assignment_key(row: Mapping[str, Any]) -> AssignmentKey:
    return (
        normalize_text(row.get("product_id") or row.get("canonical_product_id")),
        normalize_text(row.get("subject")),
        normalize_text(row.get("stage")),
        normalize_text(row.get("course_group")),
    )


def course_key(course: Mapping[str, Any]) -> CourseKey:
    return (
        normalize_text(course.get("subject")),
        normalize_text(course.get("quarter")),
        normalize_text(course.get("stage")),
        normalize_text(course.get("course_module")),
        normalize_text(course.get("course_group")),
    )


def course_assignment_key(course: Mapping[str, Any], product_id: str = "") -> AssignmentKey:
    return (
        normalize_text(product_id or course.get("product_id")),
        normalize_text(course.get("subject")),
        normalize_text(course.get("quarter")) or normalize_text(course.get("stage")),
        normalize_text(course.get("course_group")),
    )


def assignment_label(course: Mapping[str, Any]) -> str:
    key = course_assignment_key(course)
    return "/".join(item for item in key[1:] if item) or "未命名课程类别"


def stage_rank_for_courses(courses: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    ranks: Dict[str, int] = {}
    for index, course in enumerate(courses):
        stage = normalize_text(course.get("stage"))
        if stage and stage not in ranks:
            ranks[stage] = index
    return ranks


def resolve_teacher_assignment(
    course: Mapping[str, Any],
    product_id: str,
    class_assignments: Mapping[AssignmentKey, Dict[str, Any]],
    product_courses: Sequence[Mapping[str, Any]],
) -> Optional[Dict[str, Any]]:
    key = course_assignment_key(course, product_id)
    product_key = key[0]
    subject = key[1]
    stage = key[2]
    course_group = key[3]
    candidates = [
        key,
        ("", subject, stage, course_group),
        (product_key, "", stage, course_group),
        ("", "", stage, course_group),
    ]
    for candidate in candidates:
        assignment = class_assignments.get(candidate)
        if assignment:
            return assignment

    ranks = stage_rank_for_courses(product_courses)
    current_rank = ranks.get(stage, 10_000)
    fallback: List[Tuple[int, Dict[str, Any]]] = []
    for candidate_key, assignment in class_assignments.items():
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
    return None


def assignments_by_class(rows: Iterable[Mapping[str, Any]]) -> Dict[str, Dict[AssignmentKey, Dict[str, Any]]]:
    result: Dict[str, Dict[AssignmentKey, Dict[str, Any]]] = {}
    for raw in rows:
        class_id = row_value(raw, "class_id", "班级编码")
        if not class_id:
            continue
        assignment = data_admin_server.normalize_teacher_assignment(dict(raw))
        if (
            not data_admin_server.is_shared_teacher_assignment(assignment)
            and not assignment.get("teacher_id")
            and not assignment.get("teacher_name")
        ):
            continue
        key = assignment_key(assignment)
        result.setdefault(class_id, {})[key] = assignment
    return result


def class_has_teacher_assignments(
    class_id: str,
    product_id: str,
    courses: Sequence[Mapping[str, Any]],
    assignments: Mapping[str, Dict[AssignmentKey, Dict[str, Any]]],
) -> List[str]:
    class_assignments = assignments.get(class_id, {})
    seen: Set[str] = set()
    missing: List[str] = []
    for course in courses:
        if not resolve_teacher_assignment(course, product_id, class_assignments, courses):
            label = assignment_label(course)
            if label not in seen:
                seen.add(label)
                missing.append(label)
    return missing


def make_requirement(
    course: Mapping[str, Any],
    assignment: Mapping[str, Any],
    detail: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    requirement = {
        "subject_category": normalize_text(course.get("subject_category")),
        "subject": normalize_text(course.get("subject")),
        "quarter": normalize_text(course.get("quarter")),
        "stage": normalize_text(course.get("stage")),
        "course_module": normalize_text(course.get("course_module")),
        "course_group": normalize_text(course.get("course_group")),
        "teacher_id": normalize_text(assignment.get("teacher_id")),
        "teacher_name": normalize_text(assignment.get("teacher_name")),
        "total_hours": normalize_int(course.get("total_hours")),
        "block_hours": normalize_int(course.get("block_hours")),
        "notes": normalize_text(detail.get("notes")) if detail else "",
    }
    if detail:
        if detail.get("start_date"):
            requirement["start_date"] = detail["start_date"]
        if detail.get("end_date"):
            requirement["end_date"] = detail["end_date"]
    return requirement


def normalize_scheduled_lessons(rows: Iterable[Mapping[str, Any]]) -> Tuple[List[ScheduledLesson], List[str]]:
    lessons: List[ScheduledLesson] = []
    warnings: List[str] = []
    for row_number, row in enumerate(rows, start=2):
        class_id = row_value(row, "class_id", "班级编码", "班级ID", "班级id")
        raw_date = row_value(row, "date", "上课日期", "日期", "排课日期", "课程日期")
        if not class_id and not raw_date:
            continue
        if not class_id or not raw_date:
            warnings.append(f"历史课表第 {row_number} 行缺少 class_id 或 date，已跳过。")
            continue
        try:
            lesson_date = parse_business_date(raw_date, f"历史课表第 {row_number} 行")
        except ValueError as exc:
            warnings.append(f"{exc}，已跳过。")
            continue
        start_time = row_value(row, "start_time", "开始时间", "起始时间", "上课开始时间", "上课时间")
        end_time = row_value(row, "end_time", "结束时间", "下课时间", "上课结束时间")
        duration_hours = parse_duration_hours(row, start_time, end_time)
        if duration_hours <= 0:
            warnings.append(f"历史课表第 {row_number} 行课时无法识别，已跳过。")
            continue
        teacher_id = row_value(row, "teacher_id", "teacher_employee_id", "教师ID", "教师编码", "老师编码", "员工编号", "工号")
        teacher_name = row_value(row, "teacher_name", "教师姓名", "教师名称", "老师姓名", "授课教师", "老师")
        if not teacher_id and teacher_name:
            parts = teacher_parts(teacher_name)
            if len(parts) == 1:
                teacher_id = parts[0][0]
                teacher_name = parts[0][1]
        subject = row_value(row, "subject", "科目", "科目内", "学科")
        raw_course_module = row_value(row, "course_module", "课程模块", "模块", "课程名称", "课程内容")
        stage = row_value(row, "stage", "阶段")
        if is_blank_marker(stage):
            stage = infer_history_stage(raw_course_module)
        course_module = normalize_history_module(raw_course_module, subject)
        course_group = row_value(row, "course_group", "课程组", "分组", "学校产品分组名称")
        if is_blank_marker(course_group):
            course_group = infer_history_course_group(subject, course_module)
        lesson = ScheduledLesson(
            class_id=class_id,
            class_name=row_value(row, "class_name", "班级名称", "班级名称（外）"),
            lesson_date=lesson_date,
            start_time=start_time,
            end_time=end_time,
            period=infer_period(row_value(row, "period", "时段", "上课时段"), start_time),
            duration_hours=duration_hours,
            teacher_id=teacher_id,
            teacher_name=teacher_name,
            room_id=row_value(row, "room_id", "教室编码", "上课教室编码"),
            business_product_id=row_value(row, "business_product_id", "课程产品编号", "课程产品编码", "product_id"),
            business_product_name=row_value(row, "business_product_name", "课程产品名称", "课程产品(内)", "product_name"),
            subject=subject,
            quarter=row_value(row, "quarter", "季度", "季度标签"),
            stage=stage,
            course_module=course_module,
            course_group=course_group,
            merge_group=split_codes(row_value(row, "merge_group", "合班班级", "合班详情", "合班编码", "合班班号", "组班班号")),
        )
        lessons.append(lesson)
    return lessons, warnings


def lesson_has_course_key(lesson: ScheduledLesson) -> bool:
    return bool(lesson.subject and lesson.stage and lesson.course_module and lesson.course_group)


def lesson_has_assignment_key(lesson: ScheduledLesson) -> bool:
    return bool(lesson.subject and lesson.stage and lesson.course_group)


def teacher_label(lesson: ScheduledLesson) -> str:
    return lesson.teacher_id or lesson.teacher_name


def learn_teacher_assignments(
    lessons: Sequence[ScheduledLesson],
    uploaded_assignments: Mapping[str, Dict[AssignmentKey, Dict[str, Any]]],
    employee_ids_by_name: Optional[Mapping[str, str]] = None,
) -> Tuple[Dict[str, Dict[AssignmentKey, Dict[str, Any]]], List[Dict[str, Any]], List[str]]:
    employee_ids_by_name = employee_ids_by_name or {}
    learned: Dict[str, Dict[AssignmentKey, Dict[str, Any]]] = {}
    warnings: List[str] = []
    grouped: Dict[Tuple[str, AssignmentKey], List[ScheduledLesson]] = {}
    skipped_missing_course = 0
    for lesson in lessons:
        if not lesson_has_assignment_key(lesson):
            skipped_missing_course += 1
            continue
        if not teacher_label(lesson):
            continue
        grouped.setdefault((lesson.class_id, ("", lesson.subject, lesson.stage, lesson.course_group)), []).append(lesson)

    learned_rows: List[Dict[str, Any]] = []
    for (class_id, key), items in sorted(grouped.items()):
        if key in uploaded_assignments.get(class_id, {}):
            continue
        teacher_options = {
            (lesson.teacher_id, lesson.teacher_name)
            for lesson in items
            if teacher_label(lesson)
        }
        chosen = max(items, key=lambda lesson: (lesson.lesson_date, lesson.start_time))
        if len(teacher_options) > 1:
            labels = [
                f"{teacher_name}({teacher_id})" if teacher_id else teacher_name
                for teacher_id, teacher_name in sorted(teacher_options)
            ]
            warnings.append(
                f"历史课表老师冲突: 班级 {class_id} / {'/'.join(item for item in key[1:] if item)} "
                f"出现 {', '.join(labels)}，已按最近课节选择 {chosen.teacher_name or chosen.teacher_id}。"
            )
        teacher_id, teacher_name = normalize_teacher_identity(
            chosen.teacher_id,
            chosen.teacher_name,
            employee_ids_by_name,
        )
        assignment = {
            "product_id": "",
            "product_name": "",
            "subject": key[1],
            "stage": key[2],
            "course_group": key[3],
            "class_schedule_mode": "本班实际排课",
            "actual_scheduled_class_id": class_id,
            "teacher_id": teacher_id,
            "teacher_name": teacher_name or chosen.teacher_name or chosen.teacher_id,
            "assignment_extra_time_requirement": "",
            "notes": "从历史已排课明细学习",
        }
        learned.setdefault(class_id, {})[key] = assignment
        learned_rows.append({"class_id": class_id, **assignment})
    if skipped_missing_course:
        warnings.append(f"历史课表有 {skipped_missing_course} 行缺少课程字段，未用于老师学习和课时抵扣。")
    return learned, learned_rows, warnings


def combine_assignments(
    uploaded: Mapping[str, Dict[AssignmentKey, Dict[str, Any]]],
    learned: Mapping[str, Dict[AssignmentKey, Dict[str, Any]]],
) -> Dict[str, Dict[AssignmentKey, Dict[str, Any]]]:
    combined: Dict[str, Dict[AssignmentKey, Dict[str, Any]]] = {
        class_id: dict(assignments)
        for class_id, assignments in uploaded.items()
    }
    for class_id, assignments in learned.items():
        bucket = combined.setdefault(class_id, {})
        for key, assignment in assignments.items():
            bucket.setdefault(key, assignment)
    return combined


def historical_hours_by_class(
    lessons: Sequence[ScheduledLesson],
) -> Dict[str, Dict[CourseKey, float]]:
    hours: Dict[str, Dict[CourseKey, float]] = {}
    for lesson in lessons:
        if lesson.lesson_date > HISTORICAL_LOCK_END or not lesson_has_course_key(lesson):
            continue
        key = lesson_key(lesson)
        hours.setdefault(lesson.class_id, {}).setdefault(key, 0.0)
        hours[lesson.class_id][key] += lesson.duration_hours
    return hours


def historical_consumed_hours(class_hours: Mapping[CourseKey, float], requirement: Mapping[str, Any]) -> float:
    key = course_key(requirement)
    exact = class_hours.get(key, 0.0)
    if exact > 0:
        return exact
    if key[1]:
        legacy_key = (key[0], "", key[2], key[3], key[4])
        return class_hours.get(legacy_key, 0.0)
    return 0.0


def merge_rows_by_id(
    base_rows: Iterable[Mapping[str, Any]],
    generated_rows: Iterable[Mapping[str, Any]],
    *keys: str,
) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}
    anonymous: List[Dict[str, Any]] = []
    for row in [*base_rows, *generated_rows]:
        normalized = dict(row)
        row_id = row_value(normalized, *keys)
        if row_id:
            merged[row_id] = normalized
        else:
            anonymous.append(normalized)
    return [*anonymous, *[merged[key] for key in sorted(merged)]]


def include_decision(row: Mapping[str, Any], local_product_id: str = "") -> Tuple[bool, str]:
    product_system = row_value(row, "产品体系")
    if product_system == PRODUCT_SYSTEM_BILLING:
        return False, "计费体系强制排除"

    if product_system == PRODUCT_SYSTEM_REGULAR:
        return True, "常规体系默认纳入"
    if product_system == PRODUCT_SYSTEM_SPECIAL:
        return True, "专项体系按产品映射和班级排课窗口纳入"
    return False, f"未知产品体系 {product_system or '<blank>'}"


def build_class_row(
    row: Mapping[str, Any],
    local_product_id: str,
    product_meta: Mapping[str, Any],
) -> Dict[str, Any]:
    actual_start = parse_business_date(row.get("实际开课日期"), f"班级 {row_value(row, '班级编码')}/实际开课日期")
    actual_end = parse_business_date(row.get("实际结课日期"), f"班级 {row_value(row, '班级编码')}/实际结课日期")
    class_name = row_value(row, "班级名称（外）")
    product_name = row_value(row, "课程产品名称")
    exam_month = compact_text(row.get("考试月份"))
    subject = normalize_text(product_meta.get("subject")) or infer_subject(class_name, product_name)
    return {
        "id": row_value(row, "班级编码"),
        "name": class_name,
        "product_id": local_product_id,
        "project": "考研",
        "product_line": normalize_text(product_meta.get("product_line")),
        "sub_product": normalize_text(product_meta.get("sub_product")),
        "product_system": row_value(row, "产品体系"),
        "course_nature": normalize_text(product_meta.get("course_nature")),
        "subject_category": normalize_text(product_meta.get("subject_category")) or subject_category(subject),
        "subject": subject,
        "selected_stages": "",
        "exam_season": BUSINESS_EXAM_SEASON,
        "exam_month": exam_month,
        "suite_code": data_admin_server.infer_suite_code_from_class_name(class_name),
        "standard_capacity": row_value(row, "标准人数"),
        "capacity_type": row_value(row, "班容类型"),
        "size": row_value(row, "当前人数(占名额)"),
        "start_date": clamp_date(actual_start, WINDOW_START, WINDOW_END).isoformat(),
        "start_period": "AM",
        "first_lesson_date": "",
        "first_lesson_period": "",
        "end_date": clamp_date(actual_end, WINDOW_START, WINDOW_END).isoformat(),
        "end_period": "EVENING",
        "preferred_teaching_area_ids": row_value(row, "校区编码"),
        "preferred_room_ids": row_value(row, "教室编码"),
        "preferred_room_is_required": "",
        "is_manual_schedule_locked": "",
        "notes": (
            f"业务产品: {row_value(row, '课程产品编号')} {product_name}; "
            f"班级状态: {row_value(row, '班级状态')}; "
            f"排课完成状态: {row_value(row, '排课完成状态')}"
        ),
    }


def build_teaching_area_rows(rows: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    areas: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        area_id = row_value(row, "校区编码")
        if not area_id:
            continue
        area_name = row_value(row, "校区名称") or area_id
        areas[area_id] = {
            "id": area_id,
            "name": area_name,
            "short_name": data_admin_server.infer_teaching_area_short_name(area_name, area_id),
            "campus": row_value(row, "校区名称"),
            "building": "",
            "floor": "",
            "scheduling_capacity": 0,
            "capacity_check": "OK",
            "default_time_slots_raw": "",
            "is_active": "是",
            "notes": "来自业务班级导出",
        }
    return list(areas.values())


def build_room_rows(rows: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    rooms: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        room_id = row_value(row, "教室编码")
        if not room_id:
            continue
        capacity = row_value(row, "教室座位数") or row_value(row, "教室最大座位数")
        rooms[room_id] = {
            "id": room_id,
            "name": row_value(row, "上课教室") or room_id,
            "teaching_area_id": row_value(row, "校区编码"),
            "teaching_area_name": data_admin_server.infer_teaching_area_short_name(row_value(row, "校区名称")),
            "capacity": capacity,
            "room_type": row_value(row, "班容类型"),
            "is_active": "是",
            "notes": "来自业务班级导出",
        }
    return list(rooms.values())


def build_teacher_rows(
    business_rows: Iterable[Mapping[str, Any]],
    assignment_rows: Iterable[Mapping[str, Any]],
    employee_ids_by_name: Optional[Mapping[str, str]] = None,
) -> List[Dict[str, Any]]:
    employee_ids_by_name = employee_ids_by_name or {}
    teachers: Dict[str, Dict[str, Any]] = {}
    for row in business_rows:
        for teacher_id, teacher_name in teacher_parts(row.get("授课教师")):
            teacher_id, teacher_name = normalize_teacher_identity(teacher_id, teacher_name, employee_ids_by_name)
            if not teacher_id and not teacher_name:
                continue
            primary_subject = infer_subject(row.get("班级名称（外）"), row.get("课程产品名称"))
            key = teacher_id or teacher_name
            teachers[key] = {
                "employee_id": teacher_id,
                "name": teacher_name or teacher_id,
                "project": "考研",
                "primary_subject": primary_subject,
                "subject_type": data_admin_server.teacher_subject_type(primary_subject),
                "employment_status": "",
                "notes": "来自业务班级导出",
            }
    for row in assignment_rows:
        teacher_id, teacher_name = normalize_teacher_identity(
            row_value(row, "teacher_id", "employee_id"),
            row_value(row, "teacher_name", "name"),
            employee_ids_by_name,
        )
        if not teacher_id:
            continue
        primary_subject = row_value(row, "subject")
        key = teacher_id or teacher_name
        teachers[key] = {
            "employee_id": teacher_id,
            "name": teacher_name or teacher_id,
            "project": "考研",
            "primary_subject": primary_subject,
            "subject_type": data_admin_server.teacher_subject_type(primary_subject),
            "employment_status": "",
            "notes": "来自课程老师安排",
        }
    return list(teachers.values())


def current_teacher_assignments_for_class(
    class_id: str,
    assignments: Mapping[AssignmentKey, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    return [
        data_admin_server.current_teacher_assignment_row(assignment, class_id=class_id)
        for _key, assignment in sorted(assignments.items())
    ]


def apply_historical_remaining_requirements(
    classes: Dict[str, Dict[str, Any]],
    courses_by_product: Mapping[str, List[Dict[str, Any]]],
    assignments: Mapping[str, Dict[AssignmentKey, Dict[str, Any]]],
    lessons: Sequence[ScheduledLesson],
    warnings: List[str],
    errors: List[str],
    skip_class_ids: Optional[Set[str]] = None,
) -> None:
    skip_class_ids = skip_class_ids or set()
    historical_hours = historical_hours_by_class(lessons)
    completed_classes: List[str] = []
    zero_course_rows: List[str] = []
    deduction_rows: List[str] = []

    for class_id in list(classes):
        if class_id in skip_class_ids:
            continue
        cls = classes[class_id]
        class_hours = historical_hours.get(class_id, {})
        if not class_hours:
            continue

        if cls.get("requirements"):
            source_requirements = cls["requirements"]
        else:
            source_requirements = [
                make_requirement(
                    course,
                    resolve_teacher_assignment(
                        course,
                        normalize_text(cls.get("product_id")),
                        assignments.get(class_id, {}),
                        courses_by_product.get(cls["product_id"], []),
                    ) or {},
                )
                for course in courses_by_product.get(cls["product_id"], [])
            ]

        adjusted: List[Dict[str, Any]] = []
        for requirement in source_requirements:
            key = course_key(requirement)
            total_hours = normalize_int(requirement.get("total_hours"))
            consumed = historical_consumed_hours(class_hours, requirement)
            if consumed <= 0:
                adjusted.append(requirement)
                continue
            remaining = max(0, total_hours - int(round(consumed)))
            deduction_rows.append(
                f"{class_id} {'/'.join(item for item in key if item)} 已排 {consumed:g} / 总 {total_hours} / 剩余 {remaining}"
            )
            if remaining <= 0:
                zero_course_rows.append(f"{class_id} {'/'.join(item for item in key if item)}")
                continue
            adjusted_requirement = dict(requirement)
            adjusted_requirement["total_hours"] = remaining
            block_hours = normalize_int(adjusted_requirement.get("block_hours"))
            if block_hours > remaining:
                adjusted_requirement["block_hours"] = remaining
            elif block_hours and remaining % block_hours != 0:
                adjusted_requirement["block_hours"] = remaining
                warnings.append(
                    f"班级 {class_id} / {'/'.join(item for item in key if item)} 抵扣后剩余 {remaining} 小时，"
                    "已把 block_hours 调整为剩余课时。"
                )
            adjusted.append(adjusted_requirement)

        if adjusted:
            cls["requirements"] = adjusted
        else:
            completed_classes.append(class_id)
            classes.pop(class_id)

    if deduction_rows:
        warnings.append(f"{BUSINESS_EXAM_SEASON}已排课时抵扣 {len(deduction_rows)} 项: " + "；".join(deduction_rows[:30]))
    if zero_course_rows:
        warnings.append(f"剩余课时为 0 的班级课程 {len(zero_course_rows)} 项: " + "；".join(zero_course_rows[:30]))
    if completed_classes:
        warnings.append(f"整班无剩余课程，已不进入排课: " + "、".join(completed_classes[:30]))


def lesson_to_row(lesson: ScheduledLesson) -> Dict[str, Any]:
    return {
        "class_id": lesson.class_id,
        "class_name": lesson.class_name,
        "date": lesson.lesson_date.isoformat(),
        "start_time": lesson.start_time,
        "end_time": lesson.end_time,
        "period": lesson.period,
        "duration_hours": lesson.duration_hours,
        "teacher_id": lesson.teacher_id,
        "teacher_name": lesson.teacher_name,
        "room_id": lesson.room_id,
        "business_product_id": lesson.business_product_id,
        "business_product_name": lesson.business_product_name,
        "subject": lesson.subject,
        "quarter": lesson.quarter,
        "stage": lesson.stage,
        "course_module": lesson.course_module,
        "course_group": lesson.course_group,
        "merge_group": "|".join(lesson.merge_group),
    }


def write_rows_csv(path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str]) -> None:
    write_csv_rows(path, fieldnames, rows, encoding="utf-8")


def product_course_hour_rows(lessons: Sequence[ScheduledLesson]) -> List[Dict[str, Any]]:
    grouped: Dict[Tuple[str, str, str, str, str, str, str], Dict[str, Any]] = {}
    for lesson in lessons:
        if not lesson_has_course_key(lesson):
            continue
        key = (
            lesson.business_product_id,
            lesson.business_product_name,
            lesson.subject,
            lesson.quarter,
            lesson.stage,
            lesson.course_module,
            lesson.course_group,
        )
        row = grouped.setdefault(
            key,
            {
                "business_product_id": lesson.business_product_id,
                "business_product_name": lesson.business_product_name,
                "subject": lesson.subject,
                "quarter": lesson.quarter,
                "stage": lesson.stage,
                "course_module": lesson.course_module,
                "course_group": lesson.course_group,
                "scheduled_hours": 0.0,
                "lesson_count": 0,
                "first_date": lesson.lesson_date.isoformat(),
                "last_date": lesson.lesson_date.isoformat(),
            },
        )
        row["scheduled_hours"] = round(float(row["scheduled_hours"]) + lesson.duration_hours, 2)
        row["lesson_count"] += 1
        row["first_date"] = min(str(row["first_date"]), lesson.lesson_date.isoformat())
        row["last_date"] = max(str(row["last_date"]), lesson.lesson_date.isoformat())
    return [grouped[key] for key in sorted(grouped)]


def learned_schedule_rule_rows(lessons: Sequence[ScheduledLesson]) -> List[Dict[str, Any]]:
    grouped: Dict[Tuple[str, str, str, str, str, str, str], Dict[str, Any]] = {}
    periods: Dict[Tuple[str, str, str, str, str, str, str], Set[str]] = {}
    weekdays: Dict[Tuple[str, str, str, str, str, str, str], Set[str]] = {}
    durations: Dict[Tuple[str, str, str, str, str, str, str], Set[str]] = {}
    for lesson in lessons:
        if not lesson_has_course_key(lesson):
            continue
        key = (
            lesson.business_product_id,
            lesson.business_product_name,
            lesson.subject,
            lesson.quarter,
            lesson.stage,
            lesson.course_module,
            lesson.course_group,
        )
        row = grouped.setdefault(
            key,
            {
                "business_product_id": lesson.business_product_id,
                "business_product_name": lesson.business_product_name,
                "subject": lesson.subject,
                "quarter": lesson.quarter,
                "stage": lesson.stage,
                "course_module": lesson.course_module,
                "course_group": lesson.course_group,
                "start_date": lesson.lesson_date.isoformat(),
                "end_date": lesson.lesson_date.isoformat(),
                "lesson_count": 0,
            },
        )
        row["start_date"] = min(str(row["start_date"]), lesson.lesson_date.isoformat())
        row["end_date"] = max(str(row["end_date"]), lesson.lesson_date.isoformat())
        row["lesson_count"] += 1
        if lesson.period:
            periods.setdefault(key, set()).add(lesson.period)
        weekdays.setdefault(key, set()).add(weekday_name(lesson.lesson_date))
        durations.setdefault(key, set()).add(f"{lesson.duration_hours:g}")
    rows: List[Dict[str, Any]] = []
    for key in sorted(grouped):
        row = dict(grouped[key])
        row["allowed_periods"] = "|".join(sorted(periods.get(key, set())))
        row["allowed_weekdays"] = "|".join(sorted(weekdays.get(key, set())))
        row["duration_hours_samples"] = "|".join(sorted(durations.get(key, set())))
        rows.append(row)
    return rows


def merge_candidate_rows(lessons: Sequence[ScheduledLesson]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    explicit_rows: List[Dict[str, Any]] = []
    inferred_groups: Dict[Tuple[str, str, str, str, str, str, str, str, str], List[ScheduledLesson]] = {}
    seen_explicit: Set[Tuple[str, str, str, str, str, str, str, str]] = set()
    for lesson in lessons:
        merge_group = [code for code in lesson.merge_group if code]
        has_explicit_merge = (
            len(set(merge_group)) > 1
            or (len(merge_group) == 1 and merge_group[0] != lesson.class_id)
        )
        if has_explicit_merge:
            scheduled_class_id = merge_group[0]
            for source_class_id in merge_group:
                key = (
                    source_class_id,
                    scheduled_class_id,
                    lesson.subject,
                    lesson.quarter,
                    lesson.stage,
                    lesson.course_module,
                    lesson.course_group,
                    lesson.lesson_date.isoformat(),
                    lesson.lesson_date.isoformat(),
                )
                if key in seen_explicit:
                    continue
                seen_explicit.add(key)
                explicit_rows.append(
                    {
                        "source_class_id": source_class_id,
                        "scheduled_class_id": scheduled_class_id,
                        "merge_type": "partial",
                        "subject": lesson.subject,
                        "quarter": lesson.quarter,
                        "stage": lesson.stage,
                        "course_module": lesson.course_module,
                        "course_group": lesson.course_group,
                        "start_date": lesson.lesson_date.isoformat(),
                        "end_date": lesson.lesson_date.isoformat(),
                        "notes": "从历史课表明确合班字段生成的草稿",
                    }
                )
        if lesson_has_course_key(lesson) and (lesson.teacher_id or lesson.teacher_name) and lesson.room_id:
            group_key = (
                lesson.lesson_date.isoformat(),
                lesson.start_time,
                lesson.end_time,
                lesson.teacher_id or lesson.teacher_name,
                lesson.room_id,
                lesson.subject,
                lesson.quarter,
                lesson.stage,
                lesson.course_module,
                lesson.course_group,
            )
            inferred_groups.setdefault(group_key, []).append(lesson)

    inferred_rows: List[Dict[str, Any]] = []
    for key, items in sorted(inferred_groups.items()):
        class_ids = sorted({lesson.class_id for lesson in items if lesson.class_id})
        if len(class_ids) < 2:
            continue
        first = items[0]
        inferred_rows.append(
            {
                "candidate_type": "inferred_same_time_teacher_room_course",
                "class_ids": "|".join(class_ids),
                "scheduled_class_id_candidate": class_ids[0],
                "date": first.lesson_date.isoformat(),
                "start_time": first.start_time,
                "end_time": first.end_time,
                "teacher_id": first.teacher_id,
                "teacher_name": first.teacher_name,
                "room_id": first.room_id,
                "subject": first.subject,
                "quarter": first.quarter,
                "stage": first.stage,
                "course_module": first.course_module,
                "course_group": first.course_group,
            }
        )
    return explicit_rows, inferred_rows


def write_learning_outputs(
    output_dir: Optional[Path],
    timestamp: Optional[str],
    lessons: Sequence[ScheduledLesson],
    learned_assignments: Sequence[Mapping[str, Any]],
) -> List[Path]:
    if not output_dir or not timestamp or not lessons:
        return []
    output_dir.mkdir(parents=True, exist_ok=True)
    generated: List[Path] = []

    assignments_path = output_dir / f"learned_class_teacher_assignments_{timestamp}.csv"
    write_rows_csv(
        assignments_path,
        learned_assignments,
        data_admin_server.TEACHER_ASSIGNMENT_FIELDNAMES,
    )
    generated.append(assignments_path)

    product_hours_path = output_dir / f"learned_product_course_hours_{timestamp}.csv"
    write_rows_csv(
        product_hours_path,
        product_course_hour_rows(lessons),
        [
            "business_product_id",
            "business_product_name",
            "subject",
            "quarter",
            "stage",
            "course_module",
            "course_group",
            "scheduled_hours",
            "lesson_count",
            "first_date",
            "last_date",
        ],
    )
    generated.append(product_hours_path)

    rules_path = output_dir / f"learned_schedule_rules_{timestamp}.csv"
    write_rows_csv(
        rules_path,
        learned_schedule_rule_rows(lessons),
        [
            "business_product_id",
            "business_product_name",
            "subject",
            "quarter",
            "stage",
            "course_module",
            "course_group",
            "start_date",
            "end_date",
            "allowed_periods",
            "allowed_weekdays",
            "duration_hours_samples",
            "lesson_count",
        ],
    )
    generated.append(rules_path)

    explicit_merge_rows, inferred_merge_rows = merge_candidate_rows(lessons)
    shared_candidates_path = output_dir / f"shared_schedule_candidates_{timestamp}.csv"
    write_rows_csv(
        shared_candidates_path,
        inferred_merge_rows,
        [
            "candidate_type",
            "class_ids",
            "scheduled_class_id_candidate",
            "date",
            "start_time",
            "end_time",
            "teacher_id",
            "teacher_name",
            "room_id",
            "subject",
            "quarter",
            "stage",
            "course_module",
            "course_group",
        ],
    )
    generated.append(shared_candidates_path)

    if explicit_merge_rows:
        shared_rows = [
            {
                "source_class_id": row.get("source_class_id", ""),
                "actual_scheduled_class_id": row.get("scheduled_class_id", ""),
                "class_schedule_mode": "共享实际排课班级",
                "subject": row.get("subject", ""),
                "stage": row.get("stage", ""),
                "course_module": row.get("course_module", ""),
                "course_group": row.get("course_group", ""),
                "start_date": row.get("start_date", ""),
                "end_date": row.get("end_date", ""),
                "notes": row.get("notes", ""),
            }
            for row in explicit_merge_rows
        ]
        explicit_path = output_dir / f"learned_shared_schedule_relations_{timestamp}.csv"
        write_rows_csv(
            explicit_path,
            shared_rows,
            [
                "source_class_id",
                "actual_scheduled_class_id",
                "class_schedule_mode",
                "subject",
                "stage",
                "course_module",
                "course_group",
                "start_date",
                "end_date",
                "notes",
            ],
        )
        generated.append(explicit_path)
    return generated


def convert_business_tables(
    tables: Mapping[str, Any],
    base_payload: Mapping[str, Any],
    output_dir: Optional[Path] = None,
    timestamp: Optional[str] = None,
) -> BusinessConversionResult:
    business_rows = list(tables["business_classes"].rows)
    employee_ids_by_name = teacher_employee_ids_from_business_rows(business_rows)
    product_map_rows = business_product_mapping_rows(tables)
    assignment_rows = normalize_assignment_teacher_ids(
        empty_rows(tables, "class_teacher_assignments"),
        employee_ids_by_name,
    )
    scheduled_lesson_rows = empty_rows(tables, "scheduled_lessons")

    warnings: List[str] = []
    errors: List[str] = []
    product_mapping = product_map_from_rows(product_map_rows)

    merge_details: Dict[str, List[Dict[str, Any]]] = {}
    product_meta = product_catalog(base_payload)
    courses_by_product = product_courses_by_id(base_payload)
    uploaded_assignments = assignments_by_class(assignment_rows)
    scheduled_lessons, lesson_warnings = normalize_scheduled_lessons(scheduled_lesson_rows)
    warnings.extend(lesson_warnings)
    learned_assignments, learned_assignment_rows, learning_warnings = learn_teacher_assignments(
        scheduled_lessons,
        uploaded_assignments,
        employee_ids_by_name,
    )
    warnings.extend(learning_warnings)
    assignments = combine_assignments(uploaded_assignments, learned_assignments)
    generated_files = write_learning_outputs(output_dir, timestamp, scheduled_lessons, learned_assignment_rows)
    if scheduled_lesson_rows:
        warnings.append(
            f"历史课表读取 {len(scheduled_lesson_rows)} 行，成功解析 {len(scheduled_lessons)} 行；"
            f"已生成学习参考文件 {len(generated_files)} 个。"
        )

    selected_rows: Dict[str, Mapping[str, Any]] = {}
    selected_product_ids: Dict[str, str] = {}
    generated_aggregate_products: Dict[str, Dict[str, Any]] = {}
    generated_aggregate_courses: Dict[str, List[Dict[str, Any]]] = {}
    excluded_billing: List[str] = []
    excluded_other: List[str] = []
    skipped_window = 0
    skipped_project = 0
    skipped_exam = 0

    for row in business_rows:
        class_id = row_value(row, "班级编码")
        if row_value(row, "管理项目") != BUSINESS_PROJECT:
            skipped_project += 1
            continue
        if compact_text(row.get("考试月份")) != BUSINESS_EXAM_MONTH:
            skipped_exam += 1
            continue
        try:
            actual_start = parse_business_date(row.get("实际开课日期"), f"班级 {class_id}/实际开课日期")
            actual_end = parse_business_date(row.get("实际结课日期"), f"班级 {class_id}/实际结课日期")
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if actual_start > WINDOW_END or actual_end < WINDOW_START:
            skipped_window += 1
            continue

        business_product_id = row_value(row, "课程产品编号")
        mapped = select_product_mapping_for_class(row, product_mapping)
        local_product_id = mapped.get("local_product_id", "")
        mapped_product_ids = list(mapped.get("local_product_ids", []))
        include, reason = include_decision(row, local_product_id)
        if not include:
            text = f"{class_id} {row_value(row, '班级名称（外）')} ({reason})"
            if row_value(row, "产品体系") == PRODUCT_SYSTEM_BILLING:
                excluded_billing.append(text)
            else:
                excluded_other.append(text)
            continue
        if not local_product_id:
            errors.append(f"未命中产品映射: 班级 {class_id} / 业务产品 {business_product_id} {row_value(row, '课程产品名称')}")
            continue
        missing_products = [product_id for product_id in mapped_product_ids if product_id not in product_meta]
        if missing_products:
            errors.append(f"产品映射指向不存在的本地产品: 班级 {class_id} / {'|'.join(missing_products)}")
            continue
        missing_courses = [product_id for product_id in mapped_product_ids if not courses_by_product.get(product_id)]
        if missing_courses:
            errors.append(f"本地产品缺少产品课程课时: 班级 {class_id} / {'|'.join(missing_courses)}")
            continue
        effective_id = effective_product_id(business_product_id, mapped_product_ids)
        if len(mapped_product_ids) > 1 and effective_id not in product_meta:
            aggregate_name = row_value(row, "课程产品名称")
            generated_product = aggregate_product_meta(effective_id, aggregate_name, mapped_product_ids, product_meta)
            generated_courses = aggregate_product_courses(effective_id, aggregate_name, mapped_product_ids, courses_by_product)
            if not generated_courses:
                errors.append(f"业务产品聚合后缺少产品课程课时: 班级 {class_id} / {effective_id}")
                continue
            product_meta[effective_id] = generated_product
            courses_by_product[effective_id] = generated_courses
            generated_aggregate_products[effective_id] = generated_product
            generated_aggregate_courses[effective_id] = generated_courses
        selected_rows[class_id] = row
        selected_product_ids[class_id] = effective_id

    warnings.append(
        f"业务班级筛选: 原始 {len(business_rows)} 行，跳过非考研 {skipped_project} 行，"
        f"跳过非 {BUSINESS_EXAM_MONTH} 考试月份 {skipped_exam} 行，跳过窗口外 {skipped_window} 行。"
    )
    if excluded_billing:
        warnings.append(f"计费体系已排除 {len(excluded_billing)} 个班级: " + "；".join(excluded_billing[:20]))
    if excluded_other:
        warnings.append(f"其他规则排除 {len(excluded_other)} 个班级: " + "；".join(excluded_other[:20]))

    apply_default_full_merge_details(merge_details, selected_rows, warnings)

    full_sources = {
        detail["source_class_id"]: detail["scheduled_class_id"]
        for details in merge_details.values()
        for detail in details
        if detail["merge_type"] == "full" and detail["source_class_id"] != detail["scheduled_class_id"]
    }
    auto_shared_assignments = assignments_by_class(
        shared_assignments_for_full_merges(
            full_sources,
            selected_rows,
            selected_product_ids,
            courses_by_product,
        )
    )
    assignments = combine_assignments(assignments, auto_shared_assignments)

    generated_classes: Dict[str, Dict[str, Any]] = {}
    for class_id, row in selected_rows.items():
        local_product_id = selected_product_ids[class_id]
        generated_classes[class_id] = build_class_row(row, local_product_id, product_meta[local_product_id])

    for source_id, scheduled_id in full_sources.items():
        if source_id not in selected_rows:
            errors.append(f"全量合班源班级未进入排课范围: {source_id}")
        if scheduled_id not in selected_rows:
            errors.append(f"全量合班实际排课班级未进入排课范围: {scheduled_id}")

    for class_id, cls in generated_classes.items():
        missing = class_has_teacher_assignments(class_id, cls["product_id"], courses_by_product.get(cls["product_id"], []), assignments)
        if missing:
            errors.append(f"班级 {class_id} 缺少课程老师安排: " + "、".join(missing[:20]))

    apply_historical_remaining_requirements(
        generated_classes,
        courses_by_product,
        assignments,
        scheduled_lessons,
        warnings,
        errors,
        set(full_sources),
    )

    for class_id, cls in generated_classes.items():
        cls["teacher_assignments"] = current_teacher_assignments_for_class(
            class_id,
            assignments.get(class_id, {}),
        )

    if errors:
        raise BusinessDataError(errors, warnings)

    generated_business_rows = [selected_rows[class_id] for class_id in selected_rows]
    payload = {key: list(base_payload.get(key, [])) for key in (
        "schedule_windows",
        "time_slots",
        "teaching_areas",
        "rooms",
        "teachers",
        "teacher_unavailability",
        "products",
        "product_courses",
        "product_schedule_rules",
        "class_window_boundaries",
        "class_conflict_groups",
        "locked_scheduled_lessons",
        "teaching_area_links",
        "global_blackout_dates",
        "historical_scheduled_lessons",
        "business_product_mappings",
        "erp_standard_products",
    )}
    payload["products"].extend(generated_aggregate_products.values())
    for courses in generated_aggregate_courses.values():
        payload["product_courses"].extend(courses)
    payload["teaching_areas"] = merge_rows_by_id(
        payload["teaching_areas"],
        build_teaching_area_rows(generated_business_rows),
        "id",
    )
    payload["rooms"] = merge_rows_by_id(payload["rooms"], build_room_rows(generated_business_rows), "id")
    payload["teachers"] = merge_rows_by_id(
        payload["teachers"],
        build_teacher_rows(generated_business_rows, [*assignment_rows, *learned_assignment_rows], employee_ids_by_name),
        "id",
        "employee_id",
        "teacher_id",
    )
    payload["classes"] = list(generated_classes.values())
    payload["class_conflict_groups"] = data_admin_server.build_suite_conflict_groups(payload["classes"])

    warnings.append(f"业务班级纳入排课 {len(generated_classes)} 个。")
    return BusinessConversionResult(payload=payload, warnings=warnings, generated_files=generated_files)
