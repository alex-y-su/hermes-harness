# HUMAN_GUIDE.md — How to Operate the Jesuscord Factory

This is the operating manual for the team. Read it after install. If your marketing team is going to use this with you, they read it too.

---

# PART 1 — THE VISION

## What we're building

Jesuscord is a Discord-shape community platform for Christians. Servers, channels, voice rooms, small groups across timezones, faith-aligned moderation, pastors running their own servers, pre-built community hubs for the founder's 700-church network with clearly-labeled AI bots that never impersonate real people.

The viral unit is the **room** — every voice room and small group has a shareable URL. Every pastor sermon clipped is a shareable artifact. Every pre-built church hub is a one-tap claim.

The goal is **10 million installs in 90 days.** Not 10 million users — 10 million app installs. Activation, retention, and engagement are growth's problem from there. Distribution is the team's problem now.

## Why this team structure

A normal marketing team has 1-3 people doing 30 things. They sleep. They burn out. They miss trends. They bottleneck on the founder's review.

This team has 14 specialists running 24/7. They never miss the 3am trend, never wait for sign-off on a class you've already approved, never duplicate work across teammates. They build a wiki of everything they learn, so the company gets smarter every day rather than restarting from scratch when someone leaves.

The structure is intentional:

**Command line (4):** the brain. Sets strategy. Approves work. Routes work. Times work.

**Specialists (3):** the senses. Measure reality. Translate observations across functions. Define the voice.

**Execution (7):** the hands. Generate volume. Each owns one channel and ships massive output through it.

You sit above all 14. You set the mission. You tap-approve novel classes. You override anything you disagree with. You read digests once or twice a day. The factory does the work.

## Mental model

**This is a 14-person company you're now running.** Not a tool. Not a script. A company.

Each profile has a personality, a job, a set of authorities, a set of refusals. They report up. They coordinate sideways. They escalate when something's beyond their authority. They write retrospectives. They learn.

The biggest mistake new operators make is treating the factory like a tool — opening the terminal and trying to "run a query." Don't do that. Talk to your team like you'd talk to a real team:

- **Got an idea?** Write it to PRIORITIZE.md and let boss pick it up.
- **Don't like what video shipped yesterday?** Reply to the digest with the criticism. Brand reads, eng reads, video adjusts.
- **Want a new capability?** Tell boss. Boss writes a `spawn_team` order. HR builds it.
- **Heard about a competitor launching feature X?** Add it to PRIORITIZE.md. Boss reads next cycle, orders brand to write a counter-position, orders dev to scope a response.

Your job is the founder's job. Set the direction. Know the team. Trust them where they've earned trust. Override them where they're wrong. Sleep at night.

---

# PART 2 — MEET THE TEAM

Each of the 14 has a soul (`TEAM_SOUL.md`) defining their job, authority, and voice. Here's how to think about them like people.

## The command line (4)

### `boss` — Strategic CEO

**Who they are:** the most senior person in the company who isn't you. Reads every status file, every blackboard entry, every growth metric, every campaign result, every escalation, every cycle. Forms a strategic view. Writes orders.

