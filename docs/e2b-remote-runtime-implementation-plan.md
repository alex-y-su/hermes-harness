# E2B Remote Runtime Implementation Plan

## Purpose

This plan defines the final E2B implementation direction for Hermes Harness.

Hermes Harness uses the local machine as the durable boss/coordinator. E2B
sandboxes are temporary remote execution substrates. They run a full functional
Hermes team for one delegated assignment, return artifacts and status through
A2A push notifications, then shut down.

The E2B sandbox must not contain the full boss-side Hermes Harness package. It
should contain only a small remote runtime that can receive an assignment, run a
multi-agent Hermes team locally, push results back, and exit.

## Final decisions

### 1. E2B sandboxes are per assignment

The durable local object is:

```text
factory/teams/<team-name>/
```

The temporary execution object is:

```text
assignment sandbox = one E2B sandbox for one assignment
```

Lifecycle:

1. Assignment appears in `factory/teams/<team>/inbox/`.
2. Local bridge/provisioner creates an E2B sandbox.
3. Local provisioner syncs team workspace, assignment, allowed LLM env, and team
   secrets into the sandbox.
4. Sandbox boots the remote supervisor on port `8000`.
5. Bridge sends A2A `message/send`.
6. Remote team pushes `working`, terminal result, and artifacts.
7. Local side performs final sync-out/archive.
8. Sandbox is killed.

Remote teams are expected to finish under E2B's 24-hour cap. Remote cron is
disabled.

### 2. Multi-agent remote runtime from day one

The remote runtime always uses a supervisor/coordinator architecture. A
single-agent team can be represented as a multi-agent template with one worker,
but the core runtime should not have separate single-agent and multi-agent code
paths.

The remote supervisor starts:

- A2A-facing coordinator server.
- Worker execution loop.
- Reviewer loop.
- Scribe/journal loop.
- Internal heartbeat writer.
- Internal HALT watcher.

The local boss sees only one A2A peer: the remote coordinator.

### 3. E2B template contains remote runtime, not boss package

The E2B template must include:

- Hermes runtime or the selected Hermes-compatible agent CLI.
- Minimal `hermes-remote-runtime` package.
- A2A server and push client.
- Internal bus helpers.
- Common tools that agents need often: `git`, `rg`, `jq`, `sqlite3`, `python3`,
  `pip`, `node`, `npm`, `uv`, `gh`, build tools, archive tools.
- Optional heavier template variants later, such as browser/media/android
  templates.

The E2B template must not include:

- Boss-side team spawning tools.
- Main fleet SQLite database.
- Installer.
- Obsidian mirror tooling.
- E2B API credentials.
- General machine secrets unrelated to the remote assignment.

The sandbox should not be able to directly create other E2B teams.

### 4. Nested delegation is boss-mediated only

Remote teams may request more capacity or delegation, but they must not provision
infrastructure themselves.

Allowed flow:

1. Remote team pushes `input-required` or a structured `delegation-request`.
2. Local boss/hr evaluates the request.
3. Local machine spawns any child team or extra sandbox.
4. Child execution remains tracked in local SQLite and local factory state.

This preserves cost control, auditability, and a single source of truth.

### 5. Secrets model

There are two secret channels.

#### LLM runtime env

Only LLM configuration required to run the remote team is copied into the
sandbox. Use an allowlist, not a full environment dump.

Initial allowlist:

```text
OPENAI_*
ANTHROPIC_*
OPENROUTER_*
HERMES_*
LLM_*
MODEL_*
```

The allowlist can be tightened after the exact Hermes runtime requirements are
known.

#### Team-owned secrets

Each team may keep its own secret files under:

```text
factory/teams/<team>/secrets/
```

This path must be excluded from Obsidian mirroring and git. It may be copied
into the sandbox at:

```text
/home/user/workspace/secrets/
```

`transport.json` still stores secret references only.

### 6. Template strategy

Use the Nexus pattern:

- Bake slow, stable dependencies into E2B templates.
- Use one generated setup script per assignment for team identity, assignment,
  env, secrets, and source/context sync.

Do not bake a new E2B template for every team by default.

Default template:

```text
hermes-harness-remote-full
```

Optional future template families:

```text
hermes-harness-remote-browser
hermes-harness-remote-media
hermes-harness-remote-android
hermes-harness-remote-data
```

Team-specific templates are promoted only when there is repeated evidence that
runtime setup is slow or fragile for that team.

## Team-level E2B assembly contract

Each team template should include:

```text
factory/teams/<team>/
└── e2b/
    ├── setup.sh
    ├── template.ts
    ├── template.json
    └── README.md
```

### `setup.sh`

Runtime setup script executed inside the sandbox for every assignment.

Responsibilities:

- Create workspace directories.
- Merge team `AGENTS.md`, `SOUL.md`, and `TEAM_SOUL.md` into the remote runtime.
- Install small team-specific packages only when unavoidable.
- Write assignment metadata.
- Prepare internal mini-factory.
- Verify required tools.
- Never enable cron.

### `template.ts`

Optional team-specific E2B bake script. Main team may modify this when a team
repeatedly needs the same heavy dependencies.

This follows Nexus' TypeScript E2B template style:

```ts
import { Template } from "e2b"

export const template = Template()
  .fromImage("e2bdev/base")
  .runCmd("...")
```

