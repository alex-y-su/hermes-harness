from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import RLock
from typing import Any

from harness import db


class BridgeDb:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        db.init_db(self.db_path)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.lock = RLock()

    def get_assignment(self, assignment_id: str) -> sqlite3.Row | None:
        with self.lock:
            return self.conn.execute("SELECT * FROM team_assignments WHERE assignment_id = ?", (assignment_id,)).fetchone()

    def get_assignment_by_task(self, team_name: str, task_id: str) -> sqlite3.Row | None:
        with self.lock:
            return self.conn.execute(
                "SELECT * FROM team_assignments WHERE team_name = ? AND a2a_task_id = ?",
                (team_name, task_id),
            ).fetchone()

    def ensure_assignment(
        self,
        *,
        assignment_id: str,
        team_name: str,
        inbox_path: str | Path,
        order_id: str | None = None,
    ) -> sqlite3.Row | None:
        with self.lock:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO team_assignments
                  (assignment_id, team_name, order_id, status, inbox_path)
                VALUES (?, ?, ?, 'pending', ?)
                """,
                (assignment_id, team_name, order_id, str(inbox_path)),
            )
            self.conn.commit()
            return self.get_assignment(assignment_id)

    def mark_dispatched(self, *, assignment_id: str, task_id: str, in_flight_path: str | Path) -> None:
        with self.lock:
            self.conn.execute(
                """
                UPDATE team_assignments
                SET a2a_task_id = ?, status = 'dispatched', in_flight_path = ?, dispatched_at = CURRENT_TIMESTAMP
                WHERE assignment_id = ?
                """,
                (task_id, str(in_flight_path), assignment_id),
            )
            self.conn.commit()

    def mark_terminal(self, *, assignment_id: str, status: str, completed_path: str | Path | None = None) -> None:
        with self.lock:
            self.conn.execute(
                """
                UPDATE team_assignments
                SET status = ?, completed_path = COALESCE(?, completed_path), terminal_at = CURRENT_TIMESTAMP
                WHERE assignment_id = ?
                """,
                (status, str(completed_path) if completed_path else None, assignment_id),
            )
            self.conn.commit()

    def update_assignment_status(self, *, assignment_id: str, status: str) -> None:
        with self.lock:
            self.conn.execute("UPDATE team_assignments SET status = ? WHERE assignment_id = ?", (status, assignment_id))
            self.conn.commit()

    def active_assignments(self, team_name: str) -> list[sqlite3.Row]:
        with self.lock:
            return list(
                self.conn.execute(
                    """
                    SELECT * FROM team_assignments
                    WHERE team_name = ?
                      AND a2a_task_id IS NOT NULL
                      AND status IN ('dispatched', 'working', 'input-required', 'auth-required', 'cancel-requested')
                    """,
                    (team_name,),
                )
            )

    def mark_cancel_requested(self, assignment_id: str) -> None:
        self.update_assignment_status(assignment_id=assignment_id, status="cancel-requested")

    def get_substrate_handle(self, team_name: str) -> sqlite3.Row | None:
        with self.lock:
            return self.conn.execute("SELECT * FROM substrate_handles WHERE team_name = ?", (team_name,)).fetchone()

    def append_event(
        self,
        *,
        team_name: str,
        source: str,
        kind: str,
        assignment_id: str | None = None,
        task_id: str | None = None,
        sequence: int | None = None,
        state: str | None = None,
        cost_cents: int | None = None,
        duration_ms: int | None = None,
        payload_path: str | Path | None = None,
        signature: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, bool]:
        with self.lock:
            try:
                self.conn.execute(
                    """
                    INSERT INTO team_events (
                      team_name, assignment_id, task_id, sequence, source, kind, state,
                      cost_cents, duration_ms, payload_path, signature, metadata
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        team_name,
                        assignment_id,
                        task_id,
                        sequence,
                        source,
                        kind,
                        state,
                        cost_cents,
                        duration_ms,
                        str(payload_path) if payload_path else None,
                        signature,
                        json.dumps(metadata or {}, sort_keys=True),
                    ),
                )
                self.conn.commit()
                return {"inserted": True}
            except sqlite3.IntegrityError as error:
                self.conn.rollback()
                if "UNIQUE" in str(error).upper():
                    return {"inserted": False, "duplicate": True}
                raise

    def close(self) -> None:
        with self.lock:
            self.conn.close()
