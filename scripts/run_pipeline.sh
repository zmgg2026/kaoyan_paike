#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
SOURCE="${1:-incoming}"

cd "$ROOT_DIR"
"$PYTHON_BIN" run_scheduling_pipeline.py --source "$SOURCE"
