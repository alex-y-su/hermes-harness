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
from harness.bridge.push import process_push
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
    ) -> None:
        self.factory_dir = Path(factory_dir)
        self.db = db
        self.secrets = secrets
        self.port = int(port)
        self.poll_seconds = int(poll_ms) / 1000
        self.a2a_client = a2a_client or A2AClient()
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
                )
            finally:
                self.in_progress.discard(path)

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


def install_signal_handlers(daemon: BridgeDaemon, db: BridgeDb) -> None:
    def handle_signal(signum: int, _frame: Any) -> None:
        daemon.stop()
        db.close()
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
