# Hermes Harness — Final Plan

A plugin distribution that turns one local Hermes installation into the boss of an indefinitely-many remote-team fleet. Local team runs perpetually on the existing factory filesystem-bus pattern; remote teams run on E2B sandboxes (substrate is pluggable); communication is A2A push-notification only, no SSE, no polling-as-primary; observability is Obsidian over markdown plus a Postgres event log.

This document is historical planning context. The current canonical boss-team contract is `docs/boss-team-contract.md`. Vocabulary follows the generic factory bus: factory / orders / approved_orders / assignments / inbox / outbox / drafts / decisions / escalations / blackboard / status / HALT.flag / supervisor / signed / envelope / founder / standing approvals / day-night / QUIET_HOURS.md / HARD_RULES.md / PROTOCOL.md / hash chain. All implementation references cite either `~/projects/demon` (A2A) or `~/projects/Nexus` (E2B) so a reader can trace every claim back to working code.

---

## 1. Goals and non-goals

**Goals**

- One Hermes deployment, the **local boss team**, runs perpetually on a single host and coordinates an arbitrary number of remote teams.
- The local team is generic — `boss`, `supervisor`, `hr`, `conductor`, `critic`, `a2a-bridge` — six profiles total, none of them domain-specialized. Domain specialists are added by the user per project.
- **Remote teams** are named (e.g. `development`, `research`, `marketing`, `support`), each provisioned as one or more E2B sandboxes. Each remote team appears to the boss as a single A2A agent regardless of internal complexity.
- **Communication**: A2A protocol day 1, push-notification feedback only (no polling, no SSE). The bridge translates the local filesystem bus to A2A wire and back.
- **Observability**: factory/ markdown bus mirrored to Obsidian for human consumption; Postgres `team_events` log for programmatic queries; LLM-trace layer optional.
- **Plugin packaging**: a single `hermes-harness` repo that brings up the local team, the bridge, the database, and the substrate driver via one install script.
- **CLI**: eventual — `harness team spawn <name> --template <kind> --substrate e2b` — abstracted on day 1, implemented when E2B integration is concrete.

**Non-goals**

- No replacement of Hermes' single-host kanban for the boss team itself — kanban is *correct* at six-profile scale.
- No replacement of Hermes' core. The plugin installs into a stock Hermes; no fork.
- No multi-region failover on day 1. Single-host boss + single-region E2B fleet is the v1 footprint.
- No cross-host coordination between two boss teams. One boss owns one fleet.
- No SSE, no polling-as-primary feedback channel. Push notifications + idempotent webhook receiver only.
- No project-specific roles in the reusable harness. Domain teams are deployment config, not plugin code.

---

## 2. Architecture overview

```
┌─────────────────────────────────────────────────────────────────────┐
│  LOCAL HOST                                                          │
│                                                                      │
│  Hermes (one installation)                                           │
│  ├── Profile: boss        — strategic CEO, writes orders             │
│  ├── Profile: supervisor  — HMAC-signs in-envelope, escalates novel  │
│  ├── Profile: hr          — routes, spawns/sunsets remote teams      │
│  ├── Profile: conductor   — owns cron, tunes beats                   │
│  ├── Profile: critic      — durable critical review of returned work │
│  └── Profile: a2a-bridge  — daemon (Python), no LLM, factory ⇄ A2A   │
│                                                                      │
│  factory/ filesystem bus  (the coordination plane, single host)      │
│  ├── orders/, approved_orders/, assignments/, inbox/, outbox/        │
│  ├── drafts/, decisions/ (hash-chained), escalations/                │
│  ├── blackboard/, status/, HALT_<profile>.flag                       │
│  ├── HARD_RULES.md (immutable), STANDING_APPROVALS.md, PROTOCOL.md   │
│  ├── QUIET_HOURS.md, PRIORITIZE.md                                   │
│  └── teams/<name>/  ← workspace folder per remote team               │
│                                                                      │
│  Postgres                  team_events log (programmatic queries)    │
│  Obsidian vault            mirror of factory/ for human inspection   │
└─────────────────────────────────────────────────────────────────────┘
                              │
                a2a-bridge translates orders → A2A wire
                              │
        ▼ A2A message/send                  ▲ A2A push-notification webhook
                              │
┌─────────────────────────────────────────────────────────────────────┐
│  REMOTE FLEET                                                        │
│                                                                      │
│  E2B Sandbox (one per remote team)         × N teams                 │
│  ├── /workspace/  ← rsynced from factory/teams/<name>/               │
│  ├── Hermes agent running with --skills harness-worker               │
│  ├── A2A server bound to port 8000                                   │
│  └── Push-notification webhook → boss's signed endpoint              │
└─────────────────────────────────────────────────────────────────────┘
```

The local layer is a familiar single-host Hermes setup with markdown bus and SQLite kanban. The remote layer is each team in its own sandbox. The A2A bridge is the only network-aware component.

---

## 3. The local boss team

Six profiles, all on the orchestration host, all reading and writing `factory/` per the generic boss-team contract. Two additions beyond the original four-role planning model: `critic` and `a2a-bridge`.

