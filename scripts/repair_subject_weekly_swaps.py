#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import sys
from collections import Counter, defaultdict
from datetime import date as Date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_camp_maintenance_schedule import load_class_metadata  # noqa: E402
from scripts.repair_schedule_quality_hotspots import (  # noqa: E402
    PERIOD_ORDER,
    PUBLIC_SUBJECTS,
    Block,
    block_window,
    build_occupancy,
    build_blocks,
    clean,
    load_blackout_dates,
    load_class_conflicts,
    load_window_constraints,
    move_block,
    preserves_stage_order,
    read_csv_rows,
    regenerate_outputs,
    sort_rows,
    target_period_in_constraint,
    target_slots_for_block,
    week_start,
    write_csv_rows,
)


def parse_subject_spec(value: str) -> Tuple[str, str, str]:
    parts = [part.strip() for part in value.split(":")]
    if len(parts) != 3 or not all(parts):
        raise argparse.ArgumentTypeError("subject spec must be suite:over_subject:under_subject")
    return parts[0], parts[1], parts[2]


def subject_week_counts(blocks: Sequence[Block], suite_code: str) -> Counter[Tuple[str, str]]:
    counts: Counter[Tuple[str, str]] = Counter()
    for block in blocks:
        if block.suite_code == suite_code and block.subject in PUBLIC_SUBJECTS and "2026-07-01" <= block.date <= "2026-08-31":
            counts[(block.subject, block.week)] += 1
    return counts


def valid_target_with_ignored(
    rows: Sequence[dict],
    block: Block,
    target_date: str,
    target_period: str,
    class_meta: Dict[str, dict],
    class_conflicts: Dict[str, Set[str]],
    window_constraints: Dict[str, object],
    blackout_dates: Set[str],
    ignore_indices: Set[int],
) -> bool:
    if target_slots_for_block(block, target_period) is None:
        return False
    if target_date in blackout_dates:
        return False
    if "2026-07-01" <= target_date <= "2026-08-31" and Date.fromisoformat(target_date).weekday() == 6:
        return False
    start, start_period, end, end_period = block_window(block, class_meta, window_constraints)
    if not target_period_in_constraint(target_date, target_period, start, start_period, end, end_period):
        return False
    meta = class_meta.get(block.class_id, {})
    if clean(meta.get("start_date")) and (target_date, PERIOD_ORDER.get(target_period, 9)) < (
        clean(meta.get("start_date")),
        PERIOD_ORDER.get(clean(meta.get("start_period")) or "AM", 9),
    ):
        return False
    if clean(meta.get("end_date")) and (target_date, PERIOD_ORDER.get(target_period, 9)) > (
        clean(meta.get("end_date")),
        PERIOD_ORDER.get(clean(meta.get("end_period")) or "EVENING", 9),
    ):
        return False
    if not preserves_stage_order(rows, block, target_date, class_meta):
        return False

    occupancy = build_occupancy(rows, class_conflicts, ignore_indices)
    if (block.class_id, target_date, target_period) in occupancy["class_period"]:
        return False
    if (block.class_id, block.subject, target_date) in occupancy["class_subject_dates"]:
        return False
    for group_id in class_conflicts.get(block.class_id, set()):
        if (group_id, target_date, target_period) in occupancy["group_period"]:
            return False
    if block.teacher_key:
        existing_rooms = occupancy["teacher_period_rooms"].get((block.teacher_key, target_date, target_period), set())
        if existing_rooms and (len(existing_rooms) > 1 or block.room_id not in existing_rooms):
            return False
    if block.room_id and occupancy["room_period_rows"].get((block.room_id, target_date, target_period)):
        return False
    return True


def swap_score(
    counts: Counter[Tuple[str, str]],
    over_subject: str,
    under_subject: str,
    over_week: str,
    under_week: str,
) -> Tuple[int, int]:
    before_over = counts[(over_subject, over_week)] - counts[(over_subject, under_week)]
    before_under = counts[(under_subject, under_week)] - counts[(under_subject, over_week)]
    after_counts = Counter(counts)
    after_counts[(over_subject, over_week)] -= 1
    after_counts[(over_subject, under_week)] += 1
    after_counts[(under_subject, under_week)] -= 1
    after_counts[(under_subject, over_week)] += 1
    after_over = after_counts[(over_subject, over_week)] - after_counts[(over_subject, under_week)]
    after_under = after_counts[(under_subject, under_week)] - after_counts[(under_subject, over_week)]
    return before_over + before_under, after_over + after_under


