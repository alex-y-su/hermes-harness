from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from harness.bridge.a2a_client import A2AClient
from harness.bridge.fs_contract import move_if_exists, read_json
from harness.bridge.secrets import SecretResolver
from harness.bridge.store import BridgeDb


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def cancel_team(
    *,
    db: BridgeDb,
    secrets: SecretResolver,
    a2a_client: A2AClient | Any,
    factory_dir: str | Path,
    team_name: str,
    team_dir: str | Path,
) -> dict[str, Any]:
    factory_dir = Path(factory_dir)
    team_dir = Path(team_dir)
    transport = read_json(team_dir / "transport.json")
    bearer_token = secrets.resolve(transport.get("team_bearer_token_ref"))
    active = db.active_assignments(team_name)
    for assignment in active:
        try:
            a2a_client.cancel_task(transport=transport, bearer_token=bearer_token, task_id=assignment["a2a_task_id"])
            db.mark_cancel_requested(assignment["assignment_id"])
            db.append_event(
                team_name=team_name,
                assignment_id=assignment["assignment_id"],
                task_id=assignment["a2a_task_id"],
                source="a2a-bridge",
                kind="cancel-requested",
                state="cancel-requested",
            )
        except Exception as error:
            db.append_event(
                team_name=team_name,
                assignment_id=assignment["assignment_id"],
                task_id=assignment["a2a_task_id"],
                source="a2a-bridge",
                kind="cancel-failed",
                state="failed",
                metadata={"error": str(error)},
            )

    handle = db.get_substrate_handle(team_name)
    db.append_event(
        team_name=team_name,
        source="a2a-bridge",
        kind="archive",
        state="archived",
        metadata={"substrate_handle": handle["handle"] if handle else None, "substrate_cancel_stub": True},
    )

    archive_dir = factory_dir.parent / "archive" / f"teams_{team_name}_{_timestamp()}"
    if team_dir.exists():
        move_if_exists(team_dir, archive_dir)
    return {"archived_path": str(archive_dir), "canceled": len(active)}
