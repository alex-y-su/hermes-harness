# Remote Kanban Teams Plan

Status: proposed architecture; mock local dispatcher implemented for Docker VM;
KPI-aware growth/maintenance result contract implemented for the mock;
remote-team CLI protocol implemented for local/docker transports; functional
Docker X sub-team implemented with real Hermes execution and a mocked X API;
main-card lifecycle contract updated for campaign/support cycles.

Related plan: `plans/hermes-first-reset.md`.

## Goal

Make the main Hermes team responsible for creative direction, strategy, and
starting new marketing directions, while execution happens inside durable remote
Hermes teams.

The main team should keep new ideas, priorities, and high-level decisions. A
remote team should own its own Kanban board, profiles, working memory, retries,
artifacts, and execution history. The main team receives only durable status and
final results.

## Core Idea

Extend Hermes Kanban routing so a local main-board task can target a remote
team instead of a local profile.

Example:

```text
main Hermes Kanban
  task: Start SEO landing-page direction
  assignee: team:seo
  stream: growth
  context_version: 2026-05-09.1

seo-team Hermes Kanban
  receives the external task
  creates or resumes its own local board task
  decomposes into research/copy/review/publishing subtasks
  reports final result back to main
```

This keeps execution context out of the main team's context window and avoids
mixing implementation details with strategic review.

## Architecture

### Main Team

Responsibilities:

- maintain strategy, goals, and priority queue
- propose new marketing directions
- decide when a new direction deserves a durable team
- create high-level tasks assigned to `team:<name>`
- send curated context packages to remote teams
- poll remote teams for status
- record final results and promoted learnings

The main team should not implement long-running direction work itself.

### Remote Teams

Each remote team is a long-lived Hermes deployment with:

- its own `HERMES_HOME`
- its own Kanban board
- its own profiles
- its own memory
- its own dispatcher loop
- scoped credentials and tools
- persistent storage

Example teams:

```text
seo-team
x-team
email-team
video-team
partnerships-team
```

Each team tracks both support and growth work. Start with one board per team and
use task metadata such as `tenant=growth` or `tenant=support`. Split into
separate boards later only when volume or operational needs justify it.

Each direction owns two kinds of work:

- growth: new experiments, channels, campaigns, creative bets, activation loops
- maintenance: refreshing existing assets, checking broken funnels, replying to
  leads/comments, monitoring performance, pruning stale work, and keeping
  operating assets current

The main team controls the growth/maintenance budget split. Remote teams own the
day-to-day queues and report only summarized results, blockers, and decisions
back to the main board.

## Kanban Changes

### Current Mock Implementation

The local Docker VM now patches Hermes' real Kanban dispatcher at
`hermes_cli.kanban_db.dispatch_once`.

Behavior:

- `assignee=team:<name>` is treated as a remote-team task.
- The dispatcher claims the task through Hermes Kanban's normal DB flow.
- No local Hermes profile is spawned.
- A mock remote board is written under:

```text
<HERMES_KANBAN_HOME>/mock-remote-kanban/<board>/<team>/board.json
```

- One-shot success marks the main Kanban task `done` with a structured JSON
  result.
- `campaign_cycle`, `support_cycle`, and `direction` success keeps the main
  Kanban task `running`, stores the latest remote status report in
  `task.result`, appends a `remote_status_report` event, and extends the claim
  TTL so the dispatcher does not reclaim the active remote cycle.
- Failure marks the main Kanban task `blocked` and writes the failure payload as
  a comment.

The mock result currently includes:

