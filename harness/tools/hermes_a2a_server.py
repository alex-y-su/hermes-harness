from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


def _read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("content-length") or "0")
    if length <= 0:
        return {}
    return json.loads(handler.rfile.read(length).decode("utf-8"))


def _message_text(message: dict[str, Any]) -> str:
    parts = message.get("parts")
    if not isinstance(parts, list):
        return ""
    rendered: list[str] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        text = part.get("text")
        if isinstance(text, str):
            rendered.append(text)
    return "\n\n".join(rendered).strip()


BOSS_A2A_CONTEXT = """You are receiving this message through the public Hermes Harness boss A2A endpoint.
Answer as `boss`, the user-facing coordinator for the Hermes Harness boss team.
The boss team has exactly six profiles: boss, supervisor, hr, conductor, critic, and a2a-bridge.
Only boss is user-facing; the other profiles are internal roles coordinated through the local factory bus.
If the user asks how many people or agents are in your team, name these six profiles and do not answer as a single generic chat assistant.
Specialist and execution roles from docs/team are hireable remote teams, not local hub profiles.
hr creates those teams from `/factory/team_blueprints` into `/factory/teams/<name>/` and executes active work on E2B.
Operational ground truth for this deployment:
- The live factory is `/factory`. Do not create state under `/app/factory`.
- Use `python3 -m harness.tools.spawn_team --factory /factory --substrate e2b --template multi-agent --blueprint <team> <team>` to create docs/team specialist/execution teams.
- Use `python3 -m harness.tools.dispatch_team --factory /factory ...` to assign work to teams.
- Use `python3 -m harness.tools.query_remote_teams --factory /factory --json` to report remote-team state.
- Use `/home/dev/.local/bin/hermes --profile boss cron ...` for scheduled autonomous boss/profile work on VM 211.
- Boss cron scripts must be written under `/opt/hermes-home/profiles/boss/scripts/`; script names passed to `hermes --profile boss cron create --script` are resolved relative to that directory.
- The live VM deployment is host-native systemd, not Docker.
- When the user asks you to create, schedule, dispatch, or inspect, actually use tools/commands and then report the resulting files, IDs, and status.
"""


def _task_id(params: dict[str, Any], message: dict[str, Any]) -> str:
    candidate = params.get("id") or params.get("taskId") or message.get("taskId") or message.get("task_id")
    return str(candidate or f"task-{uuid.uuid4().hex[:16]}")


def _context_id(task_id: str, message: dict[str, Any]) -> str:
    return str(message.get("contextId") or message.get("context_id") or task_id)


def _task_result(task_id: str, state: str, text: str = "", *, native: bool, context_id: str = "") -> dict[str, Any]:
    if not native:
        task: dict[str, Any] = {"id": task_id, "status": {"state": "working" if state == "submitted" else state}}
        if text:
            task["artifacts"] = [{"parts": [{"type": "text", "text": text}], "index": 0}]
        return task

    task = {
        "kind": "task",
        "id": task_id,
        "contextId": context_id or task_id,
        "status": {"state": state},
    }
    if text:
        task["status"]["message"] = {
            "kind": "message",
            "messageId": f"{task_id}-status",
            "role": "agent",
            "parts": [{"kind": "text", "text": text}],
        }
        task["artifacts"] = [
            {
                "artifactId": f"{task_id}-artifact-0",
                "name": "response.md",
                "parts": [{"kind": "text", "text": text}],
            }
        ]
    return task


