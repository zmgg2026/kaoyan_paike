#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import shutil
import sys
from collections import Counter, defaultdict
from datetime import date as Date, datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.repair_schedule_quality_hotspots import (  # noqa: E402
    PERIOD_ORDER,
    PUBLIC_SUBJECTS,
    active_weeks_for_suite,
    block_window,
    build_blocks,
    clean,
    date_range,
    load_area_links,
    load_area_meta,
    load_blackout_dates,
    load_class_conflicts,
    load_window_constraints,
    load_room_meta,
    move_block,
    read_csv_rows,
    regenerate_outputs,
    sort_rows,
    suite_subject_week_counts,
    suite_week_counts,
    target_period_in_constraint,
    valid_target,
    week_dates,
    week_start,
    write_csv_rows,
)
from scripts.build_camp_maintenance_schedule import load_class_metadata  # noqa: E402


DEFAULT_TARGET_GROUP = "ENROLL_27考研__2770-管综_2776英语_2770政治"


def load_conflict_group_members(path: Path) -> Dict[str, Set[str]]:
    members: Dict[str, Set[str]] = {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            if clean(row.get("is_active")) not in {"是", "1", "true", "True", "yes"}:
                continue
            group_id = clean(row.get("id"))
            class_ids = {item.strip() for item in clean(row.get("class_ids")).split("|") if item.strip()}
            if group_id and len(class_ids) >= 2:
                members[group_id] = class_ids
    return members


def halfday_class_conflict_events(
    rows: Sequence[dict],
    group_members: Dict[str, Set[str]],
    target_groups: Set[str],
) -> List[dict]:
    slot_rows: Dict[Tuple[str, str, str], List[Tuple[int, dict]]] = defaultdict(list)
    for index, row in enumerate(rows):
        class_id = clean(row.get("class_id"))
        date_text = clean(row.get("date"))
        period = clean(row.get("period"))
        if not class_id or not date_text or not period:
            continue
        for group_id, members in group_members.items():
            if target_groups and group_id not in target_groups:
                continue
            if class_id in members:
                slot_rows[(group_id, date_text, period)].append((index, row))

    events: List[dict] = []
    for (group_id, date_text, period), items in slot_rows.items():
        classes = sorted({clean(row.get("class_id")) for _index, row in items})
        if len(classes) < 2:
            continue
        events.append(
            {
                "group_id": group_id,
                "date": date_text,
                "period": period,
                "classes": classes,
                "indices": [index for index, _row in items],
            }
        )
    events.sort(key=lambda row: (row["date"], PERIOD_ORDER.get(row["period"], 9), row["group_id"]))
    return events


def ep_target_suites(rows: Sequence[dict], class_meta: Dict[str, dict]) -> Set[Tuple[str, str]]:
    subjects: Dict[Tuple[str, str], Set[str]] = defaultdict(set)
    for row in rows:
        class_id = clean(row.get("class_id"))
        meta = class_meta.get(class_id, {})
        sub_product = clean(meta.get("sub_product"))
        suite_code = clean(meta.get("suite_code"))
        subject = clean(row.get("subject"))
        if sub_product in {"全年营", "半年营"} and suite_code and subject in PUBLIC_SUBJECTS:
            subjects[(suite_code, sub_product)].add(subject)
    return {
        key
        for key, value in subjects.items()
        if "英语" in value and "政治" in value and "数学" not in value
    }


def suite_subjects_on_date(
    rows: Sequence[dict],
    class_meta: Dict[str, dict],
    suite_code: str,
    date_text: str,
    ignore_indices: Set[int],
) -> Set[str]:
    subjects: Set[str] = set()
    for index, row in enumerate(rows):
        if index in ignore_indices:
            continue
        meta = class_meta.get(clean(row.get("class_id")), {})
        if clean(meta.get("suite_code")) != suite_code:
            continue
        if clean(row.get("date")) != date_text:
            continue
        subject = clean(row.get("subject"))
        if subject in PUBLIC_SUBJECTS:
            subjects.add(subject)
    return subjects


def is_ep_block(block, target_suites: Set[Tuple[str, str]]) -> bool:
    return (block.suite_code, block.sub_product) in target_suites and block.subject in {"英语", "政治"}


def candidate_weeks_for_block(block, start: str, end: str) -> List[str]:
    original = week_start(block.date)
    weeks = sorted({week_start(day) for day in date_range(start, end)})
    return sorted(weeks, key=lambda week: (abs((Date.fromisoformat(week) - Date.fromisoformat(original)).days), week))


def find_best_target(
    rows: Sequence[dict],
    block,
    class_meta: Dict[str, dict],
    class_conflicts: Dict[str, Set[str]],
    window_constraints: Dict[str, object],
    blackout_dates: Set[str],
    ep_suites: Set[Tuple[str, str]],
    *,
    date_start: str,
    date_end: str,
    prefer_weeks: Optional[Sequence[str]] = None,
    avoid_ep_same_day: bool = True,
    periods: Sequence[str] = ("AM", "PM"),
) -> Optional[Tuple[str, str, int]]:
    start, start_period, end, end_period = block_window(block, class_meta, window_constraints)
    if not start or not end:
        return None
    start = max(start, date_start)
    end = min(end, date_end)
    if start > end:
        return None
    if prefer_weeks:
        weeks = list(prefer_weeks)
    else:
        weeks = candidate_weeks_for_block(block, start, end)

    blocks = build_blocks(rows, class_meta)
    week_totals = suite_week_counts(blocks)
    subject_week_totals = suite_subject_week_counts(blocks)
    original_day = Date.fromisoformat(block.date)
    candidates: List[Tuple[int, str, str]] = []
    for week in weeks:
        for date_text in week_dates(week):
            if date_text == block.date:
                continue
            for period in periods:
                if not target_period_in_constraint(date_text, period, start, start_period, end, end_period):
                    continue
                if not valid_target(
                    rows,
                    block,
                    date_text,
                    period,
                    class_meta,
                    class_conflicts,
                    window_constraints,
                    blackout_dates,
                ):
                    continue
                subjects_on_day = suite_subjects_on_date(rows, class_meta, block.suite_code, date_text, set(block.indices))
                ep_penalty = 0
                if is_ep_block(block, ep_suites):
                    other = "政治" if block.subject == "英语" else "英语"
                    if other in subjects_on_day:
                        if avoid_ep_same_day:
                            continue
                        ep_penalty = 500
                target_week = week_start(date_text)
                score = (
                    abs((Date.fromisoformat(date_text) - original_day).days)
                    + week_totals.get((block.suite_code, target_week), 0) * 8
                    + subject_week_totals.get((block.suite_code, block.subject, target_week), 0) * 18
                    + (0 if period == block.period else 4)
                    + (20 if subjects_on_day and block.subject not in subjects_on_day else 0)
                    + ep_penalty
                )
                candidates.append((score, date_text, period))
    if not candidates:
        return None
    candidates.sort()
    score, date_text, period = candidates[0]
    return date_text, period, score


def repair_target_group_conflicts(
    rows: List[dict],
    class_meta: Dict[str, dict],
    class_conflicts: Dict[str, Set[str]],
    group_members: Dict[str, Set[str]],
    window_constraints: Dict[str, object],
    blackout_dates: Set[str],
    ep_suites: Set[Tuple[str, str]],
    target_groups: Set[str],
    date_start: str,
    date_end: str,
    max_moves: int,
) -> List[str]:
    lines: List[str] = []
    for _ in range(max_moves):
        events = [
            event
            for event in halfday_class_conflict_events(rows, group_members, target_groups)
            if date_start <= event["date"] <= date_end
        ]
        if not events:
            break
        event = events[0]
        blocks = [
            block
            for block in build_blocks(rows, class_meta)
            if block.class_id in set(event["classes"])
            and block.date == event["date"]
            and block.period == event["period"]
            and block.subject in PUBLIC_SUBJECTS
        ]
        blocks.sort(
            key=lambda block: (
                block.class_id not in {"KYJXY2776", "KYJXZ2770"},
                block.subject != "英语",
                block.sub_product,
                block.class_id,
            )
        )
        moved = False
        for block in blocks:
            start, _start_period, end, _end_period = block_window(block, class_meta, window_constraints)
            active_weeks = active_weeks_for_suite(build_blocks(rows, class_meta), block.suite_code, start, end)
            weeks = active_weeks or candidate_weeks_for_block(block, start, end)
            weeks = sorted(
                weeks,
                key=lambda week: (
                    abs((Date.fromisoformat(week) - Date.fromisoformat(week_start(block.date))).days),
                    week,
                ),
            )
            target = find_best_target(
                rows,
                block,
                class_meta,
                class_conflicts,
                window_constraints,
                blackout_dates,
                ep_suites,
                date_start=date_start,
                date_end=date_end,
                prefer_weeks=weeks,
                avoid_ep_same_day=True,
            )
            if not target:
                target = find_best_target(
                    rows,
                    block,
                    class_meta,
                    class_conflicts,
                    window_constraints,
                    blackout_dates,
                    ep_suites,
                    date_start=date_start,
                    date_end=date_end,
                    prefer_weeks=weeks,
                    avoid_ep_same_day=False,
                )
            if not target:
                continue
            target_date, target_period, score = target
            move_block(rows, block, target_date, target_period)
            lines.append(
                f"互斥组修复: {event['group_id']} {event['date']} {event['period']} "
                f"{'/'.join(event['classes'])}; 挪 {block.class_id} {block.subject} "
                f"{block.teacher_name or block.teacher_key} -> {target_date} {target_period} score={score}"
            )
            moved = True
            break
        if not moved:
            lines.append(
                f"互斥组仍需人工处理: {event['group_id']} {event['date']} {event['period']} "
                f"{'/'.join(event['classes'])}"
            )
            break
    return lines


def ep_same_day_events(
    rows: Sequence[dict],
    class_meta: Dict[str, dict],
    target_suites: Set[Tuple[str, str]],
    date_start: str,
    date_end: str,
) -> List[dict]:
    by_suite_date_subject: Dict[Tuple[str, str, str], List[object]] = defaultdict(list)
    for block in build_blocks(rows, class_meta):
        if not is_ep_block(block, target_suites):
            continue
        if not (date_start <= block.date <= date_end):
            continue
        by_suite_date_subject[(block.suite_code, block.date, block.subject)].append(block)

    events: List[dict] = []
    seen_keys = sorted({(suite, date) for suite, date, _subject in by_suite_date_subject})
    for suite_code, date_text in seen_keys:
        english = by_suite_date_subject.get((suite_code, date_text, "英语"), [])
        politics = by_suite_date_subject.get((suite_code, date_text, "政治"), [])
        if english and politics:
            events.append({"suite_code": suite_code, "date": date_text, "英语": english, "政治": politics})
    events.sort(key=lambda row: (row["date"], row["suite_code"]))
    return events


def repair_ep_same_day(
    rows: List[dict],
    class_meta: Dict[str, dict],
    class_conflicts: Dict[str, Set[str]],
    window_constraints: Dict[str, object],
    blackout_dates: Set[str],
    ep_suites: Set[Tuple[str, str]],
    date_start: str,
    date_end: str,
    max_moves: int,
) -> List[str]:
    lines: List[str] = []
    failed: Set[Tuple[str, str]] = set()
    for _ in range(max_moves):
        events = [
            event
            for event in ep_same_day_events(rows, class_meta, ep_suites, date_start, date_end)
            if (event["suite_code"], event["date"]) not in failed
        ]
        if not events:
            break
        moved = False
        for event in events:
            blocks = build_blocks(rows, class_meta)
            subject_counts = suite_subject_week_counts(blocks)
            candidate_blocks = list(event["英语"]) + list(event["政治"])
            candidate_blocks.sort(
                key=lambda block: (
                    -subject_counts.get((block.suite_code, block.subject, block.week), 0),
                    PERIOD_ORDER.get(block.period, 9),
                    block.subject != "政治",
                    block.class_id,
                )
            )
            for block in candidate_blocks:
                start, _start_period, end, _end_period = block_window(block, class_meta, window_constraints)
                current_week = week_start(block.date)
                all_weeks = candidate_weeks_for_block(block, start, end)
                same_week_first = [current_week] + [week for week in all_weeks if week != current_week]
                target = find_best_target(
                    rows,
                    block,
                    class_meta,
                    class_conflicts,
                    window_constraints,
                    blackout_dates,
                    ep_suites,
                    date_start=date_start,
                    date_end=date_end,
                    prefer_weeks=same_week_first,
                    avoid_ep_same_day=True,
                )
                if not target:
                    continue
                target_date, target_period, score = target
                move_block(rows, block, target_date, target_period)
                lines.append(
                    f"全年/半年英政同日拆分: 套班{event['suite_code']} {event['date']} "
                    f"挪 {block.class_id} {block.subject} {block.teacher_name or block.teacher_key} "
                    f"{block.period} -> {target_date} {target_period} score={score}"
                )
                moved = True
                break
            if moved:
                break
            failed.add((event["suite_code"], event["date"]))
        if not moved:
            break
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description="修复指定互斥组重叠，并尽量拆开全年营/半年营英政班同日英政课")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--schedule-csv", type=Path, default=Path("outputs/batch_schedule_maintenance.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--timestamp", default="")
    parser.add_argument("--target-groups", default=DEFAULT_TARGET_GROUP)
    parser.add_argument("--conflict-moves", type=int, default=80)
    parser.add_argument("--ep-moves", type=int, default=120)
    parser.add_argument("--date-start", default="2026-06-25")
    parser.add_argument("--date-end", default="2026-12-13")
    args = parser.parse_args()

    timestamp = args.timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    rows = read_csv_rows(args.schedule_csv)
    class_meta = load_class_metadata(args.data_dir)
    class_conflicts = load_class_conflicts(args.data_dir / "class_conflict_groups.csv")
    group_members = load_conflict_group_members(args.data_dir / "class_conflict_groups.csv")
    window_constraints = load_window_constraints(args.data_dir)
    blackout_dates = load_blackout_dates(args.data_dir / "global_blackout_dates.csv")
    ep_suites = ep_target_suites(rows, class_meta)
    target_groups = {item.strip() for item in args.target_groups.split(",") if item.strip()}

    backup_dir = args.output_dir / "backups" / f"before_conflict_ep_repair_{timestamp}"
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

    before_conflicts = [
        event
        for event in halfday_class_conflict_events(rows, group_members, target_groups)
        if args.date_start <= event["date"] <= args.date_end
    ]
    before_ep = ep_same_day_events(rows, class_meta, ep_suites, args.date_start, args.date_end)
    lines: List[str] = []
    lines.append(f"备份目录: {backup_dir}")
    lines.append(f"目标互斥组: {','.join(sorted(target_groups))}")
    lines.append(f"修复前目标互斥重叠: {len(before_conflicts)}")
    lines.append(f"修复前全年/半年英政班同日英政: {len(before_ep)}")
    lines.extend(
        repair_target_group_conflicts(
            rows,
            class_meta,
            class_conflicts,
            group_members,
            window_constraints,
            blackout_dates,
            ep_suites,
            target_groups,
            args.date_start,
            args.date_end,
            args.conflict_moves,
        )
    )
    lines.extend(
        repair_ep_same_day(
            rows,
            class_meta,
            class_conflicts,
            window_constraints,
            blackout_dates,
            ep_suites,
            args.date_start,
            args.date_end,
            args.ep_moves,
        )
    )

    rows = sort_rows(rows)
    write_csv_rows(args.schedule_csv, rows)
    shutil.copy2(args.schedule_csv, args.output_dir / "summer_camp_schedule.csv")
    regenerate_outputs(rows, args.data_dir, args.output_dir)

    after_conflicts = [
        event
        for event in halfday_class_conflict_events(rows, group_members, target_groups)
        if args.date_start <= event["date"] <= args.date_end
    ]
    after_ep = ep_same_day_events(rows, class_meta, ep_suites, args.date_start, args.date_end)
    lines.append(f"修复后目标互斥重叠: {len(after_conflicts)}")
    lines.append(f"修复后全年/半年英政班同日英政: {len(after_ep)}")
    if after_conflicts:
        for event in after_conflicts[:20]:
            lines.append(f"未清目标互斥: {event['group_id']} {event['date']} {event['period']} {'/'.join(event['classes'])}")

    report_path = args.output_dir / f"conflict_ep_repair_report_{timestamp}.md"
    report_path.write_text("# 互斥与英政同日局部修复报告\n\n" + "\n".join(f"- {line}" for line in lines) + "\n", encoding="utf-8")
    with (args.output_dir / "batch_schedule_maintenance_report.md").open("a", encoding="utf-8") as handle:
        handle.write(f"\n\n## 互斥与英政同日局部修复 {timestamp}\n")
        for line in lines[:120]:
            handle.write(f"- {line}\n")
    print(report_path)
    print(f"target_conflicts {len(before_conflicts)} -> {len(after_conflicts)}")
    print(f"ep_same_day {len(before_ep)} -> {len(after_ep)}")


if __name__ == "__main__":
    main()
