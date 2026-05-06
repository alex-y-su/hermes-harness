from __future__ import annotations

import asyncio
import os
import sqlite3
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
    factory_dir: str | Path | None = None,
    db_path: str | Path | None = None,
    e2b_dry_run: bool = False,
    retry_delay_seconds: int = 60,
    max_retries: int = 3,
    lease_ttl_seconds: int = 300,
    lease_holder: str | None = None,
) -> dict[str, Any]:
    team_dir = Path(team_dir)
    inbox_path = Path(inbox_path)
    assignment_id = assignment_id_from_path(inbox_path)
    existing = db.ensure_assignment(assignment_id=assignment_id, team_name=team_name, inbox_path=inbox_path)
    if existing and existing["a2a_task_id"]:
        return {"skipped": True, "task_id": existing["a2a_task_id"]}
    if not db.assignment_ready_for_dispatch(assignment_id):
        current = db.get_assignment(assignment_id)
        return {"skipped": True, "status": current["status"] if current else "unknown"}
    if not inbox_path.exists():
        return {"skipped": True, "missing": True}
    holder = lease_holder or f"bridge:{os.getpid()}"
    if not db.acquire_lease(
        resource_type="assignment",
        resource_id=assignment_id,
        holder=holder,
        ttl_seconds=lease_ttl_seconds,
    ):
        return {"skipped": True, "leased": True}
    db.mark_assignment_heartbeat(
        assignment_id=assignment_id,
        lease_owner=holder,
        lease_ttl_seconds=lease_ttl_seconds,
    )

    transport = read_json(team_dir / "transport.json")
    provisioned_assignment_sandbox = False
    if _needs_assignment_sandbox(transport):
        if factory_dir is None or db_path is None:
            raise ValueError("factory_dir and db_path are required for per-assignment E2B dispatch")
        max_machines = int(os.getenv("HARNESS_MAX_E2B_ASSIGNMENT_MACHINES", "0") or "0")
        if max_machines > 0 and _active_assignment_sandbox_count(Path(db_path)) >= max_machines:
            db.release_lease(resource_type="assignment", resource_id=assignment_id, holder=holder)
            return {"skipped": True, "status": "capacity-limited", "max_e2b_assignment_machines": max_machines}
        sandbox = _run_async_assignment_sandbox(
            factory=Path(factory_dir),
            db_path=Path(db_path),
            team=team_name,
            assignment_id=assignment_id,
            dry_run=e2b_dry_run,
            secrets=secrets,
        )
        transport = {**transport, "agent_card_url": sandbox["agent_card_url"]}
        provisioned_assignment_sandbox = True
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
        retry_row = db.mark_assignment_retrying(
            assignment_id=assignment_id,
            error=str(error),
            delay_seconds=retry_delay_seconds,
            max_retries=max_retries,
        )
        if provisioned_assignment_sandbox and factory_dir is not None and db_path is not None:
            _run_async_finalize_assignment(
                factory=Path(factory_dir),
                db_path=Path(db_path),
                team=team_name,
                assignment_id=assignment_id,
                terminal_state=retry_row["status"] if retry_row is not None else "failed",
                dry_run=e2b_dry_run,
            )
        db.release_lease(resource_type="assignment", resource_id=assignment_id, holder=holder)
        failure_path = inbox_path.parent / f"{assignment_id}.failed.json"
        write_json(
            failure_path,
            {
                "assignment_id": assignment_id,
                "team_name": team_name,
                "failed_at": utc_now(),
                "error": str(error),
                "status": retry_row["status"] if retry_row is not None else "failed",
                "retry_count": retry_row["retry_count"] if retry_row is not None else None,
                "next_retry_at": retry_row["next_retry_at"] if retry_row is not None else None,
            },
        )
        db.append_event(
            team_name=team_name,
            assignment_id=assignment_id,
            source="a2a-bridge",
            kind="dispatch-retrying" if retry_row is not None and retry_row["status"] == "retrying" else "dispatch-failed",
            state=retry_row["status"] if retry_row is not None else "failed",
            payload_path=failure_path,
            metadata={
                "error": str(error),
                "retry_count": retry_row["retry_count"] if retry_row is not None else None,
                "next_retry_at": retry_row["next_retry_at"] if retry_row is not None else None,
            },
        )
        return {
            "dispatched": False,
            "status": retry_row["status"] if retry_row is not None else "failed",
            "retry_count": retry_row["retry_count"] if retry_row is not None else None,
            "next_retry_at": retry_row["next_retry_at"] if retry_row is not None else None,
            "error": str(error),
        }

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


def _needs_assignment_sandbox(transport: dict[str, Any]) -> bool:
    if transport.get("substrate") != "e2b":
        return False
    return bool(transport.get("per_assignment")) or not bool(str(transport.get("agent_card_url") or "").strip())


def _active_assignment_sandbox_count(db_path: Path) -> int:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM assignment_sandboxes s
            JOIN team_assignments a ON a.assignment_id = s.assignment_id
            WHERE s.substrate = 'e2b'
              AND s.archived_at IS NULL
              AND s.status NOT IN ('completed', 'failed', 'canceled', 'archived', 'paused_archived')
              AND a.status IN ('dispatched', 'working', 'resuming', 'input-required', 'auth-required')
            """
        ).fetchone()
        return int(row[0] if row else 0)
    finally:
        conn.close()


def _run_async_assignment_sandbox(
    *,
    factory: Path,
    db_path: Path,
    team: str,
    assignment_id: str,
    dry_run: bool,
    secrets: SecretResolver | None = None,
) -> dict[str, str]:
    from harness.tools.run_assignment_sandbox import run_for_assignment

    return asyncio.run(
        run_for_assignment(
            factory=factory,
            db_path=db_path,
            team=team,
            assignment_id=assignment_id,
            dry_run=dry_run,
            secret_resolver=secrets,
        )
    )


def _run_async_finalize_assignment(
    *,
    factory: Path,
    db_path: Path,
    team: str,
    assignment_id: str,
    terminal_state: str,
    dry_run: bool,
) -> dict[str, str]:
    from harness.tools.finalize_assignment_sandbox import finalize_assignment

    return asyncio.run(
        finalize_assignment(
            factory=factory,
            db_path=db_path,
            team=team,
            assignment_id=assignment_id,
            terminal_state=terminal_state,
            dry_run=dry_run,
        )
    )


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
