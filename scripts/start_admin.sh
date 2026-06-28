#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
PORT="${PORT:-8765}"

cd "$ROOT_DIR"
"$PYTHON_BIN" data_admin_server.py --host 127.0.0.1 --port "$PORT"
