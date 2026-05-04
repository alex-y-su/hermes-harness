from __future__ import annotations

import json
import shutil
from pathlib import Path

from harness.models import AgentCardURL, SubstrateHandle, SubstrateHealth, TeamTemplate


class ExternalSubstrateDriver:
    """Credential-free substrate for local dry-runs and pre-existing A2A peers."""

    def __init__(self, agent_card_url: str | None = None, dry_run: bool = False) -> None:
        self.agent_card_url = agent_card_url or "http://localhost:8000/.well-known/agent-card.json"
        self.dry_run = dry_run

    async def provision(
        self,
        team_name: str,
        workspace_path: Path,
        template: TeamTemplate,
        timeout_seconds: int,
    ) -> SubstrateHandle:
        return SubstrateHandle(
            team_name=team_name,
            substrate="external",
            handle=f"external://{team_name}",
            metadata={
                "agent_card_url": self.agent_card_url,
                "workspace_path": str(workspace_path),
                "template": template.name,
                "timeout_seconds": timeout_seconds,
                "dry_run": self.dry_run,
            },
        )

    async def boot(self, handle: SubstrateHandle) -> AgentCardURL:
        return str(handle.metadata.get("agent_card_url") or self.agent_card_url)

    async def sync_in(self, handle: SubstrateHandle, workspace_path: Path) -> None:
        return None

    async def sync_out(self, handle: SubstrateHandle, workspace_path: Path) -> None:
        return None

    async def health(self, handle: SubstrateHandle) -> SubstrateHealth:
        return SubstrateHealth("unknown", "external substrate health is caller-managed", dict(handle.metadata))

    async def cancel(self, handle: SubstrateHandle) -> None:
        return None

    async def archive(self, handle: SubstrateHandle, archive_path: Path) -> None:
        source = Path(str(handle.metadata.get("workspace_path", "")))
        if source.exists():
            archive_path.parent.mkdir(parents=True, exist_ok=True)
            if archive_path.exists():
                shutil.rmtree(archive_path)
            shutil.copytree(source, archive_path)
        else:
            archive_path.mkdir(parents=True, exist_ok=True)
            (archive_path / "external-handle.json").write_text(json.dumps(handle.metadata, indent=2), encoding="utf-8")
