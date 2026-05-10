# Hermes-First Reset Plan

Status: active reset plan.

Archive snapshot: `archive/legacy-2026-05-09/`.

## Goal

Rebuild Hermes Harness around Hermes as the orchestrator. Python should provide
small, deterministic tools and adapters only. The agent should own planning,
delegation, creative proposals, and operational choices through prompts,
memory, and skill calls.

This is not an incremental migration of the old board/resource/orchestrator
stack. The old implementation is archived and may be copied forward only when a
stage explicitly names the source files and proves the copied behavior in the
local Docker VM.

## Non-Negotiable Architecture

- Hermes profiles are the brain. `AGENTS.md`, `SOUL.md`, memory, and skills
  define behavior.
- The repo provides deterministic substrate tools: skill rendering, external
  asset listing, board persistence, team hire/dispatch, artifact inspection,
  and safety checks.
- No Python cron/orchestrator decides what work should happen next.
- No legacy resource gate, legacy execution board, or legacy pulse prompt is
  authoritative.
- Real-world surfaces are controlled by a Hermes-native external asset allowlist.
- Remote teams never directly act on external-world assets. They prepare
  artifacts; the hub executes approved asset actions.
- Every stage has a local Docker VM verification gate before the next stage
  starts.

## Archive Copy Policy

### Copy Or Port

Copy these only when their stage begins, then simplify them to the new contracts:

| Archive source | New use | Stage |
|---|---|---|
| `archive/legacy-2026-05-09/harness/skills/post-twitter-real/execute.sh` | Example real-world publish skill behind external assets | 4 |
| `archive/legacy-2026-05-09/harness/skills/grant-access/execute.sh` | Credential/access workflow reference | 4 |
| `archive/legacy-2026-05-09/harness/tools/spawn_team.py` | Team hire adapter reference | 6 |
| `archive/legacy-2026-05-09/harness/tools/dispatch_team.py` | Assignment dispatch adapter reference | 6 |
| `archive/legacy-2026-05-09/harness/tools/inspect_team.py` | Team state/artifact inspection reference | 6 |
| `archive/legacy-2026-05-09/harness/tools/sunset_team.py` | Team shutdown adapter reference | 6 |
| `archive/legacy-2026-05-09/harness/tools/query_remote_teams.py` | `list_teams` output reference | 6 |
| `archive/legacy-2026-05-09/harness/substrate/e2b.py` | Real E2B substrate adapter reference | 7 |
| `archive/legacy-2026-05-09/harness_remote/` | Remote runtime reference, not wholesale copy | 7 |
| `archive/legacy-2026-05-09/templates/single-agent-team/` | Minimal remote-team filesystem contract reference | 6 |
| `archive/legacy-2026-05-09/templates/multi-agent-team/` | Optional multi-agent team template reference | 7 |
| `archive/legacy-2026-05-09/e2b-templates/hermes-harness-remote-full/` | E2B image/template reference | 7 |
| `archive/legacy-2026-05-09/scripts/bootstrap_hermes_agent.sh` | Hermes CLI install/probe reference | 1 |
| `archive/legacy-2026-05-09/Dockerfile.hermes` and compose files | Docker build reference only | 1 |

### Rewrite From Scratch

| System | Reason |
|---|---|
| Hermes profile renderer | Old `harness/boss_team.py` mixes config, old factory assumptions, and legacy prompts. |
| Skill catalog | New system needs one small canonical catalog with profile allowlists. |
| External assets | New canonical allowlist replaces legacy resources/resource gate. |
| Board | New board should be small, atomic, Hermes-readable, and not tied to old card machinery. |
| Creative pulse | This belongs in Hermes prompt/memory plus small novelty/cadence tools. |
| Verification scripts | New verification should run stage-scoped Docker checks. |

### Do Not Copy

