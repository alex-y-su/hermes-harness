# Approval flow & user-reply intake — contract

This document is the single source of truth for the approval / access-request / inbox redesign. Validators, skills, prompt steps, and tests all reference these shapes.

## Why

Until now, the boss-team posted tweets to a mock JSON file and marked cards "done". To move to real-but-supervised distribution we need:

1. A **pending approvals queue** so every real-world action (tweet, email, ad) goes through human approval before posting.
2. A **credential / access requests queue** so when the bot needs API creds it can ask for them with structured context.
3. A **free-form inbox** the user replies into; the boss-team parses replies and acts.
4. A **diversity gate** so the operator stops drafting near-identical cards.

The verifiable-outcome card model is preserved — a tweet card's `done` now means *queued for approval*, with the approval-card path as the locator. The reviewer verifies the approval file exists and contains the right text.

## Collections

### `/factory/approvals/<approval_id>.json` — pending action approvals

```json
{
  "approval_id": "appr-20260508T220045Z-7bcb",
  "schema_version": "1",
  "kind": "tweet",
  "status": "pending",
  "source_card_id": "card-...",
  "proposed_at_utc": "2026-05-08T22:00:45Z",
  "decided_at_utc": null,
  "decided_by": null,
  "decision_note": null,
  "payload": {
    "text": "the actual tweet body, <=240 chars",
    "intended_url_substrings": ["https://roomcord.com/blog/...", "Jesuscord"]
  },
  "resulting_artifact": null,
  "audit_trail": [
    {"event": "proposed", "at_utc": "2026-05-08T22:00:45Z", "by": "operator-pulse", "note": "card-XYZ proposed via propose-tweet"}
  ]
}
```

**Status transitions:**
- `pending` → `approved` (user said yes; about to attempt the side effect)
- `approved` → `posted` (side effect succeeded; resulting_artifact populated)
- `approved` → `post_failed` (side effect attempted and failed; audit_trail has why)
- `approved` → `creds_missing` (side effect blocked by missing creds; access-request raised; will retry when creds granted)
- `pending` → `rejected` (user said no)

`status="posted"` is terminal-success. `status in {rejected, post_failed}` is terminal-fail. `creds_missing` is recoverable.

`kind` is **free-text**. Examples: `tweet`, `email`, `paid_ad`, `discord_announcement`. No closed enum — keep the system dynamic.

**ID format:** `appr-<utc-iso>-<4-hex>` (e.g. `appr-20260508T220045Z-7bcb`). Filename matches.

### `/factory/access-requests/<request_id>.json` — bot requests for creds/access

```json
{
  "request_id": "accr-20260508T220123Z-3f2a",
  "schema_version": "1",
  "kind": "credentials",
  "status": "pending",
  "resource_id": "social/twitter",
  "requested_at_utc": "2026-05-08T22:01:23Z",
  "decided_at_utc": null,
  "what_we_need": "Twitter API v2 OAuth 1.0a user-context credentials so post-twitter-real can post on behalf of @roomcord. Required keys: api_key, api_key_secret, access_token, access_token_secret. Install at /factory/secrets/social-twitter.json (chmod 600, owner dev).",
  "why": "approval card appr-XYZ was approved for posting but post-twitter-real returned creds_missing.",
  "blocking_approval_id": "appr-20260508T220045Z-7bcb",
  "decision_note": null,
  "audit_trail": [
    {"event": "requested", "at_utc": "...", "by": "approve-action", "note": "..."}
  ]
}
```

**Status transitions:** `pending` → `granted` (user installed creds; boss verified file exists + json valid + chmod 600) or `denied`.

`kind` free-text: `credentials`, `external_access`, `permission`. No closed enum.

**ID format:** `accr-<utc-iso>-<4-hex>`.

### `/factory/inbox/<utc-iso>-<short>.md` — user free-form replies

Plain markdown file. Optional frontmatter:

```markdown
---
from: user
received_at_utc: 2026-05-08T22:05:00Z
---

approve the prayer-circle tweet, but tweak — replace "calm" with "peaceful". reject the second one (too salesy). I just installed twitter creds at /factory/secrets/social-twitter.json — please verify and retry.
```

