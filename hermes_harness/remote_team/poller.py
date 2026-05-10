from __future__ import annotations

import importlib
import json
import os
import re
import time
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hermes_harness.remote_team import PROTOCOL_VERSION
from hermes_harness.remote_team.protocol import heading_sections
from hermes_harness.remote_team.quality import enforce_response_quality
from hermes_harness.remote_team.transports import call_team


TEAM_PREFIX = "team:"
DEFAULT_POLL_INTERVAL_SECONDS = 15 * 60
MIN_POLL_INTERVAL_SECONDS = 15
MAX_POLL_INTERVAL_SECONDS = 24 * 60 * 60
DEFAULT_ACTIVE_CYCLE_TTL_SECONDS = 7 * 24 * 60 * 60


@dataclass(frozen=True)
class PollDecision:
    due: bool
    interval_seconds: int
    next_due_at: str
    reason: str


def poll_once(
    *,
    registry_path: Path | None = None,
    board: str | None = None,
    all_boards: bool = False,
    limit: int = 50,
    dry_run: bool = False,
    now: float | None = None,
    kb_module: Any | None = None,
) -> dict[str, Any]:
    kb = kb_module or _load_kanban_module()
    registry = registry_path or _registry_path(kb)
    state_path = _poll_state_path(kb)
    state = _load_state(state_path)
    checked = 0
    polled = 0
    updated = 0
    skipped: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    task_results: list[dict[str, Any]] = []
    timestamp = float(now if now is not None else time.time())

    for board_name in _boards(kb, board=board, all_boards=all_boards):
        try:
            board_result = _poll_board(
                kb=kb,
                registry=registry,
                state=state,
                board=board_name,
                limit=max(0, limit - polled),
                dry_run=dry_run,
                now=timestamp,
            )
        except Exception as exc:  # noqa: BLE001 - poller should report per-board failures.
            errors.append({"board": board_name, "error": exc.__class__.__name__, "message": str(exc)})
            continue
        checked += board_result["checked"]
        polled += board_result["polled"]
        updated += board_result["updated"]
        skipped.extend(board_result["skipped"])
        errors.extend(board_result["errors"])
        task_results.extend(board_result["tasks"])
        if polled >= limit:
            break

    if not dry_run:
        _save_state(state_path, state)

    return {
        "ok": not errors,
        "protocol_version": PROTOCOL_VERSION,
        "checked": checked,
        "polled": polled,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "tasks": task_results,
        "state_path": str(state_path),
    }


def poll_loop(
    *,
    registry_path: Path | None = None,
    board: str | None = None,
    all_boards: bool = False,
    limit: int = 50,
    dry_run: bool = False,
    sleep_seconds: int = 60,
    once: bool = False,
) -> int:
    while True:
        result = poll_once(
            registry_path=registry_path,
            board=board,
            all_boards=all_boards,
            limit=limit,
            dry_run=dry_run,
        )
        print(json.dumps(result, indent=2, sort_keys=True), flush=True)
        if once:
            return 0 if result.get("ok") else 1
        time.sleep(max(1, sleep_seconds))


def poll_decision(task: Any, result: dict[str, Any], state_entry: dict[str, Any], *, now: float) -> PollDecision:
    interval = _poll_interval_seconds(task, result)
    next_due_raw = _next_report_due_value(task, result) or state_entry.get("next_due_at")
    next_due_ts = _parse_time(next_due_raw)
    if next_due_ts is not None:
        due_at = next_due_ts
        reason = f"next_report_due_at={next_due_raw}"
    else:
        baseline = _last_poll_baseline(task, result, state_entry, now=now)
        due_at = baseline + interval
        reason = f"interval_seconds={interval}"
    return PollDecision(
        due=now >= due_at,
        interval_seconds=interval,
        next_due_at=_format_time(due_at),
        reason=reason,
    )


