from __future__ import annotations

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
        self.assertIn('start_date: ""', body)
        self.assertIn('end_date: ""', body)
        self.assertIn("same_half_day_4h_same_teacher_required: blockHours >= 4", body)
        self.assertIn('"RULE_WYQ_WINTER_WEEKEND_DAY"', body)

    def test_time_slot_summary_uses_current_slot_range(self) -> None:
        source = (ROOT / "web_admin" / "app.js").read_text(encoding="utf-8")

        self.assertIn("const slotRangeLabel = slotDates.length", source)
        self.assertIn('["课节明细", timeSlots.length, slotRangeLabel, ""]', source)
        self.assertNotIn("从 2026-07-01 到 2027-12-21 的课节", source)

    def test_business_mapping_editor_writes_current_local_product_field_only(self) -> None:
        source = (ROOT / "web_admin" / "app.js").read_text(encoding="utf-8")

        self.assertIn("mapping.local_product_id = product.id;", source)
        self.assertIn("mapping.local_product_id || mapping.canonical_product_id", source)
        self.assertNotIn("canonical_product_id: product.id", source)
        self.assertNotIn("mapping.canonical_product_id = product.id", source)

    def test_class_window_ids_are_derived_from_class_window_table(self) -> None:
        source = (ROOT / "web_admin" / "app.js").read_text(encoding="utf-8")

        self.assertIn("function classActualScheduleWindowIds", source)
        self.assertIn("state.class_window_boundaries", source)
        self.assertIn('["年度窗口", listText(classActualScheduleWindowIds(cls))]', source)
        self.assertIn("classActualScheduleWindowIds(cls).join", source)
        self.assertNotIn("actual_schedule_window_ids: []", source)

    def test_class_conflict_frontend_edits_current_fields(self) -> None:
        source = (ROOT / "web_admin" / "app.js").read_text(encoding="utf-8")

        self.assertIn("function conflictGroupIsActive", source)
        self.assertIn("function conflictGroupSource", source)
        self.assertIn('data-field="is_conflict_group_active"', source)
        self.assertIn('data-field="conflict_source"', source)
        self.assertIn("conflictGroupIsActive(group)", source)
        self.assertIn("conflictGroupSource(group)", source)
        self.assertIn('if (field === "is_conflict_group_active") item.is_active = value;', source)
        self.assertIn('if (field === "conflict_source") item.source = value;', source)
        self.assertIn("is_conflict_group_active: true", source)
        self.assertIn('conflict_source: "手动"', source)
        self.assertIn('conflict_source: "套班编码"', source)
        self.assertNotIn(
            'data-list="class_conflict_groups" data-index="${index}" data-field="is_active"',
            source,
        )
        self.assertNotIn(
            'data-list="class_conflict_groups" data-index="${index}" data-field="source"',
            source,
        )


if __name__ == "__main__":
    unittest.main()
