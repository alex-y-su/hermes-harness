from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from harness import db


TERMINAL_STATUSES = {"completed", "failed", "canceled", "archived"}
REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_FILENAMES = {
    "AGENTS.md",
    "SOUL.md",
    "TEAM_SOUL.md",
    "README.md",
    "PROTOCOL.md",
    "HARD_RULES.md",
    "STANDING_APPROVALS.md",
    "BLACKBOARD.md",
    "PRIORITIZE.md",
    "QUIET_HOURS.md",
    "status.json",
}
DOC_FALLBACKS = [
    REPO_ROOT / "bus_template" / "README.md",
    REPO_ROOT / "bus_template" / "BLACKBOARD.md",
    REPO_ROOT / "bus_template" / "PRIORITIZE.md",
    REPO_ROOT / "bus_template" / "QUIET_HOURS.md",
    REPO_ROOT / "docs" / "team" / "00_OVERVIEW.md",
    REPO_ROOT / "docs" / "team" / "03_top_tier_souls.md",
    REPO_ROOT / "docs" / "team" / "06_protocol.md",
    REPO_ROOT / "docs" / "team" / "HARD_RULES.md",
    REPO_ROOT / "docs" / "team" / "STANDING_APPROVALS.md",
]


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"_error": "invalid json"}


def _read_text(path: Path, *, max_chars: int = 120_000) -> str:
    if not path.exists() or not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) > max_chars:
        return text[-max_chars:]
    return text


def _rel(factory: Path, path: str | None) -> str | None:
    if not path:
        return None
    try:
        return str(Path(path).resolve().relative_to(factory.resolve()))
    except ValueError:
        return path


def _decode_user_request(row: Any) -> dict[str, Any]:
    data = dict(row)
    data["required_fields"] = json.loads(data.pop("required_fields_json") or "[]")
    data["response"] = json.loads(data.pop("response_json") or "null")
    data["metadata"] = json.loads(data.get("metadata") or "{}")
    return data


def _decode_resume(row: Any) -> dict[str, Any]:
    data = dict(row)
    data["response"] = json.loads(data.pop("response_json") or "null")
    data["metadata"] = json.loads(data.get("metadata") or "{}")
    return data


def _decode_alert(row: Any) -> dict[str, Any]:
    data = dict(row)
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


def _team_dirs(factory: Path) -> list[Path]:
    teams_dir = factory / "teams"
    if not teams_dir.exists():
        return []
    return sorted([path for path in teams_dir.iterdir() if path.is_dir()], key=lambda p: p.name)


def list_teams(factory: Path, db_path: Path) -> list[dict[str, Any]]:
    handles: dict[str, dict[str, Any]] = {}
    with db.session(db_path) as conn:
        for row in conn.execute("SELECT * FROM substrate_handles ORDER BY team_name"):
            handles[row["team_name"]] = dict(row)
        assignment_counts = {
            row["team_name"]: dict(row)
            for row in conn.execute(
                """
                SELECT
                  team_name,
                  COUNT(*) AS total_assignments,
                  COUNT(CASE WHEN status NOT IN ('completed','failed','canceled','archived') THEN 1 END) AS active_assignments,
                  COUNT(CASE WHEN status = 'retrying' THEN 1 END) AS retrying_assignments,
                  COUNT(CASE WHEN status = 'stale' THEN 1 END) AS stale_assignments
                FROM team_assignments
                GROUP BY team_name
                """
            )
        }
        request_counts = {
            row["team_name"]: dict(row)
            for row in conn.execute(
                """
                SELECT
                  team_name,
                  COUNT(CASE WHEN status = 'open' THEN 1 END) AS open_user_requests,
                  COUNT(*) AS total_user_requests
                FROM approval_requests
                GROUP BY team_name
                """
            )
        }
        last_events = {
            row["team_name"]: row["last_event_at"]
            for row in conn.execute("SELECT team_name, MAX(ts) AS last_event_at FROM team_events GROUP BY team_name")
        }

    names = set(handles)
    names.update(path.name for path in _team_dirs(factory))
    teams: list[dict[str, Any]] = []
    for name in sorted(names):
        team_dir = factory / "teams" / name
        status = _read_json(team_dir / "status.json")
        counts = assignment_counts.get(name, {})
        user_request_counts = request_counts.get(name, {})
        handle = handles.get(name, {})
        teams.append(
            {
                "team_name": name,
                "state": status.get("state") or handle.get("status") or "unknown",
                "template": status.get("template"),
                "substrate": status.get("substrate") or handle.get("substrate"),
                "hub": status.get("hub") or status.get("parent_team"),
                "role": status.get("role") or ("subteam" if status.get("hub") else "team"),
                "updated_at": status.get("updated_at"),
                "last_event_at": last_events.get(name),
                "active_assignments": counts.get("active_assignments", 0),
                "retrying_assignments": counts.get("retrying_assignments", 0),
                "stale_assignments": counts.get("stale_assignments", 0),
                "total_assignments": counts.get("total_assignments", 0),
                "open_user_requests": user_request_counts.get("open_user_requests", 0),
                "total_user_requests": user_request_counts.get("total_user_requests", 0),
                "path": str(team_dir),
                "exists": team_dir.exists(),
            }
        )
    return teams


