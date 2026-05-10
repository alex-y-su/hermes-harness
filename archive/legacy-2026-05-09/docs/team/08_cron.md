# Cron Schedule

Densified for the 14-profile architecture. Hot tier 5 min. Specialist 10 min. Wiki maintenance 15 min.

Hermes' real constraints:
- Gateway tick = 60s (megaprompt 10 patches to 5s)
- Each cron fire = isolated agent session, ~30s-3min wallclock
- File lock prevents overlapping ticks (safe)
- Cron sessions cannot spawn cron (anti-loop)
- No documented hard cap on jobs/profile
- Subagent fan-out: default 5 concurrent, raise to 25 with depth=3 (megaprompt 10)
- Provider rate limits = real ceiling

Total density: ~250-400 cron fires/hour across 14 profiles.

---

## boss (every 5 min — strategic CEO)
```
*/5 * * * *      strategic-pulse           "Read all 13 status files, last 1h blackboard, growth narrative, eng feature pipeline, brand artifacts, approved_orders, escalations, PERFORMANCE.md. Identify highest-leverage move not being made + lowest-yield to kill + missing capability. Write 1-5 orders to factory/orders/ this cycle."
*/5 * * * *      creative-pulse            "Look at the whole company state with fresh eyes. What would a sleepy human boss not have thought of? Write 1-2 creative orders this cycle."
0 */4 * * *      strategic-memo            "Write wiki/lessons/strategic_<date>.md: what learned last 4h, current bottleneck, what we're betting on next 4h, kill/double calls pending."
0 */24 * * *     territory-review          "Write wiki/lessons/territory_<date>.md: which fronts open, which producing, expand/consolidate, proposed new fronts."
0 */1 * * *      hourly-digest             "Emit hourly digest to Telegram main per format in TEAM_SOUL.md."
```

## supervisor (every 5 min — delegated approval)
```
*/5 * * * *      sign-orders               "Read all new orders/<id>.md. Per order, check envelope (STANDING_APPROVALS + HARD_RULES §3). Sign + move to approved_orders/ if in envelope. Write escalations/order_<id>.md if novel. Halt order author if §2 hit."
*/5 * * * *      day-night-router          "Read QUIET_HOURS.md. If day mode: fire single Telegram per new escalation. If night: queue silently. Process founder taps from Telegram → process responses, update STANDING_APPROVALS.md if 'make-standing'."
0 */3 * * *      pending-batch-reminder    "If unactioned escalations exist (day) or accumulated overnight (transitioning), fire ONE batched Telegram reminder."
30 7 * * *       morning-digest            "[Adjust to your morning_digest_at] Comprehensive overnight summary + batch of all queued escalations."
```

## hr (every 5 min — assignment + health)
```
*/5 * * * *      route-approved-orders     "Read approved_orders/<id>.md. Determine team(s) per order. Drop assignments to team inbox(es). Write factory/assignments/<order_id>.md."
*/5 * * * *      health-check              "Read 14 status files. Stale >5min: flag. >10min: restart tmux."
*/5 * * * *      resource-check            "Pull 24h spend per provider. Warn at 70%, halt offending team at 95% per HARD_RULES §1."
*/15 * * * *     skill-curator             "Run hermes curator status per profile. Review top-3 new auto-skills; pin/archive."
*/10 * * * *     log-scan                  "Tail activity.log for ERROR/FATAL. Surface to blackboard."
0 */2 * * *      gateway-restart-check     "Verify Telegram gateway tmux session. Restart if down."
0 3 * * *        daily-housekeeping        "Rotate logs. Archive completed approvals. Prune per HARD_RULES §9."
```

