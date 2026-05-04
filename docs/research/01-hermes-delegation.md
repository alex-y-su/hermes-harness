# Hermes Delegation: What Already Exists

Source: code reading of `/Users/x0040h/projects/hermes-agent`, May 2026.

## Summary

Hermes ships a first-class delegation subsystem called `delegate_task`. A parent agent can spawn isolated child `AIAgent` instances, run them in parallel, and aggregate their final summaries. Sub-teams (orchestrator children spawning leaves) are supported up to depth 3. Tracking is real — there is a TUI overlay, slash commands, and a registry.

**The single most important caveat:** delegation is synchronous and non-durable. Children die when the parent's turn ends or is interrupted. There is no built-in mechanism for tasks that need to outlive a turn or survive process restart.

## Implementation map

- `tools/delegate_tool.py:1812` — `delegate_task(...)` entry point. Supports `goal=`, `context=`, `toolsets=`, or `tasks=[...]` for batches.
- `tools/delegate_tool.py:1242` — `_run_single_child()` — runs one child to completion.
- `tools/delegate_tool.py:834` — `_build_child_agent()` — constructs an isolated `AIAgent` with restricted toolsets, fresh context, own terminal session.
- `tools/delegate_tool.py:533` — `_build_child_system_prompt()` — synthesizes the child's system prompt from `goal` + `context`.
- `tools/delegate_tool.py:170-218` — in-memory subagent registry: `_register_subagent`, `_unregister_subagent`, `interrupt_subagent`, `list_active_subagents`.
- `tools/delegate_tool.py:153-168` — `set_spawn_paused` / `is_spawn_paused` — operator kill-switch.

### Wired into the agent loop

- `run_agent.py:9245` — `_dispatch_delegate_task()` — single dispatch site.
- `run_agent.py:9338, 9945` — tool-call branch.
- `run_agent.py:5248` — `_cap_delegate_task_calls()` — concurrency cap when the model emits multiple parallel calls in one turn.
- `toolsets.py:56, 197, 312, 340` — registers `delegate_task` in the `delegation` toolset.

### Tracking

- TUI overlay `/agents` (alias `/tasks`): `ui-tui/src/components/agentsOverlay.tsx`, `appLayout.tsx:20`, `overlayStore.ts:41`, `turnController.ts:776`.
- CLI fallback: `cli.py:4210`.
- Gateway slash: `ui-tui/src/app/slash/commands/ops.ts:288` — `/agents [pause|resume|status]`.

### Docs

- `website/docs/user-guide/features/delegation.md` — full feature spec.

## Behavior

- **Single or batch:** `delegate_task(goal=..., context=..., toolsets=[...])` or `tasks=[{...}, ...]`.
- **Parallel:** `ThreadPoolExecutor`, default 3 concurrent. Config: `delegation.max_concurrent_children`, env `DELEGATION_MAX_CONCURRENT_CHILDREN`.
- **Isolation:** each child = fresh `AIAgent` with own conversation, own terminal session, restricted toolsets. Only the final summary returns to the parent.
- **Nesting:** `role="leaf"` (default, cannot re-delegate) or `role="orchestrator"` (can). Bounded by `delegation.max_spawn_depth` (default 1, cap 3). `delegation.orchestrator_enabled` is the global kill switch.
- **Blocked tools for children:** `delegation` (leaves), `clarify`, `memory`, `code_execution`, `send_message`.
- **Lifetime:** synchronous within parent's turn. Parent interrupt → children cancelled (`status="interrupted"`).
- **Per-child knobs:** `max_iterations` (default 50), `child_timeout_seconds` (default 600). Optional cheaper subagent model: `delegation.model` / `delegation.provider` / `delegation.base_url`.
- **Credentials:** children inherit parent's API key, provider config, credential pool.

## Adjacent durable primitives

- `tools/cronjob_tools.py` — scheduled / recurring runs. The project's documented answer for "I want this to outlive the turn."
- `tools/terminal_tool.py` — `background=True, notify_on_complete=True`. The completion event is auto-injected into the parent agent loop via `cli.py:1446` and `_pending_input` queue (`cli.py:2253, 6533, 6688, 6972`). **This is the missing piece that makes durable delegation half-built — Hermes already injects "your background task finished" as a synthetic next-turn user message.**
- `acp_adapter/`, `acp_registry/` — these are the **Zed editor frontend protocol** (the `acp` import is the Zed Agent Communication Protocol). It is not an inter-Hermes RPC bus. The project manifest at `acp_registry/agent.json` is just a manifest. **Cross-Hermes peer dispatch is not supported by ACP as written.**

## Verdict

Use `delegate_task` for in-turn parallel work today. For tasks that need to survive interrupts or run for hours-to-days, the project's documented escape hatches are `cronjob` and backgrounded `terminal`. A real durable / async delegation layer does not exist — see [`practical/02-durable-delegation-design.md`](../practical/02-durable-delegation-design.md) for the natural extension.
