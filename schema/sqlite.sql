CREATE TABLE IF NOT EXISTS team_assignments (
  assignment_id   TEXT PRIMARY KEY,
  team_name       TEXT NOT NULL,
  order_id        TEXT,
  a2a_task_id     TEXT,
  status          TEXT NOT NULL,
  inbox_path      TEXT NOT NULL,
  in_flight_path  TEXT,
  completed_path  TEXT,
  status_reason   TEXT,
  blocked_by      TEXT,
  retry_count     INTEGER NOT NULL DEFAULT 0,
  max_retries     INTEGER NOT NULL DEFAULT 3,
  next_retry_at   TEXT,
  lease_owner     TEXT,
  lease_expires_at TEXT,
  last_heartbeat_at TEXT,
  last_error      TEXT,
  created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  dispatched_at   TEXT,
  terminal_at     TEXT,
  UNIQUE (team_name, a2a_task_id)
);

CREATE INDEX IF NOT EXISTS team_assignments_team_status
  ON team_assignments (team_name, status);

CREATE INDEX IF NOT EXISTS team_assignments_next_retry
  ON team_assignments (status, next_retry_at);

CREATE INDEX IF NOT EXISTS team_assignments_lease
  ON team_assignments (lease_expires_at);

CREATE TABLE IF NOT EXISTS execution_tickets (
  ticket_id            TEXT PRIMARY KEY,
  goal_id              TEXT,
  parent_ticket_id     TEXT,
  title                TEXT NOT NULL,
  mode                 TEXT NOT NULL,
  team_name            TEXT NOT NULL,
  status               TEXT NOT NULL,
  priority             INTEGER NOT NULL DEFAULT 100,
  order_id             TEXT,
  assignment_id        TEXT,
  approval_request_id  TEXT,
  body                 TEXT NOT NULL DEFAULT '',
  write_scope_json     TEXT NOT NULL DEFAULT '[]',
  acceptance_json      TEXT NOT NULL DEFAULT '[]',
  verification_json    TEXT NOT NULL DEFAULT '[]',
  blockers_json        TEXT NOT NULL DEFAULT '[]',
  metadata             TEXT NOT NULL DEFAULT '{}',
  created_at           TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at           TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  dispatched_at        TEXT,
  terminal_at          TEXT
);

CREATE INDEX IF NOT EXISTS execution_tickets_status_priority
  ON execution_tickets (status, priority, created_at);

CREATE INDEX IF NOT EXISTS execution_tickets_team_status
  ON execution_tickets (team_name, status, priority);

CREATE INDEX IF NOT EXISTS execution_tickets_assignment
  ON execution_tickets (assignment_id);

CREATE TABLE IF NOT EXISTS orchestrator_leases (
  resource_type     TEXT NOT NULL,
  resource_id       TEXT NOT NULL,
  holder            TEXT NOT NULL,
  leased_until      TEXT NOT NULL,
  heartbeat_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  attempt           INTEGER NOT NULL DEFAULT 0,
  last_error        TEXT,
  PRIMARY KEY (resource_type, resource_id)
);

CREATE INDEX IF NOT EXISTS orchestrator_leases_until
  ON orchestrator_leases (leased_until);

CREATE TABLE IF NOT EXISTS team_events (
  event_id       INTEGER PRIMARY KEY AUTOINCREMENT,
  team_name      TEXT NOT NULL,
  assignment_id  TEXT,
  task_id        TEXT,
  sequence       BIGINT,
  source         TEXT NOT NULL,
  kind           TEXT NOT NULL,
  state          TEXT,
  ts             TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  cost_cents     INTEGER,
  duration_ms    BIGINT,
  payload_path   TEXT,
  signature      TEXT,
  metadata       TEXT NOT NULL DEFAULT '{}'
);

CREATE UNIQUE INDEX IF NOT EXISTS team_events_a2a_dedupe
  ON team_events (team_name, task_id, sequence)
  WHERE task_id IS NOT NULL AND sequence IS NOT NULL;

CREATE INDEX IF NOT EXISTS team_events_state_ts
  ON team_events (state, ts DESC);

CREATE INDEX IF NOT EXISTS team_events_team_ts
  ON team_events (team_name, ts DESC);

CREATE INDEX IF NOT EXISTS team_events_team_kind_ts
  ON team_events (team_name, kind, ts DESC);

