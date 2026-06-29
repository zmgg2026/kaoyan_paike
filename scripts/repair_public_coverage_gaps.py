#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter, defaultdict
from datetime import date as Date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Sequence, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scheduler
from scripts import build_camp_maintenance_schedule as maintenance
from scripts.calendar_utils import date_range
from scripts.csv_utils import read_csv_rows, read_csv_with_fieldnames, write_csv_rows as write_csv_rows_with_fields
from scripts.field_utils import normalize_text as clean, split_delimited_values
from scripts.period_utils import PERIOD_ORDER
from scripts.schedule_data import load_class_metadata, load_room_names
from scripts.schedule_display import week_start, weekday_label
from scripts.schedule_outputs import write_day_table_html
from scripts.subject_utils import PUBLIC_SUBJECT_PLACEMENT_ORDER as SUBJECT_ORDER
from scripts.time_slot_templates import lesson_slot_order, period_slot_specs

DEFAULT_TARGET_CLASSES = {
    "KYYY2701",
    "KYZZ2701",
    "KYYY2702",
    "KYZZ2702",
    "KYSX2702",
    "KYYY2720",
    "KYYY2722",
    "KYZZ2722",
    "KYSX2722",
    "KYYY2727",
    "KYZZ2727",
}
PERIOD_SLOTS = period_slot_specs(("AM", "PM"))
SLOT_ORDER = lesson_slot_order()


def load_csv_rows(path: Path) -> Tuple[List[str], List[dict]]:
    return read_csv_with_fieldnames(path)


def write_csv_rows(path: Path, fieldnames: Sequence[str], rows: Sequence[dict]) -> None:
    write_csv_rows_with_fields(path, fieldnames, rows)


def suite_code_for_class(class_id: str, class_rows: Dict[str, dict]) -> str:
    return clean(class_rows.get(class_id, {}).get("suite_code")) or class_id[-4:]


def sub_product_for_class(class_id: str, class_rows: Dict[str, dict]) -> str:
    return clean(class_rows.get(class_id, {}).get("sub_product"))


def room_for_class(class_id: str, class_rows: Dict[str, dict]) -> str:
    preferred = clean(class_rows.get(class_id, {}).get("preferred_room_ids"))
    preferred_rooms = split_delimited_values(preferred)
    return preferred_rooms[0] if preferred_rooms else ""


def make_class_conflict_index(data_dir: Path) -> Dict[str, Set[str]]:
    data = json.loads((data_dir / "class_conflict_groups.json").read_text(encoding="utf-8"))
    result: Dict[str, Set[str]] = defaultdict(set)
    for group in data.get("class_conflict_groups", []):
        if not group.get("is_active", True):
            continue
        group_id = clean(group.get("id"))
        for class_id in group.get("class_ids") or []:
            result[clean(class_id)].add(group_id)
    return result


def share_class_conflict(left: str, right: str, class_conflicts: Dict[str, Set[str]]) -> bool:
    return left == right or bool(class_conflicts.get(left, set()) & class_conflicts.get(right, set()))


def gap_key(row: dict) -> Tuple[str, str, str, str, str, str, str]:
    return (
        clean(row.get("class_id")),
        clean(row.get("subject")),
        clean(row.get("window_name")) or clean(row.get("quarter")),
        clean(row.get("stage")),
        clean(row.get("course_module")),
        clean(row.get("course_group")),
        clean(row.get("teacher_id")),
    )


def build_requirement_lookup(
    schedule_input: scheduler.ScheduleInput,
    target_classes: Set[str],
) -> Dict[Tuple[str, str, str, str, str, str, str], scheduler.Requirement]:
    lookup: Dict[Tuple[str, str, str, str, str, str, str], scheduler.Requirement] = {}
    for class_id in target_classes:
        school_class = schedule_input.classes.get(class_id)
        if not school_class:
            continue
        for requirement in school_class.requirements:
            key = (
                class_id,
                clean(requirement.subject),
                clean(requirement.quarter),
                clean(requirement.stage),
                clean(requirement.course_module),
                clean(requirement.course_group),
                clean(requirement.teacher_id),
            )
            lookup[key] = requirement
    return lookup


