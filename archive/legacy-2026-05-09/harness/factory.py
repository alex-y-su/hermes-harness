from __future__ import annotations

import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from string import Template
from typing import Any

from harness.models import TeamTemplate

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_ROOT = PACKAGE_ROOT / "templates"
TEAM_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def require_team_name(team_name: str) -> str:
    if not TEAM_NAME_RE.match(team_name):
        raise ValueError("team name must be 1-64 chars: letters, numbers, dot, dash, underscore")
    return team_name


def factory_path(path: str | Path | None) -> Path:
    return Path(path or "factory").resolve()


def team_path(factory: Path, team_name: str) -> Path:
    return factory / "teams" / require_team_name(team_name)


def load_template(name: str) -> TeamTemplate:
    normalized = name
    if name == "single-agent":
        normalized = "single-agent-team"
    if name == "multi-agent":
        normalized = "multi-agent-team"
    path = TEMPLATES_ROOT / normalized
    if not path.exists():
        raise FileNotFoundError(f"unknown team template: {name}")
    return TeamTemplate(name=normalized, path=path, boot_mode=normalized)  # type: ignore[arg-type]


def copy_template(template: TeamTemplate, destination: Path, variables: dict[str, str]) -> None:
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError(f"team folder already exists and is not empty: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    for source in template.path.rglob("*"):
        rel = source.relative_to(template.path)
        target = destination / rel
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        text = source.read_text(encoding="utf-8")
        target.write_text(Template(text).safe_substitute(variables), encoding="utf-8")


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def append_journal(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"\n- {utc_now()} {line}\n")


def archive_team(factory: Path, team_name: str) -> Path:
    source = team_path(factory, team_name)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    destination = factory / "archive" / f"teams_{team_name}_{timestamp}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))
    return destination
