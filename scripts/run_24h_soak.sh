#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FACTORY_DIR="${FACTORY_DIR:-/factory}"
HARNESS_SQLITE_PATH="${HARNESS_SQLITE_PATH:-$FACTORY_DIR/harness.sqlite3}"
HARNESS_VENV="${HARNESS_VENV:-$ROOT_DIR/.venv}"
SOAK_INTERVAL_SECONDS="${SOAK_INTERVAL_SECONDS:-300}"

if [[ -n "${HARNESS_PYTHON:-}" ]]; then
  PYTHON_BIN="$HARNESS_PYTHON"
elif [[ -x "$HARNESS_VENV/bin/python" ]]; then
  PYTHON_BIN="$HARNESS_VENV/bin/python"
else
  PYTHON_BIN="$(command -v python3 || command -v python)"
fi

if [[ -z "$PYTHON_BIN" ]]; then
  echo "No Python interpreter found. Set HARNESS_PYTHON or HARNESS_VENV." >&2
  exit 127
fi

exec "$PYTHON_BIN" -m harness.tools.run_soak \
  --factory "$FACTORY_DIR" \
  --db "$HARNESS_SQLITE_PATH" \
  --duration-hours 24 \
  --interval-seconds "$SOAK_INTERVAL_SECONDS" \
  "$@"
