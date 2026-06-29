#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scheduler
from scripts.csv_utils import clean_cell as clean, read_csv_rows, write_csv_rows
from scripts.field_utils import parse_bool
from scripts.schedule_data import load_class_metadata as load_raw_class_metadata


CoverageKey = Tuple[str, str, str, str, str, str, str]


@dataclass
class ClassMeta:
    class_id: str
    class_name: str
    sub_product: str
    subject_category: str
    subject: str
    suite_code: str
    is_locked: str

def load_class_metadata(data_dir: Path) -> Dict[str, ClassMeta]:
    result: Dict[str, ClassMeta] = {}
    for class_id, row in load_raw_class_metadata(data_dir).items():
        if not class_id:
            continue
        result[class_id] = ClassMeta(
            class_id=class_id,
            class_name=clean(row.get("name")),
            sub_product=clean(row.get("sub_product")),
            subject_category=clean(row.get("subject_category")),
            subject=clean(row.get("subject")),
            suite_code=clean(row.get("suite_code")),
            is_locked=clean(row.get("is_manual_schedule_locked")),
        )
    return result


def coverage_key(
    class_id: str,
    subject: object,
    quarter: object,
    stage: object,
    course_module: object,
    course_group: object,
    teacher_id: object,
    ignore_teacher: bool = False,
) -> CoverageKey:
    return (
        class_id,
        clean(subject),
        clean(quarter),
        clean(stage),
        clean(course_module),
        clean(course_group),
        "" if ignore_teacher else clean(teacher_id),
    )


def expected_hours(schedule_input: scheduler.ScheduleInput, ignore_teacher: bool = False) -> Counter[CoverageKey]:
    hours: Counter[CoverageKey] = Counter()
    for class_id, cls in schedule_input.classes.items():
        for requirement in cls.requirements:
            key = coverage_key(
                class_id,
                requirement.subject,
                requirement.quarter,
                requirement.stage,
                requirement.course_module,
                requirement.course_group,
                requirement.teacher_id,
                ignore_teacher,
            )
            hours[key] += float(requirement.total_hours)
    return hours


def scheduled_hours(schedule_csv: Path, ignore_teacher: bool = False) -> Counter[CoverageKey]:
    hours: Counter[CoverageKey] = Counter()
    for row in read_csv_rows(schedule_csv):
        class_id = clean(row.get("class_id"))
        if not class_id:
            continue
        key = coverage_key(
            class_id,
            row.get("subject"),
            row.get("window_name") or row.get("quarter"),
            row.get("stage"),
            row.get("course_module"),
            row.get("course_group"),
            row.get("teacher_id"),
            ignore_teacher,
        )
        hours[key] += float(row.get("duration_hours") or 0)
    return hours


def class_totals(hours: Counter[CoverageKey]) -> Counter[str]:
    totals: Counter[str] = Counter()
    for key, value in hours.items():
        totals[key[0]] += value
    return totals


def key_row(key: CoverageKey, meta: Dict[str, ClassMeta]) -> dict:
    class_id, subject, quarter, stage, module, group, teacher_id = key
    info = meta.get(class_id) or ClassMeta(class_id, "", "", "", "", "", "")
    return {
        "class_id": class_id,
        "class_name": info.class_name,
        "sub_product": info.sub_product,
        "subject_category": info.subject_category,
        "class_subject": info.subject,
        "suite_code": info.suite_code,
        "subject": subject,
        "window_name": quarter,
        "stage": stage,
        "course_module": module,
        "course_group": group,
        "teacher_id": teacher_id,
    }


def is_truthy(value: str) -> bool:
    return parse_bool(value)


def is_public_auto_class(info: ClassMeta) -> bool:
    return info.subject_category == "公共课" and not is_truthy(info.is_locked)


def class_summary_row(class_id: str, meta: Dict[str, ClassMeta], expected_total: float, scheduled_total: float) -> dict:
    info = meta.get(class_id) or ClassMeta(class_id, "", "", "", "", "", "")
    diff = expected_total - scheduled_total
    if diff > 0:
        status = "MISSING"
    elif diff < 0:
        status = "OVER"
    else:
        status = "OK"
    return {
        "class_id": class_id,
        "class_name": info.class_name,
        "sub_product": info.sub_product,
        "subject_category": info.subject_category,
        "class_subject": info.subject,
        "suite_code": info.suite_code,
        "is_locked": info.is_locked,
        "expected_hours": expected_total,
        "scheduled_hours": scheduled_total,
        "diff_hours": diff,
        "status": status,
    }


