#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import shutil
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import date as Date, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_camp_maintenance_schedule import (  # noqa: E402
    assignments_from_rows,
    load_all_class_window_constraint_items,
    load_class_metadata,
)
from scripts.csv_utils import clean_cell as clean, read_csv_rows, write_csv_rows  # noqa: E402
from scripts.schedule_conflicts import write_teacher_time_conflicts_csv  # noqa: E402
from scripts.schedule_data import load_room_name_to_id, load_room_names, load_teacher_name_to_id  # noqa: E402
from scripts.schedule_modes import assignment_is_shared, assignment_reference_class_id  # noqa: E402
from scripts.schedule_outputs import write_day_table_html  # noqa: E402


FIELDNAMES = [
    "date",
    "weekday",
    "period",
    "lesson_slot",
    "slot_label",
    "start_time",
    "end_time",
    "class_id",
    "class_name",
    "subject",
    "quarter",
    "stage",
    "course_module",
    "course_group",
    "course_code",
    "course_name",
    "teacher_id",
    "teacher_name",
    "room_id",
    "room_name",
    "duration_hours",
]

TIME_SLOT_MAP = {
    ("08:00", "10:00"): ("AM", "AM1", "上午一"),
    ("10:20", "12:20"): ("AM", "AM2", "上午二"),
    ("14:00", "16:00"): ("PM", "PM1", "下午一"),
    ("16:20", "18:20"): ("PM", "PM2", "下午二"),
    ("19:00", "21:00"): ("EVENING", "EVENING1", "晚上一"),
}

WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
PERIOD_ORDER = {"AM": 0, "PM": 1, "EVENING": 2}


def normalize_date(value: object) -> str:
    text = clean(value)
    if not text:
        return ""
    if " " in text:
        text = text.split(" ", 1)[0]
    if "/" in text:
        year, month, day = text.split("/")[:3]
        return Date(int(year), int(month), int(day)).isoformat()
    return Date.fromisoformat(text).isoformat()


def weekday_label(date_text: str) -> str:
    return WEEKDAYS[Date.fromisoformat(date_text).weekday()]


def parse_time_range(value: object) -> Tuple[str, str]:
    text = clean(value).replace("－", "~").replace("-", "~")
    if "~" not in text:
        return "", ""
    start, end = [part.strip() for part in text.split("~", 1)]
    return start[:5], end[:5]


def period_for_time(start_time: str, end_time: str) -> Tuple[str, str, str]:
    mapped = TIME_SLOT_MAP.get((start_time, end_time))
    if mapped:
        return mapped
    hour = int((start_time or "00:00").split(":", 1)[0])
    if hour < 13:
        return "AM", f"AM-{start_time}-{end_time}", "上午"
    if hour < 18:
        return "PM", f"PM-{start_time}-{end_time}", "下午"
    return "EVENING", f"EVENING-{start_time}-{end_time}", "晚上"


def cell_ref_to_index(ref: str) -> int:
    letters = "".join(char for char in ref if char.isalpha())
    value = 0
    for char in letters:
        value = value * 26 + (ord(char.upper()) - ord("A") + 1)
    return value - 1


def read_shared_strings(zf: zipfile.ZipFile) -> List[str]:
    try:
        xml = zf.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ET.fromstring(xml)
    ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    strings: List[str] = []
    for item in root.findall("a:si", ns):
        texts = [node.text or "" for node in item.findall(".//a:t", ns)]
        strings.append("".join(texts))
    return strings


