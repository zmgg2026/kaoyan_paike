from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WebAdminStaticTest(unittest.TestCase):
    def test_class_teacher_search_uses_debounced_render(self) -> None:
        source = (ROOT / "web_admin" / "app.js").read_text(encoding="utf-8")

        self.assertIn("function scheduleClassTeacherSearchRender", source)
        self.assertIn("window.setTimeout(() => {", source)
        self.assertIn("scheduleClassTeacherSearchRender(cursorPosition)", source)
        self.assertIn("flushClassTeacherSearchRender(cursorPosition)", source)

    def test_preflight_panel_renders_missing_teacher_preview(self) -> None:
        source = (ROOT / "web_admin" / "app.js").read_text(encoding="utf-8")

        self.assertIn("preflightResult?.missing_teacher_rows", source)
        self.assertIn("compact-result-table", source)
        self.assertIn("完整清单请下载补录 CSV", source)

    def test_class_teacher_mode_frontend_prefers_current_fields(self) -> None:
        source = (ROOT / "web_admin" / "app.js").read_text(encoding="utf-8")

        self.assertIn("function assignmentScheduleModeValue", source)
        self.assertIn('String(assignment.actual_scheduled_class_id || "").trim()', source)
        self.assertIn("return assignment.schedule_mode || assignment.assignment_mode || \"\";", source)
        self.assertIn("assignmentScheduleModeValue(assignment)", source)
        self.assertIn("assignment.actual_scheduled_class_id || assignment.inherit_from_class_id", source)
        self.assertIn("assignmentScheduleMode(exactExisting, cls)", source)
        self.assertNotIn("assignment.class_schedule_mode || assignment.schedule_mode", source)
        self.assertNotIn("assignment.schedule_mode || assignment.class_schedule_mode", source)
        self.assertNotIn("exactExisting.schedule_mode || exactExisting.class_schedule_mode", source)

        actual_check = "if (actualClass && actualClass !== currentClassId) return \"共享课表\";"
        inherited_check = "if (inheritedClass && inheritedClass !== currentClassId) return \"共享课表\";"
        self.assertLess(source.index(actual_check), source.index(inherited_check))

    def test_class_teacher_mode_edits_treat_self_reference_as_current_class_schedule(self) -> None:
        source = (ROOT / "web_admin" / "app.js").read_text(encoding="utf-8")

        self.assertIn('const requestedMode = normalizeScheduleMode(target.value);', source)
        self.assertIn('if (requestedMode === "共享课表") {', source)
        self.assertIn('assignment.actual_scheduled_class_id && assignment.actual_scheduled_class_id !== currentClassId', source)
        self.assertIn('const sourceClassId = classIdFromPickerValue(target.value) || target.value.trim();', source)
        self.assertIn('if (sourceClassId && sourceClassId !== currentClassId) {', source)
        self.assertIn('assignment.class_schedule_mode = scheduleModeDisplayName("本班实际排课");', source)
        self.assertNotIn('if (assignment.actual_scheduled_class_id) {\n        assignment.class_schedule_mode = scheduleModeDisplayName("共享课表");', source)

    def test_product_rule_guide_uses_season_window_label(self) -> None:
        source = (ROOT / "web_admin" / "app.js").read_text(encoding="utf-8")

        self.assertIn('["季节窗口", "寒假 1-2 月，春季 3-6 月，暑假 7-8 月，秋季 9-12 月。"]', source)
        self.assertNotIn('["全局窗口", "寒假 1-2 月，春季 3-6 月，暑假 7-8 月，秋季 9-12 月。"]', source)

    def test_product_rule_templates_are_season_window_based(self) -> None:
        source = (ROOT / "web_admin" / "app.js").read_text(encoding="utf-8")
        start = source.index("function defaultScheduleRuleTemplates()")
        end = source.index("\nfunction loadScheduleRuleTemplates()", start)
        body = source[start:end]

        self.assertNotIn('"2026-', body)
        self.assertNotIn("RULE_LONG_CAMP_OPEN_NORMAL", body)
        self.assertIn('season_window_id: season.season_window_id || ""', body)
        self.assertIn("window_name: windowName", body)
        self.assertNotIn("rule_name:", body)
        self.assertNotIn("scope_type:", body)
        self.assertNotIn("product_ids:", body)
        self.assertNotIn("product_name_keywords:", body)
        self.assertNotIn('start_date: ""', body)
        self.assertNotIn('end_date: ""', body)
        self.assertNotIn("block_hours_override:", body)
        self.assertIn("same_half_day_4h_same_teacher_required: blockHours >= 4", body)
        self.assertIn('"RULE_WYQ_WINTER_WEEKEND_DAY"', body)

    def test_product_rule_editor_writes_current_fields_only(self) -> None:
        source = (ROOT / "web_admin" / "app.js").read_text(encoding="utf-8")

        self.assertIn('data-field="product_id"', source)
        self.assertIn('data-field="season_window_id"', source)
        self.assertIn('data-field="block_hours"', source)
        self.assertNotIn('data-field="rule_name"', source)
        self.assertNotIn('data-field="scope_type"', source)
        self.assertNotIn('data-field="product_name_keywords"', source)
        self.assertNotIn("产品 / 关键词", source)
        self.assertNotIn("匹配方式", source)
        self.assertNotIn("rule.product_ids =", source)
        self.assertNotIn("rule.scope_type =", source)
        self.assertNotIn("rule.block_hours_override =", source)

    def test_time_slot_summary_uses_current_slot_range(self) -> None:
        source = (ROOT / "web_admin" / "app.js").read_text(encoding="utf-8")

        self.assertIn("const slotRangeLabel = slotDates.length", source)
        self.assertIn('["课节明细", timeSlots.length, slotRangeLabel, ""]', source)
        self.assertNotIn("从 2026-07-01 到 2027-12-21 的课节", source)

    def test_stage_order_uses_current_business_stage_sequence(self) -> None:
        source = (ROOT / "web_admin" / "app.js").read_text(encoding="utf-8")

        self.assertIn('const stageOrder = ["导学", "基础", "强化", "冲刺", "一轮", "二轮", "三轮", "四轮"];', source)
        self.assertIn(r"const numbered = text.match(/^(导学)(\d+)$/);", source)
        self.assertNotIn('const stageOrder = ["导学", "专项", "基础", "强化", "冲刺", "一轮", "二轮", "三轮", "四轮", "复试"];', source)
        self.assertNotIn(r"const numbered = text.match(/^(导学|专项)(\d+)$/);", source)

    def test_business_mapping_editor_writes_current_local_product_field_only(self) -> None:
        source = (ROOT / "web_admin" / "app.js").read_text(encoding="utf-8")

        self.assertIn("mapping.local_product_id = product.id;", source)
        self.assertIn("const product = productById(mapping.local_product_id);", source)
        self.assertNotIn("canonical_product_id", source)

    def test_class_window_ids_are_derived_from_class_window_table(self) -> None:
        source = (ROOT / "web_admin" / "app.js").read_text(encoding="utf-8")

        self.assertIn("function classActualScheduleWindowIds", source)
        self.assertIn("state.class_window_boundaries", source)
        self.assertIn('["年度窗口", listText(classActualScheduleWindowIds(cls))]', source)
        self.assertIn("classActualScheduleWindowIds(cls).join", source)
        self.assertNotIn("actual_schedule_window_ids", source)

    def test_class_lock_editor_writes_current_manual_lock_field(self) -> None:
        source = (ROOT / "web_admin" / "app.js").read_text(encoding="utf-8")

        self.assertIn("function classScheduleLocked", source)
        self.assertIn("cls.is_manual_schedule_locked = classScheduleLocked(cls);", source)
        self.assertIn("delete cls.is_schedule_locked;", source)
        self.assertIn('data-field="is_manual_schedule_locked"', source)
        self.assertNotIn('data-field="is_schedule_locked"', source)
        self.assertNotIn("is_schedule_locked: false", source)
        self.assertIn("const autoClasses = allClasses.filter((cls) => !classScheduleLocked(cls)).length;", source)
        self.assertIn("const lockedClasses = allClasses.filter((cls) => classScheduleLocked(cls)).length;", source)
        self.assertIn('classScheduleLocked(cls) ? "手动锁定" : "自动排课"', source)

    def test_class_stage_editor_writes_current_selected_stages_field(self) -> None:
        source = (ROOT / "web_admin" / "app.js").read_text(encoding="utf-8")

        self.assertIn("function classSelectedStages", source)
        self.assertIn("function setClassSelectedStages", source)
        self.assertIn('delete cls.stages;', source)
        self.assertIn('data-field="${target.dataset.field}"', source)
        self.assertIn('entityCheckboxOptions("class", cls.id, "selected_stages"', source)
        self.assertIn('if (target.dataset.field === "selected_stages")', source)
        self.assertNotIn('entityCheckboxOptions("class", cls.id, "stages"', source)
        self.assertNotIn('target.dataset.field === "stages"', source)
        self.assertIsNone(re.search(r"(?m)^\s*stages:\s*\[\],", source))
        self.assertNotIn("cls.stages =", source)

    def test_class_conflict_frontend_edits_current_fields(self) -> None:
        source = (ROOT / "web_admin" / "app.js").read_text(encoding="utf-8")

        self.assertIn("function conflictGroupIsActive", source)
        self.assertIn("function conflictGroupSource", source)
        self.assertIn('data-field="is_conflict_group_active"', source)
        self.assertIn('data-field="conflict_source"', source)
        self.assertIn("conflictGroupIsActive(group)", source)
        self.assertIn("conflictGroupSource(group)", source)
        self.assertIn("is_conflict_group_active: true", source)
        self.assertIn('conflict_source: "手动"', source)
        self.assertIn('conflict_source: "套班编码"', source)
        self.assertNotIn('if (field === "is_conflict_group_active") item.is_active = value;', source)
        self.assertNotIn('if (field === "conflict_source") item.source = value;', source)
        self.assertNotIn(
            'data-list="class_conflict_groups" data-index="${index}" data-field="is_active"',
            source,
        )
        self.assertNotIn(
            'data-list="class_conflict_groups" data-index="${index}" data-field="source"',
            source,
        )

    def test_teacher_resource_editor_writes_current_fields_only(self) -> None:
        source = (ROOT / "web_admin" / "app.js").read_text(encoding="utf-8")

        self.assertIn("function teacherId(teacher)", source)
        self.assertIn('data-list="teachers" data-index="${index}" data-field="employee_id"', source)
        self.assertIn('if (field === "employee_id") {', source)
        self.assertIn("delete teacher.id;", source)
        self.assertIn("teacher_role: \"\",", source)
        self.assertIn("employment_type: \"\",", source)
        self.assertNotIn('data-list="teachers" data-index="${index}" data-field="id"', source)
        self.assertNotIn("identity: \"\",", source)
        self.assertNotIn("teacher_type: \"\",", source)
        self.assertNotIn("teacher.identity = value;", source)
        self.assertNotIn("teacher.teacher_type = value;", source)

    def test_product_course_editor_writes_current_fields_only(self) -> None:
        source = (ROOT / "web_admin" / "app.js").read_text(encoding="utf-8")

        self.assertIn("function productCourseWindowName", source)
        self.assertIn("function productCourseModulePriority", source)
        self.assertIn('data-field="window_name"', source)
        self.assertIn('selected.courseFilters.window_name', source)
        self.assertIn('return ["window_name", "stage", "course_module", "course_name", "course_group"];', source)
        self.assertIn("delete course.quarter;", source)
        self.assertIn("delete course.module_priority;", source)

        start = source.index("function addCourse()")
        end = source.index("\nfunction productCourseModuleKey", start)
        body = source[start:end]
        self.assertIn("window_name: \"\",", body)
        self.assertIn("module_priority_in_group: 0,", body)
        self.assertNotIn("quarter:", body)
        self.assertNotIn("module_priority:", body)
        self.assertNotIn("block_hours:", body)

    def test_publish_page_uses_utf8_markdown_previews(self) -> None:
        source = (ROOT / "web_admin" / "app.js").read_text(encoding="utf-8")
        index = (ROOT / "web_admin" / "index.html").read_text(encoding="utf-8")

        self.assertIn("发布复用中心", index)
        self.assertIn('publish: ["发布复用中心"', source)
        self.assertIn('const scheduleReportPreviewUrl = "/preview/outputs/batch_schedule_maintenance_report.md";', source)
        self.assertIn('const scheduleReportRawUrl = "/outputs/batch_schedule_maintenance_report.md";', source)
        self.assertIn('"/preview/docs/ai-assisted-scheduling-system-user-guide.md"', source)
        self.assertIn('"/preview/docs/ai-scheduling-reuse-playbook.md"', source)
        self.assertIn('"/preview/docs/ai-scheduling-sop.md"', source)
        self.assertNotIn('["排课报告", "查看覆盖、冲突和缺口结论", "/outputs/batch_schedule_maintenance_report.md"]', source)

    def test_launch_page_uses_result_file_status_cards(self) -> None:
        source = (ROOT / "web_admin" / "app.js").read_text(encoding="utf-8")
        styles = (ROOT / "web_admin" / "styles.css").read_text(encoding="utf-8")

        self.assertIn('requestJson("/api/results/status")', source)
        self.assertIn("function fileCard(entry, fallback)", source)
        self.assertIn("currentResultCards()", source)
        self.assertIn("未生成的文件不会显示成可点击链接", source)
        self.assertIn(".result-file-grid", styles)
        self.assertIn(".result-file-card.missing", styles)
        self.assertNotIn("batch-result-links", source)
        self.assertNotIn("batch-result-links", styles)


if __name__ == "__main__":
    unittest.main()
