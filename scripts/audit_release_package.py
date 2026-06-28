#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Iterable, List, Sequence


REQUIRED_PATHS = (
    ".env.example",
    ".github/workflows/ci.yml",
    ".gitignore",
    "README.md",
    "requirements.txt",
    "run_scheduling_pipeline.py",
    "scheduler.py",
    "data_admin_server.py",
    "schedule_publish_server.py",
    "docs/department-reuse-user-guide.md",
    "docs/ai-scheduling-sop.md",
    "docs/github-release-checklist.md",
    "examples/csv_minimal/README.md",
    "examples/csv_minimal/classes.csv",
    "examples/csv_minimal/class_teacher_assignments.csv",
    "examples/csv_minimal/product_courses.csv",
    "examples/csv_minimal/product_schedule_rules.csv",
    "examples/csv_minimal/rooms.csv",
    "examples/csv_minimal/time_slots.csv",
    "scripts/audit_release_package.py",
    "scripts/build_release_archive.py",
    "scripts/template_tables.py",
    "scripts/verify_release.sh",
    "scripts/audit_schedule_coverage.py",
    "scripts/audit_schedule_quality.py",
    "web_admin/index.html",
    "web_admin/app.js",
    "web_admin/styles.css",
    "share/ai-scheduling-project/index.html",
    "cloudflare_schedule_publish/_worker.js",
    "tests/test_pipeline.py",
    "tests/test_release_package_audit.py",
    "tests/test_release_static.py",
)

FORBIDDEN_PREFIXES = (
    ".git/",
    "__pycache__/",
    "data/",
    "outputs/",
    "incoming/",
    "tmp/",
)

FORBIDDEN_PARTS = (
    "/__pycache__/",
    "/.pytest_cache/",
    "/.mypy_cache/",
    "/.ruff_cache/",
    "/.venv/",
    "/venv/",
)

FORBIDDEN_SUFFIXES = (
    ".pyc",
    ".pyo",
    ".log",
)

FORBIDDEN_FILENAMES = (
    ".DS_Store",
    ".env",
)


def normalize_path(path: str) -> str:
    normalized = path.replace(os.sep, "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.rstrip("/")


def strip_common_archive_prefix(paths: Sequence[str]) -> List[str]:
    normalized = [normalize_path(path) for path in paths if normalize_path(path)]
    if any(path in REQUIRED_PATHS for path in normalized):
        return sorted(normalized)
    first_parts = {
        path.split("/", 1)[0]
        for path in normalized
        if "/" in path
    }
    if len(first_parts) != 1:
        return sorted(normalized)
    prefix = next(iter(first_parts))
    stripped = [
        path.removeprefix(f"{prefix}/")
        for path in normalized
        if path != prefix
    ]
    return sorted(path for path in stripped if path)


def git_tracked_paths(root: Path) -> List[str] | None:
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    paths = [
        normalize_path(item.decode("utf-8"))
        for item in result.stdout.split(b"\0")
        if item
    ]
    return sorted(paths)


def walked_paths(root: Path) -> List[str]:
    paths: List[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        paths.append(normalize_path(str(path.relative_to(root))))
    return sorted(paths)


def zip_paths(path: Path) -> List[str]:
    with zipfile.ZipFile(path) as archive:
        paths = [
            normalize_path(info.filename)
            for info in archive.infolist()
            if not info.is_dir()
        ]
    return strip_common_archive_prefix(paths)


def release_paths(root: Path) -> List[str]:
    paths = git_tracked_paths(root)
    if paths is not None:
        return paths
    return walked_paths(root)


def forbidden_reason(path: str) -> str:
    if path.endswith("/.env.example") or path == ".env.example":
        return ""
    if any(path == filename or path.endswith(f"/{filename}") for filename in FORBIDDEN_FILENAMES):
        return "forbidden filename"
    if any(path.startswith(prefix) for prefix in FORBIDDEN_PREFIXES):
        return "forbidden top-level path"
    if any(part in f"/{path}/" for part in FORBIDDEN_PARTS):
        return "forbidden cache or environment path"
    if any(path.endswith(suffix) for suffix in FORBIDDEN_SUFFIXES):
        return "forbidden generated file suffix"
    return ""


def audit_paths(paths: Iterable[str]) -> List[str]:
    normalized = {normalize_path(path) for path in paths}
    issues: List[str] = []
    for required in REQUIRED_PATHS:
        if required not in normalized:
            issues.append(f"missing required file: {required}")
    for path in sorted(normalized):
        reason = forbidden_reason(path)
        if reason:
            issues.append(f"{reason}: {path}")
    return issues


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit reusable release package contents.")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Project root to audit.")
    parser.add_argument("--zip", type=Path, help="Zip archive to audit instead of a project root.")
    args = parser.parse_args(argv)

    if args.zip:
        paths = zip_paths(args.zip.resolve())
    else:
        root = args.root.resolve()
        paths = release_paths(root)
    issues = audit_paths(paths)
    if issues:
        print("Release package audit failed:", file=sys.stderr)
        for issue in issues:
            print(f"- {issue}", file=sys.stderr)
        return 1
    print(f"Release package audit passed ({len(paths)} files checked).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
