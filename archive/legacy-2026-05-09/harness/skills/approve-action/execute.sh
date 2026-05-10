#!/usr/bin/env bash
# Skill: approve-action — user-side approval of a pending action card.
#
# Inputs (env):
#   APPROVAL_ID    — approval id; the file is <FACTORY_ROOT>/approvals/<id>.json.
#   DECISION_NOTE  — optional free text recorded in audit + decision_note.
#   FACTORY_ROOT   — root for /factory paths; defaults to /factory.
#   SKILLS_ROOT    — directory containing other skills; defaults to /factory/skills.
#                    Used to resolve post-twitter-real for tweet kind dispatch.
#
# Side effect: rewrites the approval card (atomic rename) with the new status,
# decided_at_utc, decision_note, and audit-trail entries. For tweet kind, also
# invokes post-twitter-real, which may write an access-request file.
#
# Output (stdout, single-line JSON):
#   On success: {"success": true, "approval_id": "...", "final_status": "...",
#                "resulting_artifact": {...}|null, "access_request_id": null|"..."}
#   On not_pending: {"success": false, "error": "not_pending", "current_status": "..."}
#
# Exits 0. Non-zero only on internal error.

set -euo pipefail

APPROVAL_ID="${APPROVAL_ID:?APPROVAL_ID required}"
DECISION_NOTE="${DECISION_NOTE:-}"
FACTORY_ROOT="${FACTORY_ROOT:-/factory}"
SKILLS_ROOT="${SKILLS_ROOT:-/factory/skills}"

export APPROVAL_ID DECISION_NOTE FACTORY_ROOT SKILLS_ROOT
python3 - <<'PYEOF'
import json, os, sys, datetime, subprocess

approval_id = os.environ["APPROVAL_ID"]
decision_note = os.environ.get("DECISION_NOTE", "") or None
factory_root = os.environ["FACTORY_ROOT"]
skills_root = os.environ["SKILLS_ROOT"]

approval_path = os.path.join(factory_root, "approvals", f"{approval_id}.json")

def emit(obj):
    print(json.dumps(obj))
    sys.exit(0)

def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def atomic_write(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2)
    os.rename(tmp, path)

try:
    with open(approval_path) as f:
        approval = json.load(f)
except Exception as e:
    emit({"success": False, "error": "approval_unreadable", "detail": str(e)})

current_status = approval.get("status")
if current_status != "pending":
    emit({"success": False, "error": "not_pending", "current_status": current_status})

# Mark as approved.
approval["status"] = "approved"
approval["decided_at_utc"] = now_iso()
approval["decided_by"] = "user"
approval["decision_note"] = decision_note
approval.setdefault("audit_trail", []).append({
    "event": "approved",
    "at_utc": approval["decided_at_utc"],
    "by": "user",
    "note": decision_note,
})
atomic_write(approval_path, approval)

kind = approval.get("kind")
final_status = "approved"
resulting_artifact = None
access_request_id = None

if kind == "tweet":
    skill_path = os.path.join(skills_root, "post-twitter-real", "execute.sh")
    if not os.path.exists(skill_path):
        # Try fallback to repo-local harness path (for tests / pre-deploy).
        repo_skill = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "post-twitter-real", "execute.sh")
        if os.path.exists(repo_skill):
            skill_path = repo_skill

    env = os.environ.copy()
    env["APPROVAL_PATH"] = approval_path
    env["FACTORY_ROOT"] = factory_root
    proc = subprocess.run(
        ["bash", skill_path],
        env=env, capture_output=True, text=True,
    )
    out = (proc.stdout or "").strip().splitlines()
    last = out[-1] if out else ""
    try:
        result = json.loads(last) if last else {}
    except Exception:
        result = {}

    if result.get("success") is True:
        final_status = "posted"
        resulting_artifact = {
            "tweet_id": result.get("tweet_id"),
            "live_url": result.get("live_url"),
            "posted_at_utc": result.get("posted_at_utc"),
        }
        approval["status"] = final_status
        approval["resulting_artifact"] = resulting_artifact
        approval["audit_trail"].append({
            "event": "posted",
            "at_utc": now_iso(),
            "by": "approve-action",
            "tweet_id": resulting_artifact["tweet_id"],
            "live_url": resulting_artifact["live_url"],
        })
    elif result.get("error") == "creds_missing":
        final_status = "creds_missing"
        access_request_id = result.get("access_request_id")
        approval["status"] = final_status
        approval["audit_trail"].append({
            "event": "creds_missing",
            "at_utc": now_iso(),
            "by": "approve-action",
            "access_request_id": access_request_id,
            "access_request_path": result.get("access_request_path"),
        })
    elif result.get("error") == "api_error":
        final_status = "post_failed"
        approval["status"] = final_status
        approval["audit_trail"].append({
            "event": "post_failed",
            "at_utc": now_iso(),
            "by": "approve-action",
            "http_status": result.get("http_status"),
            "body_excerpt": result.get("body_excerpt"),
        })
    else:
        # Unknown skill output — record as post_failed.
        final_status = "post_failed"
        approval["status"] = final_status
        approval["audit_trail"].append({
            "event": "post_failed",
            "at_utc": now_iso(),
            "by": "approve-action",
            "note": "post-twitter-real returned unrecognized output",
            "raw": last[:200],
        })

    atomic_write(approval_path, approval)
else:
    approval["audit_trail"].append({
        "event": "no_dispatcher",
        "at_utc": now_iso(),
        "by": "approve-action",
        "note": f"approve-action: no dispatcher for kind={kind}",
    })
    atomic_write(approval_path, approval)

emit({
    "success": True,
    "approval_id": approval_id,
    "final_status": final_status,
    "resulting_artifact": resulting_artifact,
    "access_request_id": access_request_id,
})
PYEOF