### 3.1 boss / supervisor / hr / conductor

Defined by the generic SOUL and TEAM_SOUL templates in `harness/boss_team.py`. Users add domain context through deployment config, orders, skills, and wiki pages.

### 3.2 critic — durable critical review

A profile that runs on the kanban beat (every 5 min by default), reads `factory/teams/*/outbox/` for new deliverables, and runs a fresh-context critique against the team's `criteria.md` using the existing `_build_child_agent` pattern (`tools/delegate_tool.py:834` in hermes-agent).

Mechanism:

1. Watch outbox/ across all remote teams for new artifacts.
2. For each new artifact, spawn a fresh critic child agent with context = the artifact + the team's `criteria.md` + the team's `exemplars/`. **No conversation history.** Same trick that made multi-personality work — the critic doesn't carry the writer's wrap-up gradient.
3. Critic returns either `APPROVED` or numbered list of gaps with concrete evidence.
4. APPROVED → move artifact to `factory/drafts/<channel>/` for supervisor's standing-approval check.
5. Gaps → write a revision-request envelope back into `factory/teams/<name>/inbox/`.
6. Append to `factory/decisions/<unix>_critique_<id>.md` with hash chain.

The critic's auxiliary model must be strong (pin in config). A weak critic false-passes and the durable review claim collapses.

### 3.3 a2a-bridge — daemon, not an LLM profile

This is a long-running Python process, not a Hermes-driven LLM cycle. It registers in the factory bus *as if* it were a profile (writes `status/a2a-bridge.json` heartbeat, respects `HALT_a2a-bridge.flag`) so conductor's health checks treat it identically. But it consumes zero LLM tokens.

Why Python: Hermes Harness is Python-first, and the bridge's required behavior is ordinary HTTP, SQLite, HMAC, filesystem scanning, and A2A JSON-RPC. Keeping the bridge in Python removes the Node runtime from local installation while preserving the same A2A wire contract.

Bridge responsibilities:

- Watch `factory/teams/*/inbox/` for new assignments. For each, dispatch via A2A `message/send` to the team's `agent_card_url`.
- Receive A2A push-notification webhooks at a signed endpoint. For each event: update the team's `status.json`, append to `journal.md`, write completed artifacts to `outbox/`.
- On `factory/teams/*/HALT.flag` presence: send A2A `tasks/cancel` to the team.
- Maintain Postgres `team_events` log on every event.
- Heartbeat to `factory/status/a2a-bridge.json` every 30s.

### 3.4 The perpetual loop

Each LLM-driven profile (boss / supervisor / hr / conductor / critic) runs a cron beat per `06_protocol.md` §11. The bridge runs as a long-lived process. None of them stops; HALT flags are the only stop signal.

Anti-wrap-up enforcement at the SOUL.md level (per `practical/01-247-recipe.md`): every LLM profile's SOUL.md ends with the line *"You are running on a long-horizon mission. No human is waiting for a polished summary at the end of each cycle. Continue until criteria are met or you are hard-blocked."*

`agent.max_turns: 500`, `goals.max_turns: 1000`, `compression.threshold: 0.70`, `approvals.mode: off`, `hooks_auto_accept: true`, `delegation.max_iterations: 200`. All set in the per-profile `config.yaml`, shipped with the plugin.

---

## 4. Workspace folders — the team manifest

Each remote team is a named subdirectory under `factory/teams/`. The folder *is* the team's contract with the boss.

```
factory/teams/<team-name>/
├── brief.md              ← team charter (boss-set), the canonical mission statement
├── SOUL.md               ← team identity, voice, operating rules (cloned from template)
├── TEAM_SOUL.md          ← team-specific charter (boss's order spec, evolved over time)
├── AGENTS.md             ← factory-aware operating rules (knows it reports to boss)
├── transport.json        ← {protocol, agent_card_url, push_notification_token, auth_secret_ref}
├── status.json           ← digest the boss queries each cycle
├── journal.md            ← team's running narrative back to boss (Obsidian-linked)
│
├── inbox/                ← assignments from local hr (one file per assignment)
├── outbox/               ← deliverables back to boss (critic gates)
├── drafts/<channel>/     ← outbound public drafts subject to standing-approval
├── exemplars/            ← good-output examples (curated)
├── context/              ← input artifacts the team has read access to
├── source/               ← sparse git checkout if the team operates on code
├── criteria.md           ← acceptance criteria — what the critic checks against
├── HALT.flag             ← presence halts the team (bridge sends tasks/cancel)
│
└── internal/             ← team's OWN multi-agent setup (opaque to boss)
    ├── PROTOCOL.md       ← team-internal protocol (mirrors local factory pattern)
    ├── profiles/         ← team's sub-profiles (writer, reviewer, ...)
    ├── orders/           ← team-internal orders (from team's coordinator)
    ├── assignments/      ← team-internal routing
    ├── inbox/<sub>/      ← per-sub-agent inbox
    ├── outbox/<sub>/     ← per-sub-agent outbox
    ├── status/<sub>.json ← per-sub-agent heartbeat
    └── decisions/        ← team-internal decisions (separate hash chain)
```

