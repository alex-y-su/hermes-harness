from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

AgentCardURL = str


@dataclass(frozen=True)
class TeamTemplate:
    name: str
    path: Path
    boot_mode: Literal["single-agent-team", "multi-agent-team"]


@dataclass(frozen=True)
class SubstrateHandle:
    team_name: str
    substrate: str
    handle: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SubstrateHealth:
    status: Literal["healthy", "unhealthy", "unknown"]
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
