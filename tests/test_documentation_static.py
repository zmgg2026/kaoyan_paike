from __future__ import annotations

import re
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

    def test_docs_do_not_reintroduce_teacher_available_slot_language(self) -> None:
        targets = [
            ROOT / "README.md",
            ROOT / "scheduler.py",
            ROOT / "run_scheduling_pipeline.py",
            ROOT / "docs" / "ai-scheduling-sop.md",
            ROOT / "docs" / "department-reuse-user-guide.md",
        ]
        forbidden_terms = [
            "老师" + "可用" + "课节",
            "教师" + "可用" + "课节",
            "老师" + "可用" + "时段",
            "教师" + "可用" + "时段",
        ]
        offenders = []
        for path in targets:
            source = path.read_text(encoding="utf-8")
            matches = [term for term in forbidden_terms if term in source]
            if matches:
                offenders.append(f"{path.relative_to(ROOT)}: {', '.join(matches)}")

        self.assertEqual([], offenders)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("教师不可排例外过多，或班级排课窗口过窄", readme)
        scheduler_source = (ROOT / "scheduler.py").read_text(encoding="utf-8")
        self.assertIn("教师不可排日期时段、班级排课窗口、教室资源或互斥关系", scheduler_source)

    def test_readme_describes_schedule_range_as_template_driven(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertNotIn("当前排课范围按 `2026-07-01` 到 `2026-12-13` 处理", readme)
        self.assertNotIn("157 个可排课日期、785 个可用课节", readme)
        self.assertIn("正式排课范围以 `01_年度排课窗口表`、`02_课节表` 和 `11_班级排课窗口表` 为准", readme)

    def test_release_checklist_does_not_require_private_data(self) -> None:
        checklist = (ROOT / "docs" / "github-release-checklist.md").read_text(encoding="utf-8")

        self.assertNotIn("--source data --preflight", checklist)
        self.assertNotIn("372 条缺老师", checklist)
        self.assertIn("真实 `data/` 不进入 GitHub 发布包", checklist)
        self.assertIsNone(re.search(r"当前\s*\d+\s*个测试", checklist))
        self.assertIn("具体测试数量以本次命令输出为准", checklist)

    def test_class_base_docs_do_not_reintroduce_window_id_list_field(self) -> None:
        sop = (ROOT / "docs" / "ai-scheduling-sop.md").read_text(encoding="utf-8")
        example_classes = (ROOT / "examples" / "csv_minimal" / "classes.csv").read_text(encoding="utf-8")

        self.assertIn("实际年度窗口列表由班级排课窗口表生成和展示", sop)
        self.assertNotIn("班级实际排课窗口ID列表", sop)
        self.assertNotIn("actual_schedule_window_ids", example_classes.splitlines()[0])

    def test_department_guide_includes_audit_commands(self) -> None:
        guide = (ROOT / "docs" / "department-reuse-user-guide.md").read_text(encoding="utf-8")

        self.assertIn("scripts/audit_schedule_coverage.py", guide)
        self.assertIn("scripts/audit_schedule_quality.py", guide)
        self.assertIn("硬冲突和覆盖缺口必须处理", guide)
        self.assertIn("共 19 张业务表", guide)
        self.assertIn("系统能重点解决：上课时间安排、课程模块顺序、教室安排、联报班级冲突、老师同日跨教学区通勤质检", guide)
        self.assertIn("老师安排本身仍需要教务和教学提前规划", guide)
        self.assertIn("| 09 | 产品窗口排课规则表 |", guide)
        self.assertIn("| 11 | 班级排课窗口表 |", guide)
        self.assertIn("| 18 | ERP产品对应表 |", guide)
        self.assertIn("报告打开乱码或不可读", guide)
        self.assertIn("first_lesson_period` 必须有 `first_lesson_date", guide)
        self.assertIn("缺老师补录表不是另一套新数据", guide)
        self.assertIn("先分清三件事", guide)
        self.assertIn("发布复用中心：验收后的交付入口", guide)
        self.assertIn("不要把模板、报告和结果混作同一类文件", guide)

    def test_share_and_template_do_not_reintroduce_merge_detail_table_language(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        share = (ROOT / "share" / "ai-scheduling-project" / "index.html").read_text(encoding="utf-8")
        template_source = (ROOT / "formal_template.py").read_text(encoding="utf-8")

        self.assertIn("共享课表关系转成标准排课输入", share)
        self.assertIn("不需要额外维护第二张合班表", readme)
        self.assertNotIn("合班课程明细表", readme)
        self.assertNotIn("合班" + "明细", share)
        self.assertNotIn("merge_" + "course_" + "details", readme)
        self.assertNotIn("低层业务导入", readme)
        self.assertNotIn("build_" + "merge_" + "rows", template_source)
        self.assertNotIn("first_" + "merge_" + "code", template_source)
        self.assertNotIn("full" + " 或 " + "partial", template_source)
        self.assertIn("ERP产品对应", template_source)
        self.assertIn("在 local_product_id 填本地产品 ID", template_source)
        self.assertNotIn("兼容字段 canonical_product_id", template_source)
        self.assertNotIn("部分课程例外", template_source)


if __name__ == "__main__":
    unittest.main()
