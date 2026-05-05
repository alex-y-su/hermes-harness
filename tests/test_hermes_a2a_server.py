from __future__ import annotations

import json
import stat
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

from harness.tools.hermes_a2a_server import HermesA2ARuntime, build_handler


def _start_server(tmp_path: Path) -> tuple[ThreadingHTTPServer, str, str]:
    hermes = tmp_path / "hermes"
    hermes.write_text(
        "#!/usr/bin/env bash\n"
        "printf 'fake hermes response for profile %s\\n' \"$2\"\n",
        encoding="utf-8",
    )
    hermes.chmod(hermes.stat().st_mode | stat.S_IXUSR)
    runtime = HermesA2ARuntime(
        profile="boss",
        host="127.0.0.1",
        port=0,
        token="secret-token",
        hermes_bin=str(hermes),
        model="test-model",
        timeout_seconds=10,
        agent_name="boss",
        description="User-facing boss endpoint",
        public_url="http://a2a.example.test/boss",
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), build_handler(runtime))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    return server, url, runtime.token


def _rpc(url: str, token: str, method: str, params: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps({"jsonrpc": "2.0", "id": "rpc-1", "method": method, "params": params}).encode()
    request = urllib.request.Request(
        f"{url}/",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def test_agent_card_advertises_jsonrpc_native_transport(tmp_path: Path) -> None:
    server, url, _token = _start_server(tmp_path)
    try:
        with urllib.request.urlopen(f"{url}/.well-known/agent.json", timeout=10) as response:
            card = json.loads(response.read().decode("utf-8"))

        assert card["name"] == "boss"
        assert card["description"] == "User-facing boss endpoint"
        assert card["url"] == "http://a2a.example.test/boss/"
        assert card["preferredTransport"] == "JSONRPC"
        assert card["protocolVersion"] == "0.3.0"
        assert card["capabilities"]["streaming"] is False
    finally:
        server.shutdown()
        server.server_close()


def test_sendmessage_requires_bearer_auth(tmp_path: Path) -> None:
    server, url, _token = _start_server(tmp_path)
    try:
        body = json.dumps({"jsonrpc": "2.0", "id": "rpc-1", "method": "SendMessage", "params": {}}).encode()
        request = urllib.request.Request(f"{url}/", data=body, method="POST")

        try:
            urllib.request.urlopen(request, timeout=10)
        except urllib.error.HTTPError as exc:
            assert exc.code == 401
        else:
            raise AssertionError("unauthenticated A2A request was accepted")
    finally:
        server.shutdown()
        server.server_close()


def test_message_send_returns_native_task_and_strips_api_env(tmp_path: Path, monkeypatch) -> None:
    hermes = tmp_path / "hermes"
    env_dump = tmp_path / "env.json"
    hermes.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "keys = ['OPENAI_API_KEY', 'OPENROUTER_API_KEY', 'OPENROUTER_API_KEY_AIWIZ_LANDING', 'LLM_BASE_URL']\n"
        f"open({str(env_dump)!r}, 'w').write(json.dumps({{key: os.environ.get(key) for key in keys}}))\n"
        "print('fake hermes response')\n",
        encoding="utf-8",
    )
    hermes.chmod(hermes.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-leak")
    monkeypatch.setenv("OPENROUTER_API_KEY", "must-not-leak")
    monkeypatch.setenv("OPENROUTER_API_KEY_AIWIZ_LANDING", "must-not-leak")
    monkeypatch.setenv("LLM_BASE_URL", "must-not-leak")

    runtime = HermesA2ARuntime(
        profile="boss",
        host="127.0.0.1",
        port=0,
        token="secret-token",
        hermes_bin=str(hermes),
        model="test-model",
        timeout_seconds=10,
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), build_handler(runtime))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        result = _rpc(
            f"http://127.0.0.1:{server.server_port}",
            "secret-token",
            "message/send",
            {
                "message": {
                    "taskId": "task-native",
                    "contextId": "ctx-1",
                    "parts": [{"kind": "text", "text": "hello"}],
                }
            },
        )

        task = result["result"]
        assert task["id"] == "task-native"
        assert task["contextId"] == "ctx-1"
        assert task["status"]["state"] == "completed"
        assert task["artifacts"][0]["parts"][0]["text"] == "fake hermes response"
        assert all(value is None for value in json.loads(env_dump.read_text(encoding="utf-8")).values())
    finally:
        server.shutdown()
        server.server_close()


def test_sendmessage_alias_keeps_legacy_task_wrapper(tmp_path: Path) -> None:
    server, url, token = _start_server(tmp_path)
    try:
        result = _rpc(
            url,
            token,
            "SendMessage",
            {"message": {"taskId": "alias-id", "parts": [{"kind": "text", "text": "hello alias"}]}},
        )

        assert result["result"]["task"]["id"] == "alias-id"
        assert result["result"]["task"]["status"]["state"] == "completed"
        assert result["result"]["task"]["artifacts"][0]["parts"][0]["text"].startswith("fake hermes response")
    finally:
        server.shutdown()
        server.server_close()


def test_boss_a2a_context_is_prepended_to_hermes_prompt(tmp_path: Path) -> None:
    hermes = tmp_path / "hermes"
    prompt_dump = tmp_path / "prompt.txt"
    hermes.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys\n"
        "prompt = sys.argv[sys.argv.index('-z') + 1]\n"
        f"pathlib.Path({str(prompt_dump)!r}).write_text(prompt, encoding='utf-8')\n"
        "print('ok')\n",
        encoding="utf-8",
    )
    hermes.chmod(hermes.stat().st_mode | stat.S_IXUSR)
    runtime = HermesA2ARuntime(
        profile="boss",
        host="127.0.0.1",
        port=0,
        token="secret-token",
        hermes_bin=str(hermes),
        model="test-model",
        timeout_seconds=10,
    )

    runtime.send_message(
        {"message": {"taskId": "ctx-id", "parts": [{"kind": "text", "text": "how many ppl in your team?"}]}},
        native=True,
    )

    prompt = prompt_dump.read_text(encoding="utf-8")
    assert "public Hermes Harness boss A2A endpoint" in prompt
    assert "exactly six profiles: boss, supervisor, hr, conductor, critic, and a2a-bridge" in prompt
    assert "Specialist and execution roles from docs/team are hireable remote teams" in prompt
    assert "--blueprint <team> <team>" in prompt
    assert "how many ppl in your team?" in prompt


def test_tasks_send_legacy_shape_is_supported(tmp_path: Path) -> None:
    server, url, token = _start_server(tmp_path)
    try:
        result = _rpc(
            url,
            token,
            "tasks/send",
            {"id": "legacy-id", "message": {"parts": [{"type": "text", "text": "hello legacy"}]}},
        )

        assert "task" not in result["result"]
        assert result["result"]["id"] == "legacy-id"
        assert result["result"]["status"]["state"] == "completed"
        assert result["result"]["artifacts"][0]["parts"][0]["text"].startswith("fake hermes response")
    finally:
        server.shutdown()
        server.server_close()
