#!/usr/bin/env bash
set -euo pipefail

stage="${1:?usage: scripts/vm/verify-stage.sh <stage>}"
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

case "$stage" in
  1)
    scripts/vm/build.sh
    docker compose -f docker-compose.local.yml run --rm local-vm bash -lc '
      set -euo pipefail
      python -m pip install -e ".[dev]"
      command -v hermes
      hermes version || hermes --version
      test -d "$HERMES_INSTALL_DIR/.git"
      git -C "$HERMES_INSTALL_DIR" rev-parse HEAD
      test -f "$HERMES_INSTALL_DIR/hermes_cli/mock_remote_kanban.py"
      grep -q "HERMES_HARNESS_MOCK_REMOTE_KANBAN_START" "$HERMES_INSTALL_DIR/hermes_cli/kanban_db.py"
      python -m hermes_harness doctor --json | tee /tmp/hermes-harness-doctor.json
      jq -e ".hermes_available == true" /tmp/hermes-harness-doctor.json
      "$HERMES_INSTALL_DIR/venv/bin/python" - <<'"'"'PY'"'"'
from pathlib import Path
import yaml

config = yaml.safe_load(Path("/vm/hermes-home/config.yaml").read_text(encoding="utf-8"))
model = config.get("model") or {}
assert model.get("provider") == "openai-codex", model
assert model.get("default") == "gpt-5.5", model
assert model.get("base_url") == "https://chatgpt.com/backend-api/codex", model
toolsets = set(config.get("toolsets") or [])
assert "kanban" in toolsets, toolsets
memory = config.get("memory") or {}
assert memory.get("provider") == "holographic", memory
plugin = (config.get("plugins") or {}).get("hermes-memory-store") or {}
assert plugin.get("db_path") == "$HERMES_HOME/memory_store.db", plugin
assert plugin.get("auto_extract") is False, plugin
assert float(plugin.get("default_trust")) == 0.5, plugin
assert int(plugin.get("hrr_dim")) == 1024, plugin
disabled = set((config.get("agent") or {}).get("disabled_toolsets") or [])
assert {"feishu_doc", "feishu_drive"} <= disabled, disabled
PY
      hermes memory status | tee /tmp/hermes-memory-status.txt
      grep -q "Provider:  holographic" /tmp/hermes-memory-status.txt
      grep -q "Status:    available" /tmp/hermes-memory-status.txt
      "$HERMES_INSTALL_DIR/venv/bin/python" - <<'"'"'PY'"'"'
from hermes_cli.config import load_config
from hermes_cli.tools_config import _get_platform_tools

enabled = _get_platform_tools(load_config(), "cli")
assert "feishu_doc" not in enabled, sorted(enabled)
assert "feishu_drive" not in enabled, sorted(enabled)
PY
      HERMES_MOCK_KANBAN_SUCCESS_RATE=1 HERMES_MOCK_KANBAN_SEED=stage1 \
        bash -lc '"'"'
          set -euo pipefail
          hermes kanban boards rm stage1-mock-remote --delete >/dev/null 2>&1 || true
          rm -rf /vm/hermes-home/mock-remote-kanban/stage1-mock-remote
          hermes kanban boards create stage1-mock-remote --switch >/dev/null
          task_id=$(hermes kanban create "Stage 1 mock remote team task" \
            --assignee team:seo \
            --tenant growth \
            --idempotency-key stage1-mock-remote-team \
            --json | jq -r .id)
          hermes kanban dispatch --json | tee /tmp/mock-kanban-dispatch.json
          hermes kanban show "$task_id" --json | tee /tmp/mock-kanban-show.json
          jq -e ".task.status == \"done\"" /tmp/mock-kanban-show.json
          jq -e ".task.assignee == \"team:seo\"" /tmp/mock-kanban-show.json
          jq -e "(.task.result | fromjson).mock_remote == true" /tmp/mock-kanban-show.json
          jq -e "(.task.result | fromjson).team == \"seo\"" /tmp/mock-kanban-show.json
          jq -e "(.task.result | fromjson).stream == \"growth\"" /tmp/mock-kanban-show.json
          jq -e "((.task.result | fromjson).requested_kpis | length) > 0" /tmp/mock-kanban-show.json
          jq -e "((.task.result | fromjson).reported_kpis | length) > 0" /tmp/mock-kanban-show.json
          jq -e "(.task.result | fromjson).approval.tier" /tmp/mock-kanban-show.json
          jq -e "(.task.result | fromjson).main_card_update.action == \"complete\"" /tmp/mock-kanban-show.json
          jq -e "(.task.result | fromjson).test_telemetry.confidence" /tmp/mock-kanban-show.json
          test -f /vm/hermes-home/mock-remote-kanban/stage1-mock-remote/seo/board.json
          jq -e ".tasks[\"$task_id\"].source_board == \"stage1-mock-remote\"" \
            /vm/hermes-home/mock-remote-kanban/stage1-mock-remote/seo/board.json
          jq -e ".tasks[\"$task_id\"].result.reported_kpis | length > 0" \
            /vm/hermes-home/mock-remote-kanban/stage1-mock-remote/seo/board.json
        '"'"'
      pytest -q
    '
    ;;
  *)
    echo "stage $stage is not implemented yet" >&2
    exit 2
    ;;
esac
