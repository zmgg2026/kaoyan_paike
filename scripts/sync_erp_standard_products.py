#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import data_admin_server
from scripts.csv_utils import read_csv_rows, write_csv_rows
from scripts.table_schema import BUSINESS_PRODUCT_MAPPING_FIELDNAMES, ERP_STANDARD_PRODUCT_FIELDNAMES


DATA_DIR = ROOT / "data"

ERP_COLUMN_MAP = {
    "erp_product_key": None,
    "course_code": "课程编码",
    "course_product_name_inner": "课程产品名称（内）",
    "course_product_name_outer": "课程产品名称（外）",
    "service_school_name": "*服务学校名称",
    "management_project": "管理项目",
    "department": "所属部门",
    "product_system": "产品体系",
    "product_category": "产品品类",
    "course_category": "课程分类",
    "course_attribute": "课程属性",
    "project_name": "所属项目",
    "school": "学校",
    "subject": "科目_集团",
    "product_brand": "产品品牌_集团",
    "learning_stage": "学习阶段_集团",
    "target_people": "针对人群_集团",
    "group_class_type": "班容类型_集团",
    "school_version_code": "版本编码_学校分组",
    "school_version_name": "版本_学校分组",
    "school_class_type": "班容类型_学校分组",
    "standard_student_count": "标准人数_学校分组",
    "opening_student_count": "开班人数_学校分组",
    "guaranteed_student_count": "保底人数_学校分组",
    "attendance_method": "考勤方式_学校分组",
    "class_price": "班级标价_学校分组",
    "material_fee": "教材费_学校分组",
    "duration_minutes": "班级时长_分钟__学校分组",
    "lesson_count": "班级课次数_学校分组",
    "hourly_price": "小时标价_学校分组",
    "single_lesson_minutes": "单次课时长_学校分组",
    "class_form": "上课形式_学校分组",
    "teaching_method": "授课方式_学校分组",
    "teaching_channel": "授课渠道_学校分组",
    "is_enabled": "是否启用",
    "is_deleted": "是否标记删除",
    "is_teaching_method_valid": "是否授课方式有效",
    "operator": "操作人",
    "operated_at": "操作时间",
    "reviewer": "审核人",
    "reviewed_at": "审核时间",
}

CLASS_PRODUCT_PATTERN = re.compile(r"业务产品:\s*([^ ;]+)\s+([^;]+)")


def text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if value != value:
            return ""
    except TypeError:
        pass
    return str(value).strip()


def read_csv(path: Path) -> List[Dict[str, str]]:
    return read_csv_rows(path)


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    write_csv_rows(path, fieldnames, rows, encoding="utf-8", value_formatter=serialize)


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def serialize(value: Any) -> str:
    if isinstance(value, list):
        return "|".join(text(item) for item in value if text(item))
    return text(value)


def product_key(course_code: str, version_code: str) -> str:
    return f"{course_code}__{version_code}" if version_code else course_code


def import_erp_products(source: Path) -> List[Dict[str, str]]:
    try:
        import pandas as pd
    except ModuleNotFoundError as exc:
        raise RuntimeError("同步 ERP 标准产品需要 pandas，请先安装 requirements.txt") from exc

    df = pd.read_excel(source, sheet_name="学校导出数据", dtype=str).fillna("")
    rows: List[Dict[str, str]] = []
    for _, record in df.iterrows():
        row: Dict[str, str] = {}
        for target, source_column in ERP_COLUMN_MAP.items():
            row[target] = text(record.get(source_column, "")) if source_column else ""
        row["erp_product_key"] = product_key(row["course_code"], row["school_version_code"])
        row["source_file"] = str(source)
        notes: List[str] = []
        if row["is_enabled"] != "是":
            notes.append("ERP未启用")
        if row["is_deleted"] == "是":
            notes.append("ERP标记删除")
        if row["is_teaching_method_valid"] not in {"", "是"}:
            notes.append("授课方式无效")
        row["notes"] = "；".join(notes)
        rows.append(row)
    return rows


def erp_by_code(erp_rows: Iterable[Dict[str, str]]) -> Dict[str, List[Dict[str, str]]]:
    grouped: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for row in erp_rows:
        grouped[row["course_code"]].append(row)
    return grouped


def class_erp_codes_by_product() -> Dict[str, Tuple[str, str, int]]:
    counts: Dict[str, Counter[Tuple[str, str]]] = defaultdict(Counter)
    for cls in read_csv(DATA_DIR / "classes.csv"):
        match = CLASS_PRODUCT_PATTERN.search(cls.get("notes", ""))
        if not match:
            continue
        counts[cls.get("product_id", "")][(match.group(1), match.group(2))] += 1
    result: Dict[str, Tuple[str, str, int]] = {}
    for product_id, counter in counts.items():
        (course_code, course_name), count = counter.most_common(1)[0]
        result[product_id] = (course_code, course_name, count)
    return result


