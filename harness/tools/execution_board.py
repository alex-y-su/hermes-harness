from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
from typing import Any

from harness import db
from harness.factory import team_path
from harness.tools import dispatch_team
from harness.tools.common import add_factory_args, paths


MODES = {"observe", "prepare", "patch", "verify", "deploy", "operate", "escalate"}
ACTIVE_ASSIGNMENT_STATUSES = {"queued", "pending", "dispatched", "working", "retrying", "resuming", "stale"}
BLOCKED_ASSIGNMENT_STATUSES = {"input-required", "auth-required"}
TERMINAL_ASSIGNMENT_STATUSES = {"completed", "failed", "canceled", "archived", "cancel-requested"}

POLICY = """## Execution Policy

Default to closing loops, not producing strategy-only artifacts.

Allowed without user approval: inspect files/logs, create branches, edit scoped files,
run tests/builds, open draft PRs, deploy to staging, draft outbound packages, and
continue independent unblocked work.

Needs explicit user approval: send external messages, spend money, production DB writes,
publish public claims, contact external people/accounts/partners, use credentials in a new system, or
perform destructive changes outside the ticket scope.

If blocked, create a precise blocker and continue all unblocked work. Do not stop the
project because one activity is waiting on the user.
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create and run execution tickets for faster closed-loop work.")
    add_factory_args(parser)
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="Create one execution ticket.")
    create.add_argument("--ticket-id", default=None)
    create.add_argument("--goal-id", default=None)
    create.add_argument("--parent-ticket-id", default=None)
    create.add_argument("--title", required=True)
    create.add_argument("--mode", choices=sorted(MODES), default="patch")
    create.add_argument("--team", required=True)
    create.add_argument("--priority", type=int, default=100)
    create.add_argument("--order-id", default=None)
    create.add_argument("--body", default="")
    create.add_argument("--file", default=None, help="Read ticket body from Markdown file")
    create.add_argument("--write-scope", action="append", default=[])
    create.add_argument("--acceptance", action="append", default=[])
    create.add_argument("--verification", action="append", default=[])
    create.add_argument("--blocker", action="append", default=[])
    create.add_argument("--metadata", default=None, help="JSON object")
    create.add_argument("--json", action="store_true")

    tick = sub.add_parser("tick", help="Sync tickets and dispatch ready work.")
    tick.add_argument("--limit", type=int, default=10)
    tick.add_argument("--json", action="store_true")

    sync = sub.add_parser("sync", help="Sync ticket statuses from assignments and user requests.")
    sync.add_argument("--json", action="store_true")

    block = sub.add_parser("block", help="Turn a ticket into a user blocker card.")
    block.add_argument("ticket_id")
    block.add_argument("--kind", choices=["input-required", "auth-required", "approval-required"], default="approval-required")
    block.add_argument("--title", required=True)
    block.add_argument("--prompt", required=True)
    block.add_argument("--field", action="append", default=[])
    block.add_argument("--json", action="store_true")

    list_cmd = sub.add_parser("list", help="List execution tickets.")
    list_cmd.add_argument("--status", default="all")
    list_cmd.add_argument("--team", default=None)
    list_cmd.add_argument("--goal-id", default=None)
    list_cmd.add_argument("--json", action="store_true")
    return parser


def _load_json_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise SystemExit("--metadata must be a JSON object")
    return data


def _decode_ticket(row: Any) -> dict[str, Any]:
    data = dict(row)
    data["write_scope"] = json.loads(data.pop("write_scope_json") or "[]")
    data["acceptance"] = json.loads(data.pop("acceptance_json") or "[]")
    data["verification"] = json.loads(data.pop("verification_json") or "[]")
    data["blockers"] = json.loads(data.pop("blockers_json") or "[]")
    data["metadata"] = json.loads(data.get("metadata") or "{}")
    return data


def _ticket_body(ticket: dict[str, Any]) -> str:
    lines = [
        POLICY,
        f"## Execution Ticket",
        "",
        f"- ticket_id: {ticket['ticket_id']}",
        f"- mode: {ticket['mode']}",
        f"- priority: {ticket['priority']}",
        f"- goal_id: {ticket.get('goal_id') or ''}",
        "",
        "## Task",
        ticket["body"].strip() or ticket["title"],
    ]
    if ticket["write_scope"]:
        lines.extend(["", "## Write Scope", *[f"- {item}" for item in ticket["write_scope"]]])
    if ticket["acceptance"]:
        lines.extend(["", "## Acceptance Criteria", *[f"- {item}" for item in ticket["acceptance"]]])
    if ticket["verification"]:
        lines.extend(["", "## Verification Required", *[f"- {item}" for item in ticket["verification"]]])
    if ticket["blockers"]:
        lines.extend(
            [
                "",
                "## Known Blockers",
                *[f"- {item}" for item in ticket["blockers"]],
                "",
                "If one blocker applies, name the exact blocked activity and continue unblocked work.",
            ]
        )
    lines.extend(
        [
            "",
            "## Done Response",
            "Return the changed files/artifacts, verification evidence, remaining blockers, and next concrete handoff.",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def _create(args: argparse.Namespace) -> dict[str, Any]:
    factory, db_path = paths(args)
    if args.mode != "escalate" and not team_path(factory, args.team).exists():
        raise SystemExit(f"team does not exist: {args.team}")
    body = Path(args.file).read_text(encoding="utf-8") if args.file else args.body
    ticket_id = args.ticket_id or f"tkt-{uuid.uuid4().hex[:12]}"
    with db.session(db_path) as conn:
        db.upsert_execution_ticket(
            conn,
            ticket_id=ticket_id,
            goal_id=args.goal_id,
            parent_ticket_id=args.parent_ticket_id,
            title=args.title,
            mode=args.mode,
            team_name=args.team,
            status="ready",
            priority=args.priority,
            order_id=args.order_id,
            body=body,
            write_scope=args.write_scope,
            acceptance=args.acceptance,
            verification=args.verification,
            blockers=args.blocker,
            metadata=_load_json_object(args.metadata),
        )
        row = db.get_execution_ticket(conn, ticket_id)
    return {"ticket": _decode_ticket(row)}


def _sync_one(conn: Any, row: Any) -> dict[str, Any] | None:
    ticket = _decode_ticket(row)
    status = ticket["status"]
    if status in {"completed", "failed", "canceled"}:
        return None
    if ticket.get("approval_request_id"):
        request = conn.execute(
            "SELECT status FROM approval_requests WHERE request_id = ?",
            (ticket["approval_request_id"],),
        ).fetchone()
        if request and request["status"] == "open" and status != "blocked":
            updated = db.set_execution_ticket_status(conn, ticket_id=ticket["ticket_id"], status="blocked")
            return {"ticket_id": ticket["ticket_id"], "status": updated["status"], "reason": "approval_open"}
        if request and request["status"] in {"supplied", "resuming", "resolved"} and status == "blocked":
            updated = db.set_execution_ticket_status(conn, ticket_id=ticket["ticket_id"], status="ready")
            return {"ticket_id": ticket["ticket_id"], "status": updated["status"], "reason": "approval_supplied"}
    assignment_id = ticket.get("assignment_id")
    if not assignment_id:
        return None
    assignment = conn.execute("SELECT status FROM team_assignments WHERE assignment_id = ?", (assignment_id,)).fetchone()
    if assignment is None:
        return None
    assignment_status = assignment["status"]
    if assignment_status in ACTIVE_ASSIGNMENT_STATUSES:
        next_status = "working" if assignment_status in {"dispatched", "working"} else "queued"
        if status != next_status:
            updated = db.set_execution_ticket_status(conn, ticket_id=ticket["ticket_id"], status=next_status)
            return {"ticket_id": ticket["ticket_id"], "status": updated["status"], "reason": assignment_status}
    if assignment_status in BLOCKED_ASSIGNMENT_STATUSES:
        if status != "blocked":
            updated = db.set_execution_ticket_status(conn, ticket_id=ticket["ticket_id"], status="blocked")
            return {"ticket_id": ticket["ticket_id"], "status": updated["status"], "reason": assignment_status}
    if assignment_status == "completed":
        updated = db.set_execution_ticket_status(conn, ticket_id=ticket["ticket_id"], status="completed", terminal=True)
        return {"ticket_id": ticket["ticket_id"], "status": updated["status"], "reason": assignment_status}
    if assignment_status in TERMINAL_ASSIGNMENT_STATUSES:
        updated = db.set_execution_ticket_status(conn, ticket_id=ticket["ticket_id"], status="failed", terminal=True)
        return {"ticket_id": ticket["ticket_id"], "status": updated["status"], "reason": assignment_status}
    return None


def _sync(args: argparse.Namespace) -> dict[str, Any]:
    _factory, db_path = paths(args)
    changes = []
    with db.session(db_path) as conn:
        for row in db.list_execution_tickets(conn, status="all"):
            change = _sync_one(conn, row)
            if change:
                changes.append(change)
    return {"synced": changes, "count": len(changes)}


def _dispatch_ticket(factory: Path, db_path: Path, ticket: dict[str, Any]) -> dict[str, Any]:
    assignment_id = f"{ticket['ticket_id']}-{ticket['mode']}"
    parsed = dispatch_team.build_parser().parse_args(
        [
            "--factory",
            str(factory),
            "--db",
            str(db_path),
            ticket["team_name"],
            "--assignment-id",
            assignment_id,
            "--order-id",
            ticket.get("order_id") or ticket.get("goal_id") or "execution-board",
            "--title",
            ticket["title"],
            "--body",
            _ticket_body(ticket),
        ]
    )
    result = dispatch_team.run(parsed)
    with db.session(db_path) as conn:
        updated = db.set_execution_ticket_status(
            conn,
            ticket_id=ticket["ticket_id"],
            status="queued",
            assignment_id=result["assignment_id"],
        )
    return {"ticket_id": ticket["ticket_id"], "assignment_id": result["assignment_id"], "status": updated["status"]}


def _escalate_ticket(db_path: Path, ticket: dict[str, Any]) -> dict[str, Any]:
    request_id = f"{ticket['ticket_id']}:approval"
    fields = ticket["blockers"] or ticket["acceptance"] or ["approval_or_input"]
    with db.session(db_path) as conn:
        db.upsert_approval_request(
            conn,
            request_id=request_id,
            assignment_id=ticket["ticket_id"],
            team_name=ticket["team_name"],
            task_id=None,
            kind="approval-required",
            title=ticket["title"],
            prompt=ticket["body"] or ticket["title"],
            required_fields=fields,
            metadata={"ticket_id": ticket["ticket_id"], "mode": "escalate"},
        )
        updated = db.set_execution_ticket_status(
            conn,
            ticket_id=ticket["ticket_id"],
            status="blocked",
            approval_request_id=request_id,
        )
    return {"ticket_id": ticket["ticket_id"], "request_id": request_id, "status": updated["status"]}


def _tick(args: argparse.Namespace) -> dict[str, Any]:
    factory, db_path = paths(args)
    sync_result = _sync(argparse.Namespace(factory=str(factory), db=str(db_path)))
    dispatched = []
    escalated = []
    with db.session(db_path) as conn:
        ready = [_decode_ticket(row) for row in db.list_execution_tickets(conn, status="ready", limit=args.limit)]
    for ticket in ready:
        if ticket["mode"] == "escalate":
            escalated.append(_escalate_ticket(db_path, ticket))
            continue
        dispatched.append(_dispatch_ticket(factory, db_path, ticket))
    return {"synced": sync_result["synced"], "dispatched": dispatched, "escalated": escalated}


def _block(args: argparse.Namespace) -> dict[str, Any]:
    _factory, db_path = paths(args)
    request_id = f"{args.ticket_id}:{args.kind}"
    with db.session(db_path) as conn:
        ticket = db.get_execution_ticket(conn, args.ticket_id)
        if ticket is None:
            raise SystemExit(f"unknown ticket: {args.ticket_id}")
        db.upsert_approval_request(
            conn,
            request_id=request_id,
            assignment_id=args.ticket_id,
            team_name=ticket["team_name"],
            task_id=None,
            kind=args.kind,
            title=args.title,
            prompt=args.prompt,
            required_fields=args.field or ["response"],
            metadata={"ticket_id": args.ticket_id},
        )
        updated = db.set_execution_ticket_status(
            conn,
            ticket_id=args.ticket_id,
            status="blocked",
            approval_request_id=request_id,
        )
    return {"ticket": _decode_ticket(updated), "request_id": request_id}


def _list(args: argparse.Namespace) -> dict[str, Any]:
    _factory, db_path = paths(args)
    with db.session(db_path) as conn:
        tickets = [
            _decode_ticket(row)
            for row in db.list_execution_tickets(
                conn,
                status=args.status,
                team_name=args.team,
                goal_id=args.goal_id,
            )
        ]
    counts: dict[str, int] = {}
    for ticket in tickets:
        counts[ticket["status"]] = counts.get(ticket["status"], 0) + 1
    return {"tickets": tickets, "count": len(tickets), "counts": counts}


def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "create":
        return _create(args)
    if args.command == "tick":
        return _tick(args)
    if args.command == "sync":
        return _sync(args)
    if args.command == "block":
        return _block(args)
    if args.command == "list":
        return _list(args)
    raise SystemExit(f"unknown command: {args.command}")


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    result = run(args)
    if getattr(args, "json", False):
        print(json.dumps(result, indent=2, sort_keys=True))
        return
    if "ticket" in result:
        print(f"{result['ticket']['ticket_id']}: {result['ticket']['status']}")
    elif "tickets" in result:
        for ticket in result["tickets"]:
            print(f"{ticket['ticket_id']}: {ticket['status']} {ticket['mode']} {ticket['team_name']} {ticket['title']}")
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