The `internal/` subtree is **the team's mini-factory** — exactly the same single-host pattern as the boss team, just inside an E2B sandbox. Each remote team can run as its own multi-profile setup with internal kanban, bus, sub-agents.

Local boss never reads `internal/`. The team's coordinator owns it. If the founder needs to inspect, hr provides an `inspect_team(<name>)` tool that rsyncs `internal/` on demand for forensic viewing.

The plugin ships **two team templates** at `templates/`:

- `single-agent-team/` — one Hermes profile, lightweight, for atomic missions. Skips most of `internal/`.
- `multi-agent-team/` — full mini-factory with 4 sub-profiles by default (coordinator + worker + reviewer + scribe). Users add domain sub-profiles per project.

User picks template at spawn:

```
hr writes:        approved_orders/<id>.md with type=spawn_team, team=marketing,
                  template=multi-agent, substrate=e2b
hr provisions:    new factory/teams/marketing/ from templates/multi-agent-team/
                  → fills brief.md, criteria.md, transport.json placeholders
                  → calls SubstrateDriver.provision(workspace_path)
                  → registers team in wiki/team_roster_remote.md
```

---

## 5. The substrate abstraction

Day 1 substrate is E2B. Other substrates (Modal, Fly Machines, dedicated VMs, external A2A) plug in behind a `SubstrateDriver` interface.

```python
class SubstrateDriver(Protocol):
    async def provision(
        self,
        team_name: str,
        workspace_path: Path,
        template: TeamTemplate,
        timeout_seconds: int,
    ) -> SubstrateHandle: ...

    async def boot(self, handle: SubstrateHandle) -> AgentCardURL: ...

    async def sync_in(self, handle: SubstrateHandle, workspace_path: Path) -> None: ...

    async def sync_out(self, handle: SubstrateHandle, workspace_path: Path) -> None: ...

    async def health(self, handle: SubstrateHandle) -> SubstrateHealth: ...

    async def cancel(self, handle: SubstrateHandle) -> None: ...

    async def archive(self, handle: SubstrateHandle, archive_path: Path) -> None: ...
```

`SubstrateHandle` is opaque to the rest of the system — for E2B it's `{sandbox_id, hostname, port}`; for external-A2A teams it's just `{agent_card_url}`.

### 5.1 E2BDriver — day-1 implementation

Implementation references `~/projects/Nexus/packages/background-tasks/src/sandbox.ts` (570 lines, framework-free, direct port candidate). Key patterns to copy:

- **Sandbox creation** with declarative template (Nexus uses `Template().fromImage()` builder; no Dockerfile). Bake heavy tools in the template; runtime install is too slow.
- **Setup script consolidation**: one `commands.run()` with a heredoc-built shell script, not 7-8 round trips. Per Nexus `task-orchestrator.service.ts:111-118` lesson — each `commands.run` is an RPC; batch via heredocs.
- **File sync via E2B native APIs**, not rsync. `sandbox.files.write([{path, data}, ...])` batched. For getting changes back: `sandbox.files.watchDir('/workspace', cb, {recursive: true, timeoutMs: 0, onExit: reconnect})` per `~/projects/Nexus/src/sandbox/vfs/vfs-watcher.service.ts:154`. Conceptually rsync-style, mechanically E2B-native.
- **Watcher reconnect**: gRPC streams die silently. Exponential backoff 2s/4s/8s/16s/32s with `Sandbox.connect(sandboxId)` and re-attach. Non-obvious E2B behavior — copy verbatim from `vfs-watcher.service.ts:218-295`.
- **Watcher skip-list**: `node_modules/`, `.git/`, `dist/`, `build/`, `__pycache__/`, `.venv/`, `venv/`, dotfiles. Without this, npm-install events crash heartbeats. From `vfs-watcher.service.ts:309-321`.
- **Health check**: `Sandbox.connect(sandboxId)` — failure = dead. Per Nexus `health-monitor.service.ts:179-197`.
- **Slot semaphore**: in-process counter, `maxConcurrentSandboxes: 20` default. Per `sandbox-manager.service.ts:85-106`. For multi-boss-instance setups, this needs to move to Postgres.
- **Short-lived JWT**, not real API keys. Sandbox should never see provider keys; route through a local LLM proxy with 1h tokens. Per `task-orchestrator.service.ts:251-257`.

### 5.2 The gap to fill — A2A endpoint exposure

Nexus runs one-shot CLI commands inside sandboxes; it does not expose long-lived A2A endpoints. The plugin **adds**:

