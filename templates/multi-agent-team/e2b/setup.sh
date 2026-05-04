#!/usr/bin/env sh
set -eu

WORKSPACE="${WORKSPACE:-/home/user/workspace}"
mkdir -p \
  "$WORKSPACE/inbox" \
  "$WORKSPACE/outbox" \
  "$WORKSPACE/drafts" \
  "$WORKSPACE/context" \
  "$WORKSPACE/source" \
  "$WORKSPACE/exemplars" \
  "$WORKSPACE/status" \
  "$WORKSPACE/.harness"
mkdir -p \
  "$WORKSPACE/internal/orders" \
  "$WORKSPACE/internal/assignments" \
  "$WORKSPACE/internal/decisions" \
  "$WORKSPACE/internal/status"
mkdir -p \
  "$WORKSPACE/internal/inbox/coordinator" \
  "$WORKSPACE/internal/inbox/worker" \
  "$WORKSPACE/internal/inbox/reviewer" \
  "$WORKSPACE/internal/inbox/scribe"
mkdir -p \
  "$WORKSPACE/internal/outbox/coordinator" \
  "$WORKSPACE/internal/outbox/worker" \
  "$WORKSPACE/internal/outbox/reviewer" \
  "$WORKSPACE/internal/outbox/scribe"

cat > "$WORKSPACE/.harness/setup-complete.json" <<JSON
{
  "template": "multi-agent-team",
  "cron_enabled": false,
  "workspace": "$WORKSPACE"
}
JSON

for required in python3 jq rg git; do
  command -v "$required" >/dev/null 2>&1 || echo "missing optional tool: $required" >&2
done
if ! command -v codex >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
  npm install -g @openai/codex@0.128.0
fi

echo "multi-agent-team E2B setup complete"
