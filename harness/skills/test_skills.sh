#!/usr/bin/env bash
# Test harness for the approval-flow skills.
#
# Verifies all 5 skills in a temp FACTORY_ROOT (no /factory writes). Prints
# `ERROR: ...` lines on failure and exits non-zero on any failure. Silent on
# pass except for a final summary.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SKILLS_DIR="$REPO_ROOT/harness/skills"

TMPROOT="$(mktemp -d -t skills-test-XXXXXX)"
export FACTORY_ROOT="$TMPROOT/factory"
export SKILLS_ROOT="$SKILLS_DIR"
mkdir -p "$FACTORY_ROOT/approvals" "$FACTORY_ROOT/access-requests" "$FACTORY_ROOT/secrets"

FAIL=0
TESTS_RUN=0

cleanup() {
    rm -rf "$TMPROOT"
}
trap cleanup EXIT

fail() {
    echo "ERROR: $1" >&2
    FAIL=$((FAIL + 1))
}

assert_eq() {
    # $1=label $2=expected $3=actual
    if [ "$2" != "$3" ]; then
        fail "$1: expected '$2' got '$3'"
    fi
}

# Read JSON field via python (simpler than jq dependency).
jget() {
    # $1=json $2=dotted.path
    python3 -c "
import json, sys
d = json.loads(sys.argv[1])
for k in sys.argv[2].split('.'):
    if isinstance(d, list):
        d = d[int(k)]
    else:
        d = d.get(k) if isinstance(d, dict) else None
    if d is None:
        break
print('' if d is None else d if isinstance(d, str) else json.dumps(d))
" "$1" "$2"
}

run_test() {
    TESTS_RUN=$((TESTS_RUN + 1))
}

# Reset per-test state (clear approvals/access-requests/secrets).
reset_factory() {
    rm -rf "$FACTORY_ROOT"
    mkdir -p "$FACTORY_ROOT/approvals" "$FACTORY_ROOT/access-requests" "$FACTORY_ROOT/secrets"
}

install_creds() {
    # Both post-twitter-real and grant-access read /factory/secrets/<resource_id
    # with / replaced by ->.json — social/twitter → social-twitter.json.
    # Default test creds use OAuth 2.0 (matches prod). Override with
    # CRED_FLAVOR=oauth1 to install legacy creds for the OAuth 1.0a path.
    local flavor="${CRED_FLAVOR:-oauth2}"
    local body
    if [ "$flavor" = "oauth2" ]; then
        body='{"schema_version":"1","auth_flow":"oauth2","client_id":"ci","client_secret":"cs","access_token":"at","refresh_token":"rt"}'
    else
        body='{"schema_version":"1","auth_flow":"oauth1","api_key":"k","api_key_secret":"ks","access_token":"t","access_token_secret":"ts"}'
    fi
    printf '%s\n' "$body" > "$FACTORY_ROOT/secrets/social-twitter.json"
    chmod 600 "$FACTORY_ROOT/secrets/social-twitter.json"
}

# ---- TEST 1: propose-tweet with valid input ----
run_test
reset_factory
OUT=$(TASK_INPUT='{"text":"hello world","source_url":"https://example.com"}' TASK_ID="card-001" \
    bash "$SKILLS_DIR/propose-tweet/execute.sh")
ok=$(jget "$OUT" success)
status=$(jget "$OUT" approval_status)
appr_id=$(jget "$OUT" approval_id)
appr_path=$(jget "$OUT" approval_path)
assert_eq "T1 success" "true" "$ok"
assert_eq "T1 status" "pending" "$status"
case "$appr_id" in appr-*) ;; *) fail "T1 approval_id format: $appr_id" ;; esac
[ -f "$appr_path" ] || fail "T1 approval file not created at $appr_path"
text_in_file=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['payload']['text'])" "$appr_path" 2>/dev/null || echo "")
assert_eq "T1 file text" "hello world" "$text_in_file"

# ---- TEST 2: propose-tweet empty text ----
run_test
reset_factory
OUT=$(TASK_INPUT='{"text":""}' TASK_ID="card-002" \
    bash "$SKILLS_DIR/propose-tweet/execute.sh")
