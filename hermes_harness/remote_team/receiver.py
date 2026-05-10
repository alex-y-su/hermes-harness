from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from hermes_harness.remote_team import PROTOCOL_VERSION
from hermes_harness.remote_team.protocol import main_card_update, task_contract, validate_request


def receive(payload: dict[str, Any]) -> dict[str, Any]:
    request = validate_request(payload)
    operation = request["operation"]
    if operation == "health":
        return health()
    if operation == "submit_or_get":
        return submit_or_get(request)
    if operation == "status":
        return status(request)
    raise AssertionError(f"unreachable operation: {operation}")


def health() -> dict[str, Any]:
    hermes = _run(["hermes", "version"], check=False)
    return {
        "ok": hermes.returncode == 0,
        "protocol_version": PROTOCOL_VERSION,
        "status": "healthy" if hermes.returncode == 0 else "unhealthy",
        "hermes_home": str(_hermes_home()),
        "hermes_version": hermes.stdout.strip(),
    }


def submit_or_get(request: dict[str, Any]) -> dict[str, Any]:
    board = str(request.get("board") or request["target_team"])
    external_id = str(request["external_id"])
    task = request["task"]
    execution_mode = os.environ.get("HERMES_REMOTE_TEAM_EXECUTION_MODE", "deterministic")

    _ensure_board(board)
    mapping = _load_mapping(board)
    remote_task_id = mapping.get(external_id)

    if remote_task_id is None:
        created = _create_task(board, external_id, task)
        remote_task_id = created["id"]
        mapping[external_id] = remote_task_id
        _save_mapping(board, mapping)

    current = _show_task(board, remote_task_id)
    if current["task"]["status"] != "done":
        if execution_mode == "hermes":
            _dispatch_and_wait(board, remote_task_id)
        else:
            result = _build_result(request, remote_task_id)
            _complete_task(board, remote_task_id, result)
        current = _show_task(board, remote_task_id)

    return _response_from_task(request, current["task"], board=board)


def status(request: dict[str, Any]) -> dict[str, Any]:
    board = str(request.get("board") or request["target_team"])
    external_id = str(request["external_id"])
    mapping = _load_mapping(board)
    remote_task_id = request.get("remote_task_id") or mapping.get(external_id)
    if not remote_task_id:
        return {
            "ok": False,
            "protocol_version": PROTOCOL_VERSION,
            "external_id": external_id,
            "status": "not_found",
            "result": None,
        }
    current = _show_task(board, str(remote_task_id))
    return _response_from_task(request, current["task"], board=board)


def _create_task(board: str, external_id: str, task: dict[str, Any]) -> dict[str, Any]:
    assignee = task.get("assignee") or os.environ.get("HERMES_REMOTE_TEAM_PROFILE")
    command = [
        "hermes",
        "kanban",
        "--board",
        board,
        "create",
        str(task["title"]),
        "--body",
        str(task.get("body") or ""),
        "--tenant",
        str(task.get("tenant") or "growth"),
        "--priority",
        str(task.get("priority") or 0),
        "--created-by",
        "remote-team-protocol",
        "--idempotency-key",
        external_id,
        "--json",
    ]
    if assignee:
        command.extend(["--assignee", str(assignee)])
    completed = _run(command)
    return json.loads(completed.stdout)


def _dispatch_and_wait(board: str, task_id: str) -> None:
    timeout = int(os.environ.get("HERMES_REMOTE_TEAM_WAIT_SECONDS", "300"))
    deadline = time.monotonic() + timeout
    while True:
        current = _show_task(board, task_id)
        status = current["task"]["status"]
        if status in {"done", "blocked"}:
            return
        _run(["hermes", "kanban", "--board", board, "dispatch", "--max", "1", "--json"], check=False)
        time.sleep(2)
        current = _show_task(board, task_id)
        status = current["task"]["status"]
        if status in {"done", "blocked"}:
            return
        if time.monotonic() >= deadline:
            _run(
                [
                    "hermes",
                    "kanban",
                    "--board",
                    board,
                    "comment",
                    task_id,
                    f"remote-team receive timed out after {timeout}s waiting for Hermes worker",
                ],
                check=False,
            )
            return


def _show_task(board: str, task_id: str) -> dict[str, Any]:
    completed = _run(["hermes", "kanban", "--board", board, "show", task_id, "--json"])
    return json.loads(completed.stdout)


def _complete_task(board: str, task_id: str, result: dict[str, Any]) -> None:
    result_json = json.dumps(result, sort_keys=True)
    _run(
        [
            "hermes",
            "kanban",
            "--board",
            board,
            "complete",
            task_id,
            "--result",
            result_json,
            "--summary",
            result["summary"],
            "--metadata",
            json.dumps({"remote_team_protocol": True, "external_id": result["external_id"]}),
        ]
    )


