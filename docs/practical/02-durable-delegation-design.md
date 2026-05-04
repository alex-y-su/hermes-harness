# Durable Delegation for Hermes — Design

Goal: extend Hermes' synchronous `delegate_task` with a durable variant that survives parent restarts, runs for hours-to-days, and re-enters the parent's transcript when the child finishes.

This is the Option E ("Hermes-on-top-of-Hermes via shared queue") path from the original design discussion, scoped to a weekend of work.

## Why not the alternatives

- **Option A (in-process durable `delegate_task`)** — fights the OpenAI/Anthropic tool-call pairing constraint. Every `tool_use` must be paired with a `tool_result` before the next user turn. If a child takes 6 hours, the parent's transcript has an unmatched call. The compatible workaround is to return `tool_result: "queued, task_id=X"` immediately and inject the real result later as a `user` message — at which point you've built Option E with a more invasive code change.
- **Option B (cronjob / `terminal(background=True)`)** — the recommended user-facing answer today, per `tools/delegate_tool.py:2370`. Works for 1–3 fire-and-forget children. No clean fan-in. Reinvents a queue at N=5+.
- **Option C (ACP cross-Hermes dispatch)** — non-starter today. ACP in `acp_adapter/` is the Zed editor frontend protocol (`import acp`, `class HermesACPAgent(acp.Agent)` at `acp_adapter/server.py:157`), not an inter-Hermes RPC.
- **Option D (external orchestrator: LangGraph, Temporal, Prefect)** — overkill when the orchestration logic is itself LLM-driven. Temporal's strength is deterministic replay, which doesn't apply when the parent is an LLM picking sub-questions on the fly.

## Architecture

Three components, weekend-scoped.

### Component 1 — `hermes/durable_tasks/store.py`

SQLite-backed task store. ~120 lines.

Schema:

```sql
CREATE TABLE durable_task (
  task_id TEXT PRIMARY KEY,
  parent_session_id TEXT NOT NULL,
  parent_tool_call_id TEXT,
  goal TEXT NOT NULL,
  context TEXT,
  toolsets TEXT,                    -- JSON array
  role TEXT NOT NULL DEFAULT 'leaf', -- 'leaf' | 'orchestrator'
  status TEXT NOT NULL,             -- 'queued' | 'running' | 'completed' | 'failed' | 'interrupted'
  result_text TEXT,
  error TEXT,
  created_at INTEGER NOT NULL,
  started_at INTEGER,
  finished_at INTEGER,
  pid INTEGER,
  delivered_to_parent INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_durable_task_parent ON durable_task(parent_session_id, delivered_to_parent);
CREATE INDEX idx_durable_task_status ON durable_task(status);
```

API: `create(...) -> task_id`, `get(task_id)`, `list_pending_for_parent(session_id)`, `mark_running(task_id, pid)`, `mark_completed(task_id, result)`, `mark_failed(task_id, error)`, `mark_delivered(task_id)`.

Mirror the in-memory subagent registry shape from `tools/delegate_tool.py:170-218`.

Location: `~/.hermes/durable_tasks.db` (configurable via `durable_tasks.db_path`).

### Component 2 — `hermes/durable_tasks/runner.py`

Worker entry point. Runs as a detached subprocess.

```bash
python -m hermes.durable_tasks.runner --task-id <id>
```

Inside the runner:

1. Load the task from the store; mark `running`.
2. Build a child agent via the existing `_build_child_agent(...)` from `tools/delegate_tool.py:834` — same isolation, restricted toolsets, fresh context, own terminal session.
3. Run with the existing `_run_single_child(...)` from `tools/delegate_tool.py:1242`.
4. On finish, write the result + status to the store.
5. POST to the gateway webhook (`gateway/platforms/webhook.py:292`) for the parent's session, body `{task_id, status, result_excerpt}`.
6. Exit.

Spawning from the parent: `subprocess.Popen([...], start_new_session=True)` — the same pattern `tools/terminal_tool.py` already uses for `background=True`. Detached from the parent process.

### Component 3 — Parent re-entry hook

Two changes in `cli.py`:

**(a) On every turn boundary**, drain "completed durable tasks" view from the store for the current `session_id` where `delivered_to_parent = 0`. For each, append to `conversation_history` as a `user`-role message:

```
[durable_task <id> completed] <result_text>
```

