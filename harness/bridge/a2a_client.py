from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


class A2AClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class SendAssignmentResult:
    task_id: str
    result: dict[str, Any]


def base_url_from_agent_card_url(agent_card_url: str) -> str:
    parsed = urlparse(agent_card_url)
    suffix = "/.well-known/agent-card.json"
    path = parsed.path
    if path.endswith(suffix):
        path = path[: -len(suffix)] or "/"
    return parsed._replace(path=path, query="", fragment="").geturl().rstrip("/")


def extract_task_id(result: Any) -> str | None:
    if isinstance(result, dict):
        if result.get("id") and result.get("kind") == "task":
            return str(result["id"])
        task = result.get("task")
        if isinstance(task, dict) and task.get("id"):
            return str(task["id"])
        nested = result.get("result")
        if isinstance(nested, dict):
            if nested.get("id"):
                return str(nested["id"])
            nested_task = nested.get("task")
            if isinstance(nested_task, dict) and nested_task.get("id"):
                return str(nested_task["id"])
    return None


class A2AClient:
    def __init__(self, timeout_seconds: float = 30.0) -> None:
        self.timeout_seconds = timeout_seconds

    def send_assignment(
        self,
        *,
        transport: dict[str, Any],
        bearer_token: str,
        push_token: str | None,
        assignment_id: str,
        text: str,
    ) -> SendAssignmentResult:
        endpoint = self._resolve_endpoint(transport, bearer_token)
        params = {
            "configuration": {
                "blocking": False,
                "acceptedOutputModes": ["text/markdown", "application/json"],
            },
            "message": {
                "kind": "message",
                "role": "user",
                "messageId": str(uuid.uuid4()),
                "metadata": {"assignment_id": assignment_id},
                "parts": [{"kind": "text", "text": text}],
            },
            "metadata": {"assignment_id": assignment_id},
        }
        if transport.get("push_url"):
            params["configuration"]["pushNotificationConfig"] = {
                "id": assignment_id,
                "url": transport["push_url"],
                "token": push_token,
                "authentication": {"schemes": ["Bearer"], "credentials": push_token},
            }

        result = self._json_rpc(endpoint, bearer_token, "message/send", params)
        task_id = extract_task_id(result)
        if not task_id:
            raise A2AClientError("A2A message/send response did not include a task id")
        return SendAssignmentResult(task_id=task_id, result=result)

    def cancel_task(self, *, transport: dict[str, Any], bearer_token: str, task_id: str) -> Any:
        endpoint = self._resolve_endpoint(transport, bearer_token)
        return self._json_rpc(endpoint, bearer_token, "tasks/cancel", {"id": task_id})

    def _resolve_endpoint(self, transport: dict[str, Any], bearer_token: str) -> str:
        direct = transport.get("endpoint_url") or transport.get("a2a_url")
        if direct:
            return str(direct)
        agent_card_url = transport.get("agent_card_url")
        if not agent_card_url:
            raise A2AClientError("transport.json needs agent_card_url, endpoint_url, or a2a_url")

        card = self._get_json(str(agent_card_url), bearer_token)
        for interface in card.get("additionalInterfaces") or card.get("additional_interfaces") or []:
            if str(interface.get("transport", "")).upper() in {"JSONRPC", "JSON-RPC"} and interface.get("url"):
                return urljoin(base_url_from_agent_card_url(str(agent_card_url)) + "/", str(interface["url"]))
        if card.get("url"):
            return urljoin(base_url_from_agent_card_url(str(agent_card_url)) + "/", str(card["url"]))
        raise A2AClientError(f"agent card did not expose a JSON-RPC endpoint: {agent_card_url}")

    def _get_json(self, url: str, bearer_token: str) -> dict[str, Any]:
        request = Request(url, headers={"Authorization": f"Bearer {bearer_token}", "Accept": "application/json"})
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
            raise A2AClientError(f"failed to fetch A2A agent card {url}: {error}") from error

    def _json_rpc(self, endpoint: str, bearer_token: str, method: str, params: dict[str, Any]) -> Any:
        body = json.dumps(
            {"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": method, "params": params},
            separators=(",", ":"),
        ).encode("utf-8")
        request = Request(
            endpoint,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {bearer_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise A2AClientError(f"A2A {method} failed with HTTP {error.code}: {detail}") from error
        except (URLError, TimeoutError, json.JSONDecodeError) as error:
            raise A2AClientError(f"A2A {method} failed: {error}") from error
        if isinstance(payload, dict) and payload.get("error"):
            raise A2AClientError(f"A2A {method} returned JSON-RPC error: {payload['error']}")
        return payload.get("result") if isinstance(payload, dict) and "result" in payload else payload
