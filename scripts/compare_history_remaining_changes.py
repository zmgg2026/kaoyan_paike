#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scheduler
from scripts import build_camp_maintenance_schedule as maintenance


RequirementKey = Tuple[str, str, str, str]


def consumed_hours_by_requirement(
    history_rows: Sequence[dict],
    before_date: str,
    class_ids: Iterable[str],
) -> Dict[Tuple[str, RequirementKey], int]:
    allowed_class_ids = set(class_ids)
    consumed: Dict[Tuple[str, RequirementKey], int] = defaultdict(int)
    for row in history_rows:
        class_id = row.get("class_id") or ""
        if class_id not in allowed_class_ids:
            continue
        if (row.get("date") or "") >= before_date:
            continue
        key = maintenance.history_requirement_key(row)
        if not all(key[:3]):
            continue
        consumed[(class_id, key)] += int(float(row.get("duration_hours") or 0))
    return consumed


def load_expanded_history(path: Path, data_dir: Path) -> Tuple[List[dict], List[str], List[str], List[str]]:
    raw_rows, warnings, ignored = maintenance.normalize_history_rows(path, data_dir)
    expanded_rows, merge_lines = maintenance.expand_online_merge_rows(raw_rows, data_dir)
    return expanded_rows, warnings, ignored, merge_lines


def requirement_rows(
    schedule_input: scheduler.ScheduleInput,
    class_metadata: Dict[str, Dict[str, str]],
    old_consumed: Dict[Tuple[str, RequirementKey], int],
    new_consumed: Dict[Tuple[str, RequirementKey], int],
) -> List[dict]:
    rows: List[dict] = []
    for class_id, cls in sorted(schedule_input.classes.items()):
        meta = class_metadata.get(class_id, {})
        for requirement in cls.requirements:
            key = scheduler.requirement_object_key(requirement)
            old_hours = old_consumed.get((class_id, key), 0)
            new_hours = new_consumed.get((class_id, key), 0)
            old_remaining = max(0, requirement.total_hours - old_hours)
            new_remaining = max(0, requirement.total_hours - new_hours)
            if old_remaining == new_remaining:
                continue
            rows.append(
                {
                    "class_id": class_id,
                    "class_name": meta.get("name") or cls.name or class_id,
                    "suite_code": maintenance.suite_code_for_class(class_id, class_metadata),
                    "sub_product": meta.get("sub_product", ""),
                    "subject": requirement.subject,
                    "stage": requirement.stage or "",
                    "course_module": requirement.course_module or "",
                    "course_group": requirement.course_group or "",
                    "total_hours": requirement.total_hours,
                    "block_hours": requirement.block_hours,
                    "old_consumed_hours": old_hours,
                    "new_consumed_hours": new_hours,
                    "old_remaining_hours": old_remaining,
                    "new_remaining_hours": new_remaining,
                    "delta_remaining_hours": new_remaining - old_remaining,
                }
            )
    return rows