class HermesA2ARuntime:
    def __init__(
        self,
        *,
        profile: str,
        host: str,
        port: int,
        token: str,
        hermes_bin: str,
        model: str,
        timeout_seconds: int,
        agent_name: str = "",
        description: str = "",
        public_url: str = "",
    ) -> None:
        self.profile = profile
        self.agent_name = agent_name or profile
        self.description = description or f"Hermes Harness boss-team profile: {profile}"
        self.host = host
        self.port = port
        self.token = token
        self.hermes_bin = hermes_bin
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.public_url = public_url.rstrip("/") if public_url else f"http://{self.host}:{self.port}"
        self.tasks: dict[str, dict[str, Any]] = {}

    def agent_card(self) -> dict[str, Any]:
        return {
            "name": self.agent_name,
            "description": self.description,
            "url": f"{self.public_url}/",
            "version": "0.1.0",
            "preferredTransport": "JSONRPC",
            "protocolVersion": "0.3.0",
            "capabilities": {"streaming": False, "pushNotifications": False},
            "defaultInputModes": ["text"],
            "defaultOutputModes": ["text/markdown"],
            "skills": [
                {
                    "id": "hermes_profile",
                    "name": "Hermes profile",
                    "description": f"Runs the official Hermes Agent `{self.profile}` profile.",
                    "tags": ["hermes", "boss-team"],
                }
            ],
        }

    def send_message(self, params: dict[str, Any], *, native: bool, wrapped: bool = False) -> dict[str, Any]:
        message = params.get("message") if isinstance(params.get("message"), dict) else {}
        text = _message_text(message)
        task_id = _task_id(params, message)
        context_id = _context_id(task_id, message)
        self.tasks[task_id] = _task_result(task_id, "working", native=native, context_id=context_id)
        self.tasks[task_id]["createdAt"] = time.time()
        try:
            answer = self._run_hermes(text)
            task = _task_result(task_id, "completed", answer, native=native, context_id=context_id)
            self.tasks[task_id] = task
            return {"task": task} if wrapped else task
        except Exception as exc:
            task = _task_result(task_id, "failed", str(exc), native=native, context_id=context_id)
            self.tasks[task_id] = task
            return {"task": task} if wrapped else task

    def get_task(self, params: dict[str, Any], *, native: bool, wrapped: bool = False) -> dict[str, Any]:
        task_id = str(params.get("id") or params.get("taskId") or "")
        task = self.tasks.get(task_id) or _task_result(task_id, "unknown", native=native)
        return {"task": task} if wrapped else task

    def cancel_task(self, params: dict[str, Any], *, native: bool, wrapped: bool = False) -> dict[str, Any]:
        task_id = str(params.get("id") or params.get("taskId") or "")
        task = _task_result(task_id, "canceled", native=native)
        self.tasks[task_id] = task
        return {"task": task} if wrapped else task

    def _run_hermes(self, prompt: str) -> str:
        if not prompt:
            prompt = "Respond with a short status message."
        if self.profile == "boss":
            prompt = f"{BOSS_A2A_CONTEXT}\n\nUser message:\n{prompt}"
        env = dict(os.environ)
        if env.get("FACTORY_DIR") and not env.get("HARNESS_FACTORY"):
            env["HARNESS_FACTORY"] = env["FACTORY_DIR"]
        for key in list(env):
            if key.startswith("OPENAI_") or key.startswith("OPENROUTER_") or key == "LLM_BASE_URL":
                env.pop(key, None)
        args = [
            self.hermes_bin,
            "--profile",
            self.profile,
            "-z",
            prompt,
            "--provider",
            "openai-codex",
            "--model",
            self.model,
            "--accept-hooks",
        ]
        completed = subprocess.run(
            args,
            env=env,
            text=True,
            capture_output=True,
            timeout=self.timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise RuntimeError(f"Hermes exited {completed.returncode}: {detail}")
        output = (completed.stdout or "").strip()
        if not output:
            raise RuntimeError("Hermes produced no output")
        return output


def build_handler(runtime: HermesA2ARuntime) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path in {"/.well-known/agent.json", "/.well-known/agent-card.json"}:
                self._send_json(200, runtime.agent_card())
                return
            if self.path == "/health":
                self._send_json(200, {"ok": True, "profile": runtime.profile})
                return
            self._send_json(404, {"error": "not found"})

        def do_POST(self) -> None:
            if self.path != "/":
                self._send_json(404, {"error": "not found"})
                return
            if runtime.token:
                expected = f"Bearer {runtime.token}"
                if self.headers.get("authorization") != expected:
                    self._send_json(401, {"error": "unauthorized"})
                    return
            try:
                body = _read_json(self)
                method = str(body.get("method") or "")
                params = body.get("params") if isinstance(body.get("params"), dict) else {}
                if method in {"SendMessage", "message/send", "tasks/send", "task/send"}:
                    result = runtime.send_message(
                        params,
                        native=method in {"SendMessage", "message/send"},
                        wrapped=method == "SendMessage",
                    )
                elif method in {"GetTask", "tasks/get", "task/get"}:
                    result = runtime.get_task(params, native=method == "GetTask", wrapped=method == "GetTask")
                elif method in {"CancelTask", "tasks/cancel", "task/cancel"}:
                    result = runtime.cancel_task(params, native=method == "CancelTask", wrapped=method == "CancelTask")
                else:
                    self._send_json(200, {"jsonrpc": "2.0", "id": body.get("id"), "error": {"code": -32601, "message": "method not found"}})
                    return
                self._send_json(200, {"jsonrpc": "2.0", "id": body.get("id"), "result": result})
            except Exception as exc:
                self._send_json(500, {"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(exc)}})

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _send_json(self, status: int, body: dict[str, Any]) -> None:
            payload = json.dumps(body, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    return Handler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Expose one Hermes profile over A2A JSON-RPC.")
    parser.add_argument("--profile", required=True)
    parser.add_argument("--host", default=os.getenv("HERMES_A2A_BIND_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--token", default="")
    parser.add_argument("--hermes-bin", default=os.getenv("HERMES_BIN", str(os.path.expanduser("~/.local/bin/hermes"))))
    parser.add_argument("--model", default=os.getenv("HERMES_HARNESS_CODEX_MODEL", "gpt-5.3-codex"))
    parser.add_argument("--timeout-seconds", type=int, default=int(os.getenv("HERMES_A2A_TURN_TIMEOUT_SECONDS", "900")))
    parser.add_argument("--agent-name", default=os.getenv("HERMES_A2A_AGENT_NAME", ""))
    parser.add_argument("--description", default=os.getenv("HERMES_A2A_AGENT_DESCRIPTION", ""))
    parser.add_argument("--public-url", default=os.getenv("HERMES_A2A_PUBLIC_URL", ""))
    args = parser.parse_args(argv)

    runtime = HermesA2ARuntime(
        profile=args.profile,
        host=args.host,
        port=args.port,
        token=args.token,
        hermes_bin=args.hermes_bin,
        model=args.model,
        timeout_seconds=args.timeout_seconds,
        agent_name=args.agent_name,
        description=args.description,
        public_url=args.public_url,
    )
    server = ThreadingHTTPServer((args.host, args.port), build_handler(runtime))
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
