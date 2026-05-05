# 24/7 Agent Runtime TODO

This file tracks remaining work after the first watchdog/orchestrator milestone.

## Shipped

- Durable assignment lifecycle fields in SQLite.
- Atomic orchestrator leases.
- Assignment heartbeats and lease metadata.
- Retryable dispatch failures.
- User-blocked assignments pause only the affected activity.
- Watchdog/orchestrator CLI and systemd service.
- Viewer Kanban columns for `Retrying` and `Stale`.
- Query tooling for retry/stale/user-blocked state.
- Structured `assignment_resumes` records for user-request resolution.
- Idempotent continuation assignment creation for resolved user requests.
- Basic `operator_alerts` table and alert query/ack tools.
- Stale assignment and long user-request alert creation in orchestrator.
- Operator tools for board query, requeue, cancel, stale-team archive, and blocker explanation.
- Viewer alert counts plus assignment resume/sandbox/alert detail.

## Remaining Work

### E2B Lifecycle Policy

- Keep live E2B sandboxes running while assignments are `input-required` or `auth-required`.
- Add idle TTL for blocked E2B sandboxes.
- Archive/snapshot blocked sandboxes before stopping them after TTL.
- Resume live sandbox when still available.
- Restore or recreate sandbox from archive when the user responds after TTL.
- Add orphaned sandbox cleanup for sandboxes no longer tied to active assignments.

### Continuation And Resume

- Replace continuation-assignment resume with true same-task A2A resume when supported.
- Mark original assignments completed or superseded when continuation work finishes.

### Watchdog Recovery

- Add safe policy for stale in-flight A2A tasks after alerting.
- Add retry backoff instead of fixed retry delay.
- Add max stale duration before cancel/archive.
- Add recovery for service restart during sandbox boot.
- Add recovery for assignments stuck in `resuming`.

### Alerts

- Alert when bridge or orchestrator enters restart loop.
- Alert when disk space is low.
- Alert when no team events arrive for too long.
- Send alerts through boss chat first; add external channels later.

### Operational Controls

- Add read-only board API endpoint for all lifecycle columns.
- Add richer operator action history for manual interventions.

### Soak And Failure Tests

- Run 24-hour supervised soak with multiple teams.
- Force one user blocker while other teams continue.
- Force one dispatch failure and verify retry.
- Restart bridge, boss gateway, viewer, and orchestrator during active work.
- Let one E2B sandbox idle past TTL and verify archive/cleanup.
- Verify no duplicate terminal results after duplicate push events.
- Verify no global halt when one assignment is blocked.

## Deferred: Budget And Concurrency Controls

Skipped for now by decision.

- Max active E2B sandboxes.
- Max assignments per team.
- Max retries per assignment by team or priority.
- Max spend per hour/day.
- Max idle E2B time by priority.
- Per-team priority and queue weighting.
- Cost reporting in viewer and boss summaries.
