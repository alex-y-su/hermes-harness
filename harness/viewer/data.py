from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from harness import db
from harness.resources import get_resource, list_resources, resource_refs_from_metadata, resources_by_id


TERMINAL_STATUSES = {"completed", "failed", "canceled", "archived"}
TERMINAL_SANDBOX_STATUSES = {"completed", "failed", "canceled", "archived", "paused_archived"}
E2B_PROVIDER_CACHE_TTL_SECONDS = 10
_E2B_PROVIDER_CACHE: dict[str, Any] = {"expires_at": 0.0, "summary": None}
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
    REPO_ROOT / "docs" / "boss-team-contract.md",
    REPO_ROOT / "docs" / "root-team-config-organization.md",
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


def _decode_handle(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        data = json.loads(str(raw))
    except json.JSONDecodeError:
        return {"handle": str(raw), "metadata": {}}
    if isinstance(data, dict):
        return data
    return {"handle": str(raw), "metadata": {}}


def _is_real_e2b_handle(raw: Any) -> bool:
    data = _decode_handle(raw)
    handle = str(data.get("handle") or "")
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    if metadata.get("dry_run"):
        return False
    if handle.startswith(("dry-run-e2b://", "e2b-team://")):
        return False
    return bool(handle)


def _e2b_machine_summary(conn: Any) -> dict[str, Any]:
    rows = [
        dict(row)
        for row in conn.execute(
            """
            SELECT assignment_id, team_name, status, handle, created_at, booted_at,
                   last_heartbeat_at, blocked_since, archived_at
            FROM assignment_sandboxes
            WHERE substrate = 'e2b'
            ORDER BY created_at DESC, assignment_id DESC
            """
        )
    ]
    real_rows = [row for row in rows if _is_real_e2b_handle(row.get("handle"))]
    active_rows = [
        row
        for row in real_rows
        if not row.get("archived_at")
        and str(row.get("status") or "") not in TERMINAL_SANDBOX_STATUSES
    ]
    provider = _e2b_provider_summary({str(_decode_handle(row.get("handle")).get("handle")) for row in real_rows})
    provider_active = provider.get("running") if provider.get("available") else None
    return {
        "active": int(provider_active if provider_active is not None else len(active_rows)),
        "source": "provider" if provider.get("available") else "database",
        "provider": provider,
        "database_active": len(active_rows),
        "blocked": sum(1 for row in active_rows if row.get("status") == "blocked"),
        "teams": sorted({row["team_name"] for row in active_rows if row.get("team_name")}),
        "assignments": [
            {
                "assignment_id": row.get("assignment_id"),
                "team_name": row.get("team_name"),
                "status": row.get("status"),
                "booted_at": row.get("booted_at"),
                "last_heartbeat_at": row.get("last_heartbeat_at"),
                "blocked_since": row.get("blocked_since"),
            }
            for row in active_rows
        ],
        "tracked": len(real_rows),
    }


def _e2b_provider_summary(tracked_sandbox_ids: set[str]) -> dict[str, Any]:
    now = time.monotonic()
    cached = _E2B_PROVIDER_CACHE.get("summary")
    if cached is not None and now < float(_E2B_PROVIDER_CACHE.get("expires_at") or 0):
        return dict(cached)

    api_key = os.getenv("E2B_API_KEY") or os.getenv("E2B_ACCESS_TOKEN")
    if not api_key:
        summary = {"available": False, "error": "missing-api-key", "running": None, "tracked_running": None}
        _E2B_PROVIDER_CACHE.update({"expires_at": now + E2B_PROVIDER_CACHE_TTL_SECONDS, "summary": summary})
        return dict(summary)

    try:
        from e2b import Sandbox, SandboxQuery, SandboxState  # type: ignore

        paginator = Sandbox.list(query=SandboxQuery(state=[SandboxState.RUNNING]), limit=100, api_key=api_key)
        running_ids: set[str] = set()
        while paginator.has_next:
            for item in paginator.next_items():
                sandbox_id = getattr(item, "sandbox_id", None)
                if sandbox_id:
                    running_ids.add(str(sandbox_id))
    except Exception as exc:
        summary = {
            "available": False,
            "error": f"{type(exc).__name__}: {str(exc)[:240]}",
            "running": None,
            "tracked_running": None,
        }
        _E2B_PROVIDER_CACHE.update({"expires_at": now + E2B_PROVIDER_CACHE_TTL_SECONDS, "summary": summary})
        return dict(summary)

    tracked_running = sorted(running_ids & tracked_sandbox_ids)
    summary = {
        "available": True,
        "error": None,
        "running": len(running_ids),
        "tracked_running": len(tracked_running),
        "tracked_running_ids": tracked_running[:200],
        "refreshed_at": datetime.now(UTC).isoformat(),
    }
    _E2B_PROVIDER_CACHE.update({"expires_at": now + E2B_PROVIDER_CACHE_TTL_SECONDS, "summary": summary})
    return dict(summary)


def _safe_schedule_error(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    if len(text) > 500:
        return text[:497] + "..."
    return text


def _decode_schedule_job(profile: str, job: dict[str, Any]) -> dict[str, Any]:
    repeat = job.get("repeat") if isinstance(job.get("repeat"), dict) else {}
    return {
        "profile": profile,
        "job_id": job.get("id"),
        "name": job.get("name") or job.get("id"),
        "enabled": bool(job.get("enabled", True)),
        "state": job.get("state") or ("scheduled" if job.get("enabled", True) else "paused"),
        "schedule": job.get("schedule_display") or (job.get("schedule") or {}).get("display") or "",
        "next_run_at": job.get("next_run_at"),
        "last_run_at": job.get("last_run_at"),
        "last_status": job.get("last_status"),
        "last_error": _safe_schedule_error(job.get("last_error") or job.get("last_delivery_error")),
        "script": job.get("script"),
        "no_agent": bool(job.get("no_agent", False)),
        "deliver": job.get("deliver"),
        "workdir": job.get("workdir"),
        "repeat_times": repeat.get("times"),
        "repeat_completed": repeat.get("completed"),
        "created_at": job.get("created_at"),
        "paused_at": job.get("paused_at"),
        "paused_reason": job.get("paused_reason"),
    }


def schedules(hermes_home: Path | None = None) -> dict[str, Any]:
    home = hermes_home or Path(os.getenv("HERMES_HOME", "~/.hermes")).expanduser()
    stores: list[tuple[str, Path]] = []
    root_store = home / "cron" / "jobs.json"
    if root_store.exists():
        stores.append(("default", root_store))
    profiles_dir = home / "profiles"
    if profiles_dir.exists():
        stores.extend(
            (profile_dir.name, profile_dir / "cron" / "jobs.json")
            for profile_dir in sorted(profiles_dir.iterdir(), key=lambda path: path.name)
            if profile_dir.is_dir() and (profile_dir / "cron" / "jobs.json").exists()
        )

    jobs: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    updated_at: dict[str, Any] = {}
    for profile, path in stores:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            errors.append({"profile": profile, "path": str(path), "error": str(error)})
            continue
        if isinstance(payload, dict):
            updated_at[profile] = payload.get("updated_at")
            raw_jobs = payload.get("jobs") or []
        elif isinstance(payload, list):
            raw_jobs = payload
        else:
            errors.append({"profile": profile, "path": str(path), "error": "unsupported jobs.json shape"})
            continue
        for job in raw_jobs:
            if isinstance(job, dict):
                jobs.append(_decode_schedule_job(profile, job))

    jobs.sort(key=lambda job: (not job["enabled"], job.get("next_run_at") or "9999", job["profile"], job.get("name") or ""))
    return {
        "hermes_home": str(home),
        "stores": [{"profile": profile, "path": str(path)} for profile, path in stores],
        "updated_at": updated_at,
        "errors": errors,
        "counts": {
            "jobs": len(jobs),
            "active": sum(1 for job in jobs if job["enabled"]),
            "paused": sum(1 for job in jobs if not job["enabled"] or job["state"] == "paused"),
            "last_failed": sum(1 for job in jobs if job.get("last_status") not in (None, "ok")),
        },
        "jobs": jobs,
    }


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
    resources = list_resources(factory)
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
        e2b_machines = _e2b_machine_summary(conn)
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
        "resources": resources,
        "e2b_machines": e2b_machines,
        "counts": {
            "teams": len(teams),
            "hubs": len(hubs),
            "resources": len(resources),
            "resources_needing_access": sum(
                1 for resource in resources if str(resource.get("state") or "") in {"missing", "needs-access", "needs-setup", "blocked"}
            ),
            "active_e2b_machines": e2b_machines["active"],
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


def execution_ticket_detail(factory: Path, db_path: Path, ticket_id: str) -> dict[str, Any] | None:
    resource_index = resources_by_id(factory)
    with db.session(db_path) as conn:
        row = conn.execute("SELECT * FROM execution_tickets WHERE ticket_id = ?", (ticket_id,)).fetchone()
        if not row:
            return None
        ticket = _decode_ticket(row)
        assignment = None
        if ticket.get("assignment_id"):
            assignment_row = conn.execute(
                "SELECT * FROM team_assignments WHERE assignment_id = ?",
                (ticket["assignment_id"],),
            ).fetchone()
            assignment = dict(assignment_row) if assignment_row else None
        user_requests = [
            _decode_user_request(request)
            for request in conn.execute(
                """
                SELECT *
                FROM approval_requests
                WHERE request_id = ?
                   OR assignment_id = ?
                   OR assignment_id = ?
                ORDER BY created_at DESC, request_id DESC
                """,
                (ticket.get("approval_request_id"), ticket_id, ticket.get("assignment_id")),
            )
        ]
        child_tickets = [
            _decode_ticket(child)
            for child in conn.execute(
                """
                SELECT *
                FROM execution_tickets
                WHERE parent_ticket_id = ?
                ORDER BY priority ASC, created_at DESC
                """,
                (ticket_id,),
            )
        ]
    return {
        **ticket,
        "assignment": assignment,
        "user_requests": user_requests,
        "child_tickets": child_tickets,
        "resources": _linked_resources(resource_index, resource_refs_from_metadata(ticket.get("metadata"))),
    }


def user_request_detail(factory: Path, db_path: Path, request_id: str) -> dict[str, Any] | None:
    resource_index = resources_by_id(factory)
    with db.session(db_path) as conn:
        row = conn.execute("SELECT * FROM approval_requests WHERE request_id = ?", (request_id,)).fetchone()
        if not row:
            return None
        request = _decode_user_request(row)
        assignment_row = conn.execute(
            "SELECT * FROM team_assignments WHERE assignment_id = ?",
            (request["assignment_id"],),
        ).fetchone()
        ticket_row = conn.execute(
            """
            SELECT *
            FROM execution_tickets
            WHERE approval_request_id = ?
               OR ticket_id = ?
               OR assignment_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (request_id, request["assignment_id"], request["assignment_id"]),
        ).fetchone()
    escalation_path = request.get("escalation_path")
    return {
        **request,
        "assignment": dict(assignment_row) if assignment_row else None,
        "ticket": _decode_ticket(ticket_row) if ticket_row else None,
        "decision": _decision_packet(request, _decode_ticket(ticket_row) if ticket_row else None),
        "resources": _linked_resources(
            resource_index,
            [
                *resource_refs_from_metadata(request.get("metadata")),
                *resource_refs_from_metadata(_decode_ticket(ticket_row).get("metadata") if ticket_row else {}),
            ],
        ),
        "escalation_body": _read_text(Path(escalation_path)) if escalation_path else "",
        "relative_escalation_path": _rel(factory, escalation_path),
    }


def resource_detail(factory: Path, resource_id: str) -> dict[str, Any] | None:
    return get_resource(factory, resource_id)


def _linked_resources(resource_index: dict[str, dict[str, Any]], refs: list[str]) -> list[dict[str, Any]]:
    linked = []
    seen = set()
    for ref in refs:
        if ref in seen:
            continue
        seen.add(ref)
        linked.append(resource_index.get(ref) or {"id": ref, "title": ref, "state": "unknown", "missing": True})
    return linked


def _decision_packet(request: dict[str, Any], ticket: dict[str, Any] | None) -> dict[str, Any]:
    metadata = request.get("metadata") if isinstance(request.get("metadata"), dict) else {}
    ticket_metadata = ticket.get("metadata") if ticket and isinstance(ticket.get("metadata"), dict) else {}
    details = (
        metadata.get("approval")
        or metadata.get("approval_details")
        or metadata.get("decision")
        or ticket_metadata.get("approval")
        or ticket_metadata.get("approval_details")
        or {}
    )
    if not isinstance(details, dict):
        details = {}
    return {
        "requested_action": details.get("requested_action") or details.get("action") or request.get("title"),
        "why": details.get("why") or details.get("reason") or details.get("business_reason"),
        "target": details.get("target") or details.get("target_resource") or details.get("resource"),
        "artifact": details.get("artifact") or details.get("artifact_path") or details.get("diff") or details.get("content_path"),
        "expected_impact": details.get("expected_impact") or details.get("impact"),
        "blast_radius": details.get("blast_radius"),
        "cost": details.get("cost") or details.get("spend"),
        "rollback": details.get("rollback") or details.get("fallback") or details.get("fallback_plan"),
        "preconditions": details.get("preconditions") or details.get("checks") or details.get("prerequisites") or [],
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
