from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
PERSONAL_PATH_MARKERS = ("/Users/" + "plzhz", "Down" + "loads" + "/")
TEXT_RELEASE_SUFFIXES = {".csv", ".html", ".js", ".json", ".md", ".py", ".sh", ".txt", ".yml"}
TEXT_RELEASE_NAMES = {".env.example", ".gitignore"}
RELEASE_TEXT_PATHS = [
    ".env.example",
    ".gitignore",
    "LAUNCH_CHECKLIST.md",
    "PUBLIC_SCHEDULE_DEPLOY.md",
    "README.md",
    "SCHEDULING_RULES_REVIEW_20260524.md",
    ".github",
    "cloudflare_schedule_publish",
    "docs",
    "examples",
    "scripts",
    "share",
    "tests",
    "web_admin",
    "*.py",
]
RELEASE_DOC_PATHS = ["README.md", "PUBLIC_SCHEDULE_DEPLOY.md", "LAUNCH_CHECKLIST.md", "docs", "share"]


def git_tracked_files(pathspecs: Iterable[str]) -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "-c", "core.quotePath=false", "ls-files", "-z", "--", *pathspecs],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return []
    return sorted({ROOT / item for item in result.stdout.split("\0") if item})


def is_release_text_file(path: Path) -> bool:
    return path.is_file() and (path.name in TEXT_RELEASE_NAMES or path.suffix in TEXT_RELEASE_SUFFIXES)


def filesystem_release_text_files() -> list[Path]:
    paths: list[Path] = []
    top_level_files = [
        ROOT / ".env.example",
        ROOT / ".gitignore",
        ROOT / "LAUNCH_CHECKLIST.md",
        ROOT / "PUBLIC_SCHEDULE_DEPLOY.md",
        ROOT / "README.md",
        ROOT / "SCHEDULING_RULES_REVIEW_20260524.md",
    ]
    for path in top_level_files:
        if is_release_text_file(path):
            paths.append(path)
    for directory in (".github", "cloudflare_schedule_publish", "docs", "examples", "scripts", "share", "tests", "web_admin"):
        for path in sorted((ROOT / directory).rglob("*")):
            if is_release_text_file(path):
                paths.append(path)
    for path in sorted(ROOT.glob("*.py")):
        if is_release_text_file(path):
            paths.append(path)
    return sorted(paths)


def release_text_files() -> Iterable[Path]:
    tracked_paths = git_tracked_files(RELEASE_TEXT_PATHS)
    paths = [path for path in tracked_paths if is_release_text_file(path)] if tracked_paths else filesystem_release_text_files()
    for path in paths:
        yield path


def release_script_python_files() -> list[Path]:
    tracked_paths = git_tracked_files(["scripts/*.py"])
    if tracked_paths:
        return [path for path in tracked_paths if path.is_file() and path.suffix == ".py"]
    return sorted(path for path in (ROOT / "scripts").glob("*.py") if path.is_file())


def release_docs_text_files() -> list[Path]:
    tracked_paths = git_tracked_files(RELEASE_DOC_PATHS)
    if not tracked_paths:
        paths = [ROOT / "README.md", ROOT / "PUBLIC_SCHEDULE_DEPLOY.md", ROOT / "LAUNCH_CHECKLIST.md"]
        paths.extend(sorted((ROOT / "docs").rglob("*.md")))
        paths.extend(sorted((ROOT / "share").rglob("*.html")))
        return [path for path in paths if path.is_file()]

    docs: list[Path] = []
    for path in tracked_paths:
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT).as_posix()
        if relative in {"README.md", "PUBLIC_SCHEDULE_DEPLOY.md", "LAUNCH_CHECKLIST.md"}:
            docs.append(path)
        elif relative.startswith("docs/") and path.suffix == ".md":
            docs.append(path)
        elif relative.startswith("share/") and path.suffix == ".html":
            docs.append(path)
    return sorted(docs)