def make_gap_tasks(
    gap_rows: Sequence[dict],
    over_rows: Sequence[dict],
    requirement_lookup: Dict[Tuple[str, str, str, str, str, str, str], scheduler.Requirement],
    class_rows: Dict[str, dict],
    room_names: Dict[str, str],
) -> Tuple[List[dict], List[str]]:
    gap_hours: Dict[Tuple[str, str, str, str, str, str, str], float] = {
        gap_key(row): float(row.get("diff_hours") or 0)
        for row in gap_rows
        if float(row.get("diff_hours") or 0) > 0
    }
    offset_lines: List[str] = []
    for row in over_rows:
        over_hours = abs(float(row.get("diff_hours") or 0))
        if over_hours <= 0:
            continue
        over_key = gap_key(row)
        candidates = [
            key
            for key, hours in gap_hours.items()
            if hours > 0
            and key[0] == over_key[0]
            and key[1] == over_key[1]
            and key[3] == over_key[3]
            and key[5] == over_key[5]
            and key[6] == over_key[6]
        ]
        candidates.sort(key=lambda key: (-gap_hours[key], key[4]))
        remaining = over_hours
        for key in candidates:
            if remaining <= 0:
                break
            offset = min(remaining, gap_hours[key])
            gap_hours[key] -= offset
            remaining -= offset
            offset_lines.append(
                f"{key[0]} {key[1]}/{key[3]}/{over_key[4]} 超出 {offset:.1f}h，"
                f"抵扣同组缺口 {key[4]} {offset:.1f}h"
            )

    tasks: List[dict] = []
    for key, hours in gap_hours.items():
        if hours <= 0:
            continue
        if round(hours) % 4 != 0:
            raise ValueError(f"缺口不是 4 小时半天整块: {key} {hours}")
        requirement = requirement_lookup.get(key)
        if requirement is None:
            raise ValueError(f"找不到缺口对应课程需求: {key}")
        class_id = key[0]
        room_id = room_for_class(class_id, class_rows)
        for index in range(int(round(hours / 4))):
            tasks.append(
                {
                    "class_id": class_id,
                    "class_name": class_rows[class_id]["name"],
                    "subject": key[1],
                    "window_name": key[2],
                    "stage": key[3],
                    "course_module": key[4],
                    "course_group": key[5],
                    "teacher_id": key[6],
                    "teacher_name": requirement.teacher_name,
                    "course_code": requirement.course_code or "",
                    "course_name": requirement.course_name or "",
                    "room_id": room_id,
                    "room_name": room_names.get(room_id, room_id),
                    "task_index": index,
                }
            )
    tasks.sort(
        key=lambda task: (
            latest_window_end(task, class_rows),
            task["class_id"],
            SUBJECT_ORDER.get(task["subject"], 99),
            task["stage"],
            task["course_module"],
            task["task_index"],
        )
    )
    return tasks, offset_lines


def latest_window_end(task: dict, class_rows: Dict[str, dict]) -> str:
    windows = candidate_windows(task, class_rows)
    return min((window[1] for window in windows), default="9999-12-31")


def candidate_windows(task: dict, class_rows: Dict[str, dict], relax_deadline: bool = False) -> List[Tuple[str, str, Set[int], List[str]]]:
    class_id = task["class_id"]
    suite_code = suite_code_for_class(class_id, class_rows)
    sub_product = sub_product_for_class(class_id, class_rows)
    stage = task["stage"]
    class_start = clean(class_rows[class_id].get("start_date")) or "2026-07-01"
    class_end = clean(class_rows[class_id].get("end_date")) or "2026-12-13"
    windows: List[Tuple[str, str, Set[int], List[str]]] = []
    if sub_product in {"无忧秋", "无忧春"}:
        if stage in {"基础", "强化"}:
            foundation_end = {
                "2701": "2026-07-26",
                "2702": "2026-08-02",
                "2704": "2026-08-02",
                "2706": "2026-08-02",
                "2721": "2026-08-02",
                "2720": "2026-08-16",
            }.get(suite_code, "2026-08-31")
            windows.append((max(class_start, "2026-07-04"), min(class_end, foundation_end), {0, 1, 2, 3, 4, 5}, ["AM", "PM"]))
            if relax_deadline:
                windows.append((max(class_start, "2026-07-04"), min(class_end, "2026-12-06"), {0, 1, 2, 3, 4, 5, 6}, ["AM", "PM"]))
        elif stage == "冲刺":
            windows.append((max(class_start, "2026-09-05"), min(class_end, "2026-12-06"), {5, 6}, ["AM", "PM"]))
            windows.append((max(class_start, "2026-10-06"), min(class_end, "2026-10-07"), {1, 2}, ["AM", "PM"]))
    elif sub_product == "无忧暑":
        if stage in {"基础", "强化"}:
            windows.append((max(class_start, "2026-07-06"), min(class_end, "2026-08-31"), {0, 1, 2, 3, 4, 5}, ["AM", "PM"]))
            windows.append((max(class_start, "2026-09-05"), min(class_end, "2026-10-28"), {2, 5, 6}, ["PM", "AM"]))
            if relax_deadline:
                windows.append((max(class_start, "2026-07-06"), min(class_end, "2026-12-13"), {0, 1, 2, 3, 4, 5, 6}, ["AM", "PM"]))
        elif stage == "冲刺":
            windows.append((max(class_start, "2026-10-28"), min(class_end, "2026-12-13"), {2, 5, 6}, ["PM", "AM"]))
    else:
        windows.append((class_start, class_end, {0, 1, 2, 3, 4, 5}, ["AM", "PM"]))
    return [window for window in windows if window[0] <= window[1]]


