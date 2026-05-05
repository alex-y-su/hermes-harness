from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
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
                SET a2a_task_id = ?,
                    status = 'dispatched',
                    status_reason = NULL,
                    blocked_by = NULL,
                    next_retry_at = NULL,
                    last_error = NULL,
                    in_flight_path = ?,
                    dispatched_at = CURRENT_TIMESTAMP,
                    last_heartbeat_at = CURRENT_TIMESTAMP
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
                SET status = ?,
                    completed_path = COALESCE(?, completed_path),
                    terminal_at = CURRENT_TIMESTAMP,
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    next_retry_at = NULL
                WHERE assignment_id = ?
                """,
                (status, str(completed_path) if completed_path else None, assignment_id),
            )
            self.conn.commit()

    def update_assignment_status(self, *, assignment_id: str, status: str) -> None:
        with self.lock:
            self.conn.execute("UPDATE team_assignments SET status = ? WHERE assignment_id = ?", (status, assignment_id))
            self.conn.commit()

    def assignment_ready_for_dispatch(self, assignment_id: str) -> bool:
        with self.lock:
            row = self.get_assignment(assignment_id)
            if row is None:
                return True
            if row["a2a_task_id"]:
                return False
            if row["status"] in {"completed", "failed", "canceled", "archived", "input-required", "auth-required"}:
                return False
            if row["status"] == "retrying" and row["next_retry_at"]:
                return str(row["next_retry_at"]) <= datetime.now(UTC).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
            return True

    def mark_assignment_retrying(
        self,
        *,
        assignment_id: str,
        error: str,
        delay_seconds: int,
        max_retries: int = 3,
    ) -> sqlite3.Row | None:
        with self.lock:
            row = db.mark_assignment_retrying(
                self.conn,
                assignment_id=assignment_id,
                error=error,
                delay_seconds=delay_seconds,
                max_retries=max_retries,
            )
            self.conn.commit()
            return row

    def mark_assignment_heartbeat(
        self,
        *,
        assignment_id: str,
        status: str | None = None,
        lease_owner: str | None = None,
        lease_ttl_seconds: int | None = None,
    ) -> None:
        with self.lock:
            db.mark_assignment_heartbeat(
                self.conn,
                assignment_id=assignment_id,
                status=status,
                lease_owner=lease_owner,
                lease_ttl_seconds=lease_ttl_seconds,
            )
            self.conn.commit()

    def mark_assignment_blocked(
        self,
        *,
        assignment_id: str,
        status: str,
        blocked_by: str,
        reason: str,
    ) -> None:
        with self.lock:
            db.mark_assignment_blocked(
                self.conn,
                assignment_id=assignment_id,
                status=status,
                blocked_by=blocked_by,
                reason=reason,
            )
            self.conn.commit()

    def acquire_lease(
        self,
        *,
        resource_type: str,
        resource_id: str,
        holder: str,
        ttl_seconds: int,
    ) -> bool:
        with self.lock:
            acquired = db.acquire_lease(
                self.conn,
                resource_type=resource_type,
                resource_id=resource_id,
                holder=holder,
                ttl_seconds=ttl_seconds,
            )
            self.conn.commit()
            return acquired

    def release_lease(self, *, resource_type: str, resource_id: str, holder: str | None = None) -> None:
        with self.lock:
            db.release_lease(self.conn, resource_type=resource_type, resource_id=resource_id, holder=holder)
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

    def save_assignment_sandbox(
        self,
        *,
        assignment_id: str,
        team_name: str,
        substrate: str,
        handle: str,
        agent_card_url: str | None,
        status: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self.lock:
            self.conn.execute(
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
                    substrate,
                    handle,
                    agent_card_url,
                    status,
                    json.dumps(metadata or {}, sort_keys=True),
                ),
            )
            self.conn.commit()

    def get_assignment_sandbox(self, assignment_id: str) -> sqlite3.Row | None:
        with self.lock:
            return self.conn.execute("SELECT * FROM assignment_sandboxes WHERE assignment_id = ?", (assignment_id,)).fetchone()

    def mark_assignment_sandbox_terminal(self, *, assignment_id: str, status: str) -> None:
        with self.lock:
            self.conn.execute(
                """
                UPDATE assignment_sandboxes
                SET status = ?, terminal_at = COALESCE(terminal_at, CURRENT_TIMESTAMP)
                WHERE assignment_id = ?
                """,
                (status, assignment_id),
            )
            self.conn.commit()

    def mark_assignment_sandbox_archived(self, assignment_id: str) -> None:
        with self.lock:
            self.conn.execute(
                """
                UPDATE assignment_sandboxes
                SET status = 'archived', archived_at = CURRENT_TIMESTAMP
                WHERE assignment_id = ?
                """,
                (assignment_id,),
            )
            self.conn.commit()

    def upsert_approval_request(
        self,
        *,
        request_id: str,
        assignment_id: str,
        team_name: str,
        task_id: str | None,
        kind: str,
        status: str,
        title: str,
        prompt: str,
        required_fields: list[Any] | dict[str, Any] | None = None,
        escalation_path: str | Path | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> sqlite3.Row:
        with self.lock:
            db.upsert_approval_request(
                self.conn,
                request_id=request_id,
                assignment_id=assignment_id,
                team_name=team_name,
                task_id=task_id,
                kind=kind,
                status=status,
                title=title,
                prompt=prompt,
                required_fields=required_fields,
                escalation_path=str(escalation_path) if escalation_path else None,
                metadata=metadata,
            )
            self.conn.commit()
            return self.get_approval_request(request_id)

    def get_approval_request(self, request_id: str) -> sqlite3.Row:
        with self.lock:
            row = self.conn.execute("SELECT * FROM approval_requests WHERE request_id = ?", (request_id,)).fetchone()
            if row is None:
                raise KeyError(request_id)
            return row

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

    def upsert_user_peer(
        self,
        *,
        peer_id: str,
        agent_card_url: str | None,
        agent_card_json: str,
        access_token: str | None = None,
    ) -> sqlite3.Row:
        with self.lock:
            row = db.upsert_user_peer(
                self.conn,
                peer_id=peer_id,
                agent_card_url=agent_card_url,
                agent_card_json=agent_card_json,
                access_token=access_token,
            )
            self.conn.commit()
            return row

    def get_user_peer(self, peer_id: str) -> sqlite3.Row | None:
        with self.lock:
            return db.get_user_peer(self.conn, peer_id)

    def find_user_peer_by_card_url(self, agent_card_url: str) -> sqlite3.Row | None:
        with self.lock:
            return db.find_user_peer_by_card_url(self.conn, agent_card_url)

    def list_user_peers(self) -> list[sqlite3.Row]:
        with self.lock:
            return db.list_user_peers(self.conn)

    def upsert_user_context(
        self,
        *,
        context_id: str,
        peer_id: str,
        task_id: str | None = None,
        push_url: str | None = None,
        push_token: str | None = None,
        status: str | None = None,
    ) -> sqlite3.Row:
        with self.lock:
            row = db.upsert_user_context(
                self.conn,
                context_id=context_id,
                peer_id=peer_id,
                task_id=task_id,
                push_url=push_url,
                push_token=push_token,
                status=status,
            )
            self.conn.commit()
            return row

    def get_user_context(self, context_id: str) -> sqlite3.Row | None:
        with self.lock:
            return db.get_user_context(self.conn, context_id)

    def set_onboarding(
        self,
        *,
        context_id: str,
        step: str,
        pending_request: str | None = None,
        partial_card_url: str | None = None,
        partial_card_json: str | None = None,
    ) -> None:
        with self.lock:
            db.set_onboarding(
                self.conn,
                context_id=context_id,
                step=step,
                pending_request=pending_request,
                partial_card_url=partial_card_url,
                partial_card_json=partial_card_json,
            )
            self.conn.commit()

    def get_onboarding(self, context_id: str) -> sqlite3.Row | None:
        with self.lock:
            return db.get_onboarding(self.conn, context_id)

    def delete_onboarding(self, context_id: str) -> None:
        with self.lock:
            db.delete_onboarding(self.conn, context_id)
            self.conn.commit()

    def close(self) -> None:
        with self.lock:
            self.conn.close()
