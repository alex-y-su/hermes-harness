from __future__ import annotations

from pathlib import Path
from typing import Any

from harness.bridge.a2a_client import A2AClient, SendAssignmentResult
from harness.bridge.fs_contract import assignment_id_from_path, read_json, utc_now, write_json, move_if_exists
from harness.bridge.secrets import SecretResolver
from harness.bridge.store import BridgeDb


def dispatch_assignment(
    *,
    db: BridgeDb,
    secrets: SecretResolver,
    a2a_client: A2AClient | Any,
    team_name: str,
    team_dir: str | Path,
    inbox_path: str | Path,
) -> dict[str, Any]:
    team_dir = Path(team_dir)
    inbox_path = Path(inbox_path)
    assignment_id = assignment_id_from_path(inbox_path)
    existing = db.ensure_assignment(assignment_id=assignment_id, team_name=team_name, inbox_path=inbox_path)
    if existing and existing["a2a_task_id"]:
        return {"skipped": True, "task_id": existing["a2a_task_id"]}
    if not inbox_path.exists():
        return {"skipped": True, "missing": True}

    transport = read_json(team_dir / "transport.json")
    bearer_token = secrets.resolve(transport.get("team_bearer_token_ref"))
    push_token = secrets.resolve(transport.get("push_token_ref"))
    text = inbox_path.read_text(encoding="utf-8")

    try:
        send_result = a2a_client.send_assignment(
            transport=transport,
            bearer_token=bearer_token,
            push_token=push_token,
            assignment_id=assignment_id,
            text=text,
        )
    except Exception as error:
        db.update_assignment_status(assignment_id=assignment_id, status="failed")
        failure_path = inbox_path.parent / f"{assignment_id}.failed.json"
        write_json(
            failure_path,
            {
                "assignment_id": assignment_id,
                "team_name": team_name,
                "failed_at": utc_now(),
                "error": str(error),
            },
        )
        db.append_event(
            team_name=team_name,
            assignment_id=assignment_id,
            source="a2a-bridge",
            kind="dispatch-failed",
            state="failed",
            payload_path=failure_path,
            metadata={"error": str(error)},
        )
        raise

    task_id, result = _normalize_send_result(send_result)
    in_flight_path = inbox_path.parent / f"{assignment_id}.in-flight.md"
    db.mark_dispatched(assignment_id=assignment_id, task_id=task_id, in_flight_path=in_flight_path)
    write_json(
        inbox_path.parent / f"{assignment_id}.dispatched.json",
        {
            "assignment_id": assignment_id,
            "team_name": team_name,
            "task_id": task_id,
            "dispatched_at": utc_now(),
            "response": result,
        },
    )
    move_if_exists(inbox_path, in_flight_path)
    db.append_event(
        team_name=team_name,
        assignment_id=assignment_id,
        task_id=task_id,
        source="a2a-bridge",
        kind="dispatched",
        state="dispatched",
        payload_path=in_flight_path,
    )
    return {"dispatched": True, "task_id": task_id}


def _normalize_send_result(send_result: Any) -> tuple[str, Any]:
    if isinstance(send_result, SendAssignmentResult):
        return send_result.task_id, send_result.result
    if isinstance(send_result, dict):
        task_id = send_result.get("task_id") or send_result.get("taskId")
        if not task_id:
            raise ValueError("send_assignment result did not include task_id")
        return str(task_id), send_result.get("result", send_result)
    task_id = getattr(send_result, "task_id", None)
    if not task_id:
        raise ValueError("send_assignment result did not include task_id")
    return str(task_id), getattr(send_result, "result", send_result)
