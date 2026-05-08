#!/usr/bin/env bash
# Skill: reject-action — user-side rejection of a pending action card.
#
# Inputs (env):
#   APPROVAL_ID    — approval id; the file is <FACTORY_ROOT>/approvals/<id>.json.
#   DECISION_NOTE  — optional free text recorded in audit + decision_note.
#   FACTORY_ROOT   — root for /factory paths; defaults to /factory.
#
# Side effect: rewrites the approval card (atomic rename) with status=rejected.
#
# Output (stdout, single-line JSON):
#   On success: {"success": true, "approval_id": "...", "final_status": "rejected"}
#   On not_pending: {"success": false, "error": "not_pending", "current_status": "..."}
#
# Exits 0. Non-zero only on internal error.

set -euo pipefail

APPROVAL_ID="${APPROVAL_ID:?APPROVAL_ID required}"
DECISION_NOTE="${DECISION_NOTE:-}"
FACTORY_ROOT="${FACTORY_ROOT:-/factory}"

export APPROVAL_ID DECISION_NOTE FACTORY_ROOT
python3 - <<'PYEOF'
import json, os, sys, datetime

approval_id = os.environ["APPROVAL_ID"]
decision_note = os.environ.get("DECISION_NOTE", "") or None
factory_root = os.environ["FACTORY_ROOT"]
approval_path = os.path.join(factory_root, "approvals", f"{approval_id}.json")

def emit(obj):
    print(json.dumps(obj))
    sys.exit(0)

try:
    with open(approval_path) as f:
        approval = json.load(f)
except Exception as e:
    emit({"success": False, "error": "approval_unreadable", "detail": str(e)})

if approval.get("status") != "pending":
    emit({"success": False, "error": "not_pending", "current_status": approval.get("status")})

now_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
approval["status"] = "rejected"
approval["decided_at_utc"] = now_iso
approval["decided_by"] = "user"
approval["decision_note"] = decision_note
approval.setdefault("audit_trail", []).append({
    "event": "rejected",
    "at_utc": now_iso,
    "by": "user",
    "note": decision_note,
})

tmp = approval_path + ".tmp"
with open(tmp, "w") as f:
    json.dump(approval, f, indent=2)
os.rename(tmp, approval_path)

emit({"success": True, "approval_id": approval_id, "final_status": "rejected"})
PYEOF
