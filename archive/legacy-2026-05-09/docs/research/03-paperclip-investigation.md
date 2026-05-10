# Paperclip Investigation

Snapshot: 2026-05-02. Pulled directly via `gh api repos/paperclipai/paperclip` and related endpoints.

## Stars vs. real engagement

| Metric | Value |
|---|---|
| Stars | 61,583 |
| Watchers (subscribers) | 344 |
| Forks | 10,878 |
| Open issues | 3,087 |
| Total commits | 2,374 |
| Unique contributors | 84 (1 bot) |
| **Top contributor (`cryppadotta`)** | **1,928 commits ≈ 81%** |
| Next 9 combined | ≈ 248 commits |
| Unique issue/PR authors | 1,927 (936 issues, 1,207 PRs) |
| First commit | 2026-02-16 |
| Last commit | 2026-05-01 (~75 days) |
| Releases | 8 (≈ weekly cadence) |
| Watcher : star ratio | **1 : 179** (healthy is 1:30–1:80) |

### Star velocity

First 40k stars (paginated with `Accept: application/vnd.github.v3.star+json`) all landed in March 2026, the first month after public launch. Daily counts ramped 818 → 2,181 → 2,743 → 3,014 then settled at 1,000–2,500/day. **No step-function cliffs.** The curve is the shape of organic viral acquisition (HN / Twitter / Product Hunt traffic), not bought stars (which look like single-day 10k+ spikes).

### Verdict

Stars are probably real but heavily inflated by hype/launch coverage. The 1:179 watcher ratio combined with extreme contributor concentration says **engaged usage is ≈ 1–2 orders of magnitude smaller than 61k**. Real active community ≈ 300–2,000 people. Real maintainers ≈ 1.

## Architectural pitch (and what's actually proven)

Paperclip's claim: "AI companies with org charts, budgets, governance, heartbeats." Specifically:

- Goal decomposition tied to org structure (CEO/CTO/engineers/marketers)
- Heartbeat-based execution: agents wake on schedules, do atomic work-checkout with full goal ancestry
- Cost tracking, budget caps, governance gates
- Durable state across heartbeats

**Claims with empirical support in the repo: zero.**

`evals/README.md` describes a `promptfoo`-based correctness harness — does the heartbeat skill pick up todos correctly, respect approvals, exit cleanly. These are unit-level assertions, not comparative benchmarks. There is no claim anywhere in `README.md`, `evals/`, or `doc/` that a Paperclip-orchestrated team outperforms a single agent on any task. The pitch is purely architectural.

## Operational overhead

From `package.json`, `docker/docker-compose.yml`, `Dockerfile`, `AGENTS.md`:

- Runtime: Node 20+, pnpm 9.15. Two services: Postgres 17 (or embedded PGlite in dev) + the server (port 3100). UI is served by the same Node process.
- Deps: server, ui, ~8 adapter packages (Claude / Codex / Cursor / Gemini / Bash / HTTP / OpenClaw), plugin SDK, embedded-postgres patched.
- No Redis, no separate queue. Heartbeat / wakeup queue is **DB-backed** (per `AGENTS.md` / README "DB-backed wakeup queue with coalescing").
- Memory footprint claims: none disclosed.
- **Token-cost tax disclosure: zero.** README pitches budgets and hard stops but does not disclose what fraction of tokens go to manager / heartbeat / coordination calls vs. actual work. Plausibly 20–50% on top of worker tokens given the architecture, **couldn't verify**.
- No user post found reporting actual $/day. What I did find: in-flight PRs adding cost-cap and loop-detector safety rails (PR #4765 "loop detector + $ cap", `cost_events` table, "shadow cost ledger"). The fact that runaway-cost guardrails are still being hardened *now* is itself a tell.
- Operational complexity: trivial for a hobbyist (single docker-compose, embedded PG works), moderate for production (auth mode, secrets, plugin workers, governance config).

## What's worth borrowing (without adopting the dependency)

- DB-backed heartbeat queue with coalescing
- Atomic work-checkout with goal-ancestry context propagation
- Cost-event ledger schema and budget governance
- Loop-detector / runaway-cost guardrails

These are well-designed primitives and apply equally well to a single-agent harness over Hermes (see [`practical/03-forcing-functions-extensions.md`](../practical/03-forcing-functions-extensions.md)).

## What's not worth adopting

The org-chart abstraction (CEO/CTO/engineer roles) is the part with no proof. See `04-multi-vs-single-agent-evidence.md` — at matched compute, complex multi-agent role-play scaffolds do not beat single agents on cognitive tasks, and the Cemri et al. (NeurIPS 2025) and *Towards a Science of Scaling Agent Systems* (2025) results suggest active harm via error amplification on coupled work.

## Sources

- Repo: https://github.com/paperclipai/paperclip
- README, AGENTS.md, evals/README.md, doc/ (read directly via `gh api`)
- Discord: https://discord.gg/m4HZY7xNG3
- Twitter: https://x.com/papercliping