def halfday_rows(task: dict, date_text: str, period: str, fieldnames: Sequence[str]) -> List[dict]:
    rows: List[dict] = []
    window_name = task.get("window_name") or task.get("quarter") or ""
    for slot_id, slot_label, start_time, end_time in PERIOD_SLOTS[period]:
        row = {field: "" for field in fieldnames}
        row.update(
            {
                "date": date_text,
                "weekday": weekday_label(date_text),
                "period": period,
                "lesson_slot": slot_id,
                "slot_label": slot_label,
                "start_time": start_time,
                "end_time": end_time,
                "class_id": task["class_id"],
                "class_name": task["class_name"],
                "subject": task["subject"],
                "stage": task["stage"],
                "course_module": task["course_module"],
                "course_group": task["course_group"],
                "course_code": task["course_code"],
                "course_name": task["course_name"],
                "teacher_id": task["teacher_id"],
                "teacher_name": task["teacher_name"],
                "room_id": task["room_id"],
                "room_name": task["room_name"],
                "duration_hours": "2",
            }
        )
        if "window_name" in row:
            row["window_name"] = window_name
        if "quarter" in row:
            row["quarter"] = window_name
        rows.append(row)
    return rows


def sort_schedule_rows(rows: Sequence[dict]) -> List[dict]:
    return sorted(
        rows,
        key=lambda row: (
            row.get("date") or "",
            PERIOD_ORDER.get(row.get("period"), 9),
            SLOT_ORDER.get(row.get("lesson_slot"), 99),
            row.get("class_id") or "",
            row.get("subject") or "",
            row.get("stage") or "",
            row.get("course_module") or "",
        ),
    )


