#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date as Date, datetime, timedelta
from pathlib import Path
from statistics import pstdev
from typing import Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.csv_utils import clean_cell as clean, read_csv_rows, write_csv_rows
from scripts.schedule_data import (
    load_area_links as load_raw_area_links,
    load_area_metadata as load_raw_area_metadata,
    load_class_metadata as load_raw_class_metadata,
    load_room_metadata as load_raw_room_metadata,
)


PUBLIC_SUBJECTS = {"英语", "政治", "数学", "语文"}
PERIOD_ORDER = {"AM": 0, "PM": 1, "EVENING": 2}
SEASONS = (
    ("summer", "暑假7-8月", "2026-07-01", "2026-08-31"),
    ("autumn", "秋季9-12月", "2026-09-01", "2026-12-13"),
)
FAR_REGION_PAIRS = {
    ("新站", "滨湖"),
    ("滨湖", "新站"),
    ("新站", "经开"),
    ("经开", "新站"),
    ("新站", "翡翠湖"),
    ("翡翠湖", "新站"),
}


@dataclass(frozen=True)
class Halfday:
    class_id: str
    class_name: str
    suite_code: str
    sub_product: str
    subject: str
    date: str
    week_start: str
    period: str
    teacher_id: str
    teacher_name: str
    room_id: str
    room_name: str
    hours: float


def week_start(date_text: str) -> str:
    day = Date.fromisoformat(date_text)
    return (day - timedelta(days=day.weekday())).isoformat()


def week_range(start: str, end: str) -> List[str]:
    first = Date.fromisoformat(week_start(start))
    last = Date.fromisoformat(week_start(end))
    weeks: List[str] = []
    current = first
    while current <= last:
        weeks.append(current.isoformat())
        current += timedelta(days=7)
    return weeks


def week_dates(week: str) -> List[str]:
    start = Date.fromisoformat(week)
    return [(start + timedelta(days=offset)).isoformat() for offset in range(7)]


def comparable_weeks(active_weeks: Sequence[str], start: str, end: str) -> List[str]:
    weeks = [
        week
        for week in active_weeks
        if sum(1 for day in week_dates(week) if start <= day <= end) >= 4
    ]
    return weeks if len(weeks) >= 3 else list(active_weeks)


def in_range(date_text: str, start: str, end: str) -> bool:
    return start <= date_text <= end


def filter_halfdays(halfdays: Sequence[Halfday], start: str = "", end: str = "") -> List[Halfday]:
    return [
        item
        for item in halfdays
        if (not start or item.date >= start) and (not end or item.date <= end)
    ]


def load_class_metadata(data_dir: Path) -> Dict[str, dict]:
    return load_raw_class_metadata(data_dir)


def load_room_metadata(data_dir: Path) -> Dict[str, dict]:
    return load_raw_room_metadata(data_dir)


def load_area_metadata(data_dir: Path) -> Dict[str, dict]:
    return load_raw_area_metadata(data_dir)


def load_area_links(data_dir: Path) -> Dict[Tuple[str, str], dict]:
    return load_raw_area_links(data_dir)


def load_schedule_halfdays(schedule_csv: Path, class_meta: Dict[str, dict]) -> List[Halfday]:
    rows = read_csv_rows(schedule_csv)
    grouped: Dict[Tuple[str, str, str, str, str, str, str, str], dict] = {}
    for row in rows:
        class_id = clean(row.get("class_id"))
        subject = clean(row.get("subject"))
        date_text = clean(row.get("date"))
        period = clean(row.get("period"))
        if subject not in PUBLIC_SUBJECTS or not class_id or not date_text or not period:
            continue
        meta = class_meta.get(class_id, {})
        key = (
            class_id,
            date_text,
            period,
            subject,
            clean(row.get("teacher_id")),
            clean(row.get("teacher_name")),
            clean(row.get("room_id")),
            clean(row.get("course_code")),
        )
        item = grouped.setdefault(
            key,
            {
                "class_id": class_id,
                "class_name": clean(row.get("class_name")) or clean(meta.get("name")) or class_id,
                "suite_code": clean(meta.get("suite_code")),
                "sub_product": clean(meta.get("sub_product")),
                "subject": subject,
                "date": date_text,
                "period": period,
                "teacher_id": clean(row.get("teacher_id")),
                "teacher_name": clean(row.get("teacher_name")),
                "room_id": clean(row.get("room_id")),
                "room_name": clean(row.get("room_name")),
                "hours": 0.0,
            },
        )
        try:
            item["hours"] += float(row.get("duration_hours") or 0)
        except ValueError:
            pass
    halfdays: List[Halfday] = []
    for item in grouped.values():
        date_text = item["date"]
        halfdays.append(
            Halfday(
                class_id=item["class_id"],
                class_name=item["class_name"],
                suite_code=item["suite_code"],
                sub_product=item["sub_product"],
                subject=item["subject"],
                date=date_text,
                week_start=week_start(date_text),
                period=item["period"],
                teacher_id=item["teacher_id"],
                teacher_name=item["teacher_name"],
                room_id=item["room_id"],
                room_name=item["room_name"],
                hours=item["hours"],
            )
        )
    return halfdays