## conductor (every 5 min — cron tempo)
```
*/5 * * * *      throughput-monitor        "Read each profile status: avg cycle wall-time, queue_depth.inbox, cycles_per_hour. Identify imbalances."
*/5 * * * *      cadence-adjust            "Apply cron edits via hermes cron edit per imbalance. Write factory/cron_adjustments_<date>.md."
*/15 * * * *     cron-health-write         "Update factory/cron_health.json with all profiles' fire stats."
0 */1 * * *      beat-coordination         "Verify listen→synthesize→render→distribute beat ordering not drifting."
```

## growth (every 10 min — measurement)
```
*/10 * * * *     funnel-pull               "Pull last 10min metrics. Compute deltas vs 1h, 24h, 7d. Top-3 winners + bottom-3 losers."
*/10 * * * *     performance-write         "Update PERFORMANCE.md. Update narrative.md."
*/10 * * * *     boss-feed                 "If significant signal (>2x or <0.5x of expected): write directly to boss inbox."
0 */6 * * *      growth-memo               "Write wiki/lessons/growth_<date>.md."
0 */24 * * *     daily-growth-memo         "Full daily memo: funnel by segment, per-pillar performance, per-team ROI."
```

## eng (every 10 min — marketing↔dev)
```
*/10 * * * *     observation-translate     "Read blackboard last 1h, growth narrative, room-engine template performance. File feature specs to dev/inbox."
*/10 * * * *     ship-readout              "Read dev outbox. Translate ships into marketing exploitation briefs to brand inbox."
*/30 * * * *     product-metrics           "Pull product analytics if dev-side MCP configured. Push slices to growth."
0 */6 * * *      pipeline-update           "Update wiki/feature_pipeline.md."
```

## brand (every 10 min — canonical voice)
```
*/10 * * * *     brand-sync                "Read latest boss orders, growth narrative, eng ships, last 1h blackboard. Update BRAND_VOICE/MESSAGE_FRAMEWORK/CAMPAIGNS_ACTIVE if delta-justified."
*/10 * * * *     campaign-brief-gen        "For new campaigns added this cycle, generate per-team content briefs. Drop to each team inbox."
0 */2 * * *      calendar-refresh          "Refresh CALENDAR.md rolling window."
0 6 * * *        voice-snapshot            "Write wiki/branding/voice_<date>.md."
*/15 * * * *     blackboard-voice-watch    "Read blackboard for voice questions. Answer."
```

## room-engine (every 10 min — concepts)
```
*/10 * * * *     concept-cycle             "Read CAMPAIGNS_ACTIVE, CALENDAR, BRAND_VOICE, distro trends_<latest>. Generate 5-15 concepts via room-concept-generator."
*/10 * * * *     template-performance      "Update wiki/skills-library/room-templates.md with kill/scale recommendations."
*/30 * * * *     recurring-room-scheduler  "Maintain recurring rooms. Reschedule next instances."
0 */2 * * *      killswitch-pass           "Recommend kill for flopped concepts. Write lessons."
0 */1 * * *      chain-to-video            "Chain high-viral-potential concepts (>70 score) to video."
```

## video (every 10 min — render)
```
*/10 * * * *     render-cycle              "Read inbox briefs. Fan to 5-30 variants per brief via subagents. Render via Seedance/Veo/Kling/Runway with fallback."
*/10 * * * *     caption-gen               "Per video, generate platform-specific captions/hashtags."
*/30 * * * *     hook-library-refresh      "Refresh hook library from last-24h winners."
*/30 * * * *     audio-trends              "TikTok/Reels trending audio. Update wiki/skills-library/audio-trends.md."
*/10 * * * *     chain-to-distro           "Batch finished videos. Chain to distro."
0 */1 * * *      render-spend-monitor      "Track render spend. Warn at 70%."
```

