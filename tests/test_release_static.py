from __future__ import annotations

import re
import unittest
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
PERSONAL_PATH_MARKERS = ("/Users/" + "plzhz", "Down" + "loads" + "/")
TEXT_RELEASE_SUFFIXES = {".csv", ".html", ".js", ".json", ".md", ".py", ".sh", ".txt", ".yml"}


def release_text_files() -> Iterable[Path]:
    top_level_files = [
        ROOT / ".env.example",
        ROOT / ".gitignore",
        ROOT / "LAUNCH_CHECKLIST.md",
        ROOT / "PUBLIC_SCHEDULE_DEPLOY.md",
        ROOT / "README.md",
        ROOT / "SCHEDULING_RULES_REVIEW_20260524.md",
    ]
    for path in top_level_files:
        yield path
    for directory in (".github", "cloudflare_schedule_publish", "docs", "examples", "scripts", "share", "tests", "web_admin"):
        for path in sorted((ROOT / directory).rglob("*")):
            if path.is_file() and path.suffix in TEXT_RELEASE_SUFFIXES:
                yield path
    for path in sorted(ROOT.glob("*.py")):
        yield path


class ReleaseStaticTest(unittest.TestCase):
    def test_scripts_do_not_ship_personal_default_paths(self) -> None:
        offenders = []
        for path in sorted((ROOT / "scripts").glob("*.py")):
            source = path.read_text(encoding="utf-8")
            if any(marker in source for marker in PERSONAL_PATH_MARKERS):
                offenders.append(str(path.relative_to(ROOT)))

        self.assertEqual([], offenders)

    def test_release_docs_do_not_ship_personal_paths(self) -> None:
        offenders = []
        paths = [ROOT / "README.md", ROOT / "PUBLIC_SCHEDULE_DEPLOY.md", ROOT / "LAUNCH_CHECKLIST.md"]
        paths.extend(sorted((ROOT / "docs").rglob("*.md")))
        paths.extend(sorted((ROOT / "share").rglob("*.html")))
        for path in paths:
            source = path.read_text(encoding="utf-8")
            if any(marker in source for marker in PERSONAL_PATH_MARKERS):
                offenders.append(str(path.relative_to(ROOT)))

        self.assertEqual([], offenders)

    def test_release_verification_runs_audits(self) -> None:
        script = (ROOT / "scripts" / "verify_release.sh").read_text(encoding="utf-8")

        self.assertIn("scripts/audit_schedule_coverage.py", script)
        self.assertIn("scripts/audit_schedule_quality.py", script)
        self.assertIn("scripts/audit_release_package.py", script)
        self.assertIn("scripts/build_release_archive.py", script)
        self.assertIn("git archive --format=zip", script)
        self.assertIn("git diff --quiet && git diff --cached --quiet", script)
        self.assertIn("Tracked working tree has uncommitted changes", script)
        self.assertIn('--zip "$WORK_DIR/release_package_audit.zip"', script)
        self.assertIn("schedule_coverage_audit_verify_run.md", script)
        self.assertIn("schedule_quality_report_verify_run.md", script)

    def test_release_verification_compiles_all_python_scripts(self) -> None:
        script = (ROOT / "scripts" / "verify_release.sh").read_text(encoding="utf-8")

        self.assertIn('export PYTHONPYCACHEPREFIX="$WORK_DIR/pycache"', script)
        self.assertIn('find scripts -name "*.py"', script)
        self.assertIn("-m py_compile \"$script_path\"", script)
        self.assertIn("verify_cli_help()", script)
        self.assertIn('verify_cli_help "$script_path"', script)
        self.assertIn('--help >/dev/null', script)
        self.assertIn('scheduler.py \\', script)
        self.assertIn('run_scheduling_pipeline.py \\', script)
        self.assertIn('data_admin_server.py \\', script)
        self.assertIn('grep -q "argparse" "$script_path"', script)
        self.assertIn('grep -q "if __name__" "$script_path"', script)

    def test_release_surface_does_not_reintroduce_summer_lodging_constraints(self) -> None:
        forbidden_terms = [
            "camp_" + "lodging_" + "constraints",
            "schedule_" + "lodging",
            "summer_" + "room_" + "constraint",
            "暑假" + "住宿" + "上课" + "约束",
            "住宿" + "上课" + "约束",
        ]
        offenders = []
        for path in release_text_files():
            source = path.read_text(encoding="utf-8")
            matches = [term for term in forbidden_terms if term in source]
            if matches:
                offenders.append(f"{path.relative_to(ROOT)}: {', '.join(matches)}")

        self.assertEqual([], offenders)

    def test_ci_runs_release_verification(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

        self.assertIn("actions/setup-python", workflow)
        self.assertIn("python3 -m pip install -r requirements.txt", workflow)
        self.assertIn("bash scripts/verify_release.sh", workflow)

    def test_standard_table_schema_lives_outside_admin_server(self) -> None:
        admin_source = (ROOT / "data_admin_server.py").read_text(encoding="utf-8")
        schema_source = (ROOT / "scripts" / "table_schema.py").read_text(encoding="utf-8")
        formal_template_source = (ROOT / "formal_template.py").read_text(encoding="utf-8")

        self.assertIn("from scripts.table_schema import", admin_source)
        self.assertIn("STANDARD_TABLE_FIELDNAMES", schema_source)
        self.assertIsNone(re.search(r"(?m)^PRODUCT_FIELDNAMES\s*=", admin_source))
        self.assertIsNone(re.search(r"(?m)^STANDARD_TABLE_FIELDNAMES\s*[:=]", admin_source))
        self.assertIsNone(re.search(r"(?m)^CLASS_JSON_EXTRA_FIELDNAMES\s*=", admin_source))
        self.assertIn("from scripts.table_schema import", formal_template_source)
        self.assertNotIn("data_admin_server.BUSINESS_PRODUCT_MAPPING_FIELDNAMES", formal_template_source)
        self.assertNotIn("data_admin_server.TEACHER_ASSIGNMENT_FIELDNAMES", formal_template_source)

    def test_product_catalog_logic_lives_outside_admin_server(self) -> None:
        admin_source = (ROOT / "data_admin_server.py").read_text(encoding="utf-8")
        pipeline_source = (ROOT / "run_scheduling_pipeline.py").read_text(encoding="utf-8")
        formal_template_source = (ROOT / "formal_template.py").read_text(encoding="utf-8")

        self.assertIn("from scripts.product_catalog import", admin_source)
        self.assertIn("from scripts.product_catalog import", pipeline_source)
        self.assertIn("from scripts.product_catalog import", formal_template_source)
        self.assertNotIn("import data_admin_server", formal_template_source)
        self.assertIsNone(re.search(r"(?m)^def product_catalog\(", admin_source))
        self.assertIsNone(re.search(r"(?m)^def infer_project\(", admin_source))
        self.assertIsNone(re.search(r"(?m)^def product_stage_order\(", admin_source))
        self.assertNotIn("data_admin_server.product_catalog", pipeline_source)

    def test_field_normalization_lives_in_shared_field_utils(self) -> None:
        admin_source = (ROOT / "data_admin_server.py").read_text(encoding="utf-8")
        product_catalog_source = (ROOT / "scripts" / "product_catalog.py").read_text(encoding="utf-8")
        business_import_source = (ROOT / "business_class_import.py").read_text(encoding="utf-8")
        pipeline_source = (ROOT / "run_scheduling_pipeline.py").read_text(encoding="utf-8")
        scheduler_source = (ROOT / "scheduler.py").read_text(encoding="utf-8")
        erp_lesson_map_source = (ROOT / "scripts" / "build_erp_lesson_id_map.py").read_text(encoding="utf-8")
        erp_adjusted_sync_source = (ROOT / "scripts" / "sync_erp_adjusted_schedule.py").read_text(encoding="utf-8")

        self.assertIn("from scripts.field_utils import", admin_source)
        self.assertIn("from scripts.field_utils import", product_catalog_source)
        self.assertIn("from scripts.field_utils import", business_import_source)
        self.assertIn("from scripts.field_utils import", pipeline_source)
        self.assertIn("from scripts.field_utils import", scheduler_source)
        self.assertIn("from scripts.field_utils import", erp_lesson_map_source)
        self.assertIn("from scripts.field_utils import", erp_adjusted_sync_source)
        self.assertIn("normalize_blank_marker", admin_source)
        self.assertIn("blank_marker_to_empty", scheduler_source)
        self.assertIn("is_blank_marker", business_import_source)
        self.assertIsNone(re.search(r"(?m)^def normalize_int\(", admin_source))
        self.assertIsNone(re.search(r"(?m)^def normalize_float\(", admin_source))
        self.assertIsNone(re.search(r"(?m)^def normalize_date_text\(", admin_source))
        self.assertIsNone(re.search(r"(?m)^def normalize_time_text\(", admin_source))
        self.assertIsNone(re.search(r"(?m)^def normalize_blank_marker\(", admin_source))
        self.assertIsNone(re.search(r"(?m)^def normalize_time_value\(", scheduler_source))
        self.assertIsNone(re.search(r"(?m)^def blank_marker_to_empty\(", scheduler_source))
        self.assertIsNone(re.search(r"(?m)^def normalize_one_time\(", erp_lesson_map_source))
        self.assertIsNone(re.search(r"(?m)^def is_blank_marker\(", business_import_source))
        self.assertIsNone(re.search(r"(?m)^def normalize_int\(", product_catalog_source))
        self.assertNotIn("data_admin_server.normalize_int", business_import_source)
        self.assertIn("parse_date_value", business_import_source)
        self.assertIn("parse_time_minutes", business_import_source)
        self.assertNotIn("datetime.strptime(candidate, fmt)", business_import_source)
        self.assertNotIn("data_admin_server.normalize_text", pipeline_source)

    def test_list_value_splitting_lives_in_shared_field_utils(self) -> None:
        field_utils_source = (ROOT / "scripts" / "field_utils.py").read_text(encoding="utf-8")
        scheduler_source = (ROOT / "scheduler.py").read_text(encoding="utf-8")
        schedule_batch_source = (ROOT / "scripts" / "schedule_batch.py").read_text(encoding="utf-8")
        schedule_scope_source = (ROOT / "scripts" / "schedule_scope.py").read_text(encoding="utf-8")
        class_windows_source = (ROOT / "scripts" / "schedule_class_windows.py").read_text(encoding="utf-8")
        weekday_utils_source = (ROOT / "scripts" / "weekday_utils.py").read_text(encoding="utf-8")
        window_utils_source = (ROOT / "scripts" / "window_utils.py").read_text(encoding="utf-8")
        template_sync_source = (ROOT / "scripts" / "sync_template_workbook_to_admin_data.py").read_text(encoding="utf-8")
        erp_export_source = (ROOT / "scripts" / "export_erp_lesson_import.py").read_text(encoding="utf-8")
        erp_lesson_map_source = (ROOT / "scripts" / "build_erp_lesson_id_map.py").read_text(encoding="utf-8")
        camp_maintenance_source = (ROOT / "scripts" / "build_camp_maintenance_schedule.py").read_text(encoding="utf-8")

        self.assertIn("LIST_VALUE_SEPARATOR_RE", field_utils_source)
        self.assertIn("def split_delimited_values", field_utils_source)
        for source in (
            scheduler_source,
            schedule_batch_source,
            weekday_utils_source,
            window_utils_source,
            template_sync_source,
            erp_export_source,
            erp_lesson_map_source,
            camp_maintenance_source,
        ):
            self.assertIn("split_delimited_values", source)

        self.assertIn("normalize_iso_date_text", field_utils_source)
        self.assertIn("normalize_iso_date_text", schedule_batch_source)
        self.assertIn("normalize_iso_date_text", class_windows_source)
        self.assertIsNone(re.search(r"(?m)^def split_values\(", schedule_scope_source))
        self.assertIsNone(re.search(r"(?m)^def normalize_date\(", schedule_scope_source))
        self.assertIsNone(re.search(r"(?m)^def split_values\(", erp_export_source))
        self.assertIsNone(re.search(r"(?m)^def split_values\(", erp_lesson_map_source))
        self.assertIsNone(re.search(r"(?m)^def split_pipe_values\(", camp_maintenance_source))
        self.assertNotIn('.replace(",", "|").replace("，", "|").split("|")', erp_export_source)
        self.assertNotIn('.replace(",", "|").replace("，", "|").split("|")', erp_lesson_map_source)

    def test_erp_date_time_normalization_lives_in_shared_field_utils(self) -> None:
        field_utils_source = (ROOT / "scripts" / "field_utils.py").read_text(encoding="utf-8")
        erp_export_source = (ROOT / "scripts" / "export_erp_lesson_import.py").read_text(encoding="utf-8")
        erp_lesson_map_source = (ROOT / "scripts" / "build_erp_lesson_id_map.py").read_text(encoding="utf-8")
        failed_review_source = (ROOT / "scripts" / "build_failed_erp_class_schedule_review.py").read_text(encoding="utf-8")
        erp_adjusted_sync_source = (ROOT / "scripts" / "sync_erp_adjusted_schedule.py").read_text(encoding="utf-8")
        template_sync_source = (ROOT / "scripts" / "sync_template_workbook_to_admin_data.py").read_text(encoding="utf-8")

        self.assertIn("def display_date_text", field_utils_source)
        for source in (
            erp_export_source,
            erp_lesson_map_source,
            failed_review_source,
            erp_adjusted_sync_source,
            template_sync_source,
        ):
            self.assertIn("normalize_date_text", source)
        self.assertIn("display_date_text", erp_export_source)
        self.assertIn("display_date_text", failed_review_source)
        self.assertIn("normalize_time_text", erp_export_source)
        self.assertIn("normalize_time_text", template_sync_source)
        self.assertIn("split_time_range_text", erp_lesson_map_source)
        self.assertIn("split_time_range_text", erp_adjusted_sync_source)

        for source in (erp_export_source, erp_lesson_map_source, failed_review_source, erp_adjusted_sync_source):
            self.assertIsNone(re.search(r"(?m)^def normalize_date\(", source))
            self.assertNotIn("datetime.strptime", source)
        self.assertIsNone(re.search(r"(?m)^def display_date\(", erp_export_source))
        self.assertIsNone(re.search(r"(?m)^def display_date\(", failed_review_source))

    def test_lesson_datetime_parsing_lives_in_shared_field_utils(self) -> None:
        field_utils_source = (ROOT / "scripts" / "field_utils.py").read_text(encoding="utf-8")
        import_locked_source = (ROOT / "scripts" / "import_locked_professional_schedules.py").read_text(encoding="utf-8")
        camp_maintenance_source = (ROOT / "scripts" / "build_camp_maintenance_schedule.py").read_text(encoding="utf-8")

        self.assertIn("def parse_datetime_value", field_utils_source)
        self.assertIn("parse_datetime_value", import_locked_source)
        self.assertIn("parse_datetime_value", camp_maintenance_source)
        self.assertNotIn("datetime.strptime", import_locked_source)
        self.assertNotIn("datetime.strptime", camp_maintenance_source)

    def test_period_normalization_lives_in_shared_period_utils(self) -> None:
        scheduler_source = (ROOT / "scheduler.py").read_text(encoding="utf-8")
        business_import_source = (ROOT / "business_class_import.py").read_text(encoding="utf-8")
        class_windows_source = (ROOT / "scripts" / "schedule_class_windows.py").read_text(encoding="utf-8")
        erp_adjusted_sync_source = (ROOT / "scripts" / "sync_erp_adjusted_schedule.py").read_text(encoding="utf-8")
        period_utils_source = (ROOT / "scripts" / "period_utils.py").read_text(encoding="utf-8")

        self.assertIn("from scripts.period_utils import", scheduler_source)
        self.assertIn("from scripts.period_utils import", business_import_source)
        self.assertIn("from scripts.period_utils import", class_windows_source)
        self.assertIn("from scripts.period_utils import", erp_adjusted_sync_source)
        self.assertIn("VALID_PERIODS", period_utils_source)
        self.assertIn("PERIOD_ORDER", period_utils_source)
        self.assertIsNone(re.search(r"(?m)^VALID_PERIODS\s*=", scheduler_source))
        self.assertIsNone(re.search(r"(?m)^PERIOD_ORDER\s*=", scheduler_source))
        self.assertIsNone(re.search(r"(?m)^def period_sort_value\(", scheduler_source))
        self.assertIsNone(re.search(r"(?m)^def normalize_period\(", class_windows_source))
        self.assertIsNone(re.search(r"(?m)^PERIOD_ORDER\s*=", erp_adjusted_sync_source))
        self.assertIsNone(re.search(r"(?m)^\s*aliases\s*=\s*\{", business_import_source))

    def test_weekday_normalization_lives_in_shared_weekday_utils(self) -> None:
        scheduler_source = (ROOT / "scheduler.py").read_text(encoding="utf-8")
        generator_source = (ROOT / "generate_time_slots.py").read_text(encoding="utf-8")
        business_import_source = (ROOT / "business_class_import.py").read_text(encoding="utf-8")
        schedule_display_source = (ROOT / "scripts" / "schedule_display.py").read_text(encoding="utf-8")
        weekday_utils_source = (ROOT / "scripts" / "weekday_utils.py").read_text(encoding="utf-8")

        self.assertIn("from scripts.weekday_utils import", scheduler_source)
        self.assertIn("from scripts.weekday_utils import", generator_source)
        self.assertIn("from scripts.weekday_utils import", business_import_source)
        self.assertIn("from scripts.weekday_utils import", schedule_display_source)
        self.assertIn("WEEKDAY_ALIASES", weekday_utils_source)
        self.assertIn("WEEKDAY_LABELS", weekday_utils_source)
        self.assertIsNone(re.search(r"(?m)^WEEKDAY_ALIASES\s*=", scheduler_source))
        self.assertIsNone(re.search(r"(?m)^WEEKDAY_ALIASES\s*=", generator_source))
        self.assertIsNone(re.search(r"(?m)^WEEKDAY_LABELS\s*=", schedule_display_source))
        self.assertNotIn('["周一", "周二", "周三", "周四", "周五", "周六", "周日"]', business_import_source)

    def test_time_slot_generator_reuses_shared_date_normalization(self) -> None:
        generator_source = (ROOT / "generate_time_slots.py").read_text(encoding="utf-8")

        self.assertIn("from scripts.field_utils import normalize_iso_date_text", generator_source)
        self.assertNotIn("datetime.strptime", generator_source)

    def test_window_normalization_lives_in_shared_window_utils(self) -> None:
        scheduler_source = (ROOT / "scheduler.py").read_text(encoding="utf-8")
        class_windows_source = (ROOT / "scripts" / "schedule_class_windows.py").read_text(encoding="utf-8")
        window_utils_source = (ROOT / "scripts" / "window_utils.py").read_text(encoding="utf-8")

        self.assertIn("from scripts.window_utils import", scheduler_source)
        self.assertIn("from scripts.window_utils import", class_windows_source)
        self.assertIn("SEASON_WINDOW_ID_TO_NAME", window_utils_source)
        self.assertIn("YEAR_SEASON_WINDOW_PATTERN", window_utils_source)
        self.assertIsNone(re.search(r"(?m)^SEASON_WINDOW_ID_TO_NAME\s*=", scheduler_source))
        self.assertIsNone(re.search(r"(?m)^SEASON_WINDOW_NAME_TO_ID\s*=", scheduler_source))
        self.assertIsNone(re.search(r"(?m)^def expanded_window_tokens\(", scheduler_source))
        self.assertNotIn("season_tokens = {", class_windows_source)

    def test_cli_scripts_import_project_modules_with_bootstrap(self) -> None:
        project_import = re.compile(
            r"(?m)^\s*("
            r"from\s+scripts\.|import\s+scripts\."
            r"|import\s+data_admin_server\b|import\s+data_admin_server\s+as\b"
            r"|from\s+run_scheduling_pipeline\b|import\s+business_class_import\b"
            r"|import\s+business_class_import\s+as\b|import\s+scheduler\b|from\s+scheduler\b"
            r")"
        )
        offenders = []
        for path in sorted((ROOT / "scripts").glob("*.py")):
            source = path.read_text(encoding="utf-8")
            if 'if __name__ == "__main__"' not in source and "if __name__ == '__main__'" not in source:
                continue
            if not project_import.search(source):
                continue
            has_bootstrap = (
                "ROOT = Path(__file__).resolve().parents[1]" in source
                and "sys.path.insert(0, str(ROOT))" in source
            )
            if not has_bootstrap:
                offenders.append(str(path.relative_to(ROOT)))

        self.assertEqual([], offenders)

    def test_release_path_modules_use_csv_utils_for_csv_io(self) -> None:
        modules = [
            ROOT / "business_class_import.py",
            ROOT / "formal_template.py",
            ROOT / "scheduler.py",
            ROOT / "run_scheduling_pipeline.py",
            ROOT / "scripts" / "analyze_erp_import_failures.py",
            ROOT / "scripts" / "build_erp_retry_import.py",
            ROOT / "scripts" / "build_erp_lesson_id_map.py",
            ROOT / "scripts" / "build_erp_reverse_import_from_result.py",
            ROOT / "scripts" / "build_failed_erp_class_schedule_review.py",
            ROOT / "scripts" / "build_camp_maintenance_schedule.py",
            ROOT / "scripts" / "build_cloudflare_publish_bundle.py",
            ROOT / "scripts" / "compare_history_remaining_changes.py",
            ROOT / "scripts" / "export_erp_adjusted_lesson_import.py",
            ROOT / "scripts" / "export_erp_lesson_import.py",
            ROOT / "scripts" / "fix_teacher_employee_ids.py",
            ROOT / "scripts" / "repair_2726_summer_week_balance.py",
            ROOT / "scripts" / "repair_2757_halfday_blocks.py",
            ROOT / "scripts" / "repair_2792_extreme_weeks.py",
            ROOT / "scripts" / "repair_class_conflicts_and_ep_same_day.py",
            ROOT / "scripts" / "repair_public_coverage_gaps.py",
            ROOT / "scripts" / "repair_teacher_travel_swaps.py",
            ROOT / "scripts" / "repair_wyqc_foundation_deadlines.py",
            ROOT / "scripts" / "repair_wyqc_foundation_gaps.py",
            ROOT / "scripts" / "repair_wyqc_summer_week_balance.py",
            ROOT / "scripts" / "schedule_batch.py",
            ROOT / "scripts" / "schedule_data.py",
            ROOT / "scripts" / "schedule_class_windows.py",
            ROOT / "scripts" / "schedule_conflicts.py",
            ROOT / "scripts" / "schedule_outputs.py",
            ROOT / "scripts" / "schedule_scope.py",
            ROOT / "scripts" / "sync_erp_standard_products.py",
            ROOT / "scripts" / "sync_template_workbook_to_admin_data.py",
        ]
        offenders = []
        for path in modules:
            source = path.read_text(encoding="utf-8")
            imports_stdlib_csv = bool(re.search(r"(?m)^\s*(import\s+csv\b|from\s+csv\s+import\b)", source))
            calls_stdlib_csv = bool(re.search(r"(?<![A-Za-z0-9_])csv\.", source))
            if imports_stdlib_csv or calls_stdlib_csv or "scripts.csv_utils" not in source:
                offenders.append(str(path.relative_to(ROOT)))

        self.assertEqual([], offenders)

    def test_erp_excel_modules_use_shared_excel_text_normalization(self) -> None:
        modules = [
            ROOT / "scripts" / "analyze_erp_import_failures.py",
            ROOT / "scripts" / "build_erp_lesson_id_map.py",
            ROOT / "scripts" / "build_erp_reverse_import_from_result.py",
            ROOT / "scripts" / "build_erp_retry_import.py",
            ROOT / "scripts" / "build_failed_erp_class_schedule_review.py",
            ROOT / "scripts" / "export_erp_lesson_import.py",
        ]
        offenders = []
        for path in modules:
            source = path.read_text(encoding="utf-8")
            if "normalize_excel_text as clean" not in source:
                offenders.append(f"{path.relative_to(ROOT)} does not import normalize_excel_text as clean")
            if re.search(r"(?m)^def clean\(", source):
                offenders.append(f"{path.relative_to(ROOT)} defines local clean")
            if "ROOT = Path(__file__).resolve().parents[1]" not in source or "sys.path.insert(0, str(ROOT))" not in source:
                offenders.append(f"{path.relative_to(ROOT)} is missing direct-script import bootstrap")

        self.assertEqual([], offenders)

    def test_schedule_display_owns_shared_calendar_helpers_for_repair_outputs(self) -> None:
        modules = [
            ROOT / "scripts" / "build_failed_erp_class_schedule_review.py",
            ROOT / "scripts" / "repair_2726_summer_week_balance.py",
            ROOT / "scripts" / "repair_public_coverage_gaps.py",
            ROOT / "scripts" / "repair_wyqc_foundation_deadlines.py",
            ROOT / "scripts" / "repair_wyqc_foundation_gaps.py",
            ROOT / "scripts" / "repair_wyqc_summer_week_balance.py",
            ROOT / "scripts" / "sync_erp_adjusted_schedule.py",
        ]
        offenders = []
        for path in modules:
            source = path.read_text(encoding="utf-8")
            if "from scripts.schedule_display import" not in source:
                offenders.append(f"{path.relative_to(ROOT)} does not import schedule_display")
            if re.search(r"(?m)^def (weekday_label|week_start)\(", source):
                offenders.append(f"{path.relative_to(ROOT)} defines local calendar helper")
            if re.search(r"(?m)^WEEKDAYS?(?:_LABELS)?\\s*=", source):
                offenders.append(f"{path.relative_to(ROOT)} defines local weekday labels")

        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
