#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_camp_maintenance_schedule import load_class_metadata  # noqa: E402
from scripts.csv_utils import read_csv_rows  # noqa: E402
from scripts.repair_schedule_quality_hotspots import (  # noqa: E402
    PERIOD_ORDER,
    PUBLIC_SUBJECTS,
    Block,
    build_blocks,
    clean,
    load_area_links,
    load_area_meta,
    load_blackout_dates,
    load_class_conflicts,
    load_window_constraints,
    load_room_meta,
    move_block,
    parse_name_set,
    regenerate_outputs,
    sort_rows,
    teacher_day_travel_score,
    travel_events,
    write_csv_rows,
)
from scripts.repair_subject_weekly_swaps import valid_target_with_ignored  # noqa: E402


def swap_blocks(rows: List[dict], class_meta: Dict[str, dict], left: Block, right: Block) -> None:
    left_date, left_period = left.date, left.period
    right_date, right_period = right.date, right.period
    move_block(rows, left, right_date, right_period)
    # `right.indices` still points at the original rows. Reusing the original
    # block avoids accidentally grouping both swapped lessons together when
    # they are the same class/subject/teacher/room on the temporary target day.
    move_block(rows, right, left_date, left_period)


def day_score(
    rows: Sequence[dict],
    teacher_key: str,
    dates: Set[str],
    room_meta: Dict[str, dict],
    area_meta: Dict[str, dict],
    area_links: Dict[Tuple[str, str], dict],
) -> int:
    return sum(teacher_day_travel_score(rows, teacher_key, date, room_meta, area_meta, area_links) for date in dates)


def candidate_blocks_for_teacher(
    blocks: Sequence[Block],
    teacher_key: str,
    start_date: str,
    end_date: str,
) -> List[Block]:
    return [
        block
        for block in blocks
        if block.teacher_key == teacher_key
        and block.subject in PUBLIC_SUBJECTS
        and block.period in {"AM", "PM"}
        and start_date <= block.date <= end_date
    ]


def valid_swap(
    rows: Sequence[dict],
    left: Block,
    right: Block,
    class_meta: Dict[str, dict],
    class_conflicts: Dict[str, Set[str]],
    window_constraints: Dict[str, object],
    blackout_dates: Set[str],
) -> bool:
    if left.key == right.key:
        return False
    if left.date == right.date:
        return False
    if len(left.indices) != len(right.indices):
        return False
    ignore = set(left.indices) | set(right.indices)
    return valid_target_with_ignored(
        rows,
        left,
        right.date,
        right.period,
        class_meta,
        class_conflicts,
        window_constraints,
        blackout_dates,
        ignore,
    ) and valid_target_with_ignored(
        rows,
        right,
        left.date,
        left.period,
        class_meta,
        class_conflicts,
        window_constraints,
        blackout_dates,
        ignore,
    )


def find_best_swap(
    rows: List[dict],
    target_teachers: Set[str],
    class_meta: Dict[str, dict],
    class_conflicts: Dict[str, Set[str]],
    window_constraints: Dict[str, object],
    blackout_dates: Set[str],
    room_meta: Dict[str, dict],
    area_meta: Dict[str, dict],
    area_links: Dict[Tuple[str, str], dict],
    start_date: str,
    end_date: str,
) -> Optional[Tuple[int, Block, Block, str]]:
    blocks = build_blocks(rows, class_meta)
    events = [
        event
        for event in travel_events(rows, room_meta, area_meta, area_links)
        if start_date <= event["date"] <= end_date
        and (event["teacher"] in target_teachers or event["teacher_name"] in target_teachers)
    ]
    if not events:
        return None
    high_counts = Counter(event["teacher"] for event in events)
    events.sort(key=lambda event: (-high_counts[event["teacher"]], -event["risk"], -event["minutes"], event["date"]))

    best: Optional[Tuple[int, int, str, Block, Block, str]] = None
    for event in events[:80]:
        teacher_key = event["teacher"]
        event_periods = {event["left_period"], event["right_period"]}
        source_blocks = [
            block
            for block in blocks
            if block.teacher_key == teacher_key
            and block.date == event["date"]
            and block.period in event_periods
            and block.subject in PUBLIC_SUBJECTS
            and block.period in {"AM", "PM"}
        ]
        candidates = candidate_blocks_for_teacher(blocks, teacher_key, start_date, end_date)
        for left in source_blocks:
            for right in candidates:
                if right.date == left.date:
                    continue
                if not valid_swap(rows, left, right, class_meta, class_conflicts, window_constraints, blackout_dates):
                    continue
                snapshot = [dict(row) for row in rows]
                dates = {left.date, right.date}
                before = day_score(snapshot, teacher_key, dates, room_meta, area_meta, area_links)
                swap_blocks(snapshot, class_meta, left, right)
                after = day_score(snapshot, teacher_key, dates, room_meta, area_meta, area_links)
                if after >= before:
                    continue
                improvement = before - after
                distance = abs((datetime.fromisoformat(left.date) - datetime.fromisoformat(right.date)).days)
                detail = (
                    f"{event['teacher_name']} 交换 {left.class_id} {left.subject} {left.date} {left.period} "
                    f"<-> {right.class_id} {right.subject} {right.date} {right.period}，跨区评分 {before}->{after}"
                )
                candidate = (-improvement, distance, detail, left, right, teacher_key)
                if best is None or candidate < best:
                    best = candidate
    if best is None:
        return None
    _negative_improvement, _distance, detail, left, right, _teacher_key = best
    return -_negative_improvement, left, right, detail


