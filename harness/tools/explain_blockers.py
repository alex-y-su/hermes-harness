from __future__ import annotations

import argparse
import json
from typing import Any

from harness import db
from harness.tools.common import add_factory_args, paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Summarize current blockers, stale work, retries, and alerts.")
    add_factory_args(parser)
    parser.add_argument("--team", default=None)
    parser.add_argument("--json", action="store_true")
    return parser


def _rows(rows: list[Any]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def run(args: argparse.Namespace) -> dict[str, Any]:
    _factory, db_path = paths(args)
    team_filter = "AND team_name = ?" if args.team else ""
    params = (args.team,) if args.team else ()
    with db.session(db_path) as conn:
        user_requests = _rows(
            list(
                conn.execute(
                    f"""
                    SELECT request_id, assignment_id, team_name, kind, title, created_at
                    FROM approval_requests
                    WHERE status = 'open' {team_filter}
                    ORDER BY created_at ASC
                    """,
                    params,
                )
            )
        )
        assignments = _rows(
            list(
                conn.execute(
                    f"""
                    SELECT assignment_id, team_name, status, status_reason, retry_count, next_retry_at, last_error
                    FROM team_assignments
                    WHERE status IN ('stale', 'retrying', 'resuming', 'cancel-requested') {team_filter}
                    ORDER BY created_at ASC
                    """,
                    params,
                )
            )
        )
        alerts = _rows(
            [row for row in db.list_operator_alerts(conn, status="open") if not args.team or row["team_name"] == args.team]
        )
    return {
        "user_requests": user_requests,
        "assignments": assignments,
        "alerts": alerts,
        "counts": {
            "user_requests": len(user_requests),
            "assignments": len(assignments),
            "alerts": len(alerts),
        },
    }


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    result = run(args)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return
    print(
        f"user_requests={result['counts']['user_requests']} "
        f"assignments={result['counts']['assignments']} alerts={result['counts']['alerts']}"
    )
    for request in result["user_requests"]:
        print(f"waiting: {request['team_name']}/{request['assignment_id']} {request['title']}")
    for assignment in result["assignments"]:
        print(f"{assignment['status']}: {assignment['team_name']}/{assignment['assignment_id']} {assignment['status_reason'] or ''}")
    for alert in result["alerts"]:
        print(f"alert: {alert['severity']} {alert['kind']} {alert['title']}")


if __name__ == "__main__":
    main()