(matches the shape of `cli.py:9141`'s existing user-role appends from background-terminal completion notifications)

Then mark `delivered_to_parent = 1`.

The natural seam: extend the `_pending_input` consumer at `cli.py:6688` to also drain the durable-tasks view at the same point background-terminal completions are drained.

**(b) Add a polling tool** `check_durable(task_ids: list[str]) -> dict` that lets the parent explicitly poll mid-turn for status. Useful for the model's own progress checks.

### Tool surface

Add a new tool `delegate_durable(...)` next to the existing `delegate_task`:

```python
delegate_durable(
    goal: str,
    context: str = "",
    toolsets: list[str] = [...],
    role: str = "leaf",
    timeout_seconds: int = 86400,  # default 24h
) -> {"task_id": str, "status": "queued"}
```

Returns immediately. Sidesteps the LLM tool-call pairing constraint cleanly: the immediate `tool_result` is `{status: "queued"}`; the real answer arrives later as a user-role message.

Register in `toolsets.py:197` next to the existing `delegation` toolset.

## Lifecycle

1. Parent's turn: model calls `delegate_durable(goal=...)`.
2. Tool handler creates a row in `durable_task`, spawns the runner subprocess, returns `{task_id: "X", status: "queued"}` as the tool result. **Within the same turn.**
3. Parent continues with other work or ends its turn.
4. Child runs in detached subprocess. Hours later, finishes.
5. Runner writes result to store, POSTs webhook to gateway.
6. Webhook stuffs `_pending_input` for the parent session — or if parent is offline, the next time `hermes chat --continue` runs, the on-turn-boundary drain pulls the result from the store.
7. Result re-enters parent's transcript as `[durable_task X completed] <result>` user-role message. Model sees it next turn.

## Edge cases

- **Parent offline when child finishes.** Webhook delivery fails silently; result sits in the store. Next `--continue` drains it. Good.
- **Parent restarts mid-task.** Store survives; `acp_adapter/session.py:483` restores parent session. On resume, drain pulls all completed-but-undelivered tasks. Good.
- **Child crashes.** Runner catches and writes `status="failed"`; same delivery path with the error in `result_text`.
- **Parent killed permanently.** Cron watchdog can scan `delivered_to_parent = 0` rows older than X hours and reroute via the cron `deliver` mechanism (`cron/scheduler.py:150`) — Telegram, email, log file. Borrows from Paperclip's loop-detector pattern.
- **Runaway children.** Hard timeout enforced in the runner via `signal.alarm()` or a watchdog thread. Default 24h.
- **Concurrency cap.** A `running`-count check before spawn enforces a global limit. Config: `durable_tasks.max_concurrent`, default 5.

## Reuses

| Existing Hermes piece | Used for |
|---|---|
| `tools/delegate_tool.py:834` `_build_child_agent` | Child construction |
| `tools/delegate_tool.py:1242` `_run_single_child` | Child execution loop |
| `tools/terminal_tool.py` (`background=True` pattern) | Detached subprocess spawning |
| `cli.py:6688` `_pending_input` consumer | Re-entry seam |
| `cli.py:9141` user-role append shape | Result injection format |
| `gateway/platforms/webhook.py:292` | Cross-process notification |
| `acp_adapter/session.py:483` `_restore` | Parent rehydration |
| `cron/scheduler.py:150` `deliver` | Fallback delivery to external channels |

## Out of scope (deliberately)

- Multi-host workers. Single-host first; if you need multi-host, swap SQLite for Postgres and the webhook for a real queue.
- Org-chart / role-played hierarchy. Workers are leaves with restricted toolsets. Orchestrator-of-orchestrators is left to the existing `delegate_task` depth-3 nesting.
- Reflexion / self-critique. Separate concern; see [`03-forcing-functions-extensions.md`](03-forcing-functions-extensions.md).
- Real-time TUI integration. The existing `/agents` overlay can be extended later to read from the store.

## Approximate effort

- Component 1 (store): half a day.
- Component 2 (runner + tool surface): one day.
- Component 3 (parent re-entry hook): half a day.
- Tests + edge cases: one day.

Total: ~3 days for a working durable-delegation MVP.

## Why this is the right shape

- **LLM-driven decomposition is preserved.** The parent agent decides what to delegate, when, and on what criteria — not a static graph.
- **Token cost matches the value.** A 24h-running child can spend serious tokens; the parent only pays for the dispatch and the result-read.
- **Survives every restart axis.** SQLite + webhook + on-resume drain covers parent crash, child crash, network blip, machine reboot.
- **No new dependencies.** SQLite is in stdlib; subprocess is in stdlib; the webhook gateway already exists.
- **Composes cleanly with `/goal`.** Durable children can themselves be running `/goal`-driven loops. Compositional autonomy.
