# Hermes Harness Product Specification and Implementation Plan

## 1. Purpose

Hermes Harness is a plugin distribution that turns one local Hermes installation into the durable coordinator for a fleet of remote Hermes teams.

The local boss team remains a single-host Hermes factory using the existing filesystem bus. Remote teams run in isolated substrates, with E2B as the first supported substrate. The network boundary is crossed only by an A2A bridge that sends assignments to remote teams and receives push-notification updates back.

This specification converts `docs/practical/07-hermes-harness-plugin-plan.md` into a product-facing contract and an implementation plan. It also resolves the main execution risks identified in review:

- Secrets must not live in mirrored markdown workspaces.
- Assignment-to-A2A-task mapping must be explicit.
- Local lifecycle events and A2A task events must both fit the SQLite database model.
- Multi-agent remote teams need a real boot process, not only a coordinator command.
- The push endpoint needs install-time public HTTPS configuration.
- Obsidian mirroring must exclude private and secret-bearing paths.
- Budget enforcement is intentionally out of scope for v1; cost risk is accepted until explicit limits are added.

## 2. Product summary

Hermes Harness provides:

- A generic local boss team with six profiles: `boss`, `supervisor`, `hr`, `conductor`, `critic`, and `a2a-bridge`.
- A `factory/teams/<name>/` contract for each remote team.
- A Python A2A bridge that translates local filesystem assignments into A2A `message/send` calls and translates push-notification updates back into local factory state.
- An E2B substrate driver for provisioning, booting, syncing, health checking, canceling, and archiving remote teams.
- A SQLite event log for low-token team queries and operational dashboards.
- An Obsidian mirror for human-readable fleet observability.
- A future CLI surface that wraps the same tools used by the `hr` profile.

## 3. Product goals

### 3.1 Primary goals

- Let one local Hermes installation coordinate many remote teams.
- Keep the local boss team on the existing single-host factory bus.
- Make each remote team appear to the boss as one A2A peer, regardless of whether the remote team is internally single-agent or multi-agent.
- Use push notifications as the primary feedback path.
- Preserve auditability through markdown artifacts, signed envelopes, hash-chained decisions, and a SQLite event log.
- Package the system as an installable plugin without forking Hermes core.

### 3.2 Product outcomes

- A founder can install Hermes Harness into a stock Hermes setup.
- The boss can request a named remote team through `hr.spawn_team`.
- The bridge can dispatch an assignment to the team.
- The remote team can report `working`, `input-required`, `completed`, `failed`, and `canceled` states by push notification.
- Completed artifacts land in the local team's review flow.
- The critic gates returned work before supervisor standing approvals.
- The founder can inspect live state in Obsidian and query operational state through `query_remote_teams`.
- The system can halt, archive, and respawn remote teams safely.

## 4. Non-goals

- Do not replace Hermes core.
- Do not replace the local boss team's single-host factory bus.
- Do not support multiple boss teams coordinating the same fleet in v1.
- Do not require SSE or streaming.
- Do not use polling as the primary feedback mechanism.
- Do not ship JESUSCORD-specific roles or domain-specific specialists.
- Do not support non-Hermes boss agents in v1.
- Do not support substrates that cannot expose a long-lived A2A endpoint in v1.
- Do not expose remote team `internal/` folders in the live Obsidian mirror by default.

## 5. Users and personas

### 5.1 Founder/operator

The human who installs the plugin, defines hard rules, creates standing approvals, monitors the Obsidian vault, and intervenes on escalations.

Needs:

- Simple installation.
- Clear operational dashboards.
- Safe defaults for cost, secrets, and shutdown.
- Forensic inspection tools when something goes wrong.

### 5.2 Local boss team

The six-profile local Hermes team that owns strategy, routing, signing, critique, scheduling, and network bridging.

Needs:

- Stable filesystem contracts.
- Low-token summaries of remote fleet state.
- Deterministic tools for spawning, dispatching, querying, halting, and archiving.
- Explicit escalation paths.

### 5.3 Remote team coordinator

The A2A-facing entry point inside each remote team.

Needs:

- A clear assignment envelope.
- A local workspace.
- A way to emit push-notification status and artifacts.
- A private internal bus if the team uses the multi-agent template.

### 5.4 Maintainer

The engineer who extends substrates, bridge behavior, templates, tools, and package installation.