def read_first_sheet_rows(xlsx_path: Path) -> List[List[str]]:
    ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(xlsx_path) as zf:
        shared_strings = read_shared_strings(zf)
        sheet_names = sorted(
            name
            for name in zf.namelist()
            if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")
        )
        if not sheet_names:
            raise ValueError(f"Excel 文件没有 worksheet: {xlsx_path}")
        root = ET.fromstring(zf.read(sheet_names[0]))

    rows: List[List[str]] = []
    for row_node in root.findall(".//a:sheetData/a:row", ns):
        values: Dict[int, str] = {}
        max_index = -1
        for cell in row_node.findall("a:c", ns):
            ref = cell.attrib.get("r", "")
            index = cell_ref_to_index(ref) if ref else max_index + 1
            max_index = max(max_index, index)
            cell_type = cell.attrib.get("t", "")
            value_node = cell.find("a:v", ns)
            inline_node = cell.find("a:is/a:t", ns)
            if cell_type == "inlineStr":
                value = inline_node.text if inline_node is not None else ""
            elif value_node is None:
                value = ""
            elif cell_type == "s":
                raw = value_node.text or ""
                value = shared_strings[int(raw)] if raw.isdigit() and int(raw) < len(shared_strings) else raw
            else:
                value = value_node.text or ""
            values[index] = html.unescape(value or "").strip()
        if max_index >= 0:
            rows.append([values.get(index, "") for index in range(max_index + 1)])
    return rows


def read_erp_rows(xlsx_path: Path) -> List[dict]:
    raw_rows = read_first_sheet_rows(xlsx_path)
    header_index = None
    for index, row in enumerate(raw_rows):
        if "课次ID" in row and "班级编码" in row and "日期" in row:
            header_index = index
            break
    if header_index is None:
        raise ValueError(f"找不到 ERP 课次表头: {xlsx_path}")
    headers = raw_rows[header_index]
    rows: List[dict] = []
    for raw in raw_rows[header_index + 1 :]:
        if not any(clean(cell) for cell in raw):
            continue
        row = {header: clean(raw[pos]) if pos < len(raw) else "" for pos, header in enumerate(headers)}
        if clean(row.get("班级编码")):
            rows.append(row)
    return rows


def load_product_course_lookups(data_dir: Path) -> Tuple[Dict[Tuple[str, str], dict], Dict[str, List[dict]]]:
    by_product_code: Dict[Tuple[str, str], dict] = {}
    by_code: Dict[str, List[dict]] = defaultdict(list)
    for row in read_csv_rows(data_dir / "product_courses.csv"):
        product_id = clean(row.get("product_id"))
        course_code = clean(row.get("course_code"))
        if not course_code:
            continue
        by_product_code.setdefault((product_id, course_code), row)
        by_code[course_code].append(row)
    return by_product_code, by_code


def load_inherit_lookup(data_dir: Path) -> Dict[Tuple[str, str], List[str]]:
    lookup: Dict[Tuple[str, str], List[str]] = defaultdict(list)
    path = data_dir / "class_teacher_assignments.csv"
    if not path.exists():
        return {}
    for row in read_csv_rows(path):
        class_id = clean(row.get("class_id"))
        subject = clean(row.get("subject"))
        reference_class_id = assignment_reference_class_id(row)
        if class_id and subject and reference_class_id and assignment_is_shared(row, class_id=class_id):
            lookup[(class_id, subject)].append(reference_class_id)
    return lookup


def course_detail_for_code(
    product_id: str,
    course_code: str,
    by_product_code: Dict[Tuple[str, str], dict],
    by_code: Dict[str, List[dict]],
) -> dict:
    if not course_code:
        return {}
    exact = by_product_code.get((product_id, course_code))
    if exact:
        return exact
    candidates = by_code.get(course_code) or []
    return candidates[0] if candidates else {}


def should_include_erp_row(row: dict, current_class_ids: set[str], start_date: str, end_date: str) -> bool:
    class_id = clean(row.get("班级编码"))
    if class_id not in current_class_ids:
        return False
    if clean(row.get("授课内容类型")) != "正课":
        return False
    try:
        duration_minutes = float(clean(row.get("分钟数")) or 0)
    except ValueError:
        return False
    if int(duration_minutes) != 120:
        return False
    date_text = normalize_date(row.get("日期"))
    if date_text < start_date or date_text > end_date:
        return False
    course_subject = clean(row.get("课程科目"))
    course_code = clean(row.get("实际课程编码")) or clean(row.get("课程编码"))
    if course_subject == "不区分" or course_code == "CSHFWY000300158":
        return False
    return True


