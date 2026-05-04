from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from harness.bridge.fs_contract import append_journal, ensure_dir, read_json, utc_now, write_json
from harness.bridge.hmac import verify_push_signature
from harness.bridge.secrets import SecretResolver
from harness.bridge.store import BridgeDb


def bearer_from_header(header: str | None) -> str | None:
    if not header:
        return None
    match = re.match(r"^Bearer\s+(.+)$", header, re.IGNORECASE)
    return match.group(1) if match else None


def artifact_name(artifact: Any, index: int) -> str:
    raw = f"artifact-{index + 1}.md"
    if isinstance(artifact, dict):
        raw = str(artifact.get("name") or artifact.get("artifact_id") or artifact.get("id") or raw)
    name = Path(raw).name
    return re.sub(r"[^A-Za-z0-9._-]", "_", name) or f"artifact-{index + 1}.md"


def artifact_text(artifact: Any) -> str:
    if isinstance(artifact, str):
        return artifact
    if isinstance(artifact, dict):
        if artifact.get("text"):
            return str(artifact["text"])
        parts = artifact.get("parts")
        if isinstance(parts, list):
            rendered = []
            for part in parts:
                if isinstance(part, dict):
                    if part.get("text") is not None:
                        rendered.append(str(part["text"]))
                    elif isinstance(part.get("file"), dict):
                        rendered.append(str(part["file"].get("uri") or part["file"].get("bytes") or json.dumps(part)))
                    else:
                        rendered.append(json.dumps(part, sort_keys=True))
                else:
                    rendered.append(str(part))
            return "\n".join(rendered)
    return json.dumps(artifact, indent=2, sort_keys=True)


def process_push(
    *,
    db: BridgeDb,
    secrets: SecretResolver,
    factory_dir: str | Path,
    headers: dict[str, str | None],
    body: dict[str, Any],
) -> dict[str, Any]:
    factory_dir = Path(factory_dir)
    task = body.get("task") if isinstance(body.get("task"), dict) else {}
    status = body.get("status") if isinstance(body.get("status"), dict) else {}
    task_status = task.get("status") if isinstance(task.get("status"), dict) else {}

    team_name = body.get("team_name") or body.get("teamName")
    task_id = body.get("task_id") or body.get("taskId") or task.get("id")
    state = body.get("state") or status.get("state") or task_status.get("state")
    sequence = body.get("sequence")
    signature = headers.get("x-a2a-notification-token")
    if not team_name or not task_id or not state or sequence is None or not signature:
        return {"status": 400, "body": {"error": "missing required push fields"}}

    team_dir = factory_dir / "teams" / str(team_name)
    try:
        transport = read_json(team_dir / "transport.json")
    except FileNotFoundError:
        return {"status": 404, "body": {"error": "unknown team"}}

    expected_bearer = secrets.resolve(transport.get("push_token_ref"))
    if bearer_from_header(headers.get("authorization")) != expected_bearer:
        return {"status": 401, "body": {"error": "invalid bearer token"}}

    hmac_secret = secrets.resolve(transport.get("bridge_secret_ref") or transport.get("push_token_ref"))
    if not verify_push_signature(
        expected=signature,
        secret=hmac_secret,
        team_name=str(team_name),
        task_id=str(task_id),
        state=str(state),
        sequence=sequence,
        body=body,
    ):
        return {"status": 401, "body": {"error": "invalid push signature"}}

    assignment = db.get_assignment_by_task(str(team_name), str(task_id))
    if assignment is None and body.get("kind") != "peer-registration":
        return {"status": 404, "body": {"error": "unknown task"}}

    assignment_id = assignment["assignment_id"] if assignment else None
    event = db.append_event(
        team_name=str(team_name),
        assignment_id=assignment_id,
        task_id=str(task_id),
        sequence=int(sequence),
        source="a2a-push",
        kind="push",
        state=str(state),
        cost_cents=body.get("cost_cents"),
        duration_ms=body.get("duration_ms"),
        signature=signature,
        metadata=body.get("metadata") or {},
    )
    if not event["inserted"]:
        db.append_event(
            team_name=str(team_name),
            assignment_id=assignment_id,
            task_id=str(task_id),
            source="a2a-push",
            kind="push-duplicate",
            state=str(state),
            signature=signature,
            metadata={"duplicate_sequence": sequence},
        )
        return {"status": 202, "body": {"duplicate": True}}

    write_json(
        team_dir / "status.json",
        {
            "team_name": team_name,
            "task_id": task_id,
            "assignment_id": assignment_id,
            "state": state,
            "sequence": sequence,
            "updated_at": utc_now(),
            "message": body.get("message") or status.get("message") or None,
        },
    )

    if state == "working" and assignment_id:
        append_journal(team_dir, f"working {assignment_id}: {body.get('message') or ''}".strip())
        db.update_assignment_status(assignment_id=assignment_id, status="working")
    elif state in {"input-required", "auth-required"} and assignment_id:
        escalation_dir = ensure_dir(factory_dir / "escalations")
        kind = "secret-request" if state == "auth-required" else "input-required"
        path = escalation_dir / f"{team_name}_{assignment_id}_{kind}.md"
        path.write_text(f"# {kind}: {team_name}\n\n{body.get('message') or json.dumps(body, indent=2, sort_keys=True)}\n", encoding="utf-8")
        db.update_assignment_status(assignment_id=assignment_id, status=str(state))
    elif state == "completed" and assignment_id:
        outbox = ensure_dir(team_dir / "outbox")
        artifacts = body.get("artifacts") or task.get("artifacts") or [
            {"name": f"{assignment_id}.result.md", "text": body.get("message") or json.dumps(body, indent=2, sort_keys=True)}
        ]
        written = []
        for index, artifact in enumerate(artifacts):
            path = outbox / artifact_name(artifact, index)
            path.write_text(artifact_text(artifact), encoding="utf-8")
            written.append(path)
        db.mark_terminal(assignment_id=assignment_id, status="completed", completed_path=written[0] if written else None)
    elif state == "failed" and assignment_id:
        escalation_dir = ensure_dir(factory_dir / "escalations")
        path = escalation_dir / f"{team_name}_{assignment_id}_failed.md"
        path.write_text(f"# failed: {team_name}\n\n{body.get('message') or json.dumps(body, indent=2, sort_keys=True)}\n", encoding="utf-8")
        db.mark_terminal(assignment_id=assignment_id, status="failed")
        db.append_event(
            team_name=str(team_name),
            assignment_id=assignment_id,
            task_id=str(task_id),
            source="a2a-bridge",
            kind="decision",
            state="failed",
            payload_path=path,
        )
    elif state == "canceled" and assignment_id:
        db.mark_terminal(assignment_id=assignment_id, status="canceled")

    return {"status": 202, "body": {"ok": True}}
