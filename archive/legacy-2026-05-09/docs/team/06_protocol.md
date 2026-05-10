# PROTOCOL.md

The bus contract. Every profile reads this every cycle.

<!-- protocol_version: 2.0 -->

## 1. The bus

```
factory/
├── PROTOCOL.md                    this file
├── HARD_RULES.md                  immutable; only founder edits
├── STANDING_APPROVALS.md          class-level pre-authorizations
├── BLACKBOARD.md                  cross-team scratch (append-only)
├── DIRECTIVES.md                  legacy (boss orders go in orders/ now)
├── BRAND_VOICE.md                 canonical (brand writes, all read)
├── MESSAGE_FRAMEWORK.md           canonical
├── CAMPAIGNS_ACTIVE.md            current campaigns
├── POSITIONING.md                 vs competitors
├── CONTENT_PILLARS.md             5 territories
├── CALENDAR.md                    90-day rolling
├── PERFORMANCE.md                 metrics, hourly refresh
├── PRIORITIZE.md                  founder override
├── QUIET_HOURS.md                 day/night window for supervisor escalation rhythm
├── activity.log                   firehose
├── orders/<id>.md                 boss writes
├── approved_orders/<id>.md        supervisor signs
├── assignments/<id>.md            hr routes
├── inbox/<profile>/               per-profile inbound queue
├── outbox/<profile>/              per-profile published work
├── status/<profile>.json          heartbeat
├── status/<profile>.narrative.md  optional one-line
├── drafts/<channel>/              queued for approval check
├── approvals/                     batch files + signed
├── escalations/                   needs founder
├── locks/                         flock files
└── HALT_<profile>.flag            presence halts that profile
```

## 2. Order envelope (boss writes, supervisor signs)

```yaml
---
order_id: ord_<unix>_<6char>
created_at: <ISO8601>
created_by: boss
type: spawn_team | sunset_team | rewrite_soul | reallocate_budget | strategic_pivot | territory_expansion | brand_pivot | feature_request | campaign_launch | campaign_kill | creator_outreach | partnership_pursuit
priority: 0-10
deadline: <ISO8601 | null>
affects: [<profile-list>]
budget_impact_usd: <float>
---

# Thesis
[one paragraph]

# Action
[specific actions, who executes, by when]

# Success criteria
[measurable, dated]

# Kill criteria
[conditions for sunset]

# Standing approval class
[propose class name + scope if this is a recurring class]
```

After supervisor sign:

```yaml
# SIGNED
- by: supervisor (delegated by founder)
  at: <ISO8601>
  signature: <SHA256 hex>
  envelope_match: STANDING_APPROVALS:<class> | HARD_RULES_§3:<channel> | INTERNAL
```

## 3. Assignment envelope (hr writes)

```yaml
---
assignment_id: asn_<unix>_<6char>
order_id: <ord_id>
created_at: <ISO8601>
created_by: hr
to: <profile or [profiles]>
priority: 0-10
deadline: <ISO8601>
---

# Routing rationale
[why this team / split]

# Per-team scope
- <profile1>: <scope>
- <profile2>: <scope>

# Inputs
[paths to context files, prior orders, related drafts]

# Expected outputs
[paths, formats]
```

hr also drops a copy to each affected team's inbox/<profile>/.

## 4. Status heartbeat

Atomic write per cycle to `factory/status/<profile>.json`:

```json
{
  "profile": "<name>",
  "pid": 12345,
  "session_id": "<hermes-session-uuid>",
  "host": "<hostname>",
  "uptime_seconds": <n>,
  "last_cycle_at": "<ISO8601>",
  "current_task": "<task_id-or-null>",
  "tasks_completed_24h": <n>,
  "tasks_failed_24h": <n>,
  "queue_depth": {"inbox": <n>, "in_progress": <n>},
  "drafts_produced_24h": {"<channel>": <n>},
  "spend_24h_usd": <float>,
  "halted": false
}
```

Stale >5 min: hr flags. Stale >10 min: hr restarts.

## 5. Blackboard

`factory/BLACKBOARD.md` — append-only, signed, timestamped. One sentence per entry:

```
[<ISO8601>] <profile-name>: <message>
```

Boss reads last 1h every cycle. Weekly rotate to `wiki/lessons/blackboard_<week>.md`.

## 6. Locks

Two surfaces:

**flock for shared file writes:**

```bash
( flock -x -w 10 200 || exit 1
  # write
) 200> factory/locks/<resource>.lock
```

**Soft locks** for cross-process coordination — single line file:
`<profile>|<pid>|<ISO8601-acquired>`. Stale >10 min → hr reaps.

