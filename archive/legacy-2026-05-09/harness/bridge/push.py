from __future__ import annotations

import json
import re
import asyncio
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


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")[:100] or "request"


def _request_id(body: dict[str, Any], assignment_id: str, kind: str, sequence: Any) -> str:
    metadata = body.get("metadata") if isinstance(body.get("metadata"), dict) else {}
    explicit = body.get("request_id") or body.get("requestId") or metadata.get("request_id") or metadata.get("requestId")
    if explicit:
        return str(explicit)
    return f"{assignment_id}:{kind}:{sequence}"


def _message_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        if value.get("text") is not None:
            return str(value["text"])
        if value.get("message") is not None:
            return str(value["message"])
    return json.dumps(value, indent=2, sort_keys=True)


def _request_fields(body: dict[str, Any], status: dict[str, Any]) -> list[Any] | dict[str, Any]:
    metadata = body.get("metadata") if isinstance(body.get("metadata"), dict) else {}
    for source in (body, status, metadata):
        for key in ("required_fields", "requiredFields", "fields"):
            value = source.get(key)
            if isinstance(value, list | dict):
                return value
    return []


def _write_user_request_escalation(
    *,
    factory_dir: Path,
    team_name: str,
    assignment_id: str,
    task_id: str,
    request_id: str,
    kind: str,
    title: str,
    prompt: str,
    required_fields: list[Any] | dict[str, Any],
) -> Path:
    escalation_dir = ensure_dir(factory_dir / "escalations")
    path = escalation_dir / f"{_slug(team_name)}_{_slug(request_id)}.md"
    path.write_text(
        f"# {title}\n\n"
        f"- request_id: {request_id}\n"
        f"- team: {team_name}\n"
        f"- assignment_id: {assignment_id}\n"
        f"- task_id: {task_id}\n"
        f"- kind: {kind}\n"
        f"- status: open\n\n"
        f"## Prompt\n\n{prompt}\n\n"
        f"## Required Fields\n\n```json\n{json.dumps(required_fields, indent=2, sort_keys=True)}\n```\n\n"
        "## Resolution\n\n"
        f"Use `python3 -m harness.tools.resolve_user_request --factory <factory> {request_id} --response-json '{{}}'`.\n",
        encoding="utf-8",
    )
    return path


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
        db.mark_assignment_heartbeat(assignment_id=assignment_id, status="working")
    elif state in {"input-required", "auth-required"} and assignment_id:
        kind = "auth-required" if state == "auth-required" else "input-required"
        request_id = _request_id(body, assignment_id, kind, sequence)
        prompt = (
            _message_text(body.get("prompt"))
            or _message_text(body.get("message"))
            or _message_text(status.get("message"))
            or json.dumps(body, indent=2, sort_keys=True)
        )
        title = str(body.get("title") or ("Authentication required" if kind == "auth-required" else "User input required"))
        required_fields = _request_fields(body, status)
        path = _write_user_request_escalation(
            factory_dir=factory_dir,
            team_name=str(team_name),
            assignment_id=assignment_id,
            task_id=str(task_id),
            request_id=request_id,
            kind=kind,
            title=title,
            prompt=prompt,
            required_fields=required_fields,
        )
        db.upsert_approval_request(
            request_id=request_id,
            assignment_id=assignment_id,
            team_name=str(team_name),
            task_id=str(task_id),
            kind=kind,
            status="open",
            title=title,
            prompt=prompt,
            required_fields=required_fields,
            escalation_path=path,
            metadata={
                "push_sequence": sequence,
                "push_state": state,
                "resume": "TODO: send supplied response back through A2A resume when supported",
            },
        )
        db.mark_assignment_blocked(
            assignment_id=assignment_id,
            status=str(state),
            blocked_by=request_id,
            reason=title,
        )
        db.append_event(
            team_name=str(team_name),
            assignment_id=assignment_id,
            task_id=str(task_id),
            source="a2a-bridge",
            kind="user-request-opened",
            state=kind,
            payload_path=path,
            metadata={"request_id": request_id},
        )
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
        db.release_lease(resource_type="assignment", resource_id=assignment_id)
        _finalize_assignment_sandbox_if_present(db, secrets, factory_dir, str(team_name), assignment_id, "completed")
    elif state == "failed" and assignment_id:
        escalation_dir = ensure_dir(factory_dir / "escalations")
        path = escalation_dir / f"{team_name}_{assignment_id}_failed.md"
        path.write_text(f"# failed: {team_name}\n\n{body.get('message') or json.dumps(body, indent=2, sort_keys=True)}\n", encoding="utf-8")
        db.mark_terminal(assignment_id=assignment_id, status="failed")
        db.release_lease(resource_type="assignment", resource_id=assignment_id)
        _finalize_assignment_sandbox_if_present(db, secrets, factory_dir, str(team_name), assignment_id, "failed")
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
        db.release_lease(resource_type="assignment", resource_id=assignment_id)
        _finalize_assignment_sandbox_if_present(db, secrets, factory_dir, str(team_name), assignment_id, "canceled")

    return {"status": 202, "body": {"ok": True}}


def _finalize_assignment_sandbox_if_present(
    db: BridgeDb,
    secrets: SecretResolver,
    factory_dir: Path,
    team_name: str,
    assignment_id: str,
    terminal_state: str,
) -> None:
    sandbox = db.get_assignment_sandbox(assignment_id)
    if sandbox is None or sandbox["status"] == "archived":
        return
    metadata = json.loads(sandbox["metadata"] or "{}")
    dry_run = bool(metadata.get("dry_run"))
    api_key = None if dry_run else secrets.resolve("env://E2B_API_KEY")
    from harness.tools.finalize_assignment_sandbox import finalize_assignment

    asyncio.run(
        finalize_assignment(
            factory=factory_dir,
            db_path=db.db_path,
            team=team_name,
            assignment_id=assignment_id,
            terminal_state=terminal_state,
            dry_run=dry_run,
            api_key=api_key,
        )
    )