class ReleaseStaticTest(unittest.TestCase):
    def test_scripts_do_not_ship_personal_default_paths(self) -> None:
        offenders = []
        for path in release_script_python_files():
            source = path.read_text(encoding="utf-8")
            if any(marker in source for marker in PERSONAL_PATH_MARKERS):
                offenders.append(str(path.relative_to(ROOT)))

        self.assertEqual([], offenders)

    def test_release_docs_do_not_ship_personal_paths(self) -> None:
        offenders = []
        for path in release_docs_text_files():
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
        self.assertIn("release_script_files()", script)
        self.assertIn('git ls-files "scripts/*.${suffix}"', script)
        self.assertIn('find scripts -name "*.${suffix}"', script)
        self.assertIn("-m py_compile \"$script_path\"", script)
        self.assertIn("verify_cli_help()", script)
        self.assertIn('verify_cli_help "$script_path"', script)
        self.assertIn('--help >/dev/null', script)
        self.assertIn('scheduler.py \\', script)
        self.assertIn('run_scheduling_pipeline.py \\', script)
        self.assertIn('data_admin_server.py \\', script)
        self.assertIn('grep -q "argparse" "$script_path"', script)
        self.assertIn('grep -q "if __name__" "$script_path"', script)

    def test_release_static_scans_tracked_files_in_git_worktrees(self) -> None:
        release_paths = {path.relative_to(ROOT).as_posix() for path in release_text_files()}
        script_paths = {path.relative_to(ROOT).as_posix() for path in release_script_python_files()}

        self.assertNotIn("docs/generated/ai-assisted-scheduling-system-user-guide-compact.md", release_paths)
        self.assertNotIn("scripts/build_ai_user_guide_docx.py", release_paths)
        self.assertNotIn("scripts/build_ai_user_guide_docx.py", script_paths)

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
        product_catalog_source = (ROOT / "scripts" / "product_catalog.py").read_text(encoding="utf-8")
        web_admin_source = (ROOT / "web_admin" / "app.js").read_text(encoding="utf-8")

        self.assertIn("from scripts.product_catalog import", admin_source)
        self.assertIn("from scripts.product_catalog import", pipeline_source)
        self.assertIn("from scripts.product_catalog import", formal_template_source)
        self.assertIn("PRODUCT_PROJECT_OPTIONS", product_catalog_source)
        self.assertIn("PRODUCT_LINE_OPTIONS", product_catalog_source)
        self.assertIn("PRODUCT_PROJECT_OPTIONS", admin_source)
        self.assertIn("PRODUCT_LINE_OPTIONS", admin_source)
        self.assertNotIn("import data_admin_server", formal_template_source)
        self.assertIsNone(re.search(r"(?m)^def product_catalog\(", admin_source))
        self.assertIsNone(re.search(r"(?m)^def infer_project\(", admin_source))
        self.assertIsNone(re.search(r"(?m)^def product_stage_order\(", admin_source))
        self.assertNotIn('["考研", "专升本", "四六级"]', admin_source)
        self.assertNotIn('["考研复试", "考研集训营", "考研无忧", "考研个性化", "考研其他", "专升本", "四六级"]', admin_source)
        self.assertNotIn('["考研", "专升本", "四六级"]', web_admin_source)
        self.assertNotIn('["考研复试", "考研集训营", "考研无忧", "考研个性化", "考研其他", "专升本", "四六级"]', web_admin_source)
        self.assertNotIn("data_admin_server.product_catalog", pipeline_source)

    def test_teacher_resource_options_live_outside_admin_and_frontend(self) -> None:
        admin_source = (ROOT / "data_admin_server.py").read_text(encoding="utf-8")
        resource_catalog_source = (ROOT / "scripts" / "resource_catalog.py").read_text(encoding="utf-8")
        web_admin_source = (ROOT / "web_admin" / "app.js").read_text(encoding="utf-8")

        self.assertIn("from scripts.resource_catalog import", admin_source)
        self.assertIn("TEACHER_EMPLOYMENT_TYPE_OPTIONS", resource_catalog_source)
        self.assertIn("TEACHER_EMPLOYMENT_TYPE_OPTIONS", admin_source)
        self.assertIn('"teacher_employment_types": list(TEACHER_EMPLOYMENT_TYPE_OPTIONS)', admin_source)
        self.assertIn('lookupOptions("teacher_employment_types")', web_admin_source)
        self.assertNotIn('["男", "女", "其他"]', admin_source)
        self.assertNotIn('["管理者", "教师"]', admin_source)
        self.assertNotIn('{"全职", "兼职", "外聘", "内部"}', admin_source)
        self.assertNotIn('["全职", "兼职", "外聘", "内部"]', web_admin_source)
        self.assertNotIn('["已签约", "未签约", "待续签", "已终止"]', web_admin_source)
        self.assertNotIn('["在职", "离职", "停用", "待入职"]', web_admin_source)

    def test_field_normalization_lives_in_shared_field_utils(self) -> None:
        admin_source = (ROOT / "data_admin_server.py").read_text(encoding="utf-8")
        product_catalog_source = (ROOT / "scripts" / "product_catalog.py").read_text(encoding="utf-8")
        business_import_source = (ROOT / "business_class_import.py").read_text(encoding="utf-8")
        pipeline_source = (ROOT / "run_scheduling_pipeline.py").read_text(encoding="utf-8")
        scheduler_source = (ROOT / "scheduler.py").read_text(encoding="utf-8")
        schedule_data_source = (ROOT / "scripts" / "schedule_data.py").read_text(encoding="utf-8")
        schedule_outputs_source = (ROOT / "scripts" / "schedule_outputs.py").read_text(encoding="utf-8")
        schedule_display_source = (ROOT / "scripts" / "schedule_display.py").read_text(encoding="utf-8")
        schedule_conflicts_source = (ROOT / "scripts" / "schedule_conflicts.py").read_text(encoding="utf-8")
        schedule_scope_source = (ROOT / "scripts" / "schedule_scope.py").read_text(encoding="utf-8")
        coverage_source = (ROOT / "scripts" / "audit_schedule_coverage.py").read_text(encoding="utf-8")
        class_windows_source = (ROOT / "scripts" / "schedule_class_windows.py").read_text(encoding="utf-8")
        erp_lesson_map_source = (ROOT / "scripts" / "build_erp_lesson_id_map.py").read_text(encoding="utf-8")
        erp_export_source = (ROOT / "scripts" / "export_erp_lesson_import.py").read_text(encoding="utf-8")
        erp_adjusted_sync_source = (ROOT / "scripts" / "sync_erp_adjusted_schedule.py").read_text(encoding="utf-8")
        camp_maintenance_source = (ROOT / "scripts" / "build_camp_maintenance_schedule.py").read_text(encoding="utf-8")
        field_utils_source = (ROOT / "scripts" / "field_utils.py").read_text(encoding="utf-8")

        self.assertIn("def row_value", field_utils_source)
        self.assertIn("def normalize_excel_cell_text", field_utils_source)
        self.assertIn("from scripts.field_utils import", admin_source)
        self.assertIn("row_value", admin_source)
        self.assertIn("from scripts.field_utils import", product_catalog_source)
        self.assertIn("from scripts.field_utils import", business_import_source)
        self.assertIn("from scripts.field_utils import", pipeline_source)
        self.assertIn("from scripts.field_utils import", scheduler_source)
        self.assertIn("row_value", schedule_data_source)
        self.assertIn("row_value", schedule_scope_source)
        self.assertIn("normalize_text", class_windows_source)
        self.assertIn("from scripts.field_utils import", erp_lesson_map_source)
        self.assertIn("from scripts.field_utils import", erp_adjusted_sync_source)
        self.assertIn("normalize_blank_marker", camp_maintenance_source)
        self.assertIn("normalize_blank_marker", admin_source)
        self.assertIn("blank_marker_to_empty", scheduler_source)
        self.assertIn("is_blank_marker", business_import_source)
        self.assertIn("normalize_excel_cell_text", pipeline_source)
        self.assertIn("parse_time_minutes", schedule_display_source)
        self.assertIn("parse_time_minutes", schedule_conflicts_source)
        self.assertNotIn('value.split(":", 1)', schedule_display_source)
        self.assertNotIn('value.split(":", 1)', schedule_conflicts_source)
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
        self.assertIsNone(re.search(r"(?m)^def row_value\(", business_import_source))
        self.assertIsNone(re.search(r"(?m)^def row_value\(", camp_maintenance_source))
        self.assertNotIn("data_admin_server.normalize_int", business_import_source)
        self.assertIn("parse_date_value", business_import_source)
        self.assertIn("parse_time_minutes", business_import_source)
        self.assertNotIn('cls.get("stages") or cls.get("selected_stages")', admin_source)
        self.assertNotIn('"stages": cls["stages"]', admin_source)
        self.assertNotIn('"stages": selected_stages', admin_source)
        self.assertNotIn('"stages": split_id_list(cls.get("selected_stages")', admin_source)
        self.assertNotIn('"quarter": course.get("window_name")', admin_source)
        self.assertIn('"window_name": course.get("window_name")', admin_source)
        self.assertIn('"window_names": sorted(window_names)', admin_source)
        self.assertNotIn('"quarters": sorted(', admin_source)
        self.assertNotIn('"quarter": requirement.get("quarter"', admin_source)
        self.assertIn('"window_name": requirement.get("window_name")', admin_source)
        self.assertNotIn('"quarter",\n    "stage",', Path("scripts/table_schema.py").read_text(encoding="utf-8"))
        self.assertIn('"window_name",\n    "stage",', Path("scripts/table_schema.py").read_text(encoding="utf-8"))
        self.assertNotIn('"quarter",\n            "stage",', business_import_source)
        self.assertIn('"window_name",\n            "stage",', business_import_source)
        self.assertNotIn('"quarter",\n    "stage",', scheduler_source)
        self.assertIn('"window_name",\n    "stage",', scheduler_source)
        self.assertNotIn('"quarter": assignment.task.quarter', scheduler_source)
        self.assertIn('"window_name": assignment.task.quarter', scheduler_source)
        self.assertNotIn('"quarter",\n    "stage",', schedule_outputs_source)
        self.assertIn('"window_name",\n    "stage",', schedule_outputs_source)
        self.assertNotIn('"quarter": assignment.task.quarter', schedule_outputs_source)
        self.assertIn('"window_name": assignment.task.quarter', schedule_outputs_source)
        self.assertNotIn('"quarter",\n        "stage",', coverage_source)
        self.assertIn('"window_name",\n        "stage",', coverage_source)
        self.assertIn('"window_name",\n    "stage",', erp_adjusted_sync_source)
        self.assertNotIn('"quarter",\n    "stage",', erp_adjusted_sync_source)
        self.assertIn('row_value(row, "window_name", "quarter")', erp_export_source)
        self.assertNotIn('clean(row.get("quarter"))', erp_export_source)
        self.assertNotIn('"is_schedule_locked": lock_value', schedule_data_source)
        self.assertNotIn('is_locked=clean(row.get("is_schedule_locked"))', coverage_source)
        self.assertIn('"selected_stages": selected_stages', schedule_data_source)
        self.assertIn('raw_class.get("selected_stages")', scheduler_source)
        self.assertNotIn('"stages": row.get("stages"', schedule_data_source)
        self.assertNotIn("datetime.strptime(candidate, fmt)", business_import_source)
        self.assertNotIn("data_admin_server.normalize_text", pipeline_source)
        self.assertNotIn("isinstance(value, datetime)", pipeline_source)
        self.assertNotIn("set(number_format) == {\"0\"}", pipeline_source)
        self.assertIsNone(re.search(r"str\([^\n]* or \"\"\)", scheduler_source))
        self.assertIsNone(re.search(r"str\([^\n]* or \"\"\)", pipeline_source))
        self.assertIsNone(re.search(r'\(row\.get\([^)]*\) or ""\)\.strip\(\)', class_windows_source))
        self.assertIsNone(re.search(r'normalize_date\(row\.get\([^)]*\) or ""\)', class_windows_source))
        self.assertIsNone(re.search(r'is_enabled\(row\.get\([^)]*\) or ""\)', class_windows_source))
        self.assertIsNone(re.search(r'normalize_schedule_period\(row\.get\([^)]*\) or ""', class_windows_source))
        self.assertNotIn("str(value or \"\").strip()", camp_maintenance_source)

    def test_repair_clean_helpers_reuse_shared_field_utils(self) -> None:
        modules = [
            ROOT / "scripts" / "repair_2726_summer_week_balance.py",
            ROOT / "scripts" / "repair_2757_halfday_blocks.py",
            ROOT / "scripts" / "repair_public_coverage_gaps.py",
            ROOT / "scripts" / "repair_wyqc_foundation_deadlines.py",
            ROOT / "scripts" / "repair_wyqc_foundation_gaps.py",
            ROOT / "scripts" / "repair_wyqc_summer_week_balance.py",
            ROOT / "scripts" / "schedule_conflicts.py",
        ]
        offenders = []
        for path in modules:
            source = path.read_text(encoding="utf-8")
            if "from scripts.field_utils import" not in source:
                offenders.append(f"{path.relative_to(ROOT)} does not import field_utils")
            if re.search(r"(?m)^def clean\(", source):
                offenders.append(f"{path.relative_to(ROOT)} defines local clean")
            if 'str(value or "").strip()' in source:
                offenders.append(f"{path.relative_to(ROOT)} clears falsey values with value-or-empty")
            if path.name in {"repair_2757_halfday_blocks.py", "repair_wyqc_foundation_gaps.py"} and 'clean(row.get("quarter"))' in source:
                offenders.append(f"{path.relative_to(ROOT)} reads legacy quarter without window_name fallback")
            if path.name == "repair_public_coverage_gaps.py" and '"quarter": key[2]' in source:
                offenders.append(f"{path.relative_to(ROOT)} emits legacy quarter from new gap tasks")

        self.assertEqual([], offenders)

    def test_boolean_parsing_lives_in_shared_field_utils(self) -> None:
        admin_source = (ROOT / "data_admin_server.py").read_text(encoding="utf-8")
        field_utils_source = (ROOT / "scripts" / "field_utils.py").read_text(encoding="utf-8")
        publish_server_source = (ROOT / "schedule_publish_server.py").read_text(encoding="utf-8")
        schedule_scope_source = (ROOT / "scripts" / "schedule_scope.py").read_text(encoding="utf-8")
        coverage_source = (ROOT / "scripts" / "audit_schedule_coverage.py").read_text(encoding="utf-8")
        cloudflare_source = (ROOT / "scripts" / "build_cloudflare_publish_bundle.py").read_text(encoding="utf-8")
        camp_maintenance_source = (ROOT / "scripts" / "build_camp_maintenance_schedule.py").read_text(encoding="utf-8")

        self.assertIn("TRUE_VALUES", field_utils_source)
        self.assertIn('"on"', field_utils_source)
        self.assertIn("is_manual_schedule_locked", admin_source)
        self.assertNotIn('cls.get("is_schedule_locked")', admin_source)
        self.assertIn("parse_bool", publish_server_source)
        self.assertIn("parse_bool_default", schedule_scope_source)
        self.assertNotIn('(row.get("is_schedule_locked") or "").strip() in', schedule_scope_source)
        for source in (coverage_source, cloudflare_source, camp_maintenance_source):
            self.assertIn("parse_bool", source)
            self.assertNotIn('.lower() in {"是", "1", "true", "yes", "y"}', source)
            self.assertNotIn('.lower() in {"1", "true", "yes", "是"}', source)
        self.assertIn("parse_enabled", camp_maintenance_source)
        self.assertIn("class_is_locked", camp_maintenance_source)
        self.assertNotIn("truthy_text", camp_maintenance_source)
        self.assertNotIn('clean(row.get("is_schedule_locked")) in', camp_maintenance_source)
        self.assertNotIn('meta.get("is_schedule_locked") in {"是"', camp_maintenance_source)
        self.assertNotIn('meta.get("is_schedule_locked") == "是"', camp_maintenance_source)
        self.assertNotIn('.lower() not in {"0", "false", "no", "否"}', camp_maintenance_source)

    def test_list_value_splitting_lives_in_shared_field_utils(self) -> None:
        field_utils_source = (ROOT / "scripts" / "field_utils.py").read_text(encoding="utf-8")
        admin_source = (ROOT / "data_admin_server.py").read_text(encoding="utf-8")
        scheduler_source = (ROOT / "scheduler.py").read_text(encoding="utf-8")
        pipeline_source = (ROOT / "run_scheduling_pipeline.py").read_text(encoding="utf-8")
        schedule_batch_source = (ROOT / "scripts" / "schedule_batch.py").read_text(encoding="utf-8")
        schedule_scope_source = (ROOT / "scripts" / "schedule_scope.py").read_text(encoding="utf-8")
        class_windows_source = (ROOT / "scripts" / "schedule_class_windows.py").read_text(encoding="utf-8")
        weekday_utils_source = (ROOT / "scripts" / "weekday_utils.py").read_text(encoding="utf-8")
        window_utils_source = (ROOT / "scripts" / "window_utils.py").read_text(encoding="utf-8")
        template_sync_source = (ROOT / "scripts" / "sync_template_workbook_to_admin_data.py").read_text(encoding="utf-8")
        erp_export_source = (ROOT / "scripts" / "export_erp_lesson_import.py").read_text(encoding="utf-8")
        erp_lesson_map_source = (ROOT / "scripts" / "build_erp_lesson_id_map.py").read_text(encoding="utf-8")
        camp_maintenance_source = (ROOT / "scripts" / "build_camp_maintenance_schedule.py").read_text(encoding="utf-8")
        business_import_source = (ROOT / "business_class_import.py").read_text(encoding="utf-8")
        quality_repair_source = (ROOT / "scripts" / "repair_schedule_quality_hotspots.py").read_text(encoding="utf-8")
        teacher_travel_repair_source = (ROOT / "scripts" / "repair_teacher_travel_swaps.py").read_text(encoding="utf-8")
        wyqc_summer_repair_source = (ROOT / "scripts" / "repair_wyqc_summer_week_balance.py").read_text(encoding="utf-8")

        self.assertIn("LIST_VALUE_SEPARATOR_RE", field_utils_source)
        self.assertIn("def split_delimited_values", field_utils_source)
        for source in (
            admin_source,
            scheduler_source,
            pipeline_source,
            schedule_batch_source,
            class_windows_source,
            weekday_utils_source,
            window_utils_source,
            template_sync_source,
            erp_export_source,
            erp_lesson_map_source,
            camp_maintenance_source,
            quality_repair_source,
            wyqc_summer_repair_source,
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
        self.assertNotIn('re.split(r"[,，;；、|]+"', business_import_source)
        self.assertNotIn('re.split(r"[|,，;；/、]+"', scheduler_source)
        self.assertNotIn('re.split(r"[/|,，;；、\\s]+"', scheduler_source)
        self.assertNotIn('re.split(r"[,，|;\\s]+"', admin_source)
        self.assertNotIn('re.split(r"[、，,；;]+"', pipeline_source)
        self.assertNotIn('re.split(r"[,，|;\\s]+"', camp_maintenance_source)
        self.assertNotIn('value.split(",")', quality_repair_source)
        self.assertNotIn('value.split(",")', teacher_travel_repair_source)
        self.assertNotIn('value.split(",")', wyqc_summer_repair_source)
        self.assertIsNone(re.search(r"(?m)^def parse_name_set\(", teacher_travel_repair_source))

    def test_erp_date_time_normalization_lives_in_shared_field_utils(self) -> None:
        field_utils_source = (ROOT / "scripts" / "field_utils.py").read_text(encoding="utf-8")
        erp_export_source = (ROOT / "scripts" / "export_erp_lesson_import.py").read_text(encoding="utf-8")
        erp_lesson_map_source = (ROOT / "scripts" / "build_erp_lesson_id_map.py").read_text(encoding="utf-8")
        erp_adjusted_export_source = (ROOT / "scripts" / "export_erp_adjusted_lesson_import.py").read_text(encoding="utf-8")
        failed_review_source = (ROOT / "scripts" / "build_failed_erp_class_schedule_review.py").read_text(encoding="utf-8")
        erp_adjusted_sync_source = (ROOT / "scripts" / "sync_erp_adjusted_schedule.py").read_text(encoding="utf-8")
        template_sync_source = (ROOT / "scripts" / "sync_template_workbook_to_admin_data.py").read_text(encoding="utf-8")

        self.assertIn("def display_date_text", field_utils_source)
        for source in (
            erp_export_source,
            erp_lesson_map_source,
            erp_adjusted_export_source,
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
        self.assertIn("split_time_range_text", erp_adjusted_export_source)
        self.assertIn("split_time_range_text", erp_adjusted_sync_source)

        for source in (erp_export_source, erp_lesson_map_source, erp_adjusted_export_source, failed_review_source, erp_adjusted_sync_source):
            self.assertIsNone(re.search(r"(?m)^def normalize_date\(", source))
            self.assertNotIn("datetime.strptime", source)
        self.assertIsNone(re.search(r"(?m)^def normalize_date\(", template_sync_source))
        self.assertIsNone(re.search(r"(?m)^def normalize_time\(", erp_lesson_map_source))
        self.assertNotIn("normalize_time,", erp_adjusted_export_source)
        self.assertIsNone(re.search(r"(?m)^def normalize_time\(", template_sync_source))
        self.assertIsNone(re.search(r"(?m)^def display_date\(", erp_export_source))
        self.assertIsNone(re.search(r"(?m)^def display_date\(", failed_review_source))

    def test_lesson_datetime_parsing_lives_in_shared_field_utils(self) -> None:
        field_utils_source = (ROOT / "scripts" / "field_utils.py").read_text(encoding="utf-8")
        import_locked_source = (ROOT / "scripts" / "import_locked_professional_schedules.py").read_text(encoding="utf-8")
        camp_maintenance_source = (ROOT / "scripts" / "build_camp_maintenance_schedule.py").read_text(encoding="utf-8")
        wyqc_foundation_gap_source = (ROOT / "scripts" / "repair_wyqc_foundation_gaps.py").read_text(encoding="utf-8")

        self.assertIn("def parse_datetime_value", field_utils_source)
        self.assertIn("parse_datetime_value", import_locked_source)
        self.assertIn("parse_datetime_value", camp_maintenance_source)
        self.assertIn("is_manual_schedule_locked", import_locked_source)
        self.assertNotIn('cls["is_schedule_locked"] =', import_locked_source)
        self.assertIn('"window_name": window_name', import_locked_source)
        self.assertNotIn('"quarter": quarter', import_locked_source)
        self.assertNotIn('"quarter": normalize_text', import_locked_source)
        self.assertNotIn("def class_is_movable_public", wyqc_foundation_gap_source)
        self.assertNotIn("datetime.strptime", import_locked_source)
        self.assertNotIn("datetime.strptime", camp_maintenance_source)

    def test_period_normalization_lives_in_shared_period_utils(self) -> None:
        admin_source = (ROOT / "data_admin_server.py").read_text(encoding="utf-8")
        web_admin_source = (ROOT / "web_admin" / "app.js").read_text(encoding="utf-8")
        scheduler_source = (ROOT / "scheduler.py").read_text(encoding="utf-8")
        business_import_source = (ROOT / "business_class_import.py").read_text(encoding="utf-8")
        class_windows_source = (ROOT / "scripts" / "schedule_class_windows.py").read_text(encoding="utf-8")
        erp_adjusted_sync_source = (ROOT / "scripts" / "sync_erp_adjusted_schedule.py").read_text(encoding="utf-8")
        audit_quality_source = (ROOT / "scripts" / "audit_schedule_quality.py").read_text(encoding="utf-8")
        public_gap_repair_source = (ROOT / "scripts" / "repair_public_coverage_gaps.py").read_text(encoding="utf-8")
        halfday_repair_source = (ROOT / "scripts" / "repair_2757_halfday_blocks.py").read_text(encoding="utf-8")
        quality_hotspot_repair_source = (ROOT / "scripts" / "repair_schedule_quality_hotspots.py").read_text(encoding="utf-8")
        schedule_display_source = (ROOT / "scripts" / "schedule_display.py").read_text(encoding="utf-8")
        schedule_outputs_source = (ROOT / "scripts" / "schedule_outputs.py").read_text(encoding="utf-8")
        extreme_weeks_repair_source = (ROOT / "scripts" / "repair_2792_extreme_weeks.py").read_text(encoding="utf-8")
        period_utils_source = (ROOT / "scripts" / "period_utils.py").read_text(encoding="utf-8")

        self.assertIn("from scripts.period_utils import", scheduler_source)
        self.assertIn("from scripts.period_utils import", business_import_source)
        self.assertIn("from scripts.period_utils import", class_windows_source)
        self.assertIn("from scripts.period_utils import", erp_adjusted_sync_source)
        self.assertIn("from scripts.period_utils import", audit_quality_source)
        self.assertIn("from scripts.period_utils import", public_gap_repair_source)
        self.assertIn("from scripts.period_utils import", halfday_repair_source)
        self.assertIn("from scripts.period_utils import", quality_hotspot_repair_source)
        self.assertIn("from scripts.period_utils import PERIOD_LABELS", schedule_display_source)
        self.assertIn("from scripts.period_utils import PERIOD_LABELS", schedule_outputs_source)
        self.assertIn("PERIOD_OPTIONS", period_utils_source)
        self.assertIn("VALID_PERIODS", period_utils_source)
        self.assertIn("PERIOD_ORDER", period_utils_source)
        self.assertIn("PERIOD_LABELS", period_utils_source)
        self.assertIn("from scripts.period_utils import PERIOD_LABELS, PERIOD_OPTIONS", admin_source)
        self.assertIn('"period_options": list(PERIOD_OPTIONS)', admin_source)
        self.assertIn('"period_labels": dict(PERIOD_LABELS)', admin_source)
        self.assertIn('lookupOptions("period_options")', web_admin_source)
        self.assertNotIn('["AM", "PM", "EVENING"]', web_admin_source)
        self.assertIsNone(re.search(r"(?m)^VALID_PERIODS\s*=", scheduler_source))
        for source in (
            scheduler_source,
            erp_adjusted_sync_source,
            audit_quality_source,
            public_gap_repair_source,
            halfday_repair_source,
            quality_hotspot_repair_source,
        ):
            self.assertIsNone(re.search(r"(?m)^PERIOD_ORDER\s*=", source))
        for source in (schedule_display_source, schedule_outputs_source, extreme_weeks_repair_source):
            self.assertIsNone(re.search(r"(?m)^PERIOD_LABELS\s*=", source))
        self.assertIsNone(re.search(r"(?m)^def period_sort_value\(", scheduler_source))
        self.assertIsNone(re.search(r"(?m)^def normalize_period\(", class_windows_source))
        self.assertIsNone(re.search(r"(?m)^\s*aliases\s*=\s*\{", business_import_source))

    def test_public_subject_sets_live_in_shared_subject_utils(self) -> None:
        admin_source = (ROOT / "data_admin_server.py").read_text(encoding="utf-8")
        scheduler_source = (ROOT / "scheduler.py").read_text(encoding="utf-8")
        business_import_source = (ROOT / "business_class_import.py").read_text(encoding="utf-8")
        erp_export_source = (ROOT / "scripts" / "export_erp_lesson_import.py").read_text(encoding="utf-8")
        erp_lesson_map_source = (ROOT / "scripts" / "build_erp_lesson_id_map.py").read_text(encoding="utf-8")
        schedule_data_source = (ROOT / "scripts" / "schedule_data.py").read_text(encoding="utf-8")
        schedule_batch_source = (ROOT / "scripts" / "schedule_batch.py").read_text(encoding="utf-8")
        schedule_scope_source = (ROOT / "scripts" / "schedule_scope.py").read_text(encoding="utf-8")
        schedule_week_balance_source = (ROOT / "scripts" / "schedule_week_balance.py").read_text(encoding="utf-8")
        camp_maintenance_source = (ROOT / "scripts" / "build_camp_maintenance_schedule.py").read_text(encoding="utf-8")
        audit_quality_source = (ROOT / "scripts" / "audit_schedule_quality.py").read_text(encoding="utf-8")
        quality_hotspot_repair_source = (ROOT / "scripts" / "repair_schedule_quality_hotspots.py").read_text(encoding="utf-8")
        suite_week_balance_repair_source = (ROOT / "scripts" / "repair_2726_summer_week_balance.py").read_text(encoding="utf-8")
        wyqc_week_balance_repair_source = (ROOT / "scripts" / "repair_wyqc_summer_week_balance.py").read_text(encoding="utf-8")
        wyqc_deadline_repair_source = (ROOT / "scripts" / "repair_wyqc_foundation_deadlines.py").read_text(encoding="utf-8")
        halfday_repair_source = (ROOT / "scripts" / "repair_2757_halfday_blocks.py").read_text(encoding="utf-8")
        public_coverage_repair_source = (ROOT / "scripts" / "repair_public_coverage_gaps.py").read_text(encoding="utf-8")
        subject_utils_source = (ROOT / "scripts" / "subject_utils.py").read_text(encoding="utf-8")

        self.assertIn("CORE_PUBLIC_SUBJECTS", subject_utils_source)
        self.assertIn("PUBLIC_SUBJECTS_WITH_CHINESE", subject_utils_source)
        self.assertIn("PUBLIC_SUBJECT_SORT_ORDER", subject_utils_source)
        self.assertIn("PUBLIC_SUBJECT_PLACEMENT_ORDER", subject_utils_source)
        self.assertIn("CORE_PUBLIC_SUBJECT_PREFERRED_PERIODS", subject_utils_source)
        self.assertIn("from scripts.subject_utils import CORE_PUBLIC_SUBJECTS", scheduler_source)
        self.assertIn("from scripts.subject_utils import CORE_PUBLIC_SUBJECTS", business_import_source)
        self.assertIn("from scripts.subject_utils import CORE_PUBLIC_SUBJECTS", schedule_data_source)
        self.assertIn("from scripts.subject_utils import PUBLIC_SUBJECTS_WITH_CHINESE", admin_source)
        self.assertIn("from scripts.subject_utils import PUBLIC_SUBJECTS_WITH_CHINESE", erp_export_source)
        self.assertIn("from scripts.subject_utils import PUBLIC_SUBJECTS_WITH_CHINESE", erp_lesson_map_source)
        self.assertIn("CORE_PUBLIC_SUBJECTS", schedule_batch_source)
        self.assertIn("CORE_PUBLIC_SUBJECTS", camp_maintenance_source)
        self.assertIn("PUBLIC_SUBJECT_PLACEMENT_ORDER as PUBLIC_SUBJECT_PRIORITY", camp_maintenance_source)
        self.assertIn("PUBLIC_SUBJECT_PLACEMENT_ORDER as SUBJECT_ORDER", public_coverage_repair_source)
        self.assertIn("CORE_PUBLIC_SUBJECTS", suite_week_balance_repair_source)
        self.assertIn("CORE_PUBLIC_SUBJECTS", wyqc_week_balance_repair_source)
        self.assertIn("CORE_PUBLIC_SUBJECTS", wyqc_deadline_repair_source)
        self.assertIn("CORE_PUBLIC_SUBJECT_PREFERRED_PERIODS", schedule_batch_source)
        self.assertIn("CORE_PUBLIC_SUBJECT_PREFERRED_PERIODS", camp_maintenance_source)
        self.assertIn("CORE_PUBLIC_SUBJECT_PREFERRED_PERIODS", quality_hotspot_repair_source)
        self.assertIn("PUBLIC_SUBJECTS_WITH_CHINESE as PUBLIC_SUBJECTS", schedule_batch_source)
        self.assertIn("PUBLIC_SUBJECT_SORT_ORDER as SUBJECT_ORDER", schedule_batch_source)
        self.assertIn("PUBLIC_SUBJECT_SORT_ORDER as SUBJECT_ORDER", schedule_scope_source)
        self.assertIn("PUBLIC_SUBJECT_SORT_ORDER as SUBJECT_ORDER", schedule_week_balance_source)
        self.assertIn("PUBLIC_SUBJECTS_WITH_CHINESE as PUBLIC_SUBJECTS", audit_quality_source)
        self.assertIn("PUBLIC_SUBJECTS_WITH_CHINESE as PUBLIC_SUBJECTS", quality_hotspot_repair_source)
        self.assertIn("PUBLIC_SUBJECTS_WITH_CHINESE as PUBLIC_SUBJECTS", halfday_repair_source)
        for source in (
            admin_source,
            erp_export_source,
            erp_lesson_map_source,
            scheduler_source,
            business_import_source,
            schedule_data_source,
            schedule_batch_source,
            schedule_scope_source,
            schedule_week_balance_source,
            camp_maintenance_source,
            audit_quality_source,
            quality_hotspot_repair_source,
            halfday_repair_source,
            public_coverage_repair_source,
            suite_week_balance_repair_source,
            wyqc_week_balance_repair_source,
            wyqc_deadline_repair_source,
        ):
            self.assertIsNone(re.search(r'(?m)^PUBLIC_(?:TEACHER_)?SUBJECTS\s*=\s*\{"英语", "政治", "数学", "语文"\}', source))
            self.assertIsNone(re.search(r'(?m)^SUBJECT_ORDER\s*=\s*\{"数学": 0, "英语": 1, "政治": 2, "语文": 3\}', source))
            self.assertIsNone(re.search(r'(?m)^SUBJECT_ORDER\s*=\s*\{"数学": 0, "政治": 1, "英语": 2\}', source))
            self.assertIsNone(re.search(r'(?m)^PUBLIC_SUBJECT_PRIORITY\s*=\s*\{"数学": 0, "政治": 1, "英语": 2, "语文": 3\}', source))
            self.assertNotIn('{"英语", "政治", "数学"}', source)
            self.assertNotIn('{"英语", "数学", "政治"}', source)
            self.assertNotIn('{"数学": "AM", "英语": "PM", "政治": "PM"}', source)

    def test_weekday_normalization_lives_in_shared_weekday_utils(self) -> None:
        admin_source = (ROOT / "data_admin_server.py").read_text(encoding="utf-8")
        web_admin_source = (ROOT / "web_admin" / "app.js").read_text(encoding="utf-8")
        scheduler_source = (ROOT / "scheduler.py").read_text(encoding="utf-8")
        generator_source = (ROOT / "generate_time_slots.py").read_text(encoding="utf-8")
        business_import_source = (ROOT / "business_class_import.py").read_text(encoding="utf-8")
        schedule_display_source = (ROOT / "scripts" / "schedule_display.py").read_text(encoding="utf-8")
        weekday_utils_source = (ROOT / "scripts" / "weekday_utils.py").read_text(encoding="utf-8")

        self.assertIn("from scripts.weekday_utils import", scheduler_source)
        self.assertIn("from scripts.weekday_utils import", generator_source)
        self.assertIn("from scripts.weekday_utils import", business_import_source)
        self.assertIn("from scripts.weekday_utils import", schedule_display_source)
        self.assertIn("from scripts.weekday_utils import WEEKDAY_LABELS", admin_source)
        self.assertIn("WEEKDAY_ALIASES", weekday_utils_source)
        self.assertIn("WEEKDAY_LABELS", weekday_utils_source)
        self.assertIn('"weekday_options": list(WEEKDAY_LABELS)', admin_source)
        self.assertIn('lookupOptions("weekday_options")', web_admin_source)
        self.assertIsNone(re.search(r"(?m)^WEEKDAY_ALIASES\s*=", scheduler_source))
        self.assertIsNone(re.search(r"(?m)^WEEKDAY_ALIASES\s*=", generator_source))
        self.assertIsNone(re.search(r"(?m)^WEEKDAY_LABELS\s*=", schedule_display_source))
        self.assertNotIn('["周一", "周二", "周三", "周四", "周五", "周六", "周日"]', business_import_source)
        self.assertNotIn('return ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];', web_admin_source)

    def test_time_slot_generator_reuses_shared_date_normalization(self) -> None:
        generator_source = (ROOT / "generate_time_slots.py").read_text(encoding="utf-8")
        pipeline_source = (ROOT / "run_scheduling_pipeline.py").read_text(encoding="utf-8")
        admin_source = (ROOT / "data_admin_server.py").read_text(encoding="utf-8")
        web_admin_source = (ROOT / "web_admin" / "app.js").read_text(encoding="utf-8")
        schedule_display_source = (ROOT / "scripts" / "schedule_display.py").read_text(encoding="utf-8")
        maintenance_source = (ROOT / "scripts" / "build_camp_maintenance_schedule.py").read_text(encoding="utf-8")
        halfday_repair_source = (ROOT / "scripts" / "repair_2757_halfday_blocks.py").read_text(encoding="utf-8")
        public_gap_repair_source = (ROOT / "scripts" / "repair_public_coverage_gaps.py").read_text(encoding="utf-8")
        quality_hotspot_repair_source = (ROOT / "scripts" / "repair_schedule_quality_hotspots.py").read_text(encoding="utf-8")
        time_slot_templates_source = (ROOT / "scripts" / "time_slot_templates.py").read_text(encoding="utf-8")

        self.assertIn("from scripts.field_utils import normalize_iso_date_text", generator_source)
        self.assertIn("from scripts.time_slot_templates import DEFAULT_LESSON_TEMPLATES", generator_source)
        self.assertIn("from scripts.time_slot_templates import DEFAULT_LESSON_TEMPLATES, default_lesson_template_rows", admin_source)
        self.assertIn("from scripts.time_slot_templates import standard_slot_specs_by_period", maintenance_source)
        self.assertIn("from scripts.time_slot_templates import adjacent_halfday_slot_map", halfday_repair_source)
        self.assertIn("from scripts.time_slot_templates import lesson_slot_order, period_slot_specs", public_gap_repair_source)
        self.assertIn("from scripts.time_slot_templates import period_slot_specs", quality_hotspot_repair_source)
        self.assertIn("from scripts.time_slot_templates import display_lesson_slot_rows", schedule_display_source)
        self.assertIn('"lesson_templates": default_lesson_template_rows()', admin_source)
        self.assertIn("DEFAULT_LESSON_TEMPLATES", time_slot_templates_source)
        self.assertIn("def display_lesson_slot_rows", time_slot_templates_source)
        self.assertIn("state.lookups?.lesson_templates", web_admin_source)
        self.assertNotIn("DEFAULT_DAY_SLOTS = [", generator_source)
        self.assertNotIn("const defaultLessonTemplates = [", web_admin_source)
        self.assertNotIn("STANDARD_DISPLAY_SLOTS = (", schedule_display_source)
        self.assertNotIn('"label": "晚上一"', schedule_display_source)
        for source in (maintenance_source, halfday_repair_source, public_gap_repair_source, quality_hotspot_repair_source):
            self.assertNotIn('("AM1", "上午一", "08:00", "10:00")', source)
            self.assertNotIn('("PM1", "下午一", "14:00", "16:00")', source)
            self.assertNotIn("PERIOD_SLOTS = {", source)
            self.assertNotIn("SECOND_SLOT = {", source)
        self.assertNotIn("datetime.strptime", generator_source)
        self.assertIn("normalize_iso_date_text", pipeline_source)
        self.assertNotIn("date.fromisoformat(value)", pipeline_source)

    def test_window_normalization_lives_in_shared_window_utils(self) -> None:
        admin_source = (ROOT / "data_admin_server.py").read_text(encoding="utf-8")
        scheduler_source = (ROOT / "scheduler.py").read_text(encoding="utf-8")
        class_windows_source = (ROOT / "scripts" / "schedule_class_windows.py").read_text(encoding="utf-8")
        schedule_batch_source = (ROOT / "scripts" / "schedule_batch.py").read_text(encoding="utf-8")
        schedule_scope_source = (ROOT / "scripts" / "schedule_scope.py").read_text(encoding="utf-8")
        camp_maintenance_source = (ROOT / "scripts" / "build_camp_maintenance_schedule.py").read_text(encoding="utf-8")
        window_utils_source = (ROOT / "scripts" / "window_utils.py").read_text(encoding="utf-8")
        frontend_source = (ROOT / "web_admin" / "app.js").read_text(encoding="utf-8")

        self.assertIn("from scripts.window_utils import", admin_source)
        self.assertIn("from scripts.window_utils import", scheduler_source)
        self.assertIn("from scripts.window_utils import", class_windows_source)
        self.assertIn("SEASON_WINDOW_ID_TO_NAME", window_utils_source)
        self.assertIn("SEASON_WINDOW_ORDER", window_utils_source)
        self.assertIn("SEASON_WINDOW_OPTIONS", window_utils_source)
        self.assertIn("YEAR_SEASON_WINDOW_PATTERN", window_utils_source)
        self.assertIn("SEASON_WINDOW_ORDER", admin_source)
        self.assertIn("SEASON_WINDOW_OPTIONS", admin_source)
        self.assertIn("season_window_options", admin_source)
        self.assertIn("state.lookups?.season_window_options", frontend_source)
        self.assertNotIn("const seasonWindowDefaults = {", frontend_source)
        self.assertIsNone(re.search(r"(?m)^SEASON_WINDOW_ID_TO_NAME\s*=", scheduler_source))
        self.assertIsNone(re.search(r"(?m)^SEASON_WINDOW_NAME_TO_ID\s*=", scheduler_source))
        self.assertIsNone(re.search(r"(?m)^def expanded_window_tokens\(", scheduler_source))
        self.assertNotIn("season_tokens = {", class_windows_source)
        self.assertIn("window_names", schedule_scope_source)
        self.assertIn("window_names=window_names", schedule_batch_source)
        self.assertNotIn("quarters = season_names_for_constraints", schedule_batch_source)
        self.assertNotIn("quarters={", camp_maintenance_source)

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
        for path in release_script_python_files():
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

    def test_calendar_helpers_live_in_shared_calendar_utils(self) -> None:
        calendar_utils_source = (ROOT / "scripts" / "calendar_utils.py").read_text(encoding="utf-8")
        schedule_display_source = (ROOT / "scripts" / "schedule_display.py").read_text(encoding="utf-8")
        schedule_data_source = (ROOT / "scripts" / "schedule_data.py").read_text(encoding="utf-8")
        schedule_week_balance_source = (ROOT / "scripts" / "schedule_week_balance.py").read_text(encoding="utf-8")
        audit_quality_source = (ROOT / "scripts" / "audit_schedule_quality.py").read_text(encoding="utf-8")
        public_gap_source = (ROOT / "scripts" / "repair_public_coverage_gaps.py").read_text(encoding="utf-8")
        camp_maintenance_source = (ROOT / "scripts" / "build_camp_maintenance_schedule.py").read_text(encoding="utf-8")

        self.assertIn("def week_start_date", calendar_utils_source)
        self.assertIn("def week_range", calendar_utils_source)
        self.assertIn("def iso_week_key", calendar_utils_source)
        self.assertIn("from scripts.calendar_utils import", schedule_display_source)
        self.assertIn("date_range_values as shared_date_range_values", schedule_data_source)
        self.assertIn("from scripts.calendar_utils import iso_week_key", schedule_week_balance_source)
        self.assertIn("from scripts.calendar_utils import week_dates, week_range, week_start", audit_quality_source)
        self.assertIn("from scripts.calendar_utils import date_range", public_gap_source)
        self.assertIn("from scripts.calendar_utils import (", camp_maintenance_source)
        self.assertNotIn("def iter_dates", public_gap_source)
        self.assertNotIn("current += timedelta(days=7)", audit_quality_source)

    def test_schedule_display_exports_calendar_helpers_for_repair_outputs(self) -> None:
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