def add_issue(
    issues: List[dict],
    *,
    severity: str,
    issue_type: str,
    scope_type: str,
    scope_id: str,
    scope_name: str = "",
    sub_product: str = "",
    subject: str = "",
    week_start_text: str = "",
    date_text: str = "",
    period: str = "",
    teacher_name: str = "",
    metric: str = "",
    detail: str = "",
) -> None:
    issues.append(
        {
            "severity": severity,
            "issue_type": issue_type,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "scope_name": scope_name,
            "sub_product": sub_product,
            "subject": subject,
            "week_start": week_start_text,
            "date": date_text,
            "period": period,
            "teacher_name": teacher_name,
            "metric": metric,
            "detail": detail,
        }
    )


def audit_week_balance(halfdays: Sequence[Halfday], issues: List[dict]) -> None:
    by_suite_season: Dict[Tuple[str, str], List[Halfday]] = defaultdict(list)
    for item in halfdays:
        if not item.suite_code:
            continue
        for season_id, _label, start, end in SEASONS:
            if in_range(item.date, start, end):
                by_suite_season[(item.suite_code, season_id)].append(item)

    for (suite_code, season_id), items in sorted(by_suite_season.items()):
        if not items:
            continue
        season_label = next(label for sid, label, _start, _end in SEASONS if sid == season_id)
        season_start = min(item.date for item in items)
        season_end = max(item.date for item in items)
        active_weeks = week_range(season_start, season_end)
        balanced_weeks = comparable_weeks(active_weeks, season_start, season_end)
        sub_product = next((item.sub_product for item in items if item.sub_product), "")
        subjects = sorted({item.subject for item in items})
        week_total: Counter[str] = Counter()
        subject_week_total: Counter[Tuple[str, str]] = Counter()
        seen_total_keys = set()
        seen_subject_keys = set()
        for item in items:
            total_key = (item.date, item.period, item.subject, item.class_id)
            if total_key not in seen_total_keys:
                week_total[item.week_start] += 1
                seen_total_keys.add(total_key)
            subject_key = (item.subject, item.date, item.period, item.class_id)
            if subject_key not in seen_subject_keys:
                subject_week_total[(item.subject, item.week_start)] += 1
                seen_subject_keys.add(subject_key)

        totals = [week_total.get(week, 0) for week in balanced_weeks]
        if any(value == 0 for value in totals) and len(balanced_weeks) >= 3:
            for week, value in zip(balanced_weeks, totals):
                if value == 0:
                    add_issue(
                        issues,
                        severity="medium",
                        issue_type="empty_active_week",
                        scope_type="suite",
                        scope_id=suite_code,
                        sub_product=sub_product,
                        week_start_text=week,
                        metric="0",
                        detail=f"{season_label} 首末课之间这一周没有公共课，学生节奏会断档",
                    )

        if totals and max(totals) - min(totals) >= 4:
            severity = "high" if max(totals) - min(totals) >= 6 else "medium"
            add_issue(
                issues,
                severity=severity,
                issue_type="weekly_total_imbalance",
                scope_type="suite",
                scope_id=suite_code,
                sub_product=sub_product,
                metric=f"max={max(totals)},min={min(totals)},stdev={pstdev(totals):.2f}",
                detail=f"{season_label} 每周公共课总半天数不均衡：{dict(zip(balanced_weeks, totals))}",
            )

        for subject in subjects:
            values = [subject_week_total.get((subject, week), 0) for week in balanced_weeks]
            if len(values) >= 3 and any(value == 0 for value in values) and sum(values) >= len(balanced_weeks):
                zero_weeks = [week for week, value in zip(balanced_weeks, values) if value == 0]
                add_issue(
                    issues,
                    severity="medium",
                    issue_type="subject_missing_week",
                    scope_type="suite",
                    scope_id=suite_code,
                    sub_product=sub_product,
                    subject=subject,
                    week_start_text="|".join(zero_weeks[:6]),
                    metric=f"zero_weeks={len(zero_weeks)}",
                    detail=f"{season_label} {subject} 在部分周没有课，需判断是否阶段结束或排课过于集中",
                )
            if values and max(values) - min(values) >= 3:
                severity = "high" if max(values) - min(values) >= 5 else "medium"
                add_issue(
                    issues,
                    severity=severity,
                    issue_type="subject_weekly_imbalance",
                    scope_type="suite",
                    scope_id=suite_code,
                    sub_product=sub_product,
                    subject=subject,
                    metric=f"max={max(values)},min={min(values)},stdev={pstdev(values):.2f}",
                    detail=f"{season_label} {subject} 每周半天数不均衡：{dict(zip(balanced_weeks, values))}",
                )


