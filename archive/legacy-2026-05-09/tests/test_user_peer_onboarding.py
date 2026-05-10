from __future__ import annotations

import json
import os
import socket
import stat
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from harness.bridge.store import BridgeDb
from harness.tools.hermes_a2a_server import HermesA2ARuntime, _peer_id_from_card_url
from harness.tools.user_peer_client import message_peer, notify_user_context


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _make_hermes(tmp_path: Path, dump: Path | None = None) -> Path:
    hermes = tmp_path / "hermes"
    if dump is None:
        body = (
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "p = sys.argv[sys.argv.index('-z') + 1]\n"
            "print('hermes-replied:' + p[-40:])\n"
        )
    else:
        body = (
            "#!/usr/bin/env python3\n"
            "import pathlib, sys\n"
            "p = sys.argv[sys.argv.index('-z') + 1]\n"
            f"pathlib.Path({str(dump)!r}).write_text(p, encoding='utf-8')\n"
            "print('hermes-replied')\n"
        )
    hermes.write_text(body, encoding="utf-8")
    hermes.chmod(hermes.stat().st_mode | stat.S_IXUSR)
    return hermes


def _runtime(tmp_path: Path, *, db_path: Path | None, dump: Path | None = None) -> HermesA2ARuntime:
    hermes = _make_hermes(tmp_path, dump)
    return HermesA2ARuntime(
        profile="boss", host="127.0.0.1", port=0, token="",
        hermes_bin=str(hermes), model="m", timeout_seconds=10, db_path=db_path,
    )


def _send(runtime: HermesA2ARuntime, text: str, *, ctx: str = "ctx-onb", task: str = "t1") -> dict:
    return runtime.send_message(
        {"message": {"taskId": task, "contextId": ctx, "parts": [{"kind": "text", "text": text}]}},
        native=True,
    )


class _FakeUrlopen:
    """Context manager replacement for urllib.request.urlopen returning a fixed body."""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self) -> "_FakeUrlopen":
        return self

    def __exit__(self, *args: Any) -> bool:
        return False

    def read(self) -> bytes:
        return self._body


def _patch_urlopen(monkeypatch, *, raises: Exception | None = None, body: bytes | None = None) -> None:
    from harness.tools import hermes_a2a_server as srv

    def fake(url, timeout=10):
        if raises is not None:
            raise raises
        return _FakeUrlopen(body or b"{}")

    monkeypatch.setattr(srv.urllib.request, "urlopen", fake)


# --------------------------------------------------------------------------- #
# 1-2. invalid card URL / missing url field keep step=awaiting_card
# --------------------------------------------------------------------------- #