def dashboard(factory: Path, db_path: Path) -> dict[str, Any]:
    teams = list_teams(factory, db_path)
    with db.session(db_path) as conn:
        recent_events = [
            dict(row)
            for row in conn.execute(
                """
                SELECT event_id, team_name, assignment_id, kind, state, ts, payload_path
                FROM team_events
                ORDER BY ts DESC, event_id DESC
                LIMIT 50
                """
            )
        ]
        assignments = [
            dict(row)
            for row in conn.execute(
                """
                SELECT
                  assignment_id, team_name, order_id, status, status_reason,
                  blocked_by, retry_count, max_retries, next_retry_at,
                  last_heartbeat_at, last_error, lease_owner, lease_expires_at,
                  created_at, dispatched_at, terminal_at
                FROM team_assignments
                ORDER BY created_at DESC
                LIMIT 100
                """
            )
        ]
        user_requests = [
            _decode_user_request(row)
            for row in conn.execute(
                """
                SELECT *
                FROM approval_requests
                WHERE status IN ('open', 'supplied', 'resuming')
                ORDER BY created_at DESC, request_id DESC
                LIMIT 100
                """
            )
        ]
        alerts = [
            _decode_alert(row)
            for row in conn.execute(
                """
                SELECT *
                FROM operator_alerts
                WHERE status = 'open'
                ORDER BY created_at DESC, alert_id DESC
                LIMIT 100
                """
            )
        ]
        execution_tickets = [
            _decode_ticket(row)
            for row in conn.execute(
                """
                SELECT *
                FROM execution_tickets
                ORDER BY priority ASC, created_at DESC
                LIMIT 100
                """
            )
        ]
    hubs = sorted({team["hub"] for team in teams if team.get("hub")})
    active = sum(int(team.get("active_assignments") or 0) for team in teams)
    waiting = sum(1 for request in user_requests if request["status"] == "open")
    active_tickets = sum(1 for ticket in execution_tickets if ticket["status"] in {"ready", "queued", "working"})
    blocked_tickets = sum(1 for ticket in execution_tickets if ticket["status"] == "blocked")
    retrying = sum(int(team.get("retrying_assignments") or 0) for team in teams)
    stale = sum(int(team.get("stale_assignments") or 0) for team in teams)
    alert_count = len(alerts)
    return {
        "factory": str(factory),
        "teams": teams,
        "hubs": hubs,
        "counts": {
            "teams": len(teams),
            "hubs": len(hubs),
            "active_assignments": active,
            "active_execution_tickets": active_tickets,
            "blocked_execution_tickets": blocked_tickets,
            "waiting_on_user": waiting,
            "retrying_assignments": retrying,
            "stale_assignments": stale,
            "open_alerts": alert_count,
        },
        "recent_events": recent_events,
        "assignments": assignments,
        "user_requests": user_requests,
        "alerts": alerts,
        "execution_tickets": execution_tickets,
    }


def hub_config(factory: Path) -> dict[str, Any]:
    live_files: list[dict[str, Any]] = []
    if factory.exists():
        for path in sorted(factory.iterdir(), key=lambda item: item.name):
            if not path.is_file() or path.name not in CONFIG_FILENAMES:
                continue
            live_files.append(
                {
                    "name": path.name,
                    "source": "factory",
                    "path": str(path),
                    "body": _read_text(path),
                }
            )

    fallback_files = [
        {
            "name": str(path.relative_to(REPO_ROOT)),
            "source": "template",
            "path": str(path),
            "body": _read_text(path),
        }
        for path in DOC_FALLBACKS
        if path.exists()
    ]
    return {
        "factory": str(factory),
        "live": live_files,
        "fallback": fallback_files,
        "using_fallback": not live_files,
    }


