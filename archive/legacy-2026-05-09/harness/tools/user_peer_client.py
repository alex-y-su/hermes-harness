from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _bridge_db(db_path: str | Path):
    from harness.bridge.store import BridgeDb

    return BridgeDb(db_path)


def notify_user_context(*, db_path: str | Path, context_id: str, message: str) -> dict[str, Any]:
    """Look up user_contexts.push_url; if set, POST a push event there."""
    bridge = _bridge_db(db_path)
    ctx = bridge.get_user_context(context_id)
    if ctx is None:
        return {"ok": False, "status": 0, "error": f"no user_context for {context_id}"}
    push_url = ctx["push_url"]
    if not push_url:
        return {"ok": False, "status": 0, "error": "user_context has no push_url"}
    push_token = ctx["push_token"]
    payload = json.dumps(
        {
            "context_id": context_id,
            "task_id": ctx["task_id"],
            "message": message,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if push_token:
        headers["Authorization"] = f"Bearer {push_token}"
    request = Request(push_url, data=payload, method="POST", headers=headers)
    try:
        with urlopen(request, timeout=10) as response:
            return {"ok": True, "status": response.status, "error": None}
    except HTTPError as error:
        return {"ok": False, "status": error.code, "error": error.read().decode("utf-8", errors="replace")}
    except (URLError, TimeoutError) as error:
        return {"ok": False, "status": 0, "error": str(error)}


def message_peer(
    *,
    db_path: str | Path,
    peer_id: str,
    message: str,
    context_id: str | None = None,
) -> dict[str, Any]:
    """Cold-start dispatch: POST JSON-RPC `message/send` to the peer's agent card url."""
    bridge = _bridge_db(db_path)
    peer = bridge.get_user_peer(peer_id)
    if peer is None:
        return {"error": f"unknown peer_id {peer_id}"}
    card = json.loads(peer["agent_card_json"])
    endpoint = card.get("url")
    if not endpoint:
        return {"error": "peer agent card has no url"}
    access_token = peer["access_token"]

    task_id: str | None = None
    if context_id is None:
        context_id = f"ctx-{uuid.uuid4().hex[:16]}"
        task_id = f"task-{uuid.uuid4().hex[:16]}"
        bridge.upsert_user_context(
            context_id=context_id,
            peer_id=peer_id,
            task_id=task_id,
            status="outbound",
        )

    msg: dict[str, Any] = {
        "kind": "message",
        "role": "agent",
        "messageId": str(uuid.uuid4()),
        "contextId": context_id,
        "parts": [{"kind": "text", "text": message}],
    }
    if task_id:
        msg["taskId"] = task_id

    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "message/send",
            "params": {"message": msg},
        },
        separators=(",", ":"),
    ).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    request = Request(endpoint, data=body, method="POST", headers=headers)
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        return {"error": f"HTTP {error.code}: {error.read().decode('utf-8', errors='replace')}"}
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        return {"error": str(error)}
