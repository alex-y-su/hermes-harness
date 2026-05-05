#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FACTORY_DIR="${FACTORY_DIR:-/factory}"
HARNESS_SQLITE_PATH="${HARNESS_SQLITE_PATH:-$FACTORY_DIR/harness.sqlite3}"
HARNESS_VENV="${HARNESS_VENV:-$ROOT_DIR/.venv}"
SOAK_INTERVAL_SECONDS="${SOAK_INTERVAL_SECONDS:-300}"

exec "$HARNESS_VENV/bin/python" -m harness.tools.run_soak \
  --factory "$FACTORY_DIR" \
  --db "$HARNESS_SQLITE_PATH" \
  --duration-hours 24 \
  --interval-seconds "$SOAK_INTERVAL_SECONDS" \
  "$@"