def build_normalized_rows(
    erp_rows: Sequence[dict],
    current_rows: Sequence[dict],
    current_class_ids: set[str],
    data_dir: Path,
    start_date: str,
    end_date: str,
) -> Tuple[List[dict], List[dict], Counter[str]]:
    class_meta = load_class_metadata(data_dir)
    teacher_by_name = load_teacher_name_to_id(data_dir)
    room_by_name = load_room_name_to_id(data_dir)
    by_product_code, by_code = load_product_course_lookups(data_dir)
    inherit_lookup = load_inherit_lookup(data_dir)
    current_by_exact_slot = {
        (
            clean(row.get("class_id")),
            clean(row.get("date")),
            clean(row.get("start_time")),
            clean(row.get("end_time")),
        ): row
        for row in current_rows
    }

    included_rows = [
        row for row in erp_rows if should_include_erp_row(row, current_class_ids, start_date, end_date)
    ]
    normalized: List[dict] = []
    issues: List[dict] = []
    counters: Counter[str] = Counter()

    for row in included_rows:
        class_id = clean(row.get("班级编码"))
        date_text = normalize_date(row.get("日期"))
        start_time, end_time = parse_time_range(row.get("时间"))
        period, lesson_slot, slot_label = period_for_time(start_time, end_time)
        meta = class_meta.get(class_id, {})
        course_code = clean(row.get("实际课程编码")) or clean(row.get("课程编码"))
        course_name = clean(row.get("实际课程名称")) or clean(row.get("课程"))
        course_detail = course_detail_for_code(
            clean(meta.get("product_id")),
            course_code,
            by_product_code,
            by_code,
        )
        teacher_name = clean(row.get("实际教师1")) or clean(row.get("教师1"))
        teacher_id = teacher_by_name.get(teacher_name, "") if teacher_name else ""
        if teacher_name and not teacher_id:
            counters[f"unmapped_teacher:{teacher_name}"] += 1
            issues.append(
                {
                    "issue_type": "teacher_id_unmapped",
                    "class_id": class_id,
                    "date": date_text,
                    "time": clean(row.get("时间")),
                    "name": teacher_name,
                    "detail": "教师姓名未在 data/teachers.csv 中匹配到 6 位员工 ID，已保留教师姓名并置空 teacher_id",
                }
            )

        room_name = clean(row.get("实际教室名称")) or clean(row.get("教室名称"))
        room_id = room_by_name.get(room_name, "") if room_name else ""
        if room_name and not room_id:
            counters[f"unmapped_room:{room_name}"] += 1
            issues.append(
                {
                    "issue_type": "room_id_unmapped",
                    "class_id": class_id,
                    "date": date_text,
                    "time": clean(row.get("时间")),
                    "name": room_name,
                    "detail": "教室名称未在 data/rooms.csv 中匹配到教室 ID",
                }
            )

        normalized.append(
            {
                "date": date_text,
                "weekday": weekday_label(date_text),
                "period": period,
                "lesson_slot": lesson_slot,
                "slot_label": slot_label,
                "start_time": start_time,
                "end_time": end_time,
                "class_id": class_id,
                "class_name": clean(meta.get("name")) or clean(row.get("班级名称")) or class_id,
                "subject": clean(meta.get("subject")) or clean(row.get("课程科目")),
                "quarter": clean(course_detail.get("quarter")),
                "stage": clean(course_detail.get("stage")),
                "course_module": clean(course_detail.get("course_module")),
                "course_group": clean(course_detail.get("course_group")),
                "course_code": course_code,
                "course_name": course_name,
                "teacher_id": teacher_id,
                "teacher_name": teacher_name,
                "room_id": room_id,
                "room_name": room_name,
                "duration_hours": "2",
            }
        )

    fill_shared_rows_from_donors(normalized, current_by_exact_slot, inherit_lookup, issues, counters)
    return normalized, issues, counters


