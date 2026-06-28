from __future__ import annotations

import csv
import json
import re
import tempfile
import unittest
from collections import Counter
from dataclasses import replace
from datetime import date as Date
from datetime import timedelta
from pathlib import Path
from typing import List

import scheduler
from scripts.build_camp_maintenance_schedule import (
    WYQC_AUTUMN_END,
    WYQC_AUTUMN_START,
    WYQC_SPRINT_START_BY_SUBJECT,
    assignment_from_row,
    coverage_gap_blocking_lines,
    long_camp_subject_week_targets,
    public_coverage_gap_rows_from_totals,
    repair_candidate_allowed_by_outer_rules,
    relaxed_candidates_on_date,
    student_experience_warning_lines,
    class_window_venue_rebuild_suite_codes,
    run_summer_rebuild_attempts,
    summer_schedule_input_for_suites,
    teacher_same_day_campus_warning_lines,
)
from scripts.schedule_constraints import (
    assignment_constraint_sets,
    assignments_conflicting_with_candidate,
    candidate_is_valid,
    class_teacher_day_loads,
    place_candidate,
)
from scripts.schedule_conflicts import teacher_time_conflict_lines
from scripts.schedule_data import assignment_course_tag
from scripts.schedule_display import (
    assignment_display_slot_ids,
    assignment_standard_lesson_slots,
)
from scripts.schedule_class_windows import (
    ClassWindowConstraint,
    load_class_window_constraints,
    suite_window_constraints_from_class_windows,
)
from scripts.schedule_outputs import (
    BATCH_SCHEDULE_CSV_FIELDNAMES,
    build_day_table_payload,
    write_batch_csv,
    write_day_table_html,
)
from scripts.schedule_scope import class_ids_for_suite_codes, filtered_schedule_input, normalize_date
from scripts.schedule_first_lesson import (
    assignments_preserve_first_lesson_modules,
    first_lesson_candidate_allowed,
    first_lesson_module_violations,
    mark_first_lesson_anchor_done,
    replacement_preserves_first_lesson_module,
    stage_first_lesson_anchor_keys,
)
from scripts.schedule_stage_order import (
    assignments_preserve_stage_order,
    stage_order_candidate_allowed,
    stage_order_tasks_by_class,
    stage_order_violations,
)
from scripts.schedule_run_rules import (
    creates_teacher_run_over_limit,
    run_dates,
    run_dates_over_limit,
)
from scripts.schedule_week_balance import (
    average_subject_week_bounds_from_counts,
    front_loaded_week_quotas,
    long_camp_subject_week_bounds,
    shift_tail_week_quota_to_early,
)
from scripts.schedule_batch import (
    load_locked_csv_assignments,
    task_stage_rank,
)


def make_pm_blocks() -> list[tuple[scheduler.TimeSlot, ...]]:
    blocks: list[tuple[scheduler.TimeSlot, ...]] = []
    start = Date.fromisoformat("2026-07-06")
    for week_index in range(6):
        for day_offset in range(6):
            slot_date = start + timedelta(days=week_index * 7 + day_offset)
            blocks.append(
                (
                    scheduler.TimeSlot(
                        id=f"{slot_date.isoformat()}_PM",
                        date=slot_date.isoformat(),
                        period="PM",
                        name="下午",
                        order=len(blocks),
                        duration_hours=4,
                    ),
                )
            )
    final_date = Date.fromisoformat("2026-08-17")
    blocks.append(
        (
            scheduler.TimeSlot(
                id=f"{final_date.isoformat()}_PM",
                date=final_date.isoformat(),
                period="PM",
                name="下午",
                order=len(blocks),
                duration_hours=4,
            ),
        )
    )
    return blocks


class ScheduleScopeDateTest(unittest.TestCase):
    def test_normalize_date_uses_shared_import_formats(self) -> None:
        self.assertEqual(normalize_date("2026/7/1"), "2026-07-01")
        self.assertEqual(normalize_date("2026.7.1"), "2026-07-01")
        self.assertEqual(normalize_date("20260701"), "2026-07-01")


def make_teacher_travel_assignment(
    class_id: str,
    slot: scheduler.TimeSlot,
    room_id: str,
    teacher_id: str = "T_ZSS",
    teacher_name: str = "张珊珊",
    task_id: str | None = None,
) -> scheduler.Assignment:
    task = scheduler.CourseBlock(
        task_id=task_id or f"{class_id}_{slot.period}",
        class_id=class_id,
        class_name=class_id,
        product_id=None,
        product_name=None,
        class_size=None,
        subject_category="公共课",
        subject="政治",
        quarter=None,
        stage=None,
        course_module=None,
        course_group=None,
        teacher_id=teacher_id,
        teacher_name=teacher_name,
        block_hours=4,
        room_ids={room_id},
        start_date=None,
        end_date=None,
        allowed_periods=None,
        allowed_weekdays=None,
        excluded_weekdays=None,
        schedule_rules=(),
    )
    return scheduler.Assignment(task, scheduler.Candidate((slot,), teacher_id, teacher_name, room_id))


def make_stage_order_input() -> scheduler.ScheduleInput:
    morning = scheduler.TimeSlot("2026-07-01-AM", "2026-07-01", "AM", "上午", 1, "08:00", "10:00", 2)
    afternoon = scheduler.TimeSlot("2026-07-01-PM", "2026-07-01", "PM", "下午", 2, "14:00", "16:00", 2)
    cls = scheduler.SchoolClass(
        id="CLASS_STAGE",
        name="阶段测试班",
        product_id=None,
        product_name=None,
        size=None,
        room_ids={"R_101"},
        start_date=None,
        start_period=None,
        end_date=None,
        end_period=None,
        first_lesson_date=None,
        first_lesson_period=None,
        stage_order={"基础": 0, "强化": 1},
        requirements=[
            scheduler.Requirement(
                subject_category="公共课",
                subject="英语",
                quarter=None,
                stage="基础",
                course_module="词汇",
                course_group="基础组",
                teacher_id="T_1",
                teacher_name="老师1",
                total_hours=2,
                block_hours=2,
                room_ids={"R_101"},
            ),
            scheduler.Requirement(
                subject_category="公共课",
                subject="英语",
                quarter=None,
                stage="强化",
                course_module="阅读",
                course_group="强化组",
                teacher_id="T_1",
                teacher_name="老师1",
                total_hours=2,
                block_hours=2,
                room_ids={"R_101"},
            ),
        ],
    )
    return scheduler.ScheduleInput(
        time_slots=[morning, afternoon],
        rooms={"R_101": scheduler.Room("R_101")},
        classes={"CLASS_STAGE": cls},
        conflict_groups={},
        class_conflict_groups={"CLASS_STAGE": set()},
        locked_assignments=[],
    )


def make_first_lesson_input() -> scheduler.ScheduleInput:
    morning = scheduler.TimeSlot("2026-07-01-AM", "2026-07-01", "AM", "上午", 1, "08:00", "10:00", 2)
    afternoon = scheduler.TimeSlot("2026-07-01-PM", "2026-07-01", "PM", "下午", 2, "14:00", "16:00", 2)
    cls = scheduler.SchoolClass(
        id="CLASS_FIRST",
        name="首课测试班",
        product_id=None,
        product_name=None,
        size=None,
        room_ids={"R_101"},
        start_date=None,
        start_period=None,
        end_date=None,
        end_period=None,
        first_lesson_date=None,
        first_lesson_period=None,
        stage_order={"基础": 0},
        requirements=[
            scheduler.Requirement(
                subject_category="公共课",
                subject="英语",
                quarter=None,
                stage="基础",
                course_module="词汇",
                course_group="基础组",
                teacher_id="T_1",
                teacher_name="老师1",
                total_hours=2,
                block_hours=2,
                room_ids={"R_101"},
            ),
            scheduler.Requirement(
                subject_category="公共课",
                subject="英语",
                quarter=None,
                stage="基础",
                course_module="阅读",
                course_group="基础组",
                teacher_id="T_1",
                teacher_name="老师1",
                total_hours=2,
                block_hours=2,
                room_ids={"R_101"},
            ),
        ],
    )
    return scheduler.ScheduleInput(
        time_slots=[morning, afternoon],
        rooms={"R_101": scheduler.Room("R_101")},
        classes={"CLASS_FIRST": cls},
        conflict_groups={},
        class_conflict_groups={"CLASS_FIRST": set()},
        locked_assignments=[],
    )


def stage_task(schedule_input: scheduler.ScheduleInput, stage: str) -> scheduler.CourseBlock:
    tasks = stage_order_tasks_by_class(schedule_input)["CLASS_STAGE"]
    return next(task for task in tasks if task.stage == stage)


def first_lesson_task(schedule_input: scheduler.ScheduleInput, module: str) -> scheduler.CourseBlock:
    tasks = scheduler.build_course_blocks(schedule_input.classes)
    return next(task for task in tasks if task.course_module == module)


def stage_assignment(task: scheduler.CourseBlock, slot: scheduler.TimeSlot) -> scheduler.Assignment:
    return scheduler.Assignment(
        task,
        scheduler.Candidate((slot,), task.teacher_id, task.teacher_name, "R_101"),
    )