ok=$(jget "$OUT" success)
err=$(jget "$OUT" error)
assert_eq "T2 success" "false" "$ok"
assert_eq "T2 error" "operator_must_supply_text" "$err"
N=$(ls "$FACTORY_ROOT/approvals" 2>/dev/null | wc -l | tr -d ' ')
assert_eq "T2 no file" "0" "$N"

# ---- TEST 3: approve-action on tweet pending, creds present + DRY_RUN=1 ----
run_test
reset_factory
install_creds
OUT=$(TASK_INPUT='{"text":"tweet for approval"}' TASK_ID="card-003" \
    bash "$SKILLS_DIR/propose-tweet/execute.sh")
appr_id=$(jget "$OUT" approval_id)
appr_path=$(jget "$OUT" approval_path)
OUT=$(APPROVAL_ID="$appr_id" DRY_RUN=1 \
    bash "$SKILLS_DIR/approve-action/execute.sh")
ok=$(jget "$OUT" success)
final=$(jget "$OUT" final_status)
artifact=$(jget "$OUT" resulting_artifact)
assert_eq "T3 success" "true" "$ok"
assert_eq "T3 final_status" "posted" "$final"
if [ -z "$artifact" ] || [ "$artifact" = "null" ]; then
    fail "T3 resulting_artifact missing"
fi
file_status=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['status'])" "$appr_path")
assert_eq "T3 file status" "posted" "$file_status"

# ---- TEST 4: approve-action no creds → creds_missing + access-request file ----
run_test
reset_factory
OUT=$(TASK_INPUT='{"text":"another tweet"}' TASK_ID="card-004" \
    bash "$SKILLS_DIR/propose-tweet/execute.sh")
appr_id=$(jget "$OUT" approval_id)
appr_path=$(jget "$OUT" approval_path)
OUT=$(APPROVAL_ID="$appr_id" \
    bash "$SKILLS_DIR/approve-action/execute.sh")
ok=$(jget "$OUT" success)
final=$(jget "$OUT" final_status)
accr_id=$(jget "$OUT" access_request_id)
assert_eq "T4 success" "true" "$ok"
assert_eq "T4 final_status" "creds_missing" "$final"
case "$accr_id" in accr-*) ;; *) fail "T4 access_request_id format: '$accr_id'" ;; esac
[ -f "$FACTORY_ROOT/access-requests/$accr_id.json" ] || fail "T4 access-request file missing"
audit_has=$(python3 -c "
import json,sys
appr=json.load(open(sys.argv[1]))
ev=[e for e in appr.get('audit_trail',[]) if e.get('event')=='creds_missing']
print('1' if ev and ev[0].get('access_request_id')==sys.argv[2] else '0')
" "$appr_path" "$accr_id")
assert_eq "T4 audit has creds_missing" "1" "$audit_has"

# ---- TEST 5: reject-action on pending ----
run_test
reset_factory
OUT=$(TASK_INPUT='{"text":"reject me"}' TASK_ID="card-005" \
    bash "$SKILLS_DIR/propose-tweet/execute.sh")
appr_id=$(jget "$OUT" approval_id)
appr_path=$(jget "$OUT" approval_path)
OUT=$(APPROVAL_ID="$appr_id" DECISION_NOTE="too salesy" \
    bash "$SKILLS_DIR/reject-action/execute.sh")
ok=$(jget "$OUT" success)
final=$(jget "$OUT" final_status)
assert_eq "T5 success" "true" "$ok"
assert_eq "T5 final" "rejected" "$final"
file_status=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['status'])" "$appr_path")
assert_eq "T5 file status" "rejected" "$file_status"

# ---- TEST 6: reject-action on already-rejected ----
run_test
OUT=$(APPROVAL_ID="$appr_id" \
    bash "$SKILLS_DIR/reject-action/execute.sh")
ok=$(jget "$OUT" success)
err=$(jget "$OUT" error)
cur=$(jget "$OUT" current_status)
assert_eq "T6 success" "false" "$ok"
assert_eq "T6 error" "not_pending" "$err"
assert_eq "T6 current_status" "rejected" "$cur"