Never hold a lock across an LLM call. Acquire → mutate → release.

## 7. Approvals (with day/night rhythm)

**Three layers of evaluation, in order, every outbound action:**

1. **HARD_RULES.md §3 channel gate** — ungated/under-threshold? proceed.
2. **STANDING_APPROVALS.md class match** — listed with scope match? proceed.
3. **Supervisor signature flow:**
   - Order/draft falls into envelope → supervisor signs immediately
   - Order/draft is novel → supervisor escalates per QUIET_HOURS.md rhythm

**QUIET_HOURS.md format:**

```yaml
quiet_hours_local:
  start: "23:00"
  end:   "07:00"
timezone: "Asia/Taipei"
batch_reminder_hours: 3
morning_digest_at: "07:30"
```

**Day mode (outside quiet hours):**
- Novel escalation → supervisor fires single Telegram message immediately
- Tap-buttons: approve / approve-and-make-standing / deny / deny-with-reason
- If unactioned 3h later: batch into "still pending" reminder
- Reminders repeat every 3h until cleared

**Night mode (inside quiet hours):**
- Novel escalations queue silently in escalations/
- Supervisor continues signing in-envelope orders
- Boss continues writing orders
- Teams continue executing

**Wake-up boundary (transitioning night→day at morning_digest_at):**
- Single comprehensive Telegram digest:
  ```
  ☀️ OVERNIGHT — [N hours]
  SIGNED IN-ENVELOPE: <count> auto-approved
  PRODUCED: <breakdown>
  PERFORMANCE: <growth one-liner>
  ─────────────────
  NOVEL ITEMS — your tap needed:
  • [N items, tap-through]
  ─────────────────
  HARD_RULES: clean
  ```

**On founder tap:**
- "approve" → supervisor signs this order, processes
- "approve-and-make-standing" → supervisor appends class to STANDING_APPROVALS.md (the only file supervisor can write outside its own scope), signs this order, future class members auto-sign
- "deny" → supervisor writes denial; boss reads, stops issuing this class
- "deny-with-reason" → reason captured; boss reads, may reformulate

## 8. Decisions log

Append-only at `factory/decisions/<unix>_<class>_<id>.md`. Hash-chained:

```yaml
---
decision_id: dec_<unix>_<6char>
prev_hash: <sha256 of prior decision>
class: order_signed | order_denied | spawn_team | sunset_team | budget_reallocate | territory_expand | brand_pivot | emergency_halt | standing_approval_added | standing_approval_revoked
proposer: boss | supervisor | hr | conductor | founder
created_at: <ISO8601>
affects: [<profile-list>]
---
[Decision text]
```

Genesis: prev_hash = 64 zeros. Audit by recomputing forward. hr reaps stale locks but never edits this log.

## 9. PRIORITIZE.md (founder override)

Read at top of every cycle, before inbox. Anything under `## STOP_EVERYTHING` halts factory in 60s. `## OVERRIDE <X>` directives processed by boss within 1h. `## STANDING_APPROVAL <class>` adds entry to STANDING_APPROVALS.md (alternative to waiting for supervisor's prompt). `## SUNSET <team>` orders sunset.

## 10. Telegram channels (supervisor manages)

| Channel | Source | Frequency |
|---|---|---|
| Main | hourly digest from boss | every 1h |
| Supervisor | new escalations | event-driven (day) / batched (night) |
| Pulse | every 4h state per profile | every 4h |
| Performance | growth deltas | every 30 min |
| Daily-AM | comprehensive | once at morning_digest_at |
| Daily-PM | end-of-day | once at start-of-quiet-hours |
| Blockers | stale heartbeats, lock leaks | event-driven |

## 11. Loop cycle

Every profile, every cron tick:

1. Auto-injected: SOUL.md, AGENTS.md, TEAM_SOUL.md
2. Read: PROTOCOL.md, HARD_RULES.md, STANDING_APPROVALS.md, BRAND_VOICE.md, MESSAGE_FRAMEWORK.md, CAMPAIGNS_ACTIVE.md
3. Read PRIORITIZE.md, QUIET_HOURS.md
4. Check HALT_<profile>.flag → sleep cycle if present
5. Atomic write status heartbeat
6. Poll inbox; pick highest-priority valid task
7. Validate envelope; reject malformed → REJECTED/
8. Acquire locks
9. Execute
10. Write outputs to outbox/<profile>/, drafts/<channel>/, or chain
11. Append activity.log; blackboard if cross-team
12. Release locks
13. Yield

## 12. Versioning

`<!-- protocol_version: 2.0 -->`. Bump on incompatible envelope schema. Profiles seeing protocol_version > their write-against version halt + escalate.