def write_csv(path: Path, rows: Sequence[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "class_id",
        "class_name",
        "suite_code",
        "sub_product",
        "subject",
        "stage",
        "course_module",
        "course_group",
        "total_hours",
        "block_hours",
        "old_consumed_hours",
        "new_consumed_hours",
        "old_remaining_hours",
        "new_remaining_hours",
        "delta_remaining_hours",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_report(
    path: Path,
    *,
    old_history: Path,
    new_history: Path,
    old_count: int,
    new_count: int,
    old_warnings: Sequence[str],
    new_warnings: Sequence[str],
    rows: Sequence[dict],
) -> None:
    affected_suites = sorted({row["suite_code"] for row in rows if row.get("suite_code")})
    affected_classes = sorted({row["class_id"] for row in rows if row.get("class_id")})
    by_suite: Dict[str, Dict[str, int]] = defaultdict(lambda: {"classes": 0, "delta": 0})
    classes_by_suite: Dict[str, set] = defaultdict(set)
    for row in rows:
        suite = row.get("suite_code") or ""
        classes_by_suite[suite].add(row.get("class_id") or "")
        by_suite[suite]["delta"] += int(row.get("delta_remaining_hours") or 0)
    for suite, class_ids in classes_by_suite.items():
        by_suite[suite]["classes"] = len(class_ids)

    lines = [
        "# 历史课表剩余课时变化对比",
        "",
        f"- 旧历史课表: `{old_history}`",
        f"- 新历史课表: `{new_history}`",
        f"- 旧历史课表解析后课节数: {old_count}",
        f"- 新历史课表解析后课节数: {new_count}",
        f"- 剩余课时变化明细数: {len(rows)}",
        f"- 受影响班级数: {len(affected_classes)}",
        f"- 受影响套班: {', '.join(affected_suites) if affected_suites else '无'}",
        "",
    ]
    if rows:
        lines.extend(["## 套班汇总", "", "| 套班 | 受影响班级数 | 剩余课时净变化 |", "|---|---:|---:|"])
        for suite in affected_suites:
            item = by_suite[suite]
            lines.append(f"| {suite} | {item['classes']} | {item['delta']} |")
        lines.extend(["", "## 快速重排建议", ""])
        suite_args = " ".join(f"--suite-code {suite}" for suite in affected_suites)
        lines.append(
            "`HISTORY_PATH=\""
            + str(new_history)
            + "\" FAST_ALLOW_PREVIOUS_PUBLIC_ADJUSTMENT=1 "
            + "python3 scripts/build_camp_maintenance_schedule.py --mode fast "
            + suite_args
            + "`"
        )
        lines.append("")
    if old_warnings or new_warnings:
        lines.extend(["## 解析提醒", ""])
        for label, warnings in (("旧历史课表", old_warnings), ("新历史课表", new_warnings)):
            if not warnings:
                continue
            lines.append(f"### {label}")
            for warning in warnings[:30]:
                lines.append(f"- {warning}")
            if len(warnings) > 30:
                lines.append(f"- ... 另有 {len(warnings) - 30} 条")
            lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="对比两版历史课表导致的剩余课时变化")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--old-history", required=True)
    parser.add_argument("--new-history", required=True)
    parser.add_argument("--before-date", default="2026-07-01")
    parser.add_argument("--output-prefix", default="")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    old_history = Path(args.old_history)
    new_history = Path(args.new_history)
    class_metadata = maintenance.load_class_metadata(data_dir)
    relevant_class_ids = {
        class_id
        for class_id, meta in class_metadata.items()
        if maintenance.is_public_schedulable_meta(meta)
        and (
            meta.get("sub_product") in maintenance.HISTORY_DEDUCT_PRODUCTS
            or maintenance.suite_code_for_class(class_id, class_metadata) in maintenance.HALF_YEAR_BATCH_SUITES
        )
    }
    schedule_input = maintenance.load_schedule_input_for_classes(data_dir, relevant_class_ids)

    old_rows, old_warnings, _old_ignored, old_merge_lines = load_expanded_history(old_history, data_dir)
    new_rows, new_warnings, _new_ignored, new_merge_lines = load_expanded_history(new_history, data_dir)
    old_warnings = [*old_warnings, *old_merge_lines]
    new_warnings = [*new_warnings, *new_merge_lines]

    old_consumed = consumed_hours_by_requirement(old_rows, args.before_date, relevant_class_ids)
    new_consumed = consumed_hours_by_requirement(new_rows, args.before_date, relevant_class_ids)
    rows = requirement_rows(schedule_input, class_metadata, old_consumed, new_consumed)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = Path(args.output_prefix) if args.output_prefix else Path("outputs") / f"history_remaining_diff_{timestamp}"
    csv_path = prefix.with_suffix(".csv")
    report_path = prefix.with_suffix(".md")
    write_csv(csv_path, rows)
    write_report(
        report_path,
        old_history=old_history,
        new_history=new_history,
        old_count=len(old_rows),
        new_count=len(new_rows),
        old_warnings=old_warnings,
        new_warnings=new_warnings,
        rows=rows,
    )
    affected_suites = sorted({row["suite_code"] for row in rows if row.get("suite_code")})
    print(f"历史课表对比完成: {len(rows)} 条剩余课时变化，{len(affected_suites)} 个套班受影响")
    print(f"CSV: {csv_path}")
    print(f"报告: {report_path}")
    if affected_suites:
        print("受影响套班:", ",".join(affected_suites))


if __name__ == "__main__":
    main()
