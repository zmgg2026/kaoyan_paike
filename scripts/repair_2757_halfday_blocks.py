#!/usr/bin/env python3
"""Expand under-filled 2757 summer half-day lessons to standard 4-hour blocks."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.build_camp_maintenance_schedule as maintenance
from scripts.schedule_data import load_room_names
from scripts.schedule_outputs import write_day_table_html


DEFAULT_SCHEDULE = Path("outputs/batch_schedule_maintenance.csv")
DEFAULT_OUTPUT_DIR = Path("outputs")
TARGET_SUITE = "2757"
TARGET_QUARTER = "暑假"
PUBLIC_SUBJECTS = {"英语", "政治", "数学", "语文"}
SECOND_SLOT = {
    "AM1": ("AM2", "上午二", "10:20", "12:20"),
    "AM2": ("AM1", "上午一", "08:00", "10:00"),
    "PM1": ("PM2", "下午二", "16:20", "18:20"),
    "PM2": ("PM1", "下午一", "14:00", "16:00"),
}
PERIOD_ORDER = {"AM": 0, "PM": 1, "EVENING": 2}


def clean(value: object) -> str:
    return str(value or "").strip()


def read_csv(path: Path) -> Tuple[List[str], List[Dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, fieldnames: Sequence[str], rows: Iterable[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def load_class_conflict_map(path: Path) -> Dict[str, set[str]]:
    if not path.exists():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    groups = doc.get("class_conflict_groups") or doc.get("groups") or []
    result: Dict[str, set[str]] = defaultdict(set)
    for group in groups:
        if group.get("is_active") is False:
            continue
        group_id = clean(group.get("id"))
        for class_id in group.get("class_ids") or []:
            if class_id:
                result[class_id].add(group_id)
    return result


def load_product_course_expected_rows(data_dir: Path, class_metadata: Dict[str, Dict[str, str]]) -> Dict[Tuple[str, str, str, str], int]:
    _, product_courses = read_csv(data_dir / "product_courses.csv")
    product_by_class = {
        class_id: meta.get("product_id", "")
        for class_id, meta in class_metadata.items()
        if meta.get("suite_code") == TARGET_SUITE
        and meta.get("subject_category") == "公共课"
        and meta.get("subject") in PUBLIC_SUBJECTS
    }
    expected: Dict[Tuple[str, str, str, str], int] = {}
    for row in product_courses:
        if clean(row.get("quarter")) != TARGET_QUARTER:
            continue
        total_hours = float(row.get("total_hours") or 0)
        if total_hours <= 0:
            continue
        for class_id, product_id in product_by_class.items():
            if clean(row.get("product_id")) != product_id:
                continue
            key = (
                class_id,
                clean(row.get("stage")),
                clean(row.get("course_module")),
                clean(row.get("course_group")),
            )
            expected[key] = expected.get(key, 0) + int(round(total_hours / 2))
    return expected


def target_rows_by_key(rows: Sequence[Dict[str, str]], class_metadata: Dict[str, Dict[str, str]]) -> Dict[Tuple[str, str, str, str], List[Dict[str, str]]]:
    grouped: Dict[Tuple[str, str, str, str], List[Dict[str, str]]] = defaultdict(list)
    for row in rows:
        class_id = clean(row.get("class_id"))
        meta = class_metadata.get(class_id, {})
        if meta.get("suite_code") != TARGET_SUITE:
            continue
        if clean(row.get("quarter")) != TARGET_QUARTER:
            continue
        if clean(row.get("subject")) not in PUBLIC_SUBJECTS:
            continue
        key = (
            class_id,
            clean(row.get("stage")),
            clean(row.get("course_module")),
            clean(row.get("course_group")),
        )
        grouped[key].append(row)
    return grouped


def build_missing_rows(
    rows: Sequence[Dict[str, str]],
    class_metadata: Dict[str, Dict[str, str]],
    data_dir: Path,
) -> List[Dict[str, str]]:
    expected = load_product_course_expected_rows(data_dir, class_metadata)
    current = target_rows_by_key(rows, class_metadata)
    additions: List[Dict[str, str]] = []
    problems: List[str] = []

    for key, expected_count in sorted(expected.items()):
        existing = sorted(
            current.get(key, []),
            key=lambda row: (
                clean(row.get("date")),
                PERIOD_ORDER.get(clean(row.get("period")), 99),
                clean(row.get("start_time")),
                clean(row.get("lesson_slot")),
            ),
        )
        missing = expected_count - len(existing)
        if missing == 0:
            continue
        if missing < 0:
            problems.append(f"{key} 当前 {len(existing)} 节，超过产品应有 {expected_count} 节")
            continue
        if missing != len(existing):
            problems.append(f"{key} 当前 {len(existing)} 节，应有 {expected_count} 节，缺口 {missing} 不是当前行数，不能安全半天补齐")
            continue
        for row in existing:
            lesson_slot = clean(row.get("lesson_slot"))
            if lesson_slot not in SECOND_SLOT:
                problems.append(f"{key} {row.get('date')} {lesson_slot} 无法判断同半天第二节")
                continue
            next_slot, next_label, start_time, end_time = SECOND_SLOT[lesson_slot]
            new_row = dict(row)
            new_row["lesson_slot"] = next_slot
            new_row["slot_label"] = next_label
            new_row["start_time"] = start_time
            new_row["end_time"] = end_time
            new_row["duration_hours"] = "2"
            additions.append(new_row)

    if problems:
        raise ValueError("2757 半天补齐前置检查失败:\n" + "\n".join(problems))
    return additions


def check_conflicts(rows: Sequence[Dict[str, str]], additions: Sequence[Dict[str, str]], data_dir: Path) -> None:
    conflict_map = load_class_conflict_map(data_dir / "class_conflict_groups.json")
    by_exact: Dict[Tuple[str, str, str], List[Dict[str, str]]] = defaultdict(list)
    by_period: Dict[Tuple[str, str], List[Dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_exact[(clean(row.get("date")), clean(row.get("start_time")), clean(row.get("end_time")))].append(row)
        by_period[(clean(row.get("date")), clean(row.get("period")))].append(row)

    errors: List[str] = []
    for row in additions:
        class_id = clean(row.get("class_id"))
        groups = conflict_map.get(class_id, set())
        date = clean(row.get("date"))
        period = clean(row.get("period"))
        start_time = clean(row.get("start_time"))
        end_time = clean(row.get("end_time"))
        for other in by_exact[(date, start_time, end_time)]:
            other_class_id = clean(other.get("class_id"))
            if other_class_id == class_id:
                errors.append(f"{class_id} {date} {start_time}-{end_time} 同班已存在课次")
            if clean(row.get("teacher_id")) and clean(row.get("teacher_id")) == clean(other.get("teacher_id")):
                errors.append(f"{class_id} {date} {start_time}-{end_time} 老师冲突: {clean(row.get('teacher_name'))} / {other_class_id}")
            if clean(row.get("room_id")) and clean(row.get("room_id")) == clean(other.get("room_id")):
                errors.append(f"{class_id} {date} {start_time}-{end_time} 教室冲突: {clean(row.get('room_name'))} / {other_class_id}")
            if other_class_id != class_id and groups & conflict_map.get(other_class_id, set()):
                errors.append(f"{class_id} {date} {start_time}-{end_time} 互斥班级冲突: {other_class_id}")
        for other in by_period[(date, period)]:
            other_class_id = clean(other.get("class_id"))
            if other_class_id != class_id and groups & conflict_map.get(other_class_id, set()):
                errors.append(f"{class_id} {date} {period} 互斥班级同半天冲突: {other_class_id}")

    if errors:
        raise ValueError("2757 半天补齐冲突检查失败:\n" + "\n".join(errors[:80]))


def sort_rows(rows: Sequence[Dict[str, str]]) -> List[Dict[str, str]]:
    return sorted(
        rows,
        key=lambda row: (
            clean(row.get("date")),
            PERIOD_ORDER.get(clean(row.get("period")), 99),
            clean(row.get("start_time")),
            clean(row.get("class_id")),
            clean(row.get("subject")),
            clean(row.get("course_module")),
            clean(row.get("lesson_slot")),
        ),
    )


def count_target_rows(rows: Sequence[Dict[str, str]]) -> Dict[str, int]:
    counts: Dict[str, int] = defaultdict(int)
    for row in rows:
        if clean(row.get("class_id")) in {"KYJXS2757", "KYJXY2757", "KYJXZ2757"} and clean(row.get("date")) >= "2026-07-01":
            counts[clean(row.get("class_id"))] += 1
    return dict(sorted(counts.items()))


def backup_outputs(output_dir: Path, stamp: str) -> Path:
    backup_dir = output_dir / "backups" / f"before_2757_halfday_repair_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    for name in [
        "batch_schedule_maintenance.csv",
        "batch_schedule_maintenance.html",
        "summer_camp_schedule.html",
        "batch_schedule_maintenance_report.md",
    ]:
        source = output_dir / name
        if source.exists():
            shutil.copy2(source, backup_dir / name)
    return backup_dir


def regenerate_html(data_dir: Path, output_dir: Path, rows: Sequence[Dict[str, str]]) -> None:
    assignments = maintenance.assignments_from_rows(rows, "REPAIR_2757_HALF_DAY")
    room_names = load_room_names(data_dir)
    room_names.update({row["room_id"]: row["room_name"] for row in rows if row.get("room_id") and row.get("room_name")})
    class_metadata = maintenance.load_class_metadata(data_dir)
    window_constraints = maintenance.load_all_class_window_constraint_items(data_dir)
    start_date = min(row["date"] for row in rows if row.get("date"))
    end_date = max(row["date"] for row in rows if row.get("date"))
    for html_path in [output_dir / "batch_schedule_maintenance.html", output_dir / "summer_camp_schedule.html"]:
        write_day_table_html(
            assignments,
            html_path,
            "课表维护总表",
            ["AM", "PM", "EVENING"],
            room_names,
            start_date,
            end_date,
            class_metadata,
            window_constraints,
        )
    maintenance.write_teacher_time_conflicts_csv(assignments, output_dir / "teacher_time_conflicts.csv", room_names)


def write_report(path: Path, stamp: str, backup_dir: Path, additions: Sequence[Dict[str, str]], before: Dict[str, int], after: Dict[str, int]) -> None:
    counts: Dict[str, int] = defaultdict(int)
    for row in additions:
        counts[clean(row.get("class_id"))] += 1
    lines = [
        "# 2757 暑假 4 小时半天课次补齐报告",
        "",
        f"- 修复时间: {stamp}",
        f"- 备份目录: {backup_dir}",
        f"- 新增标准 2 小时课次: {len(additions)}",
        "",
        "## 新增行数",
    ]
    for class_id in sorted(counts):
        lines.append(f"- {class_id}: +{counts[class_id]}")
    lines.extend(["", "## 7-12 月课次数量", ""])
    lines.append("| 班级 | 修复前 | 修复后 |")
    lines.append("|---|---:|---:|")
    for class_id in sorted(set(before) | set(after)):
        lines.append(f"| {class_id} | {before.get(class_id, 0)} | {after.get(class_id, 0)} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="补齐 2757 暑假 4 小时半天被截成 2 小时的课次")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--schedule-csv", type=Path, default=DEFAULT_SCHEDULE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    fieldnames, rows = read_csv(args.schedule_csv)
    class_metadata = maintenance.load_class_metadata(args.data_dir)
    before_counts = count_target_rows(rows)
    additions = build_missing_rows(rows, class_metadata, args.data_dir)
    check_conflicts(rows, additions, args.data_dir)
    updated_rows = sort_rows([*rows, *additions])
    after_counts = count_target_rows(updated_rows)

    print(f"新增课次={len(additions)}")
    print(f"修复前={before_counts}")
    print(f"修复后={after_counts}")
    if args.dry_run:
        return

    backup_dir = backup_outputs(args.output_dir, stamp)
    write_csv(args.schedule_csv, fieldnames, updated_rows)
    regenerate_html(args.data_dir, args.output_dir, updated_rows)
    report_path = args.output_dir / f"repair_2757_halfday_blocks_{stamp}.md"
    write_report(report_path, stamp, backup_dir, additions, before_counts, after_counts)
    maintenance_report = args.output_dir / "batch_schedule_maintenance_report.md"
    with maintenance_report.open("a", encoding="utf-8") as handle:
        handle.write(
            "\n"
            "## 2757 暑假 4 小时半天课次补齐\n\n"
            f"- 新增标准 2 小时课次: {len(additions)}\n"
            f"- 修复报告: {report_path}\n"
            f"- 备份目录: {backup_dir}\n"
        )
    print(f"report={report_path}")
    print(f"backup={backup_dir}")


if __name__ == "__main__":
    main()
