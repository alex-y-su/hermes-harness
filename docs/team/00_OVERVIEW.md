# 00_OVERVIEW.md — Factory architecture

14 Hermes profiles. Filesystem bus. Karpathy 3-layer wiki. Single Telegram channel for human ↔ factory.

## The 14 profiles

```
┌──────────────────────────────────────────────────────────────────┐
│  COMMAND LINE                                                     │
│  ──────────────                                                   │
│  boss        — strategic CEO. Reads everything. Writes orders.    │
│  supervisor  — delegated approval. Signs as founder in envelope.  │
│  hr          — assigns work. Spawns teams. Health-checks.         │
│  conductor   — owns cron. Tunes tempo.                            │
└──────────────────────────────────────────────────────────────────┘
                              │
                  reads from / writes to
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│  SPECIALISTS (feed boss)                                          │
│  ───────────                                                      │
│  growth — funnel measurement. Kill/double calls.                  │
│  eng    — marketing↔dev liaison.                                  │
│  brand  — canonical voice + campaign briefs (funnel-source).      │
└──────────────────────────────────────────────────────────────────┘
                              │
                       brand briefs
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│  EXECUTION (7 teams)                                              │
│  ─────────                                                        │
│  room-engine  — 50-200 room concepts/day                          │
│  video        — 200-500 video renders/day                         │
│  distro       — 24/7 listen + cross-platform post                 │
│  sermons      — pastor sermon clipping                            │
│  creators     — mid-tier creator partnerships                     │
│  dev          — codebase access; ships viral features             │
│  churches     — pre-builds 700 church hubs                        │
└──────────────────────────────────────────────────────────────────┘
```

## The order flow

```
boss writes order → factory/orders/<id>.md
        ↓
supervisor evaluates against HARD_RULES.md §3 + STANDING_APPROVALS.md
        ↓
   In envelope?  →  YES: sign with HUMAN_SECRET HMAC → factory/approved_orders/<id>.md
                 →  NO:  → factory/escalations/order_<id>.md → Telegram (day) or queue (night)
        ↓ (if signed)
hr reads approved_orders/, routes to team(s) → factory/inbox/<team>/<id>.md
        ↓
team executes; output drafts → standing approval check → ship or batch
```

The supervisor's signature is the founder's signature for envelope-matching orders. It's NOT founder-override — it's founder-already-decided-this-class delegation. Outside-envelope items always escalate to the human.

## Day vs night

Defined in `factory/QUIET_HOURS.md`:

```yaml
quiet_hours_local:
  start: "23:00"
  end:   "07:00"
timezone: "Asia/Taipei"
batch_reminder_hours: 3
morning_digest_at: "07:30"
```

**Day:** novel escalations hit Telegram one-by-one immediately. Unactioned 3h later → "still pending" reminder.

**Night:** novel escalations queue silently. Supervisor signs in-envelope. Boss continues writing orders. Teams execute.

**Wake-up:** comprehensive overnight digest + batch of all queued escalations in one Telegram message.

## Communication infrastructure

```
factory/
├── PROTOCOL.md              the contract (every cycle)
├── HARD_RULES.md            immutable; only founder edits (chmod 444)
├── STANDING_APPROVALS.md    class-level pre-authorizations
├── BLACKBOARD.md            cross-team scratch (append-only)
├── BRAND_VOICE.md           canonical (brand writes, all read)
├── MESSAGE_FRAMEWORK.md
├── CAMPAIGNS_ACTIVE.md
├── POSITIONING.md
├── CONTENT_PILLARS.md
├── CALENDAR.md
├── PERFORMANCE.md           hourly refresh from growth
├── PRIORITIZE.md            founder override
├── QUIET_HOURS.md           day/night window
├── orders/                  boss writes
├── approved_orders/         supervisor signs
├── assignments/             hr routes
├── inbox/<profile>/         per-team inbound
├── outbox/<profile>/        per-team published
├── status/<profile>.json    heartbeat (every cycle)
├── drafts/                  queued
├── approvals/               batched + signed
├── decisions/               append-only, hash-chained
├── escalations/             needs founder
├── locks/                   flock files
├── activity.log             firehose
└── HALT_<profile>.flag      halts profile
```

Mirrored to Obsidian vault at `<obsidian path>/Jesuscord` for human-side viewing.

## Karpathy memory

```
sources/                 Layer 1 — immutable, append-only
└── pastors/, corpus/, platforms/, transcripts/, public/, inbound/

wiki/                    Layer 2 — curated synthesis (Obsidian-flavored)
├── audience/            demographic deep-dives
├── voice/               brand voice studies
├── competitive/         per-app analysis
├── pastors/             1000-target enriched profiles
├── creators/            200+ profiles
├── churches/            700 profiles
├── conferences/
├── opportunities/
├── campaigns/           blueprints from brand
├── lessons/             dated retrospectives
├── skills-library/      promoted skills
├── branding/            canonical artifacts archive
├── runbooks/            from hr
├── feature_pipeline/    from eng+dev
├── memory-promotions/   MEMORY.md → wiki promotions
└── team_roster/         hr maintains

wiki/SCHEMA.md           Layer 3 — governance
```

## Hard rules (HARD_RULES.md — immutable)

8 sections covering: budget caps (§1), mission refusals (§2), per-channel approval gates (§3), supervisor authority bounds (§4), unsubscribe + sender ID (§5), decision integrity hash chain (§6), status reporting mandate (§7), app store policy compliance (§8), data retention (§9), emergency halt (§10), founder escape hatch (§11).

Only the founder edits HARD_RULES.md. Supervisor cannot. Boss cannot. Council decisions cannot override §1, §2, §4.

## Bundle file index

```
INSTALL_GUIDE.md           ★ START HERE. Dummy walkthrough.
HUMAN_GUIDE.md             ★ How to use the team day-to-day. Read after install.
00_OVERVIEW.md             this file. Architecture diagram.
01_install.sh              run once.
02_SOUL_MASTER.md          inherited by every profile.
03_top_tier_souls.md       boss, supervisor, hr, conductor.
04_specialist_souls.md     growth, eng, brand.
05_team_souls.md           7 execution teams.
06_protocol.md             becomes factory/PROTOCOL.md.
07_wiki_setup.sh           run after 01.
08_cron.md                 schedule reference + register script.
09_megaprompts.md          paste into Claude Code in your hermes fork (day 2+).
11_handoff_and_first_hour.md  boot prompt + minute-by-minute hour 1.
HARD_RULES.md              immutable rules (chmod 444).
STANDING_APPROVALS.md      class-level pre-authorizations (writeable).
yolo_bridge.sh             run after 01 + 07.
```