def normalize_subject(subject: str) -> str:
    if subject == "计算机":
        return "计算机"
    if subject in {"数学", "数学一"}:
        return "数学"
    if subject in {"管综", "管理类联考"}:
        return "管综"
    return subject


def inferred_course_code(product: Dict[str, str]) -> Tuple[str, str, str]:
    subject = normalize_subject(product.get("subject", ""))
    sub_product = product.get("sub_product", "")
    product_line = product.get("product_line", "")
    course_nature = product.get("course_nature", "")

    if course_nature == "复试" and subject == "英语":
        return "553894", "考研英语复试班", "本地复试英语产品推断"

    if course_nature == "导学":
        if "无忧" in product_line or sub_product.startswith("无忧"):
            if subject == "英语":
                return "553739", "考研英语无忧计划导学班", "本地无忧导学产品推断"
            if subject == "数学":
                return "553740", "考研数学无忧计划导学班", "本地无忧导学产品推断"
        if "集训营" in product_line or sub_product in {"半年营", "全年营", "寒暑营", "暑假营"}:
            if subject == "英语":
                return "553788", "考研英语导学营", "本地集训营导学产品推断"
            if subject == "数学":
                return "553787", "考研数学导学营", "本地集训营导学产品推断"
            if subject in {"管综", "计算机"}:
                return "553875", "考研专业课体验班", "专业课导学按ERP体验班候选推断"

    if course_nature == "专项" and subject == "数学":
        return "553750", "考研数学春季集训营讲练课", "本地专项数学产品推断"

    if course_nature == "正课" and subject == "计算机" and sub_product.startswith("无忧"):
        return "561186", "考研专业课计算机无忧计划全年班", "专业课计算机无忧正课推断"

    return "", "", ""


def version_score(product: Dict[str, str], erp_row: Dict[str, str], source: str) -> int:
    version = erp_row.get("school_version_name", "")
    sub_product = product.get("sub_product", "")
    score = 0
    if erp_row.get("is_enabled") == "是":
        score += 20
    if erp_row.get("is_deleted") != "是":
        score += 20
    if erp_row.get("is_teaching_method_valid") in {"", "是"}:
        score += 10
    if "27" in version:
        score += 8
    if "26" in version:
        score += 6
    if sub_product == "暑假营" and "暑" in version and "寒暑" not in version:
        score += 40
    if sub_product == "寒暑营" and "寒暑" in version:
        score += 40
    if sub_product == "冲刺营" and "冲刺" in version:
        score += 35
    if sub_product in {"半年营", "全年营"} and "考研" in version and "寒暑" not in version and "暑假" not in version:
        score += 20
    if product.get("course_nature") == "导学" and ("24H" in version or "导学" in version):
        score += 20
    if source.startswith("专业课导学") and product.get("subject") in version:
        score += 30
    try:
        local_capacity = int(float(product.get("standard_capacity", "") or 0))
        erp_capacity = int(float(erp_row.get("standard_student_count", "") or 0))
        if local_capacity and erp_capacity and local_capacity == erp_capacity:
            score += 5
    except ValueError:
        pass
    return score


def pick_erp_row(product: Dict[str, str], code: str, grouped: Dict[str, List[Dict[str, str]]], source: str) -> Optional[Dict[str, str]]:
    candidates = grouped.get(code, [])
    if not candidates:
        return None
    return max(candidates, key=lambda row: version_score(product, row, source))


def keyword_for_product(product: Dict[str, str]) -> List[str]:
    sub_product = product.get("sub_product", "")
    subject = product.get("subject", "")
    if sub_product.startswith("无忧"):
        return [sub_product[-1]]
    if sub_product == "寒暑营":
        return ["寒暑"]
    if sub_product == "暑假营":
        return ["暑假", "暑期"]
    if sub_product in {"半年营", "全年营", "冲刺营"}:
        return [sub_product.replace("营", "")]
    if subject:
        return [subject]
    return []