def _poll_board(
    *,
    kb: Any,
    registry: Path,
    state: dict[str, Any],
    board: str,
    limit: int,
    dry_run: bool,
    now: float,
) -> dict[str, Any]:
    checked = 0
    polled = 0
    updated = 0
    skipped: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    task_results: list[dict[str, Any]] = []

    with closing(kb.connect(board=board)) as conn:
        for task in _running_tasks(kb, conn):
            checked += 1
            team = _team_name(getattr(task, "assignee", ""))
            if not team:
                continue
            result_payload = _loads_result(getattr(task, "result", None))
            remote = _remote_context(result_payload)
            if not remote:
                skipped.append({"board": board, "task_id": task.id, "reason": "missing_remote_context"})
                continue
            state_key = f"{board}:{task.id}"
            decision = poll_decision(task, result_payload, state.get(state_key) or {}, now=now)
            if not decision.due:
                skipped.append(
                    {
                        "board": board,
                        "task_id": task.id,
                        "team": team,
                        "reason": "not_due",
                        "next_due_at": decision.next_due_at,
                    }
                )
                continue
            if polled >= limit:
                skipped.append({"board": board, "task_id": task.id, "reason": "limit_reached"})
                continue

            request = _status_request(task, team=team, board=board, remote=remote, decision=decision)
            if dry_run:
                response = {
                    "ok": True,
                    "status": "dry_run",
                    "remote_team": team,
                    "remote_task_id": remote.get("remote_task_id"),
                    "main_card_update": {"action": "keep_running", "status": "running"},
                }
            else:
                try:
                    response = call_team(
                        registry_path=registry,
                        team=team,
                        operation="status",
                        request=request,
                        timeout=_remote_timeout_seconds(),
                    )
                except Exception as exc:  # noqa: BLE001 - keep polling other cards.
                    errors.append(
                        {
                            "board": board,
                            "task_id": task.id,
                            "team": team,
                            "error": exc.__class__.__name__,
                            "message": str(exc),
                        }
                    )
                    continue

            polled += 1
            next_due_at = _next_due_after_response(task, response, decision, now=now)
            state[state_key] = {
                "last_polled_at": _format_time(now),
                "next_due_at": next_due_at,
                "interval_seconds": decision.interval_seconds,
                "remote_team": team,
                "remote_task_id": response.get("remote_task_id") or remote.get("remote_task_id"),
            }
            if not dry_run:
                if response.get("ok"):
                    applied = _apply_response(kb, conn, task, response, decision)
                    updated += int(applied)
                else:
                    applied = _block_failed_poll(kb, conn, task, response)
                    updated += int(applied)
            task_results.append(
                {
                    "board": board,
                    "task_id": task.id,
                    "team": team,
                    "remote_task_id": response.get("remote_task_id") or remote.get("remote_task_id"),
                    "status": response.get("status"),
                    "main_action": _main_update(response).get("action"),
                    "updated": not dry_run,
                }
            )
    return {
        "checked": checked,
        "polled": polled,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "tasks": task_results,
    }


def _running_tasks(kb: Any, conn: Any) -> list[Any]:
    try:
        return list(kb.list_tasks(conn, status="running"))
    except TypeError:
        return [task for task in kb.list_tasks(conn) if getattr(task, "status", "") == "running"]


def _status_request(
    task: Any,
    *,
    team: str,
    board: str,
    remote: dict[str, Any],
    decision: PollDecision,
) -> dict[str, Any]:
    external_id = remote.get("external_id") or f"{board}:{task.id}"
    return {
        "protocol_version": PROTOCOL_VERSION,
        "source_team": os.environ.get("HERMES_MAIN_TEAM_NAME", "main"),
        "target_team": team,
        "external_id": external_id,
        "source_board": remote.get("source_board") or board,
        "source_task_id": remote.get("source_task_id") or task.id,
        "remote_task_id": remote.get("remote_task_id"),
        "board": remote.get("board") or team,
        "force_report": True,
        "poll": {
            "force_report": True,
            "owner": "main-dashboard",
            "reason": decision.reason,
            "interval_seconds": decision.interval_seconds,
            "next_due_at": decision.next_due_at,
            "main_card_status": getattr(task, "status", None),
        },
        "task": {
            "title": getattr(task, "title", ""),
            "body": getattr(task, "body", "") or "",
            "tenant": getattr(task, "tenant", None),
            "priority": getattr(task, "priority", None),
            "status": getattr(task, "status", None),
        },
    }


def _apply_response(kb: Any, conn: Any, task: Any, response: dict[str, Any], decision: PollDecision) -> bool:
    response = enforce_response_quality(response, task_body=getattr(task, "body", "") or "")
    main_update = _main_update(response)
    action = str(main_update.get("action") or _default_action(response))
    result_payload = _result_payload(response)
    summary = _summary(task.id, response)
    if action == "keep_running":
        if response.get("status") == "running" and response.get("result") is None:
            return _record_pending_poll(kb, conn, task, response, summary, decision)
        return _record_running_report(kb, conn, task, response, result_payload, summary, decision)
    if action == "block":
        reason = main_update.get("reason") or response.get("message") or response.get("status") or "remote team blocked"
        ok = kb.block_task(conn, task.id, reason=str(reason))
        if ok:
            kb.add_comment(conn, task.id, "remote-team-kanban", json.dumps(response, sort_keys=True))
        return bool(ok)
    ok = kb.complete_task(
        conn,
        task.id,
        result=json.dumps(result_payload, sort_keys=True),
        summary=summary,
        metadata=_metadata(response),
    )
    if ok:
        kb.add_comment(conn, task.id, "remote-team-kanban", summary)
    return bool(ok)


