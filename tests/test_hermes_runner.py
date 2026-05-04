from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from harness_remote.a2a_server import extract_message_text
from harness_remote.hermes_runner import CommandRunner, MockRunner, RunnerError, build_assignment_prompt, sanitized_env


def test_mock_runner_returns_configured_artifact() -> None:
    result = MockRunner("artifact").run(assignment_id="asn", task_id="task-asn", assignment_text="body")

    assert result.text == "artifact"
    assert result.metadata["runner"] == "mock"


def test_command_runner_passes_prompt_and_scrubs_provider_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    script = tmp_path / "runner.py"
    script.write_text(
        "import os, sys\n"
        "prompt = sys.stdin.read()\n"
        "assert 'OPENAI_API_KEY' not in os.environ\n"
        "assert 'OPENROUTER_API_KEY' not in os.environ\n"
        "print('saw:' + prompt.split('Assignment:')[-1].strip())\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-leak")
    monkeypatch.setenv("OPENROUTER_API_KEY", "must-not-leak")

    result = CommandRunner(f"{sys.executable} {script}", cwd=tmp_path, timeout_seconds=10).run(
        assignment_id="asn",
        task_id="task-asn",
        assignment_text="Do the work.",
    )

    assert result.text == "saw:Do the work."
    assert result.metadata["runner"] == "command"


def test_command_runner_reports_failure(tmp_path: Path) -> None:
    script = tmp_path / "runner.py"
    script.write_text("import sys\nprint('bad', file=sys.stderr)\nsys.exit(7)\n", encoding="utf-8")

    with pytest.raises(RunnerError, match="exited 7"):
        CommandRunner(f"{sys.executable} {script}", cwd=tmp_path, timeout_seconds=10).run(
            assignment_id="asn",
            task_id="task-asn",
            assignment_text="Do the work.",
        )


def test_assignment_prompt_contains_identity_and_body() -> None:
    prompt = build_assignment_prompt(assignment_id="asn-1", task_id="task-1", assignment_text="Body")

    assert "Assignment ID: asn-1" in prompt
    assert "A2A Task ID: task-1" in prompt
    assert "Body" in prompt


def test_sanitized_env_removes_provider_keys() -> None:
    env = sanitized_env({"OPENAI_API_KEY": "x", "OPENROUTER_API_KEY": "y", "CODEX_HOME": "/tmp/codex"})

    assert env == {"CODEX_HOME": "/tmp/codex"}


def test_extract_message_text_reads_text_parts() -> None:
    assert extract_message_text({"parts": [{"kind": "text", "text": "one"}, {"text": "two"}]}) == "one\ntwo"