```
sandbox.commands.run(
    'cd /workspace && hermes serve --profile coordinator --skills harness-worker '
    '--a2a-port 8000 --push-notification-url $BOSS_PUSH_URL '
    '--push-notification-token $TEAM_PUSH_TOKEN',
    {background: true, envs: {...}},
)
agent_card_url = `https://${sandbox.getHost(8000)}/.well-known/agent-card.json`
```

`sandbox.getHost(port)` is a real E2B SDK feature, just unused in Nexus. The Hermes agent inside runs the A2A server through the selected Hermes A2A adapter and registers its push-notification target back to the boss.

### 5.3 24-hour cap

E2B Pro caps sandboxes at 24h. Two strategies, picked per team-class in standing approvals:

- **Short-mission teams (<24h)**: spawn-execute-archive cycle, no special handling.
- **Long-running teams (>24h)**: at the 23h mark, the team's coordinator writes a checkpoint to `internal/checkpoint.json` + drains in-flight assignments. Bridge sees the checkpoint, hr provisions a fresh sandbox with the checkpoint mounted, transport.json updates, old sandbox archived. The team's `journal.md` and `status.json` are continuous from the boss's view.

---

## 6. The A2A bridge — concrete design

Single Python process. Watches the local filesystem bus and translates to A2A JSON-RPC wire calls while receiving signed push notifications.

### 6.1 Outbound — boss → team

When the bridge detects a new file in `factory/teams/<name>/inbox/<asn-id>.md`:

1. Read the assignment envelope (per `06_protocol.md` §3 schema).
2. Read `factory/teams/<name>/transport.json` for the team's `agent_card_url` and bearer token.
3. Construct A2A `message/send` JSON-RPC envelope (template from `~/projects/demon/src/protocol/a2a/client.ts:55-105`):
   ```json
   { "jsonrpc": "2.0", "id": "send-<uuid8>", "method": "message/send",
     "params": {
       "message": { "kind": "message", "messageId": "msg-<unix>",
         "role": "user",
         "parts": [{"kind": "text", "text": "<assignment markdown>"}],
         "contextId": "<team-name>" },
       "metadata": { "assignment_id": "<asn-id>", "order_id": "<ord-id>" } } }
   ```
4. POST with `Authorization: Bearer <team token>`. Treat HTTP-200 + JSON-RPC `error` as failure.
5. On success, capture the returned `task_id` and write to `factory/teams/<name>/inbox/<asn-id>.dispatched.json` so the assignment is not re-sent on bridge restart.
6. Append to Postgres `team_events`: `{team_name, ts, kind: "dispatched", state: "submitted", payload_path: ...}`.
7. Move `<asn-id>.md` to `<asn-id>.in-flight.md`.

### 6.2 Inbound — team → boss (push-notification)

The bridge runs an Express receiver on a publicly-routable URL (or behind Tailscale / similar):

```
POST /a2a/push  Authorization: Bearer <token>
                X-A2A-Notification-Token: <hmac-signature>