After the boss-team processes the message, it MUST move the file to `/factory/inbox/processed/<same-name>.md` (atomic rename) and write an audit entry at `/factory/reviews/inbox-<utc-iso>-<short>.json` describing the parsed intents and the actions taken.

### `/factory/secrets/<resource>.json` — credentials store

Out-of-band: secrets are installed by an operator (me, via SSH) NOT by parsing inbox content. The inbox note signals the install happened; the boss-team only verifies file existence + permissions + schema, never reads secret values into pulse output.

Path convention: `/factory/secrets/<resource_id-with-/-replaced-by->.json`. So the `social/twitter` resource has its creds at `/factory/secrets/social-twitter.json`. Same convention for every resource — `email/marketing-sender` → `email-marketing-sender.json`, etc.

For Twitter (`/factory/secrets/social-twitter.json`):
```json
{
  "schema_version": "1",
  "api_key": "...",
  "api_key_secret": "...",
  "access_token": "...",
  "access_token_secret": "...",
  "bearer_token": "..." 
}
```

File mode MUST be `600`, owner `dev`.

## Skills

### `propose-tweet` — replaces mock post-twitter for tweet card pipelines

- **Inputs (env):** `TASK_INPUT` (JSON of card.input — needs `text`, optionally `source_url`, `intended_url_substrings`), `TASK_ID`
- **Side effect:** writes `/factory/approvals/<approval_id>.json` with kind=tweet, status=pending, source_card_id=TASK_ID, payload from input
- **Stdout (single-line JSON):**
  ```json
  {"success": true, "approval_id": "appr-...", "approval_path": "/factory/approvals/appr-....json", "approval_status": "pending"}
  ```
- **Failure:** if `text` missing or empty, `{"success": false, "error": "operator_must_supply_text"}`

### `post-twitter-real` — invoked ONLY by approve-action, never by a card pipeline

- **Inputs (env):** `APPROVAL_PATH` (full path to approval card on disk), optionally `DRY_RUN=1` for tests
- Reads creds at `/factory/secrets/social-twitter.json`. If missing or schema-invalid, raises an access-request and returns failure.
- Posts to Twitter API v2 (`POST /2/tweets`) using OAuth 1.0a user context via `requests`.
- **Stdout (single-line JSON) on success:**
  ```json
  {"success": true, "tweet_id": "1789...", "live_url": "https://twitter.com/i/status/1789...", "posted_at_utc": "..."}
  ```
- **Stdout on creds_missing:**
  ```json
  {"success": false, "error": "creds_missing", "access_request_id": "accr-...", "access_request_path": "/factory/access-requests/accr-....json"}
  ```
- **Stdout on API error:**
  ```json
  {"success": false, "error": "api_error", "http_status": 401, "body_excerpt": "..."}
  ```

### `approve-action <approval_id> [decision_note]`

- **Inputs (env):** `APPROVAL_ID`, `DECISION_NOTE`
- Reads approval card. If status != pending, returns failure (`error: not_pending`).
- Sets `status=approved`, `decided_at_utc=<now>`, `decided_by=user`, `decision_note=<env>`. Appends `{event: approved, ...}` to audit_trail. Atomic-rename write.
- Dispatches by kind:
  - `kind=tweet`: invokes `post-twitter-real` with the approval path. On success: status=`posted`, resulting_artifact={tweet_id, live_url, posted_at_utc}. On creds_missing: status=`creds_missing`, audit-trail records access_request_id. On api_error: status=`post_failed`, audit-trail records http_status + body_excerpt.
  - other kinds: leave as `approved`, audit "approve-action: no dispatcher for kind=<kind>".
- **Stdout:** `{"success": true, "approval_id": "...", "final_status": "posted|creds_missing|post_failed|approved", "resulting_artifact": {...}|null, "access_request_id": null|"..."}`

### `reject-action <approval_id> [decision_note]`

- Reads approval. If status != pending, fails. Sets status=rejected, decided_at_utc, decision_note. Audit "rejected". Atomic write. Stdout success.

### `grant-access <request_id>`