Needs:

- Separated bridge, substrate, template, and tool responsibilities.
- Stable database schema.
- Reproducible E2B templates.
- Explicit integration tests and acceptance criteria.

## 6. Product principles

- Local-first coordination: `factory/` remains the source of operational truth for the local boss team.
- Network isolation: only the bridge and substrate driver are network-aware.
- One team, one peer: every remote team presents as a single A2A peer to the local boss.
- Push-first feedback: push notification is the normal completion and progress path.
- Idempotent effects: repeated push events and bridge restarts must not duplicate dispatches, artifacts, or event log rows.
- No secrets in markdown: mirrored folders may contain secret references, never raw tokens or provider keys.
- Human-readable state: every important action leaves markdown evidence.
- Queryable state: SQLite stores compact operational events for programmatic queries.
- Bounded autonomy: recursion depth, quiet hours, hard rules, and standing approvals constrain remote action.

## 7. System overview

### 7.1 Components

| Component | Runtime | Responsibility |
|---|---:|---|
| `boss` | Hermes LLM profile | Strategy, orders, mission direction |
| `supervisor` | Hermes LLM profile | Envelope signing, standing approval checks, escalations |
| `hr` | Hermes LLM profile | Routing, team spawning, team sunset, roster management |
| `conductor` | Hermes LLM profile | Cron beats, health checks, dashboard generation |
| `critic` | Hermes LLM profile | Fresh-context critique of returned artifacts |
| `a2a-bridge` | Python daemon | Filesystem-to-A2A dispatch, push receiver, event logging |
| `substrate` | Python package | E2B and future substrate provisioning |
| `SQLite` | Embedded database | Event log, dedupe, assignment/task mapping |
| `Obsidian mirror` | Filesystem mirror | Founder-facing live state |

### 7.2 Data planes

| Plane | Medium | Primary writer | Primary readers |
|---|---|---|---|
| Local coordination | `factory/` markdown bus | Local profiles, bridge | Local profiles, founder |
| Remote execution | E2B `/workspace` | Substrate driver, remote coordinator | Remote team |
| Wire protocol | A2A JSON-RPC and push webhook | Bridge, remote coordinator | Bridge, remote coordinator |
| Event log | SQLite | Bridge, critic, substrate tools | `query_remote_teams`, conductor, hr |
| Human observability | Obsidian vault | Mirror process, conductor | Founder |

## 8. Filesystem contract

Each remote team is represented locally by:

```text
factory/teams/<team-name>/
├── brief.md
├── SOUL.md
├── TEAM_SOUL.md
├── AGENTS.md
├── transport.json
├── status.json
├── journal.md
├── inbox/
├── outbox/
├── drafts/<channel>/
├── exemplars/
├── context/
├── source/
├── criteria.md
├── HALT.flag
└── internal/
```

### 8.1 `transport.json`

`transport.json` must contain transport metadata and secret references only.

Example:

```json
{
  "protocol": "a2a",
  "substrate": "e2b",
  "agent_card_url": "https://example.e2b.dev/.well-known/agent-card.json",
  "push_url": "https://boss.example.com/a2a/push",
  "team_bearer_token_ref": "env://HARNESS_TEAM_DEVELOPMENT_BEARER_TOKEN",
  "push_token_ref": "env://HARNESS_TEAM_DEVELOPMENT_PUSH_TOKEN",
  "bridge_secret_ref": "env://HARNESS_BRIDGE_SECRET",
  "substrate_handle_ref": "sqlite://substrate_handles/development"
}
```

Raw bearer tokens, push tokens, provider API keys, and bridge secrets must never be written to `factory/`. They are loaded from a `.env` file outside `factory/`.

### 8.2 Obsidian mirror excludes

The mirror must include:

- `factory/orders/`
- `factory/approved_orders/`
- `factory/assignments/`
- `factory/inbox/`
- `factory/outbox/`
- `factory/drafts/`
- `factory/decisions/`
- `factory/escalations/`
- `factory/blackboard/`
- `factory/status/`
- `factory/teams/*/brief.md`
- `factory/teams/*/TEAM_SOUL.md`
- `factory/teams/*/status.json`
- `factory/teams/*/journal.md`
- `factory/teams/*/criteria.md`
- `factory/teams/*/outbox/`

