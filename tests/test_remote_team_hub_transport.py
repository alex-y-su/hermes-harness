from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from hermes_harness.remote_team.transports import call_team


def test_hermes_hub_transport_submit_and_status(tmp_path: Path) -> None:
    hub = _FakeHub()
    server = ThreadingHTTPServer(("127.0.0.1", 0), hub.handler())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        registry = tmp_path / "remote_teams.json"
        registry.write_text(
            json.dumps(
                {
                    "remote_teams": {
                        "x": {
                            "transport": "hermes-hub",
                            "base_url": f"http://127.0.0.1:{server.server_port}",
                            "api_token": "admin-token",
                            "tenant_id": "tenant_x",
                            "board": "x",
                            "state_path": str(tmp_path / "hub-state.json"),
                            "poll_interval_seconds": 0.01,
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        request = {
            "protocol_version": "1",
            "source_team": "main",
            "target_team": "x",
            "external_id": "main:x:1",
            "task": {
                "title": "Create X strategy",
                "tenant": "growth",
                "body": "Requested KPIs\nQualified replies; Profile clicks",
            },
        }

        first = call_team(registry_path=registry, team="x", operation="submit_or_get", request=request, timeout=5)
        second = call_team(registry_path=registry, team="x", operation="submit_or_get", request=request, timeout=5)
        status = call_team(
            registry_path=registry,
            team="x",
            operation="status",
            request={
                "protocol_version": "1",
                "source_team": "main",
                "target_team": "x",
                "external_id": "main:x:1",
            },
            timeout=5,
        )
        forced_status = call_team(
            registry_path=registry,
            team="x",
            operation="status",
            request={
                "protocol_version": "1",
                "source_team": "main",
                "target_team": "x",
                "external_id": "main:x:1",
                "remote_task_id": first["remote_task_id"],
                "force_report": True,
                "task": request["task"],
            },
            timeout=5,
        )

        assert first["ok"] is True
        assert first["status"] == "completed"
        assert first["remote_task_id"] == "cron-000001"
        assert second["remote_task_id"] == first["remote_task_id"]
        assert status["remote_task_id"] == first["remote_task_id"]
        assert forced_status["remote_task_id"] == first["remote_task_id"]
        assert forced_status["hub"]["job_id"] == "cron-000002"
        assert first["main_card_update"]["action"] == "keep_running"
        assert first["result"]["mock_x_posts"][0]["id"] == "mock-x-1"
        assert forced_status["result"]["mock_x_posts"][0]["id"] == "mock-x-2"
        assert len(hub.created_jobs) == 2
        prompt = hub.created_jobs[0]["payload"]["input"]
        assert "Remote-team protocol request JSON" in prompt
        assert "Default remote-Kanban operating rules" in prompt
        assert "result.reports" in prompt
        assert "strategy_decisions" in prompt
        assert "execution_ledger" in prompt
        assert "create an executable recurring schedule" in prompt
        status_prompt = hub.created_jobs[1]["payload"]["input"]
        assert "scheduled main-dashboard poll" in status_prompt
    finally:
        server.shutdown()
        thread.join(timeout=5)


class _FakeHub:
    def __init__(self) -> None:
        self.created_jobs: list[dict[str, Any]] = []

    def handler(self) -> type[BaseHTTPRequestHandler]:
        hub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:
                return

            def do_GET(self) -> None:
                if self.path == "/v1/tenants/tenant_x":
                    self._write({"id": "tenant_x", "status": "ready", "agent": {"state": "cold_idle"}})
                    return
                match = self.path.rsplit("/", 1)
                if len(match) == 2 and match[0] == "/v1/tenants/tenant_x/cron-jobs":
                    job_id = match[1]
                    post_id = "mock-x-1" if job_id == "cron-000001" else "mock-x-2"
                    self._write(
                        {
                            "id": job_id,
                            "tenantID": "tenant_x",
                            "status": "executed",
                            "result": {
                                "responseText": json.dumps(
                                    {
                                        "ok": True,
                                        "protocol_version": "1",
                                        "status": "completed",
                                        "main_card_update": {
                                            "action": "keep_running",
                                            "status": "running",
                                            "kpi_state": "collecting",
                                        },
                                        "result": {
                                            "remote_team_protocol": True,
                                            "mock_remote": False,
                                            "mock_x_posts": [{"id": post_id, "text": "post"}],
                                            "main_card_update": {
                                                "action": "keep_running",
                                                "status": "running",
                                                "kpi_state": "collecting",
                                            },
                                        },
                                    }
                                )
                            },
                        }
                    )
                    return
                self.send_error(404)

            def do_POST(self) -> None:
                if self.path == "/v1/tenants/tenant_x/cron-jobs":
                    length = int(self.headers.get("content-length") or "0")
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    hub.created_jobs.append(payload)
                    job_id = f"cron-{len(hub.created_jobs):06d}"
                    self._write({"id": job_id, "tenantID": "tenant_x", "status": "pending"}, status=201)
                    return
                self.send_error(404)

            def _write(self, payload: dict[str, Any], *, status: int = 200) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return Handler