def _build_result(request: dict[str, Any], remote_task_id: str) -> dict[str, Any]:
    task = request["task"]
    contract = task_contract(str(task.get("body") or ""), tenant=task.get("tenant"))
    main_update = main_card_update(contract, remote_status="reported")
    reported_kpis = [
        {
            "name": name,
            "status": "ready_to_measure",
            "measurement_window": contract["measurement_window"],
        }
        for name in contract["requested_kpis"]
    ]
    return {
        "mock_remote": False,
        "remote_team_protocol": True,
        "protocol_version": PROTOCOL_VERSION,
        "external_id": request["external_id"],
        "remote_task_id": remote_task_id,
        "team": request["target_team"],
        "status": "success",
        "card_type": contract["card_type"],
        "summary": f"Remote team {request['target_team']} accepted and completed {request['external_id']}.",
        "stream": contract["stream"],
        "approval": contract["approval"],
        "completed_deliverables": contract["expected_deliverables"] or ["remote task packet"],
        "requested_kpis": contract["requested_kpis"],
        "reported_kpis": reported_kpis,
        "measurement_window": contract["measurement_window"],
        "cycle_window": contract["cycle_window"],
        "review_cadence": contract["review_cadence"],
        "continue_rule": contract["continue_rule"],
        "stop_rule": contract["stop_rule"],
        "next_report_due_at": contract["next_report_due_at"],
        "decision_rule": contract["decision_rule"],
        "main_card_update": main_update,
        "evidence": [
            f"remote board task {remote_task_id}",
            f"HERMES_HOME={_hermes_home()}",
        ],
        "blockers": [],
        "next_recommendation": _next_recommendation(contract),
        "updated_at": _now(),
    }


def _next_recommendation(contract: dict[str, Any]) -> str:
    if contract["card_type"] in {"campaign_cycle", "support_cycle", "direction"}:
        return "Keep the main card running and continue reporting until the cycle window or stop/continue rule resolves."
    if contract["approval"]["required_before_external_action"]:
        return "Request approval before external publishing, outreach, spend, or credentialed action."
    if contract["stream"] == "maintenance":
        return "Schedule the next maintenance check and escalate only broken or stale assets."
    return "Review KPI readiness and decide whether to launch, iterate, or stop."


def _response_from_task(request: dict[str, Any], task: dict[str, Any], *, board: str) -> dict[str, Any]:
    result = _parse_result(task.get("result"))
    if not isinstance(result, dict) and task.get("status") == "done":
        result = _build_result(request, task["id"])
        result["remote_task_result_missing"] = True
    if isinstance(result, dict):
        _enrich_result_from_remote_board(result, board=board, remote_task_id=task["id"])
    main_update = result.get("main_card_update") if isinstance(result, dict) else None
    return {
        "ok": True,
        "protocol_version": PROTOCOL_VERSION,
        "external_id": request["external_id"],
        "remote_task_id": task["id"],
        "remote_team": request["target_team"],
        "board": request.get("board") or request["target_team"],
        "status": _remote_status(task["status"]),
        "main_card_update": main_update,
        "result": result,
        "updated_at": _now(),
    }


def _enrich_result_from_remote_board(result: dict[str, Any], *, board: str, remote_task_id: str) -> None:
    posts = _collect_x_posts()
    if posts and not result.get("mock_x_posts"):
        result["mock_x_posts"] = posts

    internal_tasks = _internal_tasks(board, remote_task_id)
    if internal_tasks and not result.get("internal_tasks"):
        result["internal_tasks"] = internal_tasks
    if internal_tasks and not result.get("maintenance_loop"):
        maintenance = [
            task
            for task in internal_tasks
            if any(token in (task["title"] + "\n" + task.get("body", "")).lower() for token in ("maintenance", "cadence", "posting"))
        ]
        result["maintenance_loop"] = {
            "status": "active",
            "task_ids": [task["id"] for task in maintenance or internal_tasks],
            "summary": "Remote team created follow-up Kanban tasks to keep the campaign cadence and KPI reporting loop active.",
        }


def _collect_x_posts() -> list[dict[str, Any]]:
    paths = [_hermes_home() / "mock-x" / "posts.jsonl"]
    profiles = _hermes_home() / "profiles"
    if profiles.exists():
        paths.extend(sorted(profiles.glob("*/mock-x/posts.jsonl")))
    posts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in paths:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                post = json.loads(line)
            except json.JSONDecodeError:
                continue
            post_id = str(post.get("id") or f"{path}:{len(posts)}")
            if post_id in seen:
                continue
            seen.add(post_id)
            posts.append(post)
    return posts


def _internal_tasks(board: str, remote_task_id: str) -> list[dict[str, Any]]:
    completed = _run(["hermes", "kanban", "--board", board, "list", "--json"], check=False)
    if completed.returncode != 0:
        return []
    try:
        tasks = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return []
    if not isinstance(tasks, list):
        return []
    internal: list[dict[str, Any]] = []
    for task in tasks:
        if not isinstance(task, dict) or task.get("id") == remote_task_id:
            continue
        internal.append(
            {
                "id": task.get("id"),
                "title": task.get("title"),
                "status": task.get("status"),
                "assignee": task.get("assignee"),
                "tenant": task.get("tenant"),
                "body": task.get("body") or "",
            }
        )
    return internal


def _parse_result(raw: Any) -> Any:
    if not raw:
        return None
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return raw


def _remote_status(status: str) -> str:
    return {
        "done": "completed",
        "blocked": "blocked",
        "running": "running",
        "ready": "running",
        "todo": "running",
    }.get(status, status)


def _ensure_board(board: str) -> None:
    _run(["hermes", "kanban", "boards", "create", board, "--switch"], check=False)


def _mapping_path(board: str) -> Path:
    return _hermes_home() / "remote-team-protocol" / f"{board}.json"


def _load_mapping(board: str) -> dict[str, str]:
    path = _mapping_path(board)
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    return {str(key): str(value) for key, value in payload.items()}


def _save_mapping(board: str, mapping: dict[str, str]) -> None:
    path = _mapping_path(board)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(mapping, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME", "/vm/hermes-home"))


def _run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if check and completed.returncode != 0:
        raise RuntimeError(f"command failed ({completed.returncode}): {' '.join(command)}\n{completed.stdout}")
    return completed


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