The mirror must exclude:

- `factory/teams/*/internal/`
- `factory/teams/*/transport.json`
- `factory/teams/*/source/.git/`
- `factory/teams/*/source/node_modules/`
- `factory/teams/*/source/.venv/`
- any path matching `*.secret`, `.env`, `.env.*`, `secrets/`, or `credentials/`

## 9. SQLite database contract

The database has three required responsibilities:

- Store assignment-to-A2A-task mappings.
- Dedupe inbound A2A push events.
- Support compact operational queries.

### 9.1 `team_assignments`

```sql
CREATE TABLE team_assignments (
  assignment_id   TEXT PRIMARY KEY,
  team_name       TEXT NOT NULL,
  order_id        TEXT,
  a2a_task_id     TEXT,
  status          TEXT NOT NULL,
  inbox_path      TEXT NOT NULL,
  in_flight_path  TEXT,
  completed_path  TEXT,
  created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  dispatched_at   TEXT,
  terminal_at     TEXT,
  UNIQUE (team_name, a2a_task_id)
);

CREATE INDEX team_assignments_team_status
  ON team_assignments (team_name, status);
```

The bridge writes the returned A2A task ID here after a successful `message/send`. Cancellation reads from this table, not from `transport.json`.

### 9.2 `team_events`

```sql
CREATE TABLE team_events (
  event_id       INTEGER PRIMARY KEY AUTOINCREMENT,
  team_name      TEXT NOT NULL,
  assignment_id  TEXT,
  task_id        TEXT,
  sequence       BIGINT,
  source         TEXT NOT NULL,
  kind           TEXT NOT NULL,
  state          TEXT,
  ts             TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  cost_cents     INTEGER,
  duration_ms    BIGINT,
  payload_path   TEXT,
  signature      TEXT,
  metadata       TEXT NOT NULL DEFAULT '{}'
);

CREATE UNIQUE INDEX team_events_a2a_dedupe
  ON team_events (team_name, task_id, sequence)
  WHERE task_id IS NOT NULL AND sequence IS NOT NULL;

CREATE INDEX team_events_state_ts
  ON team_events (state, ts DESC);

CREATE INDEX team_events_team_ts
  ON team_events (team_name, ts DESC);

CREATE INDEX team_events_team_kind_ts
  ON team_events (team_name, kind, ts DESC);
```

A2A push events must include `task_id`, `sequence`, and `signature`. Local lifecycle events such as `critic-approved`, `critic-gaps`, `spawned`, and `archived` may omit A2A fields but must include `source`, `kind`, and `metadata`.

### 9.3 `substrate_handles`

```sql
CREATE TABLE substrate_handles (
  team_name       TEXT PRIMARY KEY,
  substrate       TEXT NOT NULL,
  handle          TEXT NOT NULL,
  status          TEXT NOT NULL,
  provisioned_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at      TEXT,
  archived_at     TEXT
);
```

This table stores opaque substrate handles outside mirrored markdown.

### 9.4 Budget posture

No application-level budget, concurrency, or runtime ceilings are enforced in v1. Cost telemetry may be recorded in `team_events.cost_cents` when available, but the system must not kill sandboxes solely because of cost or runtime thresholds.

## 10. A2A bridge specification

### 10.1 Runtime

The bridge is a long-running Python daemon.

It must:

- Send A2A JSON-RPC requests and validate task responses.
- Watch `factory/teams/*/inbox/`.
- Watch `factory/teams/*/HALT.flag`.
- Expose `POST /a2a/push`.
- Write `factory/status/a2a-bridge.json` every 30 seconds.
- Respect `factory/HALT_a2a-bridge.flag`.
- Use SQLite for assignment mapping, dedupe, event logging, and substrate handle lookup.

### 10.2 Outbound dispatch

When `factory/teams/<name>/inbox/<assignment-id>.md` appears:

- Read assignment markdown.
- Load `transport.json`.
- Resolve bearer token from the configured external `.env`.
- Send A2A `message/send`.
- Treat HTTP success with JSON-RPC `error` as failure.
- Persist `assignment_id -> task_id` in `team_assignments`.
- Write `<assignment-id>.dispatched.json` for human traceability.
- Move assignment to `<assignment-id>.in-flight.md`.
- Append a `team_events` row with `kind = 'dispatched'`.

