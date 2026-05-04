CREATE TABLE IF NOT EXISTS team_assignments (
  assignment_id   TEXT PRIMARY KEY,
  team_name       TEXT NOT NULL,
  order_id        TEXT,
  a2a_task_id     TEXT,
  status          TEXT NOT NULL,
  inbox_path      TEXT NOT NULL,
  in_flight_path  TEXT,
  completed_path  TEXT,
  created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  dispatched_at   TEXT,
  terminal_at     TEXT,
  UNIQUE (team_name, a2a_task_id)
);

CREATE INDEX IF NOT EXISTS team_assignments_team_status
  ON team_assignments (team_name, status);

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
  metadata        TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS assignment_sandboxes_team_status
  ON assignment_sandboxes (team_name, status);