```json
{
  "mock_remote": true,
  "team": "seo",
  "card_type": "execution",
  "stream": "growth",
  "approval": {
    "required_before_external_action": false,
    "tier": "profile"
  },
  "completed_deliverables": ["Prepared content brief"],
  "requested_kpis": ["qualified organic visits"],
  "reported_kpis": [
    {
      "name": "qualified organic visits",
      "measurement_window": "7 days after launch",
      "mock_baseline": 12,
      "mock_target": 94,
      "status": "ready_to_measure"
    }
  ],
  "measurement_window": "7 days after launch",
  "cycle_window": "",
  "review_cadence": "",
  "continue_rule": "Continue if the primary KPI beats baseline without violating guardrails.",
  "stop_rule": "",
  "next_report_due_at": "",
  "decision_rule": "Continue if the primary KPI beats baseline without violating guardrails.",
  "main_card_update": {
    "action": "complete",
    "status": "done",
    "card_type": "execution",
    "remote_status": "reported",
    "business_phase": "completed",
    "kpi_state": "reported"
  },
  "evidence": ["mock remote seo board entry"],
  "blockers": [],
  "next_recommendation": "Review the KPI contract, then approve execution or promote the best deliverable to launch.",
  "test_telemetry": {
    "confidence": 0.81,
    "readiness_score": 77,
    "risk_score": 42,
    "simulated_effort": 30,
    "simulated_impact": 225
  }
}
```

`test_telemetry` is only a local playground signal. It must not be treated as a
real marketing KPI.

## Approval Model

Approval should stay inside the Kanban workflow first. Do not introduce a
separate approval service until the task/result contract proves stable.

Approval tiers:

- automatic: research, drafts, plans, mock execution, internal analysis, and
  maintenance checks with no external side effects
- profile: low-risk non-public assets, draft landing pages, proposed outreach
  copy, and experiment specs below a cost/time threshold
- human: posting publicly, sending emails or DMs, paid ads, partner outreach,
  spending money, using credentials, using customer data, or changing production
  systems

Approval gates external-world action, not thinking. A remote team can still
produce a draft, plan, or execution packet before approval. Launch/send/publish
must be blocked until the approval tier allows it.

## Delegation Contract

Use the existing Hermes Kanban interface. Richer structure goes into the task
body and result payload.

Required task body headings:

```text
Card type:
Stream:
Goal:
Hypothesis:
Target audience:
Approval required:
Approval reason:
Expected deliverables:
Requested KPIs:
Measurement window:
Cycle window:
Review cadence:
Continue rule:
Stop rule:
Next report due:
Decision rule:
Definition of done:
Reporting format:
```

Supported `Card type` values:

- `execution`: finite task; complete the main card when DoD is satisfied
- `campaign_cycle`: active growth campaign; keep the main card running while
  reporting KPIs until the cycle window, stop rule, or continue rule resolves
- `support_cycle`: active maintenance/support cycle; keep running while
  reporting support health and blockers on cadence
- `direction`: long-lived direction container; avoid using this for work that
  can be expressed as bounded campaign/support cycles
- `kpi_review`: finite KPI collection/reporting task
- `approval`: finite approval task

Required remote result fields:

```text
card_type
completed_deliverables
requested_kpis
reported_kpis
approval
measurement_window
cycle_window
review_cadence
continue_rule
stop_rule
next_report_due_at
decision_rule
main_card_update
evidence
blockers
next_recommendation
```

The main team should reject or rework results that do not answer the requested
KPIs, do not preserve approval posture, or do not include a clear decision rule.

`main_card_update` is the sync instruction for the main board:

```json
{
  "action": "keep_running",
  "status": "running",
  "card_type": "campaign_cycle",
  "remote_status": "reported",
  "business_phase": "campaign_active",
  "kpi_state": "collecting",
  "cycle_window": "2026-05-10..2026-05-24",
  "review_cadence": "Daily KPI update, full review every 7 days.",
  "next_report_due_at": "2026-05-11T09:00:00Z",
  "continue_rule": "Continue if >=5 qualified replies.",
  "stop_rule": "Stop if 10 posts produce 0 qualified replies."
}
```

Main-board sync rules:

- `action=complete`: set the main card to `done`
- `action=keep_running`: keep the main card `running`, store the latest result,
  and wait for the next report or cycle decision
- `action=block`: set the main card to `blocked` with the blocker reason

