import { mkdirSync } from 'node:fs';
import { dirname } from 'node:path';
import { DatabaseSync } from 'node:sqlite';

export class BridgeDb {
  constructor(dbPath) {
    mkdirSync(dirname(dbPath), { recursive: true });
    this.db = new DatabaseSync(dbPath);
    this.db.exec('PRAGMA journal_mode = WAL');
    this.db.exec('PRAGMA foreign_keys = ON');
    this.migrate();
  }

  migrate() {
    this.db.exec(`
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
    `);
  }

  getAssignment(assignmentId) {
    return this.db.prepare('SELECT * FROM team_assignments WHERE assignment_id = ?').get(assignmentId);
  }

  getAssignmentByTask(teamName, taskId) {
    return this.db
      .prepare('SELECT * FROM team_assignments WHERE team_name = ? AND a2a_task_id = ?')
      .get(teamName, taskId);
  }

  ensureAssignment({ assignmentId, teamName, orderId, inboxPath }) {
    this.db
      .prepare(
        `INSERT OR IGNORE INTO team_assignments
          (assignment_id, team_name, order_id, status, inbox_path)
         VALUES (?, ?, ?, 'pending', ?)`
      )
      .run(assignmentId, teamName, orderId ?? null, inboxPath);
    return this.getAssignment(assignmentId);
  }

  markDispatched({ assignmentId, taskId, inFlightPath }) {
    this.db
      .prepare(
        `UPDATE team_assignments
         SET a2a_task_id = ?, status = 'dispatched', in_flight_path = ?, dispatched_at = CURRENT_TIMESTAMP
         WHERE assignment_id = ?`
      )
      .run(taskId, inFlightPath, assignmentId);
  }

  markTerminal({ assignmentId, status, completedPath }) {
    this.db
      .prepare(
        `UPDATE team_assignments
         SET status = ?, completed_path = COALESCE(?, completed_path), terminal_at = CURRENT_TIMESTAMP
         WHERE assignment_id = ?`
      )
      .run(status, completedPath ?? null, assignmentId);
  }

  updateAssignmentStatus({ assignmentId, status }) {
    this.db
      .prepare('UPDATE team_assignments SET status = ? WHERE assignment_id = ?')
      .run(status, assignmentId);
  }

  activeAssignments(teamName) {
    return this.db
      .prepare(
        `SELECT * FROM team_assignments
         WHERE team_name = ?
           AND a2a_task_id IS NOT NULL
           AND status IN ('dispatched', 'working', 'input-required', 'auth-required', 'cancel-requested')`
      )
      .all(teamName);
  }

  markCancelRequested(assignmentId) {
    this.db
      .prepare("UPDATE team_assignments SET status = 'cancel-requested' WHERE assignment_id = ?")
      .run(assignmentId);
  }

  updateAssignmentStatus({ assignmentId, status }) {
    this.db
      .prepare('UPDATE team_assignments SET status = ? WHERE assignment_id = ?')
      .run(status, assignmentId);
  }

  getSubstrateHandle(teamName) {
    return this.db.prepare('SELECT * FROM substrate_handles WHERE team_name = ?').get(teamName);
  }

  appendEvent({
    teamName,
    assignmentId,
    taskId,
    sequence,
    source,
    kind,
    state,
    costCents,
    durationMs,
    payloadPath,
    signature,
    metadata = {},
  }) {
    try {
      this.db
        .prepare(
          `INSERT INTO team_events
            (team_name, assignment_id, task_id, sequence, source, kind, state,
             cost_cents, duration_ms, payload_path, signature, metadata)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
        )
        .run(
          teamName,
          assignmentId ?? null,
          taskId ?? null,
          sequence ?? null,
          source,
          kind,
          state ?? null,
          costCents ?? null,
          durationMs ?? null,
          payloadPath ?? null,
          signature ?? null,
          JSON.stringify(metadata)
        );
      return { inserted: true };
    } catch (error) {
      if (error.code === 'ERR_SQLITE_ERROR' && String(error.message).includes('UNIQUE')) {
        return { inserted: false, duplicate: true };
      }
      throw error;
    }
  }

  close() {
    this.db.close();
  }
}
