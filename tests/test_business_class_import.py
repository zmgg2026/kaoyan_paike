from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import data_admin_server
from business_class_import import (
    BusinessDataError,
    assignments_by_class,
    convert_business_tables,
    product_courses_by_id,
    resolve_teacher_assignment,
)
from run_scheduling_pipeline import run_pipeline, table_name_for


ORIGINAL_DATA_DIR = data_admin_server.DATA_DIR


def table(rows: list[dict[str, object]]) -> SimpleNamespace:
    return SimpleNamespace(rows=rows)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


BUSINESS_HEADERS = [
    "班级编码",
    "班级名称（外）",
    "实际开课日期",
    "实际结课日期",
    "标准人数",
    "当前人数(占名额)",
    "授课教师",
    "合班状态",
    "班级状态",
    "合班详情",
    "排课完成状态",
    "校区编码",
    "校区名称",
    "教室编码",
    "上课教室",
    "教室座位数",
    "教室最大座位数",
    "班容类型",
    "产品体系",
    "考试月份",
    "管理项目",
    "课程产品编号",
    "课程产品名称",
]


def business_row(
    class_id: str,
    product_id: str = "100",
    product_name: str = "考研英语无忧计划全年班",
    product_system: str = "常规体系",
    exam_month: str = " 2026-12\t",
    project: str = "考研/考博",
    start: str = "2026/6/1",
    end: str = "2026/12/2",
    room_id: str = "R1",
    teacher: str = "张老师(T1)",
    merge_detail: str = "",
) -> dict[str, object]:
    return {
        "班级编码": class_id,
        "班级名称（外）": f"{product_name}（{class_id}）",
        "实际开课日期": start,
        "实际结课日期": end,
        "标准人数": "50",
        "当前人数(占名额)": "30",
        "授课教师": teacher,
        "合班状态": "是" if merge_detail else "否",
        "班级状态": "已被合班" if merge_detail else "正常",
        "合班详情": merge_detail,
        "排课完成状态": "未完成",
        "校区编码": "A1",
        "校区名称": "主校区",
        "教室编码": room_id,
        "上课教室": f"{room_id}教室",
        "教室座位数": "80",
        "教室最大座位数": "80",
        "班容类型": "班课",
        "产品体系": product_system,
        "考试月份": exam_month,
        "管理项目": project,
        "课程产品编号": product_id,
        "课程产品名称": product_name,
    }


def base_payload(two_courses: bool = False) -> dict[str, list[dict[str, object]]]:
    courses = [
        {
            "product_id": "P_REG",
            "product_name": "考研英语无忧计划全年班",
            "subject_category": "公共课",
            "subject": "英语",
            "stage": "基础",
            "course_module": "词汇",
            "course_group": "阅读类",
            "total_hours": "4",
            "block_hours": "4",
            "teaching_area_ids": "A1",
        },
        {
            "product_id": "P_SPECIAL",
            "product_name": "考研英语导学营",
            "subject_category": "公共课",
            "subject": "英语",
            "stage": "基础",
            "course_module": "词汇",
            "course_group": "阅读类",
            "total_hours": "4",
            "block_hours": "4",
            "teaching_area_ids": "A1",
        },
    ]
    if two_courses:
        courses.append(
            {
                "product_id": "P_REG",
                "product_name": "考研英语无忧计划全年班",
                "subject_category": "公共课",
                "subject": "英语",
                "stage": "基础",
                "course_module": "阅读",
                "course_group": "阅读类",
                "total_hours": "4",
                "block_hours": "4",
                "teaching_area_ids": "A1",
            }
        )
    return {
        "teaching_areas": [],
        "rooms": [],
        "teachers": [],
        "products": [
            {"id": "P_REG", "name": "考研英语无忧计划全年班", "project": "考研", "product_system": "常规体系", "subject": "英语", "subject_category": "公共课", "standard_capacity": "50"},
            {"id": "P_SPECIAL", "name": "考研英语导学营", "project": "考研", "product_system": "专项体系", "subject": "英语", "subject_category": "公共课", "standard_capacity": "50"},
        ],
        "product_courses": courses,
        "product_schedule_rules": [],
        "classes": [],
        "class_teacher_assignments": [],
        "teaching_area_links": [],
        "global_blackout_dates": [],
    }


