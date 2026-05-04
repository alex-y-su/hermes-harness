from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
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
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


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
) -> None:
    conn.execute(
        """
        INSERT INTO team_assignments (
          assignment_id, team_name, order_id, a2a_task_id, status,
          inbox_path, in_flight_path, completed_path
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(assignment_id) DO UPDATE SET
          team_name = excluded.team_name,
          order_id = COALESCE(excluded.order_id, team_assignments.order_id),
          a2a_task_id = COALESCE(excluded.a2a_task_id, team_assignments.a2a_task_id),
          status = excluded.status,
          inbox_path = excluded.inbox_path,
          in_flight_path = COALESCE(excluded.in_flight_path, team_assignments.in_flight_path),
          completed_path = COALESCE(excluded.completed_path, team_assignments.completed_path)
        """,
        (assignment_id, team_name, order_id, a2a_task_id, status, inbox_path, in_flight_path, completed_path),
    )


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
