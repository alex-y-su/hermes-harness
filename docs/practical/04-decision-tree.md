# Decision Tree — When to Pick What

A flowchart for "I want autonomous Hermes; what should I actually build/use?"

---

## Q1. What kind of task?

### A. Cognitively coupled — code refactors, multi-hop reasoning, anything where one decision constrains the next

→ **Single agent.** Multi-agent error amplification (4.4–17.2× per *Towards a Science of Scaling Agent Systems*) and the Cemri et al. (NeurIPS 2025) negative result both apply. The quality cost is real.

→ Go to **Q2 (autonomy axis)**.

### B. Parallelizable / I/O-bound — research synthesis, browsing many sources, "find N independent things," bulk transforms

→ **Multi-agent decomposition is supported by replication-grade evidence.** Use Hermes' existing `delegate_task` for in-turn parallelism (default 3 concurrent, depth 3 nesting).

→ Go to **Q3 (durability)**.

### C. Mixed — some sub-tasks parallelizable, the meta-loop is coupled

→ **Single agent at the top, `delegate_task` for the parallelizable sub-work.** This is the canonical Anthropic-deep-research shape. Don't put role-played personas at the top — use `/goal` and acceptance criteria.

→ Go to **Q2** for the top loop, **Q3** for the children.

---

## Q2. How long does the autonomous loop need to run?

### A. Minutes to a few hours, single session

→ **Use the recipe in [`01-247-recipe.md`](01-247-recipe.md) as-is.** `--yolo` + `goals.max_turns: 1000` + `agent.max_turns: 500` + SOUL.md. Zero code changes.

### B. Hours to days, can survive process restart but doesn't need to

→ Same recipe + add the **cron watchdog** from §5 of [`01-247-recipe.md`](01-247-recipe.md). 15-minute heartbeat covers gaps.

### C. Days to weeks, must survive every kind of crash

→ Recipe + **build interventions 1, 2, 3, 6 from [`03-forcing-functions-extensions.md`](03-forcing-functions-extensions.md)** (mission with criteria, self-critique, anti-wrap-up, raised caps). Add intervention 5 (heartbeat cron resume) for true durability. ~3 days of work.

### D. Indefinite, like a "background employee"

→ Everything in C, plus **build durable delegation per [`02-durable-delegation-design.md`](02-durable-delegation-design.md)**. ~3 more days of work. Total ~1 week to a serious harness.

---

## Q3. Sub-task durability

### A. Sub-tasks complete inside the parent's turn (seconds to a few minutes)

→ **Use existing `delegate_task`.** Synchronous, parallel, well-tested. Default 3 concurrent. Children skip approvals (`config.py:948`).

### B. Sub-tasks take 5–60 minutes; parent can wait

→ Still `delegate_task`, but raise `delegation.child_timeout_seconds` (default 600 = 10 min) and `delegation.max_iterations` (default 45).

### C. Sub-tasks take hours; parent should not block

→ **`terminal(background=True, notify_on_complete=True)`** is the documented Hermes answer (`tools/delegate_tool.py:2370`). Result auto-injected via `_pending_input` (`cli.py:1446`). Good for 1–3 children. Reinvents a queue at N=5+.

### D. Sub-tasks take hours-to-days; need fan-in across many; must survive parent restart

→ **Build durable delegation per [`02-durable-delegation-design.md`](02-durable-delegation-design.md).** SQLite store + detached runner subprocess + parent re-entry hook. ~3 days.

---

## Q4. Should I use a third-party orchestrator?

### A. Hermes Workspace (`outsourc-e/hermes-workspace`)

→ **Try first if you want a UI for sub-teams of Hermes.** Only one of the three with first-class Hermes integration. Persistent tmux workers, kanban, role lanes. Path of least resistance for the multi-personality pattern. Trade-off: it commits you to the multi-personality cost (5–15× tokens, error amplification on coupled tasks).

### B. Mission Control (`builderz-labs/mission-control`)

→ **Skip unless you want a polished general dashboard and are willing to write a Hermes adapter.** No first-class Hermes support. The Aegis quality-gate primitive is genuinely good and worth studying — borrow the design.

### C. Paperclip (`paperclipai/paperclip`)

→ **Don't adopt.** Bus factor 1, no Hermes adapter, org-chart abstraction unproven. Read the code for ideas — heartbeat queue with coalescing, atomic work-checkout, cost ledger, loop detector — then build them yourself in Hermes. See [`03-paperclip-investigation.md`](../research/03-paperclip-investigation.md).

### D. LangGraph / Temporal / external workflow engine

→ **Use only if your orchestration logic is rule-driven, not LLM-driven.** Rule-driven: known steps, retries, branches, deadlines, human-in-the-loop. LLM-driven: which sub-question to research next depends on prior findings. For LLM-driven (your case), the workflow engine's strength (deterministic replay, branching, retries) doesn't apply. Hermes' own `/goal` + durable delegation is the right level.

---

## Q5. Should I build a multi-personality / role-played setup (Planner / Reviewer / etc.)?

### A. If you have it already and tokens are cheap and it's working

→ **Keep it.** No paper proves single-agent + forcing functions outperforms multi-personality on horizon length. The mechanism-grounded hypothesis says they should match; the head-to-head benchmark doesn't exist. Don't refactor working code based on a hypothesis.

### B. If you're starting fresh and the task is cognitively coupled

→ **Don't.** Use single agent + forcing functions per [`03-forcing-functions-extensions.md`](03-forcing-functions-extensions.md). The compute-matched literature (Cemri et al. NeurIPS 2025; *Single-Agent vs MAS at Equal Thinking Tokens* 2026; Cognition's "Don't build multi-agents") all point against role-played multi-agent for coupled work.

### C. If you're starting fresh and the task is parallelizable / breadth-first I/O

→ **Use `delegate_task`, not role-played personas.** `delegate_task` gives you the parallelism that actually pays off. Role-played personas (CEO/CTO/engineer) add coordination overhead without the parallelism benefit. Different concept.

---

## Cheat sheet

| Situation | Answer |
|---|---|
| "I want hands-off autonomous Hermes for a complex creative task" | Recipe in `01-247-recipe.md`. SOUL.md + `--yolo` + `/goal` + raised caps. |
| "I want it to survive process restart and run for a week" | Recipe + interventions 1, 2, 3, 6 from `03-forcing-functions-extensions.md`. ~3 days of code. |
| "I want sub-tasks that run for hours independently" | Durable delegation design from `02-durable-delegation-design.md`. ~3 days of code. |
| "Should I use Paperclip?" | No. Read the patterns, skip the dependency. |
| "Should I use Hermes Workspace?" | Try it if you want sub-teams of Hermes today and are OK with the multi-persona cost. |
| "Should I use multi-personality?" | Only for parallelizable I/O work. Even then, prefer `delegate_task` over role-play. |
| "Where do I put intermediate state?" | `MEMORY.md` (auto-injected, survives compaction and restart). |
| "How do I make the agent never stop?" | Raise `agent.max_turns` and `goals.max_turns`, set strict acceptance criteria, judge runs the Ralph loop. |
| "How do I bypass approval prompts?" | `--yolo` or `approvals.mode: off`. |
