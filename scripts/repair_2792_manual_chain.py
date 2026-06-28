#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_camp_maintenance_schedule import load_class_metadata  # noqa: E402
from scripts.repair_schedule_quality_hotspots import (  # noqa: E402
    PERIOD_ORDER,
    build_blocks,
    move_block,
    read_csv_rows,
    regenerate_outputs,
    sort_rows,
    week_start,
    write_csv_rows,
)


def find_block(rows: List[dict], class_meta: dict, class_id: str, date: str, period: str, module: str = ""):
    for block in build_blocks(rows, class_meta):
        if block.class_id != class_id or block.date != date or block.period != period:
            continue
        if module and module not in {rows[index].get("course_module", "") for index in block.indices}:
            continue
        return block
    raise RuntimeError(f"cannot find block {class_id} {date} {period} {module}")


def move(rows: List[dict], class_meta: dict, class_id: str, date: str, period: str, target_date: str, target_period: str, module: str = "") -> str:
    block = find_block(rows, class_meta, class_id, date, period, module)
    detail = f"{class_id} {block.subject} {block.stage} {module or rows[block.indices[0]].get('course_module','')} {block.teacher_name}: {date} {period} -> {target_date} {target_period}"
    move_block(rows, block, target_date, target_period)
    return detail


def swap(
    rows: List[dict],
    class_meta: dict,
    left: Tuple[str, str, str, str],
    right: Tuple[str, str, str, str],
) -> List[str]:
    left_block = find_block(rows, class_meta, *left)
    right_block = find_block(rows, class_meta, *right)
    left_date, left_period = left_block.date, left_block.period
    right_date, right_period = right_block.date, right_block.period
    left_detail = (
        f"{left_block.class_id} {left_block.subject} {left_block.stage} "
        f"{left[3] or rows[left_block.indices[0]].get('course_module','')} {left_block.teacher_name}: "
        f"{left_date} {left_period} -> {right_date} {right_period}"
    )
    right_detail = (
        f"{right_block.class_id} {right_block.subject} {right_block.stage} "
        f"{right[3] or rows[right_block.indices[0]].get('course_module','')} {right_block.teacher_name}: "
        f"{right_date} {right_period} -> {left_date} {left_period}"
    )
    move_block(rows, left_block, right_date, right_period)
    refreshed = find_block(rows, class_meta, right_block.class_id, right_date, right_period, right[3])
    move_block(rows, refreshed, left_date, left_period)
    return [left_detail, right_detail]


def suite_counts(rows: List[dict]) -> dict:
    result = {}
    for subject in ("政治", "英语"):
        counts = {}
        for row in rows:
            if row.get("class_id") not in {"KYJXZ2792", "KYJXY2792"}:
                continue
            if row.get("subject") != subject or row.get("lesson_slot") not in {"AM1", "PM1"}:
                continue
            if "2026-07-01" <= row.get("date", "") <= "2026-08-31":
                week = week_start(row["date"])
                counts[week] = counts.get(week, 0) + 1
        result[subject] = {week: counts.get(week, 0) for week in ["2026-07-06", "2026-07-13", "2026-07-20", "2026-07-27"]}
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="2792 极端周课量手工链式修复")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--schedule-csv", type=Path, default=Path("outputs/batch_schedule_maintenance.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--timestamp", default="")
    args = parser.parse_args()

    timestamp = args.timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    rows = read_csv_rows(args.schedule_csv)
    class_meta = load_class_metadata(args.data_dir)
    before = suite_counts(rows)

    backup_dir = args.output_dir / "backups" / f"before_2792_manual_chain_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    for path in [
        args.schedule_csv,
        args.output_dir / "batch_schedule_maintenance.html",
        args.output_dir / "batch_schedule_maintenance_report.md",
        args.output_dir / "teacher_time_conflicts.csv",
        args.output_dir / "summer_camp_schedule.csv",
        args.output_dir / "summer_camp_schedule.html",
    ]:
        if path.exists():
            shutil.copy2(path, backup_dir / path.name)

    details: List[str] = []
    details.extend(
        swap(
            rows,
            class_meta,
            ("KYJXZ2792", "2026-07-09", "PM", "马原"),
            ("KYJXZ2793", "2026-07-15", "PM", ""),
        )
    )
    details.append(move(rows, class_meta, "KYJXY2792", "2026-07-15", "AM", "2026-07-09", "PM", "语法"))
    details.append(move(rows, class_meta, "KYJXY2792", "2026-07-27", "PM", "2026-07-15", "AM", "写作"))
    details.extend(
        swap(
            rows,
            class_meta,
            ("KYJXZ2792", "2026-07-10", "AM", "马原"),
            ("KYZZ2704", "2026-07-16", "PM", ""),
        )
    )
    details.append(move(rows, class_meta, "KYJXY2792", "2026-07-16", "AM", "2026-07-10", "AM", "语法"))
    details.append(move(rows, class_meta, "KYJXY2792", "2026-07-30", "PM", "2026-07-16", "AM", "翻译"))
    details.append(move(rows, class_meta, "KYJXZ2792", "2026-07-21", "PM", "2026-07-27", "PM", "史纲"))

    rows = sort_rows(rows)
    write_csv_rows(args.schedule_csv, rows)
    shutil.copy2(args.schedule_csv, args.output_dir / "summer_camp_schedule.csv")
    regenerate_outputs(rows, args.data_dir, args.output_dir)
    after = suite_counts(rows)

    report_path = args.output_dir / f"repair_2792_manual_chain_report_{timestamp}.md"
    report_path.write_text(
        "\n".join(
            [
                f"# 2792 极端周课量手工链式修复 {timestamp}",
                "",
                f"- 备份目录: {backup_dir}",
                f"- 调整记录: {len(details)}",
                f"- 调整前: {before}",
                f"- 调整后: {after}",
                "",
                "## 明细",
                *[f"- {line}" for line in details],
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    with (args.output_dir / "batch_schedule_maintenance_report.md").open("a", encoding="utf-8") as handle:
        handle.write(f"\n\n## 2792 极端周课量手工链式修复 {timestamp}\n")
        handle.write(f"- 备份目录: {backup_dir}\n")
        handle.write(f"- 调整前: {before}\n")
        handle.write(f"- 调整后: {after}\n")
        for line in details:
            handle.write(f"- {line}\n")
    print(report_path)


if __name__ == "__main__":
    main()