class ScheduleBatchBalancingTest(unittest.TestCase):
    def test_load_locked_csv_assignments_reads_bom_csv_with_shared_helper(self) -> None:
        slot = scheduler.TimeSlot(
            "2026-07-01-AM",
            "2026-07-01",
            "AM",
            "上午",
            1,
            "08:00",
            "12:00",
            4,
        )
        schedule_input = scheduler.ScheduleInput(
            time_slots=[slot],
            rooms={"R1": scheduler.Room("R1")},
            classes={},
            conflict_groups={},
            class_conflict_groups={},
            locked_assignments=[],
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "locked.csv"
            path.write_text(
                "\ufeffdate,period,start_time,end_time,duration_hours,class_id,class_name,subject,teacher_id,teacher_name,room_id,course_code,course_name\n"
                "2026-07-01,am,08:00,12:00,4,C_LOCK,锁定班,英语,T1,张老师,R1,ENG101,英语课\n",
                encoding="utf-8",
            )
            assignments = load_locked_csv_assignments([path], schedule_input)

        self.assertEqual(len(assignments), 1)
        assignment = assignments[0]
        self.assertTrue(assignment.task.is_locked)
        self.assertEqual(assignment.task.class_id, "C_LOCK")
        self.assertEqual(assignment.task.course_code, "ENG101")
        self.assertEqual(assignment.candidate.slots, (slot,))
        self.assertEqual(assignment.candidate.teacher_name, "张老师")

    def test_first_lesson_candidate_requires_anchor_module_first(self) -> None:
        schedule_input = make_first_lesson_input()
        morning, afternoon = schedule_input.time_slots
        vocab_task = first_lesson_task(schedule_input, "词汇")
        reading_task = first_lesson_task(schedule_input, "阅读")
        anchor_keys = stage_first_lesson_anchor_keys([vocab_task, reading_task])
        anchor_positions = {}
        reading_candidate = scheduler.Candidate((afternoon,), "T_1", "老师1", "R_101")

        self.assertFalse(
            first_lesson_candidate_allowed(
                reading_task,
                reading_candidate,
                anchor_keys,
                anchor_positions,
            )
        )

        vocab_candidate = scheduler.Candidate((morning,), "T_1", "老师1", "R_101")
        self.assertTrue(first_lesson_candidate_allowed(vocab_task, vocab_candidate, anchor_keys, anchor_positions))
        mark_first_lesson_anchor_done(vocab_task, vocab_candidate, anchor_keys, anchor_positions)

        self.assertTrue(
            first_lesson_candidate_allowed(
                reading_task,
                reading_candidate,
                anchor_keys,
                anchor_positions,
            )
        )
        self.assertFalse(
            first_lesson_candidate_allowed(
                reading_task,
                scheduler.Candidate((morning,), "T_1", "老师1", "R_101"),
                anchor_keys,
                anchor_positions,
            )
        )

    def test_first_lesson_module_violations_report_non_anchor_first(self) -> None:
        schedule_input = make_first_lesson_input()
        morning, afternoon = schedule_input.time_slots
        vocab_task = first_lesson_task(schedule_input, "词汇")
        reading_task = first_lesson_task(schedule_input, "阅读")
        valid_assignments = [
            stage_assignment(vocab_task, morning),
            stage_assignment(reading_task, afternoon),
        ]
        invalid_assignments = [
            stage_assignment(reading_task, morning),
            stage_assignment(vocab_task, afternoon),
        ]

        self.assertEqual(first_lesson_module_violations(valid_assignments), [])
        self.assertTrue(assignments_preserve_first_lesson_modules(valid_assignments))
        self.assertTrue(
            replacement_preserves_first_lesson_module(
                valid_assignments,
                1,
                reading_task,
                scheduler.Candidate((afternoon,), "T_1", "老师1", "R_101"),
            )
        )

        violations = first_lesson_module_violations(invalid_assignments)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0][0], ("CLASS_FIRST", "英语", "基础"))
        self.assertEqual(violations[0][1], "词汇")
        self.assertFalse(assignments_preserve_first_lesson_modules(invalid_assignments))
        self.assertFalse(
            replacement_preserves_first_lesson_module(
                valid_assignments,
                0,
                vocab_task,
                scheduler.Candidate(
                    (
                        scheduler.TimeSlot(
                            "2026-07-02-AM",
                            "2026-07-02",
                            "AM",
                            "上午",
                            3,
                            "08:00",
                            "10:00",
                            2,
                        ),
                    ),
                    "T_1",
                    "老师1",
                    "R_101",
                ),
            )
        )

    def test_stage_order_candidate_requires_prior_stage_assignment(self) -> None:
        schedule_input = make_stage_order_input()
        morning, afternoon = schedule_input.time_slots
        stage_tasks_by_class = stage_order_tasks_by_class(schedule_input)
        foundation_task = stage_task(schedule_input, "基础")
        advanced_task = stage_task(schedule_input, "强化")

        self.assertFalse(
            stage_order_candidate_allowed(
                schedule_input,
                stage_tasks_by_class,
                [],
                advanced_task,
                scheduler.Candidate((afternoon,), "T_1", "老师1", "R_101"),
            )
        )

        self.assertTrue(
            stage_order_candidate_allowed(
                schedule_input,
                stage_tasks_by_class,
                [stage_assignment(foundation_task, morning)],
                advanced_task,
                scheduler.Candidate((afternoon,), "T_1", "老师1", "R_101"),
            )
        )

        self.assertFalse(
            stage_order_candidate_allowed(
                schedule_input,
                stage_tasks_by_class,
                [stage_assignment(foundation_task, afternoon)],
                advanced_task,
                scheduler.Candidate((morning,), "T_1", "老师1", "R_101"),
            )
        )

    def test_stage_order_violations_report_stage_inversion(self) -> None:
        schedule_input = make_stage_order_input()
        morning, afternoon = schedule_input.time_slots
        foundation_task = stage_task(schedule_input, "基础")
        advanced_task = stage_task(schedule_input, "强化")

        valid_assignments = [
            stage_assignment(foundation_task, morning),
            stage_assignment(advanced_task, afternoon),
        ]
        self.assertEqual(stage_order_violations(schedule_input, valid_assignments), [])
        self.assertTrue(assignments_preserve_stage_order(schedule_input, valid_assignments))

        invalid_assignments = [
            stage_assignment(advanced_task, morning),
            stage_assignment(foundation_task, afternoon),
        ]
        violations = stage_order_violations(schedule_input, invalid_assignments)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0][:3], ("CLASS_STAGE", "基础", "强化"))
        self.assertFalse(assignments_preserve_stage_order(schedule_input, invalid_assignments))

    def test_task_stage_rank_uses_core_schedule_input_lookup(self) -> None:
        cls = scheduler.SchoolClass(
            id="CLASS_A",
            name="CLASS_A",
            product_id=None,
            product_name=None,
            size=None,
            room_ids=None,
            start_date=None,
            start_period=None,
            end_date=None,
            end_period=None,
            first_lesson_date=None,
            first_lesson_period=None,
            stage_order={"基础": 0, "强化": 1, "冲刺": 2},
            requirements=[],
        )
        task = scheduler.CourseBlock(
            task_id="TASK_A",
            class_id="CLASS_A",
            class_name="CLASS_A",
            product_id=None,
            product_name=None,
            class_size=None,
            subject_category="公共课",
            subject="英语",
            quarter=None,
            stage="强化",
            course_module=None,
            course_group=None,
            teacher_id="T_1",
            teacher_name="老师1",
            block_hours=2,
            room_ids=None,
            start_date=None,
            end_date=None,
            allowed_periods=None,
            allowed_weekdays=None,
            excluded_weekdays=None,
            schedule_rules=(),
        )
        schedule_input = scheduler.ScheduleInput(
            time_slots=[],
            rooms={},
            classes={"CLASS_A": cls},
            conflict_groups={},
            class_conflict_groups={},
            locked_assignments=[],
        )

        self.assertEqual(task_stage_rank(schedule_input, task), 1)
        self.assertIsNone(task_stage_rank(schedule_input, replace(task, stage=None)))
        self.assertIsNone(task_stage_rank(schedule_input, replace(task, class_id="MISSING")))

    def test_filtered_schedule_input_applies_scope_and_keeps_locked_conflicts(self) -> None:
        morning = scheduler.TimeSlot("2026-07-01-AM", "2026-07-01", "AM", "上午", 1, "08:00", "10:00", 2)
        afternoon = scheduler.TimeSlot("2026-07-02-PM", "2026-07-02", "PM", "下午", 2, "14:00", "16:00", 2)
        evening = scheduler.TimeSlot("2026-07-03-EV", "2026-07-03", "EVENING", "晚上", 3, "19:00", "21:00", 2)
        cls = scheduler.SchoolClass(
            id="CLASS_A",
            name="范围测试班",
            product_id=None,
            product_name=None,
            size=None,
            room_ids={"R_101"},
            start_date=None,
            start_period=None,
            end_date=None,
            end_period=None,
            first_lesson_date=None,
            first_lesson_period=None,
            stage_order={"基础": 0, "强化": 1},
            requirements=[
                scheduler.Requirement(
                    subject_category="公共课",
                    subject="英语",
                    quarter="春季",
                    stage="基础",
                    course_module="词汇",
                    course_group="基础组",
                    teacher_id="T_1",
                    teacher_name="老师1",
                    total_hours=2,
                    block_hours=2,
                    room_ids={"R_101"},
                ),
                scheduler.Requirement(
                    subject_category="公共课",
                    subject="政治",
                    quarter="暑假",
                    stage="强化",
                    course_module="马原",
                    course_group="强化组",
                    teacher_id="T_2",
                    teacher_name="老师2",
                    total_hours=2,
                    block_hours=2,
                    room_ids={"R_101"},
                ),
            ],
        )
        locked = make_teacher_travel_assignment("LOCKED_CLASS", afternoon, "R_LOCK", "T_LOCK", "锁定老师", "locked")
        source = scheduler.ScheduleInput(
            time_slots=[morning, afternoon, evening],
            rooms={"R_101": scheduler.Room("R_101"), "R_202": scheduler.Room("R_202")},
            classes={"CLASS_A": cls},
            conflict_groups={
                "G_SELECTED": {"CLASS_A", "LOCKED_CLASS"},
                "G_IGNORED": {"CLASS_X", "CLASS_Y"},
            },
            class_conflict_groups={},
            locked_assignments=[locked],
        )

        filtered = filtered_schedule_input(
            source,
            ["CLASS_A"],
            {"基础"},
            {"英语"},
            "2026-07-02",
            "2026-07-02",
            None,
            None,
            {"PM"},
            {"R_202"},
            quarters={"春季"},
        )

        self.assertEqual([slot.id for slot in filtered.time_slots], ["2026-07-02-PM"])
        self.assertEqual(list(filtered.classes), ["CLASS_A"])
        self.assertEqual(len(filtered.classes["CLASS_A"].requirements), 1)
        self.assertEqual(filtered.classes["CLASS_A"].requirements[0].subject, "英语")
        self.assertEqual(filtered.classes["CLASS_A"].requirements[0].room_ids, {"R_202"})
        self.assertEqual(filtered.classes["CLASS_A"].room_ids, {"R_202"})
        self.assertEqual(filtered.conflict_groups, {"G_SELECTED": {"CLASS_A", "LOCKED_CLASS"}})
        self.assertEqual(filtered.class_conflict_groups["CLASS_A"], {"G_SELECTED"})

    def test_class_window_constraints_filter_active_rows_and_apply_multi_room_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "class_window_boundaries.csv"
            with path.open("w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "class_window_id",
                        "class_id",
                        "class_name",
                        "product_id",
                        "schedule_window_id",
                        "window_year",
                        "window_order",
                        "season_window_id",
                        "season_name",
                        "window_sequence",
                        "schedule_window_name",
                        "earliest_date",
                        "earliest_period",
                        "latest_date",
                        "latest_period",
                        "preferred_teaching_area_ids",
                        "preferred_room_ids",
                        "preferred_room_is_required",
                        "is_class_window_included",
                        "notes",
                    ],
                )
                writer.writeheader()
                writer.writerows(
                    [
                        {
                            "class_window_id": "CLASS_A_2026暑假",
                            "class_id": "CLASS_A",
                            "class_name": "测试班",
                            "product_id": "P_1",
                            "schedule_window_id": "2026暑假",
                            "window_year": "2026",
                            "window_order": "202607",
                            "season_window_id": "WINDOW_SUMMER",
                            "season_name": "暑假",
                            "window_sequence": "1",
                            "schedule_window_name": "2026暑假",
                            "earliest_date": "2026/7/6",
                            "earliest_period": "",
                            "latest_date": "2026/8/1",
                            "latest_period": "",
                            "preferred_teaching_area_ids": "AREA_1|AREA_2",
                            "preferred_room_ids": "R_201|R_202",
                            "preferred_room_is_required": "是",
                            "is_class_window_included": "是",
                            "notes": "测试",
                        },
                        {
                            "class_window_id": "CLASS_B_2026暑假",
                            "class_id": "CLASS_B",
                            "class_name": "停用班",
                            "product_id": "P_1",
                            "schedule_window_id": "2026暑假",
                            "window_year": "2026",
                            "window_order": "202607",
                            "season_window_id": "WINDOW_SUMMER",
                            "season_name": "暑假",
                            "window_sequence": "1",
                            "schedule_window_name": "2026暑假",
                            "earliest_date": "2026-07-06",
                            "earliest_period": "AM",
                            "latest_date": "2026-08-01",
                            "latest_period": "PM",
                            "preferred_teaching_area_ids": "AREA_1",
                            "preferred_room_ids": "R_999",
                            "preferred_room_is_required": "是",
                            "is_class_window_included": "否",
                            "notes": "",
                        },
                    ]
                )
            constraints = load_class_window_constraints(
                path,
                class_ids={"CLASS_A", "CLASS_B"},
                season_window_ids={"WINDOW_SUMMER"},
            )

        self.assertEqual(set(constraints), {"CLASS_A"})
        constraint = constraints["CLASS_A"]
        self.assertEqual(constraint.earliest_date, "2026-07-06")
        self.assertEqual(constraint.earliest_period, "AM")
        self.assertEqual(constraint.latest_date, "2026-08-01")
        self.assertEqual(constraint.latest_period, "EVENING")
        self.assertEqual(constraint.room_ids, frozenset({"R_201", "R_202"}))

        slot = scheduler.TimeSlot("2026-07-06-AM", "2026-07-06", "AM", "上午", 1, "08:00", "10:00", 2)
        cls = scheduler.SchoolClass(
            id="CLASS_A",
            name="测试班",
            product_id="P_1",
            product_name="测试产品",
            size=20,
            room_ids={"R_OLD"},
            start_date=None,
            start_period=None,
            end_date=None,
            end_period=None,
            first_lesson_date=None,
            first_lesson_period=None,
            stage_order={"基础": 0},
            requirements=[
                scheduler.Requirement(
                    subject_category="公共课",
                    subject="英语",
                    quarter="暑假",
                    stage="基础",
                    course_module="词汇",
                    course_group="基础组",
                    teacher_id="T_1",
                    teacher_name="老师1",
                    total_hours=2,
                    block_hours=2,
                    room_ids={"R_OLD"},
                )
            ],
        )
        source = scheduler.ScheduleInput(
            time_slots=[slot],
            rooms={"R_OLD": scheduler.Room("R_OLD"), "R_201": scheduler.Room("R_201"), "R_202": scheduler.Room("R_202")},
            classes={"CLASS_A": cls},
            conflict_groups={},
            class_conflict_groups={},
            locked_assignments=[],
        )

        filtered = filtered_schedule_input(
            source,
            ["CLASS_A"],
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            class_window_constraints=constraints,
            quarters={"暑假"},
        )

        filtered_class = filtered.classes["CLASS_A"]
        self.assertEqual(filtered_class.room_ids, {"R_201", "R_202"})
        self.assertEqual(filtered_class.start_date, "2026-07-06")
        self.assertEqual(filtered_class.start_period, "AM")
        self.assertEqual(filtered_class.end_date, "2026-08-01")
        self.assertEqual(filtered_class.end_period, "EVENING")
        self.assertEqual(filtered_class.requirements[0].room_ids, {"R_201", "R_202"})

    def test_class_window_area_only_boundary_expands_to_active_area_rooms(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            (data_dir / "rooms.json").write_text(
                json.dumps(
                    {
                        "rooms": [
                            {"id": "R_A1", "name": "A1-101", "teaching_area_id": "AREA_1", "is_active": True},
                            {"id": "R_A2", "name": "A1-102", "teaching_area_id": "AREA_1", "is_active": True},
                            {"id": "R_OFF", "name": "停用教室", "teaching_area_id": "AREA_1", "is_active": False},
                            {"id": "R_B1", "name": "B1-101", "teaching_area_id": "AREA_2", "is_active": True},
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            path = data_dir / "class_window_boundaries.csv"
            with path.open("w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "class_window_id",
                        "class_id",
                        "class_name",
                        "product_id",
                        "schedule_window_id",
                        "season_window_id",
                        "season_name",
                        "schedule_window_name",
                        "earliest_date",
                        "earliest_period",
                        "latest_date",
                        "latest_period",
                        "preferred_teaching_area_ids",
                        "preferred_room_ids",
                        "preferred_room_is_required",
                        "is_class_window_included",
                        "notes",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "class_window_id": "CLASS_AREA_2026暑假",
                        "class_id": "CLASS_AREA",
                        "class_name": "教学区约束班",
                        "product_id": "P_1",
                        "schedule_window_id": "2026暑假",
                        "season_window_id": "WINDOW_SUMMER",
                        "season_name": "暑假",
                        "schedule_window_name": "2026暑假",
                        "earliest_date": "2026-07-06",
                        "earliest_period": "AM",
                        "latest_date": "2026-07-10",
                        "latest_period": "PM",
                        "preferred_teaching_area_ids": "AREA_1",
                        "preferred_room_ids": "",
                        "preferred_room_is_required": "是",
                        "is_class_window_included": "是",
                        "notes": "",
                    }
                )

            constraints = load_class_window_constraints(path, class_ids={"CLASS_AREA"})

        self.assertEqual(constraints["CLASS_AREA"].room_ids, frozenset({"R_A1", "R_A2"}))

        slot = scheduler.TimeSlot("2026-07-06-AM", "2026-07-06", "AM", "上午", 1, "08:00", "10:00", 2)
        requirement = scheduler.Requirement(
            subject_category="公共课",
            subject="英语",
            quarter="暑假",
            stage="基础",
            course_module="词汇",
            course_group="基础组",
            teacher_id="T_1",
            teacher_name="老师1",
            total_hours=2,
            block_hours=2,
            room_ids=None,
        )
        source = scheduler.ScheduleInput(
            time_slots=[slot],
            rooms={
                "R_A1": scheduler.Room("R_A1", teaching_area_id="AREA_1"),
                "R_A2": scheduler.Room("R_A2", teaching_area_id="AREA_1"),
                "R_B1": scheduler.Room("R_B1", teaching_area_id="AREA_2"),
            },
            classes={
                "CLASS_AREA": scheduler.SchoolClass(
                    id="CLASS_AREA",
                    name="教学区约束班",
                    product_id="P_1",
                    product_name="测试产品",
                    size=20,
                    room_ids=None,
                    start_date=None,
                    start_period=None,
                    end_date=None,
                    end_period=None,
                    first_lesson_date=None,
                    first_lesson_period=None,
                    stage_order={"基础": 0},
                    requirements=[requirement],
                )
            },
            conflict_groups={},
            class_conflict_groups={},
            locked_assignments=[],
        )

        filtered = filtered_schedule_input(
            source,
            ["CLASS_AREA"],
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            class_window_constraints=constraints,
            quarters={"暑假"},
        )

        filtered_class = filtered.classes["CLASS_AREA"]
        self.assertEqual(filtered_class.room_ids, {"R_A1", "R_A2"})
        self.assertEqual(filtered_class.requirements[0].room_ids, {"R_A1", "R_A2"})

    def test_suite_window_summary_keeps_class_rooms_separate(self) -> None:
        class_constraints = {
            "CLASS_A": ClassWindowConstraint(
                class_window_id="CW_A",
                class_id="CLASS_A",
                class_name="班级A",
                product_id="P_1",
                schedule_window_id="2026暑假",
                season_window_id="WINDOW_SUMMER",
                season_name="暑假",
                schedule_window_name="2026暑假",
                earliest_date="2026-07-06",
                earliest_period="AM",
                latest_date="2026-08-01",
                latest_period="PM",
                teaching_area_ids=frozenset({"AREA_1"}),
                room_ids=frozenset({"ROOM_1"}),
                preferred_room_is_required=True,
            ),
            "CLASS_B": ClassWindowConstraint(
                class_window_id="CW_B",
                class_id="CLASS_B",
                class_name="班级B",
                product_id="P_1",
                schedule_window_id="2026暑假",
                season_window_id="WINDOW_SUMMER",
                season_name="暑假",
                schedule_window_name="2026暑假",
                earliest_date="2026-07-08",
                earliest_period="AM",
                latest_date="2026-08-03",
                latest_period="PM",
                teaching_area_ids=frozenset({"AREA_2"}),
                room_ids=frozenset({"ROOM_2"}),
                preferred_room_is_required=True,
            ),
        }
        class_metadata = {
            "CLASS_A": {"suite_code": "2701"},
            "CLASS_B": {"suite_code": "2701"},
        }

        suite_constraints = suite_window_constraints_from_class_windows(
            class_constraints,
            class_metadata,
        )

        self.assertEqual(set(suite_constraints), {"2701"})
        suite_constraint = suite_constraints["2701"]
        self.assertEqual(suite_constraint.earliest_date, "2026-07-06")
        self.assertEqual(suite_constraint.latest_date, "2026-08-03")
        self.assertEqual(suite_constraint.room_ids, frozenset())
        self.assertEqual(class_constraints["CLASS_A"].room_ids, frozenset({"ROOM_1"}))
        self.assertEqual(class_constraints["CLASS_B"].room_ids, frozenset({"ROOM_2"}))

    def test_summer_schedule_input_helper_applies_class_window_and_locks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            with (data_dir / "classes.csv").open("w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["id", "name", "suite_code", "subject", "subject_category", "is_schedule_locked"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "id": "KYYY2750",
                        "name": "考研英语测试班",
                        "suite_code": "2750",
                        "subject": "英语",
                        "subject_category": "公共课",
                        "is_schedule_locked": "",
                    }
                )
            with (data_dir / "class_window_boundaries.csv").open("w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "class_window_id",
                        "class_id",
                        "class_name",
                        "product_id",
                        "schedule_window_id",
                        "season_window_id",
                        "season_name",
                        "schedule_window_name",
                        "earliest_date",
                        "earliest_period",
                        "latest_date",
                        "latest_period",
                        "preferred_teaching_area_ids",
                        "preferred_room_ids",
                        "preferred_room_is_required",
                        "is_class_window_included",
                        "notes",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "class_window_id": "KYYY2750_2026暑假",
                        "class_id": "KYYY2750",
                        "class_name": "考研英语测试班",
                        "product_id": "P_1",
                        "schedule_window_id": "2026暑假",
                        "season_window_id": "WINDOW_SUMMER",
                        "season_name": "暑假",
                        "schedule_window_name": "2026暑假",
                        "earliest_date": "2026-07-06",
                        "earliest_period": "AM",
                        "latest_date": "2026-07-10",
                        "latest_period": "PM",
                        "preferred_teaching_area_ids": "AREA_1",
                        "preferred_room_ids": "R_201",
                        "preferred_room_is_required": "是",
                        "is_class_window_included": "是",
                        "notes": "",
                    }
                )
            (data_dir / "scheduler_input_draft.json").write_text(
                json.dumps(
                    {
                        "time_slots": [
                            {"id": "2026-07-05-AM", "date": "2026-07-05", "period": "AM", "name": "上午", "order": 1, "start_time": "08:00", "end_time": "10:00", "duration_hours": 2, "schedule_window_id": "2026暑假", "season_window_id": "WINDOW_SUMMER", "season_name": "暑假"},
                            {"id": "2026-07-06-AM", "date": "2026-07-06", "period": "AM", "name": "上午", "order": 1, "start_time": "08:00", "end_time": "10:00", "duration_hours": 2, "schedule_window_id": "2026暑假", "season_window_id": "WINDOW_SUMMER", "season_name": "暑假"},
                            {"id": "2026-07-10-PM", "date": "2026-07-10", "period": "PM", "name": "下午", "order": 2, "start_time": "14:00", "end_time": "16:00", "duration_hours": 2, "schedule_window_id": "2026暑假", "season_window_id": "WINDOW_SUMMER", "season_name": "暑假"},
                            {"id": "2026-07-11-PM", "date": "2026-07-11", "period": "PM", "name": "下午", "order": 2, "start_time": "14:00", "end_time": "16:00", "duration_hours": 2, "schedule_window_id": "2026暑假", "season_window_id": "WINDOW_SUMMER", "season_name": "暑假"},
                            {"id": "2026-07-06-EVENING", "date": "2026-07-06", "period": "EVENING", "name": "晚上", "order": 3, "start_time": "19:00", "end_time": "21:00", "duration_hours": 2, "schedule_window_id": "2026暑假", "season_window_id": "WINDOW_SUMMER", "season_name": "暑假"},
                        ],
                        "rooms": [
                            {"id": "R_OLD", "capacity": 50},
                            {"id": "R_201", "capacity": 50},
                            {"id": "R_LOCK", "capacity": 50},
                        ],
                        "products": [
                            {
                                "id": "P_1",
                                "name": "暑假产品",
                                "requirements": [
                                    {
                                        "subject_category": "公共课",
                                        "subject": "英语",
                                        "quarter": "暑假",
                                        "stage": "强化",
                                        "course_module": "阅读",
                                        "course_group": "阅读类",
                                        "total_hours": 2,
                                        "block_hours": 2,
                                    }
                                ],
                            }
                        ],
                        "classes": [
                            {
                                "id": "KYYY2750",
                                "name": "考研英语测试班",
                                "product_id": "P_1",
                                "subject": "英语",
                                "stages": "强化",
                                "preferred_room_ids": ["R_OLD"],
                                "teacher_assignments": [
                                    {
                                        "subject": "英语",
                                        "stage": "强化",
                                        "course_group": "阅读类",
                                        "teacher_id": "T_1",
                                        "teacher_name": "老师1",
                                    }
                                ],
                            }
                        ],
                        "conflict_groups": [],
                        "locked_lessons": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            protected = make_teacher_travel_assignment(
                "LOCKED_CLASS",
                scheduler.TimeSlot("LOCKED_SLOT", "2026-07-06", "AM", "上午", 1, "08:00", "10:00", 2),
                "R_LOCK",
                "T_LOCK",
                "锁定老师",
                "LOCKED_TASK",
            )
            suite_constraint = ClassWindowConstraint(
                class_window_id="KYYY2750_2026暑假",
                class_id="KYYY2750",
                class_name="考研英语测试班",
                product_id="P_1",
                schedule_window_id="2026暑假",
                season_window_id="WINDOW_SUMMER",
                season_name="暑假",
                schedule_window_name="2026暑假",
                earliest_date="2026-07-06",
                earliest_period="AM",
                latest_date="2026-07-10",
                latest_period="PM",
                teaching_area_ids=frozenset({"AREA_1"}),
                room_ids=frozenset(),
                preferred_room_is_required=True,
            )

            summer_input, class_ids = summer_schedule_input_for_suites(
                data_dir,
                ["2750"],
                {"2750": suite_constraint},
                [protected],
            )

        self.assertEqual(class_ids, ["KYYY2750"])
        self.assertEqual([slot.id for slot in summer_input.time_slots], ["2026-07-06-AM", "2026-07-10-PM"])
        self.assertEqual([assignment.task.task_id for assignment in summer_input.locked_assignments], ["LOCKED_TASK"])
        filtered_class = summer_input.classes["KYYY2750"]
        self.assertEqual(filtered_class.room_ids, {"R_201"})
        self.assertEqual(filtered_class.start_date, "2026-07-06")
        self.assertEqual(filtered_class.end_date, "2026-07-10")
        self.assertEqual(filtered_class.requirements[0].room_ids, {"R_201"})

    def test_summer_rebuild_attempt_runner_keeps_order_and_errors(self) -> None:
        slot = scheduler.TimeSlot("2026-07-06-AM", "2026-07-06", "AM", "上午", 1, "08:00", "10:00", 2)
        assignment = make_teacher_travel_assignment("KYYY2750", slot, "R_201")
        calls: List[str] = []

        def fail_first() -> List[scheduler.Assignment]:
            calls.append("first")
            raise ValueError("first failed")

        def succeed_second() -> List[scheduler.Assignment]:
            calls.append("second")
            return [assignment]

        def fail_second() -> List[scheduler.Assignment]:
            calls.append("second-failed")
            raise ValueError("second failed")

        result, used_label, errors = run_summer_rebuild_attempts(
            (
                ("快速轮排", fail_first, None),
                ("均衡", succeed_second, None),
            )
        )

        self.assertEqual(result, [assignment])
        self.assertEqual(used_label, "均衡")
        self.assertEqual(errors, ["快速轮排: first failed"])
        self.assertEqual(calls, ["first", "second"])

        with self.assertRaisesRegex(ValueError, "快速轮排: first failed；均衡: second failed"):
            run_summer_rebuild_attempts(
                (
                    ("快速轮排", fail_first, None),
                    ("均衡", fail_second, None),
                )
            )

    def test_class_window_venue_rebuild_uses_class_window_choices(self) -> None:
        slot = scheduler.TimeSlot("2026-07-06-AM", "2026-07-06", "AM", "上午", 1, "08:00", "10:00", 2)
        task = scheduler.CourseBlock(
            task_id="TASK_1",
            class_id="KYYY2750",
            class_name="测试班",
            product_id="P_1",
            product_name="测试产品",
            class_size=20,
            subject_category="公共课",
            subject="英语",
            quarter="暑假",
            stage="强化",
            course_module="阅读",
            course_group="英语类",
            teacher_id="T_1",
            teacher_name="老师1",
            block_hours=2,
            room_ids={"ROOM_1", "ROOM_2"},
            start_date=None,
            end_date=None,
            allowed_periods=None,
            allowed_weekdays=None,
            excluded_weekdays=None,
            schedule_rules=(),
        )
        constraint = ClassWindowConstraint(
            class_window_id="CW_1",
            class_id="KYYY2750",
            class_name="测试班",
            product_id="P_1",
            schedule_window_id="2026暑假",
            season_window_id="WINDOW_SUMMER",
            season_name="暑假",
            schedule_window_name="2026暑假",
            earliest_date="2026-07-01",
            earliest_period="AM",
            latest_date="2026-08-01",
            latest_period="PM",
            teaching_area_ids=frozenset({"AREA_1"}),
            room_ids=frozenset({"ROOM_1", "ROOM_2"}),
            preferred_room_is_required=True,
        )
        valid_assignment = scheduler.Assignment(
            task=task,
            candidate=scheduler.Candidate((slot,), "T_1", "老师1", "ROOM_2"),
        )
        invalid_assignment = scheduler.Assignment(
            task=task,
            candidate=scheduler.Candidate((slot,), "T_1", "老师1", "ROOM_BAD"),
        )

        self.assertEqual(
            class_window_venue_rebuild_suite_codes(
                [valid_assignment],
                {"KYYY2750": constraint},
            ),
            [],
        )
        self.assertEqual(
            class_window_venue_rebuild_suite_codes(
                [invalid_assignment],
                {"KYYY2750": constraint},
            ),
            ["2750"],
        )

    def test_repair_outer_rules_prefer_class_window_over_suite_window(self) -> None:
        task = scheduler.CourseBlock(
            task_id="TASK_1",
            class_id="KYYY2750",
            class_name="测试班",
            product_id="P_1",
            product_name="寒暑营",
            class_size=20,
            subject_category="公共课",
            subject="英语",
            quarter="暑假",
            stage="强化",
            course_module="阅读",
            course_group="英语类",
            teacher_id="T_1",
            teacher_name="老师1",
            block_hours=2,
            room_ids={"ROOM_1"},
            start_date=None,
            end_date=None,
            allowed_periods=None,
            allowed_weekdays=None,
            excluded_weekdays=None,
            schedule_rules=(),
        )
        assignment = scheduler.Assignment(
            task=task,
            candidate=scheduler.Candidate(
                (scheduler.TimeSlot("2026-07-12-AM", "2026-07-12", "AM", "上午", 1),),
                "T_1",
                "老师1",
                "ROOM_1",
            ),
        )
        wide_suite_window = ClassWindowConstraint(
            class_window_id="SUITE_2750",
            class_id="",
            class_name="",
            product_id="P_1",
            schedule_window_id="2026暑假",
            season_window_id="WINDOW_SUMMER",
            season_name="暑假",
            schedule_window_name="2026暑假",
            earliest_date="2026-07-01",
            earliest_period="AM",
            latest_date="2026-08-31",
            latest_period="PM",
            teaching_area_ids=frozenset(),
            room_ids=frozenset(),
            preferred_room_is_required=True,
        )
        class_window = ClassWindowConstraint(
            class_window_id="KYYY2750_2026暑假",
            class_id="KYYY2750",
            class_name="测试班",
            product_id="P_1",
            schedule_window_id="2026暑假",
            season_window_id="WINDOW_SUMMER",
            season_name="暑假",
            schedule_window_name="2026暑假",
            earliest_date="2026-07-10",
            earliest_period="AM",
            latest_date="2026-07-20",
            latest_period="PM",
            teaching_area_ids=frozenset({"AREA_1"}),
            room_ids=frozenset({"ROOM_1"}),
            preferred_room_is_required=True,
        )
        metadata = {"KYYY2750": {"suite_code": "2750", "sub_product": "寒暑营"}}
        window_constraints = {"2750": wide_suite_window, "KYYY2750": class_window}

        early_candidate = scheduler.Candidate(
            (scheduler.TimeSlot("2026-07-05-AM", "2026-07-05", "AM", "上午", 1),),
            "T_1",
            "老师1",
            "ROOM_1",
        )
        valid_candidate = scheduler.Candidate(
            (scheduler.TimeSlot("2026-07-12-AM", "2026-07-12", "AM", "上午", 1),),
            "T_1",
            "老师1",
            "ROOM_1",
        )

        self.assertFalse(
            repair_candidate_allowed_by_outer_rules(
                assignment,
                early_candidate,
                metadata,
                window_constraints,
                set(),
            )
        )
        self.assertTrue(
            repair_candidate_allowed_by_outer_rules(
                assignment,
                valid_candidate,
                metadata,
                window_constraints,
                set(),
            )
        )

    def test_class_ids_for_suite_codes_reads_public_unlocked_classes_in_subject_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir)
            with (path / "classes.csv").open("w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["id", "suite_code", "subject", "subject_category", "is_schedule_locked"],
                )
                writer.writeheader()
                writer.writerows(
                    [
                        {"id": "KYZZ2701", "suite_code": "2701", "subject": "政治", "subject_category": "公共课", "is_schedule_locked": ""},
                        {"id": "KYYY2701", "suite_code": "2701", "subject": "英语", "subject_category": "公共课", "is_schedule_locked": "否"},
                        {"id": "KYSX2701", "suite_code": "2701", "subject": "数学", "subject_category": "公共课", "is_schedule_locked": "否"},
                        {"id": "KYJSJ2701", "suite_code": "2701", "subject": "计算机", "subject_category": "专业课", "is_schedule_locked": "否"},
                        {"id": "KYYY2701_LOCKED", "suite_code": "2701", "subject": "英语", "subject_category": "公共课", "is_schedule_locked": "是"},
                        {"id": "KYSX2702", "suite_code": "2702", "subject": "数学", "subject_category": "公共课", "is_schedule_locked": "否"},
                    ]
                )

            self.assertEqual(
                class_ids_for_suite_codes(path, ["2701"], None),
                ["KYSX2701", "KYYY2701", "KYZZ2701"],
            )
            self.assertEqual(class_ids_for_suite_codes(path, ["2701"], {"政治"}), ["KYZZ2701"])

    def test_class_ids_for_suite_codes_infers_subjects_from_compact_product_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir)
            with (path / "classes.csv").open("w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["id", "suite_code", "product_id", "name", "is_schedule_locked"],
                )
                writer.writeheader()
                writer.writerows(
                    [
                        {
                            "id": "KYYY2750",
                            "suite_code": "2750",
                            "product_id": "KYHSY_ZK_YY",
                            "name": "考研英语寒暑集训营",
                            "is_schedule_locked": "否",
                        },
                        {
                            "id": "KYZZ2750",
                            "suite_code": "2750",
                            "product_id": "KYHSY_ZK_ZZ",
                            "name": "考研政治寒暑集训营",
                            "is_schedule_locked": "否",
                        },
                        {
                            "id": "KYSX2750",
                            "suite_code": "2750",
                            "product_id": "KYHSY_ZK_SX",
                            "name": "考研数学寒暑集训营",
                            "is_schedule_locked": "否",
                        },
                        {
                            "id": "KYJSJ2750",
                            "suite_code": "2750",
                            "product_id": "KYHSY_ZK_JSJ",
                            "name": "考研计算机寒暑集训营",
                            "is_schedule_locked": "否",
                        },
                    ]
                )

            self.assertEqual(
                class_ids_for_suite_codes(path, ["2750"], None),
                ["KYSX2750", "KYYY2750", "KYZZ2750"],
            )
            self.assertEqual(class_ids_for_suite_codes(path, ["2750"], {"英语"}), ["KYYY2750"])

    def test_requirement_object_key_is_shared_for_requirements_and_tasks(self) -> None:
        requirement = scheduler.Requirement(
            subject_category="公共课",
            subject="英语",
            quarter=None,
            stage="基础",
            course_module="词汇",
            course_group="阅读类",
            teacher_id="T_1",
            teacher_name="老师1",
            total_hours=4,
            block_hours=2,
        )
        task = scheduler.CourseBlock(
            task_id="TASK_A",
            class_id="CLASS_A",
            class_name="CLASS_A",
            product_id=None,
            product_name=None,
            class_size=None,
            subject_category="公共课",
            subject="英语",
            quarter=None,
            stage="基础",
            course_module="词汇",
            course_group="阅读类",
            teacher_id="T_1",
            teacher_name="老师1",
            block_hours=2,
            room_ids=None,
            start_date=None,
            end_date=None,
            allowed_periods=None,
            allowed_weekdays=None,
            excluded_weekdays=None,
            schedule_rules=(),
        )

        self.assertEqual(scheduler.requirement_object_key(requirement), ("英语", "基础", "词汇", "阅读类"))
        self.assertEqual(scheduler.requirement_object_key(task), scheduler.requirement_object_key(requirement))
        self.assertEqual(scheduler.requirement_object_key(replace(task, stage=None, course_module=None)), ("英语", "", "", "阅读类"))

    def test_assignment_course_tag_uses_product_course_tags(self) -> None:
        task = scheduler.CourseBlock(
            task_id="TASK_A",
            class_id="CLASS_A",
            class_name="CLASS_A",
            product_id="P1",
            product_name="产品1",
            class_size=None,
            subject_category="公共课",
            subject="英语",
            quarter=None,
            stage="暑假",
            course_module="词汇",
            course_group="阅读类",
            teacher_id="T_1",
            teacher_name="老师1",
            block_hours=2,
            room_ids=None,
            start_date=None,
            end_date=None,
            allowed_periods=None,
            allowed_weekdays=None,
            excluded_weekdays=None,
            schedule_rules=(),
        )
        assignment = scheduler.Assignment(
            task=task,
            candidate=scheduler.Candidate(slots=(), teacher_id="T_1", teacher_name="老师1", room_id="R1"),
        )
        tags = [
            {
                "product_id": "P1",
                "subject": "英语",
                "quarter": "暑假",
                "stage": "",
                "course_module": "词汇",
                "course_group": "阅读类",
                "course_code": "ENG-VOC",
                "course_name": "英语词汇",
            }
        ]

        self.assertEqual(
            assignment_course_tag(assignment, product_course_tags=tags),
            {"course_code": "ENG-VOC", "course_name": "英语词汇"},
        )

    def test_write_batch_csv_expands_standard_lessons_and_course_tags(self) -> None:
        task = scheduler.CourseBlock(
            task_id="TASK_A",
            class_id="CLASS_A",
            class_name="测试班",
            product_id="P1",
            product_name="产品1",
            class_size=None,
            subject_category="公共课",
            subject="英语",
            quarter=None,
            stage="暑假",
            course_module="词汇",
            course_group="阅读类",
            teacher_id="T_1",
            teacher_name="老师1",
            block_hours=4,
            room_ids={"R1"},
            start_date=None,
            end_date=None,
            allowed_periods=None,
            allowed_weekdays=None,
            excluded_weekdays=None,
            schedule_rules=(),
        )
        assignment = scheduler.Assignment(
            task=task,
            candidate=scheduler.Candidate(
                slots=(
                    scheduler.TimeSlot(
                        "2026-07-01-AM",
                        "2026-07-01",
                        "AM",
                        "上午",
                        1,
                        "08:00",
                        "12:20",
                        4,
                    ),
                ),
                teacher_id="T_1",
                teacher_name="老师1",
                room_id="R1",
            ),
        )
        product_course_tags = [
            {
                "product_id": "P1",
                "subject": "英语",
                "quarter": "暑假",
                "stage": "",
                "course_module": "词汇",
                "course_group": "阅读类",
                "course_code": "ENG-VOC",
                "course_name": "英语词汇",
            }
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = Path(tmp_dir) / "schedule.csv"
            write_batch_csv(
                [assignment],
                out_path,
                {"R1": "101教室"},
                class_metadata={},
                product_course_tags=product_course_tags,
            )
            with out_path.open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                rows = list(reader)

        self.assertEqual(reader.fieldnames, BATCH_SCHEDULE_CSV_FIELDNAMES)
        self.assertEqual([row["lesson_slot"] for row in rows], ["AM1", "AM2"])
        self.assertEqual([row["slot_label"] for row in rows], ["上午一", "上午二"])
        self.assertEqual({row["weekday"] for row in rows}, {"周三"})
        self.assertEqual({row["course_code"] for row in rows}, {"ENG-VOC"})
        self.assertEqual({row["course_name"] for row in rows}, {"英语词汇"})
        self.assertEqual({row["room_name"] for row in rows}, {"101教室"})

    def test_write_day_table_html_embeds_display_payload(self) -> None:
        task = scheduler.CourseBlock(
            task_id="TASK_A",
            class_id="KYJSJ2773",
            class_name="测试班",
            product_id="P1",
            product_name="产品1",
            class_size=None,
            subject_category="公共课",
            subject="英语",
            quarter=None,
            stage="暑假",
            course_module="词汇",
            course_group="阅读类",
            teacher_id="T_1",
            teacher_name="老师1",
            block_hours=4,
            room_ids={"R1"},
            start_date=None,
            end_date=None,
            allowed_periods=None,
            allowed_weekdays=None,
            excluded_weekdays=None,
            schedule_rules=(),
        )
        assignment = scheduler.Assignment(
            task=task,
            candidate=scheduler.Candidate(
                slots=(
                    scheduler.TimeSlot(
                        "2026-07-01-AM",
                        "2026-07-01",
                        "AM",
                        "上午",
                        1,
                        "08:00",
                        "12:20",
                        4,
                    ),
                ),
                teacher_id="T_1",
                teacher_name="老师1",
                room_id="R1",
            ),
        )
        product_course_tags = [
            {
                "product_id": "P1",
                "subject": "英语",
                "quarter": "暑假",
                "stage": "",
                "course_module": "词汇",
                "course_group": "阅读类",
                "course_code": "ENG-VOC",
                "course_name": "英语词汇",
            }
        ]
        class_metadata = {
            "KYJSJ2773": {
                "suite_code": "2773",
                "product_id": "P1",
                "sub_product": "半年营",
            }
        }
        window_constraints = {
            "KYJSJ2773": [
                ClassWindowConstraint(
                    class_window_id="KYJSJ2773_2026暑假",
                    class_id="KYJSJ2773",
                    class_name="测试班",
                    product_id="P1",
                    schedule_window_id="2026暑假",
                    season_window_id="WINDOW_SUMMER",
                    season_name="暑假",
                    schedule_window_name="2026暑假",
                    earliest_date="2026-07-01",
                    earliest_period="AM",
                    latest_date="2026-08-31",
                    latest_period="PM",
                    teaching_area_ids=frozenset({"A1", "A3"}),
                    room_ids=frozenset({"R1", "R3"}),
                    preferred_room_is_required=True,
                    notes="暑假窗口",
                ),
                ClassWindowConstraint(
                    class_window_id="KYJSJ2773_2026秋季",
                    class_id="KYJSJ2773",
                    class_name="测试班",
                    product_id="P1",
                    schedule_window_id="2026秋季",
                    season_window_id="WINDOW_AUTUMN",
                    season_name="秋季",
                    schedule_window_name="2026秋季",
                    earliest_date="2026-09-01",
                    earliest_period="EVENING",
                    latest_date="2026-12-01",
                    latest_period="EVENING",
                    teaching_area_ids=frozenset({"A2"}),
                    room_ids=frozenset({"R2"}),
                    preferred_room_is_required=False,
                    notes="秋季窗口",
                ),
            ]
        }
        room_names = {"R1": "101教室", "R3": "103教室"}
        expected_payload = build_day_table_payload(
            [assignment],
            "测试课表",
            ["AM"],
            room_names,
            "2026-07-01",
            "2026-07-01",
            class_metadata,
            window_constraints,
            product_course_tags,
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = Path(tmp_dir) / "schedule.html"
            write_day_table_html(
                [assignment],
                out_path,
                "测试课表",
                ["AM"],
                room_names,
                "2026-07-01",
                "2026-07-01",
                class_metadata,
                window_constraints,
                product_course_tags,
            )
            html_text = out_path.read_text(encoding="utf-8")

        marker = '<script id="schedulePayload" type="application/json">'
        payload_text = html_text.split(marker, 1)[1].split("</script>", 1)[0]
        payload = json.loads(payload_text)

        self.assertEqual(payload, expected_payload)
        self.assertEqual(payload["title"], "测试课表")
        self.assertEqual(payload["dates"], ["2026-07-01"])
        self.assertEqual([slot["id"] for slot in payload["slotRows"]], ["AM1", "AM2"])
        self.assertEqual([row["lesson_slot"] for row in payload["rows"]], ["AM1", "AM2"])
        self.assertEqual({row["suite_code"] for row in payload["rows"]}, {"2775"})
        self.assertEqual({row["course_code"] for row in payload["rows"]}, {"ENG-VOC"})
        self.assertEqual({row["course_name"] for row in payload["rows"]}, {"英语词汇"})
        self.assertEqual({row["room_name"] for row in payload["rows"]}, {"101教室"})
        self.assertEqual([row["window_name"] for row in payload["constraints"]], ["2026暑假", "2026秋季"])
        self.assertEqual(payload["constraints"][0]["teaching_area_ids"], "A1|A3")
        self.assertEqual(payload["constraints"][0]["room_ids"], "R1|R3")
        self.assertEqual(payload["constraints"][0]["room_names"], "101教室 / 103教室")
        self.assertNotIn("checkin_date", payload["constraints"][0])
        self.assertNotIn("checkout_date", payload["constraints"][0])
        self.assertIn("默认展示当前结果的完整日期范围", html_text)
        self.assertNotIn("默认展示 2026-06-25 至 2026-12-13", html_text)
        self.assertNotIn("DEFAULT_START_DATE", html_text)
        self.assertNotIn("DEFAULT_END_DATE", html_text)
        ids = re.findall(r'id="([^"]+)"', html_text)
        duplicate_ids = [item for item, count in Counter(ids).items() if count > 1]
        self.assertEqual(duplicate_ids, [])
        self.assertEqual(html_text.count("const uniqueValues"), 1)

    def test_assignment_from_row_uses_standard_slots_for_four_hour_halfday(self) -> None:
        assignment = assignment_from_row(
            {
                "date": "2026-07-22",
                "period": "PM",
                "start_time": "14:00",
                "end_time": "18:20",
                "duration_hours": "4",
                "class_id": "KYJXZ2751",
                "subject": "政治",
                "teacher_id": "143724",
                "teacher_name": "张珊珊",
                "room_id": "R_NY",
            },
            "TEST:1",
        )
        self.assertEqual([slot.id for slot in assignment.candidate.slots], ["2026-07-22-PM-1", "2026-07-22-PM-2"])

    def test_relaxed_candidates_do_not_expose_legacy_teacher_slot_field(self) -> None:
        assignment = make_teacher_travel_assignment(
            "KYYY2750",
            scheduler.TimeSlot("OLD_SLOT_ONLY", "2026-07-22", "AM", "上午", 1, "08:00", "12:20", 4),
            "R_NY",
        )
        self.assertFalse(hasattr(assignment.task, "teacher_available_slots"))
        time_slots = [
            scheduler.TimeSlot("2026-07-22-AM-1", "2026-07-22", "AM", "上午一", 1, "08:00", "10:00", 2),
            scheduler.TimeSlot("2026-07-22-AM-2", "2026-07-22", "AM", "上午二", 2, "10:20", "12:20", 2),
        ]

        candidates = relaxed_candidates_on_date(assignment, time_slots, "2026-07-22", "AM")

        self.assertEqual(len(candidates), 1)
        self.assertEqual([slot.id for slot in candidates[0].slots], ["2026-07-22-AM-1", "2026-07-22-AM-2"])

    def test_display_slot_helpers_expand_halfday_blocks(self) -> None:
        slots = (
            scheduler.TimeSlot(
                id="2026-07-22_PM",
                date="2026-07-22",
                period="PM",
                name="下午",
                order=1,
                start_time="14:00",
                end_time="18:20",
                duration_hours=4,
            ),
        )

        self.assertEqual(assignment_display_slot_ids(slots, ["PM"]), ["PM1", "PM2"])
        self.assertEqual(
            [lesson["slot_id"] for lesson in assignment_standard_lesson_slots(slots, ["PM"])],
            ["PM1", "PM2"],
        )

    def test_front_loaded_week_quotas_places_extra_english_week_early(self) -> None:
        quotas = front_loaded_week_quotas(make_pm_blocks(), 14)
        self.assertEqual([quotas[key] for key in sorted(quotas)], [3, 2, 2, 2, 2, 2, 1])

    def test_front_loaded_week_quotas_places_extra_politics_weeks_early(self) -> None:
        quotas = front_loaded_week_quotas(make_pm_blocks(), 17)
        self.assertEqual([quotas[key] for key in sorted(quotas)], [3, 3, 3, 3, 2, 2, 1])

    def test_tail_week_quota_can_be_reassigned_to_earliest_light_week(self) -> None:
        blocks = make_pm_blocks()
        quotas = front_loaded_week_quotas(blocks, 14)
        tail_week = max(quotas)
        quotas[tail_week] -= 1
        shift_tail_week_quota_to_early(quotas, blocks, tail_week, 1)
        self.assertEqual([quotas[key] for key in sorted(quotas)], [3, 3, 2, 2, 2, 2, 0])

    def test_average_subject_week_bounds_use_effective_available_weeks(self) -> None:
        blocks = make_pm_blocks()
        bounds = average_subject_week_bounds_from_counts(
            {"数学": blocks},
            {"数学": 20},
        )
        self.assertEqual(bounds["数学"], (3, 4))

    def test_average_subject_week_bounds_spread_sparse_subjects_without_impossible_min(self) -> None:
        blocks = make_pm_blocks()
        bounds = average_subject_week_bounds_from_counts(
            {"政治": blocks},
            {"政治": 4},
        )
        self.assertEqual(bounds["政治"], (None, 1))

    def test_long_camp_math_allows_three_days_but_flags_fourth_day(self) -> None:
        dates = {"2026-07-06", "2026-07-07"}
        self.assertFalse(creates_teacher_run_over_limit(dates, "2026-07-08", 3))
        self.assertTrue(
            creates_teacher_run_over_limit(
                {*dates, "2026-07-08"},
                "2026-07-09",
                3,
            )
        )

    def test_run_dates_detects_consecutive_windows(self) -> None:
        dates = {"2026-07-06", "2026-07-07", "2026-07-08", "2026-07-10"}
        self.assertEqual(run_dates(dates), [("2026-07-06", "2026-07-07", "2026-07-08")])
        self.assertEqual(
            run_dates_over_limit({"2026-07-06", "2026-07-07", "2026-07-08", "2026-07-09"}, 3),
            [("2026-07-06", "2026-07-07", "2026-07-08", "2026-07-09")],
        )

    def test_long_camp_subject_targets_keep_one_halfday_per_available_week_when_feasible(self) -> None:
        weeks = [Date.fromisoformat("2026-07-06") + timedelta(days=7 * index) for index in range(4)]
        targets = long_camp_subject_week_targets(weeks, 6, "政治")
        self.assertEqual(sum(targets.values()), 6)
        self.assertTrue(all(value >= 1 for value in targets.values()))
        self.assertLessEqual(max(targets.values()) - min(targets.values()), 1)

    def test_long_camp_subject_targets_do_not_invent_lessons_when_minimum_is_impossible(self) -> None:
        weeks = [Date.fromisoformat("2026-07-06") + timedelta(days=7 * index) for index in range(4)]
        targets = long_camp_subject_week_targets(weeks, 2, "政治")
        self.assertEqual(sum(targets.values()), 2)
        self.assertEqual(sorted(targets.values()), [0, 0, 1, 1])

    def test_long_camp_subject_week_bounds_require_one_halfday_minimum(self) -> None:
        bounds = long_camp_subject_week_bounds({"英语", "政治", "数学"})
        self.assertEqual(bounds["数学"], (1, 4))
        self.assertEqual(bounds["政治"], (1, 3))
        self.assertEqual(bounds["英语"], (1, 4))

    def test_wuyou_qc_autumn_window_starts_all_subjects_on_september_fifth(self) -> None:
        self.assertEqual(WYQC_AUTUMN_START, "2026-09-05")
        self.assertEqual(WYQC_AUTUMN_END, "2026-12-06")
        self.assertEqual(WYQC_SPRINT_START_BY_SUBJECT["英语"], "2026-09-05")
        self.assertEqual(WYQC_SPRINT_START_BY_SUBJECT["数学"], "2026-09-05")
        self.assertEqual(WYQC_SPRINT_START_BY_SUBJECT["政治"], "2026-09-05")

    def test_wuyou_qc_autumn_warnings_explain_sparse_subject_weeks(self) -> None:
        assignment = assignment_from_row(
            {
                "date": "2026-09-05",
                "period": "AM",
                "start_time": "08:30",
                "end_time": "12:30",
                "duration_hours": "4",
                "class_id": "KYYY2701",
                "class_name": "27考研无忧秋英语2701班",
                "subject": "英语",
                "stage": "冲刺",
                "teacher_id": "100001",
                "teacher_name": "测试老师",
                "room_id": "ONLINE",
            },
            "TEST:1",
        )
        warnings = student_experience_warning_lines(
            [assignment],
            {
                "KYYY2701": {
                    "suite_code": "2701",
                    "sub_product": "无忧秋",
                    "subject_category": "公共课",
                }
            },
            set(),
        )
        self.assertTrue(
            any(
                "无忧秋 2701 秋季 英语: 剩余 1 个半天少于 14 个周段"
                in line
                for line in warnings
            )
        )

    def test_teacher_same_day_prefers_same_teaching_area(self) -> None:
        morning = scheduler.TimeSlot("2026-07-06-AM", "2026-07-06", "AM", "上午", 1, duration_hours=2)
        afternoon = scheduler.TimeSlot("2026-07-06-PM", "2026-07-06", "PM", "下午", 2, duration_hours=2)
        locked_task = scheduler.CourseBlock(
            task_id="LOCKED",
            class_id="A",
            class_name="A",
            product_id=None,
            product_name=None,
            class_size=None,
            subject_category="公共课",
            subject="英语",
            quarter=None,
            stage=None,
            course_module=None,
            course_group=None,
            teacher_id="T1",
            teacher_name="老师",
            block_hours=2,
            room_ids={"R_NS"},
            start_date=None,
            end_date=None,
            allowed_periods=None,
            allowed_weekdays=None,
            excluded_weekdays=None,
            schedule_rules=(),
            is_locked=True,
        )
        locked = scheduler.Assignment(locked_task, scheduler.Candidate((morning,), "T1", "老师", "R_NS"))
        cls = scheduler.SchoolClass(
            id="B",
            name="B",
            product_id=None,
            product_name=None,
            size=None,
            room_ids={"R_NS", "R_BH"},
            start_date=None,
            start_period=None,
            end_date=None,
            end_period=None,
            first_lesson_date=None,
            first_lesson_period=None,
            stage_order={},
            requirements=[
                scheduler.Requirement(
                    subject_category="公共课",
                    subject="英语",
                    quarter=None,
                    stage=None,
                    course_module=None,
                    course_group=None,
                    teacher_id="T1",
                    teacher_name="老师",
                    total_hours=2,
                    block_hours=2,
                    room_ids={"R_NS", "R_BH"},
                    allowed_periods={"PM"},
                )
            ],
        )
        schedule_input = scheduler.ScheduleInput(
            time_slots=[morning, afternoon],
            rooms={
                "R_NS": scheduler.Room("R_NS", teaching_area_id="A_NS", region_tag="新站/瑶海"),
                "R_BH": scheduler.Room("R_BH", teaching_area_id="A_BH", region_tag="包河/滨湖"),
            },
            classes={"B": cls},
            conflict_groups={},
            class_conflict_groups={"B": set(), "A": set()},
            locked_assignments=[locked],
            area_travel_minutes={("A_BH", "A_NS"): 40},
        )
        generated = [assignment for assignment in scheduler.schedule(schedule_input) if not assignment.task.is_locked]
        self.assertEqual(generated[0].candidate.room_id, "R_NS")

    def test_new_station_to_binhu_has_heavier_teacher_travel_penalty_than_same_region(self) -> None:
        morning = scheduler.TimeSlot("2026-07-06-AM", "2026-07-06", "AM", "上午", 1, duration_hours=2)
        afternoon = scheduler.TimeSlot("2026-07-06-PM", "2026-07-06", "PM", "下午", 2, duration_hours=2)
        task = scheduler.CourseBlock(
            task_id="T",
            class_id="B",
            class_name="B",
            product_id=None,
            product_name=None,
            class_size=None,
            subject_category="公共课",
            subject="政治",
            quarter=None,
            stage=None,
            course_module=None,
            course_group=None,
            teacher_id="T1",
            teacher_name="老师",
            block_hours=2,
            room_ids={"R_BH", "R_XZ2"},
            start_date=None,
            end_date=None,
            allowed_periods=None,
            allowed_weekdays=None,
            excluded_weekdays=None,
            schedule_rules=(),
        )
        locked_task = scheduler.CourseBlock(
            task_id="LOCKED",
            class_id="A",
            class_name="A",
            product_id=None,
            product_name=None,
            class_size=None,
            subject_category="公共课",
            subject="政治",
            quarter=None,
            stage=None,
            course_module=None,
            course_group=None,
            teacher_id="T1",
            teacher_name="老师",
            block_hours=2,
            room_ids={"R_XZ1"},
            start_date=None,
            end_date=None,
            allowed_periods=None,
            allowed_weekdays=None,
            excluded_weekdays=None,
            schedule_rules=(),
            is_locked=True,
        )
        locked = scheduler.Assignment(locked_task, scheduler.Candidate((morning,), "T1", "老师", "R_XZ1"))
        schedule_input = scheduler.ScheduleInput(
            time_slots=[morning, afternoon],
            rooms={
                "R_XZ1": scheduler.Room("R_XZ1", teaching_area_id="A_XZ1", region_tag="新站/瑶海"),
                "R_XZ2": scheduler.Room("R_XZ2", teaching_area_id="A_XZ2", region_tag="新站/瑶海"),
                "R_BH": scheduler.Room("R_BH", teaching_area_id="A_BH", region_tag="包河/滨湖"),
            },
            classes={},
            conflict_groups={},
            class_conflict_groups={},
            locked_assignments=[locked],
            area_travel_minutes={("A_BH", "A_XZ1"): 41, ("A_XZ1", "A_XZ2"): 12},
        )
        same_region_penalty = scheduler.candidate_same_day_teacher_travel_penalty(
            schedule_input,
            [locked],
            task,
            scheduler.Candidate((afternoon,), "T1", "老师", "R_XZ2"),
        )
        cross_region_penalty = scheduler.candidate_same_day_teacher_travel_penalty(
            schedule_input,
            [locked],
            task,
            scheduler.Candidate((afternoon,), "T1", "老师", "R_BH"),
        )
        self.assertLess(same_region_penalty, cross_region_penalty)

    def test_teacher_travel_penalty_skips_non_travel_contexts_and_keeps_region_penalty(self) -> None:
        morning = scheduler.TimeSlot("2026-07-06-AM", "2026-07-06", "AM", "上午", 1, duration_hours=2)
        afternoon = scheduler.TimeSlot("2026-07-06-PM", "2026-07-06", "PM", "下午", 2, duration_hours=2)
        candidate_assignment = make_teacher_travel_assignment(
            "CAND",
            afternoon,
            "R_REMOTE",
            teacher_id="T1",
            task_id="TASK_CAND",
        )
        schedule_input = scheduler.ScheduleInput(
            time_slots=[morning, afternoon],
            rooms={
                "R_REMOTE": scheduler.Room("R_REMOTE", teaching_area_id="A_REMOTE", region_tag="新站"),
                "R_PARALLEL": scheduler.Room("R_PARALLEL", teaching_area_id="A_PARALLEL", region_tag="滨湖"),
                "R_SAME_AREA": scheduler.Room("R_SAME_AREA", teaching_area_id="A_REMOTE", region_tag="包河"),
                "R_SAME_REGION": scheduler.Room("R_SAME_REGION", teaching_area_id="A_NEAR", region_tag="新站/瑶海"),
            },
            classes={},
            conflict_groups={},
            class_conflict_groups={},
            locked_assignments=[],
            area_travel_minutes={("A_NEAR", "A_REMOTE"): 15},
        )
        existing = [
            make_teacher_travel_assignment("PARALLEL", afternoon, "R_PARALLEL", teacher_id="T1"),
            make_teacher_travel_assignment("SAME_TASK", morning, "R_PARALLEL", teacher_id="T1", task_id="TASK_CAND"),
            make_teacher_travel_assignment("SAME_AREA", morning, "R_SAME_AREA", teacher_id="T1"),
            make_teacher_travel_assignment("SAME_REGION", morning, "R_SAME_REGION", teacher_id="T1"),
        ]

        penalty = scheduler.candidate_same_day_teacher_travel_penalty(
            schedule_input,
            existing,
            candidate_assignment.task,
            candidate_assignment.candidate,
        )

        self.assertEqual(penalty, 500)

    def test_teacher_same_day_campus_warning_collapses_parallel_class_pairs(self) -> None:
        morning = scheduler.TimeSlot("2026-07-22-AM", "2026-07-22", "AM", "上午", 1, duration_hours=4)
        afternoon = scheduler.TimeSlot("2026-07-22-PM", "2026-07-22", "PM", "下午", 2, duration_hours=4)
        assignments = [
            make_teacher_travel_assignment("KYJXZ2766", morning, "R_YG"),
            make_teacher_travel_assignment("KYJXZ2770", morning, "R_YG"),
            make_teacher_travel_assignment("KYJXZ2751", afternoon, "R_NY"),
            make_teacher_travel_assignment("KYJXZ2753", afternoon, "R_NY"),
        ]
        lines = teacher_same_day_campus_warning_lines(
            assignments,
            rooms={
                "R_YG": scheduler.Room(
                    "R_YG",
                    teaching_area_id="AREA_YG",
                    teaching_area_name="云谷",
                    region_tag="新站",
                ),
                "R_NY": scheduler.Room(
                    "R_NY",
                    teaching_area_id="AREA_NY",
                    teaching_area_name="南亚",
                    region_tag="滨湖",
                ),
            },
            area_travel_minutes={("AREA_NY", "AREA_YG"): 36},
        )
        self.assertEqual(len(lines), 1)
        self.assertIn("AM 云谷（KYJXZ2766、KYJXZ2770）", lines[0])
        self.assertIn("PM 南亚（KYJXZ2751、KYJXZ2753）", lines[0])

    def test_teacher_time_conflict_detects_parallel_different_rooms(self) -> None:
        morning = scheduler.TimeSlot(
            "2026-07-22-AM-1",
            "2026-07-22",
            "AM",
            "上午一",
            1,
            "08:00",
            "10:00",
            2,
        )
        assignments = [
            make_teacher_travel_assignment("KYJXZ2766", morning, "R_YG_503"),
            make_teacher_travel_assignment("KYJXZ2770", morning, "R_YG_507"),
        ]
        lines = teacher_time_conflict_lines(assignments)
        self.assertEqual(len(lines), 1)
        self.assertIn("张珊珊", lines[0])
        self.assertIn("KYJXZ2766", lines[0])
        self.assertIn("KYJXZ2770", lines[0])

    def test_candidate_conflict_checker_reports_core_hard_constraints(self) -> None:
        morning = scheduler.TimeSlot(
            "2026-07-22-AM-1",
            "2026-07-22",
            "AM",
            "上午一",
            1,
            "08:00",
            "10:00",
            2,
        )
        candidate = make_teacher_travel_assignment("CLASS_A", morning, "R_101", "T_1", "老师1", "candidate")
        same_class = make_teacher_travel_assignment("CLASS_A", morning, "R_102", "T_2", "老师2", "same_class")
        same_teacher = make_teacher_travel_assignment("CLASS_B", morning, "R_103", "T_1", "老师1")
        same_room = make_teacher_travel_assignment("CLASS_C", morning, "R_101", "T_3", "老师3")
        mutual_class = make_teacher_travel_assignment("CLASS_D", morning, "R_104", "T_4", "老师4")
        unrelated = make_teacher_travel_assignment("CLASS_E", morning, "R_105", "T_5", "老师5")

        conflicts = assignments_conflicting_with_candidate(
            candidate,
            [same_class, same_teacher, same_room, mutual_class, unrelated],
            {"CLASS_A": {"GROUP_1"}, "CLASS_D": {"GROUP_1"}},
        )

        self.assertEqual(
            [item.task.class_id for item in conflicts],
            ["CLASS_A", "CLASS_B", "CLASS_C", "CLASS_D"],
        )

    def test_candidate_conflict_checker_ignores_non_overlapping_assignments(self) -> None:
        morning = scheduler.TimeSlot(
            "2026-07-22-AM-1",
            "2026-07-22",
            "AM",
            "上午一",
            1,
            "08:00",
            "10:00",
            2,
        )
        afternoon = scheduler.TimeSlot(
            "2026-07-22-PM-1",
            "2026-07-22",
            "PM",
            "下午一",
            2,
            "14:00",
            "16:00",
            2,
        )
        candidate = make_teacher_travel_assignment("CLASS_A", morning, "R_101", "T_1", "老师1", "candidate")
        same_teacher_later = make_teacher_travel_assignment("CLASS_B", afternoon, "R_101", "T_1", "老师1")

        self.assertEqual(
            assignments_conflicting_with_candidate(candidate, [same_teacher_later], {}),
            [],
        )

    def test_assignment_constraint_sets_include_locked_and_placed_assignments(self) -> None:
        morning = scheduler.TimeSlot(
            "2026-07-22-AM-1",
            "2026-07-22",
            "AM",
            "上午一",
            1,
            "08:00",
            "10:00",
            2,
        )
        locked = make_teacher_travel_assignment("LOCKED_CLASS", morning, "R_LOCK", "T_LOCK", "锁定老师", "locked")
        placed = make_teacher_travel_assignment("CLASS_A", morning, "R_101", "T_1", "老师1", "placed")
        schedule_input = scheduler.ScheduleInput(
            time_slots=[morning],
            rooms={},
            classes={},
            conflict_groups={},
            class_conflict_groups={"LOCKED_CLASS": {"LOCKED_GROUP"}, "CLASS_A": {"GROUP_1"}},
            locked_assignments=[locked],
        )

        class_used, teacher_used, room_used, conflict_used = assignment_constraint_sets(schedule_input, [placed])

        self.assertIn(("LOCKED_CLASS", morning.id), class_used)
        self.assertIn(("CLASS_A", morning.id), class_used)
        self.assertIn(("T_LOCK", morning.id), teacher_used)
        self.assertIn(("T_1", morning.id), teacher_used)
        self.assertIn(("R_LOCK", morning.id), room_used)
        self.assertIn(("R_101", morning.id), room_used)
        self.assertIn(("LOCKED_GROUP", morning.id), conflict_used)
        self.assertIn(("GROUP_1", morning.id), conflict_used)

        excluded_class_used, excluded_teacher_used, excluded_room_used, excluded_conflict_used = assignment_constraint_sets(
            schedule_input,
            [placed],
            excluded_index=0,
        )
        self.assertIn(("LOCKED_CLASS", morning.id), excluded_class_used)
        self.assertNotIn(("CLASS_A", morning.id), excluded_class_used)
        self.assertNotIn(("T_1", morning.id), excluded_teacher_used)
        self.assertNotIn(("R_101", morning.id), excluded_room_used)
        self.assertNotIn(("GROUP_1", morning.id), excluded_conflict_used)

    def test_place_candidate_updates_constraint_sets_for_future_candidates(self) -> None:
        morning = scheduler.TimeSlot(
            "2026-07-22-AM-1",
            "2026-07-22",
            "AM",
            "上午一",
            1,
            "08:00",
            "10:00",
            2,
        )
        schedule_input = scheduler.ScheduleInput(
            time_slots=[morning],
            rooms={},
            classes={},
            conflict_groups={},
            class_conflict_groups={"CLASS_A": {"GROUP_1"}, "CLASS_B": {"GROUP_1"}},
            locked_assignments=[],
        )
        placed = make_teacher_travel_assignment("CLASS_A", morning, "R_101", "T_1", "老师1", "placed")
        constraint_sets = assignment_constraint_sets(schedule_input, [])

        assignment = place_candidate(schedule_input, *constraint_sets, placed.task, placed.candidate)

        self.assertEqual(assignment.task.task_id, "placed")
        same_class = make_teacher_travel_assignment("CLASS_A", morning, "R_102", "T_2", "老师2")
        same_teacher = make_teacher_travel_assignment("CLASS_C", morning, "R_103", "T_1", "老师1")
        same_room = make_teacher_travel_assignment("CLASS_D", morning, "R_101", "T_4", "老师4")
        mutual_class = make_teacher_travel_assignment("CLASS_B", morning, "R_104", "T_5", "老师5")

        for candidate in (same_class, same_teacher, same_room, mutual_class):
            self.assertFalse(candidate_is_valid(schedule_input, *constraint_sets, candidate.task, candidate.candidate))

    def test_candidate_conflict_checker_enforces_product_day_limits(self) -> None:
        morning = scheduler.TimeSlot(
            "2026-07-22-AM-1",
            "2026-07-22",
            "AM",
            "上午",
            1,
            "08:00",
            "10:00",
            2,
            season_window_id="WINDOW_SUMMER",
            season_name="暑假",
        )
        afternoon = scheduler.TimeSlot(
            "2026-07-22-PM-1",
            "2026-07-22",
            "PM",
            "下午",
            2,
            "14:00",
            "16:00",
            2,
            season_window_id="WINDOW_SUMMER",
            season_name="暑假",
        )
        rule = scheduler.ScheduleRule(
            subject=None,
            stage=None,
            course_module=None,
            course_group=None,
            start_date=None,
            end_date=None,
            allowed_periods={"AM", "PM"},
            allowed_weekdays=None,
            excluded_weekdays=None,
            block_hours=2,
            season_window_ids={"WINDOW_SUMMER"},
            window_names={"暑假"},
            max_hours_per_class_per_day=2,
            max_blocks_per_class_per_day=1,
        )
        task = scheduler.CourseBlock(
            task_id="CLASS_A:英语:1",
            class_id="CLASS_A",
            class_name="暑假班",
            product_id="P1",
            product_name="暑假产品",
            class_size=None,
            subject_category="公共课",
            subject="英语",
            quarter="暑假",
            stage="基础",
            course_module="词汇",
            course_group="阅读类",
            teacher_id="T_2",
            teacher_name="老师2",
            block_hours=2,
            room_ids={"R_102"},
            start_date=None,
            end_date=None,
            allowed_periods=None,
            allowed_weekdays=None,
            excluded_weekdays=None,
            schedule_rules=(rule,),
        )
        schedule_input = scheduler.ScheduleInput(
            time_slots=[morning, afternoon],
            rooms={"R_101": scheduler.Room("R_101"), "R_102": scheduler.Room("R_102")},
            classes={},
            conflict_groups={},
            class_conflict_groups={"CLASS_A": set()},
            locked_assignments=[],
        )
        placed = make_teacher_travel_assignment("CLASS_A", morning, "R_101", "T_1", "老师1", "placed")
        constraint_sets = assignment_constraint_sets(schedule_input, [placed])
        candidate = scheduler.Candidate((afternoon,), "T_2", "老师2", "R_102")

        self.assertFalse(candidate_is_valid(schedule_input, *constraint_sets, task, candidate))

    def test_class_teacher_day_loads_include_locked_lessons_for_daily_limit(self) -> None:
        locked_slot = scheduler.TimeSlot(
            "2026-07-22-AM",
            "2026-07-22",
            "AM",
            "上午",
            1,
            "08:00",
            "14:00",
            6,
        )
        candidate_slot = scheduler.TimeSlot(
            "2026-07-22-PM",
            "2026-07-22",
            "PM",
            "下午",
            2,
            "14:00",
            "16:00",
            2,
        )
        locked = make_teacher_travel_assignment("CLASS_A", locked_slot, "R_101", "T_1", "老师1", "locked")
        candidate = make_teacher_travel_assignment("CLASS_A", candidate_slot, "R_102", "T_1", "老师1", "candidate")
        schedule_input = scheduler.ScheduleInput(
            time_slots=[locked_slot, candidate_slot],
            rooms={},
            classes={},
            conflict_groups={},
            class_conflict_groups={},
            locked_assignments=[locked],
        )

        loads = class_teacher_day_loads(schedule_input, [])

        self.assertEqual(loads[("CLASS_A", "T_1", "2026-07-22")], 6)
        self.assertFalse(
            scheduler.candidate_avoids_same_class_teacher_day_limit(loads, candidate.task, candidate.candidate)
        )

    def test_teacher_time_conflict_allows_same_room_merge_display(self) -> None:
        morning = scheduler.TimeSlot(
            "2026-07-22-AM-1",
            "2026-07-22",
            "AM",
            "上午一",
            1,
            "08:00",
            "10:00",
            2,
        )
        assignments = [
            make_teacher_travel_assignment("KYJXY2750", morning, "ONLINE_01"),
            make_teacher_travel_assignment("KYJXY2751", morning, "ONLINE_01"),
        ]
        self.assertEqual(teacher_time_conflict_lines(assignments), [])

    def test_public_coverage_gap_rows_block_unfinished_public_classes(self) -> None:
        rows = public_coverage_gap_rows_from_totals(
            Counter({"KYYY2701": 188.0, "KYXY2770": 160.0}),
            Counter({"KYYY2701": 176.0, "KYXY2770": 120.0}),
            {
                "KYYY2701": {
                    "name": "英语班",
                    "subject_category": "公共课",
                    "sub_product": "无忧秋",
                    "subject": "英语",
                    "suite_code": "2701",
                    "is_schedule_locked": "否",
                },
                "KYXY2770": {
                    "name": "西医班",
                    "subject_category": "专业课",
                    "sub_product": "半年营",
                    "subject": "西医",
                    "suite_code": "2770",
                    "is_schedule_locked": "是",
                },
            },
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["class_id"], "KYYY2701")
        self.assertEqual(rows[0]["gap_hours"], 12.0)
        self.assertIn("KYYY2701", "\n".join(coverage_gap_blocking_lines(rows)))


if __name__ == "__main__":
    unittest.main()
