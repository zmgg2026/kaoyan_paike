#!/usr/bin/env python3
from __future__ import annotations

import argparse
import itertools
import shutil
import sys
from collections import Counter, defaultdict
from datetime import date as Date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Sequence, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_camp_maintenance_schedule import load_class_metadata  # noqa: E402
from scripts.csv_utils import read_csv_rows  # noqa: E402
from scripts.product_catalog import stage_rank_map_from_context  # noqa: E402
from scripts.repair_schedule_quality_hotspots import (  # noqa: E402
    PERIOD_ORDER,
    PERIOD_SLOTS,
    Block,
    build_blocks,
    clean,
    load_area_links,
    load_area_meta,
    load_room_meta,
    move_block,
    regenerate_outputs,
    room_area,
    sort_rows,
    travel_risk_between,
    week_start,
    weekday_label,
    write_csv_rows,
)


TARGET_CLASSES = {"KYJXY2792": "英语", "KYJXZ2792": "政治"}
ROOM_ID = "RMHFWY216009"
ROOM_NAME = "南亚理工009"
SUMMER_START = "2026-07-06"
SUMMER_END = "2026-08-01"
WEEKS = ["2026-07-06", "2026-07-13", "2026-07-20", "2026-07-27"]
QUOTAS = {
    "英语": [5, 6, 6, 6],
    "政治": [6, 5, 5, 5],
}
def week_slots(week: str) -> List[Tuple[str, str]]:
    start = Date.fromisoformat(week)
    slots: List[Tuple[str, str]] = []
    for offset in range(6):
        day = start + timedelta(days=offset)
        date_text = day.isoformat()
        for period in ("AM", "PM"):
            if date_text == "2026-08-01" and period == "PM":
                continue
            slots.append((date_text, period))
    return slots


def block_subject(block: Block) -> str:
    return TARGET_CLASSES.get(block.class_id, block.subject)


def split_blocks_by_subject(rows: Sequence[dict], class_meta: Dict[str, dict]) -> Dict[str, List[Block]]:
    blocks = [
        block
        for block in build_blocks(rows, class_meta)
        if block.class_id in TARGET_CLASSES and block.period in {"AM", "PM"}
        and SUMMER_START <= block.date <= SUMMER_END
    ]
    by_subject: Dict[str, List[Block]] = defaultdict(list)
    for block in sorted(blocks, key=lambda item: (item.date, PERIOD_ORDER.get(item.period, 9), item.stage, item.subject)):
        by_subject[block_subject(block)].append(block)
    return by_subject


def assign_target_weeks(blocks: Dict[str, List[Block]]) -> Dict[str, Dict[str, List[Block]]]:
    result: Dict[str, Dict[str, List[Block]]] = {}
    for subject, subject_blocks in blocks.items():
        quotas = QUOTAS[subject]
        if sum(quotas) != len(subject_blocks):
            raise RuntimeError(f"{subject} block count {len(subject_blocks)} does not match quotas {quotas}")
        cursor = 0
        result[subject] = {}
        for week, count in zip(WEEKS, quotas):
            result[subject][week] = subject_blocks[cursor : cursor + count]
            cursor += count
    return result


def fixed_occupancy(rows: Sequence[dict], ignored_indices: Set[int]) -> Tuple[Set[Tuple[str, str, str]], Set[Tuple[str, str, str]]]:
    teacher_slots: Set[Tuple[str, str, str]] = set()
    room_slots: Set[Tuple[str, str, str]] = set()
    for index, row in enumerate(rows):
        if index in ignored_indices:
            continue
        date_text = clean(row.get("date"))
        period = clean(row.get("period"))
        if not date_text or period not in {"AM", "PM", "EVENING"}:
            continue
        teacher = clean(row.get("teacher_id")) or clean(row.get("teacher_name"))
        if teacher:
            teacher_slots.add((teacher, date_text, period))
        room_id = clean(row.get("room_id"))
        if room_id:
            room_slots.add((room_id, date_text, period))
    return teacher_slots, room_slots


