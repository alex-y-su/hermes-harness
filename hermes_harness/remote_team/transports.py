from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from hermes_harness.remote_team import PROTOCOL_VERSION


class TransportError(RuntimeError):
    """Raised when a remote-team transport fails."""


def call_team(
    *,
    registry_path: Path,
    team: str,
    operation: str,
    request: dict[str, Any],
    timeout: int = 60,
) -> dict[str, Any]:
    registry = _load_registry(registry_path)
    teams = registry.get("remote_teams") or {}
    if team not in teams:
        raise TransportError(f"remote team is not registered: {team}")
    config = teams[team]
    if not isinstance(config, dict):
        raise TransportError(f"remote team config must be an object: {team}")
    payload = dict(request)
    payload["operation"] = operation
    payload.setdefault("target_team", team)
    payload.setdefault("board", config.get("board") or team)
    transport = str(config.get("transport") or "local")
    if transport == "local":
        return _call_local(config=config, payload=payload, timeout=timeout)
    if transport == "docker":
        return _call_docker(config=config, payload=payload, timeout=timeout)
    if transport in {"hermes-hub", "hermes_hub"}:
        return _call_hermes_hub(config=config, payload=payload, timeout=timeout)
    raise TransportError(f"unsupported transport for {team}: {transport}")


def _call_local(*, config: dict[str, Any], payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    env = os.environ.copy()
    if config.get("hermes_home"):
        env["HERMES_HOME"] = str(config["hermes_home"])
    env.update(_configured_env(config))
    command = [
        sys.executable,
        "-m",
        "hermes_harness.remote_team.cli",
        "receive",
        "--json",
    ]
    cwd = config.get("cwd")
    return _run_json(command, payload=payload, env=env, cwd=cwd, timeout=timeout)


def _call_docker(*, config: dict[str, Any], payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    container = config.get("container")
    if not container:
        raise TransportError("docker transport requires container")
    hermes_home = str(config.get("hermes_home") or "/vm/hermes-home")
    workdir = str(config.get("workdir") or "/workspace")
    python = str(config.get("python") or "python3")
    configured_env = _configured_env(config)
    command = [
        "docker",
        "exec",
        "-i",
        "-w",
        workdir,
        str(container),
        "env",
        f"HERMES_HOME={hermes_home}",
        *[f"{key}={value}" for key, value in configured_env.items()],
        python,
        "-m",
        "hermes_harness.remote_team.cli",
        "receive",
        "--json",
    ]
    return _run_json(command, payload=payload, env=os.environ.copy(), cwd=None, timeout=timeout)


def _call_hermes_hub(*, config: dict[str, Any], payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    client = _HubClient(config)
    client.ensure_ready()
    operation = str(payload.get("operation") or "")
    if operation == "health":
        return client.health(payload)
    if operation == "submit_or_get":
        return client.submit_or_get(payload, timeout=timeout)
    if operation == "status":
        return client.status(payload, timeout=timeout)
    raise TransportError(f"unsupported hermes-hub operation: {operation}")


class _HubClient:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.base_url = _required_config(config, "base_url", "url").rstrip("/")
        self.tenant_id = _required_config(config, "tenant_id", "tenant")
        self.token = _hub_token(config)
        self.state_path = _state_path(config)
        self.poll_interval = _positive_float(config.get("poll_interval_seconds"), default=2.0)

    def ensure_ready(self) -> None:
        if not self.config.get("ensure_tenant"):
            return
        response = self._request("GET", f"/v1/tenants/{self.tenant_id}", expected=(200, 404))
        if response["status"] == 200:
            return
        body = {
            "id": self.tenant_id,
            "displayName": self.config.get("display_name") or f"Remote team {self.tenant_id}",
            "agent": {"idleTimeoutSeconds": int(self.config.get("idle_timeout_seconds") or 300)},
        }
        self._request("POST", "/v1/tenants", body=body, expected=(201, 409))

    def health(self, payload: dict[str, Any]) -> dict[str, Any]:
        ready = self._request("GET", "/v1/readyz")
        tenant = self._request("GET", f"/v1/tenants/{self.tenant_id}")
        return {
            "ok": True,
            "protocol_version": PROTOCOL_VERSION,
            "status": "healthy",
            "transport": "hermes-hub",
            "hub": self.base_url,
            "tenant_id": self.tenant_id,
            "remote_team": payload.get("target_team"),
            "hub_status": ready["json"].get("status") if isinstance(ready["json"], dict) else None,
            "tenant_status": tenant["json"].get("status") if isinstance(tenant["json"], dict) else None,
            "agent_state": (tenant["json"].get("agent") or {}).get("state")
            if isinstance(tenant["json"], dict)
            else None,
        }

    def submit_or_get(self, payload: dict[str, Any], *, timeout: int) -> dict[str, Any]:
        state = self._load_state()
        key = _state_key(self.tenant_id, payload)
        entry = state.get(key)
        if not isinstance(entry, dict) or not entry.get("job_id"):
            job = self._create_cron_job(payload)
            entry = {
                "job_id": job["id"],
                "external_id": payload["external_id"],
                "tenant_id": self.tenant_id,
                "target_team": payload["target_team"],
                "board": payload.get("board"),
                "created_at": _now(),
            }
            state[key] = entry
            self._save_state(state)
        return self._wait_for_job(payload, str(entry["job_id"]), timeout=timeout)

    def status(self, payload: dict[str, Any], *, timeout: int) -> dict[str, Any]:
        state = self._load_state()
        key = _state_key(self.tenant_id, payload)
        entry = state.get(key)
        job_id = payload.get("remote_task_id")
        if not job_id and isinstance(entry, dict):
            job_id = entry.get("job_id")
        if _wants_fresh_status_report(payload):
            if not isinstance(entry, dict):
                entry = {}
            if job_id and not entry.get("job_id"):
                entry["job_id"] = str(job_id)
            job = self._create_cron_job(payload)
            entry["last_report_job_id"] = job["id"]
            entry["last_report_requested_at"] = _now()
            entry["external_id"] = payload.get("external_id")
            entry["tenant_id"] = self.tenant_id
            entry["target_team"] = payload.get("target_team")
            entry["board"] = payload.get("board")
            state[key] = entry
            self._save_state(state)
            return self._wait_for_job(payload, str(job["id"]), timeout=timeout)
        if not job_id:
            return {
                "ok": False,
                "protocol_version": PROTOCOL_VERSION,
                "external_id": payload.get("external_id"),
                "remote_team": payload.get("target_team"),
                "board": payload.get("board"),
                "status": "not_found",
                "result": None,
            }
        return self._response_from_job(payload, self._get_cron_job(str(job_id)))

    def _create_cron_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        prompt = _hub_prompt(payload, self.config)
        body = {"delaySeconds": int(self.config.get("delay_seconds") or 0), "payload": {"input": prompt}}
        response = self._request("POST", f"/v1/tenants/{self.tenant_id}/cron-jobs", body=body, expected=(201,))
        if not isinstance(response["json"], dict) or not response["json"].get("id"):
            raise TransportError("Hermes Hub cron response did not include a job id")
        return response["json"]

    def _wait_for_job(self, payload: dict[str, Any], job_id: str, *, timeout: int) -> dict[str, Any]:
        deadline = time.monotonic() + max(timeout, 1)
        last = self._get_cron_job(job_id)
        while str(last.get("status") or "") == "pending" and time.monotonic() < deadline:
            time.sleep(self.poll_interval)
            last = self._get_cron_job(job_id)
        return self._response_from_job(payload, last)

    def _get_cron_job(self, job_id: str) -> dict[str, Any]:
        response = self._request("GET", f"/v1/tenants/{self.tenant_id}/cron-jobs/{job_id}")
        if not isinstance(response["json"], dict):
            raise TransportError("Hermes Hub cron status response must be a JSON object")
        return response["json"]

    def _response_from_job(self, payload: dict[str, Any], job: dict[str, Any]) -> dict[str, Any]:
        job_status = str(job.get("status") or "")
        job_id = str(job.get("id") or "")
        remote_task_id = str(payload.get("remote_task_id") or job_id)
        if job_status == "pending":
            return {
                "ok": True,
                "protocol_version": PROTOCOL_VERSION,
                "external_id": payload.get("external_id"),
                "remote_task_id": remote_task_id,
                "remote_team": payload.get("target_team"),
                "board": payload.get("board"),
                "status": "running",
                "main_card_update": None,
                "result": None,
                "updated_at": _now(),
            }
        if job_status != "executed":
            return {
                "ok": False,
                "protocol_version": PROTOCOL_VERSION,
                "external_id": payload.get("external_id"),
                "remote_task_id": remote_task_id,
                "remote_team": payload.get("target_team"),
                "board": payload.get("board"),
                "status": job_status or "failed",
                "error": "hermes_hub_job_failed",
                "message": str(job.get("error") or "Hermes Hub job did not execute"),
                "result": job.get("result"),
                "updated_at": _now(),
            }
        remote_response = _remote_response_from_job(job)
        if not isinstance(remote_response, dict):
            raise TransportError("Hermes Hub remote response must be a JSON object")
        remote_response.setdefault("ok", True)
        remote_response.setdefault("protocol_version", PROTOCOL_VERSION)
        remote_response.setdefault("external_id", payload.get("external_id"))
        remote_response.setdefault("remote_task_id", remote_task_id)
        remote_response.setdefault("remote_team", payload.get("target_team"))
        remote_response.setdefault("board", payload.get("board"))
        remote_response.setdefault("updated_at", _now())
        remote_response.setdefault("status", "completed")
        if "main_card_update" not in remote_response and isinstance(remote_response.get("result"), dict):
            remote_response["main_card_update"] = remote_response["result"].get("main_card_update")
        _normalize_remote_response(remote_response)
        remote_response["hub"] = {
            "tenant_id": self.tenant_id,
            "job_id": job_id,
            "transport": "cron-runtime",
        }
        return remote_response

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        expected: tuple[int, ...] = (200,),
    ) -> dict[str, Any]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
            headers={
                "Accept": "application/json",
                "Authorization": "Bearer " + self.token,
            },
        )
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
                if response.status not in expected:
                    raise TransportError(f"Hermes Hub {method} {path} returned HTTP {response.status}: {raw}")
                return {"status": response.status, "json": _loads_json(raw)}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            if exc.code in expected:
                return {"status": exc.code, "json": _loads_json(raw)}
            raise TransportError(f"Hermes Hub {method} {path} returned HTTP {exc.code}: {raw}") from exc
        except urllib.error.URLError as exc:
            raise TransportError(f"Hermes Hub {method} {path} failed: {exc}") from exc

    def _load_state(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError as exc:
            raise TransportError(f"Hermes Hub transport state is invalid JSON: {self.state_path}") from exc
        if not isinstance(payload, dict):
            raise TransportError(f"Hermes Hub transport state must be a JSON object: {self.state_path}")
        return payload

    def _save_state(self, payload: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_name("." + self.state_path.name + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, self.state_path)


def _configured_env(config: dict[str, Any]) -> dict[str, str]:
    raw = config.get("env") or {}
    if not isinstance(raw, dict):
        return {}
    return {str(key): str(value) for key, value in raw.items()}


def _run_json(
    command: list[str],
    *,
    payload: dict[str, Any],
    env: dict[str, str],
    cwd: str | None,
    timeout: int,
) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        input=json.dumps(payload),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
        cwd=cwd,
        timeout=timeout,
    )
    if completed.returncode != 0:
        raise TransportError(
            f"remote-team command failed ({completed.returncode}): {' '.join(command)}\n{completed.stdout}"
        )
    try:
        response = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise TransportError(f"remote-team response was not JSON:\n{completed.stdout}") from exc
    if not isinstance(response, dict):
        raise TransportError("remote-team response must be a JSON object")
    return response


def _required_config(config: dict[str, Any], *names: str) -> str:
    for name in names:
        value = config.get(name)
        if value:
            return str(value)
    joined = " or ".join(names)
    raise TransportError(f"hermes-hub transport requires {joined}")


def _hub_token(config: dict[str, Any]) -> str:
    if config.get("api_token"):
        return str(config["api_token"])
    if config.get("api_token_env"):
        value = os.environ.get(str(config["api_token_env"]))
        if value:
            return value
        raise TransportError(f"environment variable is not set: {config['api_token_env']}")
    if config.get("api_token_file"):
        path = Path(str(config["api_token_file"])).expanduser()
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("HERMES_HUB_API_TOKEN="):
                return stripped.split("=", 1)[1].strip().strip("'\"")
        return path.read_text(encoding="utf-8").strip()
    value = os.environ.get("HERMES_HUB_API_TOKEN")
    if value:
        return value
    raise TransportError("hermes-hub transport requires api_token, api_token_env, api_token_file, or HERMES_HUB_API_TOKEN")


def _state_path(config: dict[str, Any]) -> Path:
    configured = config.get("state_path") or os.environ.get("HERMES_REMOTE_TEAM_HUB_STATE")
    if configured:
        return Path(str(configured)).expanduser()
    tenant = str(config.get("tenant_id") or config.get("tenant") or "tenant")
    return Path(os.environ.get("HERMES_HOME", ".")) / "remote-team-hub" / f"{tenant}.json"


def _state_key(tenant_id: str, payload: dict[str, Any]) -> str:
    return "\t".join(
        [
            tenant_id,
            str(payload.get("target_team") or ""),
            str(payload.get("board") or ""),
            str(payload.get("external_id") or ""),
        ]
    )


def _positive_float(value: Any, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _wants_fresh_status_report(payload: dict[str, Any]) -> bool:
    if _truthy(payload.get("force_report")):
        return True
    poll = payload.get("poll")
    return isinstance(poll, dict) and _truthy(poll.get("force_report"))


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _hub_prompt(payload: dict[str, Any], config: dict[str, Any]) -> str:
    task = payload.get("task") if isinstance(payload.get("task"), dict) else {}
    team_prompt = str(config.get("team_prompt") or "").strip()
    product_context = str(config.get("product_context") or "").strip()
    requested = json.dumps(payload, indent=2, sort_keys=True)
    return "\n".join(
        part
        for part in [
            "You are a hosted Hermes remote sub-team runtime.",
            "Process the delegated remote-team protocol request below as the sub-team, not as the main team.",
            _remote_kanban_operating_prompt(),
            _scheduled_poll_prompt(payload),
            "For X/social tasks, use the available local X gateway contract for this tenant: record accepted posts in $HERMES_HOME/mock-x/posts.jsonl as JSON lines with id, text, metadata, created_at, and mock_external_api='x'. Treat those receipts as successful X API responses for this environment.",
            "Return only one JSON object. Do not wrap it in Markdown.",
            "The JSON object must be compatible with this schema: "
            + json.dumps(_remote_response_schema(payload), sort_keys=True),
            "Product context:\n" + product_context if product_context else "",
            "Team-specific operating instructions:\n" + team_prompt if team_prompt else "",
            "Task title: " + str(task.get("title") or ""),
            "Remote-team protocol request JSON:\n" + requested,
        ]
        if part
    )


def _scheduled_poll_prompt(payload: dict[str, Any]) -> str:
    if str(payload.get("operation") or "") != "status" or not _wants_fresh_status_report(payload):
        return ""
    return (
        "This is a scheduled main-dashboard poll for an already running main-team card. "
        "Inspect the tenant's internal Kanban work and maintenance state for this external_id. "
        "Execute any due work that is inside the active strategy/time window, including due KPI checks "
        "and due X/social posts when the strategy calls for them. Then return a fresh status report. "
        "For creative/channel work, keep owning the creative strategy instead of waiting for the main team "
        "to specify individual actions. Translate source material into audience-facing work before publishing. "
        "Keep main_card_update.action='keep_running' while the cycle should continue; use 'block' for "
        "problems needing main-team attention and 'complete' only when the stop/end condition is satisfied. "
        "Your report must be cumulative: include prior strategy decisions, the execution ledger to date, "
        "new work performed in this poll, and your self-review."
    )


def _remote_kanban_operating_prompt() -> str:
    return """Default remote-Kanban operating rules:
- Treat the delegated request as a main-team Kanban card packet. Preserve external_id, source_board, source_task_id, target_team, board, requested KPIs, cycle window, review cadence, continue rule, stop rule, and next report due.
- The main team delegates outcomes, not a script. Own the strategy and execution. Choose a serious cadence, explain why, and do not optimize for the smallest output that might pass.
- If the work is creative, translate the delegated goal into audience-facing strategy. Do not copy internal implementation language just because it appears in context. Use technical terms only when they make the message sharper for the target audience.
- Create internal Kanban work for execution, KPI verification, blockers, and maintenance. Internal work must reference the originating external_id and source_task_id when available.
- A strategy/campaign/support cycle is not complete after one action. If the card has a cycle window, review cadence, next report due, or maintenance requirement, create an executable recurring schedule for the tenant to continue the work. Prefer the tenant's native cron/scheduler tool or $HERMES_HOME/cron/jobs.json. If no scheduler can be created, set maintenance_loop.status to blocked and add a blocker explaining that only a plan was created.
- Campaign reports must include an autonomy contract: strategy_decisions, execution_plan, execution_ledger, self_review, and next_adjustment. The ledger is cumulative across polls and must account for posts, KPI checks, skipped work, blockers, and schedule/heartbeat execution.
- When the tenant needs to report KPIs, problems, blockers, approvals, or stop/continue decisions back to the main team, emit a report envelope in main_card_update and result.reports. Each report must include report_type, external_id, source_task_id, severity, summary, reported_kpis, blockers, evidence, recommendation, next_report_due_at, and main_card_update.action.
- Use main_card_update.action='keep_running' for active cycles that should stay open, 'block' for problems requiring main-team attention, and 'complete' only for finite work whose definition of done is satisfied.
- Do not silently drop problems. If KPI collection, posting, scheduling, credentials, approval, or context is missing, report it as a blocker with main_card_update.action='block' unless the task can safely continue.
- Completion is forbidden until the cumulative ledger and self-review prove that the delegated outcome is actually satisfied. If the campaign is weak or under-executed, recommend iteration or continuation instead of pretending it succeeded."""


def _remote_response_schema(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "protocol_version": PROTOCOL_VERSION,
        "external_id": payload.get("external_id"),
        "remote_team": payload.get("target_team"),
        "board": payload.get("board"),
        "status": "completed",
        "main_card_update": {
            "action": "keep_running",
            "status": "running",
            "kpi_state": "collecting",
            "next_report_due_at": "ISO-8601 timestamp or clear date/time",
        },
        "result": {
            "remote_team_protocol": True,
            "mock_remote": False,
            "completed_deliverables": [],
            "strategy_decisions": [
                {
                    "decision": "cadence/channel/creative/KPI decision owned by the sub-team",
                    "rationale": "why this choice serves the delegated goal",
                }
            ],
            "execution_plan": {
                "cadence": "sub-team chosen cadence and rationale",
                "periods": [],
                "success_thresholds": [],
            },
            "execution_ledger": [
                {
                    "period": "launch|day-1|cycle-1",
                    "status": "done|active|skipped|blocked",
                    "posts": [],
                    "kpi_checks": [],
                    "blockers": [],
                    "evidence": [],
                }
            ],
            "self_review": {
                "assessment": "strong|adequate|weak|blocked",
                "reason": "sub-team critique of execution quality",
            },
            "next_adjustment": "what the sub-team will change next based on observed results",
            "requested_kpis": [],
            "reported_kpis": [],
            "mock_x_posts": [],
            "internal_tasks": [],
            "maintenance_loop": {
                "status": "active",
                "schedule": "description of executable tenant schedule or blocker",
                "next_run_at": "ISO-8601 timestamp when known",
            },
            "reports": [
                {
                    "report_type": "kpi|problem|cadence|approval|completion",
                    "external_id": payload.get("external_id"),
                    "source_task_id": payload.get("source_task_id"),
                    "severity": "info|warning|blocked",
                    "summary": "",
                    "reported_kpis": [],
                    "blockers": [],
                    "evidence": [],
                    "recommendation": "",
                    "next_report_due_at": "",
                    "main_card_update": {},
                }
            ],
            "evidence": [],
            "blockers": [],
            "next_recommendation": "",
            "main_card_update": {},
        },
    }


def _remote_response_from_job(job: dict[str, Any]) -> dict[str, Any]:
    result = job.get("result")
    if not isinstance(result, dict):
        raise TransportError("Hermes Hub executed job did not include a result object")
    text = result.get("responseText")
    if not isinstance(text, str) or not text.strip():
        raise TransportError("Hermes Hub executed job did not include responseText")
    parsed = _extract_json_object(text)
    if not isinstance(parsed, dict):
        raise TransportError("Hermes Hub responseText did not contain a JSON object")
    return parsed


def _normalize_remote_response(response: dict[str, Any]) -> None:
    result = response.get("result")
    if not isinstance(result, dict):
        return
    main_update = response.get("main_card_update")
    if isinstance(main_update, dict):
        result.setdefault("main_card_update", main_update)
    elif isinstance(result.get("main_card_update"), dict):
        response.setdefault("main_card_update", result["main_card_update"])

    requested = result.get("requested_kpis")
    if isinstance(requested, list) and requested and not result.get("reported_kpis"):
        measurement_window = result.get("measurement_window") or "configured measurement window"
        result["reported_kpis"] = [
            {
                "name": str(name),
                "status": "collecting",
                "measurement_window": measurement_window,
            }
            for name in requested
        ]
    elif isinstance(result.get("reported_kpis"), list):
        for item in result["reported_kpis"]:
            if isinstance(item, dict) and "status" not in item and item.get("state"):
                item["status"] = item["state"]

    loop = result.get("maintenance_loop")
    if isinstance(loop, dict) and "status" not in loop:
        loop["status"] = "active"
    if not isinstance(loop, dict):
        internal_tasks = result.get("internal_tasks")
        if isinstance(internal_tasks, list) and internal_tasks:
            result["maintenance_loop"] = {
                "status": "active",
                "task_ids": [
                    str(task.get("id"))
                    for task in internal_tasks
                    if isinstance(task, dict) and task.get("id")
                ],
            }


def _extract_json_object(text: str) -> Any:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise TransportError("response did not contain JSON object delimiters")
    try:
        return json.loads(stripped[start : end + 1])
    except json.JSONDecodeError as exc:
        raise TransportError(f"response JSON object is invalid: {exc}") from exc


def _loads_json(raw: str) -> Any:
    if not raw.strip():
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TransportError(f"Hermes Hub response was not JSON: {raw[:1000]}") from exc


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _load_registry(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TransportError(f"remote team registry not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise TransportError(f"remote team registry is invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise TransportError(f"remote team registry must be a JSON object: {path}")
    return payload