- Verifies `/factory/secrets/<resource>.json` exists, chmod 600, parses as JSON with required keys per request schema.
- If valid: sets access-request status=granted, decided_at_utc. Audit "granted". Atomic write.
- If invalid: stdout `{"success": false, "error": "creds_invalid", "detail": "..."}` — request stays pending.
- Then re-dispatches any approval-card with status=`creds_missing` and `audit_trail[].access_request_id == request_id` — re-invokes approve-action for that approval.

## Operator pulse prompt — additions

The operator pulse lives in `/opt/hermes-home/profiles/boss/cron/jobs.json` field `jobs[0].prompt` (and the source-of-truth copy at `docs/cards/operator-pulse-prompt.md` in this repo).

### New: Step E.0 — Diversity gate (before E.1 "add a new card")

Before drafting any new card:

1. Load last 5 cards with `status="done"` from `board.json`.
2. Compute their **pipeline signature**: `(joined-roles-list, locator_field)`.
3. If the proposed new card's signature matches any of the last 5, REFUSE to add it. Pick a DIFFERENT unfilled channel from `GOAL.md` instead. If every channel has been filled in the last 5 done cards, idle the pulse.
4. Also REFUSE if a `pending` approval-card exists with kind matching the proposed card's primary side-effect (e.g., don't draft another tweet card while a tweet approval is pending).

This rule is load-bearing: without it, the operator drafts twenty near-identical Twitter cards.

### New: Step F — Process inbox

After Step E (or whenever the operator has spare attention):

1. List `/factory/inbox/*.md` (excluding `processed/`). If empty, skip.
2. Pick the OLDEST unprocessed message (one per pulse — same one-step rule).
3. Read the message body.
4. Read `/factory/approvals/` (all pending) and `/factory/access-requests/` (all pending).
5. With LLM judgment, parse the user's intent. Possible intents:
   - **approve** an approval (by id, or by fuzzy match — "the prayer circle tweet")
   - **reject** an approval
   - **grant** an access-request (only after verifying secrets file exists; never read secret values)
   - **deny** an access-request
   - **edit-and-approve**: user wants to tweak the payload before approving (e.g., "approve but change 'calm' to 'peaceful'") — apply the edit to the approval payload, then approve.
   - **none-of-the-above**: free-form chat with no actionable intent — just acknowledge in audit.
6. For each parsed intent, invoke the corresponding skill (`approve-action`, `reject-action`, `grant-access`).
7. Move the inbox file to `/factory/inbox/processed/<same-name>.md` (atomic rename).
8. Write audit at `/factory/reviews/inbox-<utc>-<short>.json` containing: original message body, parsed_intents (with confidences), actions_taken (skill stdout per call), unresolved (intents that couldn't be matched to an id).

**Hard rule:** the boss-team MUST NOT read secret values from inbox messages. If a user pastes a key in the inbox, the boss-team logs the audit as "WARNING: secret-shaped string detected in inbox; ignored. User should install creds out-of-band at /factory/secrets/<resource>.json with chmod 600." and does NOT install creds from the inbox.

### New: Step G — Surface pending-user-action status

After Step F (every pulse, idempotent):

1. Read `/factory/approvals/` for pending entries; read `/factory/access-requests/` for pending entries.
2. Write `/factory/status/pending-user-action.md` (atomic rename) — a human-readable summary that lists each pending approval and access-request with: id, kind, age, one-line description, what the user can do.
3. If the queue is empty, the file body should say so explicitly.

This file is what I read when the user says "show pending tweets" — it must always reflect current state.

## Resource changes

`/factory/resources/social/twitter.json`:
- Flip `auto_approved: true` → `auto_approved: false` (approval is the gate; not bypassed).
- Add `execution.post_tweet.requires_approval: true` (informational; the real gate is the propose-tweet skill).
- Optionally rename or add a flag to clarify: this resource now means "twitter (real, approval-gated)". Keep `mock: true` as long as actual API isn't wired, flip to `false` once creds are installed and tested.

## Out of scope for this rework
- Critic gateway not running (separate issue, log it but don't fix here).
- Email approval flow (will follow same shape; not implementing this round).
- Rejecting partial-batch (e.g., "approve 3 of these 5") — the message can express it but we treat each id separately; the operator parses intents per-id.