def _block_failed_poll(kb: Any, conn: Any, task: Any, response: dict[str, Any]) -> bool:
    reason = response.get("message") or response.get("error") or "remote team poll failed"
    ok = kb.block_task(conn, task.id, reason=str(reason))
    if ok:
        kb.add_comment(conn, task.id, "remote-team-kanban", json.dumps(response, sort_keys=True))
    return bool(ok)


def _record_running_report(
    kb: Any,
    conn: Any,
    task: Any,
    response: dict[str, Any],
    result_payload: dict[str, Any],
    summary: str,
    decision: PollDecision,
) -> bool:
    result_json = json.dumps(result_payload, sort_keys=True)
    ttl = _active_cycle_ttl_seconds(decision.interval_seconds)
    lock = getattr(task, "claim_lock", None)
    if lock:
        kb.heartbeat_claim(conn, task.id, ttl_seconds=ttl, claimer=lock)
    now = int(time.time())
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
                "poll_interval_seconds": decision.interval_seconds,
                "next_due_at": decision.next_due_at,
            },
            run_id=run_id,
        )
    return True


def _record_pending_poll(
    kb: Any,
    conn: Any,
    task: Any,
    response: dict[str, Any],
    summary: str,
    decision: PollDecision,
) -> bool:
    ttl = _active_cycle_ttl_seconds(decision.interval_seconds)
    lock = getattr(task, "claim_lock", None)
    if lock:
        kb.heartbeat_claim(conn, task.id, ttl_seconds=ttl, claimer=lock)
    now = int(time.time())
    with kb.write_txn(conn):
        cur = conn.execute(
            """
            UPDATE tasks
               SET claim_expires = CASE
                       WHEN claim_lock IS NULL THEN claim_expires
                       ELSE ?
                   END
             WHERE id = ?
               AND status = 'running'
            """,
            (now + ttl, task.id),
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
            "remote_status_poll_pending",
            {
                "remote_team": response.get("remote_team"),
                "remote_task_id": response.get("remote_task_id"),
                "summary": summary,
                "poll_interval_seconds": decision.interval_seconds,
                "next_due_at": decision.next_due_at,
            },
            run_id=run_id,
        )
    return True


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


def _summary(task_id: str, response: dict[str, Any]) -> str:
    main_update = _main_update(response)
    return (
        f"Remote team {response.get('remote_team')} polled {task_id}: "
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


def _remote_context(result: dict[str, Any]) -> dict[str, Any]:
    response = result.get("remote_team_protocol_response")
    if isinstance(response, dict):
        remote = dict(response)
    else:
        remote = {}
    for key in ("external_id", "remote_task_id", "remote_team", "board", "source_board", "source_task_id"):
        if key not in remote and result.get(key) is not None:
            remote[key] = result.get(key)
    if not remote.get("remote_task_id") and not remote.get("external_id"):
        return {}
    return remote


def _loads_result(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(str(raw))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _poll_interval_seconds(task: Any, result: dict[str, Any]) -> int:
    fields = _card_fields(getattr(task, "body", "") or "")
    raw_values = [
        fields.get("poll interval seconds"),
        fields.get("poll interval"),
        fields.get("remote poll interval"),
        fields.get("report interval"),
        fields.get("reporting interval"),
        fields.get("review cadence"),
        _main_update_from_result(result).get("poll_interval_seconds"),
        _main_update_from_result(result).get("report_interval_seconds"),
        _main_update_from_result(result).get("review_cadence"),
        result.get("poll_interval_seconds"),
        result.get("report_interval_seconds"),
        result.get("review_cadence"),
    ]
    for raw in raw_values:
        parsed = _parse_interval(raw)
        if parsed is not None:
            return parsed
    return DEFAULT_POLL_INTERVAL_SECONDS


def _next_report_due_value(task: Any, result: dict[str, Any]) -> Any:
    fields = _card_fields(getattr(task, "body", "") or "")
    reports = result.get("reports") if isinstance(result.get("reports"), list) else []
    last_report = reports[-1] if reports and isinstance(reports[-1], dict) else {}
    values = [
        _main_update_from_result(result).get("next_report_due_at"),
        result.get("next_report_due_at"),
        last_report.get("next_report_due_at"),
        fields.get("next report due at"),
        fields.get("next report due"),
    ]
    for value in values:
        if value:
            return value
    return None


def _next_due_after_response(task: Any, response: dict[str, Any], decision: PollDecision, *, now: float) -> str:
    result_payload = _result_payload(response)
    raw = _next_report_due_value(task, result_payload)
    timestamp = _parse_time(raw)
    if timestamp is not None and timestamp > now:
        return _format_time(timestamp)
    return _format_time(now + decision.interval_seconds)


def _main_update_from_result(result: dict[str, Any]) -> dict[str, Any]:
    update = result.get("main_card_update")
    if isinstance(update, dict):
        return update
    response = result.get("remote_team_protocol_response")
    if isinstance(response, dict):
        return _main_update(response)
    return {}


def _last_poll_baseline(task: Any, result: dict[str, Any], state_entry: dict[str, Any], *, now: float) -> float:
    values = [
        state_entry.get("last_polled_at"),
        state_entry.get("last_sync_at"),
    ]
    response = result.get("remote_team_protocol_response")
    if isinstance(response, dict):
        values.extend([response.get("updated_at"), response.get("created_at")])
    values.extend([result.get("updated_at"), getattr(task, "started_at", None), getattr(task, "created_at", None)])
    for value in values:
        parsed = _parse_time(value)
        if parsed is not None:
            return parsed
    return now


def _card_fields(body: str) -> dict[str, str]:
    fields = heading_sections(body)
    for raw in body.splitlines():
        line = re.sub(r"^\s*#{1,6}\s*", "", raw).strip()
        match = re.match(r"^([A-Za-z][A-Za-z0-9 /_-]{1,60}):\s*(.+)$", line)
        if match:
            key = re.sub(r"\s+", " ", match.group(1).strip().lower().replace("_", " "))
            fields.setdefault(key, match.group(2).strip())
    return fields


def _parse_interval(raw: Any) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)) and raw > 0:
        return _clamp_interval(int(raw))
    value = str(raw).strip().lower()
    if not value:
        return None
    named = {
        "hourly": 60 * 60,
        "daily": 24 * 60 * 60,
        "weekly": 7 * 24 * 60 * 60,
        "twice daily": 12 * 60 * 60,
    }
    if value in named:
        return _clamp_interval(named[value])
    short = re.search(r"\b(\d+)\s*([smhd])\b", value)
    if short:
        return _clamp_interval(int(short.group(1)) * _unit_seconds(short.group(2)))
    match = re.search(r"(?:every\s+)?(\d+)\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?|days?)", value)
    if match:
        return _clamp_interval(int(match.group(1)) * _unit_seconds(match.group(2)))
    if "daily" in value or "end of the day" in value:
        return _clamp_interval(24 * 60 * 60)
    if "hour" in value:
        return _clamp_interval(60 * 60)
    return None


