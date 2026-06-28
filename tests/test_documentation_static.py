from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DocumentationStaticTest(unittest.TestCase):
    def test_product_course_docs_do_not_own_block_hours(self) -> None:
        presentation = (ROOT / "docs" / "ai-scheduling-presentation-script.md").read_text(encoding="utf-8")
        playbook = (ROOT / "docs" / "ai-scheduling-reuse-playbook.md").read_text(encoding="utf-8")
        sop = (ROOT / "docs" / "ai-scheduling-sop.md").read_text(encoding="utf-8")

        self.assertIn("产品窗口规则再单独约束单次连续课时", presentation)
        self.assertIn("| 产品窗口规则表 | 产品 ID、季节窗口、授课形式、可排星期、可排时段、单次连续课时 |", playbook)
        self.assertIn("课程总课时不能被产品窗口规则里的单次连续课时整除", sop)

        self.assertNotIn("产品课程有科目、阶段、模块、课程分组、总课时和单次连续课时", presentation)
        self.assertNotIn("| 产品课程表 | 产品 ID、科目、阶段、模块、课程分组、总课时、单次连续课时 |", playbook)
        self.assertNotIn("课程课时不能被单次连续课时整除", sop)

    def test_department_user_guide_images_are_present_pngs(self) -> None:
        guide = (ROOT / "docs" / "department-reuse-user-guide.md").read_text(encoding="utf-8")
        for image_name in ("admin-overview.png", "admin-launch.png"):
            image_path = ROOT / "docs" / "assets" / "user-guide" / image_name
            self.assertIn(f"assets/user-guide/{image_name}", guide)
            self.assertTrue(image_path.exists(), image_name)
            self.assertEqual(b"\x89PNG\r\n\x1a\n", image_path.read_bytes()[:8], image_name)


if __name__ == "__main__":
    unittest.main()
