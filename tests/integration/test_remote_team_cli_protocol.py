from __future__ import annotations

import json
import subprocess
import sys
import textwrap
import uuid
from pathlib import Path

import pytest


pytestmark = pytest.mark.integration


def test_remote_team_cli_docker_transport_submit_status(
    docker_compose_cmd: list[str], repo_root: Path, tmp_path: Path
) -> None:
    suffix = uuid.uuid4().hex[:8]
    container = f"hermes-remote-cli-{suffix}"
    board = f"x-{suffix}"
    hermes_home = f"/tmp/hermes-x-team-{suffix}"
    registry = tmp_path / "remote_teams.json"
    registry.write_text(
        json.dumps(
            {
                "remote_teams": {
                    "x": {
                        "transport": "docker",
                        "container": container,
                        "hermes_home": hermes_home,
                        "board": board,
                        "workdir": "/workspace",
                        "python": "python3",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    subprocess.run(
        [
            *docker_compose_cmd,
            "run",
            "-d",
            "--name",
            container,
            "-e",
            f"HERMES_HOME={hermes_home}",
            "local-vm",
            "sleep",
            "300",
        ],
        cwd=repo_root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        request = {
            "protocol_version": "1",
            "source_team": "main",
            "target_team": "x",
            "external_id": f"main:x-strategy:{suffix}",
            "task": {
                "title": "[x][growth] New X Posting Strategy",
                "tenant": "growth",
                "priority": 9,
                "body": textwrap.dedent(
                    """\
                    Card type
                    Campaign cycle

                    Stream
                    Growth

                    Goal
                    Create a new X posting strategy for remote-team Kanban orchestration.

                    Hypothesis
                    A contrarian posting strategy will generate qualified replies.

                    Target audience
                    AI builders and founder-operators.

                    Approval required
                    Human-approved for public posting. Auto-approved for drafting.

                    Approval reason
                    Posting to X is an external-world action.

                    Expected deliverables
                    1. Posting strategy
                    2. Three post drafts

                    Requested KPIs
                    Qualified replies; Profile clicks; Demo clicks

                    Measurement window
                    7 days after approved posting.

                    Decision rule
                    Continue if at least 3 qualified replies arrive.

                    Definition of done
                    Return a strategy packet and KPI report.

                    Reporting format
                    Return completed deliverables, requested KPIs, reported KPIs, approval, evidence, blockers, next recommendation, measurement window, decision rule, and main card update.
                    """
                ),
            },
        }

        first = _remote_call(registry, request, operation="submit_or_get")
        second = _remote_call(registry, request, operation="submit_or_get")
        status = _remote_call(
            registry,
            {
                "protocol_version": "1",
                "source_team": "main",
                "target_team": "x",
                "external_id": request["external_id"],
            },
            operation="status",
        )

        assert first["ok"] is True, first
        assert first["status"] == "completed", first
        assert first["remote_team"] == "x"
        assert first["board"] == board
        assert first["remote_task_id"] == second["remote_task_id"]
        assert first["remote_task_id"] == status["remote_task_id"]

        result = first["result"]
        assert result["remote_team_protocol"] is True
        assert result["mock_remote"] is False
        assert result["card_type"] == "campaign_cycle"
        assert result["stream"] == "growth"
        assert result["approval"]["tier"] == "human"
        assert result["approval"]["required_before_external_action"] is True
        assert result["requested_kpis"] == [
            "Qualified replies",
            "Profile clicks",
            "Demo clicks",
        ]
        assert [k["name"] for k in result["reported_kpis"]] == result["requested_kpis"]
        assert result["measurement_window"] == "7 days after approved posting."
        assert result["decision_rule"] == "Continue if at least 3 qualified replies arrive."
        assert result["main_card_update"]["action"] == "keep_running"
        assert result["main_card_update"]["status"] == "running"
        assert result["main_card_update"]["kpi_state"] == "collecting"
        assert first["main_card_update"] == result["main_card_update"]

        inspect = subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                "-w",
                "/workspace",
                container,
                "env",
                f"HERMES_HOME={hermes_home}",
                "bash",
                "-lc",
                (
                    f"test -f {hermes_home}/remote-team-protocol/{board}.json && "
                    f"hermes kanban --board {board} show {first['remote_task_id']} --json"
                ),
            ],
            cwd=repo_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=True,
        )
        persisted = json.loads(inspect.stdout)
        assert persisted["task"]["status"] == "done"
    finally:
        subprocess.run(["docker", "rm", "-f", container], cwd=repo_root, check=False)


def _remote_call(registry: Path, request: dict[str, object], *, operation: str) -> dict[str, object]:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "hermes_harness.remote_team.cli",
            "call",
            "--team",
            "x",
            "--operation",
            operation,
            "--registry",
            str(registry),
            "--json",
        ],
        input=json.dumps(request),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=True,
        timeout=90,
    )
    return json.loads(completed.stdout)