def audit_same_day_load(halfdays: Sequence[Halfday], issues: List[dict]) -> None:
    by_class_subject_day: Dict[Tuple[str, str, str], List[Halfday]] = defaultdict(list)
    by_class_subject_teacher_day: Dict[Tuple[str, str, str, str], List[Halfday]] = defaultdict(list)
    for item in halfdays:
        by_class_subject_day[(item.class_id, item.subject, item.date)].append(item)
        if item.teacher_name:
            by_class_subject_teacher_day[(item.class_id, item.subject, item.teacher_name, item.date)].append(item)

    for (class_id, subject, date_text), items in sorted(by_class_subject_day.items()):
        hours = sum(item.hours for item in items)
        if hours >= 8:
            first = items[0]
            add_issue(
                issues,
                severity="medium",
                issue_type="same_class_subject_8h_day",
                scope_type="class",
                scope_id=class_id,
                scope_name=first.class_name,
                sub_product=first.sub_product,
                subject=subject,
                date_text=date_text,
                metric=f"{hours:g}h",
                detail="同一班级同一科目当天达到 8 小时，学生疲劳度较高，建议拆散",
            )

    for (class_id, subject, teacher_name, date_text), items in sorted(by_class_subject_teacher_day.items()):
        hours = sum(item.hours for item in items)
        if hours >= 8:
            first = items[0]
            add_issue(
                issues,
                severity="high",
                issue_type="same_class_subject_teacher_8h_day",
                scope_type="class",
                scope_id=class_id,
                scope_name=first.class_name,
                sub_product=first.sub_product,
                subject=subject,
                date_text=date_text,
                teacher_name=teacher_name,
                metric=f"{hours:g}h",
                detail="同一班级同一科目同一老师当天达到 8 小时，优先微调",
            )


def audit_english_politics_same_day(halfdays: Sequence[Halfday], issues: List[dict]) -> None:
    suite_subjects: Dict[Tuple[str, str], set[str]] = defaultdict(set)
    for item in halfdays:
        if item.sub_product in {"全年营", "半年营"} and item.subject in PUBLIC_SUBJECTS and item.suite_code:
            suite_subjects[(item.suite_code, item.sub_product)].add(item.subject)

    target_suites = {
        (suite_code, sub_product)
        for (suite_code, sub_product), subjects in suite_subjects.items()
        if "英语" in subjects and "政治" in subjects and "数学" not in subjects
    }
    if not target_suites:
        return

    by_suite_date: Dict[Tuple[str, str], List[Halfday]] = defaultdict(list)
    seen = set()
    for item in halfdays:
        if (item.suite_code, item.sub_product) not in target_suites:
            continue
        if item.subject not in {"英语", "政治"}:
            continue
        key = (item.suite_code, item.date, item.period, item.class_id, item.subject)
        if key in seen:
            continue
        seen.add(key)
        by_suite_date[(item.suite_code, item.date)].append(item)

    for (suite_code, date_text), items in sorted(by_suite_date.items()):
        subjects = {item.subject for item in items}
        if not {"英语", "政治"}.issubset(subjects):
            continue
        first = items[0]
        detail_parts = [
            f"{item.period}:{item.class_id}{item.subject}"
            for item in sorted(items, key=lambda value: (PERIOD_ORDER.get(value.period, 9), value.class_id, value.subject))
        ]
        add_issue(
            issues,
            severity="medium",
            issue_type="english_politics_same_day",
            scope_type="suite",
            scope_id=suite_code,
            sub_product=first.sub_product,
            subject="英语+政治",
            date_text=date_text,
            metric="same_day",
            detail="全年营/半年营英政班同一天同时安排英语和政治，尽量拆到不同日期；" + "，".join(detail_parts),
        )