def team_detail(factory: Path, db_path: Path, team_name: str) -> dict[str, Any] | None:
    teams = {team["team_name"]: team for team in list_teams(factory, db_path)}
    if team_name not in teams:
        return None
    team_dir = factory / "teams" / team_name
    with db.session(db_path) as conn:
        assignments = [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM team_assignments
                WHERE team_name = ?
                ORDER BY created_at DESC
                LIMIT 100
                """,
                (team_name,),
            )
        ]
        events = [
            dict(row)
            for row in conn.execute(
                """
                SELECT event_id, assignment_id, task_id, sequence, source, kind, state, ts, payload_path, metadata
                FROM team_events
                WHERE team_name = ?
                ORDER BY ts DESC, event_id DESC
                LIMIT 100
                """,
                (team_name,),
            )
        ]
        user_requests = [
            _decode_user_request(row)
            for row in conn.execute(
                """
                SELECT *
                FROM approval_requests
                WHERE team_name = ?
                ORDER BY created_at DESC, request_id DESC
                LIMIT 100
                """,
                (team_name,),
            )
        ]
        alerts = [
            _decode_alert(row)
            for row in conn.execute(
                """
                SELECT *
                FROM operator_alerts
                WHERE team_name = ? AND status = 'open'
                ORDER BY created_at DESC, alert_id DESC
                LIMIT 100
                """,
                (team_name,),
            )
        ]
    outbox_dir = team_dir / "outbox"
    outbox = []
    if outbox_dir.exists():
        outbox = [
            {"name": path.name, "path": str(path), "relative_path": str(path.relative_to(team_dir))}
            for path in sorted(outbox_dir.rglob("*"))
            if path.is_file()
        ][:100]
    return {
        **teams[team_name],
        "status": _read_json(team_dir / "status.json"),
        "brief": _read_text(team_dir / "brief.md"),
        "criteria": _read_text(team_dir / "criteria.md"),
        "journal": _read_text(team_dir / "journal.md"),
        "assignments": assignments,
        "events": events,
        "user_requests": user_requests,
        "alerts": alerts,
        "outbox": outbox,
    }


def assignment_detail(factory: Path, db_path: Path, assignment_id: str) -> dict[str, Any] | None:
    with db.session(db_path) as conn:
        row = conn.execute("SELECT * FROM team_assignments WHERE assignment_id = ?", (assignment_id,)).fetchone()
        if not row:
            return None
        assignment = dict(row)
        events = [
            dict(event)
            for event in conn.execute(
                """
                SELECT event_id, team_name, kind, state, ts, payload_path, metadata
                FROM team_events
                WHERE assignment_id = ?
                ORDER BY ts DESC, event_id DESC
                """,
                (assignment_id,),
            )
        ]
        user_requests = [
            _decode_user_request(request)
            for request in conn.execute(
                """
                SELECT *
                FROM approval_requests
                WHERE assignment_id = ?
                ORDER BY created_at DESC, request_id DESC
                """,
                (assignment_id,),
            )
        ]
        resumes = [
            _decode_resume(resume)
            for resume in conn.execute(
                """
                SELECT *
                FROM assignment_resumes
                WHERE parent_assignment_id = ? OR continuation_assignment_id = ?
                ORDER BY created_at DESC, resume_id DESC
                """,
                (assignment_id, assignment_id),
            )
        ]
        sandbox = conn.execute("SELECT * FROM assignment_sandboxes WHERE assignment_id = ?", (assignment_id,)).fetchone()
        alerts = [
            _decode_alert(alert)
            for alert in conn.execute(
                """
                SELECT *
                FROM operator_alerts
                WHERE assignment_id = ? AND status = 'open'
                ORDER BY created_at DESC, alert_id DESC
                """,
                (assignment_id,),
            )
        ]
    payload_path = assignment.get("completed_path") or assignment.get("inbox_path")
    return {
        **assignment,
        "relative_payload_path": _rel(factory, payload_path),
        "body": _read_text(Path(payload_path)) if payload_path else "",
        "events": events,
        "user_requests": user_requests,
        "resumes": resumes,
        "sandbox": dict(sandbox) if sandbox else None,
        "alerts": alerts,
    }


def graph(factory: Path, db_path: Path) -> dict[str, Any]:
    teams = list_teams(factory, db_path)
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, str]] = []
    for team in teams:
        hub = team.get("hub")
        if hub:
            hub_id = f"hub:{hub}"
            nodes.setdefault(hub_id, {"id": hub_id, "label": hub, "type": "hub"})
            edges.append({"source": hub_id, "target": f"team:{team['team_name']}", "type": "contains"})
        team_id = f"team:{team['team_name']}"
        nodes[team_id] = {
            "id": team_id,
            "label": team["team_name"],
            "type": "team",
            "state": team["state"],
            "active_assignments": team["active_assignments"],
        }
    with db.session(db_path) as conn:
        for row in conn.execute(
            """
            SELECT assignment_id, team_name, status
            FROM team_assignments
            ORDER BY created_at DESC
            LIMIT 300
            """
        ):
            assignment_id = f"assignment:{row['assignment_id']}"
            nodes[assignment_id] = {
                "id": assignment_id,
                "label": row["assignment_id"],
                "type": "assignment",
                "state": row["status"],
            }
            edges.append({"source": f"team:{row['team_name']}", "target": assignment_id, "type": "owns"})
    return {"nodes": list(nodes.values()), "edges": edges}
