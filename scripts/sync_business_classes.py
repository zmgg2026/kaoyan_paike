#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import business_class_import as business
import data_admin_server
from run_scheduling_pipeline import backup_data_dir, load_source_tables, overlay_standard_tables_on_state


def selected_business_classes(tables: Mapping[str, Any], base_payload: Mapping[str, Any]) -> tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]], Dict[str, List[Dict[str, Any]]], List[str]]:
    business_rows = list(tables["business_classes"].rows)
    product_map_rows = business.business_product_mapping_rows(tables)
    merge_rows = business.empty_rows(tables, "merge_course_details")
    employee_ids_by_name = business.teacher_employee_ids_from_business_rows(business_rows)
    assignment_rows = business.normalize_assignment_teacher_ids(
        business.empty_rows(tables, "class_teacher_assignments"),
        employee_ids_by_name,
    )

    warnings: List[str] = []
    product_mapping = business.product_map_from_rows(product_map_rows)

    raw_by_class = {
        business.row_value(row, "班级编码"): row
        for row in business_rows
        if business.row_value(row, "班级编码")
    }
    merge_details, merge_warnings = business.merge_details_from_rows(merge_rows, raw_by_class)
    warnings.extend(merge_warnings)
    product_meta = business.product_catalog(base_payload)
    courses_by_product = business.product_courses_by_id(base_payload)

    selected_rows: Dict[str, Mapping[str, Any]] = {}
    selected_product_ids: Dict[str, str] = {}
    generated_aggregate_products: Dict[str, Dict[str, Any]] = {}
    generated_aggregate_courses: Dict[str, List[Dict[str, Any]]] = {}

    skipped_project = 0
    skipped_exam = 0
    skipped_window = 0
    skipped_product_system = 0
    skipped_mapping = 0
    errors: List[str] = []

    for row in business_rows:
        class_id = business.row_value(row, "班级编码")
        if business.row_value(row, "管理项目") != business.BUSINESS_PROJECT:
            skipped_project += 1
            continue
        if business.compact_text(row.get("考试月份")) != business.BUSINESS_EXAM_MONTH:
            skipped_exam += 1
            continue
        try:
            actual_start = business.parse_business_date(row.get("实际开课日期"), f"班级 {class_id}/实际开课日期")
            actual_end = business.parse_business_date(row.get("实际结课日期"), f"班级 {class_id}/实际结课日期")
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if actual_start > business.WINDOW_END or actual_end < business.WINDOW_START:
            skipped_window += 1
            continue

        business_product_id = business.row_value(row, "课程产品编号")
        mapped = business.select_product_mapping_for_class(row, product_mapping)
        canonical_product_id = mapped.get("canonical_product_id", "")
        mapped_product_ids = list(mapped.get("canonical_product_ids", []))
        include, _ = business.include_decision(row, canonical_product_id)
        if not include:
            skipped_product_system += 1
            continue
        if not canonical_product_id:
            skipped_mapping += 1
            continue

        missing_products = [product_id for product_id in mapped_product_ids if product_id not in product_meta]
        if missing_products:
            errors.append(f"产品映射指向不存在的系统产品: 班级 {class_id} / {'|'.join(missing_products)}")
            continue
        missing_courses = [product_id for product_id in mapped_product_ids if not courses_by_product.get(product_id)]
        if missing_courses:
            errors.append(f"系统产品缺少产品课程课时: 班级 {class_id} / {'|'.join(missing_courses)}")
            continue

        effective_id = business.effective_product_id(business_product_id, mapped_product_ids)
        if len(mapped_product_ids) > 1 and effective_id not in product_meta:
            aggregate_name = business.row_value(row, "课程产品名称")
            generated_product = business.aggregate_product_meta(effective_id, aggregate_name, mapped_product_ids, product_meta)
            generated_courses = business.aggregate_product_courses(effective_id, aggregate_name, mapped_product_ids, courses_by_product)
            if not generated_courses:
                errors.append(f"业务产品聚合后缺少产品课程课时: 班级 {class_id} / {effective_id}")
                continue
            product_meta[effective_id] = generated_product
            courses_by_product[effective_id] = generated_courses
            generated_aggregate_products[effective_id] = generated_product
            generated_aggregate_courses[effective_id] = generated_courses

        selected_rows[class_id] = row
        selected_product_ids[class_id] = effective_id

    if errors:
        raise ValueError("\n".join(errors))

    full_sources = {
        detail["source_class_id"]: detail["scheduled_class_id"]
        for details in merge_details.values()
        for detail in details
        if detail["merge_type"] == "full" and detail["source_class_id"] != detail["scheduled_class_id"]
    }
    generated_classes: Dict[str, Dict[str, Any]] = {}
    assignments = business.assignments_by_class(assignment_rows)
    for class_id, row in selected_rows.items():
        if class_id in full_sources:
            continue
        product_id = selected_product_ids[class_id]
        cls = business.build_class_row(row, product_id, product_meta[product_id])
        cls["teacher_assignments"] = list(assignments.get(class_id, {}).values())
        generated_classes[class_id] = cls

    warnings.append(
        f"业务班级同步: 原始 {len(business_rows)} 行，纳入班级管理 {len(generated_classes)} 个，"
        f"跳过非考研 {skipped_project} 行，跳过非 {business.BUSINESS_EXAM_MONTH} 考试月份 {skipped_exam} 行，"
        f"跳过窗口外 {skipped_window} 行，排除计费/未知体系 {skipped_product_system} 行，缺产品映射 {skipped_mapping} 行。"
    )
    return generated_classes, generated_aggregate_products, generated_aggregate_courses, warnings