def audit_teacher_consecutive_days(halfdays: Sequence[Halfday], issues: List[dict]) -> None:
    by_teacher_class_subject: Dict[Tuple[str, str, str], set[str]] = defaultdict(set)
    for item in halfdays:
        teacher = item.teacher_name or item.teacher_id
        if teacher:
            by_teacher_class_subject[(teacher, item.class_id, item.subject)].add(item.date)

    for (teacher, class_id, subject), raw_dates in sorted(by_teacher_class_subject.items()):
        dates = sorted(Date.fromisoformat(value) for value in raw_dates)
        if not dates:
            continue
        streak = [dates[0]]
        for day in dates[1:]:
            if (day - streak[-1]).days == 1:
                streak.append(day)
            else:
                if len(streak) > 3:
                    add_issue(
                        issues,
                        severity="medium",
                        issue_type="teacher_consecutive_days",
                        scope_type="class",
                        scope_id=class_id,
                        subject=subject,
                        teacher_name=teacher,
                        date_text=f"{streak[0].isoformat()}~{streak[-1].isoformat()}",
                        metric=f"{len(streak)} days",
                        detail="同一班同一科目同一老师连续上课超过 3 天，建议交替或拆散",
                    )
                streak = [day]
        if len(streak) > 3:
            add_issue(
                issues,
                severity="medium",
                issue_type="teacher_consecutive_days",
                scope_type="class",
                scope_id=class_id,
                subject=subject,
                teacher_name=teacher,
                date_text=f"{streak[0].isoformat()}~{streak[-1].isoformat()}",
                metric=f"{len(streak)} days",
                detail="同一班同一科目同一老师连续上课超过 3 天，建议交替或拆散",
            )


def audit_teacher_travel(
    halfdays: Sequence[Halfday],
    room_meta: Dict[str, dict],
    area_meta: Dict[str, dict],
    area_links: Dict[Tuple[str, str], dict],
    issues: List[dict],
) -> None:
    by_teacher_day: Dict[Tuple[str, str], List[Halfday]] = defaultdict(list)
    seen = set()
    for item in halfdays:
        teacher = item.teacher_name or item.teacher_id
        if not teacher or not item.room_id:
            continue
        key = (teacher, item.date, item.period, item.room_id)
        if key in seen:
            continue
        seen.add(key)
        by_teacher_day[(teacher, item.date)].append(item)

    for (teacher, date_text), items in sorted(by_teacher_day.items()):
        items = sorted(items, key=lambda item: (PERIOD_ORDER.get(item.period, 9), item.room_id))
        for left, right in zip(items, items[1:]):
            if left.period == right.period:
                continue
            left_area_id = clean(room_meta.get(left.room_id, {}).get("teaching_area_id"))
            right_area_id = clean(room_meta.get(right.room_id, {}).get("teaching_area_id"))
            if not left_area_id or not right_area_id or left_area_id == right_area_id:
                continue
            left_area = area_meta.get(left_area_id, {})
            right_area = area_meta.get(right_area_id, {})
            left_region = clean(left_area.get("region_tag"))
            right_region = clean(right_area.get("region_tag"))
            link = area_links.get((left_area_id, right_area_id), {})
            relation = clean(link.get("relation_type"))
            try:
                minutes = float(clean(link.get("travel_minutes")) or 0)
            except ValueError:
                minutes = 0
            if (left_region, right_region) in FAR_REGION_PAIRS or "不建议" in relation or minutes >= 35:
                severity = "high"
            elif left_region and right_region and left_region != right_region:
                severity = "medium"
            else:
                severity = "low"
            add_issue(
                issues,
                severity=severity,
                issue_type="teacher_same_day_cross_area",
                scope_type="teacher",
                scope_id=teacher,
                scope_name=teacher,
                date_text=date_text,
                period=f"{left.period}->{right.period}",
                teacher_name=teacher,
                metric=f"{minutes:g}min",
                detail=(
                    f"{left.room_name or left.room_id}({left_region or left_area_id}) -> "
                    f"{right.room_name or right.room_id}({right_region or right_area_id})；{relation or '未标注'}"
                ),
            )


