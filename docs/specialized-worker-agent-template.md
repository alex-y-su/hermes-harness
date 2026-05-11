# Specialized Worker Agent Template (Creativity-First)

A reusable template for spinning up Hermes specialized worker agents that emit **distinct, decision-ready** output instead of safe, repetitive, generic work.

Derived from the deployed X-team agent (creative-bet revision, 2026-05-07), which was the first agent in this project re-engineered to make creativity a *structural property of the output contract* rather than a prompt exhortation.

---

## Why this template exists

Asking an agent to "be creative" does not produce creativity. Asking it to "propose marketing ideas" produces strategy memos, vague archetypes, and the same playbook in three costumes.

The X-team revision worked because it stopped relying on the agent's good taste and instead **rejected non-creative output at the schema layer**. Generic ideas literally cannot pass the contract. Repetition is structurally disallowed.

Every specialized worker should inherit the same six levers below.

---

## The six structural levers

| # | Lever | What it does |
|---|-------|--------------|
| 1 | **Card schema** | Required fields force specificity — generic memos fail validation. |
| 2 | **Novelty diversity rule** | New cards must differ from recent history on audience / surface / format. |
| 3 | **Enumerated anti-patterns** | Explicit reject list closes the most common escape hatches. |
| 4 | **Constraint reframing** | The boss prompt names *under-creative output* as the bottleneck, flipping the agent's default from caution to variety. |
| 5 | **Critic loop** | Boss/critic gates cards against the schema before they reach the user, so non-creative work dies before consuming approval bandwidth. |
| 6 | **Artifact quality gates** | Deterministic runtime checks on emitted content (term coverage, hook shape, length, forbidden strings) — pre-LLM-judgment. |

### Lever 1 — Card schema

Every team emits **cards**, not memos. A card has required fields, and the field requirements are tailored to force specificity at the point where the agent would otherwise hand-wave.

Always include:
- **angle / hypothesis** — one sentence
- **target** — a *specific subpopulation*, not a demographic (e.g., "PCA pastors in cities with seminaries," not "Christian audience")
- **surface / channel + format** — concrete: "founder thread on X," "guest post on a named publication," "DM sequence to 50 named pastors"
- **mechanism** — why *this* target × surface × format works, not why marketing in general works
- **success metric + threshold** — what makes this a win
- **kill metric + threshold + observation window** — what makes this a loss, and when to call it
- **blast radius** — cost ceiling, reach ceiling, recoverability
- **resource dependencies** — named resource IDs from `factory/resources/`
- **exact next action if approved** — one command, one DM, one file change

### Lever 2 — Novelty diversity rule

> A card must differ from every in-flight card *and* every card from the last 14 days on at least one of {target, surface, format}.
>
> Variants of an already-proposed bet are **not new bets** — they belong inside the original card as an iteration plan.

This is the anti-repetition guard. Without it, agents reskin the same playbook indefinitely.

### Lever 3 — Enumerated anti-patterns

Make the reject list explicit in `criteria.md`. Standard rejects:
- vague audience archetypes ("Christians," "developers," "founders")
- generic experiment packs (multiple ideas bundled, no single decision)
- strategy-only memos with no associated decision card
- internal-safe work with no external reach plan
- repeated variants of one playbook submitted as separate cards
- copy missing audience / mechanism / proof / CTA / next action
- unsupported numerical claims

### Lever 4 — Constraint reframing

The boss prompt must name the bottleneck out loud, because the default LLM bias is to under-propose:

> Approval throughput is open. The constraint is **under-creative output**, not approval bandwidth. The fix is *better* proposals (distinct angles, novel surfaces), not *fewer* proposals.

This single reframe is what made the X agent stop self-censoring.

### Lever 5 — Critic loop

The boss/critic agent reads every emitted card and rejects against the schema + novelty rule + anti-pattern list *before* it lands in the user's approval queue. Non-creative work never consumes a human decision slot.

Already wired in this repo via `/factory/approvals/` + `/factory/inbox/` + Step F/G processors. New teams plug in without new infra.

### Lever 6 — Artifact quality gates