def display_extra_reason(info: ClassMeta, expected_total: float) -> str:
    if is_truthy(info.is_locked):
        return "固定/锁定课表展示，不参与自动排课门禁"
    if info.subject_category != "公共课":
        return "专业课或非公共课展示，不参与公共课自动排课门禁"
    if expected_total <= 0:
        return "无自动排课需求但维护页有展示课表"
    return "维护页包含历史/已锁定/其他阶段课表，单列为展示额外课时"


def main() -> None:
    parser = argparse.ArgumentParser(description="检查维护课表是否覆盖产品课程课时")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--schedule-csv", default="outputs/batch_schedule_maintenance.csv")
    parser.add_argument("--out-dir", default="outputs")
    parser.add_argument("--timestamp", default="")
    parser.add_argument(
        "--ignore-teacher",
        action="store_true",
        help="只按班级/科目/阶段/模块/课程分组核对课时，不把老师作为抵扣维度",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    schedule_csv = Path(args.schedule_csv)
    out_dir = Path(args.out_dir)
    stamp = args.timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")

    schedule_input = scheduler.load_input(data_dir / "scheduler_input_draft.json")
    meta = load_class_metadata(data_dir)
    expected = expected_hours(schedule_input, ignore_teacher=args.ignore_teacher)
    scheduled = scheduled_hours(schedule_csv, ignore_teacher=args.ignore_teacher)
    expected_totals = class_totals(expected)
    scheduled_totals = class_totals(scheduled)

    summary_rows: List[dict] = []
    detail_gap_rows: List[dict] = []
    detail_over_rows: List[dict] = []
    all_class_ids = sorted(set(expected_totals) | set(scheduled_totals))
    for class_id in all_class_ids:
        summary_rows.append(
            class_summary_row(
                class_id,
                meta,
                float(expected_totals[class_id]),
                float(scheduled_totals[class_id]),
            )
        )

    for key in sorted(set(expected) | set(scheduled)):
        expected_value = float(expected[key])
        scheduled_value = float(scheduled[key])
        diff = expected_value - scheduled_value
        if diff > 0:
            row = key_row(key, meta)
            row.update(
                {
                    "expected_hours": expected_value,
                    "scheduled_exact_hours": scheduled_value,
                    "diff_hours": diff,
                }
            )
            detail_gap_rows.append(row)
        elif diff < 0:
            row = key_row(key, meta)
            row.update(
                {
                    "expected_hours": expected_value,
                    "scheduled_exact_hours": scheduled_value,
                    "diff_hours": diff,
                }
            )
            detail_over_rows.append(row)

    summary_rows.sort(
        key=lambda row: (
            row["status"] != "MISSING",
            -float(row["diff_hours"]),
            row["sub_product"],
            row["suite_code"],
            row["class_id"],
        )
    )
    detail_gap_rows.sort(key=lambda row: (-float(row["diff_hours"]), row["class_id"]))
    detail_over_rows.sort(key=lambda row: (float(row["diff_hours"]), row["class_id"]))

    summary_path = out_dir / f"schedule_coverage_summary_{stamp}.csv"
    gap_path = out_dir / f"schedule_coverage_detail_gaps_{stamp}.csv"
    over_path = out_dir / f"schedule_coverage_detail_overages_{stamp}.csv"
    report_path = out_dir / f"schedule_coverage_audit_{stamp}.md"
    demand_summary_path = out_dir / f"schedule_coverage_demand_summary_{stamp}.csv"
    demand_gap_path = out_dir / f"schedule_coverage_demand_gaps_{stamp}.csv"
    demand_report_path = out_dir / f"schedule_coverage_demand_audit_{stamp}.md"
    display_extra_path = out_dir / f"schedule_coverage_display_extras_{stamp}.csv"
    display_report_path = out_dir / f"schedule_coverage_display_audit_{stamp}.md"

    summary_fields = [
        "class_id",
        "class_name",
        "sub_product",
        "subject_category",
        "class_subject",
        "suite_code",
        "is_locked",
        "expected_hours",
        "scheduled_hours",
        "diff_hours",
        "status",
    ]
    detail_fields = [
        "class_id",
        "class_name",
        "sub_product",
        "subject_category",
        "class_subject",
        "suite_code",
        "subject",
        "window_name",
        "stage",
        "course_module",
        "course_group",
        "teacher_id",
        "expected_hours",
        "scheduled_exact_hours",
        "diff_hours",
    ]
    write_csv_rows(summary_path, summary_fields, summary_rows, extrasaction="raise")
    write_csv_rows(gap_path, detail_fields, detail_gap_rows, extrasaction="raise")
    write_csv_rows(over_path, detail_fields, detail_over_rows, extrasaction="raise")

    demand_class_ids = [
        class_id
        for class_id, expected_total in expected_totals.items()
        if expected_total > 0 and is_public_auto_class(meta.get(class_id) or ClassMeta(class_id, "", "", "", "", "", ""))
    ]
    demand_rows: List[dict] = []
    for class_id in sorted(demand_class_ids):
        info = meta.get(class_id) or ClassMeta(class_id, "", "", "", "", "", "")
        expected_total = float(expected_totals[class_id])
        scheduled_total = float(scheduled_totals[class_id])
        missing_hours = max(0.0, expected_total - scheduled_total)
        extra_display_hours = max(0.0, scheduled_total - expected_total)
        if missing_hours > 0:
            status = "MISSING"
        elif scheduled_total == 0:
            status = "ZERO"
        else:
            status = "COVERED"
        demand_rows.append(
            {
                "class_id": class_id,
                "class_name": info.class_name,
                "sub_product": info.sub_product,
                "subject_category": info.subject_category,
                "class_subject": info.subject,
                "suite_code": info.suite_code,
                "is_locked": info.is_locked,
                "expected_hours": expected_total,
                "scheduled_hours": scheduled_total,
                "missing_hours": missing_hours,
                "extra_display_hours": extra_display_hours,
                "coverage_status": status,
            }
        )
    demand_rows.sort(
        key=lambda row: (
            row["coverage_status"] != "MISSING",
            -float(row["missing_hours"]),
            row["sub_product"],
            row["suite_code"],
            row["class_id"],
        )
    )
    demand_gap_rows = [row for row in demand_rows if float(row["missing_hours"]) > 0]
    demand_zero_rows = [row for row in demand_rows if float(row["expected_hours"]) > 0 and float(row["scheduled_hours"]) == 0]

    display_extra_rows: List[dict] = []
    for class_id in all_class_ids:
        info = meta.get(class_id) or ClassMeta(class_id, "", "", "", "", "", "")
        expected_total = float(expected_totals[class_id])
        scheduled_total = float(scheduled_totals[class_id])
        extra_hours = scheduled_total - expected_total
        if scheduled_total <= 0 or extra_hours <= 0:
            continue
        display_extra_rows.append(
            {
                "class_id": class_id,
                "class_name": info.class_name,
                "sub_product": info.sub_product,
                "subject_category": info.subject_category,
                "class_subject": info.subject,
                "suite_code": info.suite_code,
                "is_locked": info.is_locked,
                "expected_auto_hours": expected_total,
                "display_scheduled_hours": scheduled_total,
                "extra_display_hours": extra_hours,
                "reason": display_extra_reason(info, expected_total),
            }
        )
    display_extra_rows.sort(
        key=lambda row: (
            row["reason"],
            -float(row["extra_display_hours"]),
            row["sub_product"],
            row["suite_code"],
            row["class_id"],
        )
    )

    demand_fields = [
        "class_id",
        "class_name",
        "sub_product",
        "subject_category",
        "class_subject",
        "suite_code",
        "is_locked",
        "expected_hours",
        "scheduled_hours",
        "missing_hours",
        "extra_display_hours",
        "coverage_status",
    ]
    display_extra_fields = [
        "class_id",
        "class_name",
        "sub_product",
        "subject_category",
        "class_subject",
        "suite_code",
        "is_locked",
        "expected_auto_hours",
        "display_scheduled_hours",
        "extra_display_hours",
        "reason",
    ]
    write_csv_rows(demand_summary_path, demand_fields, demand_rows, extrasaction="raise")
    write_csv_rows(demand_gap_path, demand_fields, demand_gap_rows, extrasaction="raise")
    write_csv_rows(display_extra_path, display_extra_fields, display_extra_rows, extrasaction="raise")

    missing_rows = [row for row in summary_rows if row["status"] == "MISSING"]
    over_rows = [row for row in summary_rows if row["status"] == "OVER"]
    by_product: Dict[str, dict] = defaultdict(
        lambda: {
            "classes": 0,
            "missing_classes": 0,
            "missing_hours": 0.0,
            "zero_classes": 0,
            "over_classes": 0,
            "over_hours": 0.0,
        }
    )
    for row in summary_rows:
        product = row["sub_product"] or "未标记"
        item = by_product[product]
        item["classes"] += 1
        diff = float(row["diff_hours"])
        if diff > 0:
            item["missing_classes"] += 1
            item["missing_hours"] += diff
        elif diff < 0:
            item["over_classes"] += 1
            item["over_hours"] += abs(diff)
        if float(row["expected_hours"]) > 0 and float(row["scheduled_hours"]) == 0:
            item["zero_classes"] += 1

    demand_by_product: Dict[str, dict] = defaultdict(
        lambda: {
            "classes": 0,
            "missing_classes": 0,
            "missing_hours": 0.0,
            "zero_classes": 0,
            "extra_display_classes": 0,
            "extra_display_hours": 0.0,
        }
    )
    for row in demand_rows:
        item = demand_by_product[row["sub_product"] or "未标记"]
        item["classes"] += 1
        item["missing_hours"] += float(row["missing_hours"])
        item["extra_display_hours"] += float(row["extra_display_hours"])
        if float(row["missing_hours"]) > 0:
            item["missing_classes"] += 1
        if float(row["expected_hours"]) > 0 and float(row["scheduled_hours"]) == 0:
            item["zero_classes"] += 1
        if float(row["extra_display_hours"]) > 0:
            item["extra_display_classes"] += 1

    display_by_reason = Counter(row["reason"] for row in display_extra_rows)
    display_hours_by_reason: Dict[str, float] = defaultdict(float)
    for row in display_extra_rows:
        display_hours_by_reason[row["reason"]] += float(row["extra_display_hours"])

    demand_lines = [
        "# 自动排课需求覆盖审计",
        "",
        f"- 审计时间: {stamp}",
        f"- 覆盖口径: {'不区分老师' if args.ignore_teacher else '区分老师'}",
        "- 统计范围: `scheduler_input_draft.json` 中有自动排课需求、且班级为公共课、未锁定的班级。",
        "- 判定方式: 以班级总课时作为发布门禁；维护页额外展示课时不在本口径判为异常。",
        f"- 自动排课需求班级数: {len(demand_rows)}",
        f"- 需求缺口班级数: {len(demand_gap_rows)}",
        f"- 完全没有课表但有需求的班级数: {len(demand_zero_rows)}",
        f"- 需求缺口课时: {sum(float(row['missing_hours']) for row in demand_gap_rows):.1f}",
        f"- 自动需求汇总 CSV: {demand_summary_path}",
        f"- 自动需求缺口 CSV: {demand_gap_path}",
        "",
        "## 按产品汇总",
        "",
        "| 子产品 | 需求班级 | 缺课班级 | 缺口课时 | 0课表班级 | 有额外展示课班级 | 额外展示课时 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for product, item in sorted(demand_by_product.items(), key=lambda pair: (-pair[1]["missing_hours"], pair[0])):
        demand_lines.append(
            f"| {product} | {item['classes']} | {item['missing_classes']} | "
            f"{item['missing_hours']:.1f} | {item['zero_classes']} | "
            f"{item['extra_display_classes']} | {item['extra_display_hours']:.1f} |"
        )
    demand_lines.extend(
        [
            "",
            "## 总课时缺口最大的班级",
            "",
            "| 班级 | 产品 | 科目 | 套班 | 应排 | 已排 | 缺口 | 锁定 |",
            "|---|---|---|---:|---:|---:|---:|---|",
        ]
    )
    for row in demand_gap_rows[:100]:
        demand_lines.append(
            f"| {row['class_id']} {row['class_name']} | {row['sub_product']} | "
            f"{row['subject_category']}/{row['class_subject']} | {row['suite_code']} | "
            f"{float(row['expected_hours']):.1f} | {float(row['scheduled_hours']):.1f} | "
            f"{float(row['missing_hours']):.1f} | {row['is_locked'] or '否'} |"
        )
    demand_lines.extend(["", "## 0课表班级", ""])
    if demand_zero_rows:
        demand_lines.extend(f"- {row['class_id']} {row['class_name']}" for row in demand_zero_rows)
    else:
        demand_lines.append("- 无")

    display_lines = [
        "# 维护页额外展示课表审计",
        "",
        f"- 审计时间: {stamp}",
        "- 统计范围: 维护页中已展示，但超过当前自动排课需求总课时的课表。",
        "- 说明: 这里包含固定专业课、历史已排课、已锁定课、以及为了完整查看而展示的其他阶段课表；默认不作为自动排课失败。",
        f"- 额外展示班级数: {len(display_extra_rows)}",
        f"- 额外展示课时: {sum(float(row['extra_display_hours']) for row in display_extra_rows):.1f}",
        f"- 额外展示明细 CSV: {display_extra_path}",
        "",
        "## 按原因汇总",
        "",
        "| 原因 | 班级数 | 额外展示课时 |",
        "|---|---:|---:|",
    ]
    for reason, count in display_by_reason.most_common():
        display_lines.append(f"| {reason} | {count} | {display_hours_by_reason[reason]:.1f} |")
    display_lines.extend(
        [
            "",
            "## 额外展示课时最大的班级",
            "",
            "| 班级 | 产品 | 科目 | 套班 | 自动需求 | 维护页展示 | 额外展示 | 原因 |",
            "|---|---|---|---:|---:|---:|---:|---|",
        ]
    )
    for row in sorted(display_extra_rows, key=lambda item: -float(item["extra_display_hours"]))[:100]:
        display_lines.append(
            f"| {row['class_id']} {row['class_name']} | {row['sub_product']} | "
            f"{row['subject_category']}/{row['class_subject']} | {row['suite_code']} | "
            f"{float(row['expected_auto_hours']):.1f} | {float(row['display_scheduled_hours']):.1f} | "
            f"{float(row['extra_display_hours']):.1f} | {row['reason']} |"
        )

    with schedule_csv.open(encoding="utf-8-sig") as schedule_handle:
        schedule_row_count = sum(1 for _ in schedule_handle) - 1

    combined_lines = [
        "# 课表覆盖审计总览",
        "",
        f"- 审计时间: {stamp}",
        f"- 维护页明细行数: {schedule_row_count}",
        "",
        "## 口径 1：自动排课需求覆盖",
        "",
        f"- 自动排课需求班级数: {len(demand_rows)}",
        f"- 需求缺口班级数: {len(demand_gap_rows)}",
        f"- 完全没有课表但有需求的班级数: {len(demand_zero_rows)}",
        f"- 需求缺口课时: {sum(float(row['missing_hours']) for row in demand_gap_rows):.1f}",
        f"- 报告: {demand_report_path}",
        f"- 汇总 CSV: {demand_summary_path}",
        f"- 缺口 CSV: {demand_gap_path}",
        "",
        "## 口径 2：维护页额外展示课表",
        "",
        f"- 额外展示班级数: {len(display_extra_rows)}",
        f"- 额外展示课时: {sum(float(row['extra_display_hours']) for row in display_extra_rows):.1f}",
        f"- 报告: {display_report_path}",
        f"- 明细 CSV: {display_extra_path}",
        "",
        "## 原始精确对账文件",
        "",
        "- 以下文件按班级/科目/排课窗口/阶段/模块/课程分组精确匹配。由于历史课表与产品需求字段还存在阶段/窗口写法差异，只作为字段治理参考，不作为发布门禁。",
        f"- 原始汇总 CSV: {summary_path}",
        f"- 原始精确缺口 CSV: {gap_path}",
        f"- 原始精确超出 CSV: {over_path}",
        f"- 原始汇总缺口班级数: {len(missing_rows)}",
        f"- 原始汇总超出班级数: {len(over_rows)}",
    ]

    demand_report_path.write_text("\n".join(demand_lines) + "\n", encoding="utf-8")
    display_report_path.write_text("\n".join(display_lines) + "\n", encoding="utf-8")
    report_path.write_text("\n".join(combined_lines) + "\n", encoding="utf-8")
    print(report_path)
    print(demand_report_path)
    print(display_report_path)
    print(demand_summary_path)
    print(demand_gap_path)
    print(display_extra_path)
    print(summary_path)
    print(gap_path)
    print(over_path)


if __name__ == "__main__":
    main()
