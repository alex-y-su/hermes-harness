from __future__ import annotations

import json
import os
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from harness.bridge.a2a_client import A2AClient
from harness.bridge.cancel import cancel_team
from harness.bridge.dispatch import dispatch_assignment
from harness.bridge.fs_contract import discover_teams, ensure_dir, utc_now, write_json
from harness.bridge.push import artifact_name, artifact_text, process_push
from harness.bridge.secrets import SecretResolver
from harness.bridge.store import BridgeDb


def _read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("content-length") or "0")
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    return json.loads(raw.decode("utf-8"))


class BridgeDaemon:
    def __init__(
        self,
        *,
        factory_dir: str | Path,
        db: BridgeDb,
        secrets: SecretResolver,
        port: int | str = 8787,
        poll_ms: int | str = 2000,
        a2a_client: A2AClient | Any | None = None,
        e2b_dry_run: bool = False,
        retry_delay_seconds: int = 60,
        max_retries: int = 3,
        assignment_lease_ttl_seconds: int = 300,
    ) -> None:
        self.factory_dir = Path(factory_dir)
        self.db = db
        self.secrets = secrets
        self.port = int(port)
        self.poll_seconds = int(poll_ms) / 1000
        self.a2a_client = a2a_client or A2AClient()
        self.e2b_dry_run = e2b_dry_run
        self.retry_delay_seconds = int(retry_delay_seconds)
        self.max_retries = int(max_retries)
        self.assignment_lease_ttl_seconds = int(assignment_lease_ttl_seconds)
        self.seen_halts: set[str] = set()
        self.in_progress: set[Path] = set()
        self.stop_event = threading.Event()
        self.server: ThreadingHTTPServer | None = None
        self.http_thread: threading.Thread | None = None
        self.loop_thread: threading.Thread | None = None

    def start(self) -> None:
        self.server = ThreadingHTTPServer(("0.0.0.0", self.port), self._handler_class())
        self.http_thread = threading.Thread(target=self.server.serve_forever, name="a2a-bridge-http", daemon=True)
        self.http_thread.start()
        self.heartbeat()
        self.tick()
        self.loop_thread = threading.Thread(target=self._run_loop, name="a2a-bridge-loop", daemon=True)
        self.loop_thread.start()

    def serve_forever(self) -> None:
        self.start()
        while not self.stop_event.is_set():
            time.sleep(0.2)

    def stop(self) -> None:
        self.stop_event.set()
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        if self.loop_thread and self.loop_thread.is_alive():
            self.loop_thread.join(timeout=5)
        if self.http_thread and self.http_thread.is_alive():
            self.http_thread.join(timeout=5)

    def heartbeat(self) -> None:
        write_json(
            self.factory_dir / "status" / "a2a-bridge.json",
            {
                "service": "a2a-bridge",
                "state": "halting" if (self.factory_dir / "HALT_a2a-bridge.flag").exists() else "running",
                "pid": os.getpid(),
                "port": self.port,
                "updated_at": utc_now(),
            },
        )

    def record_error(self, error: Exception) -> None:
        self.db.append_event(
            team_name="a2a-bridge",
            source="a2a-bridge",
            kind="error",
            state="failed",
            metadata={"error": str(error)},
        )

    def tick(self) -> None:
        if (self.factory_dir / "HALT_a2a-bridge.flag").exists():
            self.stop_event.set()
            return
        for team_name, team_dir in discover_teams(self.factory_dir):
            self.process_team(team_name, team_dir)

    def process_team(self, team_name: str, team_dir: Path) -> None:
        if (team_dir / "HALT.flag").exists() and team_name not in self.seen_halts:
            self.seen_halts.add(team_name)
            cancel_team(
                db=self.db,
                secrets=self.secrets,
                a2a_client=self.a2a_client,
                factory_dir=self.factory_dir,
                team_name=team_name,
                team_dir=team_dir,
            )
            return

        inbox = ensure_dir(team_dir / "inbox")
        for path in sorted(inbox.iterdir()):
            if not path.name.endswith(".md") or path.name.endswith(".in-flight.md"):
                continue
            if not path.is_file() or path in self.in_progress:
                continue
            self.in_progress.add(path)
            try:
                dispatch_assignment(
                    db=self.db,
                    secrets=self.secrets,
                    a2a_client=self.a2a_client,
                    team_name=team_name,
                    team_dir=team_dir,
                    inbox_path=path,
                    factory_dir=self.factory_dir,
                    db_path=self.db.db_path,
                    e2b_dry_run=self.e2b_dry_run,
                    retry_delay_seconds=self.retry_delay_seconds,
                    max_retries=self.max_retries,
                    lease_ttl_seconds=self.assignment_lease_ttl_seconds,
                    lease_holder=f"a2a-bridge:{os.getpid()}",
                )
            finally:
                self.in_progress.discard(path)
        self.poll_external_team(team_name, team_dir)

    def poll_external_team(self, team_name: str, team_dir: Path) -> None:
        transport = _read_transport(team_dir)
        if not transport or transport.get("substrate") == "e2b" or not transport.get("agent_card_url"):
            return
        bearer_token = self.secrets.resolve(transport.get("team_bearer_token_ref"))
        if not bearer_token:
            return
        for assignment in self.db.active_assignments(team_name):
            task_id = assignment["a2a_task_id"]
            if not task_id:
                continue
            try:
                task = self.a2a_client.get_task(transport=transport, bearer_token=bearer_token, task_id=task_id)
            except Exception as error:
                self.db.append_event(
                    team_name=team_name,
                    assignment_id=assignment["assignment_id"],
                    task_id=task_id,
                    source="a2a-poll",
                    kind="poll-error",
                    state="failed",
                    metadata={"error": str(error)},
                )
                continue
            self._ingest_polled_task(team_name, team_dir, assignment["assignment_id"], task_id, task)

    def _ingest_polled_task(self, team_name: str, team_dir: Path, assignment_id: str, task_id: str, task: dict[str, Any]) -> None:
        status = task.get("status") if isinstance(task.get("status"), dict) else {}
        state = str(status.get("state") or task.get("state") or "")
        if not state:
            return
        inserted = self.db.append_event(
            team_name=team_name,
            assignment_id=assignment_id,
            task_id=task_id,
            source="a2a-poll",
            kind="poll",
            state=state,
            metadata={"task_kind": task.get("kind")},
        )
        if not inserted["inserted"]:
            return
        write_json(
            team_dir / "status.json",
            {
                "team_name": team_name,
                "task_id": task_id,
                "assignment_id": assignment_id,
                "state": state,
                "source": "a2a-poll",
                "updated_at": utc_now(),
                "message": status.get("message"),
            },
        )
        if state == "working":
            self.db.mark_assignment_heartbeat(assignment_id=assignment_id, status="working")
            return
        if state == "completed":
            outbox = ensure_dir(team_dir / "outbox")
            artifacts = task.get("artifacts") or [{"name": f"{assignment_id}.result.md", "text": _status_message_text(status) or ""}]
            written: list[Path] = []
            for index, artifact in enumerate(artifacts):
                path = outbox / artifact_name(artifact, index)
                path.write_text(artifact_text(artifact), encoding="utf-8")
                written.append(path)
            self.db.mark_terminal(assignment_id=assignment_id, status="completed", completed_path=written[0] if written else None)
            self.db.release_lease(resource_type="assignment", resource_id=assignment_id)
        elif state in {"failed", "canceled"}:
            self.db.mark_terminal(assignment_id=assignment_id, status=state)
            self.db.release_lease(resource_type="assignment", resource_id=assignment_id)

    def _run_loop(self) -> None:
        next_heartbeat = 0.0
        while not self.stop_event.is_set():
            try:
                now = time.monotonic()
                if now >= next_heartbeat:
                    self.heartbeat()
                    next_heartbeat = now + 30
                self.tick()
            except Exception as error:
                self.record_error(error)
            self.stop_event.wait(self.poll_seconds)
        if self.server:
            self.server.shutdown()

    def _handler_class(self) -> type[BaseHTTPRequestHandler]:
        daemon = self

        class PushHandler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                if self.path != "/a2a/push":
                    self._send_json(404, {"error": "not found"})
                    return
                try:
                    body = _read_json_body(self)
                    result = process_push(
                        db=daemon.db,
                        secrets=daemon.secrets,
                        factory_dir=daemon.factory_dir,
                        headers={
                            "authorization": self.headers.get("authorization"),
                            "x-a2a-notification-token": self.headers.get("x-a2a-notification-token"),
                        },
                        body=body,
                    )
                    self._send_json(int(result["status"]), result["body"])
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

        return PushHandler


def _read_transport(team_dir: Path) -> dict[str, Any]:
    try:
        return json.loads((team_dir / "transport.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _status_message_text(status: dict[str, Any]) -> str | None:
    message = status.get("message")
    if isinstance(message, dict):
        parts = message.get("parts")
        if isinstance(parts, list):
            rendered = []
            for part in parts:
                if isinstance(part, dict) and part.get("text") is not None:
                    rendered.append(str(part["text"]))
            return "\n".join(rendered) or None
    if isinstance(message, str):
        return message
    return None


def install_signal_handlers(daemon: BridgeDaemon, db: BridgeDb) -> None:
    def handle_signal(signum: int, _frame: Any) -> None:
        daemon.stop()
        db.close()
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