def assignment(class_id: str, module: str = "词汇", teacher_id: str = "T1") -> dict[str, object]:
    return {
        "class_id": class_id,
        "subject": "英语",
        "stage": "基础",
        "course_module": module,
        "course_group": "阅读类",
        "teacher_id": teacher_id,
        "teacher_name": f"{teacher_id}老师",
    }


def scheduled_lesson(
    class_id: str,
    module: str = "词汇",
    teacher_id: str = "T1",
    teacher_name: str = "T1老师",
    date: str = "2026/6/1",
    duration: str = "4",
) -> dict[str, object]:
    return {
        "class_id": class_id,
        "class_name": f"{class_id}班",
        "date": date,
        "start_time": "08:00",
        "end_time": "12:00",
        "duration_hours": duration,
        "teacher_id": teacher_id,
        "teacher_name": teacher_name,
        "room_id": "R1",
        "business_product_id": "100",
        "business_product_name": "考研英语无忧计划全年班",
        "subject": "英语",
        "stage": "基础",
        "course_module": module,
        "course_group": "阅读类",
    }


class BusinessClassImportTest(unittest.TestCase):
    def tearDown(self) -> None:
        data_admin_server.DATA_DIR = ORIGINAL_DATA_DIR

    def test_business_csv_pipeline_filters_scope_and_generates_schedule(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "incoming"
            data_dir = root / "data"
            output_dir = root / "outputs"
            payload = base_payload()
            write_csv(source / "products.csv", ["id", "name", "project", "product_system", "subject", "subject_category", "standard_capacity"], payload["products"])
            write_csv(source / "product_courses.csv", ["product_id", "product_name", "subject_category", "subject", "stage", "course_module", "course_group", "total_hours", "block_hours", "teaching_area_ids"], payload["product_courses"])
            write_csv(
                source / "20260429班级查询导出.csv",
                BUSINESS_HEADERS,
                [
                    business_row("C_REG", room_id="R1", teacher="张老师(T1)"),
                    business_row("C_SPECIAL", product_id="101", product_name="考研英语导学营", product_system="专项体系", room_id="R2", teacher="李老师(T2)"),
                    business_row("C_BILL", product_id="102", product_name="考研住宿费班", product_system="计费体系", room_id="R3"),
                    business_row("C_OTHER", project="专升本"),
                    business_row("C_OUTSIDE", end="2026/6/30"),
                ],
            )
            write_csv(
                source / "business_product_mappings.csv",
                ["business_product_id", "business_product_name", "canonical_product_id"],
                [
                    {"business_product_id": "100", "business_product_name": "考研英语无忧计划全年班", "canonical_product_id": "P_REG"},
                    {"business_product_id": "101", "business_product_name": "考研英语导学营", "canonical_product_id": "P_SPECIAL"},
                ],
            )
            write_csv(
                source / "class_teacher_assignments.csv",
                ["class_id", "subject", "stage", "course_module", "course_group", "teacher_id", "teacher_name"],
                [assignment("C_REG", teacher_id="T1"), assignment("C_SPECIAL", teacher_id="T2")],
            )

            result = run_pipeline(
                SimpleNamespace(
                    source=str(source),
                    data_dir=str(data_dir),
                    output_dir=str(output_dir),
                    timestamp="20260430_120000",
                    exclude_weekdays="Sun",
                    slot_set="all",
                )
            )

            scheduler_input = json.loads((data_dir / "scheduler_input_draft.json").read_text(encoding="utf-8"))
            self.assertEqual({cls["id"] for cls in scheduler_input["classes"]}, {"C_REG", "C_SPECIAL"})
            self.assertEqual({cls["exam_season"] for cls in scheduler_input["classes"]}, {"27考研"})
            self.assertEqual({cls["exam_month"] for cls in scheduler_input["classes"]}, {"2026-12"})
            self.assertTrue(all(cls["start_date"] == "2026-07-01" for cls in scheduler_input["classes"]))
            self.assertTrue(result.schedule_csv_path.exists())
            report = result.report_path.read_text(encoding="utf-8")
            self.assertIn("计费体系已排除", report)
            self.assertIn("业务班级纳入排课 2 个", report)
            self.assertNotIn("scheduling_scope_overrides", report)

    def test_scheduled_lessons_table_aliases_are_supported(self) -> None:
        self.assertEqual(table_name_for("scheduled_lessons.csv"), "scheduled_lessons")
        self.assertEqual(table_name_for("已排课明细.csv"), "scheduled_lessons")
        self.assertEqual(table_name_for("历史课表.xlsx"), "scheduled_lessons")

    def test_history_lessons_deduct_remaining_hours_and_learn_teacher(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "incoming"
            data_dir = root / "data"
            output_dir = root / "outputs"
            payload = base_payload()
            payload["product_courses"][0]["total_hours"] = "20"
            write_csv(source / "products.csv", ["id", "name", "project", "product_system", "subject", "subject_category", "standard_capacity"], payload["products"])
            write_csv(source / "product_courses.csv", ["product_id", "product_name", "subject_category", "subject", "stage", "course_module", "course_group", "total_hours", "block_hours", "teaching_area_ids"], payload["product_courses"])
            write_csv(source / "20260429班级查询导出.csv", BUSINESS_HEADERS, [business_row("C_REG")])
            write_csv(source / "business_product_mappings.csv", ["business_product_id", "canonical_product_id"], [{"business_product_id": "100", "canonical_product_id": "P_REG"}])
            write_csv(
                source / "已排课明细.csv",
                ["班级编码", "上课日期", "开始时间", "结束时间", "课时", "教师编码", "教师姓名", "教室编码", "课程产品编号", "课程产品名称", "科目", "阶段", "课程模块", "课程组"],
                [
                    {
                        "班级编码": "C_REG",
                        "上课日期": "2026/6/1",
                        "开始时间": "08:00",
                        "结束时间": "16:00",
                        "课时": "8",
                        "教师编码": "T_HIST",
                        "教师姓名": "历史老师",
                        "教室编码": "R1",
                        "课程产品编号": "100",
                        "课程产品名称": "考研英语无忧计划全年班",
                        "科目": "英语",
                        "阶段": "基础",
                        "课程模块": "词汇",
                        "课程组": "阅读类",
                    }
                ],
            )

            result = run_pipeline(
                SimpleNamespace(
                    source=str(source),
                    data_dir=str(data_dir),
                    output_dir=str(output_dir),
                    timestamp="20260430_130000",
                    exclude_weekdays="Sun",
                    slot_set="all",
                )
            )

            scheduler_input = json.loads((data_dir / "scheduler_input_draft.json").read_text(encoding="utf-8"))
            cls = scheduler_input["classes"][0]
            self.assertEqual(cls["requirements"][0]["total_hours"], 12)
            self.assertEqual(cls["requirements"][0]["teacher_id"], "T_HIST")
            self.assertTrue((output_dir / "learned_class_teacher_assignments_20260430_130000.csv").exists())
            self.assertTrue((output_dir / "learned_product_course_hours_20260430_130000.csv").exists())
            self.assertIn("27考研已排课时抵扣", result.report_path.read_text(encoding="utf-8"))

    def test_product_system_selection_includes_regular_and_special_excludes_billing(self) -> None:
        rows = [
            business_row("C_REG"),
            business_row("C_SPECIAL", product_id="101", product_name="考研英语导学营", product_system="专项体系"),
            business_row("C_BILL", product_id="102", product_name="考研住宿费班", product_system="计费体系"),
        ]
        tables = {
            "business_classes": table(rows),
            "business_product_mappings": table([
                {"business_product_id": "100", "canonical_product_id": "P_REG"},
                {"business_product_id": "101", "canonical_product_id": "P_SPECIAL"},
                {"business_product_id": "102", "canonical_product_id": "P_REG"},
            ]),
            "class_teacher_assignments": table([assignment("C_REG"), assignment("C_SPECIAL")]),
        }

        result = convert_business_tables(tables, base_payload())

        self.assertEqual([cls["id"] for cls in result.payload["classes"]], ["C_REG", "C_SPECIAL"])
        self.assertTrue(any("计费体系已排除" in warning for warning in result.warnings))

    def test_uploaded_teacher_assignment_wins_over_history_learning(self) -> None:
        payload = base_payload()
        payload["product_courses"][0]["total_hours"] = "20"
        tables = {
            "business_classes": table([business_row("C_REG")]),
            "business_product_mappings": table([{"business_product_id": "100", "canonical_product_id": "P_REG"}]),
            "class_teacher_assignments": table([assignment("C_REG", teacher_id="T_UPLOAD")]),
            "scheduled_lessons": table([scheduled_lesson("C_REG", teacher_id="T_HIST", teacher_name="历史老师")]),
        }

        result = convert_business_tables(tables, payload)
        cls = result.payload["classes"][0]

        self.assertEqual(cls["teacher_assignments"][0]["teacher_id"], "T_UPLOAD")
        self.assertEqual(cls["requirements"][0]["teacher_id"], "T_UPLOAD")

    def test_multi_product_mapping_candidate_values_are_aggregated(self) -> None:
        payload = base_payload()
        payload["products"].append({"id": "P_EXTRA", "name": "考研英语补充产品", "project": "考研", "product_system": "常规体系", "subject": "英语", "subject_category": "公共课", "standard_capacity": "50"})
        payload["product_courses"].append(
            {
                "product_id": "P_EXTRA",
                "product_name": "考研英语补充产品",
                "subject_category": "公共课",
                "subject": "英语",
                "stage": "基础",
                "course_module": "语法",
                "course_group": "写作类",
                "total_hours": "6",
                "block_hours": "2",
                "teaching_area_ids": "A1",
            }
        )
        tables = {
            "business_classes": table([business_row("C_REG")]),
            "business_product_mappings": table([
                {"business_product_id": "100", "canonical_product_id": "P_REG:考研英语无忧计划全年班|P_EXTRA:考研英语补充产品"}
            ]),
            "class_teacher_assignments": table([
                assignment("C_REG", "词汇", "T1"),
                {
                    "class_id": "C_REG",
                    "subject": "英语",
                    "stage": "基础",
                    "course_module": "语法",
                    "course_group": "写作类",
                    "teacher_id": "T2",
                    "teacher_name": "T2老师",
                },
            ]),
        }

        result = convert_business_tables(tables, payload)
        cls = result.payload["classes"][0]

        self.assertEqual(cls["product_id"], "BIZ_100")
        self.assertIn("BIZ_100", {product["id"] for product in result.payload["products"]})
        aggregate_courses = [course for course in result.payload["product_courses"] if course["product_id"] == "BIZ_100"]
        self.assertEqual({course["course_module"] for course in aggregate_courses}, {"词汇", "语法"})

    def test_multi_product_mapping_can_split_by_class_name_keywords(self) -> None:
        payload = base_payload()
        payload["products"] = [
            {"id": "P_HS", "name": "考研寒暑营-正课-英语", "project": "考研", "product_system": "常规体系", "subject": "英语", "subject_category": "公共课", "standard_capacity": "50"},
            {"id": "P_SJ", "name": "考研暑假营-正课-英语", "project": "考研", "product_system": "常规体系", "subject": "英语", "subject_category": "公共课", "standard_capacity": "50"},
        ]
        payload["product_courses"] = [
            {
                **payload["product_courses"][0],
                "product_id": "P_HS",
                "product_name": "考研寒暑营-正课-英语",
            },
            {
                **payload["product_courses"][0],
                "product_id": "P_SJ",
                "product_name": "考研暑假营-正课-英语",
            },
        ]
        tables = {
            "business_classes": table([
                business_row("C_HS", product_name="考研英语全程寒暑集训营"),
                {
                    **business_row("C_SJ", product_name="考研英语全程寒暑集训营"),
                    "班级名称（外）": "考研英语暑假集训营（27届91班）",
                },
            ]),
            "business_product_mappings": table([
                {
                    "business_product_id": "100",
                    "canonical_product_id": "P_HS:考研寒暑营-正课-英语|P_SJ:考研暑假营-正课-英语",
                }
            ]),
            "class_teacher_assignments": table([assignment("C_HS"), assignment("C_SJ")]),
        }

        result = convert_business_tables(tables, payload)
        product_by_class = {cls["id"]: cls["product_id"] for cls in result.payload["classes"]}

        self.assertEqual(product_by_class["C_HS"], "P_HS")
        self.assertEqual(product_by_class["C_SJ"], "P_SJ")

    def test_wuyou_products_split_by_class_name_before_stage_words(self) -> None:
        payload = base_payload()
        payload["products"] = [
            {"id": "P_Q", "name": "考研无忧秋-正课-英语", "project": "考研", "product_system": "常规体系", "subject": "英语", "subject_category": "公共课", "standard_capacity": "50"},
            {"id": "P_C", "name": "考研无忧春-正课-英语", "project": "考研", "product_system": "常规体系", "subject": "英语", "subject_category": "公共课", "standard_capacity": "50"},
            {"id": "P_H", "name": "考研无忧寒-正课-英语", "project": "考研", "product_system": "常规体系", "subject": "英语", "subject_category": "公共课", "standard_capacity": "50"},
            {"id": "P_S", "name": "考研无忧暑-正课-英语", "project": "考研", "product_system": "常规体系", "subject": "英语", "subject_category": "公共课", "standard_capacity": "50"},
        ]
        payload["product_courses"] = [
            {
                **payload["product_courses"][0],
                "product_id": product["id"],
                "product_name": product["name"],
            }
            for product in payload["products"]
        ]
        rows = []
        for class_id, class_name in [
            ("C_Q", "考研英语无忧秋导学班（27届03班）暑假面授-阶段2"),
            ("C_C", "考研英语无忧春导学班（27届23班）阶段2-面授-大学城"),
            ("C_H", "考研英语无忧寒导学班（27届12班）春季直播-阶段1"),
            ("C_S", "考研英语无忧暑导学班（27届31班）春季直播-阶段1"),
            ("C_PLAN_C", "考研英语无忧计划（27届03班）春-磬苑"),
            ("C_PLAN_S", "考研英语无忧计划（27届31班）暑"),
        ]:
            item = business_row(class_id)
            item["班级名称（外）"] = class_name
            rows.append(item)
        tables = {
            "business_classes": table(rows),
            "business_product_mappings": table([
                {
                    "business_product_id": "100",
                    "canonical_product_id": "P_Q:考研无忧秋-正课-英语|P_H:考研无忧寒-正课-英语|P_C:考研无忧春-正课-英语|P_S:考研无忧暑-正课-英语",
                }
            ]),
            "class_teacher_assignments": table([
                assignment("C_Q"),
                assignment("C_C"),
                assignment("C_H"),
                assignment("C_S"),
                assignment("C_PLAN_C"),
                assignment("C_PLAN_S"),
            ]),
        }

        result = convert_business_tables(tables, payload)
        product_by_class = {cls["id"]: cls["product_id"] for cls in result.payload["classes"]}

        self.assertEqual(
            product_by_class,
            {"C_Q": "P_Q", "C_C": "P_C", "C_H": "P_H", "C_S": "P_S", "C_PLAN_C": "P_C", "C_PLAN_S": "P_S"},
        )

    def test_teacher_assignment_uses_stage_group_and_first_stage_fallback(self) -> None:
        payload = base_payload(two_courses=True)
        payload["product_courses"][0]["stage"] = "基础"
        payload["product_courses"][0]["course_module"] = "词汇"
        payload["product_courses"][0]["course_group"] = "阅读类"
        payload["product_courses"][1]["stage"] = "强化"
        payload["product_courses"][1]["course_module"] = "阅读"
        payload["product_courses"][1]["course_group"] = "阅读类"
        tables = {
            "business_classes": table([business_row("C_REG")]),
            "business_product_mappings": table([{"business_product_id": "100", "canonical_product_id": "P_REG"}]),
            "class_teacher_assignments": table([
                {
                    "class_id": "C_REG",
                    "product_id": "P_REG",
                    "subject": "英语",
                    "stage": "基础",
                    "course_group": "阅读类",
                    "teacher_id": "T_BASE",
                    "teacher_name": "基础老师",
                }
            ]),
        }

        result = convert_business_tables(tables, payload)
        class_assignments = assignments_by_class(tables["class_teacher_assignments"].rows)["C_REG"]
        courses = product_courses_by_id(result.payload)["P_REG"]
        teachers_by_module = {
            course["course_module"]: resolve_teacher_assignment(course, "P_REG", class_assignments, courses)["teacher_id"]
            for course in courses
        }

        self.assertEqual(teachers_by_module, {"词汇": "T_BASE", "阅读": "T_BASE"})

    def test_history_teacher_conflict_uses_latest_lesson_and_reports(self) -> None:
        payload = base_payload()
        payload["product_courses"][0]["total_hours"] = "20"
        tables = {
            "business_classes": table([business_row("C_REG")]),
            "business_product_mappings": table([{"business_product_id": "100", "canonical_product_id": "P_REG"}]),
            "scheduled_lessons": table([
                scheduled_lesson("C_REG", teacher_id="T_OLD", teacher_name="旧老师", date="2026/3/1"),
                scheduled_lesson("C_REG", teacher_id="T_NEW", teacher_name="新老师", date="2026/6/1"),
            ]),
        }

        result = convert_business_tables(tables, payload)
        cls = result.payload["classes"][0]

        self.assertEqual(cls["teacher_assignments"][0]["teacher_id"], "T_NEW")
        self.assertTrue(any("历史课表老师冲突" in warning for warning in result.warnings))

    def test_completed_course_is_removed_and_completed_class_exits_schedule(self) -> None:
        tables = {
            "business_classes": table([business_row("C_DONE"), business_row("C_LEFT", room_id="R2")]),
            "business_product_mappings": table([{"business_product_id": "100", "canonical_product_id": "P_REG"}]),
            "class_teacher_assignments": table([assignment("C_DONE"), assignment("C_LEFT")]),
            "scheduled_lessons": table([scheduled_lesson("C_DONE", duration="4")]),
        }

        result = convert_business_tables(tables, base_payload())

        self.assertEqual([cls["id"] for cls in result.payload["classes"]], ["C_LEFT"])
        self.assertTrue(any("整班无剩余课程" in warning for warning in result.warnings))

    def test_26_season_history_learns_but_business_class_does_not_schedule(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            tables = {
                "business_classes": table([
                    business_row("C_26", exam_month="2025-12"),
                    business_row("C_27"),
                ]),
                "business_product_mappings": table([{"business_product_id": "100", "canonical_product_id": "P_REG"}]),
                "class_teacher_assignments": table([assignment("C_27")]),
                "scheduled_lessons": table([scheduled_lesson("C_26", teacher_id="T_26", teacher_name="26老师")]),
            }

            result = convert_business_tables(tables, base_payload(), output_dir=output_dir, timestamp="20260430_140000")

            self.assertEqual([cls["id"] for cls in result.payload["classes"]], ["C_27"])
            learned_path = output_dir / "learned_class_teacher_assignments_20260430_140000.csv"
            learned = learned_path.read_text(encoding="utf-8")
            self.assertIn("C_26", learned)
            with learned_path.open(encoding="utf-8") as handle:
                learned_rows = list(csv.DictReader(handle))
            self.assertEqual(learned_rows[0]["class_schedule_mode"], "本班实际排课")
            self.assertEqual(learned_rows[0]["actual_scheduled_class_id"], "C_26")
            self.assertIn("assignment_extra_time_requirement", learned_rows[0])
            self.assertNotIn("schedule_mode", learned_rows[0])
            self.assertNotIn("inherit_from_class_id", learned_rows[0])
            self.assertNotIn("teacher_available_slots", learned_rows[0])
            self.assertNotIn("course_module", learned_rows[0])

    def test_missing_product_mapping_blocks_selected_class(self) -> None:
        tables = {
            "business_classes": table([business_row("C_REG")]),
            "business_product_mappings": table([]),
            "class_teacher_assignments": table([assignment("C_REG")]),
        }

        with self.assertRaises(BusinessDataError) as context:
            convert_business_tables(tables, base_payload())

        self.assertIn("未命中产品映射", str(context.exception))

    def test_legacy_business_product_map_table_is_supported_only_at_conversion_boundary(self) -> None:
        tables = {
            "business_classes": table([business_row("C_REG")]),
            "business_product_map": table([{"business_product_id": "100", "canonical_product_id": "P_REG"}]),
            "class_teacher_assignments": table([assignment("C_REG")]),
        }

        result = convert_business_tables(tables, base_payload())

        self.assertEqual([cls["id"] for cls in result.payload["classes"]], ["C_REG"])

    def test_merge_group_without_detail_uses_default_shared_schedule(self) -> None:
        tables = {
            "business_classes": table([business_row("C_REG", merge_detail="C_REG,C_OTHER")]),
            "business_product_mappings": table([{"business_product_id": "100", "canonical_product_id": "P_REG"}]),
            "class_teacher_assignments": table([assignment("C_REG")]),
        }

        result = convert_business_tables(tables, base_payload())

        self.assertEqual([cls["id"] for cls in result.payload["classes"]], ["C_REG"])
        self.assertTrue(any("合班详情引用的班级未进入本轮排课范围" in warning for warning in result.warnings))

    def test_full_merge_keeps_source_class_as_shared_schedule(self) -> None:
        tables = {
            "business_classes": table([
                business_row("C_MAIN", merge_detail="C_MAIN,C_CHILD"),
                business_row("C_CHILD", merge_detail="C_MAIN,C_CHILD"),
            ]),
            "business_product_mappings": table([{"business_product_id": "100", "canonical_product_id": "P_REG"}]),
            "merge_course_details": table([
                {"source_class_id": "C_MAIN", "scheduled_class_id": "C_MAIN", "merge_type": "full"},
                {"source_class_id": "C_CHILD", "scheduled_class_id": "C_MAIN", "merge_type": "full"},
            ]),
            "class_teacher_assignments": table([assignment("C_MAIN")]),
        }

        result = convert_business_tables(tables, base_payload())
        classes = {cls["id"]: cls for cls in result.payload["classes"]}

        self.assertEqual(set(classes), {"C_MAIN", "C_CHILD"})
        shared_assignment = classes["C_CHILD"]["teacher_assignments"][0]
        self.assertEqual(shared_assignment["class_schedule_mode"], "共享实际排课班级")
        self.assertEqual(shared_assignment["actual_scheduled_class_id"], "C_MAIN")
        self.assertEqual(shared_assignment.get("teacher_id", ""), "")
        for old_field in ("schedule_mode", "inherit_from_class_id", "teacher_available_slots", "course_module"):
            self.assertNotIn(old_field, shared_assignment)
        self.assertNotIn("requirements", classes["C_CHILD"])

    def test_partial_merge_generates_class_level_requirements(self) -> None:
        tables = {
            "business_classes": table([
                business_row("C_MAIN"),
                business_row("C_SRC", merge_detail="C_MAIN,C_SRC"),
            ]),
            "business_product_mappings": table([{"business_product_id": "100", "canonical_product_id": "P_REG"}]),
            "merge_course_details": table([
                {
                    "source_class_id": "C_SRC",
                    "scheduled_class_id": "C_MAIN",
                    "merge_type": "partial",
                    "subject": "英语",
                    "stage": "基础",
                    "course_module": "词汇",
                    "course_group": "阅读类",
                }
            ]),
            "class_teacher_assignments": table([
                assignment("C_MAIN", "词汇", "T1"),
                assignment("C_MAIN", "阅读", "T1"),
                assignment("C_SRC", "词汇", "T2"),
                assignment("C_SRC", "阅读", "T2"),
            ]),
        }

        result = convert_business_tables(tables, base_payload(two_courses=True))
        classes = {cls["id"]: cls for cls in result.payload["classes"]}

        self.assertEqual(
            sorted(req["course_module"] for req in classes["C_MAIN"]["requirements"]),
            ["词汇", "阅读"],
        )
        self.assertEqual(
            [req["course_module"] for req in classes["C_SRC"]["requirements"]],
            ["阅读"],
        )
        for cls in classes.values():
            for assignment_row in cls["teacher_assignments"]:
                for old_field in ("schedule_mode", "inherit_from_class_id", "teacher_available_slots", "course_module"):
                    self.assertNotIn(old_field, assignment_row)
            for requirement in cls.get("requirements", []):
                self.assertNotIn("teacher_available_slots", requirement)
        with tempfile.TemporaryDirectory() as tmp:
            data_admin_server.DATA_DIR = Path(tmp) / "data"
            export = data_admin_server.export_scheduler_input(
                result.payload,
                time_slots=[
                    {
                        "id": "2026-07-01-AM-1",
                        "date": "2026-07-01",
                        "period": "AM",
                        "name": "上午一",
                        "order": 1,
                        "start_time": "08:00",
                        "end_time": "10:00",
                        "duration_hours": 2,
                    }
                ],
            )
            scheduler_input = json.loads(Path(export["path"]).read_text(encoding="utf-8"))
        exported_classes = {cls["id"]: cls for cls in scheduler_input["classes"]}
        self.assertEqual(
            [req["course_module"] for req in exported_classes["C_SRC"]["requirements"]],
            ["阅读"],
        )
        self.assertEqual(exported_classes["C_SRC"]["room_ids"], ["R1"])
        self.assertNotIn("room_ids", exported_classes["C_SRC"]["requirements"][0])


if __name__ == "__main__":
    unittest.main()