def fill_shared_rows_from_donors(
    rows: List[dict],
    current_by_exact_slot: Dict[Tuple[str, str, str, str], dict],
    inherit_lookup: Dict[Tuple[str, str], List[str]],
    issues: List[dict],
    counters: Counter[str],
) -> None:
    donor_by_date_time_subject: Dict[Tuple[str, str, str, str], List[dict]] = defaultdict(list)
    for row in rows:
        if row.get("course_code") or row.get("teacher_name") or row.get("room_name"):
            donor_by_date_time_subject[
                (row["date"], row["start_time"], row["end_time"], clean(row.get("subject")))
            ].append(row)

    fill_fields = [
        "quarter",
        "stage",
        "course_module",
        "course_group",
        "course_code",
        "course_name",
        "teacher_id",
        "teacher_name",
        "room_id",
        "room_name",
    ]
    for row in rows:
        if row.get("course_code") or row.get("teacher_name") or row.get("room_name"):
            continue
        subject = clean(row.get("subject"))
        donors = donor_by_date_time_subject.get((row["date"], row["start_time"], row["end_time"], subject), [])
        inherit_from_ids = set(inherit_lookup.get((row["class_id"], subject), []))
        donor: Optional[dict] = None
        if inherit_from_ids:
            donor = next((item for item in donors if item["class_id"] in inherit_from_ids), None)
        if donor is None and len(donors) == 1:
            donor = donors[0]
        if donor is not None:
            for field in fill_fields:
                row[field] = donor.get(field, "")
            counters["shared_rows_filled_from_erp_donor"] += 1
            continue

        current = current_by_exact_slot.get((row["class_id"], row["date"], row["start_time"], row["end_time"]))
        if current:
            for field in fill_fields:
                row[field] = current.get(field, "")
            counters["shared_rows_filled_from_previous_schedule"] += 1
            continue

        counters["unresolved_shared_row"] += 1
        issues.append(
            {
                "issue_type": "shared_row_unresolved",
                "class_id": row["class_id"],
                "date": row["date"],
                "time": f"{row['start_time']}~{row['end_time']}",
                "name": "",
                "detail": "ERP 从班空课程/教师/教室行未找到同时间主班 donor，需人工核对",
            }
        )


def row_key(row: dict) -> Tuple[str, str, str, str]:
    return (
        clean(row.get("class_id")),
        clean(row.get("date")),
        clean(row.get("start_time")),
        clean(row.get("end_time")),
    )


def detailed_key(row: dict) -> Tuple[str, str, str, str, str, str, str, str]:
    return (
        *row_key(row),
        clean(row.get("course_code")),
        clean(row.get("teacher_name")),
        clean(row.get("room_name")),
        clean(row.get("course_name")),
    )


def changed_rows(previous: Sequence[dict], normalized: Sequence[dict], start_date: str, end_date: str) -> List[dict]:
    previous_in_range = [row for row in previous if start_date <= clean(row.get("date")) <= end_date]
    prev_keys = Counter(row_key(row) for row in previous_in_range)
    new_keys = Counter(row_key(row) for row in normalized)
    rows: List[dict] = []
    for key, count in sorted((prev_keys - new_keys).items()):
        for _ in range(count):
            rows.append({"change_type": "previous_only_slot", "class_id": key[0], "date": key[1], "start_time": key[2], "end_time": key[3]})
    for key, count in sorted((new_keys - prev_keys).items()):
        for _ in range(count):
            rows.append({"change_type": "erp_only_slot", "class_id": key[0], "date": key[1], "start_time": key[2], "end_time": key[3]})

    previous_by_key: Dict[Tuple[str, str, str, str], List[dict]] = defaultdict(list)
    new_by_key: Dict[Tuple[str, str, str, str], List[dict]] = defaultdict(list)
    for row in previous_in_range:
        previous_by_key[row_key(row)].append(row)
    for row in normalized:
        new_by_key[row_key(row)].append(row)
    for key in sorted(set(previous_by_key) & set(new_by_key)):
        prev_detail = Counter(detailed_key(row) for row in previous_by_key[key])
        new_detail = Counter(detailed_key(row) for row in new_by_key[key])
        if prev_detail == new_detail:
            continue
        rows.append(
            {
                "change_type": "same_slot_detail_changed",
                "class_id": key[0],
                "date": key[1],
                "start_time": key[2],
                "end_time": key[3],
                "previous": " | ".join(
                    f"{row.get('course_code','')} {row.get('course_name','')} {row.get('teacher_name','')} {row.get('room_name','')}"
                    for row in previous_by_key[key]
                ),
                "erp": " | ".join(
                    f"{row.get('course_code','')} {row.get('course_name','')} {row.get('teacher_name','')} {row.get('room_name','')}"
                    for row in new_by_key[key]
                ),
            }
        )
    return rows


