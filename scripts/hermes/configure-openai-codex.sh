#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MODEL="${1:-${HERMES_CODEX_MODEL:-gpt-5.5}}"
BASE_URL="${HERMES_CODEX_BASE_URL:-https://chatgpt.com/backend-api/codex}"
AUTH_BACKUP="${HERMES_CODEX_AUTH_BACKUP:-/workspace/.local/hermes-auth-backup/auth.json}"

cd "$ROOT_DIR"

docker compose -f docker-compose.local.yml run --rm \
  -e HERMES_CODEX_MODEL="$MODEL" \
  -e HERMES_CODEX_BASE_URL="$BASE_URL" \
  -e HERMES_CODEX_AUTH_BACKUP="$AUTH_BACKUP" \
  local-vm bash -lc '
    set -euo pipefail
    /workspace/scripts/hermes/install-mock-kanban.sh

    "$HERMES_INSTALL_DIR/venv/bin/python" - <<'"'"'PY'"'"'
import os
import shutil
from pathlib import Path

import yaml

hermes_home = Path(os.environ.get("HERMES_HOME", "/vm/hermes-home"))
config_path = hermes_home / "config.yaml"
config_path.parent.mkdir(parents=True, exist_ok=True)

# Captured from the Docker Hermes home on 2026-05-09. This intentionally
# excludes auth.json and .env contents; those remain in the Docker volume.
captured_defaults = yaml.safe_load(
    r"""
model:
  default: gpt-5.5
  provider: openai-codex
  base_url: https://chatgpt.com/backend-api/codex
providers: {}
fallback_providers: []
credential_pool_strategies: {}
toolsets:
  - hermes-cli
  - kanban
memory:
  provider: holographic
plugins:
  hermes-memory-store:
    db_path: $HERMES_HOME/memory_store.db
    auto_extract: false
    default_trust: 0.5
    min_trust_threshold: 0.3
    temporal_decay_half_life: 0
    hrr_dim: 1024
agent:
  max_turns: 60
  gateway_timeout: 1800
  restart_drain_timeout: 180
  api_max_retries: 3
  service_tier: ''
  tool_use_enforcement: auto
  gateway_timeout_warning: 900
  gateway_notify_interval: 180
  gateway_auto_continue_freshness: 3600
  image_input_mode: auto
  disabled_toolsets:
    - feishu_doc
    - feishu_drive
  verbose: false
  reasoning_effort: medium
terminal:
  backend: local
  modal_mode: auto
  cwd: .
  timeout: 180
  env_passthrough: []
  shell_init_files: []
  auto_source_bashrc: true
  docker_image: nikolaik/python-nodejs:python3.11-nodejs20
  docker_forward_env: []
  docker_env: {}
  singularity_image: docker://nikolaik/python-nodejs:python3.11-nodejs20
  modal_image: nikolaik/python-nodejs:python3.11-nodejs20
  daytona_image: nikolaik/python-nodejs:python3.11-nodejs20
  vercel_runtime: node24
  container_cpu: 1
  container_memory: 5120
  container_disk: 51200
  container_persistent: true
  docker_volumes: []
  docker_mount_cwd_to_workspace: false
  docker_run_as_host_user: false
  persistent_shell: true
  lifetime_seconds: 300
web:
  backend: ddgs
  search_backend: ''
  extract_backend: ''
  use_gateway: false
browser:
  inactivity_timeout: 120
  command_timeout: 30
  record_sessions: false
  allow_private_urls: false
  engine: auto
  auto_local_for_private_urls: true
  cdp_url: ''
  dialog_policy: must_respond
  dialog_timeout_s: 300
  camofox:
    managed_persistence: false
compression:
  enabled: true
  threshold: 0.7
  target_ratio: 0.2
  protect_last_n: 20
display:
  compact: false
  personality: kawaii
  resume_display: full
  busy_input_mode: interrupt
  tui_auto_resume_recent: false
  bell_on_complete: false
  show_reasoning: false
  streaming: true
  final_response_markdown: strip
  persistent_output: true
  persistent_output_max_lines: 200
  inline_diffs: true
  show_cost: false
  skin: default
  language: en
  tui_status_indicator: kaomoji
  user_message_preview:
    first_lines: 2
    last_lines: 2
  interim_assistant_messages: true
  tool_progress_command: false
  tool_progress_overrides: {}
  tool_preview_length: 0
  ephemeral_system_ttl: 0
  platforms: {}
  runtime_footer:
    enabled: false
    fields:
      - model
      - context_pct
      - cwd
  copy_shortcut: auto
  tool_progress: new
  cleanup_progress: false
  background_process_notifications: all
"""
)