| Archive source | Reason |
|---|---|
| `harness/tools/orchestrator.py` | Old custom brain. Retired. |
| `harness/tools/execution_board.py` | Old board abstraction. Retired. |
| `harness/tools/resource_gate.py` | Old resource policy engine. Retired unless a future stage explicitly revives a tiny piece. |
| `harness/tools/resource_actions.py` | Old hub action queue. Replaced by external asset actions. |
| `harness/tools/request_resources.py` | Replaced by Hermes setup/escalation cards. |
| `harness/resources.py` | Replaced by external asset manifest. |
| `harness/cards/*` validators | Old card schema. Replaced by minimal board schema. |
| `docs/cards/operator-pulse-prompt.md` | Old single-profile pulse. Replaced by boss `AGENTS.md`. |
| `docs/team/` | Historical team design. |
| `factory/` | Old runtime state. Use only as examples when debugging. |
| `local-analysis/` | Historical analysis only. |
| `tmp_*` | Patch-script debt. |

## New Runtime Model

### Profiles

Local Hermes profiles:

- `boss`: user-facing strategist and orchestrator.
- `hr`: hires, dispatches, inspects, and retires remote teams.
- `supervisor`: reviews risky actions and signing decisions.
- `critic`: on-demand review of plans/artifacts.
- `conductor`: health/safety checks only, not strategy.

There is no local specialist profile sprawl. Specialists are remote teams.

### Skills

Skills are generated from a catalog into profile homes. Each skill has:

- name
- summary
- allowed profiles
- input schema
- executor
- side-effect class: `read`, `write-local`, `external`, `team`

Hermes sees skills, not internal Python modules.

### External Assets

`factory/external-assets.json` is the new canonical Hermes-facing allowlist.

Example:

```json
{
  "assets": [
    {
      "id": "social/x0040h",
      "kind": "x_account",
      "label": "X account @x0040h",
      "surface": "https://x.com/x0040h",
      "state": "ready",
      "owner": "user",
      "actions": {
        "draft_post": {
          "approval": "not_required"
        },
        "publish_post": {
          "skill": "post-twitter-real",
          "approval": "required",
          "max_per_day": 5
        }
      }
    }
  ]
}
```

States:

- `ready`
- `needs_credentials`
- `needs_approval_setup`
- `disabled`

Rules:

- Before any external-world plan, boss calls `list_external_assets`.
- If no matching asset/action exists, boss may create a setup/escalation card
  but must not invent execution.
- Drafting can be allowed without publish rights.
- Publish/send/deploy actions require the action to exist in the manifest.
- The manifest is not a credential store.
- E2B compute is not an external asset unless the goal is provider spend/quota
  control. Team delegation is handled by team tools.

### Teams

Hireable remote team blueprints:

- `research`
- `brand`
- `growth`
- `eng`
- `dev`
- `ops`
- `media`

Delegation rule for boss:

Delegate to HR when any condition holds:

- estimated work is over 50 turns
- wall-clock estimate is over 10 minutes
- requires GPU, large-model inference, ffmpeg, Blender, browser automation, or
  heavy batch compute
- produces more than five generated artifact files
- needs a specialist viewpoint or parallel exploration

Inline work is for decisions, short-form copy, tiny edits, and orchestration.

### Board

The new board is intentionally small:

- `factory/board.json`
- `factory/events/*.jsonl`
- `factory/artifacts/`
- `factory/teams/`
- `factory/status/`

Cards should be understandable by Hermes without a large validator. Required
fields:

- `id`
- `title`
- `status`: `draft`, `queued`, `doing`, `waiting`, `done`, `killed`
- `goal`
- `acceptance`
- `owner`
- `created_at`
- `updated_at`
- `audit`

Writes happen through tools only and use atomic rename.

### Creative Capacity

Boss gets an ideation step in `AGENTS.md`:

- runs only when the queue is idle
- checks current priority, memory taste, last done cards, and last ideation time
- proposes three different approaches
- scores cost-to-test, potential impact, and novelty
- creates one draft card
- records all proposals in `factory/status/last-ideation.json`

