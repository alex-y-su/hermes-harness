"""Mock remote-team Kanban dispatcher hook for local Hermes testing.

This module is installed into ``$HERMES_INSTALL_DIR/hermes_cli`` by
``scripts/hermes/install-mock-kanban.sh``. It is intentionally shaped as a
Hermes Kanban dispatcher hook, not as a separate user-facing playground.

When the real dispatcher sees a ready task assigned to ``team:<name>``, the
patch calls ``dispatch_team_task(...)`` here instead of spawning
``hermes -p <profile>`` locally. The mock records a separate remote-team board
under the Hermes Kanban home and immediately returns a random success/failure
result with numeric metrics.
"""

from __future__ import annotations

import json
import os
import random
import re
import tempfile
import time
from pathlib import Path
from typing import Any


TEAM_PREFIX = "team:"
DEFAULT_SUCCESS_RATE = 0.75


def is_team_assignee(assignee: str | None) -> bool:
    return bool(assignee and str(assignee).startswith(TEAM_PREFIX))


def dispatch_team_task(
    *,
    kb: Any,
    conn: Any,
    task_id: str,
    assignee: str,
    board: str | None = None,
) -> dict[str, Any]:
    """Claim a ``team:<name>`` task and resolve it through a mock remote board.

    Returns a small structured result used by the patched dispatcher for its
    telemetry. All durable task state is written through Hermes Kanban's own
    DB helpers.
    """
    team = _team_name(assignee)
    if not team:
        return {"ok": False, "handled": False, "error": "invalid_team_assignee"}

    task = kb.get_task(conn, task_id)
    if task is None:
        return {"ok": False, "handled": False, "error": "task_not_found"}
    if task.status != "ready":
        return {"ok": False, "handled": False, "error": f"task_not_ready:{task.status}"}

    claimed = kb.claim_task(conn, task_id)
    if claimed is None:
        return {"ok": False, "handled": False, "error": "claim_failed"}

    source_board = _source_board(kb, board)
    remote_board = _load_remote_board(kb, team, source_board)
    remote_task = _remote_task(remote_board, claimed, team, source_board)
    remote_task["attempts"] = int(remote_task.get("attempts") or 0) + 1

    rng = _rng(claimed.id, remote_task["attempts"])
    success_rate = _success_rate()
    success = rng.random() < success_rate
    now = _now()

    if success:
        numbers = _numbers(rng)
        result = {
            "mock_remote": True,
            "team": team,
            "remote_task_id": remote_task["remote_task_id"],
            "external_id": claimed.id,
            "status": "success",
            "numbers": numbers,
        }
        summary = (
            f"Mock remote team {team} completed {claimed.id}: "
            f"success_score={numbers['success_score']}, "
            f"confidence={numbers['confidence']}, "
            f"estimated_impact={numbers['estimated_impact']}."
        )
        remote_task.update(
            {
                "status": "completed",
                "result": result,
                "completed_at": now,
                "updated_at": now,
            }
        )
        ok = kb.complete_task(
            conn,
            claimed.id,
            result=json.dumps(result, sort_keys=True),
            summary=summary,
            metadata=result,
        )
        if ok:
            kb.add_comment(conn, claimed.id, "mock-remote-kanban", summary)
    else:
        numbers = _numbers(rng)
        reason = (
            f"Mock remote team {team} failed {claimed.id}: "
            f"failure_score={numbers['failure_score']}, "
            f"confidence={numbers['confidence']}."
        )
        failure = {
            "mock_remote": True,
            "team": team,
            "remote_task_id": remote_task["remote_task_id"],
            "external_id": claimed.id,
            "status": "fail",
            "numbers": numbers,
            "reason": reason,
        }
        remote_task.update(
            {
                "status": "failed",
                "result": failure,
                "completed_at": now,
                "updated_at": now,
            }
        )
        ok = kb.block_task(conn, claimed.id, reason=reason)
        if ok:
            kb.add_comment(
                conn,
                claimed.id,
                "mock-remote-kanban",
                json.dumps(failure, sort_keys=True),
            )

    _save_remote_board(kb, team, source_board, remote_board)
    return {
        "ok": bool(ok),
        "handled": True,
        "team": team,
        "remote_task_id": remote_task["remote_task_id"],
        "status": remote_task["status"],
    }


def _remote_task(remote_board: dict[str, Any], task: Any, team: str, board: str) -> dict[str, Any]:
    existing = remote_board["tasks"].get(task.id)
    if existing is not None:
        return existing
    remote_task_id = f"{team}:mock:{remote_board['next_id']}"
    remote_board["next_id"] += 1
    remote_task = {
        "external_id": task.id,
        "remote_task_id": remote_task_id,
        "team": team,
        "source_board": board,
        "title": task.title,
        "body": task.body,
        "tenant": task.tenant,
        "priority": task.priority,
        "status": "running",
        "attempts": 0,
        "result": None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    remote_board["tasks"][task.id] = remote_task
    return remote_task


def _numbers(rng: random.Random) -> dict[str, Any]:
    return {
        "success_score": rng.randint(1, 100),
        "failure_score": rng.randint(1, 100),
        "confidence": round(rng.uniform(0.35, 0.97), 2),
        "estimated_impact": rng.randint(10, 1000),
        "estimated_cost": rng.randint(1, 50),
    }


def _load_remote_board(kb: Any, team: str, board: str) -> dict[str, Any]:
    path = _board_path(kb, team, board)
    if not path.exists():
        return {
            "team": team,
            "source_board": board,
            "next_id": 1,
            "tasks": {},
            "created_at": _now(),
            "updated_at": _now(),
        }
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"mock remote board must be a JSON object: {path}")
    return payload


def _save_remote_board(kb: Any, team: str, board: str, payload: dict[str, Any]) -> None:
    payload["updated_at"] = _now()
    path = _board_path(kb, team, board)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temp_path = Path(handle.name)
    temp_path.replace(path)


def _board_path(kb: Any, team: str, board: str) -> Path:
    safe_board = _slug(board)
    safe_team = _slug(team)
    return kb.kanban_home() / "mock-remote-kanban" / safe_board / safe_team / "board.json"


def _team_name(assignee: str) -> str:
    return _slug(str(assignee)[len(TEAM_PREFIX) :])


def _source_board(kb: Any, board: str | None) -> str:
    if board:
        return _slug(board)
    env_board = os.environ.get("HERMES_KANBAN_BOARD")
    if env_board:
        return _slug(env_board)
    try:
        current = kb.get_current_board()
        if current:
            return _slug(current)
    except Exception:
        pass
    return "default"


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(value).strip().lower()).strip("-_")
    return slug or "default"


def _rng(task_id: str, attempt: int) -> random.Random:
    seed = os.environ.get("HERMES_MOCK_KANBAN_SEED")
    if seed:
        return random.Random(f"{seed}:{task_id}:{attempt}")
    return random.Random()


def _success_rate() -> float:
    raw = os.environ.get("HERMES_MOCK_KANBAN_SUCCESS_RATE", str(DEFAULT_SUCCESS_RATE))
    try:
        return max(0.0, min(1.0, float(raw)))
    except ValueError:
        return DEFAULT_SUCCESS_RATE


def _now() -> int:
    return int(time.time())
