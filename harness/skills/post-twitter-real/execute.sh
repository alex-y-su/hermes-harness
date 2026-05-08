#!/usr/bin/env bash
# Skill: post-twitter-real — invoked ONLY by approve-action, never by a card
# pipeline directly. Posts the tweet to the real Twitter API v2 (or, with
# DRY_RUN=1, simulates a successful post for tests).
#
# Inputs (env):
#   APPROVAL_PATH — full path to the approval-card JSON on disk (kind=tweet).
#   DRY_RUN       — if set to "1", do NOT call Twitter; return a fake tweet_id.
#   FACTORY_ROOT  — root for /factory paths; defaults to /factory.
#
# Side effect (creds_missing case): writes
# <FACTORY_ROOT>/access-requests/<request_id>.json with the structured request.
#
# Output (stdout, single-line JSON):
#   On success: {"success": true, "tweet_id": "...", "live_url": "...", "posted_at_utc": "..."}
#   On creds_missing: {"success": false, "error": "creds_missing", "access_request_id": "...", "access_request_path": "..."}
#   On API error: {"success": false, "error": "api_error", "http_status": <n>, "body_excerpt": "..."}
#
# Exits 0 in all cases above. Non-zero only on internal error.

set -euo pipefail

APPROVAL_PATH="${APPROVAL_PATH:?APPROVAL_PATH required}"
FACTORY_ROOT="${FACTORY_ROOT:-/factory}"
DRY_RUN="${DRY_RUN:-}"

export APPROVAL_PATH FACTORY_ROOT DRY_RUN
python3 - <<'PYEOF'
import json, os, sys, secrets, datetime, time

approval_path = os.environ["APPROVAL_PATH"]
factory_root = os.environ["FACTORY_ROOT"]
dry_run = os.environ.get("DRY_RUN", "") == "1"

def emit(obj):
    print(json.dumps(obj))
    sys.exit(0)

try:
    with open(approval_path) as f:
        approval = json.load(f)
except Exception as e:
    emit({"success": False, "error": "approval_unreadable", "detail": str(e)})

approval_id = approval.get("approval_id", "")
text = ""
if isinstance(approval.get("payload"), dict):
    text = (approval["payload"].get("text") or "").strip()

secrets_path = os.path.join(factory_root, "secrets", "social-twitter.json")
required_keys = ("api_key", "api_key_secret", "access_token", "access_token_secret")

def raise_access_request(reason):
    now_dt = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    now_iso = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    stamp = now_dt.strftime("%Y%m%dT%H%M%SZ")
    rid = f"accr-{stamp}-{secrets.token_hex(2)}"
    req_dir = os.path.join(factory_root, "access-requests")
    os.makedirs(req_dir, exist_ok=True)
    final_path = os.path.join(req_dir, f"{rid}.json")
    tmp_path = final_path + ".tmp"
    req = {
        "request_id": rid,
        "schema_version": "1",
        "kind": "credentials",
        "status": "pending",
        "resource_id": "social/twitter",
        "requested_at_utc": now_iso,
        "decided_at_utc": None,
        "what_we_need": (
            "Twitter API v2 OAuth 1.0a user-context credentials so post-twitter-real "
            "can post on behalf of @roomcord. Required keys: api_key, api_key_secret, "
            f"access_token, access_token_secret. Install at {secrets_path} (chmod 600, owner dev)."
        ),
        "why": (
            "approval card was approved for posting but post-twitter-real "
            f"returned creds_missing ({reason})."
        ),
        "blocking_approval_id": approval_id,
        "decision_note": None,
        "audit_trail": [
            {
                "event": "requested",
                "at_utc": now_iso,
                "by": "post-twitter-real",
                "note": f"raised due to: {reason}",
            }
        ],
    }
    with open(tmp_path, "w") as f:
        json.dump(req, f, indent=2)
    os.rename(tmp_path, final_path)
    return rid, final_path

# Check creds file
creds = None
reason = None
if not os.path.exists(secrets_path):
    reason = "secrets file missing"