CREATE TABLE IF NOT EXISTS substrate_handles (
  team_name       TEXT PRIMARY KEY,
  substrate       TEXT NOT NULL,
  handle          TEXT NOT NULL,
  status          TEXT NOT NULL,
  provisioned_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at      TEXT,
  archived_at     TEXT
);

CREATE TABLE IF NOT EXISTS assignment_sandboxes (
  assignment_id   TEXT PRIMARY KEY,
  team_name       TEXT NOT NULL,
  substrate       TEXT NOT NULL,
  handle          TEXT NOT NULL,
  agent_card_url  TEXT,
  status          TEXT NOT NULL,
  created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  booted_at       TEXT,
  terminal_at     TEXT,
  archived_at     TEXT,
  last_heartbeat_at TEXT,
  idle_since      TEXT,
  blocked_since   TEXT,
  expires_at      TEXT,
  archive_path    TEXT,
  restore_source  TEXT,
  last_error      TEXT,
  metadata        TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS assignment_sandboxes_team_status
  ON assignment_sandboxes (team_name, status);

CREATE TABLE IF NOT EXISTS assignment_resumes (
  resume_id                  TEXT PRIMARY KEY,
  request_id                 TEXT NOT NULL UNIQUE,
  parent_assignment_id       TEXT NOT NULL,
  continuation_assignment_id TEXT,
  team_name                  TEXT NOT NULL,
  status                     TEXT NOT NULL,
  response_json              TEXT NOT NULL DEFAULT 'null',
  strategy                   TEXT NOT NULL,
  created_at                 TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  sent_at                    TEXT,
  completed_at               TEXT,
  metadata                   TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS assignment_resumes_parent
  ON assignment_resumes (parent_assignment_id);

CREATE INDEX IF NOT EXISTS assignment_resumes_status
  ON assignment_resumes (status, created_at DESC);

CREATE TABLE IF NOT EXISTS approval_requests (
  request_id            TEXT PRIMARY KEY,
  assignment_id         TEXT NOT NULL,
  team_name             TEXT NOT NULL,
  task_id               TEXT,
  kind                  TEXT NOT NULL,
  status                TEXT NOT NULL,
  title                 TEXT NOT NULL,
  prompt                TEXT NOT NULL,
  required_fields_json  TEXT NOT NULL DEFAULT '[]',
  response_json         TEXT,
  escalation_path       TEXT,
  created_at            TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  resolved_at           TEXT,
  resumed_at            TEXT,
  metadata              TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS approval_requests_status_created
  ON approval_requests (status, created_at DESC);

CREATE INDEX IF NOT EXISTS approval_requests_team_status
  ON approval_requests (team_name, status, created_at DESC);

CREATE INDEX IF NOT EXISTS approval_requests_assignment
  ON approval_requests (assignment_id);

CREATE TABLE IF NOT EXISTS operator_alerts (
  alert_id         TEXT PRIMARY KEY,
  dedupe_key       TEXT NOT NULL UNIQUE,
  severity         TEXT NOT NULL,
  kind             TEXT NOT NULL,
  team_name        TEXT,
  assignment_id    TEXT,
  request_id       TEXT,
  status           TEXT NOT NULL,
  title            TEXT NOT NULL,
  body             TEXT NOT NULL,
  created_at       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  acknowledged_at  TEXT,
  metadata         TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS operator_alerts_status_created
  ON operator_alerts (status, created_at DESC);

CREATE INDEX IF NOT EXISTS operator_alerts_kind
  ON operator_alerts (kind, status);

CREATE TABLE IF NOT EXISTS user_peers (
  peer_id          TEXT PRIMARY KEY,
  agent_card_url   TEXT,
  agent_card_json  TEXT NOT NULL,
  access_token     TEXT,
  created_at       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_seen        TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_contexts (
  context_id       TEXT PRIMARY KEY,
  peer_id          TEXT NOT NULL REFERENCES user_peers(peer_id),
  task_id          TEXT,
  push_url         TEXT,
  push_token       TEXT,
  status           TEXT,
  created_at       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_onboarding (
  context_id        TEXT PRIMARY KEY,
  step              TEXT NOT NULL,
  pending_request   TEXT,
  partial_card_url  TEXT,
  partial_card_json TEXT,
  created_at        TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at        TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