Deterministic runtime checks on the emitted content itself. Greppable, fast, no LLM judgment. Examples from the X-team campaign tests:
- ≥N domain-term hits per post from a team-specific vocabulary
- first-sentence hook shape (signal words: "avoid," "instead," "the problem with," "stop")
- length ceiling (e.g., 280 chars for X)
- forbidden internal strings (`$hermes_home`, `mock-x`, etc.)

These run in the standard verify command and short-circuit before LLM-as-judge.

---

## Required files per new team

When spinning up a new specialized worker, produce these under `factory/teams/<team>/`:

### `brief.md`
- **Mission** — one sentence, measurable goal, time horizon.
- **Decision-ready card schema** — the field list, tailored to the team's deliverable.
- **Novelty diversity rule** — restated with the window (default 14 days).
- **Operating envelope** — what the team can do without approval (drafts, research, internal artifacts) vs. what requires approval (external posting, paid spend, partner outreach, user-visible changes).
- **External reach mandate** — every card must map to at least one externally-visible surface from an enumerated list: paid acquisition, founder content, partner co-marketing, niche communities, seasonal moments, in-app loops, content drops, IRL/hybrid, press/podcasts. No internal-safe work.

### `criteria.md`
- **Accept** — concrete pass conditions ("audience named to subpopulation granularity," "mechanism explains why *this* combo, not generic," "metrics include kill threshold").
- **Reject** — the enumerated anti-pattern list from Lever 3, plus team-specific additions.

### `SOUL.md` (injected into the worker profile)
- Identity and mission.
- **Explicit creativity mandate**: *"Repetition is the failure mode. The constraint is under-creative output, not approval bandwidth."*
- One-line restatement of the novelty rule.
- Pointer to `brief.md` and `criteria.md` as binding contracts.

### Runtime quality gate (test file)
- Lives under `tests/`, runs in the standard verify command.
- Domain-term coverage check (team-specific vocabulary list).
- Format checks: length, hook shape, forbidden internal strings.

---

## Reference implementations (in this repo)

- **Live X-team config**: `scripts/teams/configure-x-team.sh` — cleanest end-to-end profile bootstrap.
- **Brief + criteria pattern**: `archive/legacy-2026-05-09/local-analysis/prompts-creative-bet-revision-20260507/factory/teams/growth/{brief,criteria}.md`
- **Constraint reframing**: `archive/legacy-2026-05-09/local-analysis/prompts-creative-bet-revision-20260507/factory/{REAL_VALUE_MODE,PRIORITIZE}.md`
- **Boss/critic prompt**: `/opt/hermes-home/profiles/boss/cron/jobs.json` jobs[0].prompt (prod hub).
- **Remote-Kanban wiring contract**: `plans/remote-kanban-teams.md`.
- **Runtime quality gate example**: `test_remote_team_content_campaign_live.py`.

---

## Jesuscord teams that should be instantiated from this template

Each becomes a separate `factory/teams/<team>/` directory. See `docs/jesuscord-pre-launch-marketing.md` for the strategic rationale; this template defines the shape.

| Team | Card kind | Example specific target |
|------|-----------|-------------------------|
| `founding-pastors` | recruitment card | "PCA pastors in cities with seminaries, 200–1,000 congregants" |
| `sermon-clip` | content card | "sermons from Pastor X under 8 min, posted as TikTok with lower-third branding" |
| `prayer-circle-host` | live-session card | "Wednesday 8pm CT small group, 5–8 participants, prayer-request format" |
| `hub-claim` | landing-op card | "claim-your-hub flow for SBC churches in TX, segmented by congregation size" |
| `build-in-public` | narrative card | "weekly founder thread on X, single named pastor per post" |

Instantiation should take <30 minutes per team once the template is internalized.

---

## Verification

A team is correctly instantiated when:
1. A reader can identify the six levers and four required files from this doc alone, without consulting other docs.
2. A deliberately generic card (e.g., "post motivational content on social media to grow engagement") fails ≥3 reject conditions in `criteria.md`.
3. Every lever in the team's config traces back to a concrete location in either the live X-team config or this template.

---

## Out of scope

- Concrete Jesuscord team instantiation — separate plan once this template is in use.
- Modifying the live boss prompt or `REAL_VALUE_MODE.md` — they already encode levers 4 and 5.
- Any prod deploy — this is a docs-only artifact until a team is wired.
