# AGENTS.md

This remote team reports to the local Hermes boss through the A2A bridge. The coordinator may use `internal/` as a private mini-factory for worker, reviewer, and scribe profiles.

Do not write raw bearer tokens, push tokens, provider keys, bridge secrets, or credentials into this workspace.

Do not execute external-world actions from E2B: no public posting, outreach,
paid spend, production mutation, credentialed account use, or provider-limited
actions. Prepare artifacts in `outbox/` and create or request a hub-side
resource-action card that references the resource ID, action, artifact, and why.
Channel-specific execution is handled by hub-side skills, not by E2B.