def run_swaps(
    rows: List[dict],
    target_teachers: Set[str],
    class_meta: Dict[str, dict],
    class_conflicts: Dict[str, Set[str]],
    window_constraints: Dict[str, object],
    blackout_dates: Set[str],
    room_meta: Dict[str, dict],
    area_meta: Dict[str, dict],
    area_links: Dict[Tuple[str, str], dict],
    start_date: str,
    end_date: str,
    max_swaps: int,
) -> List[str]:
    lines: List[str] = []
    for _ in range(max_swaps):
        result = find_best_swap(
            rows,
            target_teachers,
            class_meta,
            class_conflicts,
            window_constraints,
            blackout_dates,
            room_meta,
            area_meta,
            area_links,
            start_date,
            end_date,
        )
        if not result:
            break
        improvement, left, right, detail = result
        swap_blocks(rows, class_meta, left, right)
        lines.append(f"{detail}；改善 {improvement}")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description="通过同老师课节交换减少同日跨远距离区域")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--schedule-csv", type=Path, default=Path("outputs/batch_schedule_maintenance.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--timestamp", default="")
    parser.add_argument("--teachers", default="张颖栋,樊奕")
    parser.add_argument("--max-swaps", type=int, default=8)
    parser.add_argument("--date-start", default="2026-06-25")
    parser.add_argument("--date-end", default="2026-12-13")
    args = parser.parse_args()

    timestamp = args.timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    rows = read_csv_rows(args.schedule_csv)
    class_meta = load_class_metadata(args.data_dir)
    class_conflicts = load_class_conflicts(args.data_dir / "class_conflict_groups.csv")
    window_constraints = load_window_constraints(args.data_dir)
    blackout_dates = load_blackout_dates(args.data_dir / "global_blackout_dates.csv")
    room_meta = load_room_meta(args.data_dir)
    area_meta = load_area_meta(args.data_dir)
    area_links = load_area_links(args.data_dir)
    target_teachers = parse_name_set(args.teachers)

    backup_dir = args.output_dir / "backups" / f"before_teacher_travel_swaps_{timestamp}"
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
        target_teachers,
        class_meta,
        class_conflicts,
        window_constraints,
        blackout_dates,
        room_meta,
        area_meta,
        area_links,
        args.date_start,
        args.date_end,
        args.max_swaps,
    )

    rows = sort_rows(rows)
    write_csv_rows(args.schedule_csv, rows)
    shutil.copy2(args.schedule_csv, args.output_dir / "summer_camp_schedule.csv")
    regenerate_outputs(rows, args.data_dir, args.output_dir)

    report_path = args.output_dir / f"teacher_travel_swap_report_{timestamp}.md"
    report_path.write_text(
        "\n".join(
            [
                f"# 老师跨区域连锁交换报告 {timestamp}",
                "",
                f"- 备份目录: {backup_dir}",
                f"- 目标老师: {','.join(sorted(target_teachers))}",
                f"- 调整记录: {len(lines)}",
                "",
                "## 明细",
                *[f"- {line}" for line in lines],
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    with (args.output_dir / "batch_schedule_maintenance_report.md").open("a", encoding="utf-8") as handle:
        handle.write(f"\n\n## 老师跨区域连锁交换 {timestamp}\n")
        handle.write(f"- 备份目录: {backup_dir}\n")
        for line in lines:
            handle.write(f"- {line}\n")
    print(report_path)
    print(f"moves={len(lines)}")


if __name__ == "__main__":
    main()