The mock is installed by:

```bash
scripts/hermes/install-mock-kanban.sh
```

and is included in the Docker image build.

### Remote Team Registry

Add a small remote-team registry to the main Hermes configuration. The registry
describes where a team lives, but the Kanban dispatcher should not know how to
talk to Docker, SSH, or HTTP directly. The dispatcher should call the stable
remote-team CLI adapter, and the adapter should hide transport-specific details.

Example:

```yaml
kanban:
  remote_teams:
    seo:
      transport: docker
      container: hermes-team-seo
      hermes_home: /vm/hermes-home
      board: seo
    x:
      transport: docker
      container: hermes-team-x
      hermes_home: /vm/hermes-home
      board: x
    cloud_video:
      transport: ssh
      host: video-agent
      hermes_home: /opt/hermes
      board: video
```

Supported transports should start small:

- `local`: separate local `HERMES_HOME`, used for tests
- `docker`: `docker exec -i <container> ...`
- `ssh`: `ssh <host> ...`

E2B should not own durable boards at first. It can later be used behind a
specific remote team for short-lived compute or media generation tasks.

### Remote Assignees

The main dispatcher should recognize assignees in this form:

```text
team:seo
team:x
team:email
```

When it sees a remote-team assignee, it should not spawn a local worker profile.
It should submit the task contract to the configured remote team.

### Main Task Metadata

Main-board tasks delegated to a remote team should store:

```json
{
  "remote_team": "seo",
  "remote_board": "seo",
  "remote_task_id": "seo:task:456",
  "external_id": "main:task:123",
  "remote_status": "running",
  "context_version": "2026-05-09.1",
  "last_sync_at": "2026-05-09T12:00:00Z"
}
```

If Hermes Kanban statuses are fixed, store remote lifecycle state in metadata
and comments instead of changing the status model.

## Communication Protocol

Decision: hide transport details behind a CLI protocol.

The Kanban dispatcher should not run raw `docker exec`, raw `ssh`, or HTTP
requests itself. It should call one stable local command:

```bash
hermes-harness remote-team call --team seo --operation submit_or_get --json
```

The request body is written to stdin. The response is read from stdout. The CLI
adapter then decides how to reach the target team based on the registry:

- `transport=local`: run the receive command with another `HERMES_HOME`
- `transport=docker`: run `docker exec -i <container> ...`
- `transport=ssh`: run `ssh <host> ...`
- future `transport=http`: POST to a remote endpoint

This creates three clean boundaries:

```text
Hermes main profile
  -> creates normal Kanban task assigned to team:seo

Kanban dispatcher
  -> calls hermes-harness remote-team call --team seo --operation submit_or_get

remote-team CLI adapter
  -> resolves transport and invokes hermes-harness remote-team receive --json
```

The remote team implements one stable receive command regardless of how it is
reached:

```bash
hermes-harness remote-team receive --json
```

Inside a Docker transport this expands to:

```bash
docker exec -i hermes-team-seo \
  env HERMES_HOME=/vm/hermes-home \
  hermes-harness remote-team receive --json
```

Inside an SSH transport this expands to:

```bash
ssh video-agent \
  'env HERMES_HOME=/opt/hermes hermes-harness remote-team receive --json'
```

Kanban only depends on the local CLI command and JSON schema. It does not depend
on Docker, SSH, or HTTP implementation details.

### CLI Commands

Main-side adapter command:

```bash
hermes-harness remote-team call --team <name> --operation <operation> --json
```

Responsibilities:

- load the remote-team registry
- validate the target team exists
- build the protocol request from stdin and CLI flags
- execute the configured transport
- enforce timeout/retry policy
- return normalized JSON to the Kanban dispatcher
- avoid leaking secrets into task comments or stdout

Remote-side receive command:

```bash
hermes-harness remote-team receive --json
```

Responsibilities:

- read one JSON request from stdin
- validate `protocol_version`, `operation`, `external_id`, and task contract
- create or resume the remote task idempotently
- use the remote team's own Hermes Kanban board
- return normalized JSON status/result to stdout

Team lifecycle commands, used later by a main-team provisioning profile:

```bash
hermes-harness remote-team init --team x --board x
hermes-harness remote-team health --json
hermes-harness remote-team export-context --json
```

These commands let a future Hermes profile create/configure teams without
knowing the internals of Docker Compose, SSH hosts, or HTTP services.

### Current CLI Implementation

Implemented package:

```text
hermes_harness/remote_team/
  __init__.py
  cli.py
  protocol.py
  receiver.py
  transports.py
```

Installed command:

```bash
hermes-harness-remote-team
```

Implemented commands:

```bash
hermes-harness-remote-team call --team <name> --operation submit_or_get --registry <path> --json
hermes-harness-remote-team call --team <name> --operation status --registry <path> --json
hermes-harness-remote-team call --team <name> --operation health --registry <path> --json
hermes-harness-remote-team receive --json
hermes-harness-remote-team health --json
```

Implemented transports:

- `local`: calls the receive command with another `HERMES_HOME`
- `docker`: calls the receive command through `docker exec -i`

Not implemented yet:

- `ssh`
- `http`
- team lifecycle commands such as `init` and `export-context`

Current receiver behavior:

- validates the protocol request
- creates or resumes a real Hermes Kanban task in the remote team's
  `HERMES_HOME`
- uses `external_id` as the idempotency key
- stores an `external_id -> remote_task_id` mapping under
  `<HERMES_HOME>/remote-team-protocol/<board>.json`
- by default, completes the remote task with a deterministic structured result
  that preserves stream, approval, requested KPIs, reported KPIs, measurement
  window, and decision rule
- deterministic results include `main_card_update`, so the main side can keep
  active campaign/support cycles `running` instead of treating every remote
  reply as final completion
- when `HERMES_REMOTE_TEAM_EXECUTION_MODE=hermes`, dispatches the task to the
  remote team's real Hermes Kanban worker and waits for `done` or `blocked`
- returns normalized JSON to the main-side adapter

The deterministic mode remains for fast contract tests. The Hermes mode proves
that the same protocol can hand work to a real remote profile with its own
Kanban board, profile home, memory, model config, artifacts, and logs.

### Functional X Sub-Team

Implemented Docker service:

```yaml
x-team:
  container_name: hermes-team-x
  HERMES_HOME: /vm/x-team-home
  HERMES_REMOTE_TEAM_EXECUTION_MODE: hermes
  HERMES_REMOTE_TEAM_PROFILE: xworker
```

Setup command:

```bash
scripts/teams/configure-x-team.sh
```

What setup does:

- starts the `x-team` Docker service
- configures Hermes with `openai-codex` and `gpt-5.5`
- enables holographic memory
- disables Feishu toolsets
- restores the Codex auth backup when present
- creates or updates the `xworker` Hermes profile
- gives `xworker` an X-team `SOUL.md`
- creates the remote `x` Kanban board

The X team's rule is strict: never call real X/Twitter. The only mocked
external-world surface is the local X API:

```bash
PYTHONPATH=/workspace python -m hermes_harness.mock_x_api post --text "<post text>" --json
```

That command records posts as JSONL under the active profile's `HERMES_HOME`:

```text
/vm/x-team-home/profiles/xworker/mock-x/posts.jsonl
```

Initial proof run:

```bash
hermes-harness-remote-team call \
  --team x \
  --operation submit_or_get \
  --registry /tmp/x-team-registry.json \
  --timeout 600 \
  --json < /tmp/x-subteam-request.json
```

Result:

- remote task id: `t_d599cf55`
- remote board: `x`
- assignee: `xworker`
- status: `completed`
- artifact:
  `/vm/x-team-home/kanban/boards/x/workspaces/t_d599cf55/x_strategy_result.json`