```

Reused logic from `~/projects/demon/src/protocol/a2a/retry-push-sender.ts` (the inverse direction). Two payload modes:

- **Peer mode**: full JSON-RPC `message/send` (the team is itself an A2A peer). Bearer auth. Body parsed as A2A `message`.
- **Webhook mode**: raw `Task` JSON with `X-A2A-Notification-Token` HMAC of `(task_id, state, sequence)`. **Required for our setup** because demon doesn't sign inbound A2A; we add this for distributed safety.

Per A2A state, bridge actions:

| A2A state | Bridge action |
|---|---|
| `working` | Append to `factory/teams/<name>/journal.md`; update `status.json.last_event_at` and `state`. |
| `input-required` | Write `factory/escalations/team_<name>_<reason>.md`. Supervisor picks up next cycle (day/night flow per QUIET_HOURS.md). |
| `auth-required` | Same as `input-required` but with `class: secret_request`. Supervisor knows the difference. |
| `completed` | Write artifacts to `factory/teams/<name>/outbox/`. Critic profile picks up next cycle. Mark assignment file as `<asn-id>.completed.md`. |
| `failed` | Write `factory/escalations/failed_team_<name>_<reason>.md`. Append to `decisions/`. hr sees, decides retry vs sunset. |
| `canceled` | Confirm the cancel was bridge-initiated (HALT flag exists) or unsolicited (rare; treat as failure). |
| `submitted` / `rejected` | Not used. (Per demon's pattern — only `working / completed / failed / canceled` flow on the wire.) |

Idempotency: every event has a `(team_id, sequence)` pair. Bridge maintains a Postgres-backed dedupe table; duplicate sequences are no-ops. Aligns with demon's lesson — they use `INSERT OR REPLACE` on `task_id` (`sdk-task-store.ts:26-29`); we do the same with explicit `ON CONFLICT DO NOTHING` for events.

### 6.3 Cancellation — boss → team

When `factory/teams/<name>/HALT.flag` appears (hr writes it on a sunset order or supervisor writes it on a §2 mission refusal):

1. Bridge reads `transport.json` for `task_id`.
2. Sends A2A `tasks/cancel` JSON-RPC envelope to the team. (Demon doesn't have outbound cancel — we write this from scratch; envelope shape from `client.ts:66-83`.)
3. On confirmation, marks team `canceled` in Postgres.
4. Calls `SubstrateDriver.cancel(handle)` to kill the sandbox.
5. Calls `SubstrateDriver.archive(handle, archive_path)` and moves `factory/teams/<name>/` to `archive/teams_<name>_<ts>/`.

### 6.4 Anti-patterns to avoid (lessons from demon)

- **Don't downgrade discovered peers.** Once a team's transport is registered, never let a partial inbound re-registration overwrite it. Demon learned this in commit `ddd6b41` (`peer-registry.ts:245-263`).
- **Sanitize pushUrl whitespace.** Demon's commit `ccda2c2` had to add `.trim()` because peers sent malformed URLs.
- **Hold the A2A task open until async work drains.** Don't ack `completed` from the bridge until `status.json` says terminal AND outbox/ has the artifact. Demon's commit `c9c21f4`.
- **Push, don't poll.** A2A's push-notification design is the primary feedback channel. Polling is a fallback only when no event has arrived in N minutes (suggests bridge-team partition). Per demon's invariant: `capabilities.streaming: false`.

---

## 7. Postgres `team_events` log

Programmatic queries the boss can run without loading 1400 journals. Single `team_events` table indexed for sub-200ms queries.

```sql
CREATE TABLE team_events (
  event_id     BIGSERIAL PRIMARY KEY,
  team_name    TEXT NOT NULL,
  task_id      TEXT NOT NULL,           -- A2A task_id
  sequence     BIGINT NOT NULL,
  ts           TIMESTAMPTZ NOT NULL,
  kind         TEXT NOT NULL,           -- 'dispatched' | a2a-state | 'critic-approved' | 'critic-gaps'
  state        TEXT,                    -- last A2A state snapshot
  cost_cents   INTEGER,
  duration_ms  BIGINT,
  payload_path TEXT,                    -- pointer to journal/artifact on disk
  signature    TEXT NOT NULL,           -- bridge's HMAC of (team_name, task_id, sequence, kind, state)
  UNIQUE (team_name, task_id, sequence)
);
CREATE INDEX team_events_state_ts        ON team_events (state, ts DESC);
CREATE INDEX team_events_team_ts         ON team_events (team_name, ts DESC);
CREATE INDEX team_events_team_kind_ts    ON team_events (team_name, kind, ts DESC);
```

Boss-side tool `query_remote_teams(filter)` runs one indexed query and returns ≤200 tokens of digest. Examples the boss can ask:

- *"failing teams over $0.50 in the last 24h"* → `WHERE state='failed' AND cost_cents > 50 AND ts > NOW() - interval '24 hours'`
- *"teams stale >5 min"* → `team_name NOT IN (SELECT team_name FROM team_events WHERE ts > NOW() - interval '5 min')`
- *"per-team cost burn last 7 days"* → `SELECT team_name, SUM(cost_cents) FROM team_events WHERE ts > NOW() - interval '7 days' GROUP BY team_name`

The hr profile's `query_remote_teams` is the daily/hourly heartbeat surface; conductor uses it for beat tuning; supervisor uses it for envelope-validity checks; boss reads only the digest.

---

## 8. Obsidian observability

The factory bus is markdown. Mirror the live `factory/` tree to an Obsidian vault or another read-only viewer when human inspection is needed.

### 8.1 What to mirror

- All of `factory/` (including per-team folders) — the founder opens the vault and sees the live state.
- `factory/teams/<name>/journal.md` is **append-only markdown with [[wiki-links]]** generated by the bridge on each event. Obsidian's graph view becomes the team-task dependency view for free.
- `factory/dashboard.md` — auto-regenerated by conductor each cycle. Top-N teams by cost, by lateness, by critic-rejection. Cross-references via `[[team_<name>]]`.
- `factory/team_roster.md` — auto-generated by hr. Active teams + their templates + their substrates + their last-checkpoint summaries.
- Boss's strategic memos at `wiki/lessons/strategic_<date>.md`.
- decisions/ hash chain (founder verifies integrity by running a hash-recompute script).

### 8.2 What NOT to mirror

- `factory/teams/<name>/internal/` subtrees — these are the team's private operating area, not for founder real-time inspection.
- Postgres tables — those are programmatic.

### 8.3 Layer 2 charts

A small Grafana or Metabase pointed at Postgres gives the founder time-series charts without leaving the markdown world. Optional. Not load-bearing.

### 8.4 Layer 3 (optional)

LLM tracing via Langfuse / Phoenix / Helicone bolted to Hermes' `pre_llm_call` / `post_llm_call` hooks (`hermes_cli/plugins.py:78`). Add when you need to debug a specific team's prompt path.

---

## 9. CLI — `harness team ...` (deferred but specified)

Day 1: a Python module wrapped as a Hermes tool the boss can call.

```
hr.spawn_team(name="research", template="single-agent", substrate="e2b", brief="...")
```

Returns: `{team_name, agent_card_url, sandbox_id}` synchronously after substrate provisioning completes.

Day N (when the abstraction is concrete): a CLI with the same surface plus operator UX:

```
harness team spawn research \
  --template single-agent \
  --substrate e2b \
  --brief brief.md \
  --criteria criteria.md

