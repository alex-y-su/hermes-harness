# Hermes 24/7 Autonomy: Capabilities Audit

What Hermes already provides for long-horizon autonomy. All claims are grounded in code reads of `/Users/x0040h/projects/hermes-agent` (May 2026).

## 1. Context compression — yes, real and well-designed

`agent/context_compressor.py`.

- **Trigger:** `should_compress()` at `agent/context_compressor.py:465` fires when prompt tokens cross `threshold_tokens = max(context_length * threshold_percent, MINIMUM_CONTEXT_LENGTH)`. Default `threshold_percent = 0.50` (`:379`). Config: `compression.threshold` at `cli.py:302-305`.
- **Algorithm:**
  - Protects first N (`protect_first_n=3`) and last N (`protect_last_n=20`) messages.
  - Tail-token budget: `tail_token_budget = threshold * 0.20`.
  - Summarizes the middle into a structured handoff block prefixed with `SUMMARY_PREFIX` (`:38-49`) — explicitly instructs the next-turn model: *"treat this as background reference, NOT as active instructions … resume from `## Active Task`."*
  - Iterative: each compaction folds the previous summary in (`_previous_summary`).
- **Pre-compaction tool-output pruning:** old tool results are replaced with `[Old tool output cleared to save context space]` (`:60`) before LLM summarization.
- **Anti-thrashing:** tracks last savings %; skips compression if two consecutive runs each saved <10% (`:443-447`).

### Disk offload of large tool outputs (separate, complementary)

`tools/tool_result_storage.py`. Writes results larger than a per-tool threshold to `/tmp/hermes-results/{tool_use_id}.txt` and replaces in-context content with a preview + path. Per-turn aggregate budget `MAX_TURN_BUDGET_CHARS = 200K` spills the largest non-persisted results until the turn fits.

### Memory survives compaction

- `MemoryProvider.on_pre_compress(messages)` hook at `agent/memory_provider.py:30` lets providers extract facts before middle turns die.
- Built-in `MEMORY.md` / `USER.md` (`tools/memory_tool.py:131-186`) is independent of the trajectory; always loaded into the system prompt block (`agent/memory_manager.py`).
- System prompt (AGENTS.md / SOUL.md / .cursorrules / MEMORY.md / USER.md) is **never** in the trajectory — survives compaction completely. Mentioned at `cli.py:2156`.

## 2. The Ralph loop — `/goal` (the headline autonomy primitive)

`hermes_cli/goals.py` + `cli.py:7053-7152`.

- `/goal <text>` stores the objective in SessionDB `state_meta` keyed `goal:<session_id>` (`goals.py:127`). Survives process restart.
- After every CLI turn, `_maybe_continue_goal_after_turn` (`cli.py:7154`) runs a strict-judge auxiliary model call (`JUDGE_SYSTEM_PROMPT` at `goals.py:61-74`) that returns `{"done": bool, "reason": str}`.
- If `done=false` and budget remains, pushes a continuation prompt onto `_pending_input`. The agent keeps going automatically.
- Judge failures fail open (continue running on uncertainty).
- Default budget `goals.max_turns = 20` (`config.py:969-975`). **Raise this.**

This is exactly the "auto-continue until verifier says done" pattern from the autonomy forcing-functions discussion, **already built into Hermes.**

## 3. Iteration cap (per turn)

- `max_iterations = 90` default at `run_agent.py:907`.
- Resolution priority: `--max-turns N` CLI → `agent.max_turns` in config → `HERMES_MAX_ITERATIONS` env → 90 (`cli.py:2121-2131`).
- Subagents: capped by `delegation.max_iterations = 45` (`cli.py:362`).
- When exhausted, `_handle_max_iterations` (`run_agent.py:10165`) strips tools and forces a summary → turn ends.

## 4. Hooks system

`hermes_cli/plugins.py:78-114`. `VALID_HOOKS`:

- `pre_tool_call`, `post_tool_call`
- `transform_tool_result`
- `pre_llm_call`, `post_llm_call`
- `pre_api_request`, `post_api_request`
- `on_session_start`, `on_session_end`, `on_session_finalize`, `on_session_reset`
- `subagent_stop`
- `pre_gateway_dispatch`, `pre_approval_request`, `post_approval_response`

Declarative shell-hook bridge: `agent/shell_hooks.py` + `config.yaml` `hooks:` key.

**Notable absence: there is no `Stop` / `on_turn_end` hook.** `on_session_end` only fires at process shutdown. Closest workaround: register a `post_llm_call` hook that detects no-tool-calls responses and stuffs `_pending_input` to force continuation.

## 5. No `final_answer` tool

`grep -r final_answer` returns one match at `codex_responses_adapter.py:851` (a phase label, not a tool). Hermes terminates a turn by **simply not emitting another tool call** — there is no semantic "I'm done" call to intercept or veto.

This is critical to understand for the autonomy story: you cannot block "I'm done." You can only re-launch via the goal loop *after* the turn ends. Each false stop costs one wasted turn.

