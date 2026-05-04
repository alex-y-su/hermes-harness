#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${ROOT_DIR:-/app}"
HERMES_HOME="${HERMES_HOME:-/opt/hermes-home}"
HERMES_INSTALL_DIR="${HERMES_INSTALL_DIR:-$HERMES_HOME/hermes-agent}"
FACTORY_DIR="${FACTORY_DIR:-/factory}"
CODEX_HOME="${CODEX_HOME:-/codex-auth}"

export ROOT_DIR HERMES_HOME HERMES_INSTALL_DIR FACTORY_DIR CODEX_HOME
export HERMES_BOOTSTRAP_BACKUP_ROOT="${HERMES_BOOTSTRAP_BACKUP_ROOT:-/tmp}"
export HERMES_BOOTSTRAP_FORCE_PIN="${HERMES_BOOTSTRAP_FORCE_PIN:-1}"
export HERMES_A2A_BASE_PORT="${HERMES_A2A_BASE_PORT:-8080}"
export HERMES_A2A_BIND_HOST="${HERMES_A2A_BIND_HOST:-0.0.0.0}"
export HERMES_A2A_PUBLIC_HOST="${HERMES_A2A_PUBLIC_HOST:-127.0.0.1}"
export HERMES_BIN="${HERMES_BIN:-$HOME/.local/bin/hermes}"
export PATH="$HOME/.local/bin:$PATH"

unset OPENAI_API_KEY OPENROUTER_API_KEY OPENROUTER_API_KEY_AIWIZ_LANDING LLM_BASE_URL

if [ ! -f "$CODEX_HOME/auth.json" ]; then
  echo "ERROR: Codex auth file is not mounted at $CODEX_HOME/auth.json" >&2
  exit 1
fi

mkdir -p "$HERMES_HOME" "$FACTORY_DIR"

if [ -x "$HERMES_INSTALL_DIR/venv/bin/hermes" ]; then
  mkdir -p "$(dirname "$HERMES_BIN")"
  ln -sfn "$HERMES_INSTALL_DIR/venv/bin/hermes" "$HERMES_BIN"
fi

if [ "${HERMES_DOCKER_REINSTALL:-0}" = "1" ] \
  || [ ! -x "$HERMES_INSTALL_DIR/venv/bin/hermes" ] \
  || [ ! -f "$HERMES_HOME/a2a-team.json" ]; then
  "$ROOT_DIR/scripts/bootstrap_hermes_agent.sh"
fi

if [ -x "$HERMES_INSTALL_DIR/venv/bin/python" ] \
  && ! find /root/.cache/ms-playwright -maxdepth 1 -type d -name 'chromium-*' 2>/dev/null | grep -q .; then
  mkdir -p /root/.cache/ms-playwright
  python3 -m playwright install chromium
fi

exec env \
  -u OPENAI_API_KEY \
  -u OPENROUTER_API_KEY \
  -u OPENROUTER_API_KEY_AIWIZ_LANDING \
  -u LLM_BASE_URL \
  HERMES_A2A_FOREGROUND=1 \
  "$ROOT_DIR/scripts/start_hermes_a2a_team.sh"
