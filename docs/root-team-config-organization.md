# Root Team Config Organization

The root team separates versioned definitions from live runtime state.

## Versioned

These files define what the boss team is allowed and instructed to do:

- goals: `PRIORITIZE.md`, `GOALS.md`, `AUTOPILOT.md`, `DIRECTIVES.md`
- policies: `STANDING_APPROVALS.md`, `QUIET_HOURS.md`, `HARD_RULES.md`
- protocol: `PROTOCOL.md`
- object definitions: `BRAND_VOICE.md`, `MESSAGE_FRAMEWORK.md`, `CAMPAIGNS_ACTIVE.md`, `POSITIONING.md`, `CONTENT_PILLARS.md`, `CALENDAR.md`
- local profile definitions: `AGENTS.md`, `SOUL.md`, `TEAM_SOUL.md` for the six boss-team profiles
- remote team definitions: `team_blueprints/**`
- root-team skills: `skills/**`
- memory schema/templates: `wiki/SCHEMA.md`, `wiki/.templates`, `wiki/.obsidian`

They live under:

```text
/factory-config/
  current -> versions/<active-version>
  versions/<version>/
    VERSION.yaml
    goals/
    policies/
    protocol/
    objects/
    profiles/
    team_blueprints/
    skills/
    memory_schema/
```

Compatibility paths under `/factory` and `/opt/hermes-home/profiles` point into the active version with symlinks.

## Live State

These are not versioned:

- `orders/`, `approved_orders/`, `assignments/`, `inbox/`, `outbox/`
- `teams/`, `status/`, `drafts/`, `approvals/`, `escalations/`, `archive/`
- `harness.sqlite3*`, `activity.log`
- Hermes profile `state.db*`, `sessions/`, `logs/`, `cron/output/`
- auth files, `.env`, bearer tokens, webhook secrets

Live state stays in stable directories so rollback does not erase audit history or running work.

## Chat-Driven Config Changes

When the user asks boss to change root-team behavior:

1. Create a new config version:

   ```bash
   /opt/hermes-harness/scripts/factory_config_versions.sh new <short-label>
   ```

2. Edit the normal compatibility paths, for example `/factory/PRIORITIZE.md` or `/factory/team_blueprints/creators/TEAM_SOUL.md`.

3. Report the active version from:

   ```bash
   /opt/hermes-harness/scripts/factory_config_versions.sh status
   ```

4. Roll back only after explicit user request:

   ```bash
   /opt/hermes-harness/scripts/factory_config_versions.sh switch <version> --restart
   ```

Old versions are not edited. A new user-requested config change creates a new version first.
