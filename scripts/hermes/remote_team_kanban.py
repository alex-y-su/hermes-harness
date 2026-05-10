"""Remote-team Kanban dispatcher hook for Hermes Harness.

Installed into ``$HERMES_INSTALL_DIR/hermes_cli`` by
``scripts/hermes/install-remote-kanban.sh``. The hook keeps Hermes' normal
Kanban surface but routes ``team:<name>`` assignees through the
``hermes-harness-remote-team`` protocol adapter when a remote-team registry is
configured.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any

from hermes_harness.remote_team.quality import enforce_response_quality


TEAM_PREFIX = "team:"
DEFAULT_ACTIVE_CYCLE_TTL_SECONDS = 7 * 24 * 60 * 60


def dispatch_team_task(
    *,
    kb: Any,
    conn: Any,
    task_id: str,
    assignee: str,
    board: str | None = None,
) -> dict[str, Any]:
    team = _team_name(assignee)
    if not team:
        return {"ok": False, "handled": False, "error": "invalid_team_assignee"}

    registry = _registry_path(kb)
    if not registry.exists() or not _registry_has_team(registry, team):
        return {
            "ok": False,
            "handled": False,
            "error": f"remote_team_not_registered:{team}",
        }

    task = kb.get_task(conn, task_id)
    if task is None:
        return {"ok": False, "handled": True, "error": "task_not_found"}
    if task.status != "ready":
        return {"ok": False, "handled": True, "error": f"task_not_ready:{task.status}"}

    claimed = kb.claim_task(conn, task_id)
    if claimed is None:
        return {"ok": False, "handled": True, "error": "claim_failed"}

    source_board = _source_board(kb, board)
    request = _request_from_task(claimed, team=team, source_board=source_board)
    response = _call_remote_team(team=team, registry=registry, request=request)
    summary = _summary(claimed.id, team, response)

    if not response.get("ok"):
        reason = response.get("message") or response.get("error") or "remote team call failed"
        ok = kb.block_task(conn, claimed.id, reason=str(reason))
        if ok:
            kb.add_comment(conn, claimed.id, "remote-team-kanban", json.dumps(response, sort_keys=True))
        return {
            "ok": bool(ok),
            "handled": True,
            "team": team,
            "remote_task_id": response.get("remote_task_id"),
            "status": "blocked",
        }

    response = enforce_response_quality(response, task_body=claimed.body or "")
    main_update = _main_update(response)
    action = str(main_update.get("action") or _default_action(response))
    result_payload = _result_payload(response)

    if action == "keep_running":
        ok = _record_running_report(kb, conn, claimed, response, result_payload, summary)
    elif action == "block":
        reason = main_update.get("reason") or response.get("status") or "remote team blocked"
        ok = kb.block_task(conn, claimed.id, reason=str(reason))
        if ok:
            kb.add_comment(conn, claimed.id, "remote-team-kanban", json.dumps(response, sort_keys=True))
    else:
        ok = kb.complete_task(
            conn,
            claimed.id,
            result=json.dumps(result_payload, sort_keys=True),
            summary=summary,
            metadata=_metadata(response),
        )
        if ok:
            kb.add_comment(conn, claimed.id, "remote-team-kanban", summary)

    return {
        "ok": bool(ok),
        "handled": True,
        "team": team,
        "remote_task_id": response.get("remote_task_id"),
        "status": main_update.get("status") or response.get("status"),
    }


def _record_running_report(
    kb: Any,
    conn: Any,
    task: Any,
    response: dict[str, Any],
    result_payload: dict[str, Any],
    summary: str,
) -> bool:
    result_json = json.dumps(result_payload, sort_keys=True)
    ttl = _active_cycle_ttl_seconds()
    lock = getattr(task, "claim_lock", None)
    if lock:
        kb.heartbeat_claim(conn, task.id, ttl_seconds=ttl, claimer=lock)
    now = _now()
    with kb.write_txn(conn):
        cur = conn.execute(
            """
            UPDATE tasks
               SET result = ?,
                   claim_expires = CASE
                       WHEN claim_lock IS NULL THEN claim_expires
                       ELSE ?
                   END
             WHERE id = ?
               AND status = 'running'
            """,
            (result_json, now + ttl, task.id),
        )
        if cur.rowcount != 1:
            return False
        run_id = getattr(task, "current_run_id", None)
        if run_id is not None:
            conn.execute(
                """
                UPDATE task_runs
                   SET summary = ?,
                       metadata = ?,
                       claim_expires = ?
                 WHERE id = ?
                   AND ended_at IS NULL
                """,
                (summary, json.dumps(_metadata(response), ensure_ascii=False), now + ttl, int(run_id)),
            )
        kb._append_event(
            conn,
            task.id,
            "remote_status_report",
            {
                "remote_team": response.get("remote_team"),
                "remote_task_id": response.get("remote_task_id"),
                "main_card_update": response.get("main_card_update"),
                "summary": summary,
            },
            run_id=run_id,
        )
    return True


def _request_from_task(task: Any, *, team: str, source_board: str) -> dict[str, Any]:
    return {
        "protocol_version": "1",
        "source_team": os.environ.get("HERMES_MAIN_TEAM_NAME", "main"),
        "target_team": team,
        "external_id": f"{source_board}:{task.id}",
        "source_board": source_board,
        "source_task_id": task.id,
        "task": {
            "title": task.title,
            "body": task.body or "",
            "tenant": task.tenant,
            "priority": task.priority,
        },
    }


def _call_remote_team(*, team: str, registry: Path, request: dict[str, Any]) -> dict[str, Any]:
    timeout = str(int(os.environ.get("HERMES_REMOTE_TEAM_TIMEOUT", "600")))
    cli = shlex.split(os.environ.get("HERMES_REMOTE_TEAM_CLI", "python3 -m hermes_harness.remote_team.cli"))
    command = [
        *cli,
        "call",
        "--team",
        team,
        "--operation",
        "submit_or_get",
        "--registry",
        str(registry),
        "--timeout",
        timeout,
        "--json",
    ]
    completed = subprocess.run(
        command,
        input=json.dumps(request),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=int(timeout) + 30,
    )
    if completed.returncode != 0:
        return {
            "ok": False,
            "protocol_version": "1",
            "error": "remote_team_command_failed",
            "message": completed.stdout,
        }
    try:
        response = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {
            "ok": False,
            "protocol_version": "1",
            "error": "remote_team_response_not_json",
            "message": completed.stdout,
        }
    if not isinstance(response, dict):
        return {
            "ok": False,
            "protocol_version": "1",
            "error": "remote_team_response_not_object",
            "message": str(response),
        }
    return response


def _main_update(response: dict[str, Any]) -> dict[str, Any]:
    direct = response.get("main_card_update")
    if isinstance(direct, dict):
        return direct
    result = response.get("result")
    if isinstance(result, dict) and isinstance(result.get("main_card_update"), dict):
        return result["main_card_update"]
    return {}


def _result_payload(response: dict[str, Any]) -> dict[str, Any]:
    result = response.get("result")
    if isinstance(result, dict):
        payload = dict(result)
    else:
        payload = {"remote_result": result}
    payload.setdefault("remote_team_protocol_response", response)
    return payload


def _metadata(response: dict[str, Any]) -> dict[str, Any]:
    return {
        "remote_team_protocol": True,
        "remote_team": response.get("remote_team"),
        "remote_board": response.get("board"),
        "remote_task_id": response.get("remote_task_id"),
        "external_id": response.get("external_id"),
        "remote_status": response.get("status"),
        "last_sync_at": response.get("updated_at"),
        "main_card_update": response.get("main_card_update"),
    }


def _summary(task_id: str, team: str, response: dict[str, Any]) -> str:
    main_update = _main_update(response)
    return (
        f"Remote team {team} synced {task_id}: "
        f"remote_task_id={response.get('remote_task_id')}, "
        f"remote_status={response.get('status')}, "
        f"main_action={main_update.get('action', 'unknown')}."
    )


def _default_action(response: dict[str, Any]) -> str:
    status = str(response.get("status") or "")
    if status in {"blocked", "failed", "fail"}:
        return "block"
    if status in {"completed", "done"}:
        return "complete"
    return "keep_running"


def _registry_path(kb: Any) -> Path:
    configured = os.environ.get("HERMES_REMOTE_TEAMS_CONFIG")
    if configured:
        return Path(configured)
    return kb.kanban_home() / "remote_teams.json"


def _registry_has_team(path: Path, team: str) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    teams = payload.get("remote_teams") if isinstance(payload, dict) else None
    return isinstance(teams, dict) and team in teams


def _team_name(assignee: str) -> str:
    return str(assignee)[len(TEAM_PREFIX) :].strip()


def _source_board(kb: Any, board: str | None) -> str:
    if board:
        return str(board)
    env_board = os.environ.get("HERMES_KANBAN_BOARD")
    if env_board:
        return env_board
    try:
        current = kb.get_current_board()
        if current:
            return str(current)
    except Exception:
        pass
    return "default"


def _active_cycle_ttl_seconds() -> int:
    raw = os.environ.get(
        "HERMES_REMOTE_TEAM_ACTIVE_TTL_SECONDS",
        str(DEFAULT_ACTIVE_CYCLE_TTL_SECONDS),
    )
    try:
        return max(60, int(raw))
    except ValueError:
        return DEFAULT_ACTIVE_CYCLE_TTL_SECONDS


def _now() -> int:
    return int(time.time())