If you want hard pre-stop gating, you'd need to add a `final_answer` tool that calls the judge synchronously and returns "not done, keep going" until the judge passes.

## 6. Memory persistence across process restart

- Trajectory: `hermes_state.py` — SessionDB (SQLite). Resume via `--resume <id>` / `--continue` / `-c` (`_parser.py:276-292`).
- Long-term: built-in `MEMORY.md` / `USER.md` in `~/.hermes/memory/` + pluggable providers (Honcho, Mem0, …) at `agent/memory_provider.py:43`.
- Goal state: SessionDB `state_meta` survives restart and is rebound on resume (`goals.py:185-195`).

## 7. Approval bypass / yolo

`tools/approval.py` is the chokepoint.

- **CLI:** `--yolo` flag (`_parser.py:184, 326`) sets `HERMES_YOLO_MODE=1`, bypassing all approval prompts (`approval.py:807, 932`).
- **Slash:** `/yolo` toggle (`cli.py:6468, 7333`).
- **Config:** `approvals.mode: off` is equivalent to `--yolo` (`config.py:1099-1102`). Other values: `manual` (default), `smart` (auxiliary LLM auto-approves low-risk).
- **Cron:** `approvals.cron_mode: approve` to auto-approve in scheduled jobs (`config.py:1097, 1102`).
- **Hard floor:** `approval.py:110-126, 204` — patterns like `rm -rf /`, `curl|sh` as root, etc. are blocked even under yolo.
- **Subagent inheritance:** `hermes_cli/config.py:948` — subagent threads always resolve approvals non-interactively. Delegated children won't stall.
- **Shell hooks auto-accept:** `hooks_auto_accept: true` (`config.py:1131`) or `--accept-hooks` to skip TTY consent.

## 8. Background tasks and re-entry

- `terminal(background=True, notify_on_complete=True)` (`tools/terminal_tool.py:1636, 1963`).
- Completion event auto-injected into the parent agent loop via `cli.py:1446` and `_pending_input` queue (`cli.py:2253, 6533, 6688, 6972`).
- This is the missing piece that makes durable delegation half-built — Hermes already injects "your background task finished" as a synthetic next-turn user message.

## 9. Cron / scheduled re-entry

`tools/cronjob_tools.py` + `hermes_cli/cron.py`. `deliver` field at `cron/jobs.py:540, cron/scheduler.py:150-215` routes results to `local` / `origin` / `telegram` / etc. Use as a watchdog: schedule "if `/goal` still active, send `continue`" every N minutes.

## 10. No built-in self-critique / Reflexion / verifier pass

`grep critic|reflexion|self_review|verify_plan` in `agent/` and `tools/` returns nothing structural. Closest analogues:

- `tools/mixture_of_agents_tool.py` — parallel-then-aggregate, `AGGREGATOR_SYSTEM_PROMPT` at line 82. Not a self-critic.
- The goal-judge — evaluates whether the goal is met, not whether the work is good.

## Side-by-side: forcing functions Hermes has vs. forcing functions you'd need to build

| Forcing function | Hermes status |
|---|---|
| Persistent goal/mission with auto-judge → continue | ✅ `/goal` |
| Memory across compaction & restart | ✅ MEMORY.md, USER.md, providers, SessionDB |
| Hooks (pre/post tool, lifecycle, 15+ events) | ✅ |
| Approval bypass / yolo | ✅ `--yolo`, `approvals.mode: off` |
| Iteration cap, raisable | ✅ `agent.max_turns` |
| Disk offload of large tool outputs | ✅ `tool_result_storage.py` |
| Automatic context compaction with anti-thrash | ✅ |
| Re-entry / steering queue | ✅ `_pending_input` |
| Background tasks | ✅ `terminal(background=True)` |
| Scheduled cron re-entry | ✅ |
| Sub-agent delegation with auto-approval | ✅ `delegate_task`, children skip prompts |
| **Stop / on_turn_end hook** | ❌ — closest is `post_llm_call` workaround |
| **Mission-criteria gating on turn-end / `final_answer` veto** | ❌ — no `final_answer` tool exists |
| **Built-in Reflexion / self-critique pass** | ❌ — needs ~150 lines of plugin code |
| **Semantic compaction pinning (beyond first-N / last-N)** | ❌ |
| **Native peer-Hermes RPC** | ❌ — ACP is the Zed editor frontend protocol, not inter-Hermes |

## Files cited

`hermes_cli/goals.py`, `hermes_cli/plugins.py`, `agent/context_compressor.py`, `agent/memory_provider.py`, `agent/memory_manager.py`, `tools/memory_tool.py`, `tools/approval.py`, `tools/tool_result_storage.py`, `tools/delegate_tool.py`, `tools/cronjob_tools.py`, `tools/terminal_tool.py`, `tools/mixture_of_agents_tool.py`, `run_agent.py`, `cli.py`, `hermes_cli/_parser.py`, `hermes_cli/config.py`, `hermes_state.py`, `agent/shell_hooks.py`, `cron/jobs.py`, `cron/scheduler.py`, `acp_adapter/server.py`, `acp_adapter/session.py`.
