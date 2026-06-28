#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
PROJECT_NAME="${PROJECT_NAME:-xdf-schedule-maintenance}"
PRODUCTION_BRANCH="${PRODUCTION_BRANCH:-production}"
BUNDLE_DIR="${BUNDLE_DIR:-$ROOT_DIR/outputs/cloudflare_schedule_publish}"

cd "$ROOT_DIR"
"$PYTHON_BIN" scripts/build_cloudflare_publish_bundle.py --bundle-dir "$BUNDLE_DIR" >/dev/null
npx --yes wrangler pages deploy "$BUNDLE_DIR" --project-name "$PROJECT_NAME" --branch "$PRODUCTION_BRANCH"
