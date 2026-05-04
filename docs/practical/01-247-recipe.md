# 24/7 Autonomous Hermes — Recipe

For "I have a complex creative task. I want one Hermes instance running for days, solving it creatively, delegating sub-tasks via `delegate_task` when useful, never stopping until done. Tokens are not a concern."

This recipe gets you ~80% of the autonomy outcome with **zero code changes** to Hermes — only configuration, a SOUL.md, and a slash command.

## Step 1 — `~/.hermes/config.yaml`

```yaml
agent:
  max_turns: 500            # per-turn iteration cap; default 90 (cli.py:307)

delegation:
  max_iterations: 200       # subagent per-turn cap; default 45 (cli.py:362)

compression:
  enabled: true             # default true (cli.py:303)
  threshold: 0.70           # raise from 0.50 — compact later, retain more useful context

goals:
  max_turns: 1000           # the Ralph-loop continuation budget; default 20 (config.py:974)

approvals:
  mode: off                 # full bypass — equivalent to --yolo
  cron_mode: approve        # auto-approve in scheduled jobs
  mcp_reload_confirm: false

hooks_auto_accept: true     # auto-accept shell-hook registrations
```

Optional env vars (set in your shell):

```bash
export HERMES_YOLO_MODE=1
export HERMES_MAX_ITERATIONS=500
export HERMES_ACCEPT_HOOKS=1
```

## Step 2 — `SOUL.md` in your project root (or `~/.hermes/SOUL.md`)

Hermes auto-injects `AGENTS.md` / `SOUL.md` / `.cursorrules` / `MEMORY.md` / `USER.md` into the system prompt block, which is never in the trajectory and survives compaction completely. Use this to bake in the mission and counter the RLHF wrap-up bias.

```markdown
# Mission

[Full task description with concrete acceptance criteria. Every criterion must be independently checkable — file exists, test passes, query returns >0 rows, URL responds 200.]

## Acceptance criteria

- [ ] Criterion 1 (with check command or file path)
- [ ] Criterion 2
- [ ] Criterion 3

## Anti-wrap-up directive

You are running on a long-horizon mission. **No human is waiting for a polished summary at the end of each turn.** The user has explicitly approved indefinite continuation until criteria are met or you are hard-blocked.

- Never emit a final wrap-up paragraph. If you think you're done, write the deliverable to a project file or to MEMORY.md, then verify it against the criteria.
- Do not summarize what you accomplished this turn. Produce the next concrete action and execute it.
- Continue improving until every criterion is verifiably met, OR until you encounter a hard blocker that requires human input. If hard-blocked, name the specific blocker and what would unblock you, then stop.

## Memory protocol

- After every meaningful action, append a one-line entry to `MEMORY.md` describing what was tried and what was learned.
- Before starting work each turn, read `MEMORY.md` and the criteria checklist. Do not redo work that's already in the ledger.
- Use `memory.write` for facts that should survive process restart.

## Delegation policy

- Use `delegate_task` for sub-work that is **parallelizable and independent** (e.g., research five sources in parallel, evaluate ten candidates simultaneously). Children inherit auth and skip approval prompts.
- Do NOT delegate cognitively coupled work (cross-file refactors, multi-step reasoning that depends on shared state) — single-agent + more thinking wins on those tasks.
- Do NOT spawn role-played persona sub-agents (CEO, CTO, Reviewer, etc.). They consume 5–15× more tokens for no proven quality benefit on coupled tasks. Use `/goal` and self-checks instead.
```

## Step 3 — Pick a strong auxiliary model

The goal-judge runs on the auxiliary model. A weak auxiliary will false-pass and end the loop early. Set in config:

```yaml
auxiliary:
  model: <your strongest available model>
  provider: <your provider>
```

(Find the exact key by searching `auxiliary` in `hermes_cli/config.py`.)

## Step 4 — Launch

```bash
hermes chat --yolo --max-turns 500
/goal <full task spec, including acceptance criteria — copy from SOUL.md>
```

The judge in `hermes_cli/goals.py:61-74` is strict by default; it only marks done on explicit completion, hard-blocked, or unachievable. Once `/goal` is set, every turn the judge runs and either (a) confirms done and stops, or (b) pushes a continuation onto `_pending_input` and the agent keeps going.

## Step 5 — Watchdog (optional but recommended)

For genuinely multi-day operation, add a cron belt-and-suspenders against pauses:

```bash
hermes cron create \
  --schedule "*/15 * * * *" \
  --prompt "If goal is still active, continue from MEMORY.md and the criteria checklist." \
  --deliver local
```

This covers the case where the goal loop is paused by budget exhaustion or process restart.

## Step 6 — Resume after restart

Session id is logged at exit. Relaunch:

```bash
hermes chat --continue
```

Goal state is rebound from SessionDB (`hermes_cli/goals.py:185-195`).

## What this recipe gives you

- ✅ Auto-continue until the judge says done (or 1000 turns, whichever first)
- ✅ Memory persists across compaction (MEMORY.md / USER.md in system prompt)
- ✅ Memory persists across process restart (SessionDB + `--continue`)
- ✅ No approval prompts (yolo)
- ✅ Per-turn ceiling raised to 500 iterations
- ✅ Cron watchdog as backstop
- ✅ Anti-wrap-up enforced via SOUL.md system prompt

## What this recipe does NOT give you

- ❌ Hard pre-stop gating. Hermes ends a turn by absence of tool calls — you cannot block "I'm done" semantically. Each false stop costs one wasted turn.
- ❌ Automatic Reflexion / self-critique pass before declaring done. The goal-judge evaluates "is the goal met," not "is the work good."
- ❌ Semantic compaction pinning. For day-long horizons, write critical state to MEMORY.md, do not rely on the trajectory.

If those gaps matter, see [`02-durable-delegation-design.md`](02-durable-delegation-design.md) and [`03-forcing-functions-extensions.md`](03-forcing-functions-extensions.md).

## Honest limits

- The goal-judge runs on the auxiliary model once per turn — judge quality is a real ceiling. False-pass is the most common failure mode.
- Token cost scales linearly with uptime. Multi-day runs at 500-iteration turns will be significant even though "tokens are not a concern."
- The model can produce declining output on long single sessions. Periodic `--continue` (new session, same goal) refreshes context fully.
- Goal ambiguity is the silent killer. Acceptance criteria that aren't independently checkable allow the model to falsely declare done.
