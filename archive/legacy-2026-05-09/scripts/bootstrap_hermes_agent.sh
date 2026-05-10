#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK_FILE="${HERMES_AGENT_LOCK_FILE:-$ROOT_DIR/hermes-agent.lock.json}"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
HERMES_INSTALL_DIR="${HERMES_INSTALL_DIR:-$HERMES_HOME/hermes-agent}"
FACTORY_DIR="${FACTORY_DIR:-$ROOT_DIR/factory}"
CODEX_MODEL="${HERMES_HARNESS_CODEX_MODEL:-gpt-5.3-codex}"
CODEX_BASE_URL="${HERMES_CODEX_BASE_URL:-https://chatgpt.com/backend-api/codex}"
BACKUP_ROOT="${HERMES_BOOTSTRAP_BACKUP_ROOT:-/private/tmp}"

export PATH="$HOME/.local/bin:$PATH"

read_lock() {
  python3 - "$LOCK_FILE" "$1" <<'PY'
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(data[sys.argv[2]])
PY
}

PIN_COMMIT="$(read_lock commit)"
INSTALL_SCRIPT_URL="$(read_lock install_script)"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

command -v python3 >/dev/null 2>&1 || fail "python3 is required"
command -v git >/dev/null 2>&1 || fail "git is required"
command -v curl >/dev/null 2>&1 || fail "curl is required"

backup_dir="$BACKUP_ROOT/hermes-agent-bootstrap-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$backup_dir"
for path in "$HERMES_HOME/.env" "$HERMES_HOME/config.yaml" "$HERMES_HOME/auth.json"; do
  if [ -f "$path" ]; then
    cp -p "$path" "$backup_dir/$(basename "$path")"
  fi
done

echo "Hermes bootstrap"
echo "  home:    $HERMES_HOME"
echo "  install: $HERMES_INSTALL_DIR"
echo "  commit:  $PIN_COMMIT"
echo "  backup:  $backup_dir"

if [ "${HERMES_BOOTSTRAP_REINSTALL:-0}" = "1" ] || [ ! -x "$HERMES_INSTALL_DIR/venv/bin/hermes" ] || [ ! -d "$HERMES_INSTALL_DIR/.git" ]; then
  installer="$backup_dir/install.sh"
  curl -fsSL "$INSTALL_SCRIPT_URL" -o "$installer"
  if [ "${HERMES_SKIP_OPTIONAL_SETUP:-0}" = "1" ]; then
    python3 - "$installer" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
text = text.replace(
    "check_node() {\n",
    "check_node() {\n"
    "    if [ \"${HERMES_SKIP_OPTIONAL_SETUP:-0}\" = \"1\" ]; then\n"
    "        log_info \"Skipping Node.js/browser dependency setup (HERMES_SKIP_OPTIONAL_SETUP=1)\"\n"
    "        HAS_NODE=false\n"
    "        return 0\n"
    "    fi\n",
    1,
)
text = text.replace(
    "install_system_packages() {\n",
    "install_system_packages() {\n"
    "    if [ \"${HERMES_SKIP_OPTIONAL_SETUP:-0}\" = \"1\" ]; then\n"
    "        log_info \"Skipping optional ripgrep/ffmpeg install (HERMES_SKIP_OPTIONAL_SETUP=1)\"\n"
    "        return 0\n"
    "    fi\n",
    1,
)
path.write_text(text, encoding="utf-8")
PY
  fi
  bash "$installer" --skip-setup --dir "$HERMES_INSTALL_DIR" --hermes-home "$HERMES_HOME"
else
  echo "Hermes install already present; set HERMES_BOOTSTRAP_REINSTALL=1 to rerun the official installer."
fi

if [ ! -d "$HERMES_INSTALL_DIR/.git" ]; then
  fail "Hermes install did not create a git checkout at $HERMES_INSTALL_DIR"
fi

if [ -n "$(git -C "$HERMES_INSTALL_DIR" status --porcelain)" ]; then
  if [ "${HERMES_BOOTSTRAP_FORCE_PIN:-0}" = "1" ]; then
    echo "Hermes checkout has generated/local files; cleaning before pinning."
    git -C "$HERMES_INSTALL_DIR" reset --hard
    git -C "$HERMES_INSTALL_DIR" clean -fdx -e venv/
  else
    fail "Hermes checkout is dirty at $HERMES_INSTALL_DIR; refusing to pin over local edits"
  fi
fi

git -C "$HERMES_INSTALL_DIR" fetch --tags origin
git -C "$HERMES_INSTALL_DIR" checkout --detach "$PIN_COMMIT"

if [ ! -x "$HERMES_INSTALL_DIR/venv/bin/python" ]; then
  python3 -m venv "$HERMES_INSTALL_DIR/venv"
fi

if ! "$HERMES_INSTALL_DIR/venv/bin/python" -m pip --version >/dev/null 2>&1; then
  "$HERMES_INSTALL_DIR/venv/bin/python" -m ensurepip --upgrade
fi

if command -v uv >/dev/null 2>&1; then
  (cd "$HERMES_INSTALL_DIR" && VIRTUAL_ENV="$HERMES_INSTALL_DIR/venv" uv pip install -e ".[all]")
else
  "$HERMES_INSTALL_DIR/venv/bin/python" -m pip install -e "$HERMES_INSTALL_DIR[all]"
fi

link_dir="$HOME/.local/bin"
mkdir -p "$link_dir"
ln -sfn "$HERMES_INSTALL_DIR/venv/bin/hermes" "$link_dir/hermes"

import_codex_auth() {
  local target_home="$1"
  mkdir -p "$target_home"
  HERMES_HOME="$target_home" \
  HERMES_CODEX_BASE_URL="$CODEX_BASE_URL" \
  "$HERMES_INSTALL_DIR/venv/bin/python" - "$CODEX_MODEL" "$CODEX_BASE_URL" <<'PY'
import sys

from hermes_cli.auth import (
    _import_codex_cli_tokens,
    _save_codex_tokens,
    _update_config_for_provider,
)

model = sys.argv[1]
base_url = sys.argv[2]
tokens = _import_codex_cli_tokens()
if not tokens:
    raise SystemExit("No valid Codex CLI OAuth tokens found at CODEX_HOME/auth.json or ~/.codex/auth.json")
_save_codex_tokens(tokens)
_update_config_for_provider("openai-codex", base_url, default_model=model)
PY
}

import_codex_auth "$HERMES_HOME"

PYTHONPATH="$ROOT_DIR" python3 -m harness.tools.boss_team install-local \
  --factory "$FACTORY_DIR" \
  --home-root "$HERMES_HOME" \
  --layout hermes-profiles \
  --overwrite

for profile in boss supervisor hr conductor critic a2a-bridge; do
  import_codex_auth "$HERMES_HOME/profiles/$profile"
done

PYTHONPATH="$ROOT_DIR" python3 -m harness.tools.boss_team verify-local \
  --factory "$FACTORY_DIR" \
  --home-root "$HERMES_HOME" \
  --layout hermes-profiles

"$ROOT_DIR/scripts/install_hermes_a2a.sh"

if [ -n "${HERMES_HUB_URL:-}" ] && [ -n "${HERMES_HUB_API_TOKEN:-}" ]; then
  PYTHONPATH="$ROOT_DIR" python3 -m harness.tools.boss_team apply-hub \
    --hub-url "$HERMES_HUB_URL" \
    --token "$HERMES_HUB_API_TOKEN"
fi

"$link_dir/hermes" version
echo "Hermes bootstrap complete."