def sync_business_classes(source: Path, data_dir: Path, output_dir: Path, timestamp: str) -> Dict[str, Any]:
    data_admin_server.DATA_DIR = data_dir
    tables = load_source_tables(source)
    if "business_classes" not in tables:
        raise ValueError("源数据中没有识别到业务班级导出表")

    base_payload = overlay_standard_tables_on_state(tables)
    classes, aggregate_products, aggregate_courses, warnings = selected_business_classes(tables, base_payload)

    selected_rows = [
        row
        for row in tables["business_classes"].rows
        if business.row_value(row, "班级编码") in classes
    ]
    payload = data_admin_server.load_state()
    payload["products"] = business.merge_rows_by_id(
        payload.get("products", []),
        aggregate_products.values(),
        "id",
    )
    payload["product_courses"] = list(payload.get("product_courses", []))
    existing_course_keys = {
        (
            business.normalize_text(row.get("product_id")),
            business.normalize_text(row.get("subject")),
            business.normalize_text(row.get("stage")),
            business.normalize_text(row.get("course_module")),
            business.normalize_text(row.get("course_group")),
        )
        for row in payload["product_courses"]
    }
    for rows in aggregate_courses.values():
        for row in rows:
            key = (
                business.normalize_text(row.get("product_id")),
                business.normalize_text(row.get("subject")),
                business.normalize_text(row.get("stage")),
                business.normalize_text(row.get("course_module")),
                business.normalize_text(row.get("course_group")),
            )
            if key not in existing_course_keys:
                payload["product_courses"].append(row)
                existing_course_keys.add(key)

    payload["teaching_areas"] = business.merge_rows_by_id(
        payload.get("teaching_areas", []),
        business.build_teaching_area_rows(selected_rows),
        "id",
    )
    payload["rooms"] = business.merge_rows_by_id(
        payload.get("rooms", []),
        business.build_room_rows(selected_rows),
        "id",
    )
    employee_ids_by_name = business.teacher_employee_ids_from_business_rows(tables["business_classes"].rows)
    assignment_rows = business.normalize_assignment_teacher_ids(
        business.empty_rows(tables, "class_teacher_assignments"),
        employee_ids_by_name,
    )
    payload["teachers"] = business.merge_rows_by_id(
        payload.get("teachers", []),
        business.build_teacher_rows(selected_rows, assignment_rows, employee_ids_by_name),
        "id",
        "employee_id",
        "teacher_id",
    )
    payload["classes"] = sorted(classes.values(), key=lambda row: row["id"])
    sync_stats = data_admin_server.sync_class_teacher_assignments(payload)
    warnings.append(
        f"已按产品课程同步班级老师安排: {sync_stats['classes']} 个班级，"
        f"{sync_stats['assignments']} 条阶段/课程类别。"
    )

    backup_path = backup_data_dir(data_dir, output_dir, f"class_sync_{timestamp}")
    result = data_admin_server.save_state(payload)
    return {
        "classes": len(payload["classes"]),
        "backup_path": str(backup_path) if backup_path else "",
        "warnings": warnings,
        "updated_at": result.get("updated_at", ""),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="把业务班级导出同步到后台班级管理页面")
    parser.add_argument("--source", required=True, type=Path, help="包含业务班级导出和补充模板的目录或 Excel/CSV")
    parser.add_argument("--data-dir", default=ROOT / "data", type=Path)
    parser.add_argument("--output-dir", default=ROOT / "outputs", type=Path)
    parser.add_argument("--timestamp", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    args = parser.parse_args()

    result = sync_business_classes(
        args.source.resolve(),
        args.data_dir.resolve(),
        args.output_dir.resolve(),
        args.timestamp,
    )
    print(f"班级管理已更新: {result['classes']} 个班级")
    print(f"数据备份: {result['backup_path']}")
    for warning in result["warnings"]:
        print(warning)


if __name__ == "__main__":
    main()