else:
    try:
        with open(secrets_path) as f:
            creds = json.load(f)
    except Exception as e:
        reason = f"secrets file invalid json: {e}"
    if creds is not None:
        missing = [k for k in required_keys if not creds.get(k)]
        if missing:
            reason = f"missing required keys: {','.join(missing)}"
            creds = None

if creds is None:
    rid, path = raise_access_request(reason or "unknown")
    emit({
        "success": False,
        "error": "creds_missing",
        "access_request_id": rid,
        "access_request_path": path,
    })

# Creds present.
posted_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

if dry_run:
    tweet_id = f"dryrun-{int(time.time())}-{secrets.token_hex(2)}"
    emit({
        "success": True,
        "tweet_id": tweet_id,
        "live_url": f"https://twitter.com/dryrun/status/{tweet_id}",
        "posted_at_utc": posted_at,
    })

# Real post path. Try requests_oauthlib first.
try:
    import requests
    from requests_oauthlib import OAuth1
    auth = OAuth1(
        creds["api_key"], creds["api_key_secret"],
        creds["access_token"], creds["access_token_secret"],
    )
    resp = requests.post(
        "https://api.twitter.com/2/tweets",
        json={"text": text},
        auth=auth,
        timeout=30,
    )
    status = resp.status_code
    body = resp.text or ""
    if status == 201:
        try:
            tweet_id = resp.json()["data"]["id"]
        except Exception as e:
            emit({"success": False, "error": "api_error", "http_status": status, "body_excerpt": (body[:200] + f" | parse err: {e}")[:200]})
        emit({
            "success": True,
            "tweet_id": str(tweet_id),
            "live_url": f"https://twitter.com/i/web/status/{tweet_id}",
            "posted_at_utc": posted_at,
        })
    else:
        emit({"success": False, "error": "api_error", "http_status": status, "body_excerpt": body[:200]})
except ImportError:
    pass

# Fallback: pure-stdlib OAuth1 signing.
import urllib.parse, urllib.request, hmac, hashlib, base64, uuid

def percent(s):
    return urllib.parse.quote(str(s), safe="")

def oauth1_post_tweets(creds_, text_):
    url = "https://api.twitter.com/2/tweets"
    method = "POST"
    body = json.dumps({"text": text_}).encode("utf-8")
    oauth_params = {
        "oauth_consumer_key": creds_["api_key"],
        "oauth_nonce": uuid.uuid4().hex,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": creds_["access_token"],
        "oauth_version": "1.0",
    }
    # For JSON body POSTs, body params are NOT included in signature base.
    sorted_params = sorted(oauth_params.items())
    param_str = "&".join(f"{percent(k)}={percent(v)}" for k, v in sorted_params)
    base = f"{method}&{percent(url)}&{percent(param_str)}"
    signing_key = f"{percent(creds_['api_key_secret'])}&{percent(creds_['access_token_secret'])}"
    sig = base64.b64encode(
        hmac.new(signing_key.encode(), base.encode(), hashlib.sha1).digest()
    ).decode()
    oauth_params["oauth_signature"] = sig
    auth_header = "OAuth " + ", ".join(
        f'{percent(k)}="{percent(v)}"' for k, v in sorted(oauth_params.items())
    )
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Authorization": auth_header, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            status = resp.getcode()
            rbody = resp.read().decode("utf-8", errors="replace")
            return status, rbody
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")

status, body = oauth1_post_tweets(creds, text)
if status == 201:
    try:
        tweet_id = json.loads(body)["data"]["id"]
    except Exception as e:
        emit({"success": False, "error": "api_error", "http_status": status, "body_excerpt": (body[:160] + f" | parse err: {e}")[:200]})
    emit({
        "success": True,
        "tweet_id": str(tweet_id),
        "live_url": f"https://twitter.com/i/web/status/{tweet_id}",
        "posted_at_utc": posted_at,
    })
else:
    emit({"success": False, "error": "api_error", "http_status": status, "body_excerpt": body[:200]})
PYEOF