- mock X post id: `mock-x-35d511913af5`
- persisted mock API row:
  `/vm/x-team-home/profiles/xworker/mock-x/posts.jsonl`

The initial proof uncovered one environment issue: the worker first attempted
the mock API without `PYTHONPATH`, then successfully ran:

```bash
PYTHONPATH=/workspace python -m hermes_harness.mock_x_api post --text "..." --json
```

The setup script now writes the `PYTHONPATH=/workspace` form directly into the
profile instructions so future X workers can call the mock API without that
initial import failure.

Repeat proof after updating the profile instructions:

- remote task id: `t_bbccb996`
- remote board: `x`
- assignee: `xworker`
- status: `completed`
- mock X post id: `mock-x-2789c0525ad5`
- persisted mock API row:
  `/vm/x-team-home/profiles/xworker/mock-x/posts.jsonl`
- worker log contains the direct successful mock API call and no
  `ModuleNotFoundError`

The repeated task result preserved the requested contract:

- completed deliverables: one X posting angle, one post draft, one mock X API
  record
- requested KPIs: `Qualified replies`, `Profile clicks`
- reported KPIs: not measured because public posting was not performed
- approval: draft and local mock posting auto-approved; public X posting still
  requires human approval
- decision rule: continue only if the approved post creates at least two
  qualified replies

Step-by-step pattern for creating another functional sub-team:

1. Add a Docker Compose service with its own `HERMES_HOME` volume.
2. Add a `scripts/teams/configure-<team>.sh` bootstrap script.
3. Configure model provider, model, memory, disabled tools, auth, and profile.
4. Write a team-specific `SOUL.md` that names allowed tools, mocked surfaces,
   approval gates, result fields, and durable artifacts.
5. Create the team's board with `hermes kanban boards create <team> --switch`.
6. Register the team in the main-side remote-team registry.
7. Submit a task through `hermes-harness-remote-team call`.
8. Verify board task status, worker log, artifact files, and mocked external API
   state.

### Operations

Keep the protocol small:

- `submit_or_get`: create a remote task if missing, otherwise return current
  status
- `status`: return status for an existing external task
- `cancel`: ask the remote team to cancel work
- `context_update`: publish a new context package/version
- `health`: verify the remote team is alive and dispatching

The first implementation only needs `submit_or_get`, `status`, and `health`.

### Idempotent Submit

`submit_or_get` is the critical operation.

Behavior:

- if `external_id` is new, create a task on the remote board
- if `external_id` already exists, return the existing remote task
- if the task is running, do not restart it
- if the task is complete, return the completed result
- if the task failed, return failure details

This makes retries safe.

Example request:

```json
{
  "protocol_version": "1",
  "operation": "submit_or_get",
  "source_team": "main",
  "target_team": "seo",
  "external_id": "main:task:123",
  "board": "seo",
  "tenant": "growth",
  "priority": "high",
  "context_version": "2026-05-09.1",
  "goal": "Create 3 landing page experiments for AI chatbot traffic",
  "definition_of_done": [
    "keyword cluster",
    "3 landing page briefs",
    "publishing recommendation"
  ],
  "inputs": {
    "context_repo_ref": "marketing-context@abc123",
    "assets": []
  },
  "report_back_format": "summary, artifacts, metrics, next_actions"
}
```

Example response:

```json
{
  "ok": true,
  "external_id": "main:task:123",
  "remote_task_id": "seo:task:456",
  "status": "running",
  "result": null,
  "updated_at": "2026-05-09T12:00:00Z"
}
```

Completed response:

```json
{
  "ok": true,
  "external_id": "main:task:123",
  "remote_task_id": "seo:task:456",
  "status": "completed",
  "result": {
    "summary": "Produced 3 landing page experiments.",
    "artifacts": [
      "seo/artifacts/landing-page-experiments.md"
    ],
    "metrics": {
      "expected_primary_kpi": "organic demo starts"
    },
    "next_actions": [
      "Review claims",
      "Approve one page for publication"
    ],
    "recommended_context_updates": [
      "Add competitor X positioning note to SEO direction context"
    ]
  },
  "updated_at": "2026-05-09T14:30:00Z"
}
```

