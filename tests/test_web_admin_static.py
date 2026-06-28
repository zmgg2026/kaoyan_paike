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

        self.assertIn("assignment.class_schedule_mode || assignment.schedule_mode", source)
        self.assertIn("assignment.actual_scheduled_class_id || assignment.inherit_from_class_id", source)
        self.assertIn("assignmentScheduleMode(exactExisting, cls)", source)
        self.assertNotIn("assignment.schedule_mode || assignment.class_schedule_mode", source)
        self.assertNotIn("exactExisting.schedule_mode || exactExisting.class_schedule_mode", source)

    def test_product_rule_guide_uses_season_window_label(self) -> None:
        source = (ROOT / "web_admin" / "app.js").read_text(encoding="utf-8")

        self.assertIn('["季节窗口", "寒假 1-2 月，春季 3-6 月，暑假 7-8 月，秋季 9-12 月。"]', source)
        self.assertNotIn('["全局窗口", "寒假 1-2 月，春季 3-6 月，暑假 7-8 月，秋季 9-12 月。"]', source)


if __name__ == "__main__":
    unittest.main()
