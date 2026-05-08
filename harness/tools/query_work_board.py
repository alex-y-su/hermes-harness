from __future__ import annotations

import argparse
import json
from typing import Any

from harness import db
from harness.tools.common import add_factory_args, paths


COLUMNS = {
    "queued": {"queued", "pending"},
    "running": {"dispatched", "working", "spawned", "booted"},
    "waiting_on_user": {"input-required", "auth-required"},
    "resuming": {"resuming"},
    "retrying": {"retrying"},
    "stale": {"stale"},
    "completed": {"completed"},
    "stopped": {"failed", "canceled", "cancel-requested", "archived"},
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Return the full read-only assignment work board.")
    add_factory_args(parser)
    parser.add_argument("--team", default=None)
    parser.add_argument("--json", action="store_true")
    return parser


def _decode_resume(row: Any) -> dict[str, Any]:
    data = dict(row)
    data["response"] = json.loads(data.pop("response_json") or "null")
    data["metadata"] = json.loads(data.get("metadata") or "{}")
    return data


def _decode_ticket(row: Any) -> dict[str, Any]:
    data = dict(row)
    data["write_scope"] = json.loads(data.pop("write_scope_json") or "[]")
    data["acceptance"] = json.loads(data.pop("acceptance_json") or "[]")
    data["verification"] = json.loads(data.pop("verification_json") or "[]")
    data["blockers"] = json.loads(data.pop("blockers_json") or "[]")
    data["metadata"] = json.loads(data.get("metadata") or "{}")
    return data


def run(args: argparse.Namespace) -> dict[str, Any]:
    _factory, db_path = paths(args)
    where = "WHERE team_name = ?" if args.team else ""
    params = (args.team,) if args.team else ()
    with db.session(db_path) as conn:
        assignments = [dict(row) for row in conn.execute(f"SELECT * FROM team_assignments {where} ORDER BY created_at DESC", params)]
        tickets = [
            _decode_ticket(row)
            for row in conn.execute(
                f"SELECT * FROM execution_tickets {where} ORDER BY priority ASC, created_at DESC",
                params,
            )
        ]
        requests = [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT request_id, assignment_id, team_name, kind, status, title, created_at, resolved_at
                FROM approval_requests
                {where}
                ORDER BY created_at DESC
                """,
                params,
            )
        ]
        resumes = [_decode_resume(row) for row in db.list_assignment_resumes(conn)]
        sandboxes = [dict(row) for row in conn.execute("SELECT * FROM assignment_sandboxes ORDER BY created_at DESC")]
        alerts = [
            dict(row)
            for row in db.list_operator_alerts(conn, status="open")
            if not args.team or row["team_name"] == args.team
        ]
    board = {name: [] for name in COLUMNS}
    for assignment in assignments:
        status = str(assignment["status"])
        target = next((name for name, statuses in COLUMNS.items() if status in statuses), "stopped")
        board[target].append(assignment)
    ticket_columns = {name: [] for name in COLUMNS}
    for ticket in tickets:
        status = str(ticket["status"])
        if status in {"ready", "queued"}:
            target = "queued"
        elif status == "working":
            target = "running"
        elif status == "blocked":
            target = "waiting_on_user"
        elif status == "completed":
            target = "completed"
        elif status in {"failed", "canceled"}:
            target = "stopped"
        else:
            target = next((name for name, statuses in COLUMNS.items() if status in statuses), "stopped")
        ticket_columns[target].append(ticket)
    return {
        "columns": board,
        "counts": {name: len(items) for name, items in board.items()},
        "execution_tickets": tickets,
        "execution_ticket_columns": ticket_columns,
        "execution_ticket_counts": {name: len(items) for name, items in ticket_columns.items()},
        "user_requests": requests,
        "resumes": resumes,
        "sandboxes": sandboxes,
        "alerts": alerts,
    }


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    result = run(args)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return
    for name, count in result["counts"].items():
        print(f"{name}: {count}")


if __name__ == "__main__":
    main()
