#!/usr/bin/env bash
# Skill: post-twitter-real — invoked ONLY by approve-action, never by a card
# pipeline directly. Posts the tweet to the real Twitter API v2 (or, with
# DRY_RUN=1, simulates a successful post for tests).
#
# Supports two auth flows determined by `auth_flow` field in the creds file:
#   - "oauth2" (default for new creds): Bearer-token auth with refresh-on-401.
#     Required keys: client_id, client_secret, access_token, refresh_token.
#   - "oauth1": OAuth 1.0a user context. Required keys: api_key, api_key_secret,
#     access_token, access_token_secret.
# If `auth_flow` is absent, oauth1 is assumed (backward compat with older creds).
#
# Inputs (env):
#   APPROVAL_PATH — full path to the approval-card JSON on disk (kind=tweet).
#   DRY_RUN       — if set to "1", do NOT call Twitter; return a fake tweet_id.
#   FACTORY_ROOT  — root for /factory paths; defaults to /factory.
#
# Side effect (creds_missing case): writes
# <FACTORY_ROOT>/access-requests/<request_id>.json with the structured request.
# Side effect (oauth2 refresh): on 401, refreshes the token and atomic-rewrites
# the creds file with the new access_token (+ refresh_token if rotated).
#
# Output (stdout, single-line JSON):
#   On success: {"success": true, "tweet_id": "...", "live_url": "...", "posted_at_utc": "..."}
#   On creds_missing: {"success": false, "error": "creds_missing", "access_request_id": "...", "access_request_path": "..."}
#   On API error: {"success": false, "error": "api_error", "http_status": <n>, "body_excerpt": "..."}
#   On refresh failure: {"success": false, "error": "refresh_failed", "http_status": <n>, "body_excerpt": "..."}
#
# Exits 0 in all cases above. Non-zero only on internal error.

set -euo pipefail

APPROVAL_PATH="${APPROVAL_PATH:?APPROVAL_PATH required}"
FACTORY_ROOT="${FACTORY_ROOT:-/factory}"
DRY_RUN="${DRY_RUN:-}"

export APPROVAL_PATH FACTORY_ROOT DRY_RUN
python3 - <<'PYEOF'
import json, os, sys, secrets, datetime, time
import urllib.parse, urllib.request, urllib.error, base64

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

REQUIRED_KEYS_OAUTH2 = ("client_id", "client_secret", "access_token", "refresh_token")
REQUIRED_KEYS_OAUTH1 = ("api_key", "api_key_secret", "access_token", "access_token_secret")

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
            "Twitter API v2 credentials so post-twitter-real can post on behalf "
            "of @roomcord. OAuth 2.0 with PKCE preferred (keys: client_id, "
            "client_secret, access_token, refresh_token, plus auth_flow=oauth2). "
            "OAuth 1.0a also accepted (keys: api_key, api_key_secret, "
            "access_token, access_token_secret). Install at "
            f"{secrets_path} (chmod 600, owner dev)."
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

# Read + validate creds.
creds = None
reason = None
auth_flow = None
if not os.path.exists(secrets_path):
    reason = "secrets file missing"
else:
    try:
        with open(secrets_path) as f:
            creds = json.load(f)
    except Exception as e:
        reason = f"secrets file invalid json: {e}"
    if creds is not None:
        auth_flow = creds.get("auth_flow") or "oauth1"
        if auth_flow == "oauth2":
            required_keys = REQUIRED_KEYS_OAUTH2
        elif auth_flow == "oauth1":
            required_keys = REQUIRED_KEYS_OAUTH1
        else:
            reason = f"unknown auth_flow: {auth_flow!r}"
            creds = None
            required_keys = ()
        if creds is not None:
            missing = [k for k in required_keys if not creds.get(k)]
            if missing:
                reason = f"missing required keys for {auth_flow}: {','.join(missing)}"
                creds = None

if creds is None:
    rid, path = raise_access_request(reason or "unknown")
    emit({
        "success": False,
        "error": "creds_missing",
        "access_request_id": rid,
        "access_request_path": path,
    })

posted_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

if dry_run:
    tweet_id = f"dryrun-{int(time.time())}-{secrets.token_hex(2)}"
    emit({
        "success": True,
        "tweet_id": tweet_id,
        "live_url": f"https://twitter.com/dryrun/status/{tweet_id}",
        "posted_at_utc": posted_at,
    })

# ---- OAuth 2.0 path ----------------------------------------------------------

def atomic_rewrite_creds(new_creds):
    tmp = secrets_path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(new_creds, f, indent=2)
    os.chmod(tmp, 0o600)
    os.rename(tmp, secrets_path)

def http_post(url, body, headers, timeout=30):
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.getcode(), resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")

def post_oauth2_tweet(token):
    return http_post(
        "https://api.twitter.com/2/tweets",
        body=json.dumps({"text": text}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )

def refresh_oauth2():
    basic = base64.b64encode(
        f"{creds['client_id']}:{creds['client_secret']}".encode()
    ).decode()
    return http_post(
        "https://api.twitter.com/2/oauth2/token",
        body=urllib.parse.urlencode({
            "grant_type": "refresh_token",
            "refresh_token": creds["refresh_token"],
            "client_id": creds["client_id"],
        }).encode("utf-8"),
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )

if auth_flow == "oauth2":
    status, body = post_oauth2_tweet(creds["access_token"])
    if status == 401:
        rstatus, rbody = refresh_oauth2()
        if rstatus != 200:
            emit({"success": False, "error": "refresh_failed", "http_status": rstatus, "body_excerpt": rbody[:200]})
        try:
            new_token = json.loads(rbody)
        except Exception as e:
            emit({"success": False, "error": "refresh_failed", "http_status": rstatus, "body_excerpt": f"refresh body parse err: {e}"[:200]})
        creds["access_token"] = new_token.get("access_token") or creds["access_token"]
        if new_token.get("refresh_token"):
            creds["refresh_token"] = new_token["refresh_token"]
        atomic_rewrite_creds(creds)
        status, body = post_oauth2_tweet(creds["access_token"])
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
    emit({"success": False, "error": "api_error", "http_status": status, "body_excerpt": body[:200]})

# ---- OAuth 1.0a path (legacy / fallback) -------------------------------------

import hmac, hashlib, uuid

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
    return http_post(url, body=body, headers={
        "Authorization": auth_header,
        "Content-Type": "application/json",
    })

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
emit({"success": False, "error": "api_error", "http_status": status, "body_excerpt": body[:200]})
PYEOF
