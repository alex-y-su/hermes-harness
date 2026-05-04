from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from harness.models import AgentCardURL, SubstrateHandle, SubstrateHealth, TeamTemplate

SKIP_DIRS = {".git", ".harness", "node_modules", "dist", "build", "__pycache__", ".venv", "venv"}
WORKSPACE_ROOT = "/home/user/workspace"
RUNTIME_ROOT = f"{WORKSPACE_ROOT}/.harness/runtime"
SANDBOX_CODEX_HOME = "/home/user/.codex"
DEFAULT_TEMPLATE_ALIAS = "hermes-harness-remote-full"
LLM_ENV_PREFIXES = ("ANTHROPIC_", "HERMES_", "LLM_", "MODEL_")
LLM_ENV_EXACT = {"CODEX_HOME", "HERMES_HOME", "HERMES_INFERENCE_PROVIDER", "HERMES_INFERENCE_MODEL"}


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
        remote_env: dict[str, str] | None = None,
    ) -> None:
        self.template_id = template_id or os.getenv("E2B_TEMPLATE_ID") or DEFAULT_TEMPLATE_ALIAS
        self.api_key = api_key or os.getenv("E2B_API_KEY")
        self.a2a_port = a2a_port
        self.dry_run = dry_run
        self.remote_env = remote_env or {}

    def _require_sdk(self) -> Any:
        if not self.api_key:
            raise E2BUnavailableError("E2B_API_KEY is required unless --dry-run or --substrate external is used")
        try:
            from e2b import Sandbox  # type: ignore
            return Sandbox
        except ImportError:
            pass
        try:
            from e2b_code_interpreter import Sandbox  # type: ignore
        except ImportError as exc:
            raise E2BUnavailableError(
                "E2B SDK is not installed. Install with `pip install -e '.[e2b]'`, "
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
            template_alias = resolve_template_alias(workspace_path, fallback=self.template_id)
            return SubstrateHandle(
                team_name=team_name,
                substrate="e2b",
                handle=f"dry-run-e2b://{team_name}",
                metadata={
                    "template_id": template_alias,
                    "workspace_path": str(workspace_path),
                    "template": template.name,
                    "a2a_port": self.a2a_port,
                    "dry_run": True,
                },
            )

        Sandbox = self._require_sdk()
        template_alias = resolve_template_alias(workspace_path, fallback=self.template_id)
        sandbox = Sandbox.create(template=template_alias, api_key=self.api_key, timeout=timeout_seconds)
        sandbox_id = getattr(sandbox, "sandbox_id", None) or getattr(sandbox, "id", None)
        if not sandbox_id:
            raise E2BUnavailableError("E2B sandbox was created but no sandbox id was returned")
        handle = SubstrateHandle(
            team_name=team_name,
            substrate="e2b",
            handle=str(sandbox_id),
            metadata={"template_id": template_alias, "a2a_port": self.a2a_port, "workspace_path": str(workspace_path)},
        )
        await self.sync_in(handle, workspace_path)
        return handle

    async def boot(self, handle: SubstrateHandle) -> AgentCardURL:
        if handle.metadata.get("dry_run"):
            return f"http://localhost:{self.a2a_port}/.well-known/agent-card.json"

        sandbox = self._connect(handle)
        boot_mode = handle.metadata.get("boot_mode", "single-agent-team")
        setup = f"{WORKSPACE_ROOT}/e2b/setup.sh"
        sandbox.commands.run(f"cd {WORKSPACE_ROOT} && if [ -f {setup} ]; then sh {setup}; fi")
        if boot_mode == "multi-agent-team":
            template_arg = "--template multi-agent"
        else:
            template_arg = "--template single-agent"
        ready_file = f"{WORKSPACE_ROOT}/.harness/remote-ready.json"
        command = (
            "if command -v harness-remote-supervisor >/dev/null 2>&1; then "
            f"harness-remote-supervisor start {template_arg} --team-name {handle.team_name} "
            f"--host 0.0.0.0 --a2a-port {self.a2a_port} --ready-file {ready_file}; "
            "else "
            f"PYTHONPATH={RUNTIME_ROOT} python3 -m harness_remote.cli start {template_arg} "
            f"--team-name {handle.team_name} --host 0.0.0.0 --a2a-port {self.a2a_port} --ready-file {ready_file}; "
            "fi"
        )
        sandbox.commands.run(f"cd {WORKSPACE_ROOT} && {command}", background=True, envs=self.remote_env)
        host = sandbox.get_host(self.a2a_port) if hasattr(sandbox, "get_host") else sandbox.getHost(self.a2a_port)
        agent_card_url = f"https://{host}/.well-known/agent-card.json"
        wait_for_remote_runtime(agent_card_url)
        return agent_card_url

    async def sync_in(self, handle: SubstrateHandle, workspace_path: Path) -> None:
        if handle.metadata.get("dry_run"):
            return None
        sandbox = self._connect(handle)
        writes = []
        for path in iter_sync_files(workspace_path):
            rel = path.relative_to(workspace_path).as_posix()
            writes.append({"path": f"{WORKSPACE_ROOT}/{rel}", "data": path.read_text(encoding="utf-8", errors="ignore")})
        for source, rel in iter_runtime_source_files():
            writes.append({"path": f"{RUNTIME_ROOT}/{rel}", "data": source.read_text(encoding="utf-8", errors="ignore")})
        llm_env = filtered_llm_env(os.environ)
        if llm_env:
            writes.append(
                {
                    "path": f"{WORKSPACE_ROOT}/.harness/llm-env.json",
                    "data": json.dumps(llm_env, indent=2, sort_keys=True),
                }
            )
        codex_auth = discover_codex_auth_file(os.environ)
        if codex_auth:
            writes.append({"path": f"{SANDBOX_CODEX_HOME}/auth.json", "data": codex_auth.read_text(encoding="utf-8")})
            self.remote_env.setdefault("CODEX_HOME", SANDBOX_CODEX_HOME)
            self.remote_env.setdefault("HERMES_INFERENCE_PROVIDER", "openai-codex")
            self.remote_env.setdefault("HARNESS_REMOTE_RUNNER", "codex")
            self.remote_env.setdefault("HARNESS_REMOTE_WORKSPACE", WORKSPACE_ROOT)
        if writes:
            write_sandbox_files(sandbox.files, writes)
        if codex_auth:
            # TODO: replace copied Codex OAuth state with a boss-machine auth proxy
            # that issues short-lived JWTs to sub-team sandboxes.
            sandbox.commands.run(f"mkdir -p {SANDBOX_CODEX_HOME} && chmod 700 {SANDBOX_CODEX_HOME} && chmod 600 {SANDBOX_CODEX_HOME}/auth.json")

    async def sync_out(self, handle: SubstrateHandle, workspace_path: Path) -> None:
        if handle.metadata.get("dry_run"):
            return None
        sandbox = self._connect(handle)
        files = getattr(sandbox, "files", None)
        if not files:
            raise E2BUnavailableError("connected E2B sandbox does not expose a files API")
        for remote_path in list_remote_files(files, WORKSPACE_ROOT):
            rel = remote_path.removeprefix(f"{WORKSPACE_ROOT}/").removeprefix(WORKSPACE_ROOT)
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


def iter_runtime_source_files():
    root = Path(__file__).resolve().parents[2]
    for package in ("harness", "harness_remote"):
        package_root = root / package
        for path in package_root.rglob("*.py"):
            if any(part in SKIP_DIRS for part in path.relative_to(package_root).parts):
                continue
            yield path, f"{package}/{path.relative_to(package_root).as_posix()}"


def discover_codex_auth_file(environ: dict[str, str] | os._Environ[str]) -> Path | None:
    candidates = []
    for key in ("HERMES_CODEX_AUTH_FILE", "CODEX_AUTH_FILE"):
        value = environ.get(key)
        if value:
            candidates.append(Path(value).expanduser())
    codex_home = environ.get("CODEX_HOME")
    if codex_home:
        candidates.append(Path(codex_home).expanduser() / "auth.json")
    candidates.append(Path.home() / ".codex" / "auth.json")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def write_sandbox_files(files: Any, writes: list[dict[str, str]]) -> None:
    if not writes:
        return
    try:
        files.write(writes)
        return
    except TypeError:
        pass
    for item in writes:
        files.write(item["path"], item["data"])


def resolve_template_alias(workspace_path: Path, *, fallback: str = DEFAULT_TEMPLATE_ALIAS) -> str:
    template_json = workspace_path / "e2b" / "template.json"
    if not template_json.exists():
        return fallback
    try:
        data = json.loads(template_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise E2BUnavailableError(f"invalid E2B template metadata: {template_json}") from exc
    for key in ("active_template", "team_alias", "default_alias"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback


def filtered_llm_env(environ: dict[str, str] | os._Environ[str]) -> dict[str, str]:
    """Return assignment runtime env that is safe to copy into the sandbox.

    API keys for OpenAI/OpenRouter are intentionally not copied by this helper.
    Hermes/Codex OAuth should be handled through Hermes auth state or a future
    short-lived proxy token, not by leaking provider keys into E2B workspaces.
    """
    result: dict[str, str] = {}
    for key, value in environ.items():
        if key in LLM_ENV_EXACT or key.startswith(LLM_ENV_PREFIXES):
            if key == "LLM_BASE_URL" or key.startswith(("OPENAI_", "OPENROUTER_")):
                continue
            result[key] = value
    return result


def wait_for_remote_runtime(agent_card_url: str, *, timeout_seconds: float = 60.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urlopen(agent_card_url, timeout=5) as response:
                if response.status < 500:
                    return
        except (URLError, TimeoutError, OSError) as error:
            last_error = error
        time.sleep(1)
    raise E2BUnavailableError(f"remote runtime did not become ready at {agent_card_url}: {last_error}")


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
            is_dir = remote_entry_is_dir(entry)
            remote = path or f"{current.rstrip('/')}/{name}"
            if any(part in SKIP_DIRS for part in Path(remote).parts):
                continue
            if is_dir:
                pending.append(remote)
            else:
                discovered.append(remote)
    return discovered


def remote_entry_is_dir(entry: Any) -> bool:
    if isinstance(entry, dict):
        if "is_dir" in entry:
            return bool(entry["is_dir"])
        entry_type = entry.get("type")
    else:
        is_dir = getattr(entry, "is_dir", None)
        if is_dir is not None:
            return bool(is_dir)
        entry_type = getattr(entry, "type", None)
    value = getattr(entry_type, "value", entry_type)
    return str(value).lower() in {"dir", "directory"}