Dispatch must be idempotent. If `team_assignments.assignment_id` already has an A2A task ID, the bridge must not send the assignment again.

### 10.3 Inbound push

The bridge receives:

```text
POST /a2a/push
Authorization: Bearer <team-specific-token>
X-A2A-Notification-Token: <signature>
```

Required validation:

- Verify bearer token by resolving the team's token reference.
- Verify HMAC over `team_name`, `task_id`, `state`, `sequence`, and canonical body hash.
- Reject missing or repeated sequence numbers after recording a dedupe no-op.
- Reject events for unknown tasks unless the event is a valid peer-registration flow.

Bridge state handling:

| A2A state | Bridge effect |
|---|---|
| `working` | Append `journal.md`, update `status.json`, append event |
| `input-required` | Write escalation, update status, append event |
| `auth-required` | Write secret-request escalation, update status, append event |
| `completed` | Write artifacts to `outbox/`, mark assignment completed, append event |
| `failed` | Write failure escalation, mark assignment failed, append decision/event |
| `canceled` | Confirm local HALT or treat as unsolicited failure |

### 10.4 Cancellation

When `factory/teams/<name>/HALT.flag` appears:

- Query active assignments from `team_assignments`.
- Send A2A `tasks/cancel` for each active `a2a_task_id`.
- Mark assignments as `cancel-requested`.
- Call `SubstrateDriver.cancel`.
- Archive sandbox state through `SubstrateDriver.archive`.
- Move local team folder to `archive/teams_<name>_<timestamp>/`.
- Append `team_events` rows for cancellation and archive.

### 10.5 Ingress

The installer assumes public HTTPS for v1. The operator must supply a reachable HTTPS URL and TLS termination before any remote team can spawn.

`BOSS_PUSH_URL` must be configured during install and validated before any remote team can spawn.

## 11. Substrate specification

### 11.1 Interface

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

### 11.2 E2B v1 requirements

The E2B driver must:

- Create sandboxes from a baked template.
- Avoid runtime package installation when possible.
- Use batched E2B file APIs for workspace sync.
- Use E2B native watch APIs for sync-out.
- Reconnect watchers with exponential backoff.
- Skip noisy folders such as `node_modules/`, `.git/`, `dist/`, `build/`, `__pycache__/`, `.venv/`, and `venv/`.
- Health check with `Sandbox.connect(sandbox_id)`.
- Avoid application-level concurrency, budget, and runtime ceilings in v1.
- Route LLM calls through short-lived proxy tokens rather than provider API keys.
- Expose the remote A2A server on port 8000.

### 11.3 Remote boot modes

`single-agent-team` boot:

```text
hermes serve --profile coordinator --skills harness-worker --a2a-port 8000
```

`multi-agent-team` boot:

```text
harness-remote-supervisor start --template multi-agent --a2a-port 8000
```

The remote supervisor must start:

- A2A-facing coordinator server.
- Worker beat.
- Reviewer beat.
- Scribe beat.
- Internal heartbeat writer.
- Internal HALT watcher.

The boss sees only the coordinator A2A endpoint. The remote team owns its internal bus.

## 12. Critic specification

The critic is an LLM Hermes profile that performs durable review of remote outputs.

Inputs:

- New artifacts in `factory/teams/*/outbox/`.
- The team's `criteria.md`.
- The team's `exemplars/`.
- The artifact's assignment metadata.

Behavior:

- Spawn a fresh-context child critic.
- Include no writer conversation history.
- Return `APPROVED` or a numbered list of evidence-backed gaps.
- Move approved artifacts to `factory/drafts/<channel>/`.
- Write revision-request envelopes for rejected artifacts.
- Append critique results to `factory/decisions/` and `team_events`.

The critic model must be configurable and strong enough to avoid systematic false passes.

## 13. Tool and CLI specification

### 13.1 Hermes tools

| Tool | Owner | Responsibility |
|---|---|---|
| `spawn_team.py` | `hr` | Create team folder, provision substrate, boot A2A endpoint |
| `dispatch_team.py` | `hr` | Write assignment envelope into team inbox |
| `sunset_team.py` | `hr` | Write HALT, archive, roster update |
| `query_remote_teams.py` | `boss`, `hr`, `conductor` | Return compact SQLite-backed digest |
| `inspect_team.py` | `hr` | On-demand forensic sync of `internal/` |
| `escalate.py` | all profiles | Write structured escalation |

