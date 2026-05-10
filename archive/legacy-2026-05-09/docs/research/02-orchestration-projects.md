# Third-Party Hermes Orchestration Projects

Verified May 2026 via `gh api`. Ranked by Hermes-relevance.

## 1. Hermes Workspace — `outsourc-e/hermes-workspace`

**The only one of the three with first-class Hermes integration.**

- Repo: https://github.com/outsourc-e/hermes-workspace
- 2,860 stars, MIT, v2.1.3
- Created 2026-03-16
- README opens with: *"Runs on vanilla `NousResearch/hermes-agent` installed via Nous's own installer. No patches, no drift."*

### What it actually ships

- Native web workspace for Hermes — chat, terminal, memory, skills, inspector
- **Swarm Mode** — persistent tmux-backed Hermes workers, 1 orchestrator + N workers
- Role-based dispatch lanes: builders / reviewers / docs / research / ops / triage / QA / lab
- Kanban TaskBoard: backlog / ready / running / review / blocked / done
- Reports + Inbox for checkpoints and human handoffs
- Byte-verified review gate before PRs ship
- Mobile-first PWA over Tailscale
- Direct gateway connection (`http://<host>:8642`) with SSE streaming

### Install

```bash
curl -fsSL https://raw.githubusercontent.com/outsourc-e/hermes-workspace/main/install.sh | bash
hermes gateway run                  # terminal 1
cd ~/hermes-workspace && pnpm dev   # terminal 2
```

### When to use it

Path of least resistance for "I want sub-teams of Hermes agents on tmux right now." The workspace's Swarm Mode delivers the multi-personality pattern out of the box.

### When to skip it

If your tasks are **cognitively coupled** (cross-file code refactors, multi-hop reasoning) — see `04-multi-vs-single-agent-evidence.md`. Multi-agent error amplification (4.4–17.2× per *Towards a Science of Scaling Agent Systems*) outweighs gains on those task shapes.

---

## 2. Mission Control — `builderz-labs/mission-control`

**Not Hermes-native, despite ecosystem chatter suggesting otherwise.**

- Repo: https://github.com/builderz-labs/mission-control
- 4,538 stars, MIT, Alpha
- Created 2026-02-13
- Stack: Next.js 16 + SQLite, Node 22+, single-process

### What it actually ships

- 32-panel dashboard: tasks, agents, skills, logs, tokens, memory, security, cron, alerts, webhooks, pipelines
- WebSocket + SSE real-time updates
- Role-based access (viewer / operator / admin) with Google Sign-In
- Quality gates ("Aegis" review system) blocking task completion without sign-off
- Skills Hub with bidirectional disk ↔ DB sync
- Multi-gateway adapters: **OpenClaw, CrewAI, LangGraph, AutoGen, Claude SDK** — *no Hermes adapter*
- Recurring tasks via natural-language scheduling
- Trust scoring, secret detection, MCP call auditing

### When to use it

If you want a polished general-purpose agent fleet dashboard and are willing to write a Hermes adapter. The Aegis quality-gate primitive is genuinely good and worth studying.

### When to skip it

If you want plug-and-play with Hermes today. There's no first-class integration and no public roadmap commitment to one.

### Install

```bash
git clone https://github.com/builderz-labs/mission-control.git
cd mission-control
bash install.sh --local   # or --docker
open http://localhost:3000/setup
```

---

## 3. Paperclip — `paperclipai/paperclip`

**Solo-founder project, viral marketing, unproven on the architectural value-add.** See `03-paperclip-investigation.md` for the full audit.

- Repo: https://github.com/paperclipai/paperclip
- 61,582 stars, MIT (most stars; least real engagement of the three)
- Created 2026-03-02
- Stack: Node 20+, Postgres 17 (or embedded PGlite), React

### What it actually ships

- "Open-source orchestration for zero-human companies"
- Org-chart abstraction: define goals → hire bots as CEO/CTO/engineer → set budgets → monitor
- DB-backed heartbeat queue with coalescing
- Atomic work-checkout with goal-ancestry context propagation
- Cost ledger and budget governance
- Loop detector + $-cap (in-flight as of May 2026 — still hardening)
- Adapters: **OpenClaw, Claude Code, Codex, Cursor, Bash, HTTP** — *no Hermes adapter*

### When to use it

For ideas. Specifically: borrow the heartbeat queue, atomic checkout, cost ledger, and loop-detector patterns. They are well-thought-out primitives.

### When to skip it (most cases)

- Bus factor 1 (top contributor = 81% of commits in 75 days)
- Watcher:star ratio 1:179 — real engaged community ≈ 300–2,000 people, not 61k
- No Hermes adapter; integration is "expose an HTTP heartbeat target"
- The org-chart / "AI company" abstraction is heavier than what most users need
- No empirical evidence the org-chart adds quality at matched compute (see `04-multi-vs-single-agent-evidence.md`)

---

## Decision: which to use for Hermes orchestration

| If you want… | Use |
|---|---|
| Plug-and-play Hermes sub-teams today | **Hermes Workspace** Swarm Mode |
| A polished fleet dashboard for any agent runtime | **Mission Control** + write a Hermes adapter |
| Reference architecture (heartbeats, atomic checkout, cost ledger) | **Paperclip** — read the code, don't import the package |
| The most durable / multi-day option | None of these as-is — see [`practical/02-durable-delegation-design.md`](../practical/02-durable-delegation-design.md) |
