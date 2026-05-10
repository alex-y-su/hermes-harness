from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hermes-harness")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="Report local reset/VM readiness.")
    doctor.add_argument("--json", action="store_true", help="Emit JSON.")

    return parser


def doctor() -> dict[str, Any]:
    hermes = shutil.which("hermes")
    repo = Path(os.environ.get("HERMES_INSTALL_DIR", "/usr/local/lib/hermes-agent"))
    result: dict[str, Any] = {
        "python_ok": True,
        "factory": os.environ.get("FACTORY_DIR", "/vm/factory"),
        "hermes_home": os.environ.get("HERMES_HOME", "/vm/hermes-home"),
        "hermes_available": bool(hermes),
        "hermes_path": hermes,
    }
    if hermes:
        result["hermes_version"] = _run_text([hermes, "version"]) or _run_text([hermes, "--version"])
        result["hermes_doctor"] = _run_text([hermes, "doctor"], timeout=30)
    if repo.exists():
        result["hermes_install_dir"] = str(repo)
        result["hermes_git_commit"] = _run_text(["git", "-C", str(repo), "rev-parse", "HEAD"])
        result["hermes_git_branch"] = _run_text(["git", "-C", str(repo), "branch", "--show-current"])
    return result


def _run_text(command: list[str], *, timeout: int = 10) -> str | None:
    try:
        completed = subprocess.run(
            command,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    output = completed.stdout.strip()
    if completed.returncode != 0 and not output:
        return None
    return output


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "doctor":
        payload = doctor()
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            for key, value in payload.items():
                print(f"{key}: {value}")
        return 0 if payload["python_ok"] else 1
    raise SystemExit(f"unknown command: {args.command}")
