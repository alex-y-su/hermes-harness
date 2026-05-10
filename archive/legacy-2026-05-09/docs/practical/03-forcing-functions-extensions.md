# Single-Agent Forcing Functions for Hermes

The seven autonomy upgrades that replicate the multi-personality effect inside one Hermes agent — without spawning role-played sub-agents.

Conceptual basis: see [`research/05-autonomy-forcing-functions.md`](../research/05-autonomy-forcing-functions.md). Multi-personality works because role-switching incidentally manufactures four forcing functions (wrap-up bias reset, external critic pressure, structure re-injection, context budget reset). The same forcing functions can be added explicitly to one agent at lower token cost and without error amplification.

Ranked by leverage. Build 1, 2, 3, and 6 first — they give ~80% of the autonomy lift.

---

## 1. Verifiable mission with acceptance criteria — biggest single lever

**What.** Add a `define_mission(goal, acceptance_criteria=[...])` skill/tool. Stores a session-local mission file. Each criterion must be **independently checkable** — file exists, test passes, query returns >0 rows, URL responds 200. Not vibes.

**Gating.** Hermes has no `final_answer` tool to gate. Workaround: integrate with the existing `/goal` judge (`hermes_cli/goals.py:61-74`) — extend `JUDGE_SYSTEM_PROMPT` to require evidence of each acceptance criterion. The judge already runs after every turn; failing it pushes a continuation prompt and the agent keeps going.

**Why this is the biggest lever.** It eliminates ~80% of premature-stop failures because the agent literally cannot lie to itself about being done — the judge has the criteria checklist.

**Where.** Extend `tools/` with a `mission_tool.py`. State in `~/.hermes/missions/<id>.json`. Hook into the existing `/goal` flow.

---

## 2. Self-critique pass before exit

**What.** When the agent's turn ends with no tool calls (Hermes' equivalent of "I'm done"), automatically spawn a fresh critic agent via the existing `_build_child_agent(...)` from `tools/delegate_tool.py:834`.

The critic gets **only** the deliverable + criteria + nothing else. No conversation history. Pure critic with a fixed prompt:

> *"You are a strict reviewer. Evaluate the deliverable against the criteria. Return either APPROVED or a numbered list of specific gaps with concrete evidence."*

If APPROVED → allow turn to end.
If gaps → inject the gap list as a user-role message, re-launch the agent.

**Why fresh context matters.** The whole reason multi-personality works is that the Reviewer doesn't carry the Planner's wrap-up gradient. Replicating "fresh context" is the entire mechanism. A self-critique with full conversation history is much weaker.

**Where.** Register a `post_llm_call` hook (Hermes has these — `hermes_cli/plugins.py:78`) that detects no-tool-calls responses. Existing `_build_child_agent` provides the fresh-context infrastructure.

---

## 3. Anti-wrap-up system prompt addendum

**What.** When in mission mode, append to the system prompt (via SOUL.md or AGENTS.md, which Hermes auto-injects and protects from compaction):

> *"No user is waiting. Do not summarize. Do not hand back. Produce the next concrete action and execute it. Continue until all acceptance criteria are verified or you are hard-blocked. If hard-blocked, name the specific blocker and what would unblock you, then stop."*

**Why this works.** Sounds trivial; isn't. Directly counteracts the RLHF wrap-up bias that the persona-switch trick was incidentally bypassing. Highest impact-per-line-of-code intervention in the entire list.

**Where.** Just edit your project SOUL.md. Zero code changes.

---

## 4. Disk-backed mission ledger + selective re-loading

**What.** Long-running work fails because context fills with intermediate findings and the original goal gets pushed out, even with compaction. Solution: every significant action writes to `~/.hermes/missions/<id>/ledger.md`. On each turn boundary, the system prompt is re-rendered with: original goal, criteria status (with checkmarks), last 5 ledger entries, pointer to the full ledger.

**Why.** Makes context length irrelevant to mission length. You can run for days without losing the goal.

**Reuses.** Hermes' memory subsystem (`tools/memory_tool.py:131-186`, `agent/memory_manager.py`) is the natural home for this. MEMORY.md is already auto-injected into the system prompt and survives compaction.

