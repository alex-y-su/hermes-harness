from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


INTERNAL_LLM_ROLES = ("supervisor", "hr", "conductor", "critic")
EXPECTED_INTERNAL_ROLES = (*INTERNAL_LLM_ROLES, "a2a-bridge")

PROBLEM = """\
Solve this team coordination problem.

Four jobs must run on two identical workers.
Durations: A=3, B=2, C=4, D=1.
Dependencies: A before C, B before C, C before D.
Workers can run only one job at a time.

Find the minimum makespan, provide one valid schedule, and decide whether adding
a third worker improves the makespan. Explain the critical path briefly.
"""

ROLE_PROMPTS = {
    "supervisor": """\
TEAM_MEMBER: supervisor

Check the problem constraints and give approval criteria for the final answer.
You must solve enough of the problem to detect schedule or dependency mistakes.
Return concise findings under these headings:
TEAM_MEMBER, ROLE_FINDINGS, ACCEPTANCE_CRITERIA.

Problem:
{problem}
""",
    "hr": """\
TEAM_MEMBER: hr

Route ownership for this problem across the boss team. Identify what each role
should contribute and solve the scheduling result you expect boss to use.
Return concise findings under these headings:
TEAM_MEMBER, ROUTING, EXPECTED_RESULT.

Problem:
{problem}
""",
    "conductor": """\
TEAM_MEMBER: conductor

Produce the execution cadence: ordering, dependency gates, timeline, and minimum
makespan. Include a concrete two-worker schedule.
Return concise findings under these headings:
TEAM_MEMBER, CADENCE, SCHEDULE.

Problem:
{problem}
""",
    "critic": """\
TEAM_MEMBER: critic

Attack likely wrong answers. Check the lower bound, worker constraints, and the
third-worker claim. State any answer that should be rejected.
Return concise findings under these headings:
TEAM_MEMBER, RISKS, VERDICT.

Problem:
{problem}
""",
}


def clean_llm_env(env: dict[str, str] | None = None) -> dict[str, str]:
    cleaned = dict(os.environ if env is None else env)
    for key in list(cleaned):
        if key.startswith("OPENAI_") or key.startswith("OPENROUTER_") or key == "LLM_BASE_URL":
            cleaned.pop(key, None)
    return cleaned


def run_hermes(
    *,
    hermes_bin: str,
    profile: str,
    prompt: str,
    model: str,
    timeout_seconds: int,
) -> str:
    completed = subprocess.run(
        [
            hermes_bin,
            "--profile",
            profile,
            "-z",
            prompt,
            "--provider",
            "openai-codex",
            "--model",
            model,
            "--accept-hooks",
        ],
        env=clean_llm_env(),
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"Hermes profile {profile} exited {completed.returncode}: {detail}")
    output = (completed.stdout or "").strip()
    if not output:
        raise RuntimeError(f"Hermes profile {profile} produced no output")
    return output


def load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def public_entry(manifest: dict[str, Any]) -> dict[str, Any]:
    entry = manifest.get("public_agent")
    if isinstance(entry, dict):
        return entry
    profiles = manifest.get("profiles")
    if isinstance(profiles, list):
        for candidate in profiles:
            if isinstance(candidate, dict) and candidate.get("profile") == "boss":
                return candidate
    raise RuntimeError("A2A manifest does not contain a public boss entry")


