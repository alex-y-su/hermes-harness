from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from harness.models import SubstrateHandle

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schema" / "sqlite.sql"


def default_db_path(factory_path: Path) -> Path:
    return factory_path / "harness.sqlite3"


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path) -> None:
    with connect(db_path) as conn:
        _pre_migrate_existing_db(conn)
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        _migrate_existing_db(conn)


def _pre_migrate_existing_db(conn: sqlite3.Connection) -> None:
    table = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'team_assignments'"
    ).fetchone()
    if table is not None:
        _ensure_assignment_columns(conn)


def _migrate_existing_db(conn: sqlite3.Connection) -> None:
    _ensure_assignment_columns(conn)
    _ensure_assignment_sandbox_columns(conn)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS orchestrator_leases (
          resource_type     TEXT NOT NULL,
          resource_id       TEXT NOT NULL,
          holder            TEXT NOT NULL,
          leased_until      TEXT NOT NULL,
          heartbeat_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          attempt           INTEGER NOT NULL DEFAULT 0,
          last_error        TEXT,
          PRIMARY KEY (resource_type, resource_id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS orchestrator_leases_until
          ON orchestrator_leases (leased_until)
        """
    )


def _ensure_assignment_columns(conn: sqlite3.Connection) -> None:
    assignment_columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(team_assignments)").fetchall()
    }
    columns = {
        "status_reason": "TEXT",
        "blocked_by": "TEXT",
        "retry_count": "INTEGER NOT NULL DEFAULT 0",
        "max_retries": "INTEGER NOT NULL DEFAULT 3",
        "next_retry_at": "TEXT",
        "lease_owner": "TEXT",
        "lease_expires_at": "TEXT",
        "last_heartbeat_at": "TEXT",
        "last_error": "TEXT",
    }
    for name, definition in columns.items():
        if name not in assignment_columns:
            conn.execute(f"ALTER TABLE team_assignments ADD COLUMN {name} {definition}")
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS team_assignments_next_retry
          ON team_assignments (status, next_retry_at)
        """
    )


def _ensure_assignment_sandbox_columns(conn: sqlite3.Connection) -> None:
    table = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'assignment_sandboxes'"
    ).fetchone()
    if table is None:
        return
    sandbox_columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(assignment_sandboxes)").fetchall()
    }
    columns = {
        "last_heartbeat_at": "TEXT",
        "idle_since": "TEXT",
        "blocked_since": "TEXT",
        "expires_at": "TEXT",
        "archive_path": "TEXT",
        "restore_source": "TEXT",
        "last_error": "TEXT",
    }
    for name, definition in columns.items():
        if name not in sandbox_columns:
            conn.execute(f"ALTER TABLE assignment_sandboxes ADD COLUMN {name} {definition}")
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS team_assignments_lease
          ON team_assignments (lease_expires_at)
        """
    )


def utc_timestamp(value: datetime | None = None) -> str:
    return (value or datetime.now(UTC)).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


def utc_after(seconds: int, value: datetime | None = None) -> str:
    return utc_timestamp((value or datetime.now(UTC)) + timedelta(seconds=seconds))


@contextmanager
def session(db_path: Path) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def record_event(
    conn: sqlite3.Connection,
    *,
    team_name: str,
    source: str,
    kind: str,
    assignment_id: str | None = None,
    task_id: str | None = None,
    sequence: int | None = None,
    state: str | None = None,
    payload_path: str | None = None,
    signature: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> int | None:
    try:
        cursor = conn.execute(
            """
            INSERT INTO team_events (
              team_name, assignment_id, task_id, sequence, source, kind, state,
              payload_path, signature, metadata
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                team_name,
                assignment_id,
                task_id,
                sequence,
                source,
                kind,
                state,
                payload_path,
                signature,
                json.dumps(metadata or {}, sort_keys=True),
            ),
        )
        return int(cursor.lastrowid)
    except sqlite3.IntegrityError:
        return None


