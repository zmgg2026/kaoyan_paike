#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.audit_release_package import normalize_path


def git_tracked_paths(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
    )
    return sorted(
        normalize_path(item.decode("utf-8"))
        for item in result.stdout.split(b"\0")
        if item
    )


def build_release_archive(root: Path, output: Path) -> None:
    root = root.resolve()
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative_path in git_tracked_paths(root):
            source_path = root / relative_path
            if not source_path.is_file():
                raise FileNotFoundError(f"tracked file is missing from working tree: {relative_path}")
            archive.write(source_path, relative_path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a release zip from current git-tracked working tree files.")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Project root. Defaults to the current directory.")
    parser.add_argument("--output", type=Path, required=True, help="Zip file to write.")
    args = parser.parse_args(argv)

    build_release_archive(args.root, args.output)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