### 13.2 CLI

The CLI is deferred until the tool surface stabilizes.

Required commands:

```text
harness team spawn <name> --template <single-agent|multi-agent> --substrate e2b
harness team list
harness team status <name>
harness team halt <name>
harness team archive <name>
harness team logs <name> [--follow]
harness team inspect <name>
harness substrate list
harness substrate health
```

The CLI must call the same underlying dispatch surface as Hermes tools.

## 14. Installation specification

`install.sh` must:

- Verify Hermes is installed.
- Verify profile creation works.
- Create local profiles for `boss`, `supervisor`, `hr`, `conductor`, `critic`, and `a2a-bridge`.
- Copy `bus_template/` to the selected project `factory/`.
- Copy remote team templates into `~/.hermes/harness/templates/`.
- Install Python package in editable mode.
- Install the Python bridge console script.
- Initialize SQLite schema.
- Configure `.env` loading from outside `factory/`.
- Configure public HTTPS ingress and write `BOSS_PUSH_URL`.
- Initialize Obsidian vault mirror with excludes.
- Register Hermes cron entries for LLM profiles.
- Start the bridge through launchd or systemd.
- Print first-run instructions for the founder.

The installer must fail closed if any of these are missing:

- SQLite database path.
- External `.env` path.
- Push ingress URL.
- Bridge secret.
- E2B API credentials when E2B is enabled.

## 15. Security requirements

### 15.1 Secrets

- Raw secrets must not be stored in `factory/`.
- Raw secrets must not be mirrored to Obsidian.
- Raw secrets are loaded from a `.env` file outside `factory/`.
- Raw provider API keys must not enter E2B sandboxes.
- Remote sandboxes receive short-lived LLM proxy tokens.
- `transport.json` stores secret references only.

### 15.2 Authentication

- Outbound boss-to-team dispatch uses team-specific bearer tokens.
- Inbound team-to-boss push uses bearer auth and HMAC signatures.
- HMAC validation includes body hash and sequence.
- Duplicate sequence numbers are no-ops.

### 15.3 Authorization

- Spawning teams requires supervisor-approved orders.
- Secret requests become `auth-required` escalations.
- Recursive delegation depth defaults to 3.

### 15.4 Audit

- Every dispatch, push event, critique, cancellation, and archive writes a `team_events` row.
- Every decision writes a hash-chained markdown entry.
- Every artifact path in SQLite points to a local markdown or file artifact.

## 16. Reliability requirements

- Bridge restart must not resend already-dispatched assignments.
- Push event retries must not duplicate artifacts.
- Watcher reconnects must be automatic.
- Stale team status over 5 minutes must surface in `query_remote_teams`.
- Bridge heartbeat stale over 5 minutes must trigger conductor escalation.
- E2B sandboxes approaching 24 hours must checkpoint or archive based on team class.

## 17. Observability requirements

### 17.1 Markdown observability

The founder must be able to inspect:

- Active teams.
- Current team status.
- Recent team journal entries.
- Assignment chains.
- Artifact locations.
- Critic decisions.
- Escalations.
- Hash-chained decisions.

### 17.2 Programmatic observability

`query_remote_teams` must answer:

- Teams stale over N minutes.
- Failed teams over a cost threshold when cost telemetry is available.
- Per-team cost over a time window when cost telemetry is available.
- Teams with repeated critic rejection.
- Long-running teams approaching substrate expiration.
- Active assignments per team.

### 17.3 Optional tracing

LLM tracing through Langfuse, Phoenix, or Helicone is optional and not required for v1.

## 18. MVP acceptance criteria

The MVP is complete when:

- A fresh Hermes install can install Hermes Harness.
- The local boss team can run all five LLM profiles on cron.
- The bridge runs as a daemon and heartbeats to `factory/status/a2a-bridge.json`.
- `hr.spawn_team` can create one `single-agent-team` on E2B.
- The spawned team exposes a valid A2A AgentCard.
- The bridge can dispatch an assignment once and only once.
- The remote team can push `working` and `completed`.
- Completed artifacts land in `factory/teams/<name>/outbox/`.
- The critic can approve or reject the artifact.
- `query_remote_teams` returns compact summaries from SQLite.
- The Obsidian mirror excludes `internal/` and secret-bearing files.
- A HALT flag cancels the active A2A task and archives the sandbox.

