# STANDING_APPROVALS.md

Class-level pre-authorizations. Read by every profile every cycle, after HARD_RULES.md. Supervisor signs orders matching any class here without founder tap.

Founder edits directly OR supervisor appends after founder taps "approve-and-make-standing" on a Telegram escalation.

To revoke: write `## REVOKE <class>` to PRIORITIZE.md, or remove the entry directly.

---

## Active classes

```yaml
- class: email_drafts_to_pastors_in_seed_list
  granted_at: 2026-05-02T00:00:00Z
  granted_by: founder (initial bundle)
  scope: |
    Draft personalized pitches for any pastor in sources/pastors/seed_list.csv
    where wiki/pastors/<name>.md shows prior 愛無線 interaction.
    Volume gate per HARD_RULES.md §3 (ungated below 500 sends/24h).
  expires: never

- class: social_post_to_seed_accounts
  granted_at: 2026-05-02T00:00:00Z
  granted_by: founder
  scope: |
    Posts to accounts in factory/seed_accounts.json, content aligned with
    BRAND_VOICE.md, no §2 violations. Below 500/24h auto.
  expires: never

- class: room_concept_creation_aligned_to_active_campaigns
  granted_at: 2026-05-02T00:00:00Z
  granted_by: founder
  scope: |
    room-engine generates concepts aligned to current CAMPAIGNS_ACTIVE.md.
    No tap. Concepts proposing new audience segments or pillars NOT in
    current campaigns flagged 'novel' for brand review before scaling.
  expires: never

- class: video_render_below_threshold
  granted_at: 2026-05-02T00:00:00Z
  granted_by: founder
  scope: |
    video renders at $5/render or below, up to $50/24h/team.
    Above threshold = batch tap.
  expires: never

- class: subagent_spawn_below_25_concurrent
  granted_at: 2026-05-02T00:00:00Z
  granted_by: founder
  scope: |
    Any profile spawns up to 25 concurrent subagents. Above = consult hr.
  expires: never

- class: wiki_writes_under_skill_governance
  granted_at: 2026-05-02T00:00:00Z
  granted_by: founder
  scope: |
    Wiki writes via wiki-write skill (which enforces SCHEMA.md). Promotions
    via promote-to-wiki skill. No tap.
  expires: never

- class: cross_team_inbox_chaining
  granted_at: 2026-05-02T00:00:00Z
  granted_by: founder
  scope: Internal coordination. Always free.
  expires: never

- class: blackboard_writes
  granted_at: 2026-05-02T00:00:00Z
  granted_by: founder
  scope: Internal coordination. Always free.
  expires: never

- class: status_heartbeat_writes
  granted_at: 2026-05-02T00:00:00Z
  granted_by: founder
  scope: Mandatory by HARD_RULES.md §7. Always free.
  expires: never

- class: cron_self_management
  granted_at: 2026-05-02T00:00:00Z
  granted_by: founder
  scope: |
    A profile manages its OWN cron. Conductor manages all profiles' crons.
    No profile may modify another team's cron without conductor or hr.
  expires: never

- class: skill_creation_and_promotion
  granted_at: 2026-05-02T00:00:00Z
  granted_by: founder
  scope: |
    Hermes auto-creates skills after 5+ tool-call patterns. Profiles keep,
    archive, or pin their own. boss/hr promote skills to wiki/skills-library/.
  expires: never

- class: pastor_clip_distribution_to_authorized_accounts
  granted_at: 2026-05-02T00:00:00Z
  granted_by: founder
  scope: |
    sermons distributes clips to pastor accounts ONLY when wiki/pastors/<name>.md
    shows clip_auth: true (pastor pre-authorized at onboarding).
  expires: never

- class: boss_orders_within_existing_campaigns
  granted_at: 2026-05-02T00:00:00Z
  granted_by: founder
  scope: |
    Boss orders that operate within currently-active campaigns and don't
    introduce new outbound classes. Supervisor signs.
  expires: never

- class: hr_team_assignments
  granted_at: 2026-05-02T00:00:00Z
  granted_by: founder
  scope: |
    hr routes signed orders to existing teams. Spawning new teams requires
    supervisor sign on the boss's spawn_team order.
  expires: never

- class: conductor_cron_adjustments
  granted_at: 2026-05-02T00:00:00Z
  granted_by: founder
  scope: |
    Conductor adjusts cron cadence within reasonable bounds (not below 30s
    intervals, not slowing critical paths >2x). Boss-ordered cron changes
    flow through normal sign chain.
  expires: never
```

---

## Adding new classes

Two paths:

**Path A — founder taps "approve-and-make-standing" on a Telegram escalation:**

Supervisor appends:
```yaml
- class: <derived from order>
  granted_at: <ISO8601 of tap>
  granted_by: founder via Telegram tap on approval batch <approval_id>
  scope: |
    [derived from order content + supervisor's envelope_match]
  expires: <date | never>
```

Supervisor announces on blackboard.

**Path B — founder writes to PRIORITIZE.md:**

```
## STANDING_APPROVAL <class-name>
Scope: <plain English>
Expires: <optional>
```

Supervisor processes on next cycle, appends to this file, announces.

---

## Revocation

Three paths:

1. PRIORITIZE.md: `## REVOKE <class>` → supervisor removes entry, future tap-required again
2. Edit this file directly (writeable, not chmod 444 like HARD_RULES.md)
3. Boss emergency revoke via decision file (if §2 violation suspected)

---

## Quarterly re-confirm

Every 90 days, supervisor includes in daily-PM digest:

```
🔁 STANDING APPROVALS — quarterly re-confirm
Active since <date>:
  • email_drafts_to_pastors_in_seed_list (granted 2026-05-02)
  • [...]
Reply REVOKE <class> to remove. Silence = persists 90 more days.
```