### `template.json`

Stores selected template metadata:

```json
{
  "default_alias": "hermes-harness-remote-full",
  "team_alias": null,
  "active_template": "hermes-harness-remote-full",
  "last_built_at": null,
  "version": 1,
  "notes": []
}
```

Local tools read this file to choose the E2B template alias. SQLite stores the
actual sandbox handle per assignment.

## Repository implementation work

### 1. Add remote runtime package

Create:

```text
harness_remote/
├── __init__.py
├── supervisor.py
├── a2a_server.py
├── push_client.py
├── internal_bus.py
├── hermes_runner.py
├── setup_env.py
└── cli.py
```

Console entrypoint:

```text
harness-remote-supervisor
```

Primary command:

```text
harness-remote-supervisor start --a2a-port 8000
```

### 2. Add E2B templates

Create:

```text
e2b-templates/hermes-harness-remote-full/
├── template.ts
├── build.dev.ts
├── build.prod.ts
├── package.json
├── package-lock.json
└── README.md
```

Base it on Nexus' `e2b-templates/claude-code/claude-code-full` pattern:

- TypeScript `Template()` builder.
- `Template.build(template, { alias })`.
- Runtime secrets passed through env only.
- Headless operation, no interactive prompts.

### 3. Extend team templates

Add `e2b/` assembly files to:

```text
templates/multi-agent-team/
templates/single-agent-team/
```

Even if single-agent remains as a user-facing template, it should execute
through the same remote supervisor runtime.

### 4. Upgrade E2B driver

Update `harness/substrate/e2b.py` to:

- Prefer the new `e2b` SDK.
- Keep a compatibility fallback if needed.
- Create a sandbox per assignment.
- Resolve template alias from `team/e2b/template.json`.
- Fall back to `E2B_TEMPLATE_ID` or `hermes-harness-remote-full`.
- Batch sync files into `/home/user/workspace`.
- Copy only allowlisted LLM env.
- Copy `factory/teams/<team>/secrets/` when present.
- Run `/home/user/workspace/e2b/setup.sh`.
- Boot `harness-remote-supervisor start --a2a-port 8000`.
- Return the temporary AgentCard URL.
- Perform final sync-out of outbox, journal, status, decisions, and internal
  checkpoint files.
- Kill sandbox after terminal state.

### 5. Add per-assignment provisioner tool

Create:

```text
harness/tools/run_assignment_sandbox.py
```

Responsibilities:

1. Read team config.
2. Create E2B sandbox.
3. Sync workspace and assignment.
4. Start remote supervisor.
5. Store sandbox handle in SQLite.
6. Print JSON containing:

```json
{
  "team_name": "development",
  "assignment_id": "asn_...",
  "sandbox_id": "...",
  "agent_card_url": "https://.../.well-known/agent-card.json"
}
```

The Node bridge can call this tool before A2A dispatch.

### 6. Update bridge dispatch lifecycle

Current bridge assumes a standing remote peer. Change dispatch to:

1. Detect inbox assignment.
2. If team substrate is E2B, call `run_assignment_sandbox.py`.
3. Use returned temporary AgentCard URL for `message/send`.
4. Store `assignment_id -> task_id -> sandbox_id` mapping.
5. On terminal push, call final sync/archive/kill helper.

For external A2A teams, keep the existing standing-peer path.

### 7. Add finalization helper

Create:

```text
harness/tools/finalize_assignment_sandbox.py
```

Responsibilities:

- Connect to sandbox by handle.
- Final sync-out.
- Archive useful state locally.
- Kill sandbox.
- Mark substrate handle archived.

The bridge calls this after `completed`, `failed`, or `canceled`.

## Tests

### Unit tests

- E2B template alias resolution from `template.json`.
- LLM env allowlist filtering.
- Team secrets copy plan.
- Setup script path validation.
- SQLite assignment/sandbox handle mapping.
- Remote push HMAC signing.
- A2A server method routing.

### Integration tests without E2B

- Mock E2B driver.
- Spawn assignment sandbox.
- Boot fake remote supervisor.
- Bridge sends assignment once.
- Remote pushes `working` then `completed`.
- Finalizer runs once.
- Sandbox handle marked archived.

### Real E2B smoke test

Once `E2B_API_KEY` and a built `hermes-harness-remote-full` template are
available:

1. Spawn one assignment sandbox.
2. Verify AgentCard URL.
3. Send one A2A assignment.
4. Receive `working`.
5. Receive `completed`.
6. Verify artifact lands in `factory/teams/<team>/outbox/`.
7. Verify sandbox is killed.

## Open questions before coding

1. Which Hermes runtime command should the remote supervisor call for each
   internal role?
2. Which LLM env vars are strictly required by the current Hermes install?
3. Should the first remote runtime use Claude Code, OpenCode, Hermes CLI, or a
   thin wrapper that can choose one per team?
4. Where should team-specific template build results be recorded: only
   `template.json`, or also SQLite?

## Recommended first implementation slice

Implement a mocked E2B path first:

1. `harness_remote` package with minimal A2A server and push client.
2. Team `e2b/` assembly files.
3. `run_assignment_sandbox.py` with mock driver.
4. Bridge callout to the provisioner.
5. End-to-end local test with fake remote runtime.

Then add real E2B template build and real sandbox execution.
