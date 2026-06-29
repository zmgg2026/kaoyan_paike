from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import scheduler
from scripts.csv_utils import write_csv_rows
from scripts.period_utils import PERIOD_LABELS
from scripts.product_catalog import DEFAULT_STAGE_ORDER
from scripts.schedule_data import (
    assignment_course_tag,
    load_class_metadata,
    load_product_course_tags,
)
from scripts.schedule_display import (
    assignment_standard_lesson_slots,
    date_range,
    standard_display_slots,
    subject_colors,
    weekday_label,
)
from scripts.window_utils import SEASON_WINDOW_ORDER


BATCH_SCHEDULE_CSV_FIELDNAMES = [
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
    "window_name",
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

DISPLAY_SUITE_OVERRIDES = {
    "KYJSJ2773": "2775",
}


def stage_filter_sort_order() -> List[str]:
    seen = set()
    result = []
    for value in [*SEASON_WINDOW_ORDER, *DEFAULT_STAGE_ORDER]:
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result


def display_suite_code(class_id: str, class_meta: Dict[str, str]) -> str:
    return DISPLAY_SUITE_OVERRIDES.get(class_id) or class_meta.get("suite_code") or ""


def window_constraint_payload(
    key: str,
    constraint: Any,
    class_metadata: Dict[str, Dict[str, str]],
    room_names: Dict[str, str],
) -> Dict[str, str]:
    class_id = getattr(constraint, "class_id", "") or ""
    class_meta = class_metadata.get(class_id, {})
    suite_code = (
        class_meta.get("suite_code")
        or getattr(constraint, "suite_code", "")
        or (key if key.isdigit() else "")
    )
    raw_room_ids = getattr(constraint, "room_ids", frozenset())
    room_ids = sorted(item for item in raw_room_ids if item)
    raw_area_ids = getattr(constraint, "teaching_area_ids", frozenset())
    area_ids = sorted(item for item in raw_area_ids if item)
    return {
        "id": getattr(constraint, "class_window_id", "") or key,
        "suite_code": suite_code,
        "class_id": class_id,
        "class_name": getattr(constraint, "class_name", "") or class_meta.get("class_name", ""),
        "sub_product": class_meta.get("sub_product", "") or getattr(constraint, "sub_product", ""),
        "window_name": (
            getattr(constraint, "schedule_window_name", "")
            or getattr(constraint, "season_name", "")
            or "窗口"
        ),
        "season_name": getattr(constraint, "season_name", ""),
        "teaching_area_ids": "|".join(area_ids),
        "room_ids": "|".join(room_ids),
        "room_names": " / ".join(room_names.get(room_id, room_id) for room_id in room_ids),
        "preferred_room_is_required": "是"
        if getattr(constraint, "preferred_room_is_required", False)
        else "否",
        "earliest_date": getattr(constraint, "earliest_date", ""),
        "earliest_period": getattr(constraint, "earliest_period", ""),
        "latest_date": getattr(constraint, "latest_date", ""),
        "latest_period": getattr(constraint, "latest_period", ""),
        "notes": getattr(constraint, "notes", ""),
    }


def build_day_table_payload(
    assignments: Sequence[scheduler.Assignment],
    title: str,
    periods: Sequence[str],
    room_names: Dict[str, str],
    start_date: Optional[str],
    end_date: Optional[str],
    class_metadata: Dict[str, Dict[str, str]],
    window_constraints: Dict[str, Any],
    product_course_tags: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    assigned_dates = sorted({assignment.candidate.slots[0].date for assignment in assignments})
    if start_date and end_date:
        dates = date_range(start_date, end_date)
    elif assigned_dates:
        dates = date_range(assigned_dates[0], assigned_dates[-1])
    else:
        dates = []
    colors = subject_colors(assignment.task.subject for assignment in assignments)
    product_course_tags = product_course_tags if product_course_tags is not None else load_product_course_tags(Path("data"))

    rows = []
    for assignment in assignments:
        slots = assignment.candidate.slots
        class_meta = class_metadata.get(assignment.task.class_id, {})
        suite_code = display_suite_code(assignment.task.class_id, class_meta)
        for lesson in assignment_standard_lesson_slots(slots, periods):
            course_tag = assignment_course_tag(assignment, class_metadata, product_course_tags)
            rows.append(
                {
                    "date": lesson["date"],
                    "weekday": weekday_label(str(lesson["date"])),
                    "period": lesson["period"],
                    "period_label": lesson["slot_label"],
                    "lesson_slot": lesson["slot_id"],
                    "slot_label": lesson["slot_label"],
                    "start_time": lesson["start_time"],
                    "end_time": lesson["end_time"],
                    "display_slot_ids": [lesson["slot_id"]],
                    "class_id": assignment.task.class_id,
                    "class_name": assignment.task.class_name,
                    "suite_code": suite_code,
                    "project": class_meta.get("project", ""),
                    "product_line": class_meta.get("product_line", ""),
                    "sub_product": class_meta.get("sub_product", ""),
                    "product_id": class_meta.get("product_id", "") or assignment.task.product_id or "",
                    "product_name": (
                        assignment.task.product_name or class_meta.get("product_name", "")
                    )
                    if not (assignment.task.product_name or "").startswith("合班到")
                    else "",
                    "product_system": class_meta.get("product_system", ""),
                    "course_nature": class_meta.get("course_nature", ""),
                    "subject_category": class_meta.get("subject_category", ""),
                    "subject": assignment.task.subject,
                    "window_name": assignment.task.quarter or "",
                    "stage": assignment.task.stage or "",
                    "course_module": assignment.task.course_module or "",
                    "course_group": assignment.task.course_group or "",
                    "course_code": course_tag.get("course_code", ""),
                    "course_name": course_tag.get("course_name", ""),
                    "teacher_id": assignment.candidate.teacher_id,
                    "teacher_name": assignment.candidate.teacher_name or assignment.candidate.teacher_id,
                    "room_id": assignment.candidate.room_id,
                    "room_name": room_names.get(assignment.candidate.room_id, assignment.candidate.room_id),
                    "duration_hours": lesson["duration_hours"],
                    "merge_note": assignment.task.product_name
                    if (assignment.task.product_name or "").startswith("合班到")
                    else "",
                    "color": colors.get(assignment.task.subject, "#6f5aa7"),
                }
            )

    constraint_rows = []
    for key, raw_constraints in sorted(window_constraints.items()):
        constraints = raw_constraints if isinstance(raw_constraints, list) else [raw_constraints]
        for constraint in constraints:
            constraint_rows.append(window_constraint_payload(key, constraint, class_metadata, room_names))
    return {
        "title": title,
        "periods": [{"id": period, "label": PERIOD_LABELS.get(period, period)} for period in periods],
        "slotRows": standard_display_slots(periods),
        "dates": dates,
        "rows": rows,
        "constraints": constraint_rows,
        "subjectColors": colors,
        "stageSortOrder": stage_filter_sort_order(),
    }


def write_day_table_html(
    assignments: Sequence[scheduler.Assignment],
    out_path: Path,
    title: str,
    periods: Sequence[str],
    room_names: Dict[str, str],
    start_date: Optional[str],
    end_date: Optional[str],
    class_metadata: Dict[str, Dict[str, str]],
    window_constraints: Dict[str, Any],
    product_course_tags: Optional[List[Dict[str, str]]] = None,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_day_table_payload(
        assignments=assignments,
        title=title,
        periods=periods,
        room_names=room_names,
        start_date=start_date,
        end_date=end_date,
        class_metadata=class_metadata,
        window_constraints=window_constraints,
        product_course_tags=product_course_tags,
    )
    payload_json = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    template = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>__TITLE__</title>
  <style>
    * { box-sizing: border-box; }
    body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #1d2733; background: #f5f7fa; }
    main { max-width: 100%; margin: 0 auto; padding: 22px; }
    h1 { margin: 0 0 8px; font-size: 24px; }
    h2 { margin: 0 0 10px; font-size: 18px; }
    .meta { margin: 0 0 16px; color: #637083; }
	    .toolbar { display: grid; gap: 12px; padding: 14px; border: 1px solid #d9e0e8; background: white; border-radius: 8px; margin-bottom: 14px; }
	    .filter-panel { margin-bottom: 14px; }
	    .filter-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(148px, 1fr)); gap: 12px; align-items: end; }
	    .filter-actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
	    .view-tabs { display: inline-flex; gap: 6px; padding: 3px; border: 1px solid #c9d3df; border-radius: 8px; background: #f8fafc; }
	    .view-tab { border: 0; background: transparent; height: 30px; padding: 0 12px; border-radius: 6px; }
	    .view-tab.active { background: #1f344a; color: white; }
	    .quick-ranges { display: flex; gap: 8px; flex-wrap: wrap; }
	    .quick-ranges button { background: white; }
	    .hidden { display: none !important; }
    label { display: grid; gap: 6px; font-size: 13px; color: #4f5d6d; }
    select, input { height: 34px; min-width: 0; border: 1px solid #c9d3df; border-radius: 6px; padding: 0 10px; color: #1d2733; background: white; font: inherit; }
    .check-row { display: flex; align-items: center; gap: 7px; min-height: 34px; }
    .check-row input { width: 16px; height: 16px; min-width: 0; padding: 0; }
    button { height: 34px; border: 1px solid #aebccd; background: #eef3f8; color: #1f344a; border-radius: 6px; padding: 0 12px; font: inherit; cursor: pointer; }
    .summary-grid { display: grid; grid-template-columns: minmax(260px, 0.9fr) minmax(320px, 1.3fr) minmax(260px, 1fr); gap: 14px; margin-bottom: 14px; }
    .panel { border: 1px solid #d9e0e8; background: white; border-radius: 8px; padding: 14px; min-width: 0; }
    .metric-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
    .metric-card { border: 1px solid #dfe6ee; background: #f8fafc; border-radius: 6px; padding: 10px; }
    .metric-card strong { display: block; font-size: 20px; margin-bottom: 2px; }
    .metric-card span { color: #667386; font-size: 12px; }
    .constraint-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 10px; max-height: 260px; overflow: auto; padding-right: 4px; }
    .constraint-item { border-left: 4px solid #557a35; background: #f7faf6; padding: 9px 10px; border-radius: 6px; line-height: 1.5; }
    .constraint-item strong { display: block; margin-bottom: 2px; }
    .legend { display: flex; gap: 12px; flex-wrap: wrap; margin: 0 0 14px; color: #4e5d6f; }
    .legend span { display: inline-flex; align-items: center; gap: 6px; }
    .legend i { width: 12px; height: 12px; border-radius: 3px; display: inline-block; }
    .table-scroll { overflow: auto; border: 1px solid #d9e0e8; background: white; border-radius: 8px; }
    table { border-collapse: separate; border-spacing: 0; min-width: max-content; background: white; }
    th, td { border-right: 1px solid #d9e0e8; border-bottom: 1px solid #d9e0e8; padding: 10px; vertical-align: top; line-height: 1.35; }
    thead th { position: sticky; top: 0; z-index: 2; background: #eef3f8; text-align: center; min-width: 132px; }
    thead th:first-child { left: 0; z-index: 4; min-width: 116px; }
    thead th span { display: block; margin-top: 3px; color: #6c7888; font-weight: 500; font-size: 12px; }
    .period-head { position: sticky; left: 0; z-index: 3; min-width: 116px; background: #f8fafc; text-align: center; }
    .period-head strong { font-size: 13px; }
    .period-head span { display: block; margin-top: 4px; color: #657285; font-size: 11px; font-weight: 500; }
    .schedule-table th, .schedule-table td { padding: 5px; line-height: 1.18; }
    .schedule-table td { width: 132px; height: 84px; }
    .slot-cell { height: 84px; }
    .slot-content { max-height: 74px; overflow-y: auto; padding-right: 2px; }
    .course-card { border-left: 4px solid var(--subject-color); background: color-mix(in srgb, var(--subject-color) 12%, white); border-radius: 5px; padding: 4px 5px; min-height: 0; font-size: 11px; }
    .course-card + .course-card { margin-top: 4px; }
    .course-card strong { display: block; color: var(--subject-color); font-size: 12px; line-height: 1.18; }
    .course-card span, .course-card em, .course-card small { display: block; margin-top: 2px; font-style: normal; font-size: 10px; line-height: 1.16; }
    .course-card em { font-weight: 600; font-size: 11px; }
    .course-card small { color: #5d6877; }
    .merge-note { color: #8a5b1f; font-weight: 600; }
    .empty { color: #a0a9b6; }
    .suite-section { margin-top: 18px; }
    .suite-title { display: flex; align-items: baseline; gap: 10px; margin: 0 0 10px; }
    .suite-title small { color: #687689; font-weight: 500; }
    .hours-table { width: 100%; min-width: 0; border: 1px solid #d9e0e8; border-right: 0; border-bottom: 0; }
    .hours-table th { position: static; min-width: 0; text-align: left; background: #eef3f8; }
    .hours-table td, .hours-table th { height: auto; width: auto; }
	    #teacherSummary, #teacherPageSummaryTable { max-height: 260px; overflow: auto; padding-right: 4px; }
	    #teacherSummary .hours-table thead th, #teacherPageSummaryTable .hours-table thead th { position: sticky; top: 0; z-index: 1; }
    .teacher-day-section { margin-top: 18px; }
    .teacher-day-title { display: flex; flex-wrap: wrap; align-items: baseline; gap: 10px; margin: 0 0 10px; }
    .teacher-day-title small { color: #687689; font-weight: 500; }
    .teacher-day-table { min-width: max-content; }
    .teacher-day-table th { position: sticky; top: 0; z-index: 2; background: #eef3f8; text-align: center; min-width: 132px; }
	    .teacher-day-table td { width: 150px; height: 104px; padding: 6px; }
    .teacher-day-table .teacher-head-header { left: 0; z-index: 5; min-width: 150px; }
    .teacher-day-table .teacher-period-header { left: 150px; z-index: 5; min-width: 126px; }
    .teacher-head-cell { position: sticky; left: 0; z-index: 3; min-width: 150px; max-width: 150px; background: #f8fafc; text-align: center; vertical-align: middle; }
    .teacher-head-cell strong { display: block; font-size: 15px; }
    .teacher-head-cell span { display: block; margin-top: 5px; color: #687689; font-size: 12px; font-weight: 500; }
    .teacher-period-cell { position: sticky; left: 150px; z-index: 3; min-width: 126px; background: #f8fafc; text-align: center; }
    .teacher-period-cell span { display: block; margin-top: 4px; color: #657285; font-size: 12px; font-weight: 500; }
	    .teacher-slot-cell { height: 92px; overflow-y: auto; padding-right: 2px; }
    .teacher-slot-cell .empty { display: block; padding: 6px 2px; }
    .teacher-lesson { border-left: 5px solid var(--subject-color); background: color-mix(in srgb, var(--subject-color) 10%, white); border-radius: 6px; padding: 6px; margin-bottom: 6px; }
    .teacher-lesson:last-child { margin-bottom: 0; }
    .teacher-lesson strong { display: block; color: var(--subject-color); font-size: 13px; }
    .teacher-lesson span, .teacher-lesson small { display: block; margin-top: 3px; font-size: 12px; }
    .teacher-lesson small { color: #5d6877; }
    .muted { color: #7b8796; }
    @media (max-width: 900px) {
      main { padding: 14px; }
      .summary-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
<main>
	  <h1 id="pageTitle"></h1>
		  <p class="meta">横向为日期，纵向为标准课节；班级课表与老师每日课表分开维护筛选，默认展示当前结果的完整日期范围。</p>
	  <section class="toolbar">
	    <div class="filter-actions">
	      <div class="view-tabs" aria-label="内容视图">
	        <button class="view-tab active" type="button" data-view="schedule">班级课表</button>
	        <button class="view-tab" type="button" data-view="teacherDaily">老师每日课表</button>
	      </div>
	    </div>
	  </section>
	  <section id="classFilterPanel" class="toolbar filter-panel">
	    <div class="filter-grid">
	      <label>产品线
	        <select id="productLineSelect"></select>
	      </label>
	      <label>子产品
	        <select id="subProductSelect"></select>
	      </label>
	      <label>产品
	        <select id="productSelect"></select>
	      </label>
	      <label>套班
	        <select id="suiteSelect"></select>
	      </label>
	      <label>班级
	        <select id="classSelect"></select>
      </label>
      <label>科目
        <select id="subjectSelect"></select>
      </label>
      <label>阶段
        <select id="stageSelect"></select>
      </label>
	      <label>老师
	        <select id="teacherSelect"></select>
	      </label>
	      <label>课程分组
	        <select id="courseGroupSelect"></select>
	      </label>
	      <label>教室
	        <select id="roomSelect"></select>
	      </label>
	      <label>分组方式
	        <select id="groupBySelect">
	          <option value="suite">按套班</option>
	          <option value="class">按班级</option>
	          <option value="product">按产品</option>
          <option value="teacher">按老师</option>
        </select>
      </label>
      <label>开始日期
        <input id="startDate" type="date">
      </label>
      <label>结束日期
        <input id="endDate" type="date">
      </label>
      <label>关键词
	        <input id="keywordInput" type="search" placeholder="班级/课程/教室">
	      </label>
	    </div>
	    <div class="filter-actions">
	      <div class="quick-ranges" aria-label="常用日期">
	        <button type="button" data-range="default">默认范围</button>
	        <button type="button" data-range="summer">暑期</button>
	        <button type="button" data-range="autumn">秋季</button>
	        <button type="button" data-range="all">全部</button>
	      </div>
	      <label class="check-row">
	        <input id="onlyCourseDates" type="checkbox">
	        <span>只看有课日期</span>
	      </label>
	      <button id="resetButton" type="button">重置</button>
	    </div>
	  </section>
	  <section id="teacherFilterPanel" class="toolbar filter-panel hidden">
	    <div class="filter-grid">
	      <label>老师
	        <select id="teacherDailySelect"></select>
	      </label>
	      <label>老师关键词
	        <input id="teacherKeywordInput" type="search" placeholder="姓名/员工ID">
	      </label>
	      <label>子产品
	        <select id="teacherSubProductSelect"></select>
	      </label>
	      <label>套班
	        <select id="teacherSuiteSelect"></select>
	      </label>
	      <label>科目
	        <select id="teacherSubjectSelect"></select>
	      </label>
	      <label>开始日期
	        <input id="teacherStartDate" type="date">
	      </label>
	      <label>结束日期
	        <input id="teacherEndDate" type="date">
	      </label>
	    </div>
	    <div class="filter-actions">
	      <div class="quick-ranges" aria-label="老师页常用日期">
	        <button type="button" data-teacher-range="default">默认范围</button>
	        <button type="button" data-teacher-range="summer">暑期</button>
	        <button type="button" data-teacher-range="autumn">秋季</button>
	        <button type="button" data-teacher-range="all">全部</button>
	      </div>
	      <label class="check-row">
	        <input id="teacherOnlyCourseDates" type="checkbox" checked>
	        <span>只看有课日期</span>
	      </label>
	      <button id="teacherResetButton" type="button">重置老师筛选</button>
	    </div>
	  </section>
	  <section id="classSummaryGrid" class="summary-grid">
	    <div class="panel">
	      <h2>筛选汇总</h2>
	      <div id="metricSummary" class="metric-grid"></div>
    </div>
    <div class="panel">
      <h2>窗口与资源边界</h2>
      <div id="constraintList" class="constraint-list"></div>
    </div>
    <div class="panel">
	      <h2>老师课时汇总</h2>
	      <div id="teacherSummary"></div>
	    </div>
	  </section>
	  <section id="teacherSummaryGrid" class="summary-grid hidden">
	    <div class="panel">
	      <h2>老师筛选汇总</h2>
	      <div id="teacherMetricSummary" class="metric-grid"></div>
	    </div>
	    <div class="panel">
	      <h2>老师课时汇总</h2>
	      <div id="teacherPageSummaryTable"></div>
	    </div>
	    <div class="panel">
	      <h2>当前范围</h2>
	      <div id="teacherRangeSummary" class="constraint-list"></div>
	    </div>
	  </section>
  <div id="legend" class="legend"></div>
  <div id="scheduleSections"></div>
</main>
<script id="schedulePayload" type="application/json">__PAYLOAD__</script>
<script>
	const payload = JSON.parse(document.getElementById("schedulePayload").textContent);
	const periodLabels = Object.fromEntries(payload.periods.map((period) => [period.id, period.label]));
	const slotRows = payload.slotRows || payload.periods.map((period) => ({ ...period, start_time: "", end_time: "" }));
const weekdayLabels = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
const classFilterPanel = document.getElementById("classFilterPanel");
const teacherFilterPanel = document.getElementById("teacherFilterPanel");
const classSummaryGrid = document.getElementById("classSummaryGrid");
const teacherSummaryGrid = document.getElementById("teacherSummaryGrid");
const productLineSelect = document.getElementById("productLineSelect");
const subProductSelect = document.getElementById("subProductSelect");
const productSelect = document.getElementById("productSelect");
const suiteSelect = document.getElementById("suiteSelect");
const classSelect = document.getElementById("classSelect");
const subjectSelect = document.getElementById("subjectSelect");
const stageSelect = document.getElementById("stageSelect");
const teacherSelect = document.getElementById("teacherSelect");
const courseGroupSelect = document.getElementById("courseGroupSelect");
const roomSelect = document.getElementById("roomSelect");
const groupBySelect = document.getElementById("groupBySelect");
const startDateInput = document.getElementById("startDate");
const endDateInput = document.getElementById("endDate");
const keywordInput = document.getElementById("keywordInput");
const onlyCourseDatesInput = document.getElementById("onlyCourseDates");
const teacherDailySelect = document.getElementById("teacherDailySelect");
const teacherKeywordInput = document.getElementById("teacherKeywordInput");
const teacherSubProductSelect = document.getElementById("teacherSubProductSelect");
const teacherSuiteSelect = document.getElementById("teacherSuiteSelect");
const teacherSubjectSelect = document.getElementById("teacherSubjectSelect");
	const teacherStartDateInput = document.getElementById("teacherStartDate");
	const teacherEndDateInput = document.getElementById("teacherEndDate");
	const teacherOnlyCourseDatesInput = document.getElementById("teacherOnlyCourseDates");
	let currentView = "schedule";
	let renderTimer = 0;

function parseDate(value) {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day);
}

function toISODate(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function datesBetween(start, end) {
  const dates = [];
  if (!start || !end || start > end) return dates;
  const current = parseDate(start);
  const last = parseDate(end);
  while (current <= last) {
    dates.push(toISODate(current));
    current.setDate(current.getDate() + 1);
  }
  return dates;
}

function weekday(value) {
  return weekdayLabels[parseDate(value).getDay()];
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[char]);
}

	const quickDateRanges = {
	  default: () => [defaultStartDate(), defaultEndDate()],
	  summer: () => seasonRange(7, 8),
	  autumn: () => seasonRange(9, 12),
	  all: () => [payload.dates[0] || "", payload.dates[payload.dates.length - 1] || ""],
};

const stageMonthRanges = {
  "寒假": [1, 2],
  "春季": [3, 6],
  "暑假": [7, 8],
  "秋季": [9, 12],
};

function defaultStartDate() {
  return payload.dates[0] || "";
	}

	function defaultEndDate() {
	  return payload.dates[payload.dates.length - 1] || "";
	}

function seasonRange(startMonth, endMonth) {
  const matching = (payload.dates || []).filter((date) => {
    const month = Number(String(date).slice(5, 7));
    return month >= startMonth && month <= endMonth;
  });
  if (!matching.length) return quickDateRanges.all();
  return [matching[0], matching[matching.length - 1]];
}

	function requestRender() {
	  window.clearTimeout(renderTimer);
	  renderTimer = window.setTimeout(render, 300);
	}

function applyDateRange(rangeKey, startInput = startDateInput, endInput = endDateInput) {
  const rangeFactory = quickDateRanges[rangeKey] || quickDateRanges.default;
  const [start, end] = rangeFactory();
  startInput.value = start;
  endInput.value = end;
}

function applyStageDateRange() {
  const months = stageMonthRanges[stageSelect.value];
  const range = months ? seasonRange(months[0], months[1]) : null;
  if (range && range[0] && range[1]) {
    startDateInput.value = range[0];
    endDateInput.value = range[1];
    return;
	  }
	  startDateInput.value = defaultStartDate();
	  endDateInput.value = defaultEndDate();
	}

function rowSuite(row) {
  return row.suite_code || "未分组";
}

function rowClass(row) {
  return [row.class_id, row.class_name].filter(Boolean).join(" / ");
}

function rowProduct(row) {
  return [row.product_id, row.product_name].filter(Boolean).join(" ") || "未分产品";
}

function rowTeacher(row) {
  return [row.teacher_name, row.teacher_id].filter(Boolean).join(" ") || "未分老师";
}

function rowRoom(row) {
  return [row.room_name, row.room_id].filter(Boolean).join(" ") || "未分教室";
}

function rowStage(row) {
  return row.stage || "未分阶段";
}

function valueOrAll(select) {
  return select.value === "__all__" ? "" : select.value;
}

function rowMatchesSelect(row, select, getter) {
  const value = valueOrAll(select);
  return !value || getter(row) === value;
}

function rowSearchText(row) {
  return [
    row.project,
    row.product_line,
    row.sub_product,
    row.product_id,
    row.product_name,
    row.class_id,
    row.class_name,
    row.suite_code,
    row.subject,
    row.window_name || row.quarter,
    row.stage,
    row.course_module,
    row.course_group,
    row.course_code,
    row.course_name,
	    row.teacher_id,
	    row.teacher_name,
	    row.room_id,
	    row.room_name,
	    row.merge_note,
	  ].filter(Boolean).join(" ").toLowerCase();
	}

function filteredClassRows() {
	  const start = startDateInput.value;
	  const end = endDateInput.value;
	  const keyword = keywordInput.value.trim().toLowerCase();
	  return payload.rows.filter((row) =>
	    rowMatchesSelect(row, productLineSelect, (item) => item.product_line || "未分产品线") &&
	    rowMatchesSelect(row, subProductSelect, (item) => item.sub_product || "未分子产品") &&
	    rowMatchesSelect(row, productSelect, rowProduct) &&
	    rowMatchesSelect(row, suiteSelect, rowSuite) &&
	    rowMatchesSelect(row, classSelect, rowClass) &&
	    rowMatchesSelect(row, subjectSelect, (item) => item.subject || "未分科目") &&
	    rowMatchesSelect(row, stageSelect, rowStage) &&
	    rowMatchesSelect(row, teacherSelect, rowTeacher) &&
	    rowMatchesSelect(row, courseGroupSelect, (item) => item.course_group || "未分课程分组") &&
	    rowMatchesSelect(row, roomSelect, rowRoom) &&
	    (!start || row.date >= start) &&
	    (!end || row.date <= end) &&
	    (!keyword || rowSearchText(row).includes(keyword))
	  );
	}

	function filteredTeacherRows() {
	  const start = teacherStartDateInput.value;
  const end = teacherEndDateInput.value;
  const keyword = teacherKeywordInput.value.trim().toLowerCase();
  return payload.rows.filter((row) =>
    rowMatchesSelect(row, teacherDailySelect, rowTeacher) &&
    rowMatchesSelect(row, teacherSubProductSelect, (item) => item.sub_product || "未分子产品") &&
    rowMatchesSelect(row, teacherSuiteSelect, rowSuite) &&
    rowMatchesSelect(row, teacherSubjectSelect, (item) => item.subject || "未分科目") &&
    (!start || row.date >= start) &&
    (!end || row.date <= end) &&
    (!keyword || rowTeacher(row).toLowerCase().includes(keyword))
	  );
	}

	function hasTeacherScope() {
	  return valueOrAll(teacherDailySelect) ||
	    valueOrAll(teacherSubProductSelect) ||
	    valueOrAll(teacherSuiteSelect) ||
	    valueOrAll(teacherSubjectSelect) ||
	    teacherKeywordInput.value.trim();
	}

function optionList(select, values, allLabel, currentValue = select.value) {
  const uniqueValues = [...new Set(values.filter(Boolean))].sort((a, b) => String(a).localeCompare(String(b)));
  select.innerHTML = [
    `<option value="__all__">${escapeHtml(allLabel)}</option>`,
    ...uniqueValues.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`),
  ].join("");
  if (currentValue && [...uniqueValues, "__all__"].includes(currentValue)) {
    select.value = currentValue;
  }
}

function optionValueOrAll(select, preferredValue) {
  return [...select.options].some((item) => item.value === preferredValue) ? preferredValue : "__all__";
}

function renderFilterOptions() {
  optionList(productLineSelect, payload.rows.map((row) => row.product_line || "未分产品线"), "全部产品线");
  optionList(subProductSelect, payload.rows.map((row) => row.sub_product || "未分子产品"), "全部子产品");
  optionList(productSelect, payload.rows.map(rowProduct), "全部产品");
  optionList(suiteSelect, payload.rows.map(rowSuite), "全部套班");
  optionList(classSelect, payload.rows.map(rowClass), "全部班级");
  optionList(subjectSelect, payload.rows.map((row) => row.subject || "未分科目"), "全部科目");
  optionList(teacherSelect, payload.rows.map(rowTeacher), "全部老师");
  optionList(courseGroupSelect, payload.rows.map((row) => row.course_group || "未分课程分组"), "全部课程分组");
  optionList(roomSelect, payload.rows.map(rowRoom), "全部教室");
  optionList(teacherDailySelect, payload.rows.map(rowTeacher), "全部老师");
  optionList(teacherSubProductSelect, payload.rows.map((row) => row.sub_product || "未分子产品"), "全部子产品");
  optionList(teacherSuiteSelect, payload.rows.map(rowSuite), "全部套班");
  optionList(teacherSubjectSelect, payload.rows.map((row) => row.subject || "未分科目"), "全部科目");
  const preferred = Array.isArray(payload.stageSortOrder) ? payload.stageSortOrder : [];
  const stages = [...new Set(payload.rows.map((row) => rowStage(row)))].sort((a, b) => {
    const ai = preferred.indexOf(a);
    const bi = preferred.indexOf(b);
    if (ai !== -1 || bi !== -1) return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
    return a.localeCompare(b);
  });
  optionList(stageSelect, stages, "全部阶段");
}

function renderLegend() {
  const entries = Object.entries(payload.subjectColors);
  document.getElementById("legend").innerHTML = entries
    .map(([subject, color]) => `<span><i style="background:${escapeHtml(color)}"></i>${escapeHtml(subject)}</span>`)
    .join("");
}

function renderMetrics(rows) {
  const totalHours = rows.reduce((sum, row) => sum + Number(row.duration_hours || 0), 0);
  const metrics = [
    ["课节", rows.length],
    ["课时", totalHours],
    ["班级", new Set(rows.map((row) => row.class_id)).size],
    ["老师", new Set(rows.map((row) => row.teacher_name || row.teacher_id).filter(Boolean)).size],
  ];
  document.getElementById("metricSummary").innerHTML = metrics
    .map(([label, value]) => `<div class="metric-card"><strong>${escapeHtml(value)}</strong><span>${escapeHtml(label)}</span></div>`)
    .join("");
}

function renderConstraints(rows) {
  const selectedSuites = new Set(rows.map(rowSuite));
  const selectedClasses = new Set(rows.map((row) => row.class_id));
  const constraintRows = payload.constraints.filter((constraint) =>
    selectedClasses.has(constraint.class_id) || selectedSuites.has(constraint.suite_code)
  );
  document.getElementById("constraintList").innerHTML = constraintRows.length
    ? constraintRows.map((constraint) => `
        <div class="constraint-item">
          <strong>${escapeHtml([constraint.class_id || constraint.suite_code, constraint.window_name].filter(Boolean).join(" / "))}</strong>
          <div>${escapeHtml([constraint.sub_product, constraint.class_name].filter(Boolean).join(" / "))}</div>
          <div>资源：${escapeHtml(constraint.room_names || constraint.room_ids || "未指定教室")} ${constraint.preferred_room_is_required === "是" ? "（固定）" : ""}</div>
          <div>可排：${escapeHtml(constraint.earliest_date)} ${escapeHtml(constraint.earliest_period)} 至 ${escapeHtml(constraint.latest_date)} ${escapeHtml(constraint.latest_period)}</div>
          ${constraint.notes ? `<div>${escapeHtml(constraint.notes)}</div>` : ""}
        </div>
      `).join("")
    : `<p class="muted">当前筛选范围没有可展示的班级排课窗口。</p>`;
}

function renderTeacherSummary(rows) {
  const summary = new Map();
  for (const row of rows) {
	    const key = [row.sub_product, rowSuite(row), row.teacher_id, row.teacher_name, row.subject].join("|");
	    const current = summary.get(key) || { product: row.sub_product || row.product_line || "", suite: rowSuite(row), teacher: rowTeacher(row), subject: row.subject, hours: 0, count: 0 };
    current.hours += Number(row.duration_hours || 0);
    current.count += 1;
    summary.set(key, current);
  }
  const values = [...summary.values()].sort((a, b) => a.product.localeCompare(b.product) || a.suite.localeCompare(b.suite) || a.teacher.localeCompare(b.teacher) || a.subject.localeCompare(b.subject));
  document.getElementById("teacherSummary").innerHTML = values.length
    ? `<table class="hours-table">
        <thead><tr><th>产品</th><th>套班</th><th>老师</th><th>科目</th><th>课时</th><th>课次数</th></tr></thead>
        <tbody>${values.map((item) => `
          <tr>
            <td>${escapeHtml(item.product)}</td>
            <td>${escapeHtml(item.suite)}</td>
            <td>${escapeHtml(item.teacher)}</td>
            <td>${escapeHtml(item.subject)}</td>
            <td>${item.hours}</td>
            <td>${item.count}</td>
          </tr>
        `).join("")}</tbody>
      </table>`
	    : `<p class="muted">当前日期范围没有课程。</p>`;
	}

function renderTeacherPageSummary(rows) {
  const totalHours = rows.reduce((sum, row) => sum + Number(row.duration_hours || 0), 0);
  const metrics = [
    ["课节", rows.length],
    ["课时", totalHours],
    ["老师", new Set(rows.map(rowTeacher).filter(Boolean)).size],
    ["班级", new Set(rows.map((row) => row.class_id).filter(Boolean)).size],
  ];
  document.getElementById("teacherMetricSummary").innerHTML = metrics
    .map(([label, value]) => `<div class="metric-card"><strong>${escapeHtml(value)}</strong><span>${escapeHtml(label)}</span></div>`)
    .join("");
  renderTeacherSummaryInto(rows, document.getElementById("teacherPageSummaryTable"));
  const activeTeachers = [...new Set(rows.map(rowTeacher).filter(Boolean))].sort((a, b) => a.localeCompare(b));
  document.getElementById("teacherRangeSummary").innerHTML = `
    <div class="constraint-item">
      <strong>${escapeHtml(teacherStartDateInput.value || "不限")} 至 ${escapeHtml(teacherEndDateInput.value || "不限")}</strong>
      <div>${escapeHtml(activeTeachers.length ? `${activeTeachers.length} 位老师` : "当前范围没有老师课表")}</div>
      <div>${escapeHtml(activeTeachers.slice(0, 8).join("、"))}${activeTeachers.length > 8 ? "..." : ""}</div>
    </div>`;
}

function renderTeacherSummaryInto(rows, target) {
  const summary = new Map();
  for (const row of rows) {
    const key = [row.sub_product, rowSuite(row), row.teacher_id, row.teacher_name, row.subject].join("|");
    const current = summary.get(key) || { product: row.sub_product || row.product_line || "", suite: rowSuite(row), teacher: rowTeacher(row), subject: row.subject, hours: 0, count: 0 };
    current.hours += Number(row.duration_hours || 0);
    current.count += 1;
    summary.set(key, current);
  }
  const values = [...summary.values()].sort((a, b) => a.teacher.localeCompare(b.teacher) || a.product.localeCompare(b.product) || a.suite.localeCompare(b.suite) || a.subject.localeCompare(b.subject));
  target.innerHTML = values.length
    ? `<table class="hours-table">
        <thead><tr><th>老师</th><th>产品</th><th>套班</th><th>科目</th><th>课时</th><th>课次数</th></tr></thead>
        <tbody>${values.map((item) => `
          <tr>
            <td>${escapeHtml(item.teacher)}</td>
            <td>${escapeHtml(item.product)}</td>
            <td>${escapeHtml(item.suite)}</td>
            <td>${escapeHtml(item.subject)}</td>
            <td>${item.hours}</td>
            <td>${item.count}</td>
          </tr>
        `).join("")}</tbody>
      </table>`
    : `<p class="muted">当前日期范围没有课程。</p>`;
}

function courseCard(row) {
  const windowName = row.window_name || row.quarter || "";
  const detail = [windowName, row.stage, row.course_module].filter(Boolean).join(" ");
  const courseName = row.course_name || "";
  const location = [row.class_id, row.sub_product || "", row.room_name].filter(Boolean).join(" / ");
  return `<div class="course-card" style="--subject-color: ${escapeHtml(row.color)}">
    <strong>${escapeHtml(row.subject)}</strong>
    <span>${escapeHtml(detail)}</span>
    <em>${escapeHtml(row.teacher_name)}</em>
    ${row.merge_note ? `<small class="merge-note">${escapeHtml(row.merge_note)}</small>` : ""}
    <small>${escapeHtml(location)}</small>
    ${courseName ? `<small>${escapeHtml(courseName)}</small>` : ""}
  </div>`;
}

function teacherLessonCard(row) {
  const timeText = [row.start_time, row.end_time].filter(Boolean).join("-");
  const courseName = row.course_name || "";
  const windowName = row.window_name || row.quarter || "";
  return `<div class="teacher-lesson" style="--subject-color: ${escapeHtml(row.color)}">
    <strong>${escapeHtml(row.subject)} ${escapeHtml([windowName, row.stage, row.course_module].filter(Boolean).join(" "))}</strong>
    <span>${escapeHtml(timeText)} / ${escapeHtml(row.class_id)} ${escapeHtml(row.class_name || "")}</span>
    ${row.merge_note ? `<small class="merge-note">${escapeHtml(row.merge_note)}</small>` : ""}
    <small>${escapeHtml(row.sub_product || row.product_name || "")} / 套班 ${escapeHtml(rowSuite(row))}</small>
    <small>${escapeHtml(row.room_name)}</small>
    ${courseName ? `<small>${escapeHtml(courseName)}</small>` : ""}
  </div>`;
}

function groupLabel(row) {
  if (groupBySelect.value === "class") return rowClass(row);
  if (groupBySelect.value === "product") return row.sub_product || row.product_line || row.product_id || "未分产品";
  if (groupBySelect.value === "teacher") return row.teacher_name || row.teacher_id || "未分老师";
  return `${rowSuite(row)} 套班`;
}

function selectedDates(rows, startInput = startDateInput, endInput = endDateInput, onlyCourseDates = onlyCourseDatesInput) {
  let dates = datesBetween(startInput.value, endInput.value);
  if (onlyCourseDates.checked) {
    const activeDates = new Set(rows.map((row) => row.date));
    dates = dates.filter((date) => activeDates.has(date));
  }
  return dates;
}

function renderScheduleTable(groupName, rows, dates) {
  const byKey = new Map();
  for (const row of rows) {
    const slotIds = row.display_slot_ids?.length ? row.display_slot_ids : [row.period];
    for (const slotId of slotIds) {
      const key = `${row.date}|${slotId}`;
      const bucket = byKey.get(key) || [];
      bucket.push(row);
      byKey.set(key, bucket);
    }
  }
  const header = dates.map((date) => `<th><strong>${escapeHtml(date.slice(5))}</strong><span>${escapeHtml(weekday(date))}</span></th>`).join("");
  const body = slotRows.map((slot) => {
    const cells = dates.map((date) => {
      const entries = (byKey.get(`${date}|${slot.id}`) || []).sort((a, b) => a.class_id.localeCompare(b.class_id));
      return `<td class="slot-cell"><div class="slot-content">${entries.length ? entries.map(courseCard).join("") : `<span class="empty">空</span>`}</div></td>`;
    }).join("");
    const timeText = [slot.start_time, slot.end_time].filter(Boolean).join("-");
    return `<tr><th class="period-head"><strong>${escapeHtml(slot.label || periodLabels[slot.period] || slot.id)}</strong><span>${escapeHtml(timeText)}</span></th>${cells}</tr>`;
  }).join("");
  return `<section class="suite-section">
    <div class="suite-title"><h2>${escapeHtml(groupName)}课表</h2><small>${rows.length} 条课程</small></div>
    <div class="table-scroll">
      <table class="schedule-table">
        <thead><tr><th>时段</th>${header}</tr></thead>
        <tbody>${body}</tbody>
      </table>
    </div>
  </section>`;
}

function renderSchedules(rows) {
  const dates = selectedDates(rows, startDateInput, endDateInput, onlyCourseDatesInput);
  const groups = new Map();
  for (const row of rows) {
    const label = groupLabel(row);
    const bucket = groups.get(label) || [];
    bucket.push(row);
    groups.set(label, bucket);
  }
  const orderedGroups = [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
  document.getElementById("scheduleSections").innerHTML = orderedGroups.length
    ? orderedGroups.map(([groupName, groupRows]) => renderScheduleTable(groupName, groupRows, dates)).join("")
    : `<div class="panel"><p class="muted">当前筛选范围没有课程。</p></div>`;
}

	function renderTeacherDaily(rows) {
  const dates = selectedDates(rows, teacherStartDateInput, teacherEndDateInput, teacherOnlyCourseDatesInput);
  const groups = new Map();
  for (const row of rows) {
	    const teacherName = rowTeacher(row);
    const bucket = groups.get(teacherName) || [];
    bucket.push(row);
    groups.set(teacherName, bucket);
  }
  const orderedGroups = [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
  const dateHeader = dates
    .map((date) => `<th><strong>${escapeHtml(date.slice(5))}</strong><span>${escapeHtml(weekday(date))}</span></th>`)
    .join("");
  const body = orderedGroups.map(([teacherName, teacherRows]) => {
    const byKey = new Map();
    for (const row of teacherRows) {
      const slotIds = row.display_slot_ids?.length ? row.display_slot_ids : [row.period];
      for (const slotId of slotIds) {
        const key = `${row.date}|${slotId}`;
        const bucket = byKey.get(key) || [];
        bucket.push(row);
        byKey.set(key, bucket);
      }
    }
    const totalHours = teacherRows.reduce((sum, row) => sum + Number(row.duration_hours || 0), 0);
    const classCount = new Set(teacherRows.map((row) => row.class_id)).size;
    return slotRows.map((slot, index) => {
      const teacherCell = index === 0
        ? `<th class="teacher-head-cell" rowspan="${slotRows.length}">
            <strong>${escapeHtml(teacherName)}</strong>
            <span>${teacherRows.length} 节 / ${totalHours} 小时</span>
            <span>${classCount} 个班级</span>
          </th>`
        : "";
      const timeText = [slot.start_time, slot.end_time].filter(Boolean).join("-");
      const cells = dates.map((date) => {
        const entries = (byKey.get(`${date}|${slot.id}`) || [])
          .sort((a, b) => `${a.start_time}${a.class_id}${a.subject}`.localeCompare(`${b.start_time}${b.class_id}${b.subject}`));
        return `<td><div class="teacher-slot-cell">${entries.length ? entries.map(teacherLessonCard).join("") : `<span class="empty">空</span>`}</div></td>`;
      }).join("");
      return `<tr>
        ${teacherCell}
        <th class="teacher-period-cell"><strong>${escapeHtml(slot.label || periodLabels[slot.period] || slot.id)}</strong><span>${escapeHtml(timeText)}</span></th>
        ${cells}
      </tr>`;
    }).join("");
  }).join("");
  document.getElementById("scheduleSections").innerHTML = orderedGroups.length
    ? `<section class="teacher-day-section">
        <div class="teacher-day-title">
          <h2>老师每日课表</h2>
          <small>${orderedGroups.length} 位老师 / ${rows.length} 条课程</small>
        </div>
        <div class="table-scroll">
          <table class="teacher-day-table">
            <thead><tr><th class="teacher-head-header">老师</th><th class="teacher-period-header">时段</th>${dateHeader}</tr></thead>
            <tbody>${body}</tbody>
          </table>
        </div>
      </section>`
	    : `<div class="panel"><p class="muted">当前筛选范围没有老师课表。</p></div>`;
	}

	function renderTeacherScopePrompt() {
	  document.getElementById("scheduleSections").innerHTML = `
	    <div class="panel">
	      <p class="muted">请选择老师、子产品、套班或科目后查看老师每日课表。</p>
	    </div>`;
	}

	function render() {
	  if (currentView === "teacherDaily") {
	    classFilterPanel.classList.add("hidden");
	    classSummaryGrid.classList.add("hidden");
	    teacherFilterPanel.classList.remove("hidden");
	    teacherSummaryGrid.classList.remove("hidden");
	    if (!hasTeacherScope()) {
	      renderTeacherPageSummary([]);
	      renderTeacherScopePrompt();
	      return;
	    }
	    const rows = filteredTeacherRows();
	    renderTeacherPageSummary(rows);
	    renderTeacherDaily(rows);
	  } else {
    const rows = filteredClassRows();
    teacherFilterPanel.classList.add("hidden");
    teacherSummaryGrid.classList.add("hidden");
    classFilterPanel.classList.remove("hidden");
    classSummaryGrid.classList.remove("hidden");
    renderMetrics(rows);
    renderConstraints(rows);
    renderTeacherSummary(rows);
    renderSchedules(rows);
  }
}

function init() {
	  document.getElementById("pageTitle").textContent = payload.title;
		  renderFilterOptions();
		  renderLegend();
		  startDateInput.value = defaultStartDate();
		  endDateInput.value = defaultEndDate();
		  teacherStartDateInput.value = defaultStartDate();
		  teacherEndDateInput.value = defaultEndDate();
		  subProductSelect.value = optionValueOrAll(subProductSelect, "无忧秋");
		  suiteSelect.value = "__all__";
	  productLineSelect.addEventListener("change", render);
	  subProductSelect.addEventListener("change", render);
	  productSelect.addEventListener("change", render);
	  suiteSelect.addEventListener("change", render);
	  classSelect.addEventListener("change", render);
	  subjectSelect.addEventListener("change", render);
	  teacherSelect.addEventListener("change", render);
	  courseGroupSelect.addEventListener("change", render);
	  roomSelect.addEventListener("change", render);
	  groupBySelect.addEventListener("change", render);
  stageSelect.addEventListener("change", () => {
    applyStageDateRange();
    render();
  });
		  startDateInput.addEventListener("input", requestRender);
		  endDateInput.addEventListener("input", requestRender);
		  keywordInput.addEventListener("input", requestRender);
	  onlyCourseDatesInput.addEventListener("change", render);
	  teacherDailySelect.addEventListener("change", render);
		  teacherKeywordInput.addEventListener("input", requestRender);
	  teacherSubProductSelect.addEventListener("change", render);
	  teacherSuiteSelect.addEventListener("change", render);
	  teacherSubjectSelect.addEventListener("change", render);
		  teacherStartDateInput.addEventListener("input", requestRender);
		  teacherEndDateInput.addEventListener("input", requestRender);
	  teacherOnlyCourseDatesInput.addEventListener("change", render);
	  document.querySelectorAll("[data-range]").forEach((button) => {
	    button.addEventListener("click", () => {
	      applyDateRange(button.dataset.range || "default", startDateInput, endDateInput);
	      render();
	    });
	  });
	  document.querySelectorAll("[data-teacher-range]").forEach((button) => {
	    button.addEventListener("click", () => {
	      applyDateRange(button.dataset.teacherRange || "default", teacherStartDateInput, teacherEndDateInput);
	      render();
	    });
	  });
  document.querySelectorAll(".view-tab").forEach((button) => {
    button.addEventListener("click", () => {
      currentView = button.dataset.view || "schedule";
      document.querySelectorAll(".view-tab").forEach((item) => item.classList.toggle("active", item === button));
      render();
    });
  });
  document.getElementById("resetButton").addEventListener("click", () => {
    productLineSelect.value = "__all__";
    subProductSelect.value = optionValueOrAll(subProductSelect, "无忧秋");
    suiteSelect.value = "__all__";
	    classSelect.value = "__all__";
	    subjectSelect.value = "__all__";
	    stageSelect.value = "__all__";
	    teacherSelect.value = "__all__";
	    productSelect.value = "__all__";
	    courseGroupSelect.value = "__all__";
	    roomSelect.value = "__all__";
	    groupBySelect.value = "suite";
	    keywordInput.value = "";
	    onlyCourseDatesInput.checked = false;
	    currentView = "schedule";
	    document.querySelectorAll(".view-tab").forEach((item) => item.classList.toggle("active", item.dataset.view === currentView));
	    applyStageDateRange();
	    render();
	  });
	  document.getElementById("teacherResetButton").addEventListener("click", () => {
	    teacherDailySelect.value = "__all__";
	    teacherSubProductSelect.value = "__all__";
	    teacherSuiteSelect.value = "__all__";
	    teacherSubjectSelect.value = "__all__";
	    teacherKeywordInput.value = "";
	    teacherOnlyCourseDatesInput.checked = true;
	    applyDateRange("default", teacherStartDateInput, teacherEndDateInput);
	    render();
	  });
	  render();
	}

init();
</script>
</body>
</html>
"""
    out_path.write_text(
        template.replace("__TITLE__", html.escape(title)).replace("__PAYLOAD__", payload_json),
        encoding="utf-8",
    )

def course_text(
    assignment: scheduler.Assignment,
    room_names: Dict[str, str],
    class_metadata: Optional[Dict[str, Dict[str, str]]] = None,
    product_course_tags: Optional[List[Dict[str, str]]] = None,
) -> str:
    task = assignment.task
    room_id = assignment.candidate.room_id
    room_name = room_names.get(room_id, room_id)
    course_tag = assignment_course_tag(assignment, class_metadata, product_course_tags)
    parts = [
        f"{task.subject} {task.quarter or ''} {task.stage or ''} {task.course_module or ''}".strip(),
        course_tag.get("course_name", ""),
        f"{assignment.candidate.teacher_name or assignment.candidate.teacher_id}",
        room_name,
    ]
    return " / ".join(part for part in parts if part)


def write_batch_csv(
    assignments: Sequence[scheduler.Assignment],
    out_path: Path,
    room_names: Dict[str, str],
    class_metadata: Optional[Dict[str, Dict[str, str]]] = None,
    product_course_tags: Optional[List[Dict[str, str]]] = None,
) -> None:
    class_metadata = class_metadata if class_metadata is not None else load_class_metadata(Path("data"))
    product_course_tags = product_course_tags if product_course_tags is not None else load_product_course_tags(Path("data"))
    rows = []
    for assignment in assignments:
        course_tag = assignment_course_tag(assignment, class_metadata, product_course_tags)
        for lesson in assignment_standard_lesson_slots(assignment.candidate.slots, ["AM", "PM", "EVENING"]):
            rows.append(
                {
                    "date": lesson["date"],
                    "weekday": weekday_label(str(lesson["date"])),
                    "period": lesson["period"],
                    "lesson_slot": lesson["slot_id"],
                    "slot_label": lesson["slot_label"],
                    "start_time": lesson["start_time"],
                    "end_time": lesson["end_time"],
                    "class_id": assignment.task.class_id,
                    "class_name": assignment.task.class_name,
                    "subject": assignment.task.subject,
                    "window_name": assignment.task.quarter or "",
                    "stage": assignment.task.stage or "",
                    "course_module": assignment.task.course_module or "",
                    "course_group": assignment.task.course_group or "",
                    "course_code": course_tag.get("course_code", ""),
                    "course_name": course_tag.get("course_name", ""),
                    "teacher_id": assignment.candidate.teacher_id,
                    "teacher_name": assignment.candidate.teacher_name,
                    "room_id": assignment.candidate.room_id,
                    "room_name": room_names.get(assignment.candidate.room_id, assignment.candidate.room_id),
                    "duration_hours": lesson["duration_hours"],
                }
            )
    write_csv_rows(out_path, BATCH_SCHEDULE_CSV_FIELDNAMES, rows, encoding="utf-8", extrasaction="raise")