def profile_names(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    names: list[str] = []
    for item in items:
        if isinstance(item, str):
            names.append(item)
        elif isinstance(item, dict) and isinstance(item.get("profile"), str):
            names.append(item["profile"])
    return names


def http_json(url: str, *, body: dict[str, Any] | None = None, token: str = "", timeout: int = 30) -> dict[str, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=data, headers=headers, method="POST" if body is not None else "GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def check_a2a_bridge(manifest_path: Path) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    entry = public_entry(manifest)
    url = str(entry.get("url") or "").rstrip("/")
    internal_profiles = profile_names(manifest.get("internal_profiles"))

    card = http_json(f"{url}/.well-known/agent.json", timeout=30)
    health = http_json(f"{url}/health", timeout=30)
    public_profiles = profile_names(manifest.get("profiles"))
    checks = {
        "public_boss_only": public_profiles == ["boss"],
        "expected_internal_profiles": sorted(internal_profiles) == sorted(EXPECTED_INTERNAL_ROLES),
        "agent_card_is_boss": card.get("name") == "boss",
        "health_ok": health.get("ok") is True and health.get("profile") == "boss",
        "has_bearer_token": bool(entry.get("auth_token")),
    }
    return {
        "team_member": "a2a-bridge",
        "ok": all(checks.values()),
        "url": url,
        "public_profiles": public_profiles,
        "internal_profiles": internal_profiles,
        "agent_card": {
            "name": card.get("name"),
            "protocolVersion": card.get("protocolVersion"),
            "preferredTransport": card.get("preferredTransport"),
        },
        "health": health,
        "checks": checks,
    }


def a2a_send(url: str, token: str, prompt: str, *, timeout_seconds: int) -> str:
    task_id = f"intelligence-{int(time.time())}"
    result = http_json(
        f"{url}/",
        token=token,
        timeout=timeout_seconds,
        body={
            "jsonrpc": "2.0",
            "id": task_id,
            "method": "SendMessage",
            "params": {
                "message": {
                    "kind": "message",
                    "messageId": f"{task_id}-message",
                    "role": "user",
                    "parts": [{"kind": "text", "text": prompt}],
                }
            },
        },
    )
    if "error" in result:
        raise RuntimeError(f"A2A boss call failed: {result['error']}")
    task = result.get("result", {}).get("task")
    if not isinstance(task, dict):
        raise RuntimeError(f"A2A boss call returned no task: {result}")
    if task.get("status", {}).get("state") != "completed":
        raise RuntimeError(f"A2A boss task did not complete: {task}")

    artifacts = task.get("artifacts")
    if isinstance(artifacts, list):
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            for part in artifact.get("parts", []):
                if isinstance(part, dict):
                    text = part.get("text")
                    if isinstance(text, str) and text.strip():
                        return text.strip()
    message = task.get("status", {}).get("message")
    if isinstance(message, dict):
        for part in message.get("parts", []):
            if isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    return text.strip()
    raise RuntimeError(f"A2A boss task completed without text artifact: {task}")


def boss_prompt(role_outputs: dict[str, str], bridge_report: dict[str, Any]) -> str:
    sections = [f"Problem:\n{PROBLEM.strip()}", "Internal role outputs:"]
    for role in INTERNAL_LLM_ROLES:
        sections.append(f"--- {role} ---\n{role_outputs[role].strip()}")
    sections.append(f"--- a2a-bridge ---\n{json.dumps(bridge_report, indent=2, sort_keys=True)}")
    sections.append(
        """\
You are TEAM_MEMBER: boss.

Synthesize the team work into the final answer. Requirements:
- Start with TEAM_MEMBER: boss.
- Include FINAL_ANSWER.
- Name each contributing role: supervisor, hr, conductor, critic, a2a-bridge.
- State the minimum makespan, one valid schedule, whether a third worker helps,
  and the critical path reasoning.
"""
    )
    return "\n\n".join(sections)


def score_result(role_outputs: dict[str, str], bridge_report: dict[str, Any], boss_output: str) -> dict[str, bool]:
    lower = boss_output.lower()
    role_markers = {
        role: bool(re.search(rf"\bteam_member\b\s*:?\s*{re.escape(role)}\b", output, re.IGNORECASE))
        for role, output in role_outputs.items()
    }
    boss_mentions = {
        role: role in lower
        for role in EXPECTED_INTERNAL_ROLES
    }
    return {
        "all_internal_llm_roles_answered": all(role_markers.values()),
        "a2a_bridge_ok": bridge_report.get("ok") is True,
        "boss_answered": bool(re.search(r"\bteam_member\s*:\s*boss\b", boss_output, re.IGNORECASE)),
        "boss_mentions_all_roles": all(boss_mentions.values()),
        "boss_has_makespan_8": bool(re.search(r"\b8\b", boss_output)) and "makespan" in lower,
        "boss_says_third_worker_no_help": "third" in lower
        and (
            "does not improve" in lower
            or "no improvement" in lower
            or "doesn't improve" in lower
            or "not improve" in lower
            or "makespan stays 8" in lower
            or "still 8" in lower
            or "cannot reduce" in lower
        ),
    }


def write_text(path: Path, text: str) -> None:
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def run_test(args: argparse.Namespace) -> dict[str, Any]:
    factory_dir = Path(args.factory_dir)
    test_id = args.test_id or time.strftime("%Y%m%d-%H%M%S")
    output_dir = factory_dir / "intelligence-tests" / test_id
    output_dir.mkdir(parents=True, exist_ok=True)
    write_text(output_dir / "problem.md", PROBLEM)

    role_outputs: dict[str, str] = {}
    for role in INTERNAL_LLM_ROLES:
        prompt = ROLE_PROMPTS[role].format(problem=PROBLEM)
        output = run_hermes(
            hermes_bin=args.hermes_bin,
            profile=role,
            prompt=prompt,
            model=args.model,
            timeout_seconds=args.timeout_seconds,
        )
        role_outputs[role] = output
        write_text(output_dir / f"{role}.md", output)

    bridge_report = check_a2a_bridge(Path(args.manifest))
    write_text(output_dir / "a2a-bridge.json", json.dumps(bridge_report, indent=2, sort_keys=True))

    manifest = load_manifest(Path(args.manifest))
    entry = public_entry(manifest)
    boss_output = a2a_send(
        str(entry["url"]).rstrip("/"),
        str(entry.get("auth_token") or ""),
        boss_prompt(role_outputs, bridge_report),
        timeout_seconds=args.timeout_seconds,
    )
    write_text(output_dir / "boss.md", boss_output)

    checks = score_result(role_outputs, bridge_report, boss_output)
    summary = {
        "ok": all(checks.values()),
        "test_id": test_id,
        "output_dir": str(output_dir),
        "model": args.model,
        "checks": checks,
        "artifacts": {
            "problem": str(output_dir / "problem.md"),
            "supervisor": str(output_dir / "supervisor.md"),
            "hr": str(output_dir / "hr.md"),
            "conductor": str(output_dir / "conductor.md"),
            "critic": str(output_dir / "critic.md"),
            "a2a_bridge": str(output_dir / "a2a-bridge.json"),
            "boss": str(output_dir / "boss.md"),
        },
    }
    write_text(output_dir / "summary.json", json.dumps(summary, indent=2, sort_keys=True))
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a real boss-team intelligence test in Docker.")
    parser.add_argument("--factory-dir", default=os.getenv("FACTORY_DIR", "/factory"))
    parser.add_argument("--manifest", default=os.getenv("HERMES_A2A_MANIFEST", "/opt/hermes-home/a2a-team.json"))
    parser.add_argument("--hermes-bin", default=os.getenv("HERMES_BIN", "/root/.local/bin/hermes"))
    parser.add_argument("--model", default=os.getenv("HERMES_HARNESS_CODEX_MODEL", "gpt-5.3-codex"))
    parser.add_argument("--timeout-seconds", type=int, default=int(os.getenv("HERMES_TEAM_TEST_TIMEOUT_SECONDS", "900")))
    parser.add_argument("--test-id", default="")
    args = parser.parse_args(argv)

    try:
        summary = run_test(args)
    except (RuntimeError, subprocess.TimeoutExpired, urllib.error.URLError) as exc:
        print(f"TEAM_INTELLIGENCE_TEST_FAILED: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
