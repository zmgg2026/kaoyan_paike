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


if __name__ == "__main__":
    unittest.main()
