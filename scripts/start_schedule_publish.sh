#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8780}"

cd "$ROOT_DIR"
exec "$PYTHON_BIN" schedule_publish_server.py --host "$HOST" --port "$PORT"