def test_onboarding_invalid_card_url_stays_in_awaiting_card(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "h.sqlite3"
    runtime = _runtime(tmp_path, db_path=db_path)

    r1 = _send(runtime, "do the thing")
    assert r1["status"]["state"] == "input-required"

    _patch_urlopen(monkeypatch, raises=RuntimeError("boom-network"))
    r2 = _send(runtime, "http://nope.example/agent.json")
    assert r2["status"]["state"] == "input-required"
    assert "boom-network" in r2["status"]["message"]["parts"][0]["text"] or "Couldn't fetch" in r2["status"]["message"]["parts"][0]["text"]

    bridge = runtime._db()
    onb = bridge.get_onboarding("ctx-onb")
    assert onb is not None and onb["step"] == "awaiting_card"


def test_onboarding_card_missing_url_field_stays_in_awaiting_card(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "h.sqlite3"
    runtime = _runtime(tmp_path, db_path=db_path)

    _send(runtime, "do the thing")  # first contact
    _patch_urlopen(monkeypatch, body=json.dumps({"name": "noUrl"}).encode("utf-8"))
    r2 = _send(runtime, "http://x.example/card.json")

    assert r2["status"]["state"] == "input-required"
    text = r2["status"]["message"]["parts"][0]["text"]
    assert "url" in text or "Couldn't fetch" in text

    bridge = runtime._db()
    onb = bridge.get_onboarding("ctx-onb")
    assert onb is not None and onb["step"] == "awaiting_card"


# --------------------------------------------------------------------------- #
# 3-4. token persistence + skip case-insensitive
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "third_turn,expect_token",
    [("super-secret-token", "super-secret-token"), ("SKIP", None), ("Skip", None)],
)
def test_onboarding_token_paths(
    tmp_path: Path, monkeypatch, third_turn: str, expect_token: str | None
) -> None:
    db_path = tmp_path / "h.sqlite3"
    runtime = _runtime(tmp_path, db_path=db_path)

    fake_card = {"url": "http://peer.example/a2a/", "name": "peer", "version": "0.1.0"}
    _patch_urlopen(monkeypatch, body=json.dumps(fake_card).encode("utf-8"))

    _send(runtime, "do the thing")
    _send(runtime, "http://peer.example/.well-known/agent-card.json")
    r3 = _send(runtime, third_turn)

    assert r3["status"]["state"] == "completed"

    bridge = runtime._db()
    peer_id = _peer_id_from_card_url("http://peer.example/.well-known/agent-card.json")
    peer = bridge.get_user_peer(peer_id)
    assert peer is not None
    assert peer["access_token"] == expect_token


# --------------------------------------------------------------------------- #
# 5. returning user_context skips onboarding
# --------------------------------------------------------------------------- #


def test_returning_user_context_skips_onboarding(tmp_path: Path) -> None:
    db_path = tmp_path / "h.sqlite3"
    bridge_seed = BridgeDb(db_path)
    peer_id = "deadbeef"
    bridge_seed.upsert_user_peer(
        peer_id=peer_id,
        agent_card_url="http://peer.example/card.json",
        agent_card_json=json.dumps({"url": "http://peer.example/a2a/"}),
        access_token=None,
    )
    bridge_seed.upsert_user_context(
        context_id="C1", peer_id=peer_id, task_id="prev-task", status="active",
    )
    seeded = bridge_seed.get_user_context("C1")
    seeded_updated = seeded["updated_at"]
    bridge_seed.close()
    time.sleep(1.1)  # ensure CURRENT_TIMESTAMP advances (1s resolution)

    runtime = _runtime(tmp_path, db_path=db_path)
    r = runtime.send_message(
        {"message": {"taskId": "tnew", "contextId": "C1", "parts": [{"kind": "text", "text": "hi again"}]}},
        native=True,
    )
    assert r["status"]["state"] == "completed"

    bridge = runtime._db()
    fresh = bridge.get_user_context("C1")
    assert fresh["updated_at"] >= seeded_updated
    assert bridge.get_onboarding("C1") is None


# --------------------------------------------------------------------------- #
# 6. db_path=None preserves legacy behavior
# --------------------------------------------------------------------------- #


def test_db_path_none_preserves_legacy_behavior(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path, db_path=None)
    r = _send(runtime, "hello")
    assert r["status"]["state"] == "completed"
    text = r["artifacts"][0]["parts"][0]["text"]
    assert "hermes-replied" in text


# --------------------------------------------------------------------------- #
# 7-8. DB helpers
# --------------------------------------------------------------------------- #


def test_peer_id_stable_across_upserts(tmp_path: Path) -> None:
    db_path = tmp_path / "h.sqlite3"
    bridge = BridgeDb(db_path)
    peer_id = _peer_id_from_card_url("http://peer.example/card.json")
    bridge.upsert_user_peer(
        peer_id=peer_id,
        agent_card_url="http://peer.example/card.json",
        agent_card_json=json.dumps({"url": "http://peer.example/a2a/"}),
    )
    first = bridge.get_user_peer(peer_id)
    time.sleep(1.1)
    bridge.upsert_user_peer(
        peer_id=peer_id,
        agent_card_url="http://peer.example/card.json",
        agent_card_json=json.dumps({"url": "http://peer.example/a2a/", "version": "0.2"}),
    )
    rows = bridge.list_user_peers()
    assert len(rows) == 1
    second = bridge.get_user_peer(peer_id)
    assert second["last_seen"] >= first["last_seen"]


def test_find_user_peer_by_card_url_returns_none_when_absent(tmp_path: Path) -> None:
    bridge = BridgeDb(tmp_path / "h.sqlite3")
    assert bridge.find_user_peer_by_card_url("http://nobody.example/card") is None


# --------------------------------------------------------------------------- #
# 9-12. user_peer_client.notify_user_context / message_peer
# --------------------------------------------------------------------------- #


class _RecorderHandler(BaseHTTPRequestHandler):
    log: list[dict[str, Any]] = []
    response_body: bytes = b'{"jsonrpc":"2.0","id":"x","result":{"id":"task-x","status":{"state":"completed"}}}'

    def do_POST(self) -> None:
        length = int(self.headers.get("content-length") or "0")
        body = self.rfile.read(length) if length else b""
        self.__class__.log.append(
            {
                "path": self.path,
                "headers": {k.lower(): v for k, v in self.headers.items()},
                "body": body,
            }
        )
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(self.response_body)))
        self.end_headers()
        self.wfile.write(self.response_body)

    def log_message(self, *a: Any) -> None:
        return


def _start_recorder() -> tuple[ThreadingHTTPServer, str]:
    _RecorderHandler.log = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _RecorderHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}/"


