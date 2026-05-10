# Remote Kanban Teams Plan

Status: proposed architecture; mock local dispatcher implemented for Docker VM;
KPI-aware growth/maintenance result contract implemented for the mock.

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

- Success marks the main Kanban task `done` with a structured JSON result.
- Failure marks the main Kanban task `blocked` and writes the failure payload as
  a comment.

The mock result currently includes:

```json
{
  "mock_remote": true,
  "team": "seo",
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
  "decision_rule": "Continue if the primary KPI beats baseline without violating guardrails.",
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
Stream:
Goal:
Hypothesis:
Target audience:
Approval required:
Approval reason:
Expected deliverables:
Requested KPIs:
Measurement window:
Decision rule:
Definition of done:
Reporting format:
```

Required remote result fields:

```text
completed_deliverables
requested_kpis
reported_kpis
approval
measurement_window
decision_rule
evidence
blockers
next_recommendation
```

The main team should reject or rework results that do not answer the requested
KPIs, do not preserve approval posture, or do not include a clear decision rule.

The mock is installed by:

```bash
scripts/hermes/install-mock-kanban.sh
```

and is included in the Docker image build.

### Remote Team Registry

Add a small remote-team registry to the main Hermes configuration.

Example:

```yaml
kanban:
  remote_teams:
    seo:
      transport: ssh
      host: seo-agent
      hermes_home: /opt/hermes
      board: seo
    x:
      transport: docker
      container: hermes-x-team
      board: x
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

Use JSON over stdin/stdout. Start with SSH and Docker transports because they
are easy to debug and do not require a public API.

Main sends:

```bash
ssh seo-agent 'HERMES_HOME=/opt/hermes hermes remote-team receive --json'
```

or locally:

```bash
docker exec -i hermes-seo-team hermes remote-team receive --json
```

The request body is written to stdin. The response is read from stdout.

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