def other_teacher_rooms_by_day(
    rows: Sequence[dict],
    ignored_indices: Set[int],
) -> Dict[Tuple[str, str], Dict[str, Set[str]]]:
    result: Dict[Tuple[str, str], Dict[str, Set[str]]] = defaultdict(lambda: defaultdict(set))
    for index, row in enumerate(rows):
        if index in ignored_indices:
            continue
        teacher = clean(row.get("teacher_id")) or clean(row.get("teacher_name"))
        date_text = clean(row.get("date"))
        period = clean(row.get("period"))
        room_id = clean(row.get("room_id"))
        if teacher and date_text and period and room_id:
            result[(teacher, date_text)][period].add(room_id)
    return result


def teacher_key(block: Block) -> str:
    return block.teacher_key or block.teacher_name


def slot_available(
    block: Block,
    date_text: str,
    period: str,
    teacher_slots: Set[Tuple[str, str, str]],
    room_slots: Set[Tuple[str, str, str]],
) -> bool:
    teacher = teacher_key(block)
    if teacher and (teacher, date_text, period) in teacher_slots:
        return False
    if (ROOM_ID, date_text, period) in room_slots:
        return False
    return True


def travel_cost(
    block: Block,
    date_text: str,
    period: str,
    other_rooms: Dict[Tuple[str, str], Dict[str, Set[str]]],
    room_meta: Dict[str, dict],
    area_meta: Dict[str, dict],
    area_links: Dict[Tuple[str, str], dict],
) -> int:
    teacher = teacher_key(block)
    if not teacher:
        return 0
    cost = 0
    for other_period, rooms in other_rooms.get((teacher, date_text), {}).items():
        if abs(PERIOD_ORDER.get(other_period, 9) - PERIOD_ORDER.get(period, 9)) != 1:
            continue
        for other_room in rooms:
            risk, minutes, _relation = travel_risk_between(ROOM_ID, other_room, room_meta, area_meta, area_links)
            if risk >= 3:
                cost += 80 + int(minutes)
            elif risk == 2:
                cost += 25 + int(minutes // 5)
            elif risk == 1:
                cost += 5
    return cost


def sequence_cost(
    sequence: Sequence[str],
    slots: Sequence[Tuple[str, str]],
    week_blocks: Dict[str, List[Block]],
    teacher_slots: Set[Tuple[str, str, str]],
    room_slots: Set[Tuple[str, str, str]],
    other_rooms: Dict[Tuple[str, str], Dict[str, Set[str]]],
    room_meta: Dict[str, dict],
    area_meta: Dict[str, dict],
    area_links: Dict[Tuple[str, str], dict],
) -> Tuple[int, List[Tuple[Block, str, str]]]:
    cursors = {"英语": 0, "政治": 0}
    assignments: List[Tuple[Block, str, str]] = []
    seen_subject_dates: Set[Tuple[str, str]] = set()
    cost = 0
    for label, (date_text, period) in zip(sequence, slots):
        if label == "-":
            continue
        block = week_blocks[label][cursors[label]]
        cursors[label] += 1
        if not slot_available(block, date_text, period, teacher_slots, room_slots):
            return 10**9, []
        if (label, date_text) in seen_subject_dates:
            cost += 80
        seen_subject_dates.add((label, date_text))
        cost += travel_cost(block, date_text, period, other_rooms, room_meta, area_meta, area_links)
        preferred = "AM" if label == "英语" else "PM"
        if period != preferred:
            cost += 3
        assignments.append((block, date_text, period))
    if any(cursors[subject] != len(week_blocks[subject]) for subject in ("英语", "政治")):
        return 10**9, []
    return cost, assignments


def best_week_assignments(
    week: str,
    week_blocks: Dict[str, List[Block]],
    teacher_slots: Set[Tuple[str, str, str]],
    room_slots: Set[Tuple[str, str, str]],
    other_rooms: Dict[Tuple[str, str], Dict[str, Set[str]]],
    room_meta: Dict[str, dict],
    area_meta: Dict[str, dict],
    area_links: Dict[Tuple[str, str], dict],
) -> Tuple[int, List[Tuple[Block, str, str]]]:
    slots = week_slots(week)
    required_counts = {subject: len(week_blocks[subject]) for subject in ("英语", "政治")}
    rest_count = len(slots) - required_counts["英语"] - required_counts["政治"]
    if rest_count < 0:
        raise RuntimeError(f"{week} has insufficient slots")

    best_cost = 10**9
    best: List[Tuple[Block, str, str]] = []

    stage_order = stage_rank_map_from_context("无忧秋")

    def allowed_candidates(subject: str, remaining: Tuple[int, ...]) -> List[int]:
        if not remaining:
            return []
        min_stage = min(stage_order.get(week_blocks[subject][index].stage, 99) for index in remaining)
        return [
            index
            for index in remaining
            if stage_order.get(week_blocks[subject][index].stage, 99) == min_stage
        ]

    def dfs(
        slot_index: int,
        remaining: Dict[str, Tuple[int, ...]],
        rests_left: int,
        seen_subject_dates: Set[Tuple[str, str]],
        current_cost: int,
        assignments: List[Tuple[Block, str, str]],
    ) -> None:
        nonlocal best_cost, best
        if current_cost >= best_cost:
            return
        if slot_index == len(slots):
            if all(not remaining[subject] for subject in ("英语", "政治")) and rests_left == 0:
                best_cost = current_cost
                best = list(assignments)
            return

        slots_left = len(slots) - slot_index
        required_left = len(remaining["英语"]) + len(remaining["政治"])
        if required_left > slots_left or required_left + rests_left < slots_left:
            return

        date_text, period = slots[slot_index]
        if rests_left > 0:
            dfs(slot_index + 1, remaining, rests_left - 1, seen_subject_dates, current_cost, assignments)

        for subject in ("英语", "政治"):
            if not remaining[subject]:
                continue
            for block_index in allowed_candidates(subject, remaining[subject]):
                block = week_blocks[subject][block_index]
                if not slot_available(block, date_text, period, teacher_slots, room_slots):
                    continue
                next_remaining = dict(remaining)
                next_remaining[subject] = tuple(index for index in remaining[subject] if index != block_index)
                extra = travel_cost(
                    block,
                    date_text,
                    period,
                    other_rooms,
                    room_meta,
                    area_meta,
                    area_links,
                )
                preferred = "AM" if subject == "英语" else "PM"
                if period != preferred:
                    extra += 3
                next_seen = set(seen_subject_dates)
                if (subject, date_text) in next_seen:
                    extra += 80
                next_seen.add((subject, date_text))
                assignments.append((block, date_text, period))
                dfs(
                    slot_index + 1,
                    next_remaining,
                    rests_left,
                    next_seen,
                    current_cost + extra,
                    assignments,
                )
                assignments.pop()

    dfs(
        0,
        {
            "英语": tuple(range(len(week_blocks["英语"]))),
            "政治": tuple(range(len(week_blocks["政治"]))),
        },
        rest_count,
        set(),
        0,
        [],
    )
    if not best:
        raise RuntimeError(f"cannot find feasible 2792 schedule for week {week}")
    return best_cost, best


def apply_assignment(rows: List[dict], block: Block, date_text: str, period: str) -> None:
    slots = PERIOD_SLOTS[period]
    if len(block.indices) > len(slots):
        raise RuntimeError(f"block {block.class_id} {block.date} {block.period} has too many rows")
    for index, (slot_id, slot_label, start_time, end_time) in zip(sorted(block.indices), slots):
        rows[index]["date"] = date_text
        rows[index]["weekday"] = weekday_label(date_text)
        rows[index]["period"] = period
        rows[index]["lesson_slot"] = slot_id
        rows[index]["slot_label"] = slot_label
        rows[index]["start_time"] = start_time
        rows[index]["end_time"] = end_time
        rows[index]["room_id"] = ROOM_ID
        rows[index]["room_name"] = ROOM_NAME


def subject_week_counts(rows: Sequence[dict]) -> Counter[Tuple[str, str]]:
    counts: Counter[Tuple[str, str]] = Counter()
    for row in rows:
        if clean(row.get("class_id")) not in TARGET_CLASSES:
            continue
        if clean(row.get("lesson_slot")) not in {"AM1", "PM1"}:
            continue
        date_text = clean(row.get("date"))
        if "2026-07-01" <= date_text <= "2026-08-31":
            counts[(clean(row.get("subject")), week_start(date_text))] += 1
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="专项重排 2792 暑假极端周课量")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--schedule-csv", type=Path, default=Path("outputs/batch_schedule_maintenance.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--timestamp", default="")
    args = parser.parse_args()

    timestamp = args.timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    rows = read_csv_rows(args.schedule_csv)
    class_meta = load_class_metadata(args.data_dir)
    room_meta = load_room_meta(args.data_dir)
    area_meta = load_area_meta(args.data_dir)
    area_links = load_area_links(args.data_dir)

    blocks_by_subject = split_blocks_by_subject(rows, class_meta)
    target_blocks = assign_target_weeks(blocks_by_subject)
    ignored_indices = {index for blocks in blocks_by_subject.values() for block in blocks for index in block.indices}
    teacher_slots, room_slots = fixed_occupancy(rows, ignored_indices)
    other_rooms = other_teacher_rooms_by_day(rows, ignored_indices)

    before_counts = subject_week_counts(rows)
    all_assignments: List[Tuple[Block, str, str]] = []
    week_costs: Dict[str, int] = {}
    for week in WEEKS:
        week_blocks = {subject: target_blocks[subject][week] for subject in ("英语", "政治")}
        cost, assignments = best_week_assignments(
            week,
            week_blocks,
            teacher_slots,
            room_slots,
            other_rooms,
            room_meta,
            area_meta,
            area_links,
        )
        week_costs[week] = cost
        all_assignments.extend(assignments)

    backup_dir = args.output_dir / "backups" / f"before_2792_extreme_repair_{timestamp}"
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

    for block, date_text, period in all_assignments:
        apply_assignment(rows, block, date_text, period)

    rows = sort_rows(rows)
    write_csv_rows(args.schedule_csv, rows)
    shutil.copy2(args.schedule_csv, args.output_dir / "summer_camp_schedule.csv")
    regenerate_outputs(rows, args.data_dir, args.output_dir)
    after_counts = subject_week_counts(rows)

    lines = [
        f"# 2792 极端周课量专项重排报告 {timestamp}",
        "",
        f"- 备份目录: {backup_dir}",
        f"- 调整半天块: {len(all_assignments)}",
        f"- 周目标: 英语 {QUOTAS['英语']}；政治 {QUOTAS['政治']}",
        "",
        "## 调整前后周半天数",
    ]
    for subject in ("政治", "英语"):
        before = {week: before_counts.get((subject, week), 0) for week in WEEKS}
        after = {week: after_counts.get((subject, week), 0) for week in WEEKS}
        lines.append(f"- {subject}: {before} -> {after}")
    lines.append("")
    lines.append("## 周搜索成本")
    for week in WEEKS:
        lines.append(f"- {week}: {week_costs[week]}")
    lines.append("")
    lines.append("## 新排课明细")
    for block, date_text, period in sorted(all_assignments, key=lambda item: (item[1], PERIOD_ORDER.get(item[2], 9), item[0].class_id)):
        lines.append(
            f"- {date_text} {period}: {block.class_id} {block.subject} {block.stage} "
            f"{block.course_module} {block.teacher_name}"
        )

    report_path = args.output_dir / f"repair_2792_extreme_weeks_report_{timestamp}.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with (args.output_dir / "batch_schedule_maintenance_report.md").open("a", encoding="utf-8") as handle:
        handle.write(f"\n\n## 2792 极端周课量专项重排 {timestamp}\n")
        handle.write(f"- 备份目录: {backup_dir}\n")
        for line in lines[7:15]:
            handle.write(f"{line}\n")
    print(report_path)


if __name__ == "__main__":
    main()