## distro (mixed cadence — listen 2 min, post 5 min, email 15 min)
```
*/2 * * * *      listen-cycle              "Multi-platform scrape. Synthesize trends. Push to room-engine inbox."
*/5 * * * *      post-cycle                "Read inbox distribution batches. Route to optimal platform/account/time. Per-platform compliance."
*/15 * * * *     engagement-track          "Per-post engagement at 15min/1h/6h/24h marks. Surface to growth."
*/15 * * * *     email-personalization     "Per pastor, draft personalized pitch from wiki/pastors/<name>.md profile."
*/30 * * * *     email-batch-build         "Batch 50 drafts into approvals/emails_batch_<id>.md. Supervisor signs in-envelope."
*/10 * * * *     reply-handler             "Process inbound replies. Auto-draft responses."
0 */2 * * *      account-rotation          "Rotate seed accounts. Anti-spam patterns."
*/30 * * * *     performance-update        "Update PERFORMANCE.md."
```

## sermons (every 15 min — clipping)
```
*/15 * * * *     feed-monitor              "Check pastor feeds for new sermons."
*/15 * * * *     sermon-process            "Download, transcribe, identify clip windows, render 5-10 clips."
*/15 * * * *     caption-correct           "Theological term accuracy review."
*/15 * * * *     chain-to-distro           "Drop clips to distro for distribution to authorized accounts."
0 12 * * 0       weekly-pastor-brief       "Weekly per-pastor performance brief to pastor inbox via distro."
0 */6 * * *      onboarding-poll           "Reach out via creators for clip authorization."
```

## creators (every 15 min — partnerships)
```
*/15 * * * *     pipeline-cycle            "Read wiki/creators/. Identify next-step creators. Draft outreach."
0 */2 * * *      creator-prospect          "Identify 5-10 new mid-tier candidates."
0 */6 * * *      pipeline-state-track      "Funnel state. Surface stuck >7 days."
*/15 * * * *     partnership-coord         "Coordinate active partnerships across teams."
0 */4 * * *      pastor-as-creator         "Pastors with creator audiences: build creator profile."
```

## dev (every 30 min — feature ships)
```
*/30 * * * *     feature-spec-cycle        "Read inbox for specs from eng. Scope. File PRs."
*/15 * * * *     in-progress-implement     "Continue implementations. Test. Deploy with feature flags."
*/15 * * * *     ship-announcer            "On ship: announce to outbox. Tag eng."
0 */6 * * *      pipeline-update           "Maintain wiki/feature_pipeline.md."
*/30 * * * *     product-analytics         "Pull metrics. Surface anomalies to eng."
0 */1 * * *      flag-monitor              "Recommend rollout for positive-metric flagged features."
```

## churches (every 15 min — pre-build)
```
*/15 * * * *     prebuild-cycle            "Build 5-10 church profiles + pre-built room concept envelopes per cycle."
*/15 * * * *     chain-to-room-engine      "Drop concepts to room-engine."
0 */1 * * *      notification-cycle        "Draft pastor notifications for fresh pre-builts."
0 */6 * * *      claim-funnel-track        "Track per-church state. Surface unclaimed-after-72h to creators for follow-up."
0 12 * * *       content-refresh           "Refresh content for live unclaimed rooms (new sermons, upcoming events)."
*/30 * * * *     compliance-check          "Apple 5.6.2 + Google compliance review on new room concepts."
```

---

## Cron registration script (run after install)