harness team list
harness team status <name>
harness team halt <name>
harness team archive <name>
harness team logs <name> [--follow]
harness team inspect <name>      # rsyncs internal/ for forensics

harness substrate list
harness substrate health
```

CLI is pure thin wrapper over the same dispatch surface the boss agent uses. No separate code path.

---

## 10. Plugin packaging — `hermes-harness` repo

```
hermes-harness/
├── README.md
├── install.sh                   ← one-command install: factory/, profiles, bridge, db
├── pyproject.toml               ← Python tools, substrate drivers, bridge daemon
│
├── skills/                      ← markdown skill packs
│   ├── boss/SKILL.md
│   ├── supervisor/SKILL.md
│   ├── hr/SKILL.md
│   ├── conductor/SKILL.md
│   ├── critic/SKILL.md
│   ├── harness-worker/SKILL.md  ← loaded into every remote team's coordinator
│   └── harness-coordinator/SKILL.md ← multi-agent template's internal coordinator
│
├── tools/                       ← Hermes tool registry additions
│   ├── dispatch_team.py
│   ├── spawn_team.py
│   ├── sunset_team.py
│   ├── query_remote_teams.py
│   ├── inspect_team.py
│   └── escalate.py
│
├── hooks/                       ← shell + python hooks via plugins.py
│   ├── pre_tool_call/sign_envelope.sh
│   ├── post_tool_call/persist_event.py
│   └── on_session_start/load_factory.sh
│
├── profiles/                    ← installable profile bundles
│   ├── boss/{SOUL.md, AGENTS.md, config.yaml}
│   ├── supervisor/{...}
│   ├── hr/{...}
│   ├── conductor/{...}
│   ├── critic/{...}
│   └── a2a-bridge/{...}         ← daemon config, not LLM
│
├── templates/                   ← remote-team templates
│   ├── single-agent-team/
│   │   ├── brief.md (placeholder)
│   │   ├── SOUL.md
│   │   ├── AGENTS.md
│   │   ├── criteria.md
│   │   ├── transport.json (placeholder)
│   │   └── status.json (initial)
│   └── multi-agent-team/
│       ├── (everything in single-agent-team/)
│       └── internal/
│           ├── PROTOCOL.md
│           └── profiles/
│               ├── coordinator/
│               ├── worker/
│               ├── reviewer/
│               └── scribe/
│
├── bus_template/                ← initial factory/ scaffolding
│   ├── HARD_RULES.md            ← skeleton, founder fills
│   ├── PROTOCOL.md              ← copied verbatim from team docs
│   ├── STANDING_APPROVALS.md    ← starts empty
│   ├── QUIET_HOURS.md           ← skeleton
│   └── README.md
│
├── harness/bridge/              ← Python a2a-bridge daemon
│   ├── cli.py                   ← console entrypoint
│   ├── daemon.py                ← push receiver + watcher
│   ├── a2a_client.py            ← JSON-RPC send/cancel adapter
│   ├── push.py                  ← signed push receiver logic
│   ├── store.py                 ← SQLite assignment/event access
│   └── hmac.py                  ← signature gen + verify
│
├── infra/
│   ├── postgres/schema.sql      ← team_events
│   ├── obsidian/vault.json      ← config for mirror
│   └── e2b/template.ts          ← E2B template definition (Template().fromImage())
│
├── substrate/                   ← Python substrate drivers
│   ├── base.py                  ← SubstrateDriver protocol
│   ├── e2b_driver.py            ← day-1 implementation, ported from Nexus
│   └── external_a2a_driver.py   ← stub, for non-Hermes A2A agents
│
├── cli/                         ← deferred but stub
│   └── harness/__init__.py
│
└── docs/
    ├── README.md
    ├── INSTALL.md
    ├── ARCHITECTURE.md          ← copy of this plan
    └── HARD_RULES_TEMPLATE.md
