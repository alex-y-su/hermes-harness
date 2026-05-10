from __future__ import annotations

from pathlib import Path
from typing import Protocol

from harness.models import AgentCardURL, SubstrateHandle, SubstrateHealth, TeamTemplate


class SubstrateDriver(Protocol):
    async def provision(
        self,
        team_name: str,
        workspace_path: Path,
        template: TeamTemplate,
        timeout_seconds: int,
    ) -> SubstrateHandle: ...

    async def boot(self, handle: SubstrateHandle) -> AgentCardURL: ...

    async def sync_in(self, handle: SubstrateHandle, workspace_path: Path) -> None: ...

    async def sync_out(self, handle: SubstrateHandle, workspace_path: Path) -> None: ...

    async def health(self, handle: SubstrateHandle) -> SubstrateHealth: ...

    async def cancel(self, handle: SubstrateHandle) -> None: ...

    async def archive(self, handle: SubstrateHandle, archive_path: Path) -> None: ...