def mapping_row(
    product: Dict[str, str],
    erp_row: Optional[Dict[str, str]],
    source: str,
    class_count: int = 0,
) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "local_product_id": product.get("id", ""),
        "local_product_name": product.get("name", ""),
        "local_product_line": product.get("product_line", ""),
        "local_sub_product": product.get("sub_product", ""),
        "local_product_system": product.get("product_system", ""),
        "local_course_nature": product.get("course_nature", ""),
        "local_subject": product.get("subject", ""),
        "match_source": source or "",
        "class_name_keywords": keyword_for_product(product),
    }
    if erp_row:
        row.update(
            {
                "erp_product_key": erp_row.get("erp_product_key", ""),
                "erp_course_code": erp_row.get("course_code", ""),
                "erp_course_name": erp_row.get("course_product_name_inner", ""),
                "erp_version_code": erp_row.get("school_version_code", ""),
                "erp_version_name": erp_row.get("school_version_name", ""),
                "erp_product_system": erp_row.get("product_system", ""),
                "erp_product_category": erp_row.get("product_category", ""),
                "erp_project_name": erp_row.get("project_name", ""),
                "erp_subject": erp_row.get("subject", ""),
                "erp_class_type": erp_row.get("school_class_type", ""),
                "erp_duration_minutes": erp_row.get("duration_minutes", ""),
                "erp_lesson_count": erp_row.get("lesson_count", ""),
                "erp_single_lesson_minutes": erp_row.get("single_lesson_minutes", ""),
                "erp_class_form": erp_row.get("class_form", ""),
                "erp_teaching_method": erp_row.get("teaching_method", ""),
                "business_product_id": erp_row.get("course_code", ""),
                "business_product_name": erp_row.get("course_product_name_inner", ""),
            }
        )
        if source == "班级ERP业务产品编码":
            row["match_status"] = "已匹配"
            row["match_confidence"] = "高"
        else:
            row["match_status"] = "待确认"
            row["match_confidence"] = "中" if "推断" in source and "专业课导学" not in source else "低"
    else:
        row.update(
            {
                "erp_product_key": "",
                "erp_course_code": "",
                "erp_course_name": "",
                "erp_version_code": "",
                "erp_version_name": "",
                "erp_product_system": "",
                "erp_product_category": "",
                "erp_project_name": "",
                "erp_subject": "",
                "erp_class_type": "",
                "erp_duration_minutes": "",
                "erp_lesson_count": "",
                "erp_single_lesson_minutes": "",
                "erp_class_form": "",
                "erp_teaching_method": "",
                "business_product_id": "",
                "business_product_name": "",
                "match_status": "未匹配",
                "match_confidence": "",
            }
        )
    notes = ["ERP标准产品源=命令行参数 --erp-source"]
    if class_count:
        notes.append(f"本轮班级ERP业务产品编码命中 {class_count} 个班级")
    if source and source != "班级ERP业务产品编码":
        notes.append(source)
    if row["match_status"] != "已匹配":
        notes.append("请人工核对后确认")
    row["notes"] = "；".join(notes)
    return row


def build_mappings(erp_rows: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    grouped = erp_by_code(erp_rows)
    class_codes = class_erp_codes_by_product()
    mappings: List[Dict[str, Any]] = []
    for product in read_csv(DATA_DIR / "products.csv"):
        source = ""
        class_count = 0
        course_code = ""
        if product.get("id") in class_codes:
            course_code, _, class_count = class_codes[product["id"]]
            source = "班级ERP业务产品编码"
        else:
            course_code, _, source = inferred_course_code(product)
        erp_row = pick_erp_row(product, course_code, grouped, source) if course_code else None
        mappings.append(mapping_row(product, erp_row, source, class_count))
    return mappings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="同步 ERP 标准产品清单，并生成本地产品对应关系。")
    parser.add_argument("--erp-source", type=Path, required=True, help="ERP 系统标准产品 Excel 导出文件")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    erp_rows = import_erp_products(args.erp_source)
    mappings = build_mappings(erp_rows)
    updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    write_json(
        DATA_DIR / "erp_standard_products.json",
        {
            "updated_at": updated_at,
            "source": str(args.erp_source),
            "record_count": len(erp_rows),
            "erp_standard_products": erp_rows,
        },
    )
    write_csv(DATA_DIR / "erp_standard_products.csv", erp_rows, ERP_STANDARD_PRODUCT_FIELDNAMES)

    write_json(
        DATA_DIR / "business_product_mappings.json",
        {
            "updated_at": updated_at,
            "source": "scripts/sync_erp_standard_products.py",
            "record_count": len(mappings),
            "business_product_mappings": mappings,
        },
    )
    write_csv(DATA_DIR / "business_product_mappings.csv", mappings, BUSINESS_PRODUCT_MAPPING_FIELDNAMES)

    status_counts = Counter(row["match_status"] for row in mappings)
    print(
        json.dumps(
            {
                "erp_standard_products": len(erp_rows),
                "local_product_mappings": len(mappings),
                "match_status_counts": status_counts,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