## 19. Implementation plan

### Phase 0: Product decisions and repo scaffold

Estimated effort: 5 implementer iterations.

Deliverables:

- Repo skeleton.
- `README.md`.
- `install.sh` stub.
- Python package structure.
- Python bridge package structure.
- Initial SQLite schema.
- `.env` loader for secrets outside `factory/`.
- Public HTTPS ingress configuration contract.
- Hermes A2A server seam discovery.

Acceptance criteria:

- `pip install -e .` works for Python package.
- `harness-a2a-bridge --help` works after editable install.
- Schema files include assignments, events, and substrate handles.
- Installer refuses to continue without configured external `.env` path and public HTTPS push URL.
- Implementation records whether `hermes serve --a2a-port` exists or a wrapper server must be built.

### Phase 1: Local boss team package

Estimated effort: 8 implementer iterations.

Deliverables:

- Generic `boss`, `supervisor`, `hr`, and `conductor` profile bundles.
- `critic` profile bundle.
- `a2a-bridge` daemon profile bundle.
- `bus_template/` with `HARD_RULES.md`, `PROTOCOL.md`, `STANDING_APPROVALS.md`, and `QUIET_HOURS.md`.
- Envelope signing hook.
- `escalate.py`.
- Cron registration.

Acceptance criteria:

- Fresh install creates all local profiles.
- Boss writes orders.
- Supervisor signs approved envelopes.
- Decisions hash chain accumulates.
- Conductor sees bridge heartbeat.
- No remote team is required yet.

### Phase 2: Bridge MVP with local stub team

Estimated effort: 10 implementer iterations.

Deliverables:

- Filesystem watcher for `factory/teams/*/inbox/`.
- Filesystem watcher for `factory/teams/*/HALT.flag`.
- Outbound A2A `message/send`.
- Assignment/task mapping.
- Express push receiver.
- HMAC verification.
- Event dedupe.
- SQLite event writer.
- Heartbeat writer.
- Local stub A2A team for development.

Acceptance criteria:

- One local stub team receives an assignment.
- Bridge restart does not resend dispatched assignment.
- Stub push `working` updates `journal.md` and `status.json`.
- Stub push `completed` writes artifact to `outbox/`.
- Duplicate push sequence is ignored.
- HALT sends `tasks/cancel`.

### Phase 3: E2B substrate driver

Estimated effort: 12 implementer iterations.

Deliverables:

- `SubstrateDriver` protocol.
- E2B driver.
- E2B template definition.
- Batched file sync.
- Watcher reconnect.
- Health checks.
- Slot semaphore.
- LLM proxy token injection.
- Substrate handle storage.

Acceptance criteria:

- E2B sandbox provisions from baked template.
- Workspace sync-in works.
- A2A server boots on port 8000.
- `sandbox.getHost(8000)` or equivalent returns an AgentCard URL.
- Health check detects live and dead sandboxes.
- No provider API keys are visible inside sandbox workspace.

### Phase 4: Remote team templates

Estimated effort: 8 implementer iterations.

Deliverables:

- `single-agent-team/` template.
- `multi-agent-team/` template.
- Remote `harness-worker` skill.
- Remote `harness-coordinator` skill.
- `harness-remote-supervisor` boot process.
- Internal heartbeat and HALT handling for multi-agent teams.

Acceptance criteria:

- `single-agent-team` completes a simple assignment end to end.
- `multi-agent-team` starts coordinator, worker, reviewer, and scribe.
- Boss sees both templates as one A2A peer.
- `internal/` remains opaque to boss and excluded from Obsidian mirror.

### Phase 5: Critic and observability

Estimated effort: 6 implementer iterations.

Deliverables:

- Critic artifact watcher.
- Fresh-context critique runner.
- Approval and revision-request flows.
- `query_remote_teams.py`.
- Obsidian mirror with include/exclude rules.
- `factory/dashboard.md`.
- `factory/team_roster.md`.

Acceptance criteria:

- Approved artifact moves to `factory/drafts/<channel>/`.
- Rejected artifact creates revision envelope in team inbox.
- Critique result writes to decisions and SQLite.
- `query_remote_teams` answers stale, failed, cost-telemetry, and rejection queries from SQLite.
- Obsidian mirror excludes `internal/` and `transport.json`.