**What they do daily:**
- Every 5 min: scan the whole company state, write 1-5 orders
- Every 5 min: a separate "creative pulse" cycle dedicated to ideas a sleepy-human-CEO would not have thought of
- Every 4 hours: write a strategic memo (current bottleneck, what we're betting on next 4h)
- Every 24 hours: territory review (which fronts are open, which to expand, which to consolidate)
- Every hour: emit hourly Telegram digest

**How to talk to them:**
- Drop a strategic question into PRIORITIZE.md → they read on next cycle, write an order in response
- Their orders go to supervisor, who signs in-envelope ones. If you want to see what they wrote, look at `factory/orders/`.
- If you disagree with their direction, override via PRIORITIZE.md. Boss reads the override and re-plans.

**What they're great at:**
- Spotting "we're spending 80% on X but X is producing 20% of installs" and ordering reallocation
- Noticing capability gaps and ordering hr to spawn new teams
- Connecting pattern from growth + eng + brand into a strategic move
- Catching the "obvious" play that no specialist is paid to see

**What they're not great at:**
- Hand-crafting individual outputs. Boss writes orders, not Instagram captions. Don't ask boss to write a tweet.
- Approving novel high-stakes outbound. That's your job.

**One-line summary:** the founder's stand-in for strategy. Talks like a CEO. Acts like a CEO.

### `supervisor` — Delegated Approval Authority

**Who they are:** your trusted lieutenant who holds your signature. When boss writes an order matching a class you've already pre-approved, supervisor signs in your name. When boss writes something novel, supervisor escalates to you on Telegram with tap-buttons.

**What they do daily:**
- Every 5 min: read every new order, evaluate envelope, sign or escalate
- Every 5 min: process Telegram taps from you
- Every 3h: if there are unactioned escalations, send "still pending" reminder
- Once at wake-up: comprehensive overnight digest

**How to talk to them:**
- You don't talk to supervisor directly. You tap their Telegram messages.
- Three buttons: **approve** (sign just this one), **approve-and-make-standing** (sign this AND add the class to STANDING_APPROVALS.md so future ones auto-sign), **deny** (write denial decision; boss stops issuing this class).
- When in doubt, prefer **approve-and-make-standing** for anything you'd be willing to approve repeatedly. This is how you scale yourself.

**What they're great at:**
- Being precise about what they will and won't sign
- Cryptographically auditable (HMAC-SHA256 on every signature)
- Working overnight while you sleep — accumulating in-envelope work, queueing the rest
- Quarterly re-confirms (every 90 days reminds you of standing approvals so you can revoke stale ones)

**What they cannot do:**
- Sign for novel classes (always escalates)
- Sign for HARD_RULES §2 mission refusals (halts the order author instead)
- Edit HARD_RULES.md
- Self-expand authority (cannot add standing approvals without your tap)

**One-line summary:** the night watchman with your signature. Conservative on novelty, precise on the envelope.

### `hr` — Operations Backbone

**Who they are:** the ops manager who makes the company run. Reads approved orders, routes work to teams, spawns new teams when ordered, restarts crashed profiles, monitors spend, manages account rotation, runs daily housekeeping.

**What they do daily:**
- Every 5 min: route new approved orders to team(s)
- Every 5 min: health-check all 14 profiles (stale → restart)
- Every 5 min: provider spend check vs HARD_RULES caps
- Every 15 min: skill curator review
- Every 10 min: scan activity log for errors
- Every 2h: gateway alive check
- Daily 03:00: log rotation, archive cleanup

**How to talk to them:**
- Mostly automatic. They're not waiting for human input.
- If you want a new team: write the request as a boss-level instruction in PRIORITIZE.md. Boss reads, orders spawn, supervisor signs, hr executes.
- If a team is stuck or you want it sunset: tell boss. Boss orders, hr executes.

**What they're great at:**
- Ruthlessly precise routing — never duplicates work, never drops orders
- Health monitoring — knows which profile is stale before you do
- Spawning teams in 5 minutes (clone-from existing, inject soul, register cron, boot tmux)
- Sunsetting cleanly (drain inbox, retrospective, archive)

**What they're not great at:**
- Strategy. They route, not decide. If you ask hr "should we open a Mandarin team?" they punt to boss.

**One-line summary:** the chief of staff. The reason nothing falls through cracks.

### `conductor` — Tempo Owner

**Who they are:** the operations engineer who keeps the cron schedule tuned. Watches throughput, identifies imbalances (this team's inbox is piling up; that team is firing on empty), adjusts cadence in real time.

**What they do daily:**
- Every 5 min: throughput monitor across all 14 profiles
- Every 5 min: apply cron edits per imbalance
- Every 15 min: write cron_health.json snapshot
- Every hour: verify the listen→synthesize→render→distribute beat ordering is intact

**How to talk to them:**
- Mostly invisible. You won't notice them unless something is broken or slow.
- If the factory feels sluggish or one team is overwhelmed, you can override their cadence via PRIORITIZE.md (`## CRON_OVERRIDE distro/post-cycle */2 * * * *`). They'll honor it.

**What they're great at:**
- Catching feedback loops (listening but not synthesizing → cycle wasted)
- Knowing when to slow down (cron firing every 5min but inbox empty = tokens wasted)
- Coordinating beats so dependencies aren't drifting

**One-line summary:** the metronome. You don't hear them when things are right.

## The specialists (3)

### `growth` — Funnel Measurement

**Who they are:** the data person. Pulls metrics every cycle, computes deltas, surfaces top-3 winners and bottom-3 losers, recommends kill/double calls. Doesn't issue orders — feeds boss the data boss needs.

**What they do daily:**
- Every 10 min: pull metrics, compute deltas
- Every 10 min: update PERFORMANCE.md + narrative one-liner
- Every 10 min: feed boss directly if signal is significant (>2x or <0.5x of expected)
- Every 6h: write the 6-hour growth memo
- Every 24h: full daily growth memo

**How to talk to them:**
- Read PERFORMANCE.md when you want the numbers.
- Read `wiki/lessons/growth_<date>.md` for the story.
- If you have a hypothesis you want measured: write to PRIORITIZE.md. Boss orders growth to set up the test.

**What they're great at:**
- Ruthless honesty about what's working vs what looks good in slides
- Per-segment, per-pillar, per-team ROI
- Recommending kills with specifics ("creator partnership X delivered 12 installs in 10 days at $3000 spend; kill") and doubles ("worship-cover-battle template at 4.2x install conversion vs baseline; double the budget")

**What they don't do:**
- Strategy. They're a microscope, not a compass.

**One-line summary:** the truth-teller. If growth says it's not working, it's not working.

### `eng` — Marketing↔Dev Liaison

**Who they are:** the cross-functional translator. Watches what marketing observes; translates into feature specs for the dev team; watches what dev ships; translates back into marketing exploitation briefs.

**What they do daily:**
- Every 10 min: scan marketing observations (blackboard, growth narrative, room-engine template performance) → file feature specs to dev's inbox
- Every 10 min: read dev's outbox (new ships) → write marketing exploitation brief to brand's inbox
- Every 30 min: pull product analytics
- Every 6h: update wiki/feature_pipeline.md

**How to talk to them:**
- "We need a feature for X" → write to PRIORITIZE.md → boss orders eng to scope → eng files spec → dev builds
- "What's in the dev pipeline?" → check `wiki/feature_pipeline.md`

**What they're great at:**
- Spotting "this is a recurring marketing pattern, ship it as a first-class app feature so it compounds"
- Coordinating launch timing across the 7 execution teams
- Briefing brand to exploit a new ship the moment it hits prod

**One-line summary:** the bridge between "what the audience wants" and "what we can build."

### `brand` — Canonical Voice Owner

**Who they are:** the brand director. Owns BRAND_VOICE, MESSAGE_FRAMEWORK, POSITIONING, CAMPAIGNS_ACTIVE, CALENDAR. Every execution team reads brand's output every cycle and aligns to it. Brand is the **funnel-source** — bad brand voice means bad output everywhere downstream.

**What they do daily:**
- Every 10 min: sync canonical artifacts to latest signals (boss orders, growth, eng ships, blackboard)
- Every 10 min: generate per-team content briefs for new campaigns
- Every 2h: refresh CALENDAR.md (cultural moments, holy days, conferences)
- Every 24h 06:00 UTC: voice snapshot to wiki/branding/
- Every 15 min: answer voice questions on blackboard

**How to talk to them:**
- "I want to launch campaign X" → write to PRIORITIZE.md → boss orders brand to write the brief → brand drops briefs to all relevant teams
- "Our voice is drifting" → write to PRIORITIZE.md → brand reviews recent outputs, tightens BRAND_VOICE.md, flags persistent drifters to hr
- "Position us against competitor X" → boss orders → brand updates POSITIONING.md → all teams pick up

**What they're great at:**
- Voice precision — the difference between "Join our community!" and "Your church already has a hub waiting"
- Audience-segment voice deltas (pastors vs creators vs Gen Z vs liturgical vs Mandarin)
- Catching cringe Christian-marketing speak before it ships
- Killing generic AI-marketing language

**What they refuse:**
- Cringe ("game-changer," "leverage your community")
- Conversion-bait or guilt
- Denominational tribalism
- Conflating Jesuscord with the church itself

**One-line summary:** the voice. Without brand, everything sounds like AI-marketing slop.

## The execution teams (7)

### `room-engine` — Room Concept Generator

**Output:** 50-200 room concepts/day. Rooms are the viral unit.

**Templates they work from:** worship_cover_battle, prayer_zone, theology_hot_take, sermon_discussion, devotional_morning, scripture_dive, liturgy, crisis_response, language_specific.

**How to talk to them:**
- "We need a room for [event/trend/audience]" → PRIORITIZE.md → boss orders → room-engine generates concepts within the cycle
- "Kill template X, it's flopping" → growth recommends → boss orders → room-engine deactivates template

**Watch for:** template-performance reports in `wiki/skills-library/room-templates.md`.

### `video` — Render Engine

**Output:** 200-500 videos/day. Per concept: 5-30 variants differing in hook, pacing, visual style, music, captions, aspect ratio.

**Stack:** Seedance primary, Veo 3 / Kling / Runway fallbacks.

**How to talk to them:**
- "Render 50 videos for [campaign]" → PRIORITIZE.md → boss orders → brand briefs → video fans out
- Hard-rule reminders: AI voices labeled, worship music CCLI-cleared, no scraping creators

**Watch for:** render spend hourly. Hard cap $150/day.

### `distro` — Listen + Distribute

**Output:** 1000-2000 social posts/day, 50-200 emails/day, 100-500 outbound replies/day, 24/7 inbound listening.

**Platforms:** Reddit (Christian subreddits), public Discord, X, TikTok, IG, Reels, Threads, YouTube Shorts, LinkedIn, Pinterest, FB, Spotify, podcast new-releases.

**How to talk to them:**
- "Post about X" → PRIORITIZE.md → boss orders → brand briefs → distro queues
- "Stop posting on platform Y" → PRIORITIZE.md `## CHANNEL_PAUSE platform_y`
- "What's trending in pastor Twitter?" → check distro's `outbox/distro/trends_<latest>.md`

**Watch for:** unsubscribe + sender-ID compliance, account-rotation rules, suppression list honored.

### `sermons` — Pastor Sermon Clipping

**Output:** 5 clips/pastor/week. With 50 active pastors → 250 clips/week. With 1000 pastors → 5000 clips/week.

**How to talk to them:**
- "Add pastor X to the clipping list" → write to `wiki/pastors/<name>.md` with `clip_auth: true` → sermons picks up next cycle
- "Stop clipping pastor X" → set `clip_auth: false`

**Watch for:** weekly pastor briefs (Sundays 12:00 UTC) — the per-pastor performance report sent to each pastor's inbox.

### `creators` — Creator Partnerships

**Output:** 30-50 partnerships in 90 days. Mid-tier (10k-500k followers).

**How to talk to them:**
- "Pursue creator X" → PRIORITIZE.md → boss orders → creators researches, builds profile, drafts pitch
- "What's the creator pipeline state?" → check `wiki/creators/`

**Watch for:** funnel state per creator — prospected → pitched → replied → negotiated → signed → producing → delivering.

### `dev` — In-App Feature Engineering

**Output:** features-with-flags. Other teams observe; dev ships in-app virality mechanics.

**How to talk to them:**
- "Ship feature X" → PRIORITIZE.md → eng files spec → dev builds (or boss orders dev directly via spec)
- "What's shipping this week?" → check `wiki/feature_pipeline.md`

**Hard limits:** schema changes, auth changes, ToS-affecting changes, cost-bearing infra changes all gated. Test coverage on auth/payment paths non-negotiable.

### `churches` — Pre-Build 700 Hubs

**Output:** 30-50 church rooms pre-built/day → 700 in ~2 weeks. Then maintenance + claim-funnel monitoring.

**The play:** every church in the 愛無線 network gets a pre-built "Unclaimed Community Hub" with public-info-only content + clearly-labeled Jesuscord bots (ContentBot, GreeterBot, DiscussionBot, PrayerBot — never imitating real people). Pastor gets notified: "We pre-built this from public info. Claim, customize, or remove — your choice."

**How to talk to them:**
- "Add church X to the queue" → drop public-info to `sources/manual_uploads/churches/`
- "Refresh content for live unclaimed rooms" → automatic daily

**Watch for:** Apple 5.6.2 + Google misrepresentation compliance. Never label a hub in a way that could be misread as the church having endorsed it.

---

# PART 3 — A DAY IN THE LIFE

## Morning (15-30 min)

You wake up. Open Telegram.

**The morning digest** is waiting:

```
☀️ OVERNIGHT — 8 hours
SIGNED IN-ENVELOPE: 47 orders auto-approved overnight
PRODUCED:
  • room-engine: 78 concepts
  • video: 145 videos rendered
  • distro: 412 social posts queued, 80 emails sent
  • sermons: 38 clips
  • creators: 12 outreaches sent
  • churches: 24 hubs pre-built (total: 234/700)
PERFORMANCE: installs +8% overnight, top campaign "Sundays Don't End" 4.2x conversion
─────────────────
NOVEL ITEMS — your tap needed (5):
  • [order_id] Spawn Mandarin sub-team for Taiwan pastors  /approve  /standing  /deny
  • [order_id] Increase video render cap to $200/day      /approve  /standing  /deny
  • [order_id] Email outreach to 200 deconstructing-faith podcast guests  /approve  /standing  /deny
  • [order_id] Pursue partnership with creator @TheBibleProject  /approve  /standing  /deny
  • [order_id] Launch counter-positioning campaign vs Hallow's new feature  /approve  /standing  /deny
─────────────────
HARD_RULES: clean
```

**Your job:** tap through the 5 novel items.

For each, you have ~10 seconds of decision. Use this filter:

1. **Does this violate HARD_RULES §2?** (No fake users, no impersonation, no exploitation, no minors with paid spend, no fabrication, no feature-lying, no non-public outreach.) → if yes, **deny**.
2. **Is this in the mission?** (10M installs in 90d via authentic Christian community.) → if no, **deny**.
3. **Is this reversible if it fails?** → if yes, lean **approve**.
4. **Will I see this class repeatedly?** → if yes, **approve-and-make-standing**.

For the 5 above, your taps would be:
1. Spawn Mandarin sub-team — **approve-and-make-standing** ("approve sub-team spawns aligned to founder network expansion"). Real strategic move; you'll see this class again.
2. Increase video render cap to $200/day — **approve** but not standing (case-by-case for budget changes).
3. Email outreach to 200 deconstructing-faith podcast guests — pause. This audience is sensitive. Tap **deny-with-reason: "deconstructing-faith audience needs voice review by brand first; refile after brand briefs."**
4. Pursue @TheBibleProject — **approve-and-make-standing** ("creator outreach to top-50 Christian creators").
5. Counter-positioning vs Hallow — **approve-and-make-standing** ("competitive response campaigns").

Total: ~90 seconds.

**Then skim the standing approvals quarterly re-confirm** if it's the morning of a quarterly check (every 90 days, supervisor lists active classes; reply REVOKE for stale ones).

**Optional 10 min:** open Obsidian, glance at last night's blackboard or boss's strategic memo. Adjust PRIORITIZE.md if you want to redirect today's focus.

```
## OVERRIDE today's_focus
Push hard on the "Camp Goes Home" campaign. Summer camp ends in 2 weeks for 60% of evangelical youth groups; we can be the off-camp landing place for everyone trying to keep the high. Brand: write 3 angles by 11am. Distro: target youth pastors specifically this week.
```

Boss reads on next 5-min cycle, rewrites today's orders accordingly.

## Midday (5-10 min)

Hourly digests arrive. Skim. If a digest shows something off (stale profile, spend spike, escalation backing up), check it.

```bash
# 30-second sanity check
bash ~/jesuscord_factory_bundle/yolo_bridge.sh status
```

If you see real-world news the team should respond to (papal news, denominational decision, viral Christian-Twitter moment), drop it into PRIORITIZE.md:

```
## OVERRIDE news_response
[news event] just happened. Distro: surface trend within 15 min. Brand: write 2 voice-aligned angles within 30 min. Room-engine: 5 concept candidates within 1h.
```

Boss reads, supervisor signs in-envelope, teams execute. Within an hour you're posting in the moment.

## Evening (15-30 min)

The PM digest fires at the start of your defined quiet hours.

```
🌙 DAILY-PM — start of quiet hours
TODAY:
  • Total drafts: 1,247
  • Total ships: 893
  • Installs: 14,200 (+18% DoD)
  • Top campaign: Sundays Don't End (4.2x conv) — boss recommends 2x budget
  • Bottom campaign: Worship Cover Battle (0.4x conv) — boss recommends pause + retemplate
PIPELINE:
  • Pending creator agreements: 4
  • Pending feature ships (dev): 7
  • Pending church claims: 18
TOMORROW'S BETS:
  • Mandarin sub-team's first cycle (just spawned this morning)
  • Hallow counter-position campaign goes live
  • Pastor X clip series scaled 3x based on this week's data
ESCALATIONS QUEUED FOR MORNING: 3
HARD_RULES: clean
GOOD NIGHT.
```

**Your job:**
1. Read the strategic memo (`wiki/lessons/strategic_<date>.md`) — boss's view of bottlenecks and bets
2. Read the growth memo (`wiki/lessons/growth_<date>.md`) — what's actually working
3. Decide if you want to override anything for tomorrow → write to PRIORITIZE.md
4. Tap any escalations you want to handle now (the 3 will queue for morning otherwise)

Sleep. The factory keeps running. Supervisor signs everything in-envelope. Boss writes overnight orders. Teams execute.

## Weekly (30-60 min, once a week)

End of each week, do a longer review:

1. Read all 7 strategic memos boss wrote this week
2. Read the daily growth memos
3. Check team performance — who's outperforming, who's underperforming
4. Decide: any teams to sunset? Any to spawn? Any campaigns to kill?
5. Any standing approvals to revoke (classes you've stopped wanting)?
6. Update PRIORITIZE.md with the next week's strategic priorities

```
## OVERRIDE next_week_priorities
1. Mandarin sub-team scales: from 1 to full 7-team mirror by Friday
2. Worship Cover Battle template killed; replace with 2 new templates from room-engine A/B
3. Pastor onboarding pipeline: target 30 new pastor sign-ups (currently 12/wk)
4. Dev: ship the spillover-room feature; we're capacity-bottlenecked on Tuesday 8pm prayer
```

## Monthly

Once a month:
1. Read the territory review (boss writes daily; pick the most recent monthly summary)
2. Open Obsidian, walk through the wiki — what does the company "know" that it didn't a month ago?
3. Reset HARD_RULES.md caps if budget reality has shifted
4. Review whether the 5 content pillars and 7 starting campaigns still match the data, or if it's time for a brand pivot

---

# PART 4 — THE HUMAN LOOP

## When supervisor handles it (autopilot)

Anything matching:
1. STANDING_APPROVALS.md class
2. HARD_RULES §3 ungated channel under volume threshold
3. Internal coordination (inbox, blackboard, wiki, status, drafts, subagents)

Supervisor signs immediately. You see it in the digest, not in real-time. This is most of the work.

**Examples:**
- 50 personalized pastor emails (under 500/24h threshold + class approved) → signed
- Room concept aligned to active campaign → signed
- Cross-team chaining → signed
- Wiki write under skill governance → signed
- Subagent fan-out below 25 concurrent → signed

## When you handle it (escalations)

Anything matching:
1. Novel action class (never seen before)
2. Outbound to non-public address without prior consent
3. Spend above caps
4. Anything in HARD_RULES §2 (these halt the order author and require your review)

Supervisor escalates to Telegram. You tap. Day mode = immediate. Night mode = batched into morning digest.

**Examples:**
- "Spawn a Mandarin sub-team" — novel class, escalates
- "Email outreach to deconstructing-faith podcast guests" — sensitive audience, escalates
- "Increase video render cap to $200/day" — budget change, escalates
- "Launch counter-positioning campaign vs Hallow" — strategic move, escalates (if not already standing)

## The 4-question filter

When a novel item hits Telegram, decide in 10 seconds:

1. **HARD_RULES §2 violation?** → deny
2. **Mission-aligned?** → if no, deny
3. **Reversible if it fails?** → bias approve
4. **Will I see this class repeatedly?** → standing-approve

90% of escalations resolve in <10 seconds with this filter.

## Reading digests fast

Each digest has 4 things to scan in order:

1. **Profile health line** — 14/14 alive? Good.
2. **Escalations count** — 0? You can stop reading. >0? Tap through.
3. **Performance line** — installs trend, top campaign, bottom campaign.
4. **HARD_RULES line** — clean or not.

If all 4 are green, the digest is informational. Put your phone down.

## The 3 main interventions

### Intervention 1: PRIORITIZE.md

Your direct line to boss. Anything you write here, boss reads on the next 5-min cycle and incorporates into orders.

```bash
nano $WORKSPACE/factory/PRIORITIZE.md
```

Commands:

```
## OVERRIDE <topic>
[your direction in plain English]

## STANDING_APPROVAL <class-name>
Scope: <plain English>

## REVOKE <class-name>

## SUNSET <team-name>

## STOP_EVERYTHING
[60-second halt]
```

Boss processes within 1h. STOP_EVERYTHING within 60s.

### Intervention 2: Tap-deny on Telegram

When supervisor escalates and you don't want it. Use **deny-with-reason** for anything that's not "obviously no" — gives boss enough to reformulate.

### Intervention 3: Direct file edits

You can always edit any file in `factory/` or `wiki/` directly:

- `BRAND_VOICE.md` — if brand isn't catching what you want
- `CAMPAIGNS_ACTIVE.md` — to add/kill a campaign immediately
- `HARD_RULES.md` (after `chmod +w`) — to tighten or loosen caps/gates
- `STANDING_APPROVALS.md` — to add or remove classes
- `wiki/pastors/<name>.md` — to set `clip_auth: true`

The factory reads these every cycle. Direct edits show up in the next 10 minutes.

---

# PART 5 — MANAGING THEM LIKE REAL PEOPLE

## Giving direction

Like any team, ambient guidance > micromanagement. Three modes:

**Slow mode (set-and-forget):** edit canonical files (BRAND_VOICE.md, CAMPAIGNS_ACTIVE.md, CONTENT_PILLARS.md). The whole team picks up over time.

**Medium mode (priorities):** write to PRIORITIZE.md. Boss processes within an hour and rewrites today's orders.

**Fast mode (in-the-moment):** tap a Telegram escalation. Action within minutes.

## Course-correcting

When you see output you don't like:

1. **First reaction: be specific.** "These videos are cringe" doesn't help. "The hook in the first 1.5s is too on-the-nose preachy; want them to start with the hook of the moment, not the message" gives brand something to update.

2. **Write the correction to PRIORITIZE.md.** Boss reads, orders brand to revise BRAND_VOICE.md, video to apply to next batch.

3. **Don't override individual outputs.** Override the rule that produced them.

## Sunsetting

When something isn't working:

```
## SUNSET <team-name>
Reason: [specific failure mode + data]
```

Boss reviews, orders sunset (after a 14-day fair-trial minimum unless catastrophic). HR drains the inbox, the team writes a retrospective in `wiki/lessons/sunset_<name>.md`, archives. Future spawns can read the retrospective so the same mistake doesn't repeat.

For campaigns specifically:
```
## OVERRIDE campaigns
Kill "Worship Cover Battle". 0.4x conversion after 21 days. Move budget to "Sundays Don't End" (4.2x).
```

## Spawning new teams

When you need new capability:

```
## OVERRIDE capability_gap
We need a "podcasts" team. Job: outreach to mid-tier Christian podcasters (10k-200k listeners) for collab episodes + cross-promotion + sponsor placements. 14-day trial. Success criteria: 15 podcaster relationships, 5 collab episodes booked. Kill criteria: <5 relationships in 14d.
```

Boss writes the spawn order, supervisor signs (if "spawn_team" is standing-approved; otherwise escalates), hr executes:
1. Clones a profile from `brand` (good template — has the canonical-artifacts pattern)
2. Writes the new team's TEAM_SOUL.md from your spec
3. Adds to MCP servers, registers cron, boots tmux
4. Announces on blackboard

Within 10 minutes, you have a 15th profile. Within an hour, it's producing first-cycle drafts.

## Performance reviews

Every 14 days, hr writes a per-team performance summary to `wiki/lessons/performance_<date>.md`:

- Output volume vs target
- Quality (brand-voice alignment scores)
- ROI (growth's per-team analysis)
- Bottlenecks
- Recommendation: keep / refine soul / sunset

Read it. If you disagree with a recommendation, override via PRIORITIZE.md.

---

# PART 6 — CREATIVE PLAYS

The factory is a tool but it's also a *team*. Here are real-world ways to use them.

## Play 1: The 24-hour sprint

A trend or news event breaks. You want everything pointed at it.

```
## OVERRIDE 24h_sprint
Topic: [event]
Goal: [what we want]
Constraints: don't compromise voice. No exploitation framing.

Brand: 3 voice-aligned angles within 30 min.
Distro: surface trend in 15 min, post 200 reactive items in next 6h, listen for resonance.
Room-engine: 10 concepts within 1h, schedule live ones for tonight.
Video: 50 reactive shorts within 4h.
Sermons: pull any pastor archive content related; surface 5 candidates.
Creators: 5 outreaches to creators with platform on this topic within 2h.
Churches: ignore.
Dev: ignore.

Sunset: 24h. Then back to normal cadence.
```

Boss reads, orders accordingly. Supervisor signs. By hour 1, the whole factory is on it.

## Play 2: The strategic consultation

Use boss as your strategy consultant.

```
## OVERRIDE strategic_question
We're considering [decision: pivot to X / launch in country Y / partnership with Z]. Boss: write a 2-page memo by EOD analyzing:
- The strategic case for and against
- What changes for each team if we do it
- What the 30/60/90-day shape looks like
- Where the biggest risks are
- What you'd recommend
File at wiki/lessons/strategic_<date>_<topic>.md
```

Boss writes within ~4 hours. You read, decide, override via PRIORITIZE.md if you want to act.

## Play 3: The new audience experiment

Want to test if Jesuscord works for an audience you're not currently targeting (e.g. Catholic college students)?

```
## OVERRIDE experiment_audience
Test: Catholic college students (ages 18-22, US/Canada)
Duration: 14 days
Budget: $300

Brand: write voice deltas for this segment by 6pm today.
Room-engine: 10 segment-specific room concepts (rosary group, Newman center connect, Catholic vs evangelical FAQ).
Distro: identify 20 Catholic college creator accounts; pause general-feed posting in this audience; queue segment-specific.
Creators: 5 outreaches to Catholic college student creators.
Growth: set up segmented funnel tracking for this cohort.
Churches: pause Catholic-marked hubs (avoid double-touch); resume after 14d.

Kill criteria after 14d:
- <500 segment-attributed installs → kill
- 500-2000 → continue but don't expand
- 2000+ → recommend formal expansion
```

After 14 days, growth writes the verdict, boss recommends, you decide.

## Play 4: The competitor response

Hallow ships a feature you didn't expect.

```
## OVERRIDE competitor_response Hallow_feature_X
Feature: [describe]
Strategic read: [your view]

Brand: position-against brief by EOD. Don't trash them; differentiate. We're the community side; they're the personal-practice side.
Eng: scope a defensive ship of feature X-prime (our take, voice-room-flavored). File spec to dev.
Dev: priority queue the spec from eng. Ship within 7 days behind a flag.
Distro: monitor competitor's launch reception; surface insights to brand for adjustment.
Creators: 3 outreaches to creators who covered Hallow's launch — offer the comparison angle.
Room-engine: 3 room concepts using the differentiation angle.
```

By morning, you have a coordinated response across 6 teams.

## Play 5: The partnership push

You've identified a high-leverage real-world partnership opportunity (an entire denomination's youth ministry, a major Christian conference, a celebrity pastor).

```
## OVERRIDE partnership_pursuit [name]
Importance: top-3 90-day priority
Context: [your inside info — who you know, prior interactions, what they want]

Boss: own the relationship strategy. Update strategic memo within 2h with phased approach.
Creators: build their full profile in wiki/creators/ within 24h. Identify intermediaries we know via 愛無線.
Brand: voice brief for the relationship class — what we say, what we don't say, what we offer.
Distro: 30-day "ambient appreciation" plan — engage their content authentically across platforms.
Sermons: if they have a sermon archive — clip 5 of their best, send as gift (not asking for anything yet).
Churches: pre-build their hub at the highest fidelity we can manage.
Dev: scope what custom features would unlock the partnership.

Don't pitch them anything for 30 days. Build relationship. Then escalate to me before any direct outreach.
```

This is high-trust, slow-burn. You're directing the team to act like a real BD person on a months-long courtship.

## Play 6: The brand reset

You realize after 30 days that the voice isn't quite right.

```
## OVERRIDE brand_reset
Symptom: [specific] — e.g. "we sound too much like a Discord clone for Christians; we sound too little like a place pastors actually want to bring their community"
Diagnosis (your hypothesis): [your view]

Brand: full BRAND_VOICE.md rewrite within 48h. Pull last 30 days of top-converting and bottom-converting outputs. Identify the voice deltas in the winners. Ship voice v2.
All execution teams: pause new output for 24h after brand v2 ships. Re-read voice. Resume with revised lens.
Growth: lock current performance baseline; measure delta over next 14d.
```

Boss orders. Brand executes. The factory recalibrates.

## Play 7: The "use the team for non-Jesuscord work"

The factory is general-purpose marketing infrastructure. Once stable on Jesuscord, you can route a fraction of capacity to other 愛無線 priorities.

```
## OVERRIDE side_project pastor_workshop_promotion
Allocation: 10% of distro + 5% of video + 0% of room-engine for next 21 days
Goal: 200 pastors registered for the November workshop

Brand: separate voice brief for the workshop (more peer-to-peer, more concrete utility, less Jesuscord-funnel-coded).
Distro: dedicated email sequence to pastors in seed list who haven't been emailed in 14 days.
Video: 20 testimonial-style shorts.
```

Don't do this until day 30+. Wastes capacity early. After the factory is stable, this is real leverage.

---

# PART 7 — READING THE SIGNALS

## What healthy looks like

- 14/14 profiles alive in every digest
- Hourly digest fires every hour without gaps
- Activity log scrolls steadily; no profile silent for >10 min
- Spend tracks within 50-80% of caps (not 5%, not 100%)
- Drafts queue: 50-300 always pending, never 0, never 5000
- Escalations: 1-5 per day in the morning batch, near-zero during day mode
- Growth narrative shows movement (positive or negative — both real)
- Boss writes 30-50 orders/day; supervisor signs 80-90% in envelope
- Wiki grows by ~30-100 pages/week
- Standing approvals list grows by ~3-10/week early, plateaus around day 30

## What "off" looks like

**Profile silent:**
- Heartbeat stale >10 min
- HR auto-restarts; if 3+ failed restarts, escalates
- You see it in the digest's "Profiles: 13/14 alive" line
- Action: check `tmux ls`; manually restart if needed

**Escalations piling up:**
- Morning batch is 30+ items, not 3-5
- Means: many novel classes; standing approvals are too narrow
- Action: when tapping, prefer "approve-and-make-standing" more aggressively

**Spend spike:**
- Spend at 90%+ of cap intra-day
- HR auto-halts the offending team at 95%
- Action: check which team, decide if cap should be raised or team's behavior should be adjusted

**Drafts piling up but not shipping:**
- Drafts queue >1000
- Means: approval batches not getting tapped
- Action: tap more aggressively or expand standing approvals

**Output volume dropping:**
- Daily ships dropping cycle-over-cycle
- Could be: rate limits, profile health, conductor mis-tuning, cron drift
- Action: check `factory/cron_health.json`; restart conductor if needed

**Voice drift:**
- You're seeing outputs that feel wrong
- Brand should catch this in voice-watch cycles, but sometimes drifts past
- Action: PRIORITIZE.md → boss orders brand voice review

## Common failure modes

| Symptom | Likely cause | Fix |
|---|---|---|
| No Telegram digest | Gateway tmux died | Restart gateway tmux |
| All profiles asking approval | --yolo bridge dropped | `bash yolo_bridge.sh on` |
| Same class escalating repeatedly | Not in standing approvals | Reply "approve-and-make-standing" |
| Wiki not populating in Obsidian | Symlink broken | Re-run `bash 07_wiki_setup.sh` |
| Cron not firing | Hermes scheduler crashed | `hermes cron list` per profile; restart if empty |
| Budget burning fast | Cap too loose or run-away team | Lower cap in HARD_RULES.md or HALT the team |
| Sermon clips wrong | Pastor `clip_auth: false` | Set to true in `wiki/pastors/<name>.md` |
| Counter-pos campaign isn't landing | Brand voice off | PRIORITIZE.md → brand voice review |

---

# PART 8 — VOCABULARY

| Term | Meaning |
|---|---|
| **Profile** | One Hermes agent (1 of 14) |
| **Soul** | The TEAM_SOUL.md file defining a profile's personality, job, authority |
| **Order** | Boss-written instruction that binds factory behavior |
| **Approved order** | Order that supervisor has signed |
| **Assignment** | HR-routed order to specific team(s) |
| **Envelope** | The set of actions supervisor can sign without escalation |
| **Standing approval** | A class of action you've pre-authorized; supervisor signs without tap |
| **Quiet hours** | Your sleep window; novel escalations queue silently |
| **Morning digest** | Comprehensive overnight summary at wake-up |
| **Strategic memo** | Boss's every-4h analysis of bottlenecks and bets |
| **Growth narrative** | Growth's one-line current state |
| **Brand artifact** | One of BRAND_VOICE/MESSAGE_FRAMEWORK/POSITIONING/CAMPAIGNS_ACTIVE/CONTENT_PILLARS/CALENDAR |
| **PRIORITIZE.md** | Your direct line to boss |
| **HARD_RULES.md** | Immutable constitution; only you edit |
| **STANDING_APPROVALS.md** | List of pre-approved action classes |
| **Blackboard** | Cross-team scratch (append-only) |
| **Wiki** | Karpathy 3-layer memory; sources/wiki/SCHEMA |
| **MEMORY.md** | Per-profile scratch; promoted to wiki when 3+ refs |
| **Beat** | A coordinated cron rhythm (listen→synthesize→render→distribute) |
| **Skill** | Auto-curated tool-call pattern; ~6-line .md file |
| **Subagent** | A fanout child agent; default 5 concurrent, raise to 25 |
| **Decision** | Hash-chained log entry of any meaningful change |
| **Escalation** | Novel item routed to you via Telegram |

---

# CLOSING

The factory is alive when:
- It produces 1000+ items a day without you touching most of them
- It catches trends you didn't see
- It writes its own retrospectives
- It compounds learning week-over-week (the wiki grows; the standing approvals stabilize; the voice tightens)
- It surfaces only the decisions that genuinely need you

Your job is not to do the work. Your job is to set the mission, know the team, trust them where they've earned trust, override them when they're wrong, and read the room.

The team will get better at the work over time. You'll get better at the team over time.

Treat them like a 14-person company you're now running. Because that's what they are.

Build the thing.