class PlacementContext:
    def __init__(
        self,
        rows: List[dict],
        class_rows: Dict[str, dict],
        class_conflicts: Dict[str, Set[str]],
        blackouts: Set[str],
        fieldnames: Sequence[str],
    ) -> None:
        self.rows = rows
        self.class_rows = class_rows
        self.class_conflicts = class_conflicts
        self.blackouts = blackouts
        self.fieldnames = fieldnames

    def hard_conflict(self, task: dict, date_text: str, period: str) -> bool:
        for new_row in halfday_rows(task, date_text, period, self.fieldnames):
            for row in self.rows:
                if row.get("date") != date_text or row.get("lesson_slot") != new_row["lesson_slot"]:
                    continue
                if share_class_conflict(new_row["class_id"], row.get("class_id", ""), self.class_conflicts):
                    return True
                if new_row["teacher_id"] and row.get("teacher_id") and new_row["teacher_id"] == row.get("teacher_id"):
                    return True
                if new_row["room_id"] and row.get("room_id") and new_row["room_id"] == row.get("room_id"):
                    return True
        return False

    def same_subject_day_hours(self, task: dict, date_text: str) -> float:
        return sum(
            float(row.get("duration_hours") or 0)
            for row in self.rows
            if row.get("class_id") == task["class_id"]
            and row.get("subject") == task["subject"]
            and row.get("date") == date_text
        )

    def class_day_hours(self, task: dict, date_text: str) -> float:
        return sum(
            float(row.get("duration_hours") or 0)
            for row in self.rows
            if row.get("class_id") == task["class_id"] and row.get("date") == date_text
        )

    def suite_week_halfdays(self, task: dict, date_text: str, subject: str = "") -> int:
        suite_code = suite_code_for_class(task["class_id"], self.class_rows)
        week = week_start(date_text)
        return len(
            {
                (row.get("date"), row.get("period"), row.get("class_id"))
                for row in self.rows
                if suite_code_for_class(row.get("class_id", ""), self.class_rows) == suite_code
                and week_start(row.get("date")) == week
                and (not subject or row.get("subject") == subject)
            }
        )

    def suite_day_halfdays(self, task: dict, date_text: str) -> int:
        suite_code = suite_code_for_class(task["class_id"], self.class_rows)
        return len(
            {
                (row.get("class_id"), row.get("period"))
                for row in self.rows
                if suite_code_for_class(row.get("class_id", ""), self.class_rows) == suite_code
                and row.get("date") == date_text
            }
        )

    def teacher_consecutive_penalty(self, task: dict, date_text: str) -> int:
        teacher_id = task["teacher_id"]
        if not teacher_id:
            return 0
        center = Date.fromisoformat(date_text)
        teacher_dates = {
            Date.fromisoformat(row["date"])
            for row in self.rows
            if row.get("teacher_id") == teacher_id and row.get("date")
        }
        teacher_dates.add(center)
        longest = 0
        current = 0
        for offset in range(-7, 8):
            day = center + timedelta(days=offset)
            if day in teacher_dates:
                current += 1
                longest = max(longest, current)
            else:
                current = 0
        return max(0, longest - 3)

    def candidates(self, task: dict, allow_same_subject_day: bool, relax_deadline: bool) -> List[Tuple[float, str, str]]:
        candidates: List[Tuple[float, str, str]] = []
        seen: Set[Tuple[str, str]] = set()
        for start, end, weekdays, periods in candidate_windows(task, self.class_rows, relax_deadline):
            for date_text in date_range(start, end):
                day = Date.fromisoformat(date_text)
                if day.weekday() not in weekdays or date_text in self.blackouts:
                    continue
                for period in periods:
                    if (date_text, period) in seen:
                        continue
                    seen.add((date_text, period))
                    if self.hard_conflict(task, date_text, period):
                        continue
                    if not allow_same_subject_day and self.same_subject_day_hours(task, date_text) > 0:
                        continue
                    if self.class_day_hours(task, date_text) >= 8:
                        continue
                    penalty = 0.0
                    penalty += self.suite_week_halfdays(task, date_text) * 6
                    penalty += self.suite_week_halfdays(task, date_text, task["subject"]) * 12
                    penalty += self.suite_day_halfdays(task, date_text) * 8
                    penalty += self.teacher_consecutive_penalty(task, date_text) * 30
                    if sub_product_for_class(task["class_id"], self.class_rows) == "无忧暑" and date_text >= "2026-09-01":
                        weekday = day.weekday()
                        if weekday == 2 and period == "AM":
                            penalty += 5
                        if weekday in {5, 6}:
                            penalty += 1
                    if relax_deadline:
                        penalty += 100
                    penalty += (day - Date.fromisoformat(candidate_windows(task, self.class_rows)[0][0])).days * 0.05
                    candidates.append((penalty, date_text, period))
        candidates.sort()
        return candidates

    def place(self, task: dict) -> Tuple[str, str, float]:
        for allow_same_subject_day, relax_deadline in (
            (False, False),
            (True, False),
            (False, True),
            (True, True),
        ):
            candidates = self.candidates(task, allow_same_subject_day, relax_deadline)
            if not candidates:
                continue
            penalty, date_text, period = candidates[0]
            self.rows.extend(halfday_rows(task, date_text, period, self.fieldnames))
            return date_text, period, penalty
        raise ValueError(
            f"无法补入课程: {task['class_id']} {task['subject']}/{task['stage']}/{task['course_module']} {task['teacher_name']}"
        )


def regenerate_outputs(data_dir: Path, output_dir: Path, rows: Sequence[dict]) -> None:
    assignments = maintenance.assignments_from_rows(rows, "PUBLIC_GAP_REPAIR")
    room_names = load_room_names(data_dir)
    room_names.update({row["room_id"]: row["room_name"] for row in rows if row.get("room_id") and row.get("room_name")})
    class_metadata = load_class_metadata(data_dir)
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


