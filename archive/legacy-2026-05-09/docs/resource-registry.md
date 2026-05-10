# Resource Registry

Hermes Harness tracks operational resources as files under `factory/resources/`.

Resources include external accounts, websites, repositories, databases, production app configuration, social channels, paid ad accounts, credentialed APIs, and any user-visible or cost-bearing surface.

The registry is file-backed so project state can be reviewed, versioned, and edited without database migrations. Ticket and approval rows should reference resource IDs in metadata rather than duplicating resource state.

## Resource File Format

Resources may be JSON files or Markdown files with frontmatter.

```json
{
  "id": "website/main",
  "title": "Main website",
  "kind": "website",
  "state": "ready",
  "owner": "dev",
  "approval_policy": "production mutations require explicit approval",
  "execution": {
    "mode": "hub_skill",
    "skill": "resource-action-website-edit",
    "network": "main_machine"
  },
  "usage_policy": {
    "actions": {
      "change_page_title": {
        "max_per_30d": 1,
        "observation_window_days": 21,
        "requires_approval": true
      }
    }
  },
  "access": "repo and deployment credentials required",
  "url": "https://example.com"
}
```

Allowed states:

- `ready`
- `missing`
- `needs-access`
- `needs-setup`
- `blocked`
- `deprecated`

## Ticket Metadata

Tickets that touch resources should include IDs in metadata:

```json
{
  "resources": ["website/main", "social/x"],
  "approval": {
    "requested_action": "publish prepared landing page copy",
    "target_resource": "website/main",
    "why": "test a higher-conversion onboarding page",
    "artifact": "factory/teams/dev/outbox/landing-copy.md",
    "blast_radius": "public website content",
    "rollback": "restore previous page copy"
  }
}
```

If a required resource is missing or not ready, create a setup/access ticket first. Do not ask the user to approve an action that cannot be executed.

## Usage Policy and External Actions

Ready resources are still limited. A social account, website, paid channel,
database, production config, or compute provider may be ready but temporarily
depleted, cooling down, outside quiet hours, or waiting for an observation
window.

Every externally visible, account-sensitive, paid, production, credentialed, or
provider-limited action must pass the deterministic resource gate before
approval or execution:

```bash
python3 -m harness.tools.resource_gate check \
  --factory /factory \
  --resource social/x-main \
  --action post_public \
  --ticket-id tkt-123 \
  --artifact /factory/teams/brand/outbox/post.md \
  --json
```

Remote E2B teams do not execute external-world actions. They prepare artifacts
and create hub-side resource action cards:

```bash
python3 -m harness.tools.resource_gate card create \
  --factory /factory \
  --resource social/x-main \
  --action post_public \
  --ticket-id tkt-123 \
  --team brand \
  --artifact /factory/teams/brand/outbox/post.md \
  --why "test onboarding copy angle" \
  --json
```

If a remote team is running in an isolated workspace and cannot write the hub
factory queue directly, it should write an outbox artifact named
`<ticket-id>.resource-action.json` containing:

```json
{
  "ticket_id": "tkt-123",
  "team": "brand",
  "resource_id": "social/x-main",
  "action": "post_public",
  "artifact": "outbox/tkt-123-post.md",
  "why": "test onboarding copy angle",
  "title": "Post approved X launch copy",
  "metadata": {
    "blast_radius": "public social post",
    "rollback": "delete post if incorrect"
  }
}
```

The hub processor harvests this file into `factory/resource_action_cards/pending/`.

The hub-side resource manager gates cards, requests approval when needed, then
uses the resource's configured skill from `factory/skills/` to perform the
approved action from the main machine or configured proxy. The harness should not
grow one deterministic adapter per social network. Deterministic code owns
policy, reservation, approval state, and usage logging; channel-specific
operation belongs in skills.

Run the hub-side processor with:

```bash
python3 -m harness.tools.resource_actions --factory /factory --db /factory/harness.sqlite3 process --loop
```

or through the consolidated control CLI:

```bash
harness-control resource-actions process
```

Resource execution config:

```json
{
  "execution": {
    "mode": "hub_skill",
    "skill": "resource-action-social-post",
    "network": "residential_proxy:main",
    "operator": "resource-manager"
  }
}
```

The skill decides the operational steps for that resource/action, for example
browser session, native app, API, or manual handoff. It must still call the gate
to reserve before execution and commit/release after execution.

File-backed runtime state:

- `factory/resource_usage/<resource-id>.jsonl`: append-only usage ledger.
- `factory/resource_gate_decisions/<date>/*.json`: deterministic gate decisions.
- `factory/resource_action_cards/{pending,ready,approval-required,blocked,completed,released,failed,needs-human}/`: hub-side action queue.
- `factory/locks/resources/*.lock`: atomic reservation locks.

The processor only executes actions that declare a hub-side skill/command in the
resource file, for example `execution.actions.<action>.hub_skill`. If no
executable skill exists under `factory/skills/<skill>/`, the card moves to
`needs-human` and the related ticket stays blocked instead of being marked done.
