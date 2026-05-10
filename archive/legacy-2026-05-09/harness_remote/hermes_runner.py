from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


BLOCKED_ENV_PREFIXES = ("OPENAI_", "OPENROUTER_")
BLOCKED_ENV_EXACT = {"LLM_BASE_URL"}
DEFAULT_CODEX_MODEL = "gpt-5.2"


@dataclass(frozen=True)
class RunnerResult:
    text: str
    metadata: dict[str, str]


class RunnerError(RuntimeError):
    pass


class AssignmentRunner:
    def run(self, *, assignment_id: str, task_id: str, assignment_text: str) -> RunnerResult:
        raise NotImplementedError


class MockRunner(AssignmentRunner):
    def __init__(self, artifact_text: str) -> None:
        self.artifact_text = artifact_text

    def run(self, *, assignment_id: str, task_id: str, assignment_text: str) -> RunnerResult:
        return RunnerResult(text=self.artifact_text, metadata={"runner": "mock"})


class CommandRunner(AssignmentRunner):
    def __init__(self, command: str, *, cwd: Path, timeout_seconds: int) -> None:
        self.command = command
        self.cwd = cwd
        self.timeout_seconds = timeout_seconds

    def run(self, *, assignment_id: str, task_id: str, assignment_text: str) -> RunnerResult:
        args = shlex.split(self.command)
        if not args:
            raise RunnerError("runner command is empty")
        prompt = build_assignment_prompt(assignment_id=assignment_id, task_id=task_id, assignment_text=assignment_text)
        env = sanitized_env(os.environ)
        env.update({"HARNESS_ASSIGNMENT_ID": assignment_id, "HARNESS_TASK_ID": task_id})
        completed = subprocess.run(
            args,
            input=prompt,
            text=True,
            cwd=self.cwd,
            env=env,
            capture_output=True,
            timeout=self.timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise RunnerError(f"runner command exited {completed.returncode}: {detail}")
        output = (completed.stdout or "").strip()
        if not output:
            output = (completed.stderr or "").strip()
        if not output:
            raise RunnerError("runner command produced no output")
        return RunnerResult(text=output, metadata={"runner": "command", "command": self.command})


class CodexExecRunner(AssignmentRunner):
    def __init__(self, *, cwd: Path, timeout_seconds: int, model: str | None = None) -> None:
        self.cwd = cwd
        self.timeout_seconds = timeout_seconds
        self.model = model or os.getenv("HARNESS_REMOTE_CODEX_MODEL") or os.getenv("MODEL_DEFAULT") or DEFAULT_CODEX_MODEL

    def run(self, *, assignment_id: str, task_id: str, assignment_text: str) -> RunnerResult:
        codex = shutil.which("codex")
        if codex is None:
            raise RunnerError("codex executable was not found in PATH")
        prompt = build_assignment_prompt(assignment_id=assignment_id, task_id=task_id, assignment_text=assignment_text)
        env = sanitized_env(os.environ)
        env.update({"HARNESS_ASSIGNMENT_ID": assignment_id, "HARNESS_TASK_ID": task_id})
        with tempfile.NamedTemporaryFile(prefix=f"{assignment_id}-", suffix=".md", delete=False) as tmp:
            output_path = Path(tmp.name)
        try:
            args = [
                codex,
                "exec",
                "--skip-git-repo-check",
                "--sandbox",
                "workspace-write",
                "--config",
                "approval_policy=\"never\"",
                "--model",
                self.model,
                "--output-last-message",
                str(output_path),
                "-",
            ]
            completed = subprocess.run(
                args,
                input=prompt,
                text=True,
                cwd=self.cwd,
                env=env,
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
            )
            if completed.returncode != 0:
                detail = (completed.stderr or completed.stdout or "").strip()
                raise RunnerError(f"codex exec exited {completed.returncode}: {detail}")
            output = output_path.read_text(encoding="utf-8", errors="replace").strip()
            if not output:
                output = (completed.stdout or "").strip()
            if not output:
                raise RunnerError("codex exec produced no final response")
            return RunnerResult(text=output, metadata={"runner": "codex", "model": self.model})
        finally:
            output_path.unlink(missing_ok=True)


def build_runner(*, mode: str, artifact_text: str, command: str | None, workspace: Path, timeout_seconds: int) -> AssignmentRunner:
    if mode == "mock":
        return MockRunner(artifact_text)
    if mode == "command":
        if not command:
            raise RunnerError("HARNESS_REMOTE_RUNNER_COMMAND is required for command runner mode")
        return CommandRunner(command, cwd=workspace, timeout_seconds=timeout_seconds)
    if mode == "codex":
        return CodexExecRunner(cwd=workspace, timeout_seconds=timeout_seconds)
    raise RunnerError(f"unsupported remote runner mode: {mode}")


def build_assignment_prompt(*, assignment_id: str, task_id: str, assignment_text: str) -> str:
    return (
        "You are a remote Hermes Harness worker running inside an isolated assignment sandbox.\n"
        "Complete the assignment below and return only the final artifact content in Markdown.\n"
        "Do not ask follow-up questions unless credentials or human input are strictly required.\n\n"
        f"Assignment ID: {assignment_id}\n"
        f"A2A Task ID: {task_id}\n\n"
        "Assignment:\n"
        f"{assignment_text.strip()}\n"
    )


def sanitized_env(environ: dict[str, str] | os._Environ[str]) -> dict[str, str]:
    result = dict(environ)
    for key in list(result):
        if key in BLOCKED_ENV_EXACT or key.startswith(BLOCKED_ENV_PREFIXES):
            result.pop(key, None)
    return result
