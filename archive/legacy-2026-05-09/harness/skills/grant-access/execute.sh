#!/usr/bin/env bash
# Skill: grant-access — user-side approval of a pending access-request once the
# secrets file has been installed out-of-band. Verifies the file exists with the
# right permissions and schema, then re-dispatches any approval card that was
# parked in creds_missing waiting on this request.
#
# Inputs (env):
#   REQUEST_ID    — access-request id; <FACTORY_ROOT>/access-requests/<id>.json.
#   FACTORY_ROOT  — root for /factory paths; defaults to /factory.
#   SKILLS_ROOT   — directory containing other skills; defaults to /factory/skills.
#   DRY_RUN       — propagated to post-twitter-real on redispatch.
#
# Side effect: rewrites the access-request (status=granted) and re-dispatches
# any creds_missing approvals tied to this request via post-twitter-real.
#
# Output (stdout, single-line JSON):
#   On success: {"success": true, "request_id": "...", "final_status": "granted",
#                "redispatched_approvals": [...]}
#   On creds_invalid: {"success": false, "error": "creds_invalid", "detail": "..."}
#   On not_pending: {"success": false, "error": "not_pending", "current_status": "..."}
#
# Exits 0. Non-zero only on internal error.

set -euo pipefail

REQUEST_ID="${REQUEST_ID:?REQUEST_ID required}"
FACTORY_ROOT="${FACTORY_ROOT:-/factory}"
SKILLS_ROOT="${SKILLS_ROOT:-/factory/skills}"
DRY_RUN="${DRY_RUN:-}"

export REQUEST_ID FACTORY_ROOT SKILLS_ROOT DRY_RUN
python3 - <<'PYEOF'
import json, os, sys, datetime, glob, stat, subprocess

request_id = os.environ["REQUEST_ID"]
factory_root = os.environ["FACTORY_ROOT"]
skills_root = os.environ["SKILLS_ROOT"]
dry_run = os.environ.get("DRY_RUN", "")

request_path = os.path.join(factory_root, "access-requests", f"{request_id}.json")

REQUIRED_KEYS_BY_FLOW = {
    "social/twitter": {
        "oauth2": ("client_id", "client_secret", "access_token", "refresh_token"),
        "oauth1": ("api_key", "api_key_secret", "access_token", "access_token_secret"),
    },
}

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
    with open(request_path) as f:
        request = json.load(f)
except Exception as e:
    emit({"success": False, "error": "request_unreadable", "detail": str(e)})

if request.get("status") != "pending":
    emit({"success": False, "error": "not_pending", "current_status": request.get("status")})

resource_id = request.get("resource_id") or ""
secrets_filename = resource_id.replace("/", "-") + ".json"
secrets_path = os.path.join(factory_root, "secrets", secrets_filename)

# Verify
if not os.path.exists(secrets_path):
    emit({"success": False, "error": "creds_invalid", "detail": f"secrets file missing at {secrets_path}"})

st = os.stat(secrets_path)
mode = stat.S_IMODE(st.st_mode)
# Be slightly lenient on tests: require not world/group readable. Hard-mode is 0o600.
if mode & 0o077:
    emit({"success": False, "error": "creds_invalid", "detail": f"secrets file mode {oct(mode)} must be 0o600 (no group/world bits)"})

try:
    with open(secrets_path) as f:
        creds = json.load(f)
except Exception as e:
    emit({"success": False, "error": "creds_invalid", "detail": f"secrets file invalid json: {e}"})

flow_keys = REQUIRED_KEYS_BY_FLOW.get(resource_id)
if flow_keys is not None:
    auth_flow = creds.get("auth_flow") or "oauth1"
    required = flow_keys.get(auth_flow)
    if required is None:
        emit({"success": False, "error": "creds_invalid", "detail": f"unknown auth_flow {auth_flow!r}; expected one of {sorted(flow_keys)}"})
    missing = [k for k in required if not creds.get(k)]
    if missing:
        emit({"success": False, "error": "creds_invalid", "detail": f"missing required keys for {auth_flow}: {','.join(missing)}"})

# Mark request granted.
request["status"] = "granted"
request["decided_at_utc"] = now_iso()
request["decision_note"] = request.get("decision_note")
request.setdefault("audit_trail", []).append({
    "event": "granted",
    "at_utc": request["decided_at_utc"],
    "by": "user",
    "note": "creds verified via grant-access",
})
atomic_write(request_path, request)

# Find approvals in creds_missing referencing this request_id.
approvals_dir = os.path.join(factory_root, "approvals")
redispatched = []
if os.path.isdir(approvals_dir):
    for path in sorted(glob.glob(os.path.join(approvals_dir, "*.json"))):
        try:
            with open(path) as f:
                appr = json.load(f)
        except Exception:
            continue
        if appr.get("status") != "creds_missing":
            continue
        audit = appr.get("audit_trail") or []
        if not any(e.get("access_request_id") == request_id for e in audit):
            continue

        # Re-dispatch directly via post-twitter-real (approval is past pending).
        skill_path = os.path.join(skills_root, "post-twitter-real", "execute.sh")
        if not os.path.exists(skill_path):
            repo_skill = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "post-twitter-real", "execute.sh",
            )
            if os.path.exists(repo_skill):
                skill_path = repo_skill

        env = os.environ.copy()
        env["APPROVAL_PATH"] = path
        env["FACTORY_ROOT"] = factory_root
        if dry_run:
            env["DRY_RUN"] = dry_run
        proc = subprocess.run(["bash", skill_path], env=env, capture_output=True, text=True)
        out = (proc.stdout or "").strip().splitlines()
        last = out[-1] if out else ""
        try:
            result = json.loads(last) if last else {}
        except Exception:
            result = {}

        new_status = appr.get("status")
        if result.get("success") is True:
            new_status = "posted"
            appr["status"] = new_status
            appr["resulting_artifact"] = {
                "tweet_id": result.get("tweet_id"),
                "live_url": result.get("live_url"),
                "posted_at_utc": result.get("posted_at_utc"),
            }
            appr.setdefault("audit_trail", []).append({
                "event": "posted",
                "at_utc": now_iso(),
                "by": "grant-access",
                "tweet_id": result.get("tweet_id"),
                "live_url": result.get("live_url"),
                "redispatched_from_request_id": request_id,
            })
        elif result.get("error") == "creds_missing":
            new_status = "creds_missing"
            appr.setdefault("audit_trail", []).append({
                "event": "creds_missing",
                "at_utc": now_iso(),
                "by": "grant-access",
                "access_request_id": result.get("access_request_id"),
                "access_request_path": result.get("access_request_path"),
                "note": "redispatch still failing creds check",
            })
        elif result.get("error") == "api_error":
            new_status = "post_failed"
            appr["status"] = new_status
            appr.setdefault("audit_trail", []).append({
                "event": "post_failed",
                "at_utc": now_iso(),
                "by": "grant-access",
                "http_status": result.get("http_status"),
                "body_excerpt": result.get("body_excerpt"),
            })
        else:
            new_status = "post_failed"
            appr["status"] = new_status
            appr.setdefault("audit_trail", []).append({
                "event": "post_failed",
                "at_utc": now_iso(),
                "by": "grant-access",
                "note": "post-twitter-real returned unrecognized output",
                "raw": last[:200],
            })

        atomic_write(path, appr)
        redispatched.append({
            "approval_id": appr.get("approval_id"),
            "final_status": new_status,
        })

emit({
    "success": True,
    "request_id": request_id,
    "final_status": "granted",
    "redispatched_approvals": redispatched,
})
PYEOF
