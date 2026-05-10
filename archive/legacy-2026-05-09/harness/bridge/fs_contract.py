from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_dir(path: str | Path) -> Path:
    resolved = Path(path)
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def read_json(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, value: dict) -> None:
    resolved = Path(path)
    ensure_dir(resolved.parent)
    resolved.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def append_journal(team_dir: str | Path, line: str) -> None:
    path = Path(team_dir) / "journal.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"{utc_now()} {line}\n")


def discover_teams(factory_dir: str | Path) -> list[tuple[str, Path]]:
    teams_dir = Path(factory_dir) / "teams"
    if not teams_dir.exists():
        return []
    return [(path.name, path) for path in sorted(teams_dir.iterdir()) if path.is_dir()]


def assignment_id_from_path(path: str | Path) -> str:
    return Path(path).name.removesuffix(".md")


def move_if_exists(source: str | Path, destination: str | Path) -> bool:
    src = Path(source)
    dst = Path(destination)
    if not src.exists():
        return False
    ensure_dir(dst.parent)
    src.rename(dst)
    return True
