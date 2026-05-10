from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


class TransportError(RuntimeError):
    """Raised when a remote-team transport fails."""


def call_team(
    *,
    registry_path: Path,
    team: str,
    operation: str,
    request: dict[str, Any],
    timeout: int = 60,
) -> dict[str, Any]:
    registry = _load_registry(registry_path)
    teams = registry.get("remote_teams") or {}
    if team not in teams:
        raise TransportError(f"remote team is not registered: {team}")
    config = teams[team]
    if not isinstance(config, dict):
        raise TransportError(f"remote team config must be an object: {team}")
    payload = dict(request)
    payload["operation"] = operation
    payload.setdefault("target_team", team)
    payload.setdefault("board", config.get("board") or team)
    transport = str(config.get("transport") or "local")
    if transport == "local":
        return _call_local(config=config, payload=payload, timeout=timeout)
    if transport == "docker":
        return _call_docker(config=config, payload=payload, timeout=timeout)
    raise TransportError(f"unsupported transport for {team}: {transport}")


def _call_local(*, config: dict[str, Any], payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    env = os.environ.copy()
    if config.get("hermes_home"):
        env["HERMES_HOME"] = str(config["hermes_home"])
    env.update(_configured_env(config))
    command = [
        sys.executable,
        "-m",
        "hermes_harness.remote_team.cli",
        "receive",
        "--json",
    ]
    cwd = config.get("cwd")
    return _run_json(command, payload=payload, env=env, cwd=cwd, timeout=timeout)


def _call_docker(*, config: dict[str, Any], payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    container = config.get("container")
    if not container:
        raise TransportError("docker transport requires container")
    hermes_home = str(config.get("hermes_home") or "/vm/hermes-home")
    workdir = str(config.get("workdir") or "/workspace")
    python = str(config.get("python") or "python3")
    configured_env = _configured_env(config)
    command = [
        "docker",
        "exec",
        "-i",
        "-w",
        workdir,
        str(container),
        "env",
        f"HERMES_HOME={hermes_home}",
        *[f"{key}={value}" for key, value in configured_env.items()],
        python,
        "-m",
        "hermes_harness.remote_team.cli",
        "receive",
        "--json",
    ]
    return _run_json(command, payload=payload, env=os.environ.copy(), cwd=None, timeout=timeout)


def _configured_env(config: dict[str, Any]) -> dict[str, str]:
    raw = config.get("env") or {}
    if not isinstance(raw, dict):
        return {}
    return {str(key): str(value) for key, value in raw.items()}


def _run_json(
    command: list[str],
    *,
    payload: dict[str, Any],
    env: dict[str, str],
    cwd: str | None,
    timeout: int,
) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        input=json.dumps(payload),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
        cwd=cwd,
        timeout=timeout,
    )
    if completed.returncode != 0:
        raise TransportError(
            f"remote-team command failed ({completed.returncode}): {' '.join(command)}\n{completed.stdout}"
        )
    try:
        response = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise TransportError(f"remote-team response was not JSON:\n{completed.stdout}") from exc
    if not isinstance(response, dict):
        raise TransportError("remote-team response must be a JSON object")
    return response


def _load_registry(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TransportError(f"remote team registry not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise TransportError(f"remote team registry is invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise TransportError(f"remote team registry must be a JSON object: {path}")
    return payload