def backup_outputs(paths: Sequence[Path], backup_dir: Path) -> None:
    backup_dir.mkdir(parents=True, exist_ok=True)
    for path in paths:
        if path.exists():
            shutil.copy2(path, backup_dir / path.name)


def sort_schedule_rows(rows: Iterable[dict]) -> List[dict]:
    return sorted(
        rows,
        key=lambda row: (
            clean(row.get("date")),
            PERIOD_ORDER.get(clean(row.get("period")), 9),
            clean(row.get("start_time")),
            clean(row.get("class_id")),
            clean(row.get("subject")),
            clean(row.get("course_code")),
        ),
    )


def append_report_section(report_path: Path, lines: Sequence[str]) -> None:
    with report_path.open("a", encoding="utf-8") as handle:
        handle.write("\n\n")
        handle.write("\n".join(lines))
        handle.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="将 ERP 调整后的课次导出同步回课表维护页")
    parser.add_argument("--erp-export", required=True)
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--schedule-csv", default="outputs/batch_schedule_maintenance.csv")
    parser.add_argument("--schedule-html", default="outputs/batch_schedule_maintenance.html")
    parser.add_argument("--report", default="outputs/batch_schedule_maintenance_report.md")
    parser.add_argument("--teacher-conflicts", default="outputs/teacher_time_conflicts.csv")
    parser.add_argument("--start-date", default="2026-07-01")
    parser.add_argument("--end-date", default="2026-12-13")
    parser.add_argument("--timestamp", default="")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    schedule_csv = Path(args.schedule_csv)
    schedule_html = Path(args.schedule_html)
    report_path = Path(args.report)
    teacher_conflicts_path = Path(args.teacher_conflicts)
    timestamp = args.timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")

    previous_rows = read_csv_rows(schedule_csv)
    current_class_ids = {clean(row.get("class_id")) for row in previous_rows if clean(row.get("class_id"))}
    erp_rows = read_erp_rows(Path(args.erp_export))
    normalized, issues, counters = build_normalized_rows(
        erp_rows,
        previous_rows,
        current_class_ids,
        data_dir,
        args.start_date,
        args.end_date,
    )

    preserved_rows = [
        row
        for row in previous_rows
        if not (args.start_date <= clean(row.get("date")) <= args.end_date)
    ]
    final_rows = sort_schedule_rows([*preserved_rows, *normalized])
    changes = changed_rows(previous_rows, normalized, args.start_date, args.end_date)

    backup_dir = Path("outputs/backups") / f"before_erp_sync_{timestamp}"
    backup_outputs(
        [
            schedule_csv,
            schedule_html,
            report_path,
            teacher_conflicts_path,
            Path("outputs/summer_camp_schedule.csv"),
            Path("outputs/summer_camp_schedule.html"),
        ],
        backup_dir,
    )

    write_csv_rows(schedule_csv, FIELDNAMES, final_rows)
    shutil.copy2(schedule_csv, "outputs/summer_camp_schedule.csv")

    class_metadata = load_class_metadata(data_dir)
    window_constraints = load_all_class_window_constraint_items(data_dir)
    room_names = load_room_names(data_dir)
    assignments = assignments_from_rows(final_rows, f"ERP_SYNC_{timestamp}")
    write_day_table_html(
        assignments,
        schedule_html,
        "27考研公共课课表维护页",
        ["AM", "PM", "EVENING"],
        room_names,
        "2026-06-25",
        args.end_date,
        class_metadata,
        window_constraints,
    )
    shutil.copy2(schedule_html, "outputs/summer_camp_schedule.html")
    write_teacher_time_conflicts_csv(assignments, teacher_conflicts_path, room_names)

    changes_path = Path("outputs") / f"erp_schedule_sync_changes_{timestamp}.csv"
    write_csv_rows(
        changes_path,
        ["change_type", "class_id", "date", "start_time", "end_time", "previous", "erp"],
        changes,
    )
    issues_path = Path("outputs") / f"erp_schedule_sync_unmapped_{timestamp}.csv"
    write_csv_rows(
        issues_path,
        ["issue_type", "class_id", "date", "time", "name", "detail"],
        issues,
    )
    sync_report_path = Path("outputs") / f"erp_schedule_sync_report_{timestamp}.md"
    previous_in_range_count = sum(1 for row in previous_rows if args.start_date <= clean(row.get("date")) <= args.end_date)
    report_lines = [
        f"# ERP 调整课表同步报告 {timestamp}",
        "",
        f"- ERP 文件：`{Path(args.erp_export)}`",
        f"- 同步范围：{args.start_date} 至 {args.end_date}",
        f"- 当前课表范围内原课次：{previous_in_range_count}",
        f"- ERP 正课有效课次：{len(normalized)}",
        f"- 保留范围外课次：{len(preserved_rows)}",
        f"- 同步后维护页总课次：{len(final_rows)}",
        f"- 课次时间槽变化：{sum(1 for row in changes if row.get('change_type') != 'same_slot_detail_changed')}",
        f"- 同时间明细变化：{sum(1 for row in changes if row.get('change_type') == 'same_slot_detail_changed')}",
        f"- 从班空明细填充：ERP 主班 {counters.get('shared_rows_filled_from_erp_donor', 0)}，上一版课表 {counters.get('shared_rows_filled_from_previous_schedule', 0)}",
        f"- 未解析从班空明细：{counters.get('unresolved_shared_row', 0)}",
        f"- 未匹配教师 ID：{sum(count for key, count in counters.items() if key.startswith('unmapped_teacher:'))}",
        f"- 未匹配教室 ID：{sum(count for key, count in counters.items() if key.startswith('unmapped_room:'))}",
        "",
        "## 输出",
        f"- 维护页 CSV：`{schedule_csv}`",
        f"- 维护页 HTML：`{schedule_html}`",
        f"- 变更明细：`{changes_path}`",
        f"- 未匹配/异常明细：`{issues_path}`",
        f"- 备份目录：`{backup_dir}`",
    ]
    if issues:
        top_issues = Counter(row["issue_type"] for row in issues)
        report_lines.extend(["", "## 异常类型统计"])
        for issue_type, count in top_issues.most_common():
            report_lines.append(f"- {issue_type}: {count}")
    sync_report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    append_report_section(
        report_path,
        [
            f"## ERP 调整课表同步 {timestamp}",
            f"- ERP 文件：`{Path(args.erp_export)}`",
            f"- 同步范围：{args.start_date} 至 {args.end_date}",
            f"- ERP 正课有效课次：{len(normalized)}；同步后维护页总课次：{len(final_rows)}",
            f"- 同步报告：`{sync_report_path}`",
        ],
    )

    print(f"已同步 ERP 调整课表: {len(normalized)} rows")
    print(sync_report_path)
    print(changes_path)
    print(issues_path)


if __name__ == "__main__":
    main()
