from __future__ import annotations

import json
import re
import sys
from typing import Any

from hermes_harness.remote_team import PROTOCOL_VERSION


class ProtocolError(ValueError):
    """Raised when a remote-team request is malformed."""


def read_request() -> dict[str, Any]:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        raise ProtocolError(f"invalid JSON request: {exc}") from exc
    if not isinstance(payload, dict):
        raise ProtocolError("request must be a JSON object")
    return payload


def write_response(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def error_response(message: str, *, code: str = "protocol_error") -> dict[str, Any]:
    return {
        "ok": False,
        "protocol_version": PROTOCOL_VERSION,
        "error": code,
        "message": message,
    }


def validate_request(payload: dict[str, Any]) -> dict[str, Any]:
    version = str(payload.get("protocol_version") or PROTOCOL_VERSION)
    if version != PROTOCOL_VERSION:
        raise ProtocolError(f"unsupported protocol_version: {version}")
    operation = payload.get("operation")
    if operation not in {"submit_or_get", "status", "health"}:
        raise ProtocolError(f"unsupported operation: {operation}")
    if operation == "health":
        return payload
    if not payload.get("external_id"):
        raise ProtocolError("external_id is required")
    if not payload.get("target_team"):
        raise ProtocolError("target_team is required")
    if operation == "submit_or_get":
        task = payload.get("task")
        if not isinstance(task, dict):
            raise ProtocolError("task object is required for submit_or_get")
        if not task.get("title"):
            raise ProtocolError("task.title is required for submit_or_get")
    return payload


def heading_sections(body: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    known = {
        "card type",
        "stream",
        "goal",
        "hypothesis",
        "target audience",
        "approval required",
        "approval reason",
        "expected deliverables",
        "requested kpis",
        "measurement window",
        "cycle window",
        "review cadence",
        "continue rule",
        "stop rule",
        "next report due",
        "next report due at",
        "decision rule",
        "definition of done",
        "reporting format",
    }
    for raw in body.splitlines():
        line = raw.rstrip()
        heading_line = re.sub(r"^\s*#{1,6}\s*", "", line)
        colon = re.match(r"^\s*([A-Za-z][A-Za-z0-9 /_-]{1,60}):\s*(.*)$", heading_line)
        if colon:
            current = normalize_heading(colon.group(1))
            sections.setdefault(current, [])
            if colon.group(2).strip():
                sections[current].append(colon.group(2).strip())
            continue
        heading = normalize_heading(heading_line)
        if heading in known:
            current = heading
            sections.setdefault(current, [])
            continue
        if current and line.strip():
            sections[current].append(line.strip())
    return {key: "\n".join(value).strip() for key, value in sections.items()}


def normalize_heading(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower().replace("_", " "))


def section_items(value: str | None) -> list[str]:
    if not value:
        return []
    lines = []
    for line in value.splitlines():
        cleaned = re.sub(r"^\s*[-*0-9.)]+\s*", "", line).strip()
        if cleaned:
            lines.append(cleaned)
    if len(lines) <= 1:
        parts = [part.strip() for part in re.split(r";|\n", value) if part.strip()]
        if len(parts) > len(lines):
            lines = parts
    return lines


def task_contract(body: str, *, tenant: str | None = None) -> dict[str, Any]:
    sections = heading_sections(body)
    stream = (sections.get("stream") or "").strip().lower()
    if stream not in {"growth", "maintenance"}:
        stream = "maintenance" if tenant == "support" else "growth"
    card_type = _card_type(sections.get("card type"), stream)

    requested_kpis = section_items(sections.get("requested kpis"))
    if not requested_kpis:
        requested_kpis = ["primary KPI", "secondary KPI"]

    approval_text = (sections.get("approval required") or "").strip().lower()
    approval_required = _approval_required(approval_text)
    approval_tier = "human" if approval_required else ("automatic" if stream == "maintenance" else "profile")
    cycle_window = sections.get("cycle window") or ""
    review_cadence = sections.get("review cadence") or _default_review_cadence(card_type)
    continue_rule = sections.get("continue rule") or sections.get("decision rule") or ""
    stop_rule = sections.get("stop rule") or ""
    next_report_due_at = sections.get("next report due at") or sections.get("next report due") or ""

    return {
        "card_type": card_type,
        "stream": stream,
        "approval": {
            "required_before_external_action": approval_required,
            "tier": approval_tier,
            "reason": sections.get("approval reason") or "",
        },
        "requested_kpis": requested_kpis,
        "measurement_window": sections.get("measurement window") or "7 days after launch",
        "cycle_window": cycle_window,
        "review_cadence": review_cadence,
        "continue_rule": continue_rule,
        "stop_rule": stop_rule,
        "next_report_due_at": next_report_due_at,
        "decision_rule": sections.get("decision rule") or "Review result and decide continue, iterate, or stop.",
        "expected_deliverables": section_items(sections.get("expected deliverables")),
        "definition_of_done": sections.get("definition of done") or "",
        "reporting_format": sections.get("reporting format") or "",
    }


def main_card_update(contract: dict[str, Any], *, remote_status: str) -> dict[str, Any]:
    action = _main_card_action(contract, remote_status=remote_status)
    return {
        "action": action,
        "status": _main_card_status(action),
        "card_type": contract["card_type"],
        "remote_status": remote_status,
        "business_phase": _business_phase(contract, action=action),
        "kpi_state": _kpi_state(contract, action=action),
        "cycle_window": contract["cycle_window"],
        "review_cadence": contract["review_cadence"],
        "next_report_due_at": contract["next_report_due_at"],
        "continue_rule": contract["continue_rule"],
        "stop_rule": contract["stop_rule"],
        "reason": _main_card_reason(contract, action=action, remote_status=remote_status),
    }


def _approval_required(value: str) -> bool:
    if not value:
        return False
    if value in {"false", "no", "none", "not required"}:
        return False
    if value.startswith("auto-approved") or value.startswith("auto approved"):
        return False
    if "human-approved" in value or value.startswith("human"):
        return True
    return any(token in value for token in ("publish", "outreach", "send", "spend", "credential"))


def _card_type(value: str | None, stream: str) -> str:
    normalized = normalize_heading(value or "").replace(" ", "_").replace("-", "_")
    aliases = {
        "campaign": "campaign_cycle",
        "campaign_cycle": "campaign_cycle",
        "growth_cycle": "campaign_cycle",
        "support": "support_cycle",
        "support_cycle": "support_cycle",
        "maintenance_cycle": "support_cycle",
        "direction": "direction",
        "kpi": "kpi_review",
        "kpi_review": "kpi_review",
        "approval": "approval",
        "execution": "execution",
        "task": "execution",
    }
    if normalized in aliases:
        return aliases[normalized]
    if normalized == "cycle" and stream == "maintenance":
        return "support_cycle"
    return "execution"


def _default_review_cadence(card_type: str) -> str:
    if card_type == "campaign_cycle":
        return "daily status report; full review at the end of the cycle"
    if card_type == "support_cycle":
        return "daily support report; weekly maintenance review"
    if card_type == "direction":
        return "weekly direction review"
    return ""


def _main_card_action(contract: dict[str, Any], *, remote_status: str) -> str:
    if remote_status in {"blocked", "failed", "fail"}:
        return "block"
    if contract["card_type"] in {"campaign_cycle", "support_cycle", "direction"}:
        return "keep_running"
    return "complete"


def _main_card_status(action: str) -> str:
    return {
        "block": "blocked",
        "keep_running": "running",
        "complete": "done",
    }.get(action, "running")


def _business_phase(contract: dict[str, Any], *, action: str) -> str:
    if action == "block":
        return "blocked"
    if action == "complete":
        return "completed"
    if contract["card_type"] == "support_cycle":
        return "support_active"
    if contract["card_type"] == "direction":
        return "direction_active"
    return "campaign_active"


def _kpi_state(contract: dict[str, Any], *, action: str) -> str:
    if action == "block":
        return "blocked"
    if action == "complete":
        return "reported"
    if contract["card_type"] in {"campaign_cycle", "support_cycle", "direction"}:
        return "collecting"
    return "ready_to_measure"


def _main_card_reason(contract: dict[str, Any], *, action: str, remote_status: str) -> str:
    if action == "block":
        return f"Remote team status is {remote_status}."
    if action == "keep_running":
        return (
            f"{contract['card_type']} is an active cycle; keep the main card running "
            "until the cycle window, stop rule, continue rule, or a blocker resolves it."
        )
    return "Remote task satisfied the card's finite Definition of Done."
