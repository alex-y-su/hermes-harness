# Hermes Harness Reset

This repository has been reset for a Hermes-first orchestration rebuild.

The previous implementation is preserved under:

- `archive/legacy-2026-05-09/`

The active plan is:

- `plans/hermes-first-reset.md`
- `plans/remote-kanban-teams.md`

The reset rule is simple: copy code out of `archive/` only when a stage names it
explicitly and verifies it in the local Docker VM.

## Mock Remote Kanban

The Docker VM patches Hermes' real Kanban dispatcher with a mock remote-team
implementation. Tasks assigned to `team:<name>` are not spawned as local Hermes
profiles. They are claimed by the dispatcher, recorded under a mock remote-team
board, and resolved with a structured mock report.

The mock report is intentionally Kanban-compatible: Hermes still creates a
normal task with title/body/assignee/tenant, and the remote team writes the
answer into the normal task result. The stricter contract lives inside the task
body and result payload.

Delegated task bodies should include:

- `Stream`: `growth` or `maintenance`
- `Goal`
- `Hypothesis`
- `Target audience`
- `Approval required`
- `Approval reason`
- `Expected deliverables`
- `Requested KPIs`
- `Measurement window`
- `Decision rule`
- `Definition of done`
- `Reporting format`

Remote-team results include:

- completed deliverables
- requested KPIs
- reported KPIs
- approval posture
- evidence
- blockers
- next recommendation
- measurement window
- decision rule
- mock-only test telemetry

Random values are now reported under `test_telemetry`; they prove the playground
flow works but are not business KPIs.

Example:

```bash
docker compose -f docker-compose.local.yml run --rm \
  -e HERMES_MOCK_KANBAN_SUCCESS_RATE=1 \
  -e HERMES_MOCK_KANBAN_SEED=demo \
  local-vm bash -lc '
    task_id=$(hermes kanban create "Test SEO direction" \
      --assignee team:seo \
      --tenant growth \
      --json | jq -r .id)
    hermes kanban dispatch --json
    hermes kanban show "$task_id" --json
  '
```

Mock remote boards are stored inside the Hermes Kanban home:

```text
/vm/hermes-home/mock-remote-kanban/<board>/<team>/board.json
```

Control knobs:

- `HERMES_MOCK_KANBAN_SUCCESS_RATE=1` forces success.
- `HERMES_MOCK_KANBAN_SUCCESS_RATE=0` forces failure.
- `HERMES_MOCK_KANBAN_SEED=<value>` makes mock test telemetry repeatable.

## Fresh Docker VM Check

To prove the VM can be rebuilt from a clean Docker volume:

```bash
docker compose -f docker-compose.local.yml down -v --remove-orphans
docker compose -f docker-compose.local.yml build --no-cache local-vm
scripts/hermes/configure-openai-codex.sh
scripts/vm/verify-stage.sh 1
```

`scripts/hermes/configure-openai-codex.sh` restores the captured Hermes defaults
and uses `.local/hermes-auth-backup/auth.json` when that ignored local backup is
present. Auth files are not tracked in git.
