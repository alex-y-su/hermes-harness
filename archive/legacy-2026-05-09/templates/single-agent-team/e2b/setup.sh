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
  "$WORKSPACE/internal" \
  "$WORKSPACE/status" \
  "$WORKSPACE/.harness"

cat > "$WORKSPACE/.harness/setup-complete.json" <<JSON
{
  "template": "single-agent-team",
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

echo "single-agent-team E2B setup complete"
