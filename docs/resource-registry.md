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
