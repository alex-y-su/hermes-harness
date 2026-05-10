#!/usr/bin/env bash
# Skill: propose-tweet — replaces mock post-twitter for tweet card pipelines.
#
# Inputs (env):
#   TASK_INPUT — JSON of card.input. Must include `text` (the tweet body).
#                Optionally `source_url`, `intended_url_substrings` (list).
#   TASK_ID    — id of the source card.
#   FACTORY_ROOT (optional) — root for /factory paths; defaults to /factory.
#
# Side effect: writes <FACTORY_ROOT>/approvals/<approval_id>.json (atomic rename)
# with kind=tweet, status=pending, source_card_id=TASK_ID, payload from input.
#
# Output (stdout, single-line JSON):
#   On success: {"success": true, "approval_id": "appr-...", "approval_path": "...", "approval_status": "pending"}
#   On missing/empty text: {"success": false, "error": "operator_must_supply_text"}
#
# Exits 0 in both cases. Non-zero only on internal error (no JSON produced).

set -euo pipefail

INPUT="${TASK_INPUT:?TASK_INPUT required}"
TASK_ID="${TASK_ID:?TASK_ID required}"
FACTORY_ROOT="${FACTORY_ROOT:-/factory}"

export FACTORY_ROOT TASK_ID
TASK_INPUT_JSON="$INPUT" python3 - <<'PYEOF'
import json, os, secrets, datetime, sys

factory_root = os.environ["FACTORY_ROOT"]
task_id = os.environ["TASK_ID"]
raw = os.environ.get("TASK_INPUT_JSON", "") or ""

try:
    inp = json.loads(raw) if raw else {}
except Exception:
    inp = {}

text = (inp.get("text") or "").strip() if isinstance(inp, dict) else ""
if not text:
    print(json.dumps({"success": False, "error": "operator_must_supply_text"}))
    sys.exit(0)

source_url = inp.get("source_url") if isinstance(inp, dict) else None
intended_url_substrings = inp.get("intended_url_substrings") if isinstance(inp, dict) else None
if intended_url_substrings is not None and not isinstance(intended_url_substrings, list):
    intended_url_substrings = None

now_dt = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
now_iso = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
stamp = now_dt.strftime("%Y%m%dT%H%M%SZ")
approval_id = f"appr-{stamp}-{secrets.token_hex(2)}"

approvals_dir = os.path.join(factory_root, "approvals")
os.makedirs(approvals_dir, exist_ok=True)
final_path = os.path.join(approvals_dir, f"{approval_id}.json")
tmp_path = final_path + ".tmp"

payload = {"text": text}
if source_url is not None:
    payload["source_url"] = source_url
if intended_url_substrings is not None:
    payload["intended_url_substrings"] = intended_url_substrings

card = {
    "approval_id": approval_id,
    "schema_version": "1",
    "kind": "tweet",
    "status": "pending",
    "source_card_id": task_id,
    "proposed_at_utc": now_iso,
    "decided_at_utc": None,
    "decided_by": None,
    "decision_note": None,
    "payload": payload,
    "resulting_artifact": None,
    "audit_trail": [
        {
            "event": "proposed",
            "at_utc": now_iso,
            "by": "operator-pulse",
            "note": f"{task_id} proposed via propose-tweet",
        }
    ],
}

with open(tmp_path, "w") as f:
    json.dump(card, f, indent=2)
os.rename(tmp_path, final_path)

print(json.dumps({
    "success": True,
    "approval_id": approval_id,
    "approval_path": final_path,
    "approval_status": "pending",
}))
PYEOF
