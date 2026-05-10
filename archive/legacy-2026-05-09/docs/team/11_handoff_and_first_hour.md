# Handoff + First-Hour Kickoff

## The handoff prompt

Auto-sent by `01_install.sh` and `yolo_bridge.sh on` to each profile's first tmux session. Documented here for reference and manual respawning.

```
Read AGENTS.md, SOUL.md, TEAM_SOUL.md in full. Then $FACTORY/PROTOCOL.md, HARD_RULES.md, STANDING_APPROVALS.md, QUIET_HOURS.md, DIRECTIVES.md, BRAND_VOICE.md, MESSAGE_FRAMEWORK.md, CAMPAIGNS_ACTIVE.md. Enter your operating loop per TEAM_SOUL.md. Write your first heartbeat. Write your first cycle output now. No preamble. Execute.
```

## First hour minute-by-minute

What happens after `01_install.sh` completes. Your contract: by minute 60, factory has produced concrete drafts and you've received the first Telegram digest.

### 0:00–0:05 — Install completes

`01_install.sh` finishes:
- 14 profiles created at `~/.hermes-<name>/`
- Bus at `factory/`
- Wiki at `wiki/`
- Obsidian symlinked
- Telegram gateway tmux running
- HUMAN_SECRET generated for supervisor signature
- 14 + 1 tmux sessions alive
- Cron jobs registered (~70+ across factory)
- All profiles in `--yolo` mode (Hermes UI prompts off)

You see:
```
JESUSCORD FACTORY v2.0 DEPLOY COMPLETE
  Profiles: 14 / 14
  Tmux sessions: 15 alive
```

### 0:05–0:15 — Command line convenes

**boss** boots: reads soul, protocol, hard rules, standing approvals, quiet hours. Reads all 13 status files (others might still be booting). Forms first strategic intent. Writes 3-5 opening orders to `factory/orders/`.

**supervisor** boots: reads orders. All 5 will be in-envelope (existing standing approvals cover them). Signs each. Writes to `factory/approved_orders/`. Sends boot-confirm to Telegram.

**hr** boots: reads approved_orders. Routes work to teams. Writes assignments. Health-checks all profiles.

**conductor** boots: reads cron schedules, throughput baselines (none yet — fresh install). Writes initial cron_health.json.

Blackboard at minute 15:
```
[<TS>] boss: online. read protocol. 5 opening orders written.
[<TS>] supervisor: online. signed 5 orders in envelope.
[<TS>] hr: online. routed 5 orders. 14 profiles healthy.
[<TS>] conductor: online. cron schedule baselined.
```

### 0:15–0:25 — Specialists boot

**growth** boots: reads protocol, defines metrics schema in PERFORMANCE.md (since empty), writes week-1 hypotheses to wiki/lessons/.

**eng** boots: reads protocol, reads boss's first orders, identifies feature implications, writes initial wiki/feature_pipeline.md.

**brand** boots: reads protocol, reads boss's first orders, drafts v1 of all canonical artifacts:
- BRAND_VOICE.md (voice rules, audience-segment deltas)
- MESSAGE_FRAMEWORK.md (core messages)
- POSITIONING.md (vs YouVersion/Hallow/Discord)
- CONTENT_PILLARS.md (5 territories)
- CAMPAIGNS_ACTIVE.md (7 starting campaigns)
- CALENDAR.md (first 30 days)

Brand drops per-team content briefs into each team's inbox.

### 0:25–0:45 — 7 execution teams boot

In parallel, each reads soul + protocol + brand artifacts + assignment from hr + content brief from brand. Each does first-cycle output:

**room-engine**: 50 room concepts (mix of evergreen + trend-rideable). Drafts to drafts/room_concepts/.

**video**: 20 video drafts (top-10 highest-viral concepts × 2 variants each). Renders begin via Seedance.

**distro**: kicks off first listen-cycle (full multi-platform scrape, baseline 6h). Drafts 100 personalized email pitches to seed pastor list. Batches into approvals/emails_batch_001.md.

**sermons**: scans configured pastor feeds. If any have new sermons, clips top 5 (5 clips each = 25 drafts).