# ---- TEST 7: grant-access valid ----
run_test
reset_factory
# Need an access-request to grant. Create one by running approve-action with no creds.
OUT=$(TASK_INPUT='{"text":"grant test"}' TASK_ID="card-007" \
    bash "$SKILLS_DIR/propose-tweet/execute.sh")
appr_id=$(jget "$OUT" approval_id)
OUT=$(APPROVAL_ID="$appr_id" \
    bash "$SKILLS_DIR/approve-action/execute.sh")
accr_id=$(jget "$OUT" access_request_id)
# Now install creds and grant.
install_creds
OUT=$(REQUEST_ID="$accr_id" DRY_RUN=1 \
    bash "$SKILLS_DIR/grant-access/execute.sh")
ok=$(jget "$OUT" success)
final=$(jget "$OUT" final_status)
assert_eq "T7 success" "true" "$ok"
assert_eq "T7 final" "granted" "$final"
req_path="$FACTORY_ROOT/access-requests/$accr_id.json"
req_status=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['status'])" "$req_path")
assert_eq "T7 file status" "granted" "$req_status"

# ---- TEST 8: grant-access missing creds → creds_invalid, request still pending ----
run_test
reset_factory
OUT=$(TASK_INPUT='{"text":"grant fail"}' TASK_ID="card-008" \
    bash "$SKILLS_DIR/propose-tweet/execute.sh")
appr_id=$(jget "$OUT" approval_id)
OUT=$(APPROVAL_ID="$appr_id" \
    bash "$SKILLS_DIR/approve-action/execute.sh")
accr_id=$(jget "$OUT" access_request_id)
# No creds installed.
OUT=$(REQUEST_ID="$accr_id" \
    bash "$SKILLS_DIR/grant-access/execute.sh")
ok=$(jget "$OUT" success)
err=$(jget "$OUT" error)
assert_eq "T8 success" "false" "$ok"
assert_eq "T8 error" "creds_invalid" "$err"
req_path="$FACTORY_ROOT/access-requests/$accr_id.json"
req_status=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['status'])" "$req_path")
assert_eq "T8 still pending" "pending" "$req_status"

# ---- TEST 9: grant-access redispatches creds_missing approval ----
run_test
reset_factory
OUT=$(TASK_INPUT='{"text":"redispatch me"}' TASK_ID="card-009" \
    bash "$SKILLS_DIR/propose-tweet/execute.sh")
appr_id=$(jget "$OUT" approval_id)
appr_path=$(jget "$OUT" approval_path)
OUT=$(APPROVAL_ID="$appr_id" \
    bash "$SKILLS_DIR/approve-action/execute.sh")
accr_id=$(jget "$OUT" access_request_id)
file_status=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['status'])" "$appr_path")
assert_eq "T9 pre status" "creds_missing" "$file_status"
install_creds
OUT=$(REQUEST_ID="$accr_id" DRY_RUN=1 \
    bash "$SKILLS_DIR/grant-access/execute.sh")
ok=$(jget "$OUT" success)
final=$(jget "$OUT" final_status)
redispatched=$(jget "$OUT" redispatched_approvals)
assert_eq "T9 grant success" "true" "$ok"
assert_eq "T9 grant final" "granted" "$final"
file_status=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['status'])" "$appr_path")
assert_eq "T9 approval flipped" "posted" "$file_status"
# Verify the redispatched_approvals list mentions our approval id.
hit=$(python3 -c "
import json,sys
data=json.loads(sys.argv[1])
print('1' if any(d.get('approval_id')==sys.argv[2] and d.get('final_status')=='posted' for d in data) else '0')
" "$redispatched" "$appr_id" 2>/dev/null || echo 0)
assert_eq "T9 redispatched list" "1" "$hit"

if [ "$FAIL" -eq 0 ]; then
    echo "OK: $TESTS_RUN/9 tests passed"
    exit 0
else
    echo "FAIL: $FAIL failure(s) across $TESTS_RUN tests" >&2
    exit 1
fi