```

`install.sh` does, in order:

1. Verify Hermes is installed and a profile-creation works.
2. Create `~/.hermes/profiles/{boss,supervisor,hr,conductor,critic,a2a-bridge}/` from `profiles/`.
3. Copy `bus_template/` to `<project>/factory/`.
4. Copy `templates/` to `~/.hermes/harness/templates/`.
5. `pip install -e .` for tools and substrate drivers.
6. Verify `harness-a2a-bridge --help`.
7. Spin up Postgres, run `infra/postgres/schema.sql`.
8. Initialize Obsidian vault at the configured path with `infra/obsidian/vault.json`.
9. Register cron entries via `hermes cron create` for boss/supervisor/hr/conductor/critic (5-min beats by default).
10. Start the a2a-bridge daemon as a launchd / systemd service.
11. Print boot prompt for the founder to paste into their first boss session.

---

## 11. Implementation phases (in agent-iterations)

Plan in agent-iteration units per the user's CLAUDE.md. One iteration ≈ one focused implementer-agent run.

### Phase 0 — scaffold (~5 iters)

- Create `hermes-harness` repo skeleton, license, README, install.sh stub.
- Set up Python project with `tools/` and `substrate/` packages.
- Set up Python bridge package and console script.
- Postgres schema in `infra/postgres/schema.sql`.

### Phase 1 — local boss team (~8 iters)

- Strip JESUSCORD specifics from boss/supervisor/hr/conductor SOULs; ship generic versions in `profiles/`.
- Write `critic` profile (SOUL + AGENTS + cycle definition).
- Write `bus_template/` skeletons for HARD_RULES, PROTOCOL, STANDING_APPROVALS, QUIET_HOURS.
- Hooks for envelope signing (HMAC of order_id, content, secret).
- Tool: `escalate.py` writes to `factory/escalations/`.
- Verify: install.sh on a fresh Hermes brings up 5 LLM profiles + factory/, boss writes orders, supervisor signs, decisions/ chain accumulates, no remote teams yet.

### Phase 2 — A2A bridge (~10 iters)

- Port `retry-push-sender.ts` from demon. Adjust payload shapes for our envelope schema.
- Port `peer-registry.ts` with the `discovered`/`partial` state distinction.
- Port `agent-card.ts` with our agent's capabilities (boss-side: `pushNotifications: true`, `streaming: false`).
- Build `factory-watcher.ts` using chokidar over `factory/teams/*/inbox/` and `factory/teams/*/HALT.flag`.
- Build Express receiver at `/a2a/push` with HMAC verification (the gap we add over demon).
- Postgres event-log writer.
- Heartbeat to `factory/status/a2a-bridge.json`.
- Launchd/systemd unit for the daemon.
- Verify: a stub remote team running locally exposing an A2A AgentCard receives a `factory/inbox/<id>/` envelope, completes, drops `factory/teams/<id>/outbox/<artifact>.md`.

### Phase 3 — substrate driver + templates (~12 iters)

- Define `SubstrateDriver` protocol in `substrate/base.py`.
- Port Nexus's `packages/background-tasks/src/sandbox.ts` to Python in `substrate/e2b_driver.py`. Specifically: setup-script consolidation, batched `files.write`, `watchDir` with reconnect, `Sandbox.connect()` health check, slot semaphore.
- Define E2B template at `infra/e2b/template.ts` baking Hermes + git + ripgrep + python + node + jq + curl + ssh.
- Add `sandbox.commands.run('hermes serve --a2a-port 8000 ...', {background: true})` + `sandbox.getHost(8000)` for endpoint exposure (the gap Nexus didn't fill).
- Build `single-agent-team/` template.
- Build `multi-agent-team/` template with internal/ scaffolding.
- hr's `spawn_team` tool calls `SubstrateDriver.provision()` + writes workspace folder + announces blackboard + appends to decisions/.
- Verify: a `spawn_team` order with `team_kind: remote, substrate: e2b, template: single-agent` produces a working remote team end-to-end.

### Phase 4 — observability (~5 iters)

- `query_remote_teams` tool — Postgres query layer.
- `inspect_team` tool — on-demand rsync of `internal/`.
- Obsidian vault config + auto-mirror of factory/ via fsnotify.
- Auto-generated `factory/dashboard.md` and `factory/team_roster.md` written by conductor each cycle.
- Verify: founder opens vault in Obsidian, graph view shows full order→assignment→team→deliverable chain for remote teams; `query_remote_teams("WHERE state='failed' AND cost_cents > 50")` returns the right answer in <200ms with 1000 simulated team events.

### Phase 5 — CLI (~5 iters)

- `harness team {spawn,list,status,halt,archive,logs,inspect}` as thin wrapper over hr's tool surface.
- `harness substrate {list,health}`.
- Verify: CLI commands produce identical bus-state changes to direct Hermes tool calls. End-to-end: `harness team spawn research --template single-agent --brief brief.md` produces a healthy remote team in <60s wall-clock.

### Phase 6 — long-mission handling (~6 iters)

- Checkpoint-and-respawn for >24h missions in `e2b_driver.py`.
- Bridge-side handling of mid-mission `transport.json` updates.
- Verify: a deliberately-23.5h-aged team is checkpointed, archived, fresh sandbox provisioned with the checkpoint, journal continues seamlessly from boss's view.

**Total: ~51 iterations** to a complete, tested, founder-usable plugin.

---

## 12. Honest caveats

- **Bridge availability is load-bearing.** If the a2a-bridge daemon dies, no remote team gets new assignments and no completions arrive. conductor's stale-detection (>5 min on `status/a2a-bridge.json`) catches it; hr restarts via systemd. For higher availability, run two bridge processes against the same Postgres event log; A2A's idempotency keys (`task_id` + `sequence` UNIQUE constraint) prevent duplicate effects. Defer until single-bridge SLA is the binding constraint.
- **Bus is eventually consistent.** factory/teams/<name>/ reflects what the bridge has heard, not necessarily what the team is *currently* doing. status.json `last_event_at` >5 min old → assume the team is stuck or partitioned. Founder needs to internalize this; "what's in factory/" is *eventually consistent* with remote-team reality.
- **A2A is still maturing in 2026.** [a2a-protocol.org](https://a2a-protocol.org/) and [a2aproject/a2a-python](https://github.com/a2aproject/a2a-python) are real, donated to the Linux Foundation. But the heterogeneous-agent-fleet promise is partly aspirational — most production agent platforms speak custom HTTP or MCP-tool-server. The bridge being A2A means *future* heterogeneity is cheap; today, every team is Hermes.
- **E2B file-sync is API-driven, not rsync.** Nexus's pattern (`sandbox.files.write` + `watchDir`) is mechanically different from rsync. We say "rsync-style" colloquially but the implementation is E2B-native. If you migrate to a substrate where rsync is natural (Fly Machines, dedicated VMs), the substrate driver wraps it.
- **24h mission boundary is soft.** The checkpoint-and-respawn pattern works but introduces a discontinuity in the team's internal state (sub-profiles see a fresh boot). Teams with non-checkpointable internal state (e.g. an in-flight long-running shell command) lose work at the boundary. Boss decides which teams are >24h-eligible via standing approvals.
- **Bridge cost is non-zero but small.** A Python daemon + database connection + filesystem scan per ~1–10s burns negligible CPU. The dominant cost is LLM tokens (boss/supervisor/hr/conductor/critic each running every 5 min) — that's the lever to optimize, not bridge infrastructure.
- **HMAC-key rotation is a future problem.** Day-1 ships one `BRIDGE_SECRET`. Rotation requires a brief downtime where the bridge accepts both old and new signatures. Defer until you have a regulatory or incident-driven reason to rotate.
- **Per-team substrate cost ceilings are critical.** At fleet scale, a single team in a runaway loop can burn $1000s in E2B + LLM tokens before the conductor's hourly cost beat catches it. HARD_RULES.md §1 caps + per-team budget envelopes in standing approvals + bridge-side enforcement at the substrate level (kill sandbox at $X/hr threshold) are non-negotiable. Specify these before phase 3.
- **The plugin is opinionated.** No support for boss agents that aren't Hermes. No support for substrates that don't expose a long-lived port. No support for non-A2A protocols (yet). If your fleet needs any of these, write the corresponding driver — but the architecture stays.
- **Recursive delegation depth needs a cap.** Nothing in A2A or the architecture prevents `marketing` → `marketing/europe` → `marketing/europe/germany` → … . Set `max_delegation_depth = 3` in HARD_RULES.md §12 from day 1. Higher depths require explicit founder approval.

---

## 13. References

**Local boss team source-of-truth:**
- `~/projects/hermes-harness/docs/boss-team-contract.md` — canonical boss-team contract.
- `~/projects/hermes-harness/harness/boss_team.py` — generated generic profiles, contracts, blueprints, wiki scaffold, and verification.
- `~/projects/hermes-harness/bus_template/` — minimal generic bus template files.

**A2A reference implementation (~/projects/demon):**
- `src/protocol/a2a/retry-push-sender.ts` — push delivery, copy as-is
- `src/protocol/a2a/sdk-task-store.ts`, `sdk-push-store.ts` — port to Postgres
- `src/protocol/a2a/executor-adapter.ts` + `src/transport/task-engine.ts:35-38` — the bridge interface pattern
- `src/protocol/a2a/peer-registry.ts` — `discovered`/`partial` state distinction
- `src/protocol/a2a/agent-card.ts` — card builder
- `src/protocol/a2a/client.ts:55-105` — outbound `message/send` template
- `src/auth/bearer.ts` — UserBuilder (50 lines, direct copy)
- demon's `AGENTS.md:58-59` invariants — `streaming: false`, no SSE
- demon's commits `b7933fc, ddd6b41, ccda2c2, c9aa69a, c9c21f4` — anti-patterns we avoid

**E2B reference implementation (~/projects/Nexus):**
- `packages/background-tasks/src/sandbox.ts` (570 lines) — direct port to Python in `substrate/e2b_driver.py`
- `src/sandbox/agents/sandbox-manager.service.ts:85-106` — slot semaphore (port)
- `src/sandbox/vfs/vfs-watcher.service.ts:113-295, 492-626` — watchDir + reconnect (direct copy of pattern)
- `e2b-templates/claude-code/claude-code-full/template.ts` — template definition pattern (adapt for Hermes)
- `src/sandbox/agents/health-monitor.service.ts:179-235` — `Sandbox.connect()` health check (port)
- `task-orchestrator.service.ts:111-118` — setup-script consolidation lesson

**Hermes core seams the plugin uses:**
- `cli.py:6541, :9922` — `_pending_input` queue (re-entry path)
- `tools/delegate_tool.py:834` — `_build_child_agent` (used by critic for fresh-context critique)
- `hermes_cli/plugins.py:78` — VALID_HOOKS (where bridge-event hooks register)
- `tools/cronjob_tools.py` — cron entries for the 5 LLM profiles
- `agent/context_compressor.py:465` — compaction trigger (raise threshold to 0.70 in profile config)
- `tools/memory_tool.py:131-186` — MEMORY.md autoinjection (bus-aware status digest lives here)

---

End of plan. Start at Phase 0.