**Where.** Extend `agent/memory_manager.py` to support per-mission MEMORY pages. Or — simpler MVP — just have the agent write to MEMORY.md via the existing memory tool, structured with mission headers.

---

## 5. Heartbeat resume via cron + `_pending_input`

**What.** For genuinely multi-day work, don't run one long session. Schedule a cron (`tools/cronjob_tools.py` already does this) that wakes Hermes every N minutes with `mission_resume(mission_id)`. The agent reads the ledger, checks unchecked criteria, picks the next action, executes, writes ledger, exits. Cron fires again later. Decouples runtime from session length entirely.

**Reuses.** `_pending_input` injection at `cli.py:6533` is the seam — heartbeat events become "next action" prompts. SessionDB resume via `--continue` keeps state.

**Why.** Bypasses every "agent ran for 3 hours then crashed / restarted / context-filled" failure mode. Each heartbeat is a fresh, short session reading state from disk.

**Where.** Cron entry + a small `mission_resume` skill. No core changes.

---

## 6. Lift the implicit iteration cap

**What.** `agent.max_turns` defaults to 90 (`run_agent.py:907`, `cli.py:307`). For mission mode, set it to 500–2000.

**Why.** Most premature stops at iteration ~30 are not the model giving up — they're the framework yanking the carpet (`run_agent.py:10165` strips tools and forces a summary at max_iterations). Lifting the cap is one config change.

**Where.** `~/.hermes/config.yaml`:

```yaml
agent:
  max_turns: 500
delegation:
  max_iterations: 200
goals:
  max_turns: 1000
```

Zero code changes.

---

## 7. Goal re-injection every Nth turn

**What.** Every 10 turns, the framework synthesizes a user-role message:

```
[reminder] Original goal: <goal>. Unchecked criteria: <list>. Continue.
```

**Why.** Cheap and devastatingly effective against goal drift in long sessions. This is the "planner persona" trick automated.

**Where.** A `pre_llm_call` hook (`hermes_cli/plugins.py:78`) that counts turns-since-last-reminder per session and injects the reminder when N is hit.

---

## Priority order and effort

| # | Intervention | Effort | Value |
|---|---|---|---|
| 1 | Mission with acceptance criteria + judge gating | ~1 day (tool + judge prompt edit) | ★★★★★ |
| 2 | Self-critique pass via fresh child | ~1 day (post_llm_call hook + critic agent) | ★★★★★ |
| 3 | Anti-wrap-up SOUL.md | 5 minutes | ★★★★★ |
| 6 | Lift iteration caps | 5 minutes (config) | ★★★★ |
| 7 | Periodic goal re-injection | ~half day (pre_llm_call hook) | ★★★ |
| 4 | Disk-backed mission ledger | ~1 day (memory tool extension) | ★★★ |
| 5 | Heartbeat cron resume | ~half day (cron + resume skill) | ★★★★ for multi-day |

For a weekend, build **1, 2, 3, 6** in that order. Add **4 and 5** when you have genuinely multi-day missions. Add **7** if you observe goal drift in the wild.

## What this approach buys vs. multi-personality

| Axis | Multi-persona | Single agent + forcing functions |
|---|---|---|
| Token cost | 5–15× single-agent | 1–2× single-agent |
| Error amplification (independent topology) | 17.2× per scaling-paper | 1× |
| Coherent context | No (split across personas) | Yes (one trajectory) |
| Quality on coupled tasks | Worse (per Cemri et al., NeurIPS 2025) | Better |
| Autonomy / horizon | Reliably extended (the observed effect) | Same effect via explicit mechanisms |
| Engineering cost | None (already works) | ~3–4 days |

The honest tradeoff: if multi-persona is already working and tokens are cheap, the engineering ROI to switch is questionable. If you're cost-constrained or your tasks are cognitively coupled, build the forcing functions.

## What this does NOT solve

- **Judge quality ceiling.** A weak auxiliary model false-passes the criteria. Pin a strong model in the `auxiliary` config.
- **Ambiguous criteria.** Garbage criteria → garbage gating. The discipline of writing testable criteria is half the battle.
- **Genuinely hard creative tasks** where success itself is ambiguous. No forcing function rescues a goal you can't define. Multi-persona doesn't either; it just hides the problem behind verbose role-play.