def test_notify_user_context_no_push_url_returns_ok_false(tmp_path: Path) -> None:
    db_path = tmp_path / "h.sqlite3"
    bridge = BridgeDb(db_path)
    bridge.upsert_user_peer(
        peer_id="p1", agent_card_url="http://p1.example/card", agent_card_json="{}",
    )
    bridge.upsert_user_context(context_id="C1", peer_id="p1", task_id="t1")
    bridge.close()

    res = notify_user_context(db_path=db_path, context_id="C1", message="hi")
    assert res["ok"] is False
    assert "push_url" in (res.get("error") or "")


def test_notify_user_context_posts_with_bearer(tmp_path: Path) -> None:
    db_path = tmp_path / "h.sqlite3"
    server, url = _start_recorder()
    try:
        bridge = BridgeDb(db_path)
        bridge.upsert_user_peer(
            peer_id="p1", agent_card_url="http://p1.example/card", agent_card_json="{}",
        )
        bridge.upsert_user_context(
            context_id="C1", peer_id="p1", task_id="t1",
            push_url=url, push_token="push-tk",
        )
        bridge.close()

        res = notify_user_context(db_path=db_path, context_id="C1", message="hello-push")
        assert res["ok"] is True

        assert len(_RecorderHandler.log) == 1
        rec = _RecorderHandler.log[0]
        assert rec["headers"].get("authorization") == "Bearer push-tk"
        body = json.loads(rec["body"].decode("utf-8"))
        assert body["context_id"] == "C1"
        assert body["message"] == "hello-push"
    finally:
        server.shutdown()
        server.server_close()


def test_message_peer_cold_start_creates_user_context(tmp_path: Path) -> None:
    db_path = tmp_path / "h.sqlite3"
    server, url = _start_recorder()
    try:
        bridge = BridgeDb(db_path)
        bridge.upsert_user_peer(
            peer_id="p1",
            agent_card_url="http://p1.example/card",
            agent_card_json=json.dumps({"url": url}),
            access_token="peer-tk",
        )
        bridge.close()

        result = message_peer(db_path=db_path, peer_id="p1", message="ping")
        assert "result" in result

        assert len(_RecorderHandler.log) == 1
        rec = _RecorderHandler.log[0]
        assert rec["headers"].get("authorization") == "Bearer peer-tk"
        body = json.loads(rec["body"].decode("utf-8"))
        assert body["jsonrpc"] == "2.0"
        assert body["method"] == "message/send"
        assert body["params"]["message"]["parts"][0]["text"] == "ping"
        minted_context = body["params"]["message"]["contextId"]

        bridge2 = BridgeDb(db_path)
        ctx_row = bridge2.get_user_context(minted_context)
        assert ctx_row is not None
        assert ctx_row["peer_id"] == "p1"
        bridge2.close()
    finally:
        server.shutdown()
        server.server_close()


def test_message_peer_with_no_token_omits_authorization(tmp_path: Path) -> None:
    db_path = tmp_path / "h.sqlite3"
    server, url = _start_recorder()
    try:
        bridge = BridgeDb(db_path)
        bridge.upsert_user_peer(
            peer_id="p2",
            agent_card_url="http://p2.example/card",
            agent_card_json=json.dumps({"url": url}),
            access_token=None,
        )
        bridge.close()

        message_peer(db_path=db_path, peer_id="p2", message="ping")
        rec = _RecorderHandler.log[0]
        assert "authorization" not in rec["headers"]
    finally:
        server.shutdown()
        server.server_close()


# --------------------------------------------------------------------------- #
# 13. CLI smoke
# --------------------------------------------------------------------------- #


def test_list_peers_cli_outputs_json(tmp_path: Path) -> None:
    db_path = tmp_path / "h.sqlite3"
    bridge = BridgeDb(db_path)
    bridge.upsert_user_peer(
        peer_id="aaa", agent_card_url="http://a.example/c", agent_card_json="{}",
        access_token="t",
    )
    bridge.upsert_user_peer(
        peer_id="bbb", agent_card_url="http://b.example/c", agent_card_json="{}",
        access_token=None,
    )
    bridge.close()

    repo_root = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(repo_root) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-m", "harness.tools.list_peers", "--db-path", str(db_path)],
        capture_output=True, text=True, timeout=30, env=env, cwd=str(repo_root),
    )
    assert proc.returncode == 0, proc.stderr
    parsed = json.loads(proc.stdout)
    assert {p["peer_id"] for p in parsed} == {"aaa", "bbb"}
    by_id = {p["peer_id"]: p for p in parsed}
    assert by_id["aaa"]["has_token"] is True
    assert by_id["bbb"]["has_token"] is False