Creative taste is user-curated. Hermes may read taste; it must not silently
promote its own guesses into taste memory.

## Local Docker VM

The reset will create a local Docker VM-like container for all verification.

Target files:

- `docker/local-vm/Dockerfile`
- `docker-compose.local.yml`
- `scripts/vm/build.sh`
- `scripts/vm/shell.sh`
- `scripts/vm/verify-stage.sh`
- `scripts/vm/soak.sh`

Container properties:

- mounts the repo at `/workspace`
- uses `/vm/factory` as disposable runtime state
- uses `/vm/hermes-home` as disposable Hermes home
- includes Python, bash, git, jq, sqlite, curl, node only if Hermes install needs it
- includes ffmpeg/ImageMagick by Stage 6 for media-team smoke tests
- never mounts real secrets by default
- starts with mock external assets only
- can run with network disabled for deterministic tests after image build

Verification command shape:

```bash
scripts/vm/build.sh
scripts/vm/verify-stage.sh 1
scripts/vm/verify-stage.sh 2
```

Each stage adds one Docker verification target. A stage is not complete until its
target passes from a clean container with an empty `/vm/factory`.

## Stages

### Stage 0: Reset Baseline

Goal: prove the repo root is clean and old code is archived.

Build:

- Archive current implementation under `archive/legacy-2026-05-09/`.
- Add this plan and minimal root docs.
- Add root `.gitignore`.

Verification:

- `test -d archive/legacy-2026-05-09/harness`
- `test -f plans/hermes-first-reset.md`
- root contains no active `harness/`, `factory/`, `docs/`, `scripts/`, or
  `tests/` directories from the legacy system.

Pass gate:

```bash
find . -maxdepth 1 -mindepth 1 \
  ! -name .git ! -name archive ! -name plans ! -name README.md ! -name .gitignore
```

Expected output: empty.

### Stage 1: New Skeleton and Docker VM

Goal: create a minimal new project that can be tested inside Docker.

Build:

- New `pyproject.toml`.
- New package skeleton, likely `hermes_harness/`.
- New `scripts/verify.sh`.
- New Docker VM files.
- Hermes CLI probe script.

Copy from archive:

- Use `scripts/bootstrap_hermes_agent.sh` only as reference for how Hermes was
  installed/probed.
- Use old Docker files only as reference, not as base files.

Verification:

- Docker image builds.
- `python -m hermes_harness doctor --json` runs inside container.
- Hermes probe records one of:
  - `hermes_available: true` with version and skill-list command confirmed
  - `hermes_available: false` with exact missing binary/install reason
- Unit tests run inside Docker.

Pass gate:

```bash
scripts/vm/verify-stage.sh 1
```

Result on 2026-05-09:

- Docker image `hermes-harness-local-vm:latest` builds.
- Hermes installs from the current upstream installer:
  `https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh`
- Installed Hermes:
  - version: `Hermes Agent v0.13.0 (2026.5.7)`
  - branch: `main`
  - commit: `dae94fa6526dec0c7660276a4d875cebc6e344f6`
  - status: `Up to date`
- Stage 1 verification command passed:
  `scripts/vm/verify-stage.sh 1`
- Fresh-volume proof sequence passed after removing Docker containers and named
  volumes:
  `docker compose -f docker-compose.local.yml down -v --remove-orphans`,
  `docker compose -f docker-compose.local.yml build --no-cache local-vm`,
  `scripts/hermes/configure-openai-codex.sh`, then
  `scripts/vm/verify-stage.sh 1`.
- The base installer path skips optional browser setup
  (`HERMES_INSTALL_BROWSER_TOOLS=0`). The dashboard image path installs Node and
  builds the Hermes web UI.

### Stage 2: Hermes Profile Renderer

Goal: render clean Hermes homes without legacy factory assumptions.

Build:

- `hermes_harness/profiles.py`
- `hermes_harness/render.py`
- `profiles/boss/AGENTS.md.tmpl`
- `profiles/boss/SOUL.md.tmpl`
- templates for `hr`, `supervisor`, `critic`, `conductor`
- CLI: `hermes-harness profiles install --home /vm/hermes-home --factory /vm/factory`

Copy from archive:

- Do not copy `harness/boss_team.py`.
- Reuse only profile names and the observed skill folder layout.

Verification:

- Fresh Docker factory renders all profile homes.
- Generated boss `AGENTS.md` contains external asset rule, delegation rule, and
  one-step pulse rule.
- No generated prompt mentions legacy `resource_gate`, `execution_board`, or
  `operator-pulse-prompt`.
- If Hermes CLI exists, `hermes --profile boss skill list` runs against the
  generated home.

Pass gate:

```bash
scripts/vm/verify-stage.sh 2
```

### Stage 3: Skill Catalog

Goal: Hermes can see and invoke deterministic tools through generated skills.

Build:

- `hermes_harness/skills/catalog.py`
- `hermes_harness/skills/render.py`
- `hermes_harness/tools/list_skills.py`
- generated `SKILL.md` + executable wrapper per skill

Initial skills:

- `list_external_assets`
- `read_board`
- `add_card`
- `update_card`
- `list_teams`
- `hire_team`
- `dispatch_team`
- `inspect_team`

Only stub executors are required in this stage.

Copy from archive:

- None. This is new code.

Verification:

- Profile allowlists are enforced.
- Boss sees board and external asset skills.
- HR sees team skills.
- Supervisor sees read/review skills only.
- Generated `execute.sh` files are executable.
- Stub skill invocation returns JSON with `success`, `skill`, and `profile`.

Pass gate:

```bash
scripts/vm/verify-stage.sh 3
```

### Stage 4: External Assets

Goal: implement the new canonical external asset allowlist.

Build:

- `hermes_harness/external_assets.py`
- CLI/tool executor for `list_external_assets`
- CLI/tool executor for `check_external_action`
- local usage ledger for action limits:
  `factory/external-asset-usage/<asset-id>.jsonl`
- mock external skill for publish/send/deploy tests

Copy from archive:

- Port `harness/skills/post-twitter-real/execute.sh` only after the manifest
  contract is working with a mock publisher.
- Use `grant-access/execute.sh` as reference for credential setup flow, not as
  authority.

Verification:

- Empty manifest returns no assets and external action check blocks.
- Asset exists but `state=disabled` blocks.
- `draft_post` can be allowed without publish rights.
- `publish_post` requires approval when configured.
- `max_per_day` blocks after the limit.
- Manifest never exposes secret values.
- Real publish skill is not called in Docker; mock skill is used.

Pass gate:

```bash
scripts/vm/verify-stage.sh 4
```

### Stage 5: Board and Audit Events

Goal: provide a small durable work board Hermes can mutate safely.

Build:

- `hermes_harness/board.py`
- tools: `read_board`, `read_card`, `add_card`, `update_card`, `kill_card`
- event append log
- atomic file writes

Copy from archive:

- None. Do not copy old card validators or execution board.

Verification:

- Empty factory creates an empty board.
- Add/update/kill card works through tool executors.
- Invalid status rejects.
- Concurrent writes leave valid JSON.
- Every mutation appends an event.

Pass gate:

```bash
scripts/vm/verify-stage.sh 5
```

### Stage 6: Local Team Delegation

Goal: prove boss can delegate hard work to a local fake remote team before real E2B.

Build:

- team registry under `factory/teams/`
- local substrate driver
- tools: `list_teams`, `hire_team`, `dispatch_team`, `inspect_team`,
  `sunset_team`
- `media` blueprint
- local worker shim that writes an outbox artifact for an assignment

Copy from archive:

- Port the concepts from `spawn_team.py`, `dispatch_team.py`,
  `inspect_team.py`, `sunset_team.py`, and `query_remote_teams.py`.