def append_report(output_dir: Path, placements: Sequence[Tuple[dict, str, str, float]], offset_lines: Sequence[str]) -> None:
    report_path = output_dir / "batch_schedule_maintenance_report.md"
    lines = [
        "",
        "## 2701/2702/2720/2722/2727 公共课缺口专项补课",
        f"- 执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 新增补课半天: {len(placements)}",
        f"- 新增补课 2 小时课节行: {len(placements) * 2}",
    ]
    if offset_lines:
        lines.append("- 既有超排抵扣:")
        lines.extend(f"  - {line}" for line in offset_lines)
    lines.append("- 补课明细:")
    for task, date_text, period, _penalty in placements:
        lines.append(
            f"  - {date_text} {period} {task['class_id']} "
            f"{task['subject']}/{task['stage']}/{task['course_module']} {task['teacher_name']}"
        )
    report_path.write_text(report_path.read_text(encoding="utf-8") + "\n".join(lines) + "\n", encoding="utf-8")
    (output_dir / "summer_camp_schedule_build_report.md").write_text(report_path.read_text(encoding="utf-8"), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="专项补齐公共课班级总课时缺口")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--schedule-csv", type=Path, default=Path("outputs/batch_schedule_maintenance.csv"))
    parser.add_argument("--gap-csv", type=Path, default=Path("outputs/schedule_coverage_detail_gaps_2776_kyxy_current.csv"))
    parser.add_argument("--over-csv", type=Path, default=Path("outputs/schedule_coverage_detail_overages_2776_kyxy_current.csv"))
    parser.add_argument("--target-class", action="append", default=[], help="可重复传入班级编码；默认处理本次 5 套缺口班")
    args = parser.parse_args()

    target_classes = set(args.target_class) if args.target_class else set(DEFAULT_TARGET_CLASSES)
    data_dir = args.data_dir
    output_dir = args.output_dir
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = output_dir / "backups" / f"before_public_gap_repair_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    for path in [
        args.schedule_csv,
        output_dir / "batch_schedule_maintenance.html",
        output_dir / "batch_schedule_maintenance_report.md",
        output_dir / "teacher_time_conflicts.csv",
        output_dir / "summer_camp_schedule.csv",
        output_dir / "summer_camp_schedule.html",
    ]:
        if path.exists():
            shutil.copy2(path, backup_dir / path.name)

    fieldnames, rows = load_csv_rows(args.schedule_csv)
    class_rows = {
        row["id"]: row
        for row in read_csv_rows(data_dir / "classes.csv")
        if row.get("id")
    }
    room_names = load_room_names(data_dir)
    room_names.update({row["room_id"]: row["room_name"] for row in rows if row.get("room_id") and row.get("room_name")})
    schedule_input = scheduler.load_input(data_dir / "scheduler_input_draft.json")
    requirement_lookup = build_requirement_lookup(schedule_input, target_classes)
    gap_rows = [
        row
        for row in read_csv_rows(args.gap_csv)
        if row.get("class_id") in target_classes and float(row.get("diff_hours") or 0) > 0
    ]
    over_rows = [
        row
        for row in read_csv_rows(args.over_csv)
        if row.get("class_id") in target_classes and float(row.get("diff_hours") or 0) < 0
    ]
    tasks, offset_lines = make_gap_tasks(gap_rows, over_rows, requirement_lookup, class_rows, room_names)
    blackouts = set(maintenance.load_active_blackout_dates(data_dir)) | set(maintenance.WUYOU_PRODUCT_BLACKOUT_DATES)
    context = PlacementContext(
        rows=list(rows),
        class_rows=class_rows,
        class_conflicts=make_class_conflict_index(data_dir),
        blackouts=blackouts,
        fieldnames=fieldnames,
    )

    placements: List[Tuple[dict, str, str, float]] = []
    for task in tasks:
        date_text, period, penalty = context.place(task)
        placements.append((task, date_text, period, penalty))

    repaired_rows = sort_schedule_rows(context.rows)
    write_csv_rows(args.schedule_csv, fieldnames, repaired_rows)
    write_csv_rows(output_dir / "summer_camp_schedule.csv", fieldnames, repaired_rows)
    regenerate_outputs(data_dir, output_dir, repaired_rows)
    append_report(output_dir, placements, offset_lines)

    print(f"备份目录: {backup_dir}")
    print(f"抵扣项: {len(offset_lines)}")
    print(f"补课半天: {len(placements)}")
    for task, date_text, period, _penalty in placements:
        print(f"{date_text} {period} {task['class_id']} {task['subject']}/{task['stage']}/{task['course_module']} {task['teacher_name']}")


if __name__ == "__main__":
    main()
