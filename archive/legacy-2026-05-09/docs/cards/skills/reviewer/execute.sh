#!/usr/bin/env bash
# Reviewer skill — invoked by the operator at the `reviewer` pipeline step.
#
# Inputs (env):
#   TASK_INPUT  — full card JSON
#   TASK_ID     — card id (informational; the runtime reads card.id from the JSON)
#
# Output (stdout, single JSON line):
#   {"success": <bool>, "verification_steps": [...], "audit_path": "...",
#    "card_id": "...", "reviewed_at_utc": "..."}
#
# Side effect: writes /factory/reviews/<card_id>-<utc_ts>.json (audit log)
#
# Exits 0 on review-complete (regardless of pass/fail). Non-zero only on
# internal error (no JSON produced).

set -euo pipefail
INPUT="${TASK_INPUT:?TASK_INPUT required}"
TASK_ID="${TASK_ID:-unknown}"

# Pipe the card JSON to the runtime; capture its single-line JSON stdout.
RESULT=$(printf '%s' "$INPUT" | python3 /factory/lib/reviewer_runtime.py 2>/tmp/reviewer-stderr-$$.log) || rc=$?
rc=${rc:-0}
if [ "$rc" -ne 0 ] || [ -z "${RESULT:-}" ]; then
    err="$(cat /tmp/reviewer-stderr-$$.log 2>/dev/null || true)"
    rm -f /tmp/reviewer-stderr-$$.log
    printf '%s\n' "{\"success\": false, \"error\": \"reviewer_runtime_failed\", \"task_id\": \"$TASK_ID\", \"stderr\": $(printf '%s' "$err" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')}"
    exit 0
fi
rm -f /tmp/reviewer-stderr-$$.log

printf '%s\n' "$RESULT"