def score_rows(issues: Sequence[dict]) -> List[dict]:
    penalty = {"high": 12, "medium": 6, "low": 3}
    grouped: Dict[Tuple[str, str], List[dict]] = defaultdict(list)
    for issue in issues:
        grouped[(issue["scope_type"], issue["scope_id"])].append(issue)
    rows: List[dict] = []
    for (scope_type, scope_id), items in sorted(grouped.items()):
        issue_counts = Counter(item["severity"] for item in items)
        score = max(0, 100 - sum(penalty.get(item["severity"], 0) for item in items))
        rows.append(
            {
                "scope_type": scope_type,
                "scope_id": scope_id,
                "score": score,
                "high": issue_counts.get("high", 0),
                "medium": issue_counts.get("medium", 0),
                "low": issue_counts.get("low", 0),
                "issue_count": len(items),
            }
        )
    return sorted(rows, key=lambda row: (int(row["score"]), -int(row["high"]), -int(row["medium"]), row["scope_type"], row["scope_id"]))


def write_report(path: Path, issues: Sequence[dict], scores: Sequence[dict], timestamp: str) -> None:
    counts = Counter(issue["issue_type"] for issue in issues)
    severity_counts = Counter(issue["severity"] for issue in issues)
    lines = [
        f"# 排课质量审计报告 {timestamp}",
        "",
        "本报告用于发现课表舒适度和老师移动体验问题，不代表硬冲突。硬冲突仍以老师/教室/互斥冲突校验为准。",
        "",
        "## 总览",
        f"- 问题总数：{len(issues)}",
        f"- 高优先级：{severity_counts.get('high', 0)}",
        f"- 中优先级：{severity_counts.get('medium', 0)}",
        f"- 低优先级：{severity_counts.get('low', 0)}",
        "",
        "## 问题类型",
    ]
    for issue_type, count in counts.most_common():
        lines.append(f"- {issue_type}: {count}")
    lines.extend(["", "## 低分对象 Top 30"])
    for row in scores[:30]:
        lines.append(
            f"- {row['scope_type']} {row['scope_id']}: {row['score']} 分，"
            f"high={row['high']} medium={row['medium']} low={row['low']}"
        )
    lines.extend(["", "## 高优先级问题 Top 40"])
    for issue in [item for item in issues if item["severity"] == "high"][:40]:
        lines.append(
            f"- {issue['issue_type']} | {issue['scope_type']} {issue['scope_id']} | "
            f"{issue.get('date') or issue.get('week_start')} | {issue.get('subject')} | "
            f"{issue.get('teacher_name')} | {issue.get('detail')}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="审计公共课排课质量：周均衡、同日负载、老师跨校区移动")
    parser.add_argument("--schedule-csv", default="outputs/batch_schedule_maintenance.csv")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--out-dir", default="outputs")
    parser.add_argument("--timestamp", default="")
    parser.add_argument("--date-start", default="", help="只审计不早于该日期的课表，例如 2026-06-25")
    parser.add_argument("--date-end", default="", help="只审计不晚于该日期的课表，例如 2026-12-13")
    args = parser.parse_args()

    timestamp = args.timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    data_dir = Path(args.data_dir)
    out_dir = Path(args.out_dir)
    class_meta = load_class_metadata(data_dir)
    room_meta = load_room_metadata(data_dir)
    area_meta = load_area_metadata(data_dir)
    area_links = load_area_links(data_dir)
    halfdays = filter_halfdays(load_schedule_halfdays(Path(args.schedule_csv), class_meta), args.date_start, args.date_end)

    issues: List[dict] = []
    audit_week_balance(halfdays, issues)
    audit_same_day_load(halfdays, issues)
    audit_english_politics_same_day(halfdays, issues)
    audit_teacher_consecutive_days(halfdays, issues)
    audit_teacher_travel(halfdays, room_meta, area_meta, area_links, issues)
    issues.sort(
        key=lambda row: (
            {"high": 0, "medium": 1, "low": 2}.get(row["severity"], 9),
            row["issue_type"],
            row["scope_type"],
            row["scope_id"],
            row["date"],
            row["week_start"],
        )
    )
    scores = score_rows(issues)

    issues_path = out_dir / f"schedule_quality_issues_{timestamp}.csv"
    scores_path = out_dir / f"schedule_quality_scores_{timestamp}.csv"
    report_path = out_dir / f"schedule_quality_report_{timestamp}.md"
    write_csv_rows(
        issues_path,
        [
            "severity",
            "issue_type",
            "scope_type",
            "scope_id",
            "scope_name",
            "sub_product",
            "subject",
            "week_start",
            "date",
            "period",
            "teacher_name",
            "metric",
            "detail",
        ],
        issues,
    )
    write_csv_rows(
        scores_path,
        ["scope_type", "scope_id", "score", "high", "medium", "low", "issue_count"],
        scores,
    )
    write_report(report_path, issues, scores, timestamp)
    print(report_path)
    print(issues_path)
    print(scores_path)


if __name__ == "__main__":
    main()