**creators**: prospects first 20 mid-tier creators. Builds wiki/creators/ profiles. Drafts 20 personalized pitches.

**dev**: reads eng's pipeline brief. If codebase access configured, pulls baseline product-analytics → pushes to growth.

**churches**: pre-builds first 20 church profiles from sources/pastors/seed_list.csv. Drops 20 room concept envelopes to room-engine inbox.

### 0:45–0:55 — Cross-team coordination begins

Cron schedules from `08_cron.md` start firing:
- distro fires 2nd listen-cycle (refined trends)
- room-engine fires 2nd concept-cycle, this time consuming Genesis chains (now has ~70 concepts in pipeline)
- video fires 2nd render-cycle (church-room promos)
- hr fires 2nd health-check (all green; spend ~$15-30)
- growth fires 1st measurement (zero installs expected, baseline output volume captured)
- conductor fires 1st throughput-monitor (baseline established, no adjustments yet)
- boss fires 2nd strategic-pulse (now reading actual factory state, not boot state — issues 2-3 refined orders)

### 0:55–1:00 — First hourly digest fires

At top-of-hour, boss's `hourly-digest` cron fires:

```
🟢 JESUSCORD FACTORY — HOURLY [HH:MM UTC]
─────────────────────────────────
PROFILES:    14/14 alive
DRAFTS:      ~250 waiting your tap
ESCALATIONS: 0 need decision
LAST HOUR:
  • room-engine:  ~70 rooms drafted (~10 hot)
  • video:        ~22 videos rendered
  • distro:       ~30 social posts queued, 100 emails drafted (1 batch awaiting tap)
  • sermons:      ~25 clips drafted
  • creators:     ~20 outreaches drafted
  • churches:     ~40 church rooms pre-built (chained to room-engine)
  • dev:          feature pipeline written, baseline analytics
ORDERS: 8 written by boss, 8 signed by supervisor
PERFORMANCE: baseline. 0 installs (expected).
HARD_RULES: clean
─────────────────────────────────
Tap /full for deep digest.
```

Plus 1-2 approval batches awaiting your tap (emails_batch_001, possibly social_batch_001). When you tap-approve and supervisor follows up "Add as standing?" — say YES for any class you'll repeat.

### Minute 60 you have

- 250 drafts queued
- 1-2 approval batches awaiting tap
- 14 profiles healthy in their loops
- Wiki populated with: 6 brand artifacts, 1 schema, 1 metrics doc, 20 church profiles, 20 creator profiles, 1 feature pipeline, 1 growth-week-1 doc, 1 territory baseline
- Sources/ populated with: first multi-platform scrape from distro
- Decisions/: 8-10 entries (orders signed)
- Telegram main channel: 1 hourly digest

You can:
- Tap approval batches via Telegram (each tap releases 50 emails / 20 posts)
- Open Obsidian → see wiki populating
- `tail -f factory/activity.log` → live activity

### What you don't see yet

- Installs in dashboards (haven't pushed to public — your taps + supervisor signatures unlock that)
- All 700 church rooms (churches does 30-50/day, ~2 weeks to full population)
- Refined voice (brand v1; growth measures; brand v2 in 24h based on data)

### Hour 2-24

Cron schedule from `08_cron.md` runs autopilot. Each subsequent hour:
- ~50-100 new room concepts (room-engine, accelerating with trends)
- ~20-50 new videos
- ~50-100 new sermon clips (when pastor sermons publish)
- 1-3 new creator pitches
- 30-50 new church rooms pre-built
- 1-3 feature specs filed → dev → ship
- Hourly Telegram digest from boss
- Every 4h: strategic memo, contradiction scan
- Every 6h: growth memo, feature pipeline update
- Daily 06:30/18:30 UTC: comprehensive daily digests

By end of day 1:
- ~1500+ room concepts drafted
- ~500+ videos rendered
- ~500+ sermon clips
- 30-50 creator outreaches sent (after taps)
- 200-400 personalized emails sent (after taps)
- 100+ church rooms pre-built and notified
- Wiki: ~100+ pages of synthesized intel
- First measurable installs

Day 2 = same shape, refined by day-1 winners/losers.
