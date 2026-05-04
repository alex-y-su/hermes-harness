from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from harness.models import AgentCardURL, SubstrateHandle, SubstrateHealth, TeamTemplate

SKIP_DIRS = {".git", "node_modules", "dist", "build", "__pycache__", ".venv", "venv"}


class E2BUnavailableError(RuntimeError):
    pass


class E2BDriver:
    """Import-safe E2B substrate driver.

    The SDK is imported only when a real operation needs it. `dry_run=True`
    exercises local filesystem and database paths without E2B credentials.
    """

    def __init__(
        self,
        *,
        template_id: str | None = None,
        api_key: str | None = None,
        a2a_port: int = 8000,
        dry_run: bool = False,
    ) -> None:
        self.template_id = template_id or os.getenv("E2B_TEMPLATE_ID") or "hermes-harness-remote-team"
        self.api_key = api_key or os.getenv("E2B_API_KEY")
        self.a2a_port = a2a_port
        self.dry_run = dry_run

    def _require_sdk(self) -> Any:
        if not self.api_key:
            raise E2BUnavailableError("E2B_API_KEY is required unless --dry-run or --substrate external is used")
        try:
            from e2b_code_interpreter import Sandbox  # type: ignore
        except ImportError as exc:
            raise E2BUnavailableError(
                "E2B SDK is not installed. Install with `pip install -e .[e2b]`, "
                "or use --dry-run/--substrate external."
            ) from exc
        return Sandbox

    async def provision(
        self,
        team_name: str,
        workspace_path: Path,
        template: TeamTemplate,
        timeout_seconds: int,
    ) -> SubstrateHandle:
        if self.dry_run:
            return SubstrateHandle(
                team_name=team_name,
                substrate="e2b",
                handle=f"dry-run-e2b://{team_name}",
                metadata={
                    "template_id": self.template_id,
                    "workspace_path": str(workspace_path),
                    "template": template.name,
                    "a2a_port": self.a2a_port,
                    "dry_run": True,
                },
            )

        Sandbox = self._require_sdk()
        sandbox = Sandbox.create(template=self.template_id, api_key=self.api_key, timeout=timeout_seconds)
        sandbox_id = getattr(sandbox, "sandbox_id", None) or getattr(sandbox, "id", None)
        if not sandbox_id:
            raise E2BUnavailableError("E2B sandbox was created but no sandbox id was returned")
        handle = SubstrateHandle(
            team_name=team_name,
            substrate="e2b",
            handle=str(sandbox_id),
            metadata={"template_id": self.template_id, "a2a_port": self.a2a_port},
        )
        await self.sync_in(handle, workspace_path)
        return handle

    async def boot(self, handle: SubstrateHandle) -> AgentCardURL:
        if handle.metadata.get("dry_run"):
            return f"http://localhost:{self.a2a_port}/.well-known/agent-card.json"

        sandbox = self._connect(handle)
        boot_mode = handle.metadata.get("boot_mode", "single-agent-team")
        if boot_mode == "multi-agent-team":
            command = f"harness-remote-supervisor start --template multi-agent --a2a-port {self.a2a_port}"
        else:
            command = f"hermes serve --profile coordinator --skills harness-worker --a2a-port {self.a2a_port}"
        sandbox.commands.run(f"cd /workspace && {command}", background=True)
        host = sandbox.get_host(self.a2a_port) if hasattr(sandbox, "get_host") else sandbox.getHost(self.a2a_port)
        return f"https://{host}/.well-known/agent-card.json"

    async def sync_in(self, handle: SubstrateHandle, workspace_path: Path) -> None:
        if handle.metadata.get("dry_run"):
            return None
        sandbox = self._connect(handle)
        writes = []
        for path in iter_sync_files(workspace_path):
            rel = path.relative_to(workspace_path).as_posix()
            writes.append({"path": f"/workspace/{rel}", "data": path.read_text(encoding="utf-8", errors="ignore")})
        if writes:
            sandbox.files.write(writes)

    async def sync_out(self, handle: SubstrateHandle, workspace_path: Path) -> None:
        if handle.metadata.get("dry_run"):
            return None
        sandbox = self._connect(handle)
        files = getattr(sandbox, "files", None)
        if not files:
            raise E2BUnavailableError("connected E2B sandbox does not expose a files API")
        for remote_path in list_remote_files(files, "/workspace"):
            rel = remote_path.removeprefix("/workspace/").removeprefix("/workspace")
            if not rel or any(part in SKIP_DIRS for part in Path(rel).parts):
                continue
            data = files.read(remote_path)
            target = workspace_path / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(data, bytes):
                target.write_bytes(data)
            else:
                target.write_text(str(data), encoding="utf-8")

    async def health(self, handle: SubstrateHandle) -> SubstrateHealth:
        if handle.metadata.get("dry_run"):
            return SubstrateHealth("unknown", "dry-run E2B handle", dict(handle.metadata))
        try:
            self._connect(handle)
        except Exception as exc:
            return SubstrateHealth("unhealthy", str(exc), {"handle": handle.handle})
        return SubstrateHealth("healthy", "E2B sandbox connect succeeded", {"handle": handle.handle})

    async def cancel(self, handle: SubstrateHandle) -> None:
        if handle.metadata.get("dry_run"):
            return None
        sandbox = self._connect(handle)
        if hasattr(sandbox, "kill"):
            sandbox.kill()

    async def archive(self, handle: SubstrateHandle, archive_path: Path) -> None:
        workspace_path = handle.metadata.get("workspace_path")
        if workspace_path and Path(str(workspace_path)).exists():
            archive_path.parent.mkdir(parents=True, exist_ok=True)
            if archive_path.exists():
                shutil.rmtree(archive_path)
            shutil.copytree(Path(str(workspace_path)), archive_path, ignore=shutil.ignore_patterns(*SKIP_DIRS))
            return
        archive_path.mkdir(parents=True, exist_ok=True)
        (archive_path / "e2b-handle.json").write_text(json.dumps(handle.metadata, indent=2), encoding="utf-8")

    def _connect(self, handle: SubstrateHandle) -> Any:
        Sandbox = self._require_sdk()
        if hasattr(Sandbox, "connect"):
            return Sandbox.connect(handle.handle, api_key=self.api_key)
        return Sandbox(handle.handle, api_key=self.api_key)


def iter_sync_files(root: Path):
    for path in root.rglob("*"):
        if path.is_dir():
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        yield path


def list_remote_files(files: Any, root: str) -> list[str]:
    """Best-effort recursive listing across E2B SDK file API variants."""
    if not hasattr(files, "list"):
        raise E2BUnavailableError("connected E2B sandbox files API does not support list()")
    discovered: list[str] = []
    pending = [root]
    while pending:
        current = pending.pop()
        entries = files.list(current)
        for entry in entries or []:
            path = entry.get("path") if isinstance(entry, dict) else getattr(entry, "path", None)
            name = entry.get("name") if isinstance(entry, dict) else getattr(entry, "name", None)
            is_dir = entry.get("is_dir") if isinstance(entry, dict) else getattr(entry, "is_dir", False)
            remote = path or f"{current.rstrip('/')}/{name}"
            if any(part in SKIP_DIRS for part in Path(remote).parts):
                continue
            if is_dir:
                pending.append(remote)
            else:
                discovered.append(remote)
    return discovered