def merge(base, patch):
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            merge(base[key], value)
        else:
            base[key] = value
    return base


if config_path.exists():
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
else:
    config = {}

merge(config, captured_defaults)
config.setdefault("model", {})
config["model"]["provider"] = "openai-codex"
config["model"]["default"] = os.environ["HERMES_CODEX_MODEL"]
config["model"]["base_url"] = os.environ["HERMES_CODEX_BASE_URL"]

config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

for secret_name in ("auth.json", ".env"):
    secret_path = hermes_home / secret_name
    if secret_path.exists():
        secret_path.chmod(0o600)

auth_backup = Path(os.environ["HERMES_CODEX_AUTH_BACKUP"])
auth_restored = False
if auth_backup.exists() and auth_backup.is_file():
    auth_target = hermes_home / "auth.json"
    shutil.copy2(auth_backup, auth_target)
    auth_target.chmod(0o600)
    auth_restored = True

(hermes_home / ".codex-auth-restored").write_text(str(auth_restored), encoding="utf-8")
PY

    echo
    echo "Configured Hermes defaults:"
    "$HERMES_INSTALL_DIR/venv/bin/python" - <<'"'"'PY'"'"'
from pathlib import Path
import yaml

config = yaml.safe_load(Path("/vm/hermes-home/config.yaml").read_text(encoding="utf-8"))
selected = {
    "model": config["model"],
    "toolsets": config.get("toolsets", []),
    "memory": config.get("memory", {}),
    "plugins": {
        "hermes-memory-store": config.get("plugins", {}).get("hermes-memory-store", {}),
    },
    "agent": {
        "max_turns": config.get("agent", {}).get("max_turns"),
        "reasoning_effort": config.get("agent", {}).get("reasoning_effort"),
    },
    "terminal": {
        "backend": config.get("terminal", {}).get("backend"),
        "cwd": config.get("terminal", {}).get("cwd"),
        "timeout": config.get("terminal", {}).get("timeout"),
    },
    "display": {
        "personality": config.get("display", {}).get("personality"),
        "show_reasoning": config.get("display", {}).get("show_reasoning"),
        "streaming": config.get("display", {}).get("streaming"),
    },
}
print(yaml.safe_dump(selected, sort_keys=False).strip())
PY

    echo
    if [ "$(cat /vm/hermes-home/.codex-auth-restored 2>/dev/null || true)" = "True" ]; then
      echo "OpenAI Codex auth restored from local backup."
      echo
    fi
    hermes auth status openai-codex || true
  '

cat <<EOF

Hermes is configured to use OpenAI Codex by default.

Model:    $MODEL
Provider: openai-codex
Base URL: $BASE_URL
Memory:   holographic
Kanban:   mock remote team dispatcher installed for team:<name> assignees

If OpenAI Codex auth is not logged in yet, run:

  docker compose -f docker-compose.local.yml run --rm local-vm hermes auth add openai-codex

The script restores non-secret Hermes settings captured from the current Docker
configuration. If .local/hermes-auth-backup/auth.json exists, it restores that
local ignored auth backup into the Docker volume. Auth is never printed.

EOF
