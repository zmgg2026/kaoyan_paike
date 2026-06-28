from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts.build_release_archive import build_release_archive
from scripts.audit_release_package import REQUIRED_PATHS, audit_paths, forbidden_reason, normalize_path, zip_paths


class ReleasePackageAuditTest(unittest.TestCase):
    def test_required_release_paths_pass_without_private_files(self) -> None:
        self.assertEqual([], audit_paths(REQUIRED_PATHS))

    def test_shared_template_metadata_is_required(self) -> None:
        self.assertIn("scripts/table_schema.py", REQUIRED_PATHS)
        self.assertIn("scripts/template_tables.py", REQUIRED_PATHS)

    def test_release_audit_reports_missing_required_paths(self) -> None:
        paths = [path for path in REQUIRED_PATHS if path != "README.md"]

        self.assertIn("missing required file: README.md", audit_paths(paths))

    def test_release_audit_blocks_private_generated_and_secret_paths(self) -> None:
        paths = [
            *REQUIRED_PATHS,
            "data/classes.csv",
            "outputs/schedule.csv",
            "scripts/__pycache__/schedule_batch.cpython-313.pyc",
            ".env",
            "share/.DS_Store",
        ]

        issues = audit_paths(paths)

        self.assertTrue(any(issue.endswith("data/classes.csv") for issue in issues))
        self.assertTrue(any(issue.endswith("outputs/schedule.csv") for issue in issues))
        self.assertTrue(any(issue.endswith("scripts/__pycache__/schedule_batch.cpython-313.pyc") for issue in issues))
        self.assertTrue(any(issue.endswith(".env") for issue in issues))
        self.assertTrue(any(issue.endswith("share/.DS_Store") for issue in issues))

    def test_env_example_is_allowed_but_real_env_is_not(self) -> None:
        self.assertEqual("", forbidden_reason(".env.example"))
        self.assertNotEqual("", forbidden_reason(".env"))

    def test_normalize_path_uses_archive_style_slashes(self) -> None:
        self.assertEqual("foo/bar.csv", normalize_path("./foo/bar.csv"))
        self.assertEqual(".env", normalize_path("./.env"))

    def test_zip_paths_strip_single_github_archive_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            zip_path = Path(tmp_dir) / "release.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                for path in REQUIRED_PATHS:
                    archive.writestr(f"repo-main/{path}", "")

            self.assertEqual([], audit_paths(zip_paths(zip_path)))

    def test_zip_audit_blocks_private_files_inside_archive_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            zip_path = Path(tmp_dir) / "release.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                for path in REQUIRED_PATHS:
                    archive.writestr(f"repo-main/{path}", "")
                archive.writestr("repo-main/data/classes.csv", "")

            issues = audit_paths(zip_paths(zip_path))

        self.assertTrue(any(issue.endswith("data/classes.csv") for issue in issues))

    def test_build_release_archive_uses_current_tracked_files_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "README.md").write_text("current", encoding="utf-8")
            (root / "data").mkdir()
            (root / "data" / "classes.csv").write_text("private", encoding="utf-8")
            output = root / "release.zip"

            with patch("scripts.build_release_archive.git_tracked_paths", return_value=["README.md"]):
                build_release_archive(root, output)

            with zipfile.ZipFile(output) as archive:
                self.assertEqual(["README.md"], archive.namelist())
                self.assertEqual("current", archive.read("README.md").decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