def _unit_seconds(unit: str) -> int:
    normalized = unit.lower()
    if normalized.startswith("s"):
        return 1
    if normalized.startswith("m"):
        return 60
    if normalized.startswith("h"):
        return 60 * 60
    if normalized.startswith("d"):
        return 24 * 60 * 60
    return 1


def _clamp_interval(seconds: int) -> int:
    return min(MAX_POLL_INTERVAL_SECONDS, max(MIN_POLL_INTERVAL_SECONDS, seconds))


def _parse_time(raw: Any) -> float | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    value = str(raw).strip()
    if not value:
        return None
    if value.isdigit():
        return float(value)
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _format_time(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat().replace("+00:00", "Z")


def _boards(kb: Any, *, board: str | None, all_boards: bool) -> list[str]:
    if board:
        return [board]
    if all_boards:
        try:
            boards = kb.list_boards(include_archived=False)
        except TypeError:
            boards = kb.list_boards()
        names = []
        for item in boards:
            names.append(str(getattr(item, "name", item)))
        return names or [_source_board(kb, None)]
    return [_source_board(kb, None)]


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


def _team_name(assignee: str) -> str:
    value = str(assignee or "")
    if not value.startswith(TEAM_PREFIX):
        return ""
    return value[len(TEAM_PREFIX) :].strip()


def _registry_path(kb: Any) -> Path:
    configured = os.environ.get("HERMES_REMOTE_TEAMS_CONFIG")
    if configured:
        return Path(configured)
    return kb.kanban_home() / "remote_teams.json"


def _poll_state_path(kb: Any) -> Path:
    configured = os.environ.get("HERMES_REMOTE_TEAM_POLL_STATE")
    if configured:
        return Path(configured).expanduser()
    return kb.kanban_home() / "remote-team-poller" / "state.json"


def _load_state(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_state(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _load_kanban_module() -> Any:
    try:
        return importlib.import_module("hermes_cli.kanban_db")
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Hermes Kanban module is not available. Run remote-team polling inside the Hermes "
            "dashboard/runtime environment where hermes_cli.kanban_db is installed."
        ) from exc


def _remote_timeout_seconds() -> int:
    raw = os.environ.get("HERMES_REMOTE_TEAM_TIMEOUT", "600")
    try:
        return max(1, int(raw))
    except ValueError:
        return 600


def _active_cycle_ttl_seconds(interval_seconds: int) -> int:
    raw = os.environ.get("HERMES_REMOTE_TEAM_ACTIVE_TTL_SECONDS")
    if raw:
        try:
            return max(60, int(raw))
        except ValueError:
            pass
    return max(DEFAULT_ACTIVE_CYCLE_TTL_SECONDS, interval_seconds * 3)
