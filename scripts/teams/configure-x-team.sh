#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROFILE="${HERMES_X_TEAM_PROFILE:-xworker}"
MODEL="${HERMES_CODEX_MODEL:-gpt-5.5}"
BASE_URL="${HERMES_CODEX_BASE_URL:-https://chatgpt.com/backend-api/codex}"
AUTH_BACKUP="${HERMES_CODEX_AUTH_BACKUP:-/workspace/.local/hermes-auth-backup/auth.json}"

cd "$ROOT_DIR"

docker compose -f docker-compose.local.yml up -d x-team >/dev/null

docker compose -f docker-compose.local.yml exec -T \
  -e HERMES_X_TEAM_PROFILE="$PROFILE" \
  -e HERMES_CODEX_MODEL="$MODEL" \
  -e HERMES_CODEX_BASE_URL="$BASE_URL" \
  -e HERMES_CODEX_AUTH_BACKUP="$AUTH_BACKUP" \
  x-team bash -lc '
    set -euo pipefail
    mkdir -p "$HERMES_HOME"

    "$HERMES_INSTALL_DIR/venv/bin/python" - <<'"'"'PY'"'"'
import os
import shutil
from pathlib import Path

import yaml

home = Path(os.environ["HERMES_HOME"])
home.mkdir(parents=True, exist_ok=True)
config_path = home / "config.yaml"
config = yaml.safe_load(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
config = config or {}

config.setdefault("model", {})
config["model"]["provider"] = "openai-codex"
config["model"]["default"] = os.environ["HERMES_CODEX_MODEL"]
config["model"]["base_url"] = os.environ["HERMES_CODEX_BASE_URL"]

toolsets = list(config.get("toolsets") or [])
for name in ("hermes-cli", "kanban", "terminal", "file", "memory"):
    if name not in toolsets:
        toolsets.append(name)
config["toolsets"] = toolsets

config.setdefault("memory", {})["provider"] = "holographic"
agent = config.setdefault("agent", {})
agent["reasoning_effort"] = "high"
agent["max_turns"] = 80
disabled = set(agent.get("disabled_toolsets") or [])
disabled.update({"feishu_doc", "feishu_drive"})
agent["disabled_toolsets"] = sorted(disabled)

config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

auth_backup = Path(os.environ["HERMES_CODEX_AUTH_BACKUP"])
if auth_backup.exists():
    auth_target = home / "auth.json"
    shutil.copy2(auth_backup, auth_target)
    auth_target.chmod(0o600)
PY

    if ! hermes profile show "$HERMES_X_TEAM_PROFILE" >/dev/null 2>&1; then
      hermes profile create "$HERMES_X_TEAM_PROFILE" --clone --no-alias >/dev/null
    fi

    profile_home="$HERMES_HOME/profiles/$HERMES_X_TEAM_PROFILE"
    mkdir -p "$profile_home"
    cp "$HERMES_HOME/config.yaml" "$profile_home/config.yaml"
    cp "$HERMES_HOME/auth.json" "$profile_home/auth.json" 2>/dev/null || true
    chmod 600 "$profile_home/auth.json" 2>/dev/null || true

    cat > "$profile_home/SOUL.md" <<'"'"'EOF'"'"'
# X Remote Marketing Team

You are the durable X/social sub-team for Hermes Harness.

You execute X strategy and draft-posting tasks delegated by the main marketing
team through Kanban. You own your own board, context, and results. Do not ask the
main team to do your work.

Rules:

- Preserve the task contract: stream, approval, requested KPIs, measurement
  window, decision rule, deliverables, and reporting format.
- Produce concrete X strategy and post drafts, not generic marketing advice.
- Treat the local X gateway command as the configured X API for this
  environment. A successful JSON response from that command is the posting
  receipt for the task.
- Never call any other X/Twitter endpoint.
- For any posting or post-recording step, use only this X API command:
  `hermes-harness-x-api post --text "<post text>" --json`
- For this test, posting through the configured X gateway is pre-approved when
  the post stays inside the delegated product context and avoids customer
  claims, benchmark claims, pricing claims, private roadmap, credentials, or
  customer data.
- Record at least two X posts when the task asks for a campaign cycle, posting
  strategy, or strategy proof.
- For `Card type: campaign_cycle`, create internal follow-up Kanban cards on
  your own `x` board before completing the delegated task:
  1. a KPI verification card that checks engagement, replies, profile clicks,
     and demo clicks on the requested cadence;
  2. a maintenance/cadence card that keeps posting according to the strategy
     until the cycle window ends or a stop rule triggers.
- Link those internal cards to the delegated task when possible using
  `--parent <delegated task id>`, and mention their task ids in the final JSON
  result.
- Treat public posting outside the configured X gateway, real outreach, spend,
  credentials, and customer data as human-approved actions. Posting through
  the configured X gateway is allowed for this test.
- Complete the Kanban task with a JSON result whenever possible. Include:
  completed_deliverables, requested_kpis, reported_kpis, approval,
  measurement_window, decision_rule, evidence, blockers, next_recommendation,
  mock_x_posts, internal_tasks, maintenance_loop, and main_card_update.
- For active campaign cycles, set `main_card_update.action` to `keep_running`,
  `main_card_update.status` to `running`, and `main_card_update.kpi_state` to
  `collecting`.
EOF

    hermes kanban boards create x --switch >/dev/null 2>&1 || true

    echo "Configured X team profile: $HERMES_X_TEAM_PROFILE"
    hermes profile show "$HERMES_X_TEAM_PROFILE"
    hermes auth status openai-codex || true
  '
