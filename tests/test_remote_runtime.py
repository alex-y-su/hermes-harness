from __future__ import annotations

import json
import socket
import time
from pathlib import Path

from harness.bridge.a2a_client import A2AClient
from harness.bridge.daemon import BridgeDaemon
from harness.bridge.dispatch import dispatch_assignment
from harness.bridge.secrets import SecretResolver
from harness.bridge.store import BridgeDb
from harness.models import SubstrateHandle
from harness import db as harness_db
from harness_remote.a2a_server import RemoteRuntimeConfig, RemoteRuntimeServer
from harness_remote.push_client import parse_http_json_response


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_remote_runtime_receives_assignment_and_pushes_artifact(tmp_path: Path) -> None:
    factory_dir = tmp_path / "factory"
    team_dir = factory_dir / "teams" / "dev"
    (team_dir / "inbox").mkdir(parents=True)
    (team_dir / "outbox").mkdir()

    env_path = tmp_path / "bridge.env"
    env_path.write_text(
        "TEAM_BEARER=remote-token\nPUSH_TOKEN=push-token\nBRIDGE_SECRET=bridge-secret\n",
        encoding="utf-8",
    )
    secrets = SecretResolver(env_path)
    db = BridgeDb(tmp_path / "bridge.sqlite")
    bridge_port = free_port()
    push_url = f"http://127.0.0.1:{bridge_port}/a2a/push"

    bridge = BridgeDaemon(
        factory_dir=factory_dir,
        db=db,
        secrets=secrets,
        port=bridge_port,
        poll_ms=10_000,
        a2a_client=A2AClient(timeout_seconds=5),
    )
    runtime = RemoteRuntimeServer(
        RemoteRuntimeConfig(
            team_name="dev",
            push_url=push_url,
            push_token="push-token",
            bridge_secret="bridge-secret",
            artifact_text="artifact from mock runtime",
            port=0,
        )
    )

    try:
        runtime.start()
        (team_dir / "transport.json").write_text(
            json.dumps(
                {
                    "protocol": "a2a",
                    "substrate": "external",
                    "agent_card_url": runtime.agent_card_url,
                    "push_url": push_url,
                    "team_bearer_token_ref": "env://TEAM_BEARER",
                    "push_token_ref": "env://PUSH_TOKEN",
                    "bridge_secret_ref": "env://BRIDGE_SECRET",
                }
            ),
            encoding="utf-8",
        )
        inbox_path = team_dir / "inbox" / "assign-remote.md"
        inbox_path.write_text("# Remote assignment\n", encoding="utf-8")
        bridge.start()

        artifact_path = team_dir / "outbox" / "assign-remote.result.md"
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not artifact_path.exists():
            time.sleep(0.05)

        assert artifact_path.read_text(encoding="utf-8") == "artifact from mock runtime"
        assert db.get_assignment("assign-remote")["a2a_task_id"] == "task-assign-remote"
        assert db.get_assignment("assign-remote")["status"] == "completed"
    finally:
        runtime.stop()
        bridge.stop()
        db.close()


def test_push_client_parses_ipv4_fallback_response() -> None:
    response = b'HTTP/1.1 202 Accepted\r\ncontent-type: application/json\r\n\r\n{"ok":true}'

    assert parse_http_json_response(response) == {"ok": True}


def test_bridge_provisions_per_assignment_e2b_before_dispatch(tmp_path: Path, monkeypatch) -> None:
    factory_dir = tmp_path / "factory"
    team_dir = factory_dir / "teams" / "e2bdev"
    (team_dir / "inbox").mkdir(parents=True)
    (team_dir / "outbox").mkdir()
    (team_dir / "status.json").write_text(json.dumps({"template": "single-agent-team"}), encoding="utf-8")

    env_path = tmp_path / "bridge.env"
    env_path.write_text(
        "TEAM_BEARER=remote-token\nPUSH_TOKEN=push-token\nBRIDGE_SECRET=bridge-secret\n",
        encoding="utf-8",
    )
    secrets = SecretResolver(env_path)
    bridge_db = BridgeDb(tmp_path / "bridge.sqlite")
    bridge_port = free_port()
    push_url = f"http://127.0.0.1:{bridge_port}/a2a/push"

    bridge = BridgeDaemon(
        factory_dir=factory_dir,
        db=bridge_db,
        secrets=secrets,
        port=bridge_port,
        poll_ms=10_000,
        a2a_client=A2AClient(timeout_seconds=5),
        e2b_dry_run=True,
    )
    runtime = RemoteRuntimeServer(
        RemoteRuntimeConfig(
            team_name="e2bdev",
            push_url=push_url,
            push_token="push-token",
            bridge_secret="bridge-secret",
            artifact_text="artifact from per-assignment runtime",
            port=0,
        )
    )

    def fake_run_assignment_sandbox(*, factory, db_path, team, assignment_id, dry_run, secrets=None):
        handle = SubstrateHandle(
            team_name=team,
            substrate="e2b",
            handle=f"dry-run-e2b://{assignment_id}",
            metadata={"dry_run": True, "workspace_path": str(team_dir), "assignment_id": assignment_id},
        )
        with harness_db.session(db_path) as conn:
            harness_db.save_assignment_sandbox(
                conn,
                assignment_id=assignment_id,
                team_name=team,
                handle=handle,
                agent_card_url=runtime.agent_card_url,
                status="booted",
                metadata={"dry_run": True},
            )
        return {
            "team_name": team,
            "assignment_id": assignment_id,
            "sandbox_id": handle.handle,
            "agent_card_url": runtime.agent_card_url,
        }

    monkeypatch.setattr("harness.bridge.dispatch._run_async_assignment_sandbox", fake_run_assignment_sandbox)

    try:
        runtime.start()
        (team_dir / "transport.json").write_text(
            json.dumps(
                {
                    "protocol": "a2a",
                    "substrate": "e2b",
                    "per_assignment": True,
                    "agent_card_url": "",
                    "push_url": push_url,
                    "team_bearer_token_ref": "env://TEAM_BEARER",
                    "push_token_ref": "env://PUSH_TOKEN",
                    "bridge_secret_ref": "env://BRIDGE_SECRET",
                }
            ),
            encoding="utf-8",
        )
        (team_dir / "inbox" / "assign-e2b.md").write_text("# E2B assignment\n", encoding="utf-8")
        bridge.start()

        artifact_path = team_dir / "outbox" / "assign-e2b.result.md"
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not artifact_path.exists():
            time.sleep(0.05)

        assert artifact_path.read_text(encoding="utf-8") == "artifact from per-assignment runtime"
        assert bridge_db.get_assignment("assign-e2b")["status"] == "completed"
        sandbox = bridge_db.get_assignment_sandbox("assign-e2b")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and sandbox is not None and sandbox["status"] != "archived":
            time.sleep(0.05)
            sandbox = bridge_db.get_assignment_sandbox("assign-e2b")
        assert sandbox is not None
        assert sandbox["status"] == "archived"
    finally:
        runtime.stop()
        bridge.stop()
        bridge_db.close()