### Phase 6: CLI

Estimated effort: 5 implementer iterations.

Deliverables:

- `harness team spawn`.
- `harness team list`.
- `harness team status`.
- `harness team halt`.
- `harness team archive`.
- `harness team logs`.
- `harness team inspect`.
- `harness substrate list`.
- `harness substrate health`.

Acceptance criteria:

- CLI commands produce the same bus and database effects as Hermes tools.
- CLI can spawn and halt a `single-agent-team`.
- CLI status matches `query_remote_teams`.

### Phase 7: Long-running mission handling

Estimated effort: 6 implementer iterations.

Deliverables:

- 23-hour checkpoint trigger for E2B.
- Checkpoint file contract.
- Drain in-flight assignments.
- Respawn with checkpoint.
- Transport update handling.
- Archive continuity.

Acceptance criteria:

- A long-running team checkpoints before E2B expiration.
- Fresh sandbox starts with checkpoint.
- `journal.md` and `status.json` remain continuous from boss view.
- Active assignment state is preserved or escalated explicitly.

## 20. Suggested implementation order

1. Build SQLite schema and `.env` secret handling first.
2. Build bridge against a local stub A2A team.
3. Add E2B provisioning only after bridge idempotency works locally.
4. Add critic gating before using remote teams for externally visible artifacts.
5. Add CLI after Hermes tool behavior stabilizes.
6. Add long-mission respawn after short missions are reliable.

## 21. Open questions

These are the main inputs still needed before implementation starts:

- What public HTTPS domain/path should receive `POST /a2a/push`?
- Where should the external `.env` live by default?
- Is `hermes serve --a2a-port` already implemented, or does Hermes core need an A2A server seam added first?
- What Obsidian vault path should the installer use by default?
- What E2B account tier and sandbox lifetime should v1 target?

## 22. Risk register

| Risk | Severity | Mitigation |
|---|---:|---|
| Push URL unavailable from E2B | High | Installer requires public HTTPS configuration before spawn |
| Secret leakage through mirrored markdown | High | Secret references only, mirror excludes, installer checks |
| Duplicate dispatch after bridge restart | High | `team_assignments` idempotency |
| Duplicate artifacts from push retries | High | `(team_name, task_id, sequence)` dedupe |
| Budget runaway | High | Accepted v1 risk. No application-level limit by product decision; use provider/account-level controls manually. |
| Multi-agent remote team only boots coordinator | Medium | `harness-remote-supervisor` required for multi-agent template |
| E2B 24-hour expiration loses work | Medium | Checkpoint and respawn phase |
| Watcher stream dies silently | Medium | Reconnect with backoff |
| A2A protocol changes | Medium | Keep bridge adapter isolated |
| Weak critic false-passes artifacts | Medium | Configurable strong critic model and exemplar-based criteria |

## 23. Definition of done for v1

v1 is founder-usable when the system can:

- Install into a stock Hermes setup.
- Spawn one E2B `single-agent-team`.
- Dispatch one assignment through A2A.
- Receive push progress and completion.
- Persist events and artifacts locally.
- Critique returned work.
- Show safe live state in Obsidian.
- Answer compact SQLite-backed status queries.
- Halt and archive the team.

Multi-agent teams, CLI, and long-running checkpoint-respawn are planned follow-on capabilities unless explicitly promoted into the MVP.

## Final A2A/E2B Architecture Decision

This section supersedes any earlier uncertainty about whether Hermes needs a new A2A seam for remote delegation. For the MVP, A2A is not a separate harness-only protocol layer. It is part of the remote team runtime template.

### Decision

- The boss machine is the only public client-facing service.
- The boss exposes public HTTPS and an A2A server for external clients.
- Each remote team E2B sandbox is created from a template that already contains Hermes plus a Hermes A2A adapter/plugin.
- The boss delegates work to remote teams by calling the remote team's A2A endpoint.
- Remote teams report task progress and final results back to the boss using an HTTPS push callback.
- External clients do not directly discover or call remote E2B teams.

### Runtime topology