## Context Sharing

Do not share raw main-team sessions or memory with remote teams.

Share curated context packages.

### Context Layers

Global context:

```text
company overview
product description
audience
brand voice
allowed claims
forbidden claims
competitors
publishing rules
metrics
```

Direction context:

```text
direction goal
channel strategy
current assets
known constraints
target metrics
support responsibilities
growth hypotheses
```

Task context:

```text
specific goal
why now
stream: growth/support
priority
context version
inputs
expected outputs
definition of done
report-back format
```

### Context Storage

Use a versioned context directory or repository.

Example:

```text
marketing-context/
  global/
    company.md
    product.md
    audience.md
    brand.md
    claims-policy.md
  directions/
    seo.md
    x-twitter.md
    email.md
  assets/
    approved-screenshots/
    logos/
    case-studies/
  reports/
```

Every delegated task records the context version it used.

Main owns canonical context. Remote teams can recommend context updates, but
main decides whether to promote them.

## Result Sync

Use pull-based sync first.

Main periodically asks each remote team about delegated tasks that are not yet
complete. This is more durable than relying only on callbacks.

Sync loop:

1. Main finds tasks assigned to `team:<name>` with incomplete remote state.
2. Main calls `submit_or_get` or `status`.
3. Remote team returns current status.
4. Main updates task metadata/comment.
5. If completed, main records the final result and promoted learnings.

Callbacks can be added later, but polling should remain as recovery.

## Spawning New Teams

When main decides to start a new marketing direction, it should create a
long-lived team, not a per-task worker.

Team creation should:

1. create a Docker/cloud deployment
2. create persistent storage
3. install or verify Hermes
4. configure OpenAI Codex, model, memory, and disabled toolsets
5. create team profiles
6. create the team board
7. seed team context
8. start the dispatcher or gateway loop
9. register the team in the main remote-team registry
10. run a health check

The team then receives normal delegated tasks through the remote Kanban
protocol.

## Durability Choice

Recommended order:

1. Cloud VM or long-lived cloud Hermes agent over SSH.
2. Docker Compose with named volumes.
3. E2B for short-lived execution behind a team, not for durable board ownership.

Durability requires:

- persistent disks or named volumes
- idempotent task submission
- retry-safe protocol
- remote health checks
- dispatcher supervision
- task/result reconciliation
- logs
- backups
- scoped credentials per team

No implementation should claim perfect reliability without these controls.

## Verification Plan

### Stage A: Local Two-Home Test

Run main and one remote team with separate local `HERMES_HOME` directories.

Verify:

- main creates a task assigned to `team:seo`
- dispatcher routes it remotely
- remote `submit_or_get` creates exactly one remote task
- repeated submit does not duplicate the remote task
- remote completion syncs back to main

### Stage B: Docker Test

Run main and `seo-team` as separate containers with named volumes.

Verify:

- containers survive restart
- remote board state survives restart
- main can resync after restart
- health check detects stopped remote team
- failed transport does not lose the main task

### Stage C: Cloud SSH Test

Run one remote team on a cloud Hermes VM.

Verify:

- SSH transport submits a task
- remote dispatcher executes it
- main syncs completion
- logs are available on both sides
- no credentials leak into main task comments

### Stage D: New Direction Test

Ask main to start a new direction.

Verify:

- main creates a team deployment request
- new team is registered
- context is seeded
- health passes
- first task is delegated and completed remotely

## Implementation Notes

- Prefer changes at the Kanban dispatch boundary.
- Keep the remote protocol independent of marketing concepts.
- Marketing direction, stream, and report format should be task metadata.
- Keep transports pluggable but initially simple.
- Keep remote teams autonomous once a task is submitted.
- Keep main-team context curated and versioned.
- Do not make E2B the durable source of truth for Kanban boards.
