#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Set


DEFAULT_DAY_SLOTS = [
    {
        "period": "AM",
        "name": "上午一",
        "order": 1,
        "start_time": "08:00",
        "end_time": "10:00",
        "duration_hours": 2,
    },
    {
        "period": "AM",
        "name": "上午二",
        "order": 2,
        "start_time": "10:20",
        "end_time": "12:20",
        "duration_hours": 2,
    },
    {
        "period": "PM",
        "name": "下午一",
        "order": 1,
        "start_time": "14:00",
        "end_time": "16:00",
        "duration_hours": 2,
    },
    {
        "period": "PM",
        "name": "下午二",
        "order": 2,
        "start_time": "16:20",
        "end_time": "18:20",
        "duration_hours": 2,
    },
    {
        "period": "EVENING",
        "name": "晚上",
        "order": 1,
        "start_time": "19:00",
        "end_time": "21:00",
        "duration_hours": 2,
    },
]

WEEKDAY_ALIASES = {
    "MON": 0,
    "MONDAY": 0,
    "周一": 0,
    "星期一": 0,
    "TUE": 1,
    "TUESDAY": 1,
    "周二": 1,
    "星期二": 1,
    "WED": 2,
    "WEDNESDAY": 2,
    "周三": 2,
    "星期三": 2,
    "THU": 3,
    "THURSDAY": 3,
    "周四": 3,
    "星期四": 3,
    "FRI": 4,
    "FRIDAY": 4,
    "周五": 4,
    "星期五": 4,
    "SAT": 5,
    "SATURDAY": 5,
    "周六": 5,
    "星期六": 5,
    "SUN": 6,
    "SUNDAY": 6,
    "周日": 6,
    "周天": 6,
    "星期日": 6,
    "星期天": 6,
}


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def parse_weekdays(values: str) -> Set[int]:
    weekdays: Set[int] = set()
    for value in values.split(","):
        key = value.strip().upper()
        if not key:
            continue
        if key not in WEEKDAY_ALIASES:
            raise ValueError(f"不支持的星期: {value}")
        weekdays.add(WEEKDAY_ALIASES[key])
    return weekdays


def slot_allowed(slot: dict, slot_set: str) -> bool:
    if slot_set == "all":
        return True
    if slot_set == "day":
        return slot["period"] in {"AM", "PM"}
    if slot_set == "evening":
        return slot["period"] == "EVENING"
    raise ValueError("--slot-set 只能是 all、day 或 evening")


def should_exclude_day(current: date, excluded_weekdays: Set[int], sunday_policy: str) -> bool:
    weekday = current.weekday()
    if weekday not in excluded_weekdays:
        return False
    if sunday_policy == "summer-only" and weekday == WEEKDAY_ALIASES["SUN"]:
        return current.month in {7, 8}
    return True


def generate_time_slots(
    start: date,
    end: date,
    excluded_weekdays: Set[int],
    slot_set: str,
    sunday_policy: str = "always",
) -> List[dict]:
    if end < start:
        raise ValueError("结束日期不能早于开始日期")
    if sunday_policy not in {"always", "summer-only"}:
        raise ValueError("sunday_policy 只能是 always 或 summer-only")

    slots: List[dict] = []
    current = start
    while current <= end:
        if not should_exclude_day(current, excluded_weekdays, sunday_policy):
            date_text = current.isoformat()
            for slot in DEFAULT_DAY_SLOTS:
                if not slot_allowed(slot, slot_set):
                    continue
                slots.append(
                    {
                        "id": f"{date_text}-{slot['period']}-{slot['order']}",
                        "date": date_text,
                        **slot,
                    }
                )
        current += timedelta(days=1)

    return slots


def main() -> None:
    parser = argparse.ArgumentParser(description="生成排课课节，默认包含白天 4 个课节和晚上 19:00-21:00。")
    parser.add_argument("--start", required=True, help="开始日期，格式 YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="结束日期，格式 YYYY-MM-DD")
    parser.add_argument("--output", required=True, type=Path, help="输出 JSON 文件")
    parser.add_argument(
        "--exclude-weekdays",
        default="Sun",
        help="排除星期，用逗号分隔，例如 Sun 或 Mon,Sun。留空表示不排除。",
    )
    parser.add_argument(
        "--slot-set",
        choices=["all", "day", "evening"],
        default="all",
        help="生成课节范围：all=白天+晚上，day=仅白天，evening=仅晚上。",
    )
    parser.add_argument(
        "--sunday-policy",
        choices=["always", "summer-only"],
        default="always",
        help="当 --exclude-weekdays 包含 Sun 时的处理：always=全程排除周日，summer-only=仅 7-8 月排除周日。",
    )
    args = parser.parse_args()

    excluded_weekdays = parse_weekdays(args.exclude_weekdays)
    slots = generate_time_slots(
        parse_date(args.start),
        parse_date(args.end),
        excluded_weekdays,
        args.slot_set,
        args.sunday_policy,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps({"time_slots": slots}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    days = len({slot["date"] for slot in slots})
    print(f"已生成 {days} 个可排课日期、{len(slots)} 个课节: {args.output}")


if __name__ == "__main__":
    main()