Save as `08_install_cron.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

register() {
  local profile="$1" name="$2" schedule="$3" prompt="$4" skill="${5:-}"
  local skill_arg=""
  [[ -n "$skill" ]] && skill_arg="--skill $skill"
  HERMES_HOME="$HOME/.hermes-$profile" hermes cron create \
    --name "$name" \
    --schedule "$schedule" \
    --prompt "$prompt" \
    $skill_arg || echo "[WARN] $profile/$name registration failed"
}

# Boss
register boss "strategic-pulse" "*/5 * * * *" "Read all 13 status files, last 1h blackboard, growth narrative, eng feature pipeline, brand artifacts, approved_orders, escalations, PERFORMANCE. Form strategic intent. Write 1-5 orders to factory/orders/ this cycle."
register boss "creative-pulse" "*/5 * * * *" "Look at full company state with fresh eyes. What would sleepy human boss not have thought of? Write 1-2 creative orders this cycle."
register boss "strategic-memo" "0 */4 * * *" "Write wiki/lessons/strategic_<date>.md."
register boss "territory-review" "0 0 * * *" "Write wiki/lessons/territory_<date>.md."
register boss "hourly-digest" "0 * * * *" "Emit hourly digest to Telegram main."

# Supervisor
register supervisor "sign-orders" "*/5 * * * *" "Read new orders. Sign in-envelope. Escalate novel."
register supervisor "day-night-router" "*/5 * * * *" "Read QUIET_HOURS. Day=immediate Telegram. Night=queue silently. Process founder taps."
register supervisor "pending-batch-reminder" "0 */3 * * *" "If unactioned escalations from past 3h: fire ONE batched reminder."
register supervisor "morning-digest" "30 7 * * *" "Comprehensive overnight summary + batch of queued escalations."

# HR
register hr "route-orders" "*/5 * * * *" "Read approved_orders. Route to teams. Write assignments/."
register hr "health-check" "*/5 * * * *" "Status freshness check. Restart stale."
register hr "resource-check" "*/5 * * * *" "Provider spend check per HARD_RULES §1."
register hr "skill-curator" "*/15 * * * *" "Review new auto-skills."
register hr "log-scan" "*/10 * * * *" "Tail activity.log for errors."
register hr "gateway-restart-check" "0 */2 * * *" "Verify Telegram gateway."
register hr "daily-housekeeping" "0 3 * * *" "Rotate logs, archive approvals."

# Conductor
register conductor "throughput-monitor" "*/5 * * * *" "Compute per-profile throughput. Identify imbalances."
register conductor "cadence-adjust" "*/5 * * * *" "Apply cron edits per imbalance."
register conductor "cron-health-write" "*/15 * * * *" "Update cron_health.json."
register conductor "beat-coordination" "0 */1 * * *" "Verify beat ordering."

# Growth
register growth "funnel-pull" "*/10 * * * *" "Pull metrics. Deltas. Top/bottom 3."
register growth "performance-write" "*/10 * * * *" "Update PERFORMANCE.md + narrative."
register growth "boss-feed" "*/10 * * * *" "Write to boss inbox if significant signal."
register growth "growth-memo" "0 */6 * * *" "Write wiki/lessons/growth_<date>.md."
register growth "daily-growth-memo" "0 0 * * *" "Full daily memo."

# Eng
register eng "observation-translate" "*/10 * * * *" "Translate marketing observations to feature specs. File to dev."
register eng "ship-readout" "*/10 * * * *" "Translate dev ships to brand exploitation briefs."
register eng "product-metrics" "*/30 * * * *" "Pull product analytics."
register eng "pipeline-update" "0 */6 * * *" "Update wiki/feature_pipeline.md."

# Brand
register brand "brand-sync" "*/10 * * * *" "Sync canonical artifacts to latest signals."
register brand "campaign-brief-gen" "*/10 * * * *" "Generate per-team content briefs for new campaigns."
register brand "calendar-refresh" "0 */2 * * *" "Refresh CALENDAR.md."
register brand "voice-snapshot" "0 6 * * *" "Daily voice snapshot."
register brand "blackboard-voice" "*/15 * * * *" "Answer voice questions."

# room-engine
register room-engine "concept-cycle" "*/10 * * * *" "Generate 5-15 room concepts."
register room-engine "template-performance" "*/10 * * * *" "Update template kill/scale."
register room-engine "recurring-rooms" "*/30 * * * *" "Maintain recurring rooms."
register room-engine "killswitch-pass" "0 */2 * * *" "Kill flopped concepts."
register room-engine "chain-to-video" "0 */1 * * *" "Chain high-viral concepts to video."

# video
register video "render-cycle" "*/10 * * * *" "Render 5-30 variants per brief."
register video "caption-gen" "*/10 * * * *" "Platform-specific captions."
register video "hook-library" "*/30 * * * *" "Refresh hook library."
register video "audio-trends" "*/30 * * * *" "Trending audio update."
register video "chain-to-distro" "*/10 * * * *" "Batch to distro."
register video "render-spend" "0 */1 * * *" "Track spend."

# distro
register distro "listen-cycle" "*/2 * * * *" "Multi-platform scrape. Push trends to room-engine."
register distro "post-cycle" "*/5 * * * *" "Route distribution batches."
register distro "engagement-track" "*/15 * * * *" "Per-post engagement marks."
register distro "email-personalization" "*/15 * * * *" "Per-pastor draft."
register distro "email-batch" "*/30 * * * *" "Batch 50 drafts into approvals."
register distro "reply-handler" "*/10 * * * *" "Process inbound replies."
register distro "account-rotation" "0 */2 * * *" "Rotate seed accounts."
register distro "performance" "*/30 * * * *" "Update PERFORMANCE.md."

# sermons
register sermons "feed-monitor" "*/15 * * * *" "Check pastor feeds."
register sermons "sermon-process" "*/15 * * * *" "Download, transcribe, clip."
register sermons "caption-correct" "*/15 * * * *" "Theological term accuracy."
register sermons "chain-to-distro" "*/15 * * * *" "Drop clips to distro."
register sermons "weekly-brief" "0 12 * * 0" "Weekly per-pastor brief."
register sermons "onboarding-poll" "0 */6 * * *" "Reach out for clip auth."

# creators
register creators "pipeline-cycle" "*/15 * * * *" "Identify next-step creators."
register creators "creator-prospect" "0 */2 * * *" "5-10 new candidates."
register creators "pipeline-track" "0 */6 * * *" "Surface stuck >7 days."
register creators "partnership-coord" "*/15 * * * *" "Coordinate active partnerships."
register creators "pastor-as-creator" "0 */4 * * *" "Build creator profiles for creator-shaped pastors."

# dev
register dev "feature-spec" "*/30 * * * *" "Read eng specs. Scope. File PRs."
register dev "in-progress" "*/15 * * * *" "Continue implementations."
register dev "ship-announcer" "*/15 * * * *" "Announce ships."
register dev "feature-pipeline" "0 */6 * * *" "Maintain pipeline."
register dev "product-analytics" "*/30 * * * *" "Pull metrics."
register dev "flag-monitor" "0 */1 * * *" "Recommend rollout."

# churches
register churches "prebuild-cycle" "*/15 * * * *" "Build 5-10 profiles + room concepts."
register churches "chain-to-room-engine" "*/15 * * * *" "Drop concepts to room-engine."
register churches "notification" "0 */1 * * *" "Draft pastor notifications."
register churches "claim-funnel" "0 */6 * * *" "Track funnel; surface unclaimed-after-72h."
register churches "content-refresh" "0 12 * * *" "Refresh live unclaimed rooms."
register churches "compliance" "*/30 * * * *" "Apple/Google compliance review."

echo "[OK] All cron jobs registered"
hermes cron list 2>/dev/null | head -50
```

---

## Density math

Hot tier (5 min): boss × 2 + supervisor × 2 + hr × 3 + conductor × 2 + distro × 2 = 11 fires per 5 min = 132/hour
Warm tier (10 min): growth × 3 + eng × 2 + brand × 2 + room-engine × 2 + video × 3 + distro × 1 = 13/10 min = 78/hour
Standard (15 min): hr × 2 + brand × 1 + sermons × 4 + creators × 2 + churches × 2 = 11/15 min = 44/hour
Half-hourly: distro × 2 + video × 2 + dev × 4 + churches × 1 = ~22/hour
Hourly+: ~10/hour

Total: ~285 fires/hour. ~6,800/24h. Comfortable inside Hermes' lock-protected scheduler. Real ceiling is provider rate limits — hr monitors.
