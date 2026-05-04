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
                  COUNT(CASE WHEN status NOT IN ('completed','failed','canceled','archived') THEN 1 END) AS active_assignments
                FROM team_assignments
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
                "total_assignments": counts.get("total_assignments", 0),
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
                SELECT assignment_id, team_name, order_id, status, created_at, dispatched_at, terminal_at
                FROM team_assignments
                ORDER BY created_at DESC
                LIMIT 100
                """
            )
        ]
    hubs = sorted({team["hub"] for team in teams if team.get("hub")})
    active = sum(int(team.get("active_assignments") or 0) for team in teams)
    return {
        "factory": str(factory),
        "teams": teams,
        "hubs": hubs,
        "counts": {
            "teams": len(teams),
            "hubs": len(hubs),
            "active_assignments": active,
        },
        "recent_events": recent_events,
        "assignments": assignments,
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
    payload_path = assignment.get("completed_path") or assignment.get("inbox_path")
    return {
        **assignment,
        "relative_payload_path": _rel(factory, payload_path),
        "body": _read_text(Path(payload_path)) if payload_path else "",
        "events": events,
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
