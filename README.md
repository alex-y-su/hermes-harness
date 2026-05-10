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
board, and resolved with random success/failure metrics.

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
- `HERMES_MOCK_KANBAN_SEED=<value>` makes random metrics repeatable.

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