```text
External client
  -> HTTPS A2A
Boss harness plugin
  -> E2B spawn + initial payload
Remote team sandbox
  -> exposed E2B HTTPS host for team A2A endpoint
Boss harness plugin
  -> A2A message/send to remote team
Remote team sandbox
  -> HTTPS push callback to boss
Boss harness plugin
  -> A2A task updates/results to external client
```

### Boss responsibilities

- Run the public HTTPS A2A server for external clients.
- Maintain SQLite-backed state for external tasks, remote teams, dispatches, events, and callback records.
- Load secrets and environment-specific configuration from `.env`.
- Spawn E2B sandboxes from the remote team template.
- Send the initial sandbox payload containing team identity, boss callback URL, auth token references, and task bootstrap context.
- Resolve the remote team's public A2A URL using E2B port exposure, for example `sandbox.getHost(a2aPort)`.
- Store the remote team endpoint and any E2B traffic access token needed to call it.
- Delegate work to remote teams using A2A JSON-RPC.
- Receive remote task updates through the boss HTTPS callback endpoint.
- Translate remote team results back into the boss-facing A2A task lifecycle.

### Remote team template responsibilities

The E2B template must include:

- Hermes installed and runnable.
- A Hermes A2A adapter/plugin installed, preferably `tickernelz/hermes-a2a` for the first compatibility spike.
- SQLite available for the remote team's local A2A/task state.
- A startup script that reads the boss-provided initial payload.
- A startup script that launches the Hermes A2A server on a configured port.
- A health endpoint usable by the boss before dispatching work.
- Push callback configuration pointing at the boss public HTTPS endpoint.

The remote team A2A server is intended for boss-to-team delegation, not general public client access.

### E2B networking model

- Boss-to-remote calls use the E2B exposed HTTPS host for the configured A2A port.
- Remote-to-boss calls use normal outbound HTTPS from the sandbox to the boss callback URL.
- If the E2B sandbox disables unrestricted public traffic, the boss must include the E2B traffic access token header when calling the remote team endpoint.
- The boss should treat the E2B host and traffic access token as runtime state, not static config.

### Initial payload contract

The boss sends an initial payload when creating the sandbox. Minimum fields:

```json
{
  "team_id": "team-...",
  "boss_base_url": "https://boss.example.com",
  "boss_callback_url": "https://boss.example.com/a2a/push",
  "callback_auth_token_ref": "env://BOSS_CALLBACK_TOKEN",
  "a2a_port": 3000,
  "task_context": {}
}
```

After sandbox startup and port exposure, the boss records:

```json
{
  "team_id": "team-...",
  "a2a_url": "https://3000-sandboxid.e2b.app",
  "traffic_access_token_ref": "runtime://e2b/traffic_access_token"
}
```

### A2A adapter strategy

Use an existing Hermes A2A adapter for the remote team template instead of implementing A2A from scratch in the harness.

Initial candidate order:

1. `tickernelz/hermes-a2a` as the preferred MVP candidate because it appears to support profile-safe install, SQLite-backed task state, A2A task methods, push callbacks, and health/agent-card endpoints.
2. `iamagenius00/hermes-a2a` as the upstream/reference implementation to compare behavior and compatibility.
3. `ceo1st/hermes-a2a-gateway` only if the plugin-based candidates cannot be packaged cleanly into the E2B template.

The first implementation spike must verify exact install commands, start commands, endpoint paths, supported A2A protocol version, push callback behavior, and cancellation behavior for the chosen adapter.

### MVP communication flow

1. External client sends an A2A task to the boss.
2. Boss creates or selects a remote team.
3. Boss spawns an E2B sandbox when no suitable team exists.
4. Boss passes the initial payload into the sandbox.
5. Remote team startup launches Hermes plus the A2A adapter on the configured port.
6. Boss resolves the E2B exposed HTTPS host for that port.
7. Boss sends A2A `message/send` to the remote team endpoint.
8. Remote team executes the task using Hermes.
9. Remote team posts task updates/results to the boss callback endpoint.
10. Boss updates SQLite state and responds to the external client through the boss A2A task lifecycle.

### Explicit non-goals for MVP

- No direct external client access to remote E2B teams.
- No custom A2A implementation for Hermes unless existing adapters fail the compatibility spike.
- No Postgres dependency.
- No budget, runtime, or concurrency limits.
- No distributed service discovery beyond boss-managed E2B endpoint registration.