def find_best_swap(
    rows: Sequence[dict],
    suite_code: str,
    over_subject: str,
    under_subject: str,
    class_meta: Dict[str, dict],
    class_conflicts: Dict[str, Set[str]],
    window_constraints: Dict[str, object],
    blackout_dates: Set[str],
) -> Optional[Tuple[Block, Block, str]]:
    blocks = build_blocks(rows, class_meta)
    counts = subject_week_counts(blocks, suite_code)
    weeks = sorted({week for subject, week in counts if subject in {over_subject, under_subject}})
    if len(weeks) < 2:
        return None
    over_week = max(weeks, key=lambda week: (counts[(over_subject, week)], week))
    under_week = min(weeks, key=lambda week: (counts[(over_subject, week)], week))
    swap_candidates: List[Tuple[int, int, int, str, str, Block, Block]] = []
    source_blocks = [
        block
        for block in blocks
        if block.suite_code == suite_code
        and block.subject == over_subject
        and block.week == over_week
        and block.period in {"AM", "PM"}
    ]
    target_blocks = [
        block
        for block in blocks
        if block.suite_code == suite_code
        and block.subject == under_subject
        and block.week == under_week
        and block.period in {"AM", "PM"}
    ]
    for source in source_blocks:
        for target in target_blocks:
            ignore = set(source.indices) | set(target.indices)
            if len(source.indices) != len(target.indices):
                continue
            if not valid_target_with_ignored(
                rows,
                source,
                target.date,
                target.period,
                class_meta,
                class_conflicts,
                window_constraints,
                blackout_dates,
                ignore,
            ):
                continue
            if not valid_target_with_ignored(
                rows,
                target,
                source.date,
                source.period,
                class_meta,
                class_conflicts,
                window_constraints,
                blackout_dates,
                ignore,
            ):
                continue
            before, after = swap_score(counts, over_subject, under_subject, over_week, under_week)
            if after >= before:
                continue
            distance = abs((Date.fromisoformat(source.date) - Date.fromisoformat(target.date)).days)
            period_penalty = 0 if source.period == target.period else 3
            swap_candidates.append((after, distance, period_penalty, source.date, target.date, source, target))
    if not swap_candidates:
        return None
    swap_candidates.sort()
    after, _distance, _period_penalty, _source_date, _target_date, source, target = swap_candidates[0]
    return source, target, f"{over_subject} {source.date} {source.period} <-> {under_subject} {target.date} {target.period}; score_after={after}"


def run_swaps(
    rows: List[dict],
    specs: Sequence[Tuple[str, str, str]],
    class_meta: Dict[str, dict],
    class_conflicts: Dict[str, Set[str]],
    window_constraints: Dict[str, object],
    blackout_dates: Set[str],
    max_rounds: int,
) -> List[str]:
    lines: List[str] = []
    for _round in range(max_rounds):
        moved = False
        for suite_code, over_subject, under_subject in specs:
            result = find_best_swap(
                rows,
                suite_code,
                over_subject,
                under_subject,
                class_meta,
                class_conflicts,
                window_constraints,
                blackout_dates,
            )
            if not result:
                continue
            source, target, detail = result
            source_date, source_period = source.date, source.period
            target_date, target_period = target.date, target.period
            move_block(rows, source, target_date, target_period)
            target_after_source = build_blocks(rows, class_meta)
            refreshed_target = next(
                (
                    block
                    for block in target_after_source
                    if block.class_id == target.class_id
                    and block.subject == target.subject
                    and block.date == target_date
                    and block.period == target_period
                    and block.teacher_key == target.teacher_key
                    and block.room_id == target.room_id
                ),
                None,
            )
            if refreshed_target is None:
                raise RuntimeError(f"cannot refresh target block for {target.class_id} {target.subject}")
            move_block(rows, refreshed_target, source_date, source_period)
            lines.append(
                f"套班{suite_code} 分科周课量换位: {detail}; "
                f"{source.class_id}/{source.teacher_name or source.teacher_key} 与 "
                f"{target.class_id}/{target.teacher_name or target.teacher_key}"
            )
            moved = True
            break
        if not moved:
            break
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description="同套班内交换不同科目的半天，降低分科周课量离散度")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--schedule-csv", type=Path, default=Path("outputs/batch_schedule_maintenance.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--timestamp", default="")
    parser.add_argument(
        "--spec",
        action="append",
        type=parse_subject_spec,
        required=True,
        help="格式 suite:over_subject:under_subject，例如 2792:政治:英语",
    )
    parser.add_argument("--max-rounds", type=int, default=8)
    args = parser.parse_args()

    timestamp = args.timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    rows = read_csv_rows(args.schedule_csv)
    class_meta = load_class_metadata(args.data_dir)
    class_conflicts = load_class_conflicts(args.data_dir / "class_conflict_groups.csv")
    window_constraints = load_window_constraints(args.data_dir)
    blackout_dates = load_blackout_dates(args.data_dir / "global_blackout_dates.csv")

    backup_dir = args.output_dir / "backups" / f"before_subject_weekly_swaps_{timestamp}"
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

    lines = run_swaps(
        rows,
        args.spec,
        class_meta,
        class_conflicts,
        window_constraints,
        blackout_dates,
        args.max_rounds,
    )
    rows = sort_rows(rows)
    write_csv_rows(args.schedule_csv, rows)
    shutil.copy2(args.schedule_csv, args.output_dir / "summer_camp_schedule.csv")
    regenerate_outputs(rows, args.data_dir, args.output_dir)

    report_path = args.output_dir / f"subject_weekly_swap_report_{timestamp}.md"
    report_path.write_text(
        "# 分科周课量换位修复报告\n\n"
        + f"- 备份目录: {backup_dir}\n"
        + f"- 调整记录: {len(lines)} 条\n"
        + "\n## 明细\n"
        + "\n".join(f"- {line}" for line in lines)
        + "\n",
        encoding="utf-8",
    )
    with (args.output_dir / "batch_schedule_maintenance_report.md").open("a", encoding="utf-8") as handle:
        handle.write(f"\n\n## 分科周课量换位修复 {timestamp}\n")
        handle.write(f"- 备份目录: {backup_dir}\n")
        for line in lines[:80]:
            handle.write(f"- {line}\n")
    print(report_path)
    print(f"moves={len(lines)}")


if __name__ == "__main__":
    main()
