#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import business_class_import as business
import data_admin_server
from run_scheduling_pipeline import backup_data_dir, load_source_tables


def employee_map_from_source(source: Path) -> Dict[str, str]:
    tables = load_source_tables(source)
    if "business_classes" not in tables:
        raise ValueError("源数据中没有识别到业务班级导出表，无法建立教师姓名到 6 位员工号的映射")
    return business.teacher_employee_ids_from_business_rows(tables["business_classes"].rows)


def fix_teacher_id(teacher_id: Any, teacher_name: Any, employee_ids_by_name: Mapping[str, str]) -> str:
    current_id = data_admin_server.normalize_text(teacher_id)
    name = data_admin_server.normalize_text(teacher_name)
    if data_admin_server.is_employee_id(current_id):
        return current_id
    return employee_ids_by_name.get(name, "")


def merge_teacher_row(target: Dict[str, Dict[str, Any]], row: Dict[str, Any]) -> None:
    teacher_id = row["id"]
    existing = target.get(teacher_id)
    if not existing:
        target[teacher_id] = row
        return
    for key, value in row.items():
        if key in {"id", "employee_id"}:
            continue
        if not existing.get(key) and value:
            existing[key] = value


def fix_state(state: Dict[str, Any], employee_ids_by_name: Mapping[str, str]) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    report_rows: List[Dict[str, Any]] = []
    teachers_by_id: Dict[str, Dict[str, Any]] = {}

    for teacher in state.get("teachers", []):
        old_id = data_admin_server.normalize_text(teacher.get("id") or teacher.get("employee_id"))
        teacher_name = data_admin_server.normalize_text(teacher.get("name"))
        new_id = fix_teacher_id(old_id, teacher_name, employee_ids_by_name)
        if not new_id:
            report_rows.append(
                {
                    "table": "teachers",
                    "class_id": "",
                    "teacher_name": teacher_name,
                    "old_id": old_id,
                    "new_id": "",
                    "action": "removed_invalid_without_employee_id",
                }
            )
            continue
        fixed = dict(teacher)
        fixed["id"] = new_id
        fixed["employee_id"] = new_id
        merge_teacher_row(teachers_by_id, fixed)
        if old_id != new_id:
            report_rows.append(
                {
                    "table": "teachers",
                    "class_id": "",
                    "teacher_name": teacher_name,
                    "old_id": old_id,
                    "new_id": new_id,
                    "action": "replaced_with_employee_id",
                }
            )

    for cls in state.get("classes", []):
        for assignment in cls.get("teacher_assignments", []):
            old_id = data_admin_server.normalize_text(assignment.get("teacher_id"))
            teacher_name = data_admin_server.normalize_text(assignment.get("teacher_name"))
            new_id = fix_teacher_id(old_id, teacher_name, employee_ids_by_name)
            if old_id == new_id:
                continue
            assignment["teacher_id"] = new_id
            report_rows.append(
                {
                    "table": "class_teacher_assignments",
                    "class_id": cls.get("id", ""),
                    "teacher_name": teacher_name,
                    "old_id": old_id,
                    "new_id": new_id,
                    "action": "replaced_with_employee_id" if new_id else "cleared_invalid_without_employee_id",
                }
            )
            if new_id and new_id not in teachers_by_id:
                teachers_by_id[new_id] = {
                    "id": new_id,
                    "employee_id": new_id,
                    "name": teacher_name,
                    "project": "考研",
                    "primary_subject": assignment.get("subject", ""),
                    "subject_type": data_admin_server.teacher_subject_type(assignment.get("subject", "")),
                    "employment_status": "",
                    "notes": "来自班级老师安排",
                }

    state["teachers"] = sorted(teachers_by_id.values(), key=lambda row: row["id"])
    return state, report_rows


def write_report(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["table", "class_id", "teacher_name", "old_id", "new_id", "action"])
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="把教师 ID 修正为业务系统 6 位员工号")
    parser.add_argument("--source", required=True, type=Path, help="业务班级导出 CSV/Excel，或包含该表的目录")
    parser.add_argument("--data-dir", default=ROOT / "data", type=Path)
    parser.add_argument("--output-dir", default=ROOT / "outputs", type=Path)
    parser.add_argument("--timestamp", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    args = parser.parse_args()

    data_admin_server.DATA_DIR = args.data_dir.resolve()
    employee_ids_by_name = employee_map_from_source(args.source.resolve())
    state = data_admin_server.load_state()
    fixed_state, report_rows = fix_state(state, employee_ids_by_name)
    backup_path = backup_data_dir(args.data_dir.resolve(), args.output_dir.resolve(), f"teacher_ids_{args.timestamp}")
    data_admin_server.save_state(fixed_state)
    report_path = args.output_dir.resolve() / f"teacher_id_fix_report_{args.timestamp}.csv"
    write_report(report_path, report_rows)

    print(f"教师姓名映射: {len(employee_ids_by_name)} 个")
    print(f"修正记录: {len(report_rows)} 条")
    print(f"数据备份: {backup_path}")
    print(f"修正报告: {report_path}")


if __name__ == "__main__":
    main()
