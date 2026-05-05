from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta

from harness import db
from harness.tools.common import add_factory_args, paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Return a compact SQLite-backed remote-team digest.")
    add_factory_args(parser)
    parser.add_argument("--team", default=None)
    parser.add_argument("--stale-minutes", type=int, default=5)
    parser.add_argument("--json", action="store_true")
    return parser


def run(args: argparse.Namespace) -> dict:
    _factory, db_path = paths(args)
    cutoff = (datetime.now(UTC) - timedelta(minutes=args.stale_minutes)).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
    where = "WHERE h.team_name = ?" if args.team else ""
    params = (args.team,) if args.team else ()
    with db.session(db_path) as conn:
        teams = [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT
                  h.team_name,
                  h.substrate,
                  h.status AS substrate_status,
                  h.provisioned_at,
                  h.expires_at,
                  h.archived_at,
                  MAX(e.ts) AS last_event_at,
                  COUNT(DISTINCT CASE
                    WHEN a.status NOT IN ('completed','failed','canceled','archived')
                    THEN a.assignment_id
                  END)
                    AS active_assignments,
                  COUNT(DISTINCT CASE
                    WHEN a.status = 'retrying'
                    THEN a.assignment_id
                  END)
                    AS retrying_assignments,
                  COUNT(DISTINCT CASE
                    WHEN a.status = 'stale'
                    THEN a.assignment_id
                  END)
                    AS stale_assignments,
                  COUNT(DISTINCT CASE
                    WHEN r.status = 'open'
                    THEN r.request_id
                  END)
                    AS open_user_requests
                FROM substrate_handles h
                LEFT JOIN team_events e ON e.team_name = h.team_name
                LEFT JOIN team_assignments a ON a.team_name = h.team_name
                LEFT JOIN approval_requests r ON r.team_name = h.team_name
                {where}
                GROUP BY h.team_name
                ORDER BY h.team_name
                """,
                params,
            )
        ]
        stale = [row["team_name"] for row in teams if not row["last_event_at"] or row["last_event_at"] < cutoff]
        failed = [
            dict(row)
            for row in conn.execute(
                """
                SELECT team_name, COUNT(*) AS failures
                FROM team_events
                WHERE state = 'failed' OR kind IN ('failed', 'critic-gaps')
                GROUP BY team_name
                ORDER BY failures DESC, team_name
                """
            )
        ]
        recent_events = [
            dict(row)
            for row in conn.execute(
                """
                SELECT team_name, kind, state, ts
                FROM team_events
                ORDER BY ts DESC, event_id DESC
                LIMIT 20
                """
            )
        ]
        user_requests = [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT request_id, assignment_id, team_name, task_id, kind, status, title, created_at, resolved_at, escalation_path
                FROM approval_requests
                WHERE status = 'open' {"AND team_name = ?" if args.team else ""}
                ORDER BY created_at DESC, request_id DESC
                LIMIT 50
                """,
                params,
            )
        ]
        assignments = [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT
                  assignment_id, team_name, status, status_reason, blocked_by,
                  retry_count, max_retries, next_retry_at, last_heartbeat_at,
                  last_error, lease_owner, lease_expires_at
                FROM team_assignments
                WHERE status IN ('retrying', 'stale', 'input-required', 'auth-required')
                  {"AND team_name = ?" if args.team else ""}
                ORDER BY created_at DESC, assignment_id DESC
                LIMIT 100
                """,
                params,
            )
        ]
    return {
        "teams": teams,
        "stale": stale,
        "failed": failed,
        "recent_events": recent_events,
        "user_requests": user_requests,
        "assignments": assignments,
    }


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    result = run(args)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return
    for team in result["teams"]:
        print(
            f"{team['team_name']}: substrate={team['substrate']} "
            f"status={team['substrate_status']} active={team['active_assignments'] or 0} "
            f"retrying={team['retrying_assignments'] or 0} stale={team['stale_assignments'] or 0} "
            f"user_requests={team['open_user_requests'] or 0} "
            f"last_event={team['last_event_at'] or 'never'}"
        )
    if result["user_requests"]:
        print("waiting_on_user:")
        for request in result["user_requests"]:
            print(
                f"  {request['request_id']} team={request['team_name']} "
                f"assignment={request['assignment_id']} kind={request['kind']} title={request['title']}"
            )
    if result["stale"]:
        print("stale: " + ", ".join(result["stale"]))


if __name__ == "__main__":
    main()