def upsert_assignment(
    conn: sqlite3.Connection,
    *,
    assignment_id: str,
    team_name: str,
    status: str,
    inbox_path: str,
    order_id: str | None = None,
    a2a_task_id: str | None = None,
    in_flight_path: str | None = None,
    completed_path: str | None = None,
    status_reason: str | None = None,
    blocked_by: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO team_assignments (
          assignment_id, team_name, order_id, a2a_task_id, status,
          inbox_path, in_flight_path, completed_path, status_reason, blocked_by
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(assignment_id) DO UPDATE SET
          team_name = excluded.team_name,
          order_id = COALESCE(excluded.order_id, team_assignments.order_id),
          a2a_task_id = COALESCE(excluded.a2a_task_id, team_assignments.a2a_task_id),
          status = excluded.status,
          inbox_path = excluded.inbox_path,
          in_flight_path = COALESCE(excluded.in_flight_path, team_assignments.in_flight_path),
          completed_path = COALESCE(excluded.completed_path, team_assignments.completed_path),
          status_reason = COALESCE(excluded.status_reason, team_assignments.status_reason),
          blocked_by = COALESCE(excluded.blocked_by, team_assignments.blocked_by)
        """,
        (
            assignment_id,
            team_name,
            order_id,
            a2a_task_id,
            status,
            inbox_path,
            in_flight_path,
            completed_path,
            status_reason,
            blocked_by,
        ),
    )


def acquire_lease(
    conn: sqlite3.Connection,
    *,
    resource_type: str,
    resource_id: str,
    holder: str,
    ttl_seconds: int,
    now: datetime | None = None,
) -> bool:
    now_text = utc_timestamp(now)
    leased_until = utc_after(ttl_seconds, now)
    cursor = conn.execute(
        """
        INSERT INTO orchestrator_leases (
          resource_type, resource_id, holder, leased_until, heartbeat_at, attempt
        )
        VALUES (?, ?, ?, ?, ?, 1)
        ON CONFLICT(resource_type, resource_id) DO UPDATE SET
          holder = excluded.holder,
          leased_until = excluded.leased_until,
          heartbeat_at = excluded.heartbeat_at,
          attempt = orchestrator_leases.attempt + 1,
          last_error = NULL
        WHERE orchestrator_leases.leased_until <= ?
           OR orchestrator_leases.holder = excluded.holder
        """,
        (resource_type, resource_id, holder, leased_until, now_text, now_text),
    )
    return cursor.rowcount > 0


def heartbeat_lease(
    conn: sqlite3.Connection,
    *,
    resource_type: str,
    resource_id: str,
    holder: str,
    ttl_seconds: int,
    now: datetime | None = None,
) -> bool:
    cursor = conn.execute(
        """
        UPDATE orchestrator_leases
        SET leased_until = ?, heartbeat_at = ?
        WHERE resource_type = ? AND resource_id = ? AND holder = ?
        """,
        (utc_after(ttl_seconds, now), utc_timestamp(now), resource_type, resource_id, holder),
    )
    return cursor.rowcount > 0


def release_lease(
    conn: sqlite3.Connection,
    *,
    resource_type: str,
    resource_id: str,
    holder: str | None = None,
) -> None:
    if holder:
        conn.execute(
            "DELETE FROM orchestrator_leases WHERE resource_type = ? AND resource_id = ? AND holder = ?",
            (resource_type, resource_id, holder),
        )
        return
    conn.execute(
        "DELETE FROM orchestrator_leases WHERE resource_type = ? AND resource_id = ?",
        (resource_type, resource_id),
    )


def mark_assignment_heartbeat(
    conn: sqlite3.Connection,
    *,
    assignment_id: str,
    status: str | None = None,
    lease_owner: str | None = None,
    lease_ttl_seconds: int | None = None,
    now: datetime | None = None,
) -> None:
    heartbeat = utc_timestamp(now)
    lease_expires_at = utc_after(lease_ttl_seconds, now) if lease_ttl_seconds is not None else None
    conn.execute(
        """
        UPDATE team_assignments
        SET status = COALESCE(?, status),
            last_heartbeat_at = ?,
            lease_owner = COALESCE(?, lease_owner),
            lease_expires_at = COALESCE(?, lease_expires_at)
        WHERE assignment_id = ?
        """,
        (status, heartbeat, lease_owner, lease_expires_at, assignment_id),
    )


def mark_assignment_retrying(
    conn: sqlite3.Connection,
    *,
    assignment_id: str,
    error: str,
    delay_seconds: int,
    max_retries: int = 3,
    now: datetime | None = None,
) -> sqlite3.Row | None:
    row = conn.execute("SELECT retry_count, max_retries FROM team_assignments WHERE assignment_id = ?", (assignment_id,)).fetchone()
    if row is None:
        return None
    retry_count = int(row["retry_count"] or 0) + 1
    effective_max = int(row["max_retries"] or max_retries or 3)
    status = "retrying" if retry_count <= effective_max else "failed"
    conn.execute(
        """
        UPDATE team_assignments
        SET status = ?,
            status_reason = ?,
            retry_count = ?,
            max_retries = ?,
            next_retry_at = CASE WHEN ? = 'retrying' THEN ? ELSE NULL END,
            last_error = ?,
            lease_owner = NULL,
            lease_expires_at = NULL,
            terminal_at = CASE WHEN ? = 'failed' THEN COALESCE(terminal_at, CURRENT_TIMESTAMP) ELSE terminal_at END
        WHERE assignment_id = ?
        """,
        (
            status,
            "dispatch failed; waiting to retry" if status == "retrying" else "retry budget exhausted",
            retry_count,
            effective_max,
            status,
            utc_after(delay_seconds, now),
            error,
            status,
            assignment_id,
        ),
    )
    return conn.execute("SELECT * FROM team_assignments WHERE assignment_id = ?", (assignment_id,)).fetchone()


def mark_assignment_retry_due(
    conn: sqlite3.Connection,
    *,
    assignment_id: str,
) -> None:
    conn.execute(
        """
        UPDATE team_assignments
        SET status = 'queued',
            status_reason = 'retry due',
            next_retry_at = NULL,
            terminal_at = NULL
        WHERE assignment_id = ?
          AND status = 'retrying'
          AND (next_retry_at IS NULL OR next_retry_at <= CURRENT_TIMESTAMP)
        """,
        (assignment_id,),
    )


def mark_assignment_blocked(
    conn: sqlite3.Connection,
    *,
    assignment_id: str,
    status: str,
    blocked_by: str,
    reason: str,
) -> None:
    conn.execute(
        """
        UPDATE team_assignments
        SET status = ?,
            blocked_by = ?,
            status_reason = ?,
            last_heartbeat_at = CURRENT_TIMESTAMP,
            lease_owner = NULL,
            lease_expires_at = NULL
        WHERE assignment_id = ?
        """,
        (status, blocked_by, reason, assignment_id),
    )


def mark_assignment_stale(
    conn: sqlite3.Connection,
    *,
    assignment_id: str,
    reason: str,
) -> None:
    conn.execute(
        """
        UPDATE team_assignments
        SET status = 'stale',
            status_reason = ?,
            lease_owner = NULL,
            lease_expires_at = NULL
        WHERE assignment_id = ?
          AND status NOT IN ('completed', 'failed', 'canceled', 'archived', 'input-required', 'auth-required')
        """,
        (reason, assignment_id),
    )


def clear_assignment_blocker(conn: sqlite3.Connection, *, assignment_id: str, status: str = "resuming") -> None:
    conn.execute(
        """
        UPDATE team_assignments
        SET status = ?,
            blocked_by = NULL,
            status_reason = 'user response supplied',
            last_heartbeat_at = CURRENT_TIMESTAMP
        WHERE assignment_id = ?
        """,
        (status, assignment_id),
    )


def upsert_assignment_resume(
    conn: sqlite3.Connection,
    *,
    resume_id: str,
    request_id: str,
    parent_assignment_id: str,
    team_name: str,
    status: str,
    response: Any,
    strategy: str,
    continuation_assignment_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> sqlite3.Row:
    conn.execute(
        """
        INSERT INTO assignment_resumes (
          resume_id, request_id, parent_assignment_id, continuation_assignment_id,
          team_name, status, response_json, strategy, sent_at, metadata
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, CASE WHEN ? IN ('sent', 'completed') THEN CURRENT_TIMESTAMP ELSE NULL END, ?)
        ON CONFLICT(request_id) DO UPDATE SET
          continuation_assignment_id = COALESCE(assignment_resumes.continuation_assignment_id, excluded.continuation_assignment_id),
          status = CASE
            WHEN assignment_resumes.status = 'completed' THEN assignment_resumes.status
            ELSE excluded.status
          END,
          response_json = COALESCE(assignment_resumes.response_json, excluded.response_json),
          strategy = excluded.strategy,
          sent_at = COALESCE(assignment_resumes.sent_at, excluded.sent_at),
          metadata = excluded.metadata
        """,
        (
            resume_id,
            request_id,
            parent_assignment_id,
            continuation_assignment_id,
            team_name,
            status,
            json.dumps(response, sort_keys=True),
            strategy,
            status,
            json.dumps(metadata or {}, sort_keys=True),
        ),
    )
    return conn.execute("SELECT * FROM assignment_resumes WHERE request_id = ?", (request_id,)).fetchone()


def get_assignment_resume_by_request(conn: sqlite3.Connection, request_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM assignment_resumes WHERE request_id = ?", (request_id,)).fetchone()


def list_assignment_resumes(
    conn: sqlite3.Connection,
    *,
    request_id: str | None = None,
    assignment_id: str | None = None,
    status: str | None = None,
) -> list[sqlite3.Row]:
    clauses = []
    params: list[Any] = []
    if request_id:
        clauses.append("request_id = ?")
        params.append(request_id)
    if assignment_id:
        clauses.append("(parent_assignment_id = ? OR continuation_assignment_id = ?)")
        params.extend([assignment_id, assignment_id])
    if status and status != "all":
        clauses.append("status = ?")
        params.append(status)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return list(
        conn.execute(
            f"""
            SELECT *
            FROM assignment_resumes
            {where}
            ORDER BY created_at DESC, resume_id DESC
            """,
            params,
        )
    )


def upsert_operator_alert(
    conn: sqlite3.Connection,
    *,
    alert_id: str,
    dedupe_key: str,
    severity: str,
    kind: str,
    title: str,
    body: str,
    team_name: str | None = None,
    assignment_id: str | None = None,
    request_id: str | None = None,
    status: str = "open",
    metadata: dict[str, Any] | None = None,
) -> sqlite3.Row:
    conn.execute(
        """
        INSERT INTO operator_alerts (
          alert_id, dedupe_key, severity, kind, team_name, assignment_id,
          request_id, status, title, body, metadata
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(dedupe_key) DO UPDATE SET
          severity = excluded.severity,
          status = CASE
            WHEN operator_alerts.status = 'acknowledged' THEN operator_alerts.status
            ELSE excluded.status
          END,
          title = excluded.title,
          body = excluded.body,
          metadata = excluded.metadata
        """,
        (
            alert_id,
            dedupe_key,
            severity,
            kind,
            team_name,
            assignment_id,
            request_id,
            status,
            title,
            body,
            json.dumps(metadata or {}, sort_keys=True),
        ),
    )
    return conn.execute("SELECT * FROM operator_alerts WHERE dedupe_key = ?", (dedupe_key,)).fetchone()


def list_operator_alerts(
    conn: sqlite3.Connection,
    *,
    status: str | None = "open",
    severity: str | None = None,
    kind: str | None = None,
) -> list[sqlite3.Row]:
    clauses = []
    params: list[Any] = []
    if status and status != "all":
        clauses.append("status = ?")
        params.append(status)
    if severity:
        clauses.append("severity = ?")
        params.append(severity)
    if kind:
        clauses.append("kind = ?")
        params.append(kind)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return list(
        conn.execute(
            f"""
            SELECT *
            FROM operator_alerts
            {where}
            ORDER BY created_at DESC, alert_id DESC
            """,
            params,
        )
    )


def acknowledge_operator_alert(conn: sqlite3.Connection, alert_id: str) -> sqlite3.Row | None:
    conn.execute(
        """
        UPDATE operator_alerts
        SET status = 'acknowledged',
            acknowledged_at = COALESCE(acknowledged_at, CURRENT_TIMESTAMP)
        WHERE alert_id = ?
        """,
        (alert_id,),
    )
    return conn.execute("SELECT * FROM operator_alerts WHERE alert_id = ?", (alert_id,)).fetchone()


def cleanup_expired_leases(conn: sqlite3.Connection, *, before: datetime | None = None) -> int:
    cursor = conn.execute("DELETE FROM orchestrator_leases WHERE leased_until <= ?", (utc_timestamp(before),))
    return int(cursor.rowcount)


def save_substrate_handle(
    conn: sqlite3.Connection,
    handle: SubstrateHandle,
    *,
    status: str = "provisioned",
    expires_at: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO substrate_handles (team_name, substrate, handle, status, expires_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(team_name) DO UPDATE SET
          substrate = excluded.substrate,
          handle = excluded.handle,
          status = excluded.status,
          expires_at = excluded.expires_at,
          archived_at = NULL
        """,
        (handle.team_name, handle.substrate, json.dumps(asdict(handle), sort_keys=True), status, expires_at),
    )


def load_substrate_handle(conn: sqlite3.Connection, team_name: str) -> SubstrateHandle | None:
    row = conn.execute("SELECT handle FROM substrate_handles WHERE team_name = ?", (team_name,)).fetchone()
    if not row:
        return None
    data = json.loads(row["handle"])
    return SubstrateHandle(
        team_name=data["team_name"],
        substrate=data["substrate"],
        handle=data["handle"],
        metadata=data.get("metadata") or {},
    )


def mark_handle_archived(conn: sqlite3.Connection, team_name: str) -> None:
    conn.execute(
        "UPDATE substrate_handles SET status = 'archived', archived_at = CURRENT_TIMESTAMP WHERE team_name = ?",
        (team_name,),
    )


def save_assignment_sandbox(
    conn: sqlite3.Connection,
    *,
    assignment_id: str,
    team_name: str,
    handle: SubstrateHandle,
    agent_card_url: str | None,
    status: str = "booted",
    metadata: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO assignment_sandboxes (
          assignment_id, team_name, substrate, handle, agent_card_url, status,
          booted_at, metadata
        )
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
        ON CONFLICT(assignment_id) DO UPDATE SET
          team_name = excluded.team_name,
          substrate = excluded.substrate,
          handle = excluded.handle,
          agent_card_url = excluded.agent_card_url,
          status = excluded.status,
          booted_at = COALESCE(assignment_sandboxes.booted_at, excluded.booted_at),
          metadata = excluded.metadata
        """,
        (
            assignment_id,
            team_name,
            handle.substrate,
            json.dumps(asdict(handle), sort_keys=True),
            agent_card_url,
            status,
            json.dumps(metadata or {}, sort_keys=True),
        ),
    )


def load_assignment_sandbox(conn: sqlite3.Connection, assignment_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM assignment_sandboxes WHERE assignment_id = ?", (assignment_id,)).fetchone()


def mark_assignment_sandbox_terminal(conn: sqlite3.Connection, assignment_id: str, status: str) -> None:
    conn.execute(
        """
        UPDATE assignment_sandboxes
        SET status = ?, terminal_at = COALESCE(terminal_at, CURRENT_TIMESTAMP)
        WHERE assignment_id = ?
        """,
        (status, assignment_id),
    )


def mark_assignment_sandbox_archived(
    conn: sqlite3.Connection,
    assignment_id: str,
    archive_path: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE assignment_sandboxes
        SET status = 'archived',
            archived_at = CURRENT_TIMESTAMP,
            archive_path = COALESCE(?, archive_path)
        WHERE assignment_id = ?
        """,
        (archive_path, assignment_id),
    )


def mark_assignment_sandbox_blocked(
    conn: sqlite3.Connection,
    *,
    assignment_id: str,
    ttl_seconds: int,
    now: datetime | None = None,
) -> sqlite3.Row | None:
    conn.execute(
        """
        UPDATE assignment_sandboxes
        SET status = CASE WHEN status = 'booted' THEN 'blocked' ELSE status END,
            blocked_since = COALESCE(blocked_since, ?),
            expires_at = COALESCE(expires_at, ?),
            idle_since = COALESCE(idle_since, ?),
            last_heartbeat_at = COALESCE(last_heartbeat_at, ?)
        WHERE assignment_id = ?
          AND status NOT IN ('archived', 'paused_archived')
        """,
        (
            utc_timestamp(now),
            utc_after(ttl_seconds, now),
            utc_timestamp(now),
            utc_timestamp(now),
            assignment_id,
        ),
    )
    return load_assignment_sandbox(conn, assignment_id)


def mark_assignment_sandbox_active(conn: sqlite3.Connection, assignment_id: str) -> None:
    conn.execute(
        """
        UPDATE assignment_sandboxes
        SET status = CASE WHEN status IN ('blocked', 'idle') THEN 'booted' ELSE status END,
            last_heartbeat_at = CURRENT_TIMESTAMP,
            idle_since = NULL,
            blocked_since = NULL,
            expires_at = NULL,
            last_error = NULL
        WHERE assignment_id = ?
          AND status NOT IN ('archived', 'paused_archived')
        """,
        (assignment_id,),
    )


def mark_assignment_sandbox_paused_archived(
    conn: sqlite3.Connection,
    *,
    assignment_id: str,
    archive_path: str,
    restore_source: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE assignment_sandboxes
        SET status = 'paused_archived',
            archived_at = COALESCE(archived_at, CURRENT_TIMESTAMP),
            archive_path = ?,
            restore_source = ?
        WHERE assignment_id = ?
        """,
        (archive_path, restore_source or archive_path, assignment_id),
    )


def mark_assignment_sandbox_error(conn: sqlite3.Connection, *, assignment_id: str, error: str) -> None:
    conn.execute(
        """
        UPDATE assignment_sandboxes
        SET last_error = ?
        WHERE assignment_id = ?
        """,
        (error, assignment_id),
    )


def upsert_approval_request(
    conn: sqlite3.Connection,
    *,
    request_id: str,
    assignment_id: str,
    team_name: str,
    task_id: str | None,
    kind: str,
    status: str = "open",
    title: str,
    prompt: str,
    required_fields: list[Any] | dict[str, Any] | None = None,
    response: dict[str, Any] | list[Any] | str | int | float | bool | None = None,
    escalation_path: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO approval_requests (
          request_id, assignment_id, team_name, task_id, kind, status, title,
          prompt, required_fields_json, response_json, escalation_path, metadata
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(request_id) DO UPDATE SET
          assignment_id = excluded.assignment_id,
          team_name = excluded.team_name,
          task_id = COALESCE(excluded.task_id, approval_requests.task_id),
          kind = excluded.kind,
          status = CASE
            WHEN approval_requests.status != 'open' THEN approval_requests.status
            ELSE excluded.status
          END,
          title = excluded.title,
          prompt = excluded.prompt,
          required_fields_json = excluded.required_fields_json,
          response_json = COALESCE(approval_requests.response_json, excluded.response_json),
          escalation_path = COALESCE(excluded.escalation_path, approval_requests.escalation_path),
          metadata = excluded.metadata
        """,
        (
            request_id,
            assignment_id,
            team_name,
            task_id,
            kind,
            status,
            title,
            prompt,
            json.dumps(required_fields or [], sort_keys=True),
            json.dumps(response, sort_keys=True) if response is not None else None,
            escalation_path,
            json.dumps(metadata or {}, sort_keys=True),
        ),
    )


def list_approval_requests(
    conn: sqlite3.Connection,
    *,
    status: str | None = "open",
    team_name: str | None = None,
    assignment_id: str | None = None,
) -> list[sqlite3.Row]:
    clauses = []
    params: list[Any] = []
    if status and status != "all":
        clauses.append("status = ?")
        params.append(status)
    if team_name:
        clauses.append("team_name = ?")
        params.append(team_name)
    if assignment_id:
        clauses.append("assignment_id = ?")
        params.append(assignment_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return list(
        conn.execute(
            f"""
            SELECT *
            FROM approval_requests
            {where}
            ORDER BY created_at DESC, request_id DESC
            """,
            params,
        )
    )


def resolve_approval_request(
    conn: sqlite3.Connection,
    *,
    request_id: str,
    response: dict[str, Any] | list[Any] | str | int | float | bool | None,
    status: str = "supplied",
    metadata: dict[str, Any] | None = None,
) -> sqlite3.Row | None:
    row = conn.execute("SELECT metadata FROM approval_requests WHERE request_id = ?", (request_id,)).fetchone()
    if row is None:
        return None
    existing_metadata = json.loads(row["metadata"] or "{}")
    if metadata:
        existing_metadata.update(metadata)
    conn.execute(
        """
        UPDATE approval_requests
        SET status = ?,
            response_json = ?,
            resolved_at = COALESCE(resolved_at, CURRENT_TIMESTAMP),
            metadata = ?
        WHERE request_id = ?
        """,
        (
            status,
            json.dumps(response, sort_keys=True),
            json.dumps(existing_metadata, sort_keys=True),
            request_id,
        ),
    )
    return conn.execute("SELECT * FROM approval_requests WHERE request_id = ?", (request_id,)).fetchone()


def upsert_user_peer(
    conn: sqlite3.Connection,
    *,
    peer_id: str,
    agent_card_url: str | None,
    agent_card_json: str,
    access_token: str | None = None,
) -> sqlite3.Row:
    conn.execute(
        """
        INSERT INTO user_peers (peer_id, agent_card_url, agent_card_json, access_token)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(peer_id) DO UPDATE SET
          agent_card_url = excluded.agent_card_url,
          agent_card_json = excluded.agent_card_json,
          access_token = excluded.access_token,
          last_seen = CURRENT_TIMESTAMP
        """,
        (peer_id, agent_card_url, agent_card_json, access_token),
    )
    return conn.execute("SELECT * FROM user_peers WHERE peer_id = ?", (peer_id,)).fetchone()


def get_user_peer(conn: sqlite3.Connection, peer_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM user_peers WHERE peer_id = ?", (peer_id,)).fetchone()


def find_user_peer_by_card_url(conn: sqlite3.Connection, agent_card_url: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM user_peers WHERE agent_card_url = ?", (agent_card_url,)).fetchone()


def list_user_peers(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(conn.execute("SELECT * FROM user_peers ORDER BY last_seen DESC, peer_id ASC"))


def upsert_user_context(
    conn: sqlite3.Connection,
    *,
    context_id: str,
    peer_id: str,
    task_id: str | None = None,
    push_url: str | None = None,
    push_token: str | None = None,
    status: str | None = None,
) -> sqlite3.Row:
    conn.execute(
        """
        INSERT INTO user_contexts (context_id, peer_id, task_id, push_url, push_token, status)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(context_id) DO UPDATE SET
          peer_id = excluded.peer_id,
          task_id = COALESCE(excluded.task_id, user_contexts.task_id),
          push_url = COALESCE(excluded.push_url, user_contexts.push_url),
          push_token = COALESCE(excluded.push_token, user_contexts.push_token),
          status = COALESCE(excluded.status, user_contexts.status),
          updated_at = CURRENT_TIMESTAMP
        """,
        (context_id, peer_id, task_id, push_url, push_token, status),
    )
    return conn.execute("SELECT * FROM user_contexts WHERE context_id = ?", (context_id,)).fetchone()


def get_user_context(conn: sqlite3.Connection, context_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM user_contexts WHERE context_id = ?", (context_id,)).fetchone()


def set_onboarding(
    conn: sqlite3.Connection,
    *,
    context_id: str,
    step: str,
    pending_request: str | None = None,
    partial_card_url: str | None = None,
    partial_card_json: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO user_onboarding (
          context_id, step, pending_request, partial_card_url, partial_card_json
        )
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(context_id) DO UPDATE SET
          step = excluded.step,
          pending_request = COALESCE(excluded.pending_request, user_onboarding.pending_request),
          partial_card_url = COALESCE(excluded.partial_card_url, user_onboarding.partial_card_url),
          partial_card_json = COALESCE(excluded.partial_card_json, user_onboarding.partial_card_json),
          updated_at = CURRENT_TIMESTAMP
        """,
        (context_id, step, pending_request, partial_card_url, partial_card_json),
    )


def get_onboarding(conn: sqlite3.Connection, context_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM user_onboarding WHERE context_id = ?", (context_id,)).fetchone()


def delete_onboarding(conn: sqlite3.Connection, context_id: str) -> None:
    conn.execute("DELETE FROM user_onboarding WHERE context_id = ?", (context_id,))


def active_assignments(conn: sqlite3.Connection, team_name: str) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT * FROM team_assignments
            WHERE team_name = ?
              AND status NOT IN ('completed', 'failed', 'canceled', 'archived')
            ORDER BY created_at ASC
            """,
            (team_name,),
        )
    )
