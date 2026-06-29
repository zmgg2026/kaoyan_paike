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

    def test_user_guide_images_are_present_pngs(self) -> None:
        guide = (ROOT / "docs" / "ai-assisted-scheduling-system-user-guide.md").read_text(encoding="utf-8")
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
            ROOT / "docs" / "ai-assisted-scheduling-system-user-guide.md",
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
        self.assertIn("classes.selected_stages", readme)
        self.assertNotIn("classes.stages", readme)

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

    def test_user_guide_includes_audit_commands_and_ai_workflow(self) -> None:
        guide = (ROOT / "docs" / "ai-assisted-scheduling-system-user-guide.md").read_text(encoding="utf-8")

        self.assertIn("# AI辅助排课系统使用攻略", guide)
        self.assertIn("这份攻略面向第一次下载、配置和复用本项目的部门同事", guide)
        self.assertIn("## 目录索引", guide)
        self.assertIn("| 阅读位置 | 章节 | 主要用途 |", guide)
        self.assertIn("| 要改程序时读 | 11. 程序调整的正确顺序 |", guide)
        self.assertIn("bash scripts/verify_release.sh", guide)
        self.assertIn("./scripts/start_admin.sh", guide)
        self.assertIn("https://github.com/zmgg2026/kaoyan_paike", guide)
        self.assertNotIn("zhimagege520-hub", guide)
        self.assertIn("http://127.0.0.1:8765", guide)
        self.assertIn("排课运行维护", guide)
        self.assertIn("scripts/audit_schedule_coverage.py", guide)
        self.assertIn("scripts/audit_schedule_quality.py", guide)
        self.assertIn("硬冲突和覆盖缺口必须处理", guide)
        self.assertIn("共 19 张业务表", guide)
        self.assertIn("老师安排、班级范围、特殊例外和最终验收仍需要业务负责人确认", guide)
        self.assertIn("| 09 | 产品窗口排课规则表 |", guide)
        self.assertIn("| 11 | 班级排课窗口表 |", guide)
        self.assertIn("| 18 | ERP产品对应表 |", guide)
        self.assertIn("报告打开乱码或不可读", guide)
        self.assertIn("如果填写了时段，就必须填写对应日期", guide)
        self.assertIn("缺老师补录表不是另一套新数据", guide)
        self.assertIn("使用前先确认边界", guide)
        self.assertIn("锁定课表、排课运行维护", guide)
        self.assertIn("不要把模板、报告和结果混作同一类文件", guide)
        self.assertIn("给 AI 的材料包", guide)
        self.assertIn("真实业务数据只在本机处理", guide)
        self.assertIn("ERP 回写字段对照", guide)
        self.assertIn("如何让 AI 助理参与", guide)
        self.assertIn("调整程序", guide)
        self.assertIn("程序调整的正确顺序", guide)
        self.assertIn("同步修改模板表、后台页面、导入同步脚本、排课器和报告", guide)
        self.assertIn("修改后必须运行相关单元测试和 bash scripts/verify_release.sh", guide)
        self.assertNotIn("只读发布", guide)
        self.assertNotIn("只读分享", guide)
        self.assertNotIn("发布复用中心", guide)

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
