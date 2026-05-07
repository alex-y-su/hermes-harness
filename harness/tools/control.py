from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

from harness import db
from harness.tools import (
    ack_alert,
    cancel_assignment,
    execution_board,
    explain_blockers,
    orchestrator,
    query_alerts,
    query_remote_teams,
    query_user_requests,
    query_work_board,
    requeue_assignment,
    resolve_user_request,
)
from harness.tools.common import add_factory_args, paths
from harness.viewer.data import (
    assignment_detail,
    dashboard,
    execution_ticket_detail,
    graph,
    hub_config,
    resource_detail,
    schedules,
    team_detail,
)


def _base_parent() -> argparse.ArgumentParser:
    parent = argparse.ArgumentParser(add_help=False)
    add_factory_args(parent)
    parent.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parent.add_argument("--url", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    parent.add_argument("--token", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    return parent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Consolidated Hermes Harness operator CLI for observability and control."
    )
    parser.add_argument("--url", default=os.getenv("HARNESS_CONTROL_URL", ""), help="Remote Hermes Harness control API base URL.")
    parser.add_argument("--token", default=os.getenv("HARNESS_CONTROL_TOKEN", ""), help="Bearer token for remote control API.")
    sub = parser.add_subparsers(dest="command", required=True)
    base = _base_parent()

    dashboard_cmd = sub.add_parser("dashboard", parents=[base], help="Return the same aggregate data used by the web dashboard.")
    dashboard_cmd.add_argument("--full", action="store_true", help="Keep full dashboard payload in text mode.")

    status = sub.add_parser("status", parents=[base], help="Summarize teams, blockers, alerts, requests, and board counts.")
    status.add_argument("--team", default=None)
    status.add_argument("--stale-minutes", type=int, default=5)

    logs = sub.add_parser("logs", parents=[base], help="Read recent DB events plus team/assignment log files.")
    logs.add_argument("--team", default=None)
    logs.add_argument("--assignment-id", default=None)
    logs.add_argument("--limit", type=int, default=30)
    logs.add_argument("--tail-lines", type=int, default=80)
    logs.add_argument("--include-files", action="store_true", help="Include assignment payload file tails.")

    teams = sub.add_parser("teams", help="List and inspect teams.")
    team_sub = teams.add_subparsers(dest="team_command", required=True)
    team_list = team_sub.add_parser("list", parents=[base], help="List remote teams and compact health state.")
    team_list.add_argument("--team", default=None)
    team_list.add_argument("--stale-minutes", type=int, default=5)
    team_get = team_sub.add_parser("get", parents=[base], help="Inspect one team with journal, requests, alerts, and assignments.")
    team_get.add_argument("team")

    board = sub.add_parser("board", parents=[base], help="Show the assignment/ticket work board.")
    board.add_argument("--team", default=None)

    requests = sub.add_parser("requests", help="List, inspect, and resolve user-blocked requests.")
    request_sub = requests.add_subparsers(dest="request_command", required=True)
    req_list = request_sub.add_parser("list", parents=[base], help="List approval/input/auth requests.")
    req_list.add_argument("--status", choices=["open", "supplied", "resuming", "resolved", "denied", "all"], default="open")
    req_list.add_argument("--team", default=None)
    req_list.add_argument("--assignment-id", default=None)
    req_get = request_sub.add_parser("get", parents=[base], help="Inspect one request with prompt, response, metadata, and ticket link.")
    req_get.add_argument("request_id")
    req_resolve = request_sub.add_parser("resolve", parents=[base], help="Resolve one request with explicit JSON.")
    req_resolve.add_argument("request_id")
    req_resolve.add_argument("--response-json", required=True)
    req_resolve.add_argument("--status", choices=["supplied", "resuming", "resolved", "denied"], default="supplied")
    req_resolve.add_argument("--continue-work", action="store_true", help="Queue continuation work when supported.")
    req_resolve.add_argument("--continuation-assignment-id", default=None)
    req_approve = request_sub.add_parser("approve", parents=[base], help="Approve a human approval request.")
    req_approve.add_argument("request_id")
    req_approve.add_argument("--comment", default="")
    req_approve.add_argument("--continue-work", action="store_true")
    req_reject = request_sub.add_parser("reject", parents=[base], help="Reject a human approval request.")
    req_reject.add_argument("request_id")
    req_reject.add_argument("--comment", default="")

    approve = sub.add_parser("approve", parents=[base], help="Shortcut for requests approve.")
    approve.add_argument("request_id")
    approve.add_argument("--comment", default="")
    approve.add_argument("--continue-work", action="store_true")

    alerts = sub.add_parser("alerts", help="List and acknowledge operator alerts.")
    alert_sub = alerts.add_subparsers(dest="alert_command", required=True)
    alert_list = alert_sub.add_parser("list", parents=[base], help="List alerts.")
    alert_list.add_argument("--status", default="open")
    alert_list.add_argument("--severity", default=None)
    alert_list.add_argument("--kind", default=None)
    alert_ack = alert_sub.add_parser("ack", parents=[base], help="Acknowledge one alert.")
    alert_ack.add_argument("alert_id")

    assignments = sub.add_parser("assignments", help="Inspect and manage assignments.")
    assignment_sub = assignments.add_subparsers(dest="assignment_command", required=True)
    assignment_list = assignment_sub.add_parser("list", parents=[base], help="List assignments.")
    assignment_list.add_argument("--team", default=None)
    assignment_list.add_argument("--status", default="active", help="active, all, or an exact status.")
    assignment_list.add_argument("--limit", type=int, default=50)
    assignment_get = assignment_sub.add_parser("get", parents=[base], help="Inspect one assignment.")
    assignment_get.add_argument("assignment_id")
    assignment_cancel = assignment_sub.add_parser("cancel", parents=[base], help="Mark one assignment cancel-requested.")
    assignment_cancel.add_argument("assignment_id")
    assignment_cancel.add_argument("--reason", default="operator requested cancellation")
    assignment_requeue = assignment_sub.add_parser("requeue", parents=[base], help="Requeue retrying or stale work.")
    assignment_requeue.add_argument("assignment_id")
    assignment_requeue.add_argument("--force", action="store_true")

    tickets = sub.add_parser("tickets", help="Manage execution tickets and goals.")
    ticket_sub = tickets.add_subparsers(dest="ticket_command", required=True)
    ticket_list = ticket_sub.add_parser("list", parents=[base], help="List execution tickets.")
    ticket_list.add_argument("--status", default="all")
    ticket_list.add_argument("--team", default=None)
    ticket_list.add_argument("--goal-id", default=None)
    ticket_get = ticket_sub.add_parser("get", parents=[base], help="Inspect one execution ticket.")
    ticket_get.add_argument("ticket_id")
    ticket_create = ticket_sub.add_parser("create", parents=[base], help="Create an execution ticket.")
    ticket_create.add_argument("--ticket-id", default=None)
    ticket_create.add_argument("--goal-id", default=None)
    ticket_create.add_argument("--parent-ticket-id", default=None)
    ticket_create.add_argument("--title", required=True)
    ticket_create.add_argument("--mode", choices=sorted(execution_board.MODES), default="patch")
    ticket_create.add_argument("--team", required=True)
    ticket_create.add_argument("--priority", type=int, default=100)
    ticket_create.add_argument("--order-id", default=None)
    ticket_create.add_argument("--body", default="")
    ticket_create.add_argument("--file", default=None)
    ticket_create.add_argument("--write-scope", action="append", default=[])
    ticket_create.add_argument("--acceptance", action="append", default=[])
    ticket_create.add_argument("--verification", action="append", default=[])
    ticket_create.add_argument("--blocker", action="append", default=[])
    ticket_create.add_argument("--metadata", default=None)
    ticket_set = ticket_sub.add_parser("set", parents=[base], help="Update ticket goal/status/priority/title/body.")
    ticket_set.add_argument("ticket_id")
    ticket_set.add_argument("--goal-id", default=None)
    ticket_set.add_argument("--status", default=None)
    ticket_set.add_argument("--priority", type=int, default=None)
    ticket_set.add_argument("--title", default=None)
    ticket_set.add_argument("--body", default=None)
    ticket_set.add_argument("--team", default=None)
    ticket_block = ticket_sub.add_parser("block", parents=[base], help="Turn a ticket into a user blocker card.")
    ticket_block.add_argument("ticket_id")
    ticket_block.add_argument("--kind", choices=["input-required", "auth-required", "approval-required"], default="approval-required")
    ticket_block.add_argument("--title", required=True)
    ticket_block.add_argument("--prompt", required=True)
    ticket_block.add_argument("--field", action="append", default=[])
    ticket_tick = ticket_sub.add_parser("tick", parents=[base], help="Sync tickets and dispatch ready work.")
    ticket_tick.add_argument("--limit", type=int, default=10)
    ticket_sub.add_parser("sync", parents=[base], help="Sync ticket statuses from assignments and user requests.")

    goals = sub.add_parser("goals", help="List or reassign ticket goal IDs.")
    goal_sub = goals.add_subparsers(dest="goal_command", required=True)
    goal_sub.add_parser("list", parents=[base], help="Summarize goal IDs from execution tickets.")
    goal_set = goal_sub.add_parser("set", parents=[base], help="Move one ticket to a goal ID.")
    goal_set.add_argument("ticket_id")
    goal_set.add_argument("--goal-id", required=True)

    watchdog = sub.add_parser("watchdog", parents=[base], help="Run one orchestrator/watchdog pass.")
    watchdog.add_argument("--stale-minutes", type=int, default=15)
    watchdog.add_argument("--user-request-alert-minutes", type=int, default=60)
    watchdog.add_argument("--blocked-sandbox-ttl-minutes", type=int, default=240)
    watchdog.add_argument("--orphan-sandbox-ttl-minutes", type=int, default=60)
    watchdog.add_argument("--lease-ttl-seconds", type=int, default=60)
    watchdog.add_argument("--holder", default=None)
    watchdog.add_argument("--env", default=None)

    resources = sub.add_parser("resources", help="List and inspect file-backed resources.")
    resource_sub = resources.add_subparsers(dest="resource_command", required=True)
    resource_sub.add_parser("list", parents=[base], help="List resource summaries from the dashboard.")
    resource_get = resource_sub.add_parser("get", parents=[base], help="Inspect one resource.")
    resource_get.add_argument("resource_id")

    sub.add_parser("graph", parents=[base], help="Return org graph nodes and edges.")
    sub.add_parser("schedules", parents=[base], help="Return Hermes cron schedules.")
    sub.add_parser("config", parents=[base], help="Return live/fallback hub config files.")

    return parser


def _decode_json_field(data: dict[str, Any], key: str, default: str) -> None:
    data[key] = json.loads(data.get(key) or default)


def _decode_request(row: Any) -> dict[str, Any]:
    data = dict(row)
    _decode_json_field(data, "metadata", "{}")
    data["required_fields"] = json.loads(data.pop("required_fields_json") or "[]")
    data["response"] = json.loads(data.pop("response_json") or "null")
    return data


def _decode_alert(row: Any) -> dict[str, Any]:
    data = dict(row)
    _decode_json_field(data, "metadata", "{}")
    return data


def _decode_ticket(row: Any) -> dict[str, Any]:
    data = dict(row)
    data["write_scope"] = json.loads(data.pop("write_scope_json") or "[]")
    data["acceptance"] = json.loads(data.pop("acceptance_json") or "[]")
    data["verification"] = json.loads(data.pop("verification_json") or "[]")
    data["blockers"] = json.loads(data.pop("blockers_json") or "[]")
    _decode_json_field(data, "metadata", "{}")
    return data


def _decode_resume(row: Any) -> dict[str, Any]:
    data = dict(row)
    data["response"] = json.loads(data.pop("response_json") or "null")
    _decode_json_field(data, "metadata", "{}")
    return data


def _ns(args: argparse.Namespace, **overrides: Any) -> argparse.Namespace:
    data = vars(args).copy()
    data.update(overrides)
    return argparse.Namespace(**data)


def _tail_text(path: Path, lines: int) -> str:
    if not path.exists() or not path.is_file():
        return ""
    content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(content[-lines:])


def _run_status(args: argparse.Namespace) -> dict[str, Any]:
    remote = query_remote_teams.run(_ns(args, json=True))
    blockers = explain_blockers.run(_ns(args, json=True))
    alerts = query_alerts.run(_ns(args, status="open", severity=None, kind=None, json=True))
    requests = query_user_requests.run(_ns(args, status="open", assignment_id=None, json=True))
    board = query_work_board.run(_ns(args, json=True))
    return {
        "summary": {
            "teams": len(remote["teams"]),
            "stale_teams": len(remote["stale"]),
            "open_alerts": alerts["count"],
            "waiting_on_user": requests["count"],
            "assignments": board["counts"],
            "execution_tickets": board["execution_ticket_counts"],
            "blockers": blockers["counts"],
        },
        "teams": remote["teams"],
        "stale": remote["stale"],
        "open_alerts": alerts["alerts"],
        "user_requests": requests["requests"],
        "recent_events": remote["recent_events"],
        "blockers": blockers,
    }


def _run_dashboard(args: argparse.Namespace) -> dict[str, Any]:
    factory, db_path = paths(args)
    return dashboard(factory, db_path)


def _run_logs(args: argparse.Namespace) -> dict[str, Any]:
    factory, db_path = paths(args)
    clauses = []
    params: list[Any] = []
    if args.team:
        clauses.append("team_name = ?")
        params.append(args.team)
    if args.assignment_id:
        clauses.append("assignment_id = ?")
        params.append(args.assignment_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with db.session(db_path) as conn:
        events = [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT event_id, team_name, assignment_id, task_id, source, kind, state, ts, payload_path, metadata
                FROM team_events
                {where}
                ORDER BY ts DESC, event_id DESC
                LIMIT ?
                """,
                [*params, args.limit],
            )
        ]
        for event in events:
            event["metadata"] = json.loads(event.get("metadata") or "{}")
        assignment = None
        sandbox = None
        if args.assignment_id:
            row = conn.execute("SELECT * FROM team_assignments WHERE assignment_id = ?", (args.assignment_id,)).fetchone()
            assignment = dict(row) if row else None
            sandbox_row = db.load_assignment_sandbox(conn, args.assignment_id)
            sandbox = dict(sandbox_row) if sandbox_row else None
    journal_tail = ""
    if args.team:
        journal_tail = _tail_text(factory / "teams" / args.team / "journal.md", args.tail_lines)
    files: dict[str, str] = {}
    if args.include_files and assignment:
        for key in ("inbox_path", "in_flight_path", "completed_path"):
            value = assignment.get(key)
            if value:
                files[key] = _tail_text(Path(value), args.tail_lines)
    return {
        "events": events,
        "journal_tail": journal_tail,
        "assignment": assignment,
        "sandbox": sandbox,
        "files": files,
    }


def _run_request_get(args: argparse.Namespace) -> dict[str, Any]:
    factory, db_path = paths(args)
    with db.session(db_path) as conn:
        row = conn.execute("SELECT * FROM approval_requests WHERE request_id = ?", (args.request_id,)).fetchone()
        if row is None:
            raise SystemExit(f"unknown request: {args.request_id}")
        request = _decode_request(row)
        ticket = conn.execute(
            """
            SELECT *
            FROM execution_tickets
            WHERE approval_request_id = ?
               OR ticket_id = ?
               OR assignment_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (args.request_id, request["assignment_id"], request["assignment_id"]),
        ).fetchone()
    escalation_body = ""
    if request.get("escalation_path"):
        escalation_body = _tail_text(Path(request["escalation_path"]), 10_000)
    return {
        "request": request,
        "ticket": _decode_ticket(ticket) if ticket else None,
        "escalation_body": escalation_body,
        "relative_escalation_path": str(Path(request["escalation_path"]).relative_to(factory))
        if request.get("escalation_path") and Path(request["escalation_path"]).is_absolute() and Path(request["escalation_path"]).is_relative_to(factory)
        else request.get("escalation_path"),
    }


def _update_ticket_after_request(db_path: Path, request_id: str, action: str) -> dict[str, Any] | None:
    with db.session(db_path) as conn:
        row = conn.execute("SELECT * FROM approval_requests WHERE request_id = ?", (request_id,)).fetchone()
        if row is None:
            return None
        ticket = conn.execute(
            """
            SELECT *
            FROM execution_tickets
            WHERE approval_request_id = ?
               OR ticket_id = ?
               OR assignment_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (request_id, row["assignment_id"], row["assignment_id"]),
        ).fetchone()
        if ticket is None:
            return None
        if action == "reject":
            updated = db.set_execution_ticket_status(conn, ticket_id=ticket["ticket_id"], status="canceled", terminal=True)
        elif ticket["status"] == "blocked":
            next_status = "completed" if ticket["mode"] == "escalate" else "ready"
            updated = db.set_execution_ticket_status(
                conn,
                ticket_id=ticket["ticket_id"],
                status=next_status,
                terminal=next_status == "completed",
            )
        else:
            updated = ticket
    return _decode_ticket(updated) if updated else None


def _resolve_request(args: argparse.Namespace, *, response: Any, action: str, status: str) -> dict[str, Any]:
    factory, db_path = paths(args)
    if getattr(args, "continue_work", False):
        result = resolve_user_request.run(
            _ns(
                args,
                response_json=json.dumps(response, sort_keys=True),
                status=status,
                no_continuation=False,
                continuation_assignment_id=getattr(args, "continuation_assignment_id", None),
            )
        )
    else:
        with db.session(db_path) as conn:
            row = db.resolve_approval_request(
                conn,
                request_id=args.request_id,
                response=response,
                status=status,
                metadata={"resolved_by": "harness-control", "viewer_action": action},
            )
            if row is None:
                raise SystemExit(f"unknown request: {args.request_id}")
            result = _decode_request(row)
    ticket = _update_ticket_after_request(db_path, args.request_id, action)
    return {"request": result, "ticket": ticket}


def _run_requests(args: argparse.Namespace) -> dict[str, Any]:
    command = args.request_command
    if command == "list":
        return query_user_requests.run(args)
    if command == "get":
        return _run_request_get(args)
    if command == "resolve":
        response = json.loads(args.response_json)
        action = "resolve" if args.status != "denied" else "reject"
        return _resolve_request(args, response=response, action=action, status=args.status)
    if command == "approve":
        response = {"action": "approve", "approved": True, "comment": args.comment, "source": "harness-control"}
        return _resolve_request(args, response=response, action="approve", status="supplied")
    if command == "reject":
        response = {"action": "reject", "approved": False, "comment": args.comment, "source": "harness-control"}
        return _resolve_request(args, response=response, action="reject", status="denied")
    raise SystemExit(f"unknown requests command: {command}")


def _run_alerts(args: argparse.Namespace) -> dict[str, Any]:
    if args.alert_command == "list":
        return query_alerts.run(args)
    if args.alert_command == "ack":
        return {"alert": ack_alert.run(args)}
    raise SystemExit(f"unknown alerts command: {args.alert_command}")


def _run_assignments(args: argparse.Namespace) -> dict[str, Any]:
    factory, db_path = paths(args)
    command = args.assignment_command
    if command == "cancel":
        return {"assignment": cancel_assignment.run(args)}
    if command == "requeue":
        return {"assignment": requeue_assignment.run(args)}
    with db.session(db_path) as conn:
        if command == "list":
            clauses = []
            params: list[Any] = []
            if args.team:
                clauses.append("team_name = ?")
                params.append(args.team)
            if args.status == "active":
                clauses.append("status NOT IN ('completed','failed','canceled','archived')")
            elif args.status != "all":
                clauses.append("status = ?")
                params.append(args.status)
            where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            rows = [
                dict(row)
                for row in conn.execute(
                    f"SELECT * FROM team_assignments {where} ORDER BY created_at DESC, assignment_id DESC LIMIT ?",
                    [*params, args.limit],
                )
            ]
            return {"count": len(rows), "assignments": rows}
        if command == "get":
            detail = assignment_detail(factory, db_path, args.assignment_id)
            if detail is None:
                raise SystemExit(f"unknown assignment: {args.assignment_id}")
            return detail
    raise SystemExit(f"unknown assignments command: {command}")


def _ticket_set(args: argparse.Namespace) -> dict[str, Any]:
    _factory, db_path = paths(args)
    updates = {
        "goal_id": getattr(args, "goal_id", None),
        "status": getattr(args, "status", None),
        "priority": getattr(args, "priority", None),
        "title": getattr(args, "title", None),
        "body": getattr(args, "body", None),
        "team_name": getattr(args, "team", None),
    }
    pairs = [(key, value) for key, value in updates.items() if value is not None]
    if not pairs:
        raise SystemExit("provide at least one field to update")
    set_sql = ", ".join(f"{key} = ?" for key, _value in pairs)
    values = [value for _key, value in pairs]
    with db.session(db_path) as conn:
        row = db.get_execution_ticket(conn, args.ticket_id)
        if row is None:
            raise SystemExit(f"unknown ticket: {args.ticket_id}")
        conn.execute(
            f"UPDATE execution_tickets SET {set_sql}, updated_at = CURRENT_TIMESTAMP WHERE ticket_id = ?",
            [*values, args.ticket_id],
        )
        updated = db.get_execution_ticket(conn, args.ticket_id)
    return {"ticket": _decode_ticket(updated)}


def _run_tickets(args: argparse.Namespace) -> dict[str, Any]:
    if args.ticket_command == "list":
        return execution_board.run(_ns(args, command="list"))
    if args.ticket_command == "get":
        factory, db_path = paths(args)
        detail = execution_ticket_detail(factory, db_path, args.ticket_id)
        if detail is None:
            raise SystemExit(f"unknown ticket: {args.ticket_id}")
        return detail
    if args.ticket_command == "create":
        return execution_board.run(_ns(args, command="create"))
    if args.ticket_command == "block":
        return execution_board.run(_ns(args, command="block"))
    if args.ticket_command == "tick":
        return execution_board.run(_ns(args, command="tick"))
    if args.ticket_command == "sync":
        return execution_board.run(_ns(args, command="sync"))
    if args.ticket_command == "set":
        return _ticket_set(args)
    raise SystemExit(f"unknown tickets command: {args.ticket_command}")


def _run_goals(args: argparse.Namespace) -> dict[str, Any]:
    if args.goal_command == "set":
        return _ticket_set(_ns(args, ticket_id=args.ticket_id))
    _factory, db_path = paths(args)
    with db.session(db_path) as conn:
        tickets = [_decode_ticket(row) for row in db.list_execution_tickets(conn, status="all")]
    by_goal: dict[str, list[dict[str, Any]]] = {}
    for ticket in tickets:
        by_goal.setdefault(ticket.get("goal_id") or "unassigned", []).append(ticket)
    goals = [
        {
            "goal_id": goal_id,
            "count": len(items),
            "statuses": dict(Counter(item["status"] for item in items)),
            "tickets": [
                {
                    "ticket_id": item["ticket_id"],
                    "title": item["title"],
                    "status": item["status"],
                    "team_name": item["team_name"],
                    "priority": item["priority"],
                }
                for item in items
            ],
        }
        for goal_id, items in sorted(by_goal.items())
    ]
    return {"count": len(goals), "goals": goals}


def _run_watchdog(args: argparse.Namespace) -> dict[str, Any]:
    return orchestrator.run(
        _ns(
            args,
            loop=False,
            poll_seconds=30,
        )
    )


def _run_teams(args: argparse.Namespace) -> dict[str, Any]:
    if args.team_command == "list":
        return query_remote_teams.run(args)
    if args.team_command == "get":
        factory, db_path = paths(args)
        detail = team_detail(factory, db_path, args.team)
        if detail is None:
            raise SystemExit(f"unknown team: {args.team}")
        return detail
    raise SystemExit(f"unknown teams command: {args.team_command}")


def _run_resources(args: argparse.Namespace) -> dict[str, Any]:
    factory, db_path = paths(args)
    if args.resource_command == "list":
        return {"resources": dashboard(factory, db_path).get("resources", [])}
    if args.resource_command == "get":
        detail = resource_detail(factory, args.resource_id)
        if detail is None:
            raise SystemExit(f"unknown resource: {args.resource_id}")
        return detail
    raise SystemExit(f"unknown resources command: {args.resource_command}")


def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "dashboard":
        return _run_dashboard(args)
    if args.command == "status":
        return _run_status(args)
    if args.command == "logs":
        return _run_logs(args)
    if args.command == "teams":
        return _run_teams(args)
    if args.command == "board":
        return query_work_board.run(args)
    if args.command == "requests":
        return _run_requests(args)
    if args.command == "approve":
        return _resolve_request(
            _ns(args, request_id=args.request_id),
            response={"action": "approve", "approved": True, "comment": args.comment, "source": "harness-control"},
            action="approve",
            status="supplied",
        )
    if args.command == "alerts":
        return _run_alerts(args)
    if args.command == "assignments":
        return _run_assignments(args)
    if args.command == "tickets":
        return _run_tickets(args)
    if args.command == "goals":
        return _run_goals(args)
    if args.command == "watchdog":
        return _run_watchdog(args)
    if args.command == "resources":
        return _run_resources(args)
    if args.command == "graph":
        factory, db_path = paths(args)
        return graph(factory, db_path)
    if args.command == "schedules":
        return schedules()
    if args.command == "config":
        factory, _db_path = paths(args)
        return hub_config(factory)
    raise SystemExit(f"unknown command: {args.command}")


def _remote_argv(raw_argv: list[str]) -> list[str]:
    cleaned: list[str] = []
    skip_next = False
    for item in raw_argv:
        if skip_next:
            skip_next = False
            continue
        if item in {"--url", "--token"}:
            skip_next = True
            continue
        if item.startswith("--url=") or item.startswith("--token="):
            continue
        cleaned.append(item)
    return cleaned


def run_remote(args: argparse.Namespace, raw_argv: list[str]) -> dict[str, Any]:
    if not args.token:
        raise SystemExit("remote control requires --token or HARNESS_CONTROL_TOKEN")
    endpoint = args.url.rstrip("/") + "/api/control"
    body = json.dumps({"argv": _remote_argv(raw_argv)}, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {args.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise SystemExit(f"remote control failed with HTTP {error.code}: {detail}") from error
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise SystemExit(f"remote control failed: {error}") from error
    if not isinstance(payload, dict):
        raise SystemExit("remote control returned a non-object response")
    if payload.get("error"):
        raise SystemExit(f"remote control error: {payload['error']}")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise SystemExit("remote control response missing object result")
    return result


def _print_text(args: argparse.Namespace, result: dict[str, Any]) -> None:
    if args.command == "dashboard":
        counts = result.get("counts", {})
        print(
            "teams={teams} active_assignments={active_assignments} waiting_on_user={waiting_on_user} "
            "open_alerts={open_alerts} active_tickets={active_execution_tickets}".format(**counts)
        )
        if getattr(args, "full", False):
            print(json.dumps(result, indent=2, sort_keys=True))
        return
    if args.command == "status":
        summary = result["summary"]
        print(
            "teams={teams} stale={stale_teams} alerts={open_alerts} waiting_on_user={waiting_on_user}".format(
                **summary
            )
        )
        print(f"assignments={summary['assignments']}")
        print(f"execution_tickets={summary['execution_tickets']}")
        for request in result["user_requests"][:10]:
            print(f"request {request['request_id']} {request['kind']} {request['team_name']}: {request['title']}")
        for alert in result["open_alerts"][:10]:
            print(f"alert {alert['alert_id']} {alert['severity']} {alert['kind']}: {alert['title']}")
        return
    if args.command == "logs":
        for event in result["events"]:
            print(f"{event['ts']} {event['team_name']} {event['assignment_id'] or '-'} {event['kind']} {event['state'] or ''}")
        if result.get("journal_tail"):
            print("\n--- journal tail ---")
            print(result["journal_tail"])
        return
    if args.command == "teams":
        if args.team_command == "list":
            for team in result["teams"]:
                print(
                    f"{team['team_name']}: {team['substrate_status']} active={team['active_assignments'] or 0} "
                    f"requests={team['open_user_requests'] or 0} last_event={team['last_event_at'] or 'never'}"
                )
        else:
            print(json.dumps(result, indent=2, sort_keys=True))
        return
    if args.command == "board":
        print(f"assignments={result['counts']}")
        print(f"execution_tickets={result['execution_ticket_counts']}")
        return
    if args.command == "requests":
        if args.request_command == "list":
            for request in result["requests"]:
                print(f"{request['request_id']}: {request['status']} {request['kind']} {request['team_name']} {request['title']}")
        else:
            print(json.dumps(result, indent=2, sort_keys=True))
        return
    if args.command == "alerts" and args.alert_command == "list":
        for alert in result["alerts"]:
            print(f"{alert['alert_id']}: {alert['severity']} {alert['kind']} {alert['title']}")
        return
    if args.command == "assignments" and args.assignment_command == "list":
        for assignment in result["assignments"]:
            print(f"{assignment['assignment_id']}: {assignment['status']} {assignment['team_name']}")
        return
    if args.command == "tickets" and args.ticket_command == "list":
        for ticket in result["tickets"]:
            print(f"{ticket['ticket_id']}: {ticket['status']} {ticket['mode']} {ticket['team_name']} {ticket['title']}")
        return
    if args.command == "resources" and args.resource_command == "list":
        for resource in result["resources"]:
            print(f"{resource.get('id')}: {resource.get('state')} {resource.get('kind')} {resource.get('title')}")
        return
    if args.command == "goals" and args.goal_command == "list":
        for goal in result["goals"]:
            print(f"{goal['goal_id']}: {goal['count']} {goal['statuses']}")
        return
    print(json.dumps(result, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> None:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(raw_argv)
    result = run_remote(args, raw_argv) if args.url else run(args)
    if getattr(args, "json", False):
        print(json.dumps(result, indent=2, sort_keys=True))
        return
    _print_text(args, result)


if __name__ == "__main__":
    main()
