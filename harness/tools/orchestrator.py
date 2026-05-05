from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from harness import db
from harness.tools.common import add_factory_args, paths


RUNNING_STATUSES = {"dispatched", "working", "resuming"}
WAITING_STATUSES = {"input-required", "auth-required"}
TERMINAL_STATUSES = {"completed", "failed", "canceled", "archived"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Hermes Harness watchdog/orchestrator maintenance.")
    add_factory_args(parser)
    parser.add_argument("--holder", default=None)
    parser.add_argument("--stale-minutes", type=int, default=int(os.getenv("HARNESS_ORCHESTRATOR_STALE_MINUTES", "15")))
    parser.add_argument("--user-request-alert-minutes", type=int, default=int(os.getenv("HARNESS_USER_REQUEST_ALERT_MINUTES", "60")))
    parser.add_argument("--lease-ttl-seconds", type=int, default=int(os.getenv("HARNESS_ORCHESTRATOR_LEASE_TTL_SECONDS", "60")))
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--poll-seconds", type=int, default=int(os.getenv("HARNESS_ORCHESTRATOR_POLL_SECONDS", "30")))
    parser.add_argument("--json", action="store_true")
    return parser


def _holder(explicit: str | None) -> str:
    return explicit or f"orchestrator:{socket.gethostname()}:{os.getpid()}"


def _cutoff(stale_minutes: int) -> str:
    return (datetime.now(UTC) - timedelta(minutes=stale_minutes)).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


def _decode_assignment(row: Any) -> dict[str, Any]:
    return dict(row)


def _alert_id(dedupe_key: str) -> str:
    return f"alert-{hashlib.sha1(dedupe_key.encode('utf-8')).hexdigest()[:16]}"


def run_once(args: argparse.Namespace) -> dict[str, Any]:
    _factory, db_path = paths(args)
    holder = _holder(getattr(args, "holder", None))
    lease_ttl = int(getattr(args, "lease_ttl_seconds", 60))
    stale_cutoff = _cutoff(int(getattr(args, "stale_minutes", 15)))
    user_request_cutoff = _cutoff(int(getattr(args, "user_request_alert_minutes", 60)))
    actions: list[dict[str, Any]] = []
    with db.session(db_path) as conn:
        expired_leases = db.cleanup_expired_leases(conn)
        if expired_leases:
            actions.append({"action": "expired-leases-cleaned", "count": expired_leases, "team_name": "system", "assignment_id": ""})

        retry_rows = list(
            conn.execute(
                """
                SELECT *
                FROM team_assignments
                WHERE status = 'retrying'
                  AND (next_retry_at IS NULL OR next_retry_at <= CURRENT_TIMESTAMP)
                ORDER BY next_retry_at ASC, created_at ASC
                """
            )
        )
        for row in retry_rows:
            assignment_id = row["assignment_id"]
            if not db.acquire_lease(
                conn,
                resource_type="assignment",
                resource_id=assignment_id,
                holder=holder,
                ttl_seconds=lease_ttl,
            ):
                continue
            db.mark_assignment_retry_due(conn, assignment_id=assignment_id)
            db.record_event(
                conn,
                team_name=row["team_name"],
                assignment_id=assignment_id,
                source="harness.orchestrator",
                kind="retry-due",
                state="queued",
                metadata={"previous_status": row["status"], "retry_count": row["retry_count"]},
            )
            db.release_lease(conn, resource_type="assignment", resource_id=assignment_id, holder=holder)
            actions.append({"action": "retry-due", "assignment_id": assignment_id, "team_name": row["team_name"]})

        stale_rows = list(
            conn.execute(
                """
                SELECT a.*
                FROM team_assignments a
                WHERE a.status IN ('dispatched', 'working', 'resuming')
                  AND COALESCE(a.last_heartbeat_at, a.dispatched_at, a.created_at) < ?
                  AND NOT EXISTS (
                    SELECT 1
                    FROM approval_requests r
                    WHERE r.assignment_id = a.assignment_id
                      AND r.status = 'open'
                  )
                ORDER BY COALESCE(a.last_heartbeat_at, a.dispatched_at, a.created_at) ASC
                """,
                (stale_cutoff,),
            )
        )
        for row in stale_rows:
            assignment_id = row["assignment_id"]
            if not db.acquire_lease(
                conn,
                resource_type="assignment",
                resource_id=assignment_id,
                holder=holder,
                ttl_seconds=lease_ttl,
            ):
                continue
            reason = f"no heartbeat since {row['last_heartbeat_at'] or row['dispatched_at'] or row['created_at']}"
            db.mark_assignment_stale(conn, assignment_id=assignment_id, reason=reason)
            dedupe_key = f"assignment-stale:{assignment_id}"
            db.upsert_operator_alert(
                conn,
                alert_id=_alert_id(dedupe_key),
                dedupe_key=dedupe_key,
                severity="warning",
                kind="assignment-stale",
                team_name=row["team_name"],
                assignment_id=assignment_id,
                title=f"Assignment stale: {assignment_id}",
                body=f"{row['team_name']} assignment {assignment_id} has {reason}.",
                metadata={"previous_status": row["status"], "task_id": row["a2a_task_id"]},
            )
            db.record_event(
                conn,
                team_name=row["team_name"],
                assignment_id=assignment_id,
                task_id=row["a2a_task_id"],
                source="harness.orchestrator",
                kind="assignment-stale",
                state="stale",
                metadata={"reason": reason, "previous_status": row["status"]},
            )
            db.release_lease(conn, resource_type="assignment", resource_id=assignment_id, holder=holder)
            actions.append({"action": "assignment-stale", "assignment_id": assignment_id, "team_name": row["team_name"]})

        long_requests = list(
            conn.execute(
                """
                SELECT *
                FROM approval_requests
                WHERE status = 'open'
                  AND created_at < ?
                ORDER BY created_at ASC
                """,
                (user_request_cutoff,),
            )
        )
        for row in long_requests:
            dedupe_key = f"user-request-waiting:{row['request_id']}"
            db.upsert_operator_alert(
                conn,
                alert_id=_alert_id(dedupe_key),
                dedupe_key=dedupe_key,
                severity="info",
                kind="user-request-waiting",
                team_name=row["team_name"],
                assignment_id=row["assignment_id"],
                request_id=row["request_id"],
                title=f"User request still open: {row['title']}",
                body=f"{row['team_name']} is waiting on user input for {row['assignment_id']}.",
                metadata={"created_at": row["created_at"], "kind": row["kind"]},
            )
            actions.append(
                {
                    "action": "user-request-alerted",
                    "assignment_id": row["assignment_id"],
                    "team_name": row["team_name"],
                    "request_id": row["request_id"],
                }
            )

        waiting_rows = [
            _decode_assignment(row)
            for row in conn.execute(
                """
                SELECT DISTINCT a.*
                FROM team_assignments a
                JOIN approval_requests r ON r.assignment_id = a.assignment_id
                WHERE r.status = 'open'
                  AND a.status NOT IN ('completed', 'failed', 'canceled', 'archived', 'input-required', 'auth-required')
                ORDER BY a.created_at ASC
                """
            )
        ]
        for row in waiting_rows:
            request = conn.execute(
                """
                SELECT request_id, kind, title
                FROM approval_requests
                WHERE assignment_id = ? AND status = 'open'
                ORDER BY created_at DESC, request_id DESC
                LIMIT 1
                """,
                (row["assignment_id"],),
            ).fetchone()
            if request is None:
                continue
            status = "auth-required" if request["kind"] == "auth-required" else "input-required"
            db.mark_assignment_blocked(
                conn,
                assignment_id=row["assignment_id"],
                status=status,
                blocked_by=request["request_id"],
                reason=request["title"],
            )
            actions.append(
                {
                    "action": "waiting-on-user",
                    "assignment_id": row["assignment_id"],
                    "team_name": row["team_name"],
                    "request_id": request["request_id"],
                }
            )

    return {"holder": holder, "actions": actions, "count": len(actions)}


def run(args: argparse.Namespace) -> dict[str, Any]:
    if not getattr(args, "loop", False):
        return run_once(args)
    latest: dict[str, Any] = {"actions": [], "count": 0}
    while True:
        latest = run_once(args)
        time.sleep(int(getattr(args, "poll_seconds", 30)))
    return latest


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    result = run(args)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return
    for action in result["actions"]:
        print(f"{action['action']}: {action['team_name']}/{action['assignment_id']}")
    if not result["actions"]:
        print("no watchdog actions")


if __name__ == "__main__":
    main()