- Use `templates/single-agent-team/` as filesystem contract reference.

Verification:

- `hire_team(blueprint=media)` creates a team.
- `dispatch_team` writes an assignment.
- local worker produces `factory/teams/<team>/outbox/<assignment>.json`.
- `inspect_team` returns status and artifact paths.
- `sunset_team` is idempotent.
- Boss prompt snapshot includes the delegation heuristic.

Pass gate:

```bash
scripts/vm/verify-stage.sh 6
```

### Stage 7: Real E2B Adapter

Goal: add real E2B as a substrate behind the same team tool contract.

Build:

- `hermes_harness/substrates/e2b.py`
- E2B config validation
- remote runtime package only as needed
- E2B template build instructions

Copy from archive:

- Port from `harness/substrate/e2b.py`.
- Port only needed files from `harness_remote/`.
- Port only needed template files from `e2b-templates/hermes-harness-remote-full/`.

Verification:

- Without E2B credentials, Docker reports `substrate_unavailable` cleanly.
- With test credentials explicitly mounted, a smoke assignment runs and returns
  an artifact.
- Local substrate tests remain the default CI gate.
- No E2B API key appears in generated prompts, logs, or board files.

Pass gate:

```bash
scripts/vm/verify-stage.sh 7
```

### Stage 8: Hermes Boss Pulse

Goal: run one real Hermes-driven pulse against the Docker factory.

Build:

- boss pulse prompt in `AGENTS.md`
- minimal cron/install script
- `last-pulse.json`
- safety check that detects stale pulse but does not decide strategy

Copy from archive:

- None from old orchestrator.

Verification:

- Given an empty queue and configured priority, boss creates at most one draft
  card.
- Given a doing card, boss advances only that card one step.
- Given a video-generation goal, boss delegates to HR/media rather than trying
  to do the work inline.
- Given a publish goal with no external asset, boss creates setup/escalation
  instead of publishing.
- If Hermes CLI is unavailable in Docker, this stage cannot pass.

Pass gate:

```bash
scripts/vm/verify-stage.sh 8
```

### Stage 9: Creative Capacity

Goal: make Hermes propose useful new approaches without repeating itself.

Build:

- `factory/MEMORY.md` with `Facts`, `Taste`, and `Vetoed approaches`
- `memory_note` skill
- `check_card_novelty` tool
- ideation cadence file: `factory/status/last-ideation.json`

Copy from archive:

- None.

Verification:

- Idle queue plus stale priority creates exactly one ideation draft.
- Two pulses within cooldown do not create a second ideation card.
- Three proposals are recorded in audit.
- Vetoed approaches are not proposed again in fixture scenarios.
- Taste section can be appended only by user-approved memory tool.

Pass gate:

```bash
scripts/vm/verify-stage.sh 9
```

### Stage 10: End-to-End Local Soak

Goal: prove the new system works as a whole in Docker before any production use.

Scenario:

1. Start fresh Docker VM.
2. Install profiles and skills.
3. Seed:
   - one ready mock X asset with draft allowed and publish approval required
   - one disabled website asset
   - one priority asking for launch content and a teaser video
4. Run boss pulse.
5. Verify boss creates a content card and delegates video to media.
6. Run HR/team tools.
7. Verify media outbox artifact exists.
8. Run boss pulse again.
9. Verify publish action waits for approval and never calls real external skill.
10. Run conductor health check.

Pass gate:

```bash
scripts/vm/soak.sh
```

Required evidence:

- board JSON
- event log
- generated profile prompts
- skill invocation logs
- team outbox artifact
- external asset decision log
- no secret leakage
- no legacy module imports

## Implementation Discipline

- Implement one stage at a time.
- Do not copy a whole archive directory when a single function or contract is
  enough.
- Every copied file must be simplified or wrapped to match the new model.
- Do not restore old docs as active docs.
- Do not revive custom orchestration logic under a new name.
- Every stage updates this plan with actual verification commands and results.
