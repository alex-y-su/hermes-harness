from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from harness_remote.hermes_runner import AssignmentRunner, RunnerError, build_runner
from harness_remote.push_client import build_push_event, post_push_event


@dataclass(frozen=True)
class RemoteRuntimeConfig:
    team_name: str
    push_url: str
    push_token: str
    bridge_secret: str
    artifact_text: str = "Mock remote runtime completed the assignment."
    complete_delay_seconds: float = 0.05
    host: str = "127.0.0.1"
    port: int = 0
    runner_mode: str = "mock"
    runner_command: str | None = None
    runner_timeout_seconds: int = 900
    workspace: str = "/home/user/workspace"


def _read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("content-length") or "0")
    if length <= 0:
        return {}
    return json.loads(handler.rfile.read(length).decode("utf-8"))


class RemoteRuntimeServer:
    """Small A2A-compatible test/runtime server.

    This is intentionally not a Hermes replacement. It provides the remote-team
    network contract so the local bridge can be proven before a real Hermes
    profile and Codex OAuth are introduced in the sandbox.
    """

    def __init__(self, config: RemoteRuntimeConfig) -> None:
        self.config = config
        self.httpd = ThreadingHTTPServer((config.host, config.port), self._handler_class())
        self.thread: threading.Thread | None = None
        self.tasks: dict[str, dict[str, Any]] = {}
        self.runner: AssignmentRunner = build_runner(
            mode=config.runner_mode,
            artifact_text=config.artifact_text,
            command=config.runner_command,
            workspace=Path(config.workspace),
            timeout_seconds=config.runner_timeout_seconds,
        )

    @property
    def port(self) -> int:
        return int(self.httpd.server_address[1])

    @property
    def base_url(self) -> str:
        return f"http://{self.config.host}:{self.port}"

    @property
    def agent_card_url(self) -> str:
        return f"{self.base_url}/.well-known/agent-card.json"

    def start(self) -> None:
        self.thread = threading.Thread(target=self.httpd.serve_forever, name="harness-remote-runtime", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)

    def serve_forever(self) -> None:
        try:
            self.httpd.serve_forever()
        finally:
            self.httpd.server_close()

    def agent_card(self) -> dict[str, Any]:
        return {
            "name": f"{self.config.team_name} remote runtime",
            "description": "Hermes Harness remote runtime",
            "url": "/a2a/jsonrpc",
            "version": "0.1.0",
            "capabilities": {"streaming": False, "pushNotifications": True},
            "additionalInterfaces": [{"transport": "JSONRPC", "url": "/a2a/jsonrpc"}],
            "defaultInputModes": ["text/markdown"],
            "defaultOutputModes": ["text/markdown", "application/json"],
        }

    def handle_message_send(self, params: dict[str, Any]) -> dict[str, Any]:
        metadata = params.get("metadata") if isinstance(params.get("metadata"), dict) else {}
        message = params.get("message") if isinstance(params.get("message"), dict) else {}
        message_metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
        assignment_id = str(metadata.get("assignment_id") or message_metadata.get("assignment_id") or uuid.uuid4().hex[:12])
        task_id = f"task-{assignment_id}"
        assignment_text = extract_message_text(message)
        self.tasks[task_id] = {"assignment_id": assignment_id, "state": "submitted", "text": assignment_text}
        threading.Thread(
            target=self._complete_task,
            args=(assignment_id, task_id, assignment_text),
            name=f"harness-remote-complete-{assignment_id}",
            daemon=True,
        ).start()
        return {"id": task_id, "kind": "task", "status": {"state": "submitted"}}

    def handle_cancel(self, params: dict[str, Any]) -> dict[str, Any]:
        task_id = str(params.get("id") or params.get("task_id") or "")
        if task_id:
            self.tasks[task_id] = {"state": "canceled"}
            self._push(task_id=task_id, state="canceled", sequence=99, message="canceled by boss")
        return {"id": task_id, "kind": "task", "status": {"state": "canceled"}}

    def _complete_task(self, assignment_id: str, task_id: str, assignment_text: str) -> None:
        time.sleep(max(0.0, self.config.complete_delay_seconds))
        self._push(task_id=task_id, state="working", sequence=1, message=f"started {assignment_id}")
        try:
            result = self.runner.run(assignment_id=assignment_id, task_id=task_id, assignment_text=assignment_text)
            artifact = {
                "name": f"{assignment_id}.result.md",
                "text": result.text,
                "metadata": result.metadata,
            }
            self.tasks[task_id] = {"assignment_id": assignment_id, "state": "completed"}
            self._push(
                task_id=task_id,
                state="completed",
                sequence=2,
                message=f"completed {assignment_id}",
                artifacts=[artifact],
            )
        except RunnerError as error:
            self.tasks[task_id] = {"assignment_id": assignment_id, "state": "failed", "error": str(error)}
            self._push(task_id=task_id, state="failed", sequence=2, message=str(error))

    def _push(
        self,
        *,
        task_id: str,
        state: str,
        sequence: int,
        message: str,
        artifacts: list[dict[str, Any]] | None = None,
    ) -> None:
        event = build_push_event(
            team_name=self.config.team_name,
            task_id=task_id,
            state=state,
            sequence=sequence,
            message=message,
            artifacts=artifacts,
        )
        post_push_event(
            push_url=self.config.push_url,
            bearer_token=self.config.push_token,
            bridge_secret=self.config.bridge_secret,
            event=event,
        )

    def _handler_class(self) -> type[BaseHTTPRequestHandler]:
        runtime = self

        class RemoteHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if self.path == "/.well-known/agent-card.json":
                    self._send_json(200, runtime.agent_card())
                    return
                if self.path == "/health":
                    self._send_json(200, {"ok": True})
                    return
                self._send_json(404, {"error": "not found"})

            def do_POST(self) -> None:
                if self.path != "/a2a/jsonrpc":
                    self._send_json(404, {"error": "not found"})
                    return
                try:
                    body = _read_json_body(self)
                    method = body.get("method")
                    params = body.get("params") if isinstance(body.get("params"), dict) else {}
                    if method == "message/send":
                        result = runtime.handle_message_send(params)
                    elif method == "tasks/cancel":
                        result = runtime.handle_cancel(params)
                    else:
                        self._send_json(200, {"jsonrpc": "2.0", "id": body.get("id"), "error": {"code": -32601, "message": "method not found"}})
                        return
                    self._send_json(200, {"jsonrpc": "2.0", "id": body.get("id"), "result": result})
                except Exception as error:
                    self._send_json(500, {"error": str(error)})

            def log_message(self, format: str, *args: Any) -> None:
                return

            def _send_json(self, status: int, body: dict[str, Any]) -> None:
                payload = json.dumps(body, sort_keys=True).encode("utf-8")
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        return RemoteHandler


def extract_message_text(message: dict[str, Any]) -> str:
    parts = message.get("parts")
    if not isinstance(parts, list):
        return ""
    rendered = []
    for part in parts:
        if isinstance(part, dict) and part.get("text") is not None:
            rendered.append(str(part["text"]))
        elif isinstance(part, dict):
            rendered.append(json.dumps(part, sort_keys=True))
        else:
            rendered.append(str(part))
    return "\n".join(rendered)
