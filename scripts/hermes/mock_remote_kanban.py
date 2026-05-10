"""Mock remote-team Kanban dispatcher hook for local Hermes testing.

This module is installed into ``$HERMES_INSTALL_DIR/hermes_cli`` by
``scripts/hermes/install-mock-kanban.sh``. It is intentionally shaped as a
Hermes Kanban dispatcher hook, not as a separate user-facing playground.

When the real dispatcher sees a ready task assigned to ``team:<name>``, the
patch calls ``dispatch_team_task(...)`` here instead of spawning
``hermes -p <profile>`` locally. The mock records a separate remote-team board
under the Hermes Kanban home and immediately returns a structured
growth/maintenance report. Random values are kept as test telemetry only; the
main contract is the KPI-aware task/result shape.
"""

from __future__ import annotations

import json
import os
import random
import re
import tempfile
import time
from pathlib import Path
from typing import Any


TEAM_PREFIX = "team:"
DEFAULT_SUCCESS_RATE = 0.75
DEFAULT_ACTIVE_CYCLE_TTL_SECONDS = 7 * 24 * 60 * 60


def is_team_assignee(assignee: str | None) -> bool:
    return bool(assignee and str(assignee).startswith(TEAM_PREFIX))


def dispatch_team_task(
    *,
    kb: Any,
    conn: Any,
    task_id: str,
    assignee: str,
    board: str | None = None,
) -> dict[str, Any]:
    """Claim a ``team:<name>`` task and resolve it through a mock remote board.

    Returns a small structured result used by the patched dispatcher for its
    telemetry. All durable task state is written through Hermes Kanban's own
    DB helpers.
    """
    team = _team_name(assignee)
    if not team:
        return {"ok": False, "handled": False, "error": "invalid_team_assignee"}

    task = kb.get_task(conn, task_id)
    if task is None:
        return {"ok": False, "handled": False, "error": "task_not_found"}
    if task.status != "ready":
        return {"ok": False, "handled": False, "error": f"task_not_ready:{task.status}"}

    claimed = kb.claim_task(conn, task_id)
    if claimed is None:
        return {"ok": False, "handled": False, "error": "claim_failed"}

    source_board = _source_board(kb, board)
    remote_board = _load_remote_board(kb, team, source_board)
    remote_task = _remote_task(remote_board, claimed, team, source_board)
    remote_task["attempts"] = int(remote_task.get("attempts") or 0) + 1

    rng = _rng(claimed.id, remote_task["attempts"])
    success_rate = _success_rate()
    success = rng.random() < success_rate
    now = _now()

    if success:
        result = _build_result(
            task=claimed,
            team=team,
            remote_task_id=remote_task["remote_task_id"],
            status="success",
            rng=rng,
        )
        main_update = result["main_card_update"]
        summary = (
            f"Mock remote team {team} reported {claimed.id}: "
            f"stream={result['stream']}, "
            f"card_type={result['card_type']}, "
            f"main_action={main_update['action']}, "
            f"kpis={len(result['reported_kpis'])}, "
            f"confidence={result['test_telemetry']['confidence']}."
        )
        remote_status = "running" if main_update["action"] == "keep_running" else "completed"
        remote_task.update(
            {
                "status": remote_status,
                "result": result,
                "completed_at": now if remote_status == "completed" else None,
                "updated_at": now,
            }
        )
        if main_update["action"] == "keep_running":
            ok = _record_running_report(kb, conn, claimed, result, summary)
        else:
            ok = kb.complete_task(
                conn,
                claimed.id,
                result=json.dumps(result, sort_keys=True),
                summary=summary,
                metadata=result,
            )
        if ok:
            kb.add_comment(conn, claimed.id, "mock-remote-kanban", summary)
    else:
        failure = _build_result(
            task=claimed,
            team=team,
            remote_task_id=remote_task["remote_task_id"],
            status="fail",
            rng=rng,
        )
        reason = (
            f"Mock remote team {team} failed {claimed.id}: "
            f"risk={failure['test_telemetry']['risk_score']}, "
            f"confidence={failure['test_telemetry']['confidence']}."
        )
        failure["reason"] = reason
        failure["blockers"].append(reason)
        remote_task.update(
            {
                "status": "failed",
                "result": failure,
                "completed_at": now,
                "updated_at": now,
            }
        )
        ok = kb.block_task(conn, claimed.id, reason=reason)
        if ok:
            kb.add_comment(
                conn,
                claimed.id,
                "mock-remote-kanban",
                json.dumps(failure, sort_keys=True),
            )

    _save_remote_board(kb, team, source_board, remote_board)
    return {
        "ok": bool(ok),
        "handled": True,
        "team": team,
        "remote_task_id": remote_task["remote_task_id"],
        "status": remote_task["status"],
    }


def _record_running_report(
    kb: Any,
    conn: Any,
    task: Any,
    result: dict[str, Any],
    summary: str,
) -> bool:
    """Keep an active main card running while storing the latest remote report."""
    result_json = json.dumps(result, sort_keys=True)
    ttl = _active_cycle_ttl_seconds()
    lock = getattr(task, "claim_lock", None)
    if lock:
        kb.heartbeat_claim(conn, task.id, ttl_seconds=ttl, claimer=lock)
    now = _now()
    with kb.write_txn(conn):
        cur = conn.execute(
            """
            UPDATE tasks
               SET result = ?,
                   claim_expires = CASE
                       WHEN claim_lock IS NULL THEN claim_expires
                       ELSE ?
                   END
             WHERE id = ?
               AND status = 'running'
            """,
            (result_json, now + ttl, task.id),
        )
        if cur.rowcount != 1:
            return False
        run_id = getattr(task, "current_run_id", None)
        if run_id is not None:
            conn.execute(
                """
                UPDATE task_runs
                   SET summary = ?,
                       metadata = ?,
                       claim_expires = ?
                 WHERE id = ?
                   AND ended_at IS NULL
                """,
                (summary, json.dumps(result, ensure_ascii=False), now + ttl, int(run_id)),
            )
        kb._append_event(
            conn,
            task.id,
            "remote_status_report",
            {
                "remote_team": result["team"],
                "remote_task_id": result["remote_task_id"],
                "main_card_update": result["main_card_update"],
                "summary": summary,
            },
            run_id=run_id,
        )
    return True


def _remote_task(remote_board: dict[str, Any], task: Any, team: str, board: str) -> dict[str, Any]:
    existing = remote_board["tasks"].get(task.id)
    if existing is not None:
        return existing
    remote_task_id = f"{team}:mock:{remote_board['next_id']}"
    remote_board["next_id"] += 1
    remote_task = {
        "external_id": task.id,
        "remote_task_id": remote_task_id,
        "team": team,
        "source_board": board,
        "title": task.title,
        "body": task.body,
        "tenant": task.tenant,
        "priority": task.priority,
        "status": "running",
        "attempts": 0,
        "result": None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    remote_board["tasks"][task.id] = remote_task
    return remote_task


def _numbers(rng: random.Random) -> dict[str, Any]:
    return {
        "readiness_score": rng.randint(1, 100),
        "risk_score": rng.randint(1, 100),
        "confidence": round(rng.uniform(0.35, 0.97), 2),
        "simulated_impact": rng.randint(10, 1000),
        "simulated_effort": rng.randint(1, 50),
    }


def _build_result(
    *,
    task: Any,
    team: str,
    remote_task_id: str,
    status: str,
    rng: random.Random,
) -> dict[str, Any]:
    body = task.body or ""
    sections = _sections(body)
    stream = _stream(task, sections)
    card_type = _card_type(sections, stream)
    requested_kpis = _requested_kpis(team, stream, sections)
    deliverables = _deliverables(team, stream, sections)
    measurement_window = _section_value(
        sections,
        "measurement window",
        "measurement",
        "test window",
    ) or _default_measurement_window(stream)
    decision_rule = _section_value(
        sections,
        "decision rule",
        "ship/kill rule",
        "stop/ship thresholds",
    ) or _default_decision_rule(stream)
    cycle_window = _section_value(sections, "cycle window") or ""
    review_cadence = _section_value(sections, "review cadence") or _default_review_cadence(card_type)
    continue_rule = _section_value(sections, "continue rule") or decision_rule
    stop_rule = _section_value(sections, "stop rule") or ""
    next_report_due_at = _section_value(sections, "next report due at", "next report due") or ""
    approval = _approval(body, stream, sections)
    telemetry = _numbers(rng)
    main_update = _main_card_update(
        card_type=card_type,
        status=status,
        cycle_window=cycle_window,
        review_cadence=review_cadence,
        continue_rule=continue_rule,
        stop_rule=stop_rule,
        next_report_due_at=next_report_due_at,
    )

    reported_kpis = [
        _reported_kpi(kpi, index, measurement_window, rng)
        for index, kpi in enumerate(requested_kpis, start=1)
    ]
    completed_deliverables = [
        f"Prepared {item}" for item in deliverables[:6]
    ] or [f"Prepared {team} {stream} execution brief"]

    result = {
        "mock_remote": True,
        "team": team,
        "remote_task_id": remote_task_id,
        "external_id": task.id,
        "status": status,
        "card_type": card_type,
        "stream": stream,
        "approval": approval,
        "completed_deliverables": completed_deliverables,
        "requested_kpis": requested_kpis,
        "reported_kpis": reported_kpis,
        "measurement_window": measurement_window,
        "cycle_window": cycle_window,
        "review_cadence": review_cadence,
        "continue_rule": continue_rule,
        "stop_rule": stop_rule,
        "next_report_due_at": next_report_due_at,
        "decision_rule": decision_rule,
        "main_card_update": main_update,
        "evidence": _evidence(team, stream, deliverables),
        "blockers": [],
        "next_recommendation": _next_recommendation(status, stream, approval, main_update),
        "test_telemetry": telemetry,
    }
    if stream == "maintenance":
        result["maintenance_summary"] = {
            "kept_current": deliverables[:3] or [f"{team} operating checklist"],
            "watch_items": _maintenance_watch_items(team),
        }
    else:
        result["growth_summary"] = {
            "hypothesis": _section_value(sections, "hypothesis")
            or f"{team} experiment can create measurable growth signal.",
            "launchable": approval["tier"] != "human" or not approval["required_before_external_action"],
        }
    return result


def _sections(body: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    known_headings = {
        "card type",
        "stream",
        "goal",
        "hypothesis",
        "target audience",
        "approval required",
        "approval reason",
        "expected deliverables",
        "expected output",
        "deliverables",
        "requested kpis",
        "kpis",
        "success metrics",
        "primary metric",
        "reporting kpis",
        "measurement window",
        "measurement",
        "test window",
        "cycle window",
        "review cadence",
        "continue rule",
        "stop rule",
        "next report due",
        "next report due at",
        "decision rule",
        "ship/kill rule",
        "stop/ship thresholds",
        "definition of done",
        "reporting format",
    }
    for raw_line in body.splitlines():
        line = raw_line.rstrip()
        heading_line = re.sub(r"^\s*#{1,6}\s*", "", line)
        match = re.match(r"^\s*(?:[-*]\s*)?([A-Za-z][A-Za-z0-9 /_-]{1,60}):\s*(.*)$", heading_line)
        if match:
            current = _norm_key(match.group(1))
            sections.setdefault(current, [])
            if match.group(2):
                sections[current].append(match.group(2).strip())
            continue
        heading = _norm_key(heading_line)
        if heading in known_headings:
            current = heading
            sections.setdefault(current, [])
            continue
        if current and line.strip():
            sections[current].append(line.strip())
    return {key: "\n".join(value).strip() for key, value in sections.items()}


def _norm_key(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower().replace("_", " "))


def _section_value(sections: dict[str, str], *names: str) -> str | None:
    for name in names:
        value = sections.get(_norm_key(name))
        if value:
            return value
    return None


def _items(value: str | None) -> list[str]:
    if not value:
        return []
    items: list[str] = []
    for line in value.splitlines():
        cleaned = re.sub(r"^\s*[-*0-9.)]+\s*", "", line).strip()
        if cleaned:
            items.append(cleaned)
    if len(items) <= 1:
        parts = [part.strip() for part in re.split(r";|\n", value) if part.strip()]
        if len(parts) > len(items):
            items = parts
    return items


def _stream(task: Any, sections: dict[str, str]) -> str:
    stream = _section_value(sections, "stream", "workstream", "queue")
    if stream:
        normalized = _slug(stream)
        if normalized in {"maintenance", "support", "upkeep"}:
            return "maintenance"
        if normalized in {"growth", "experiment", "expansion"}:
            return "growth"
    tenant = _slug(getattr(task, "tenant", "") or "")
    if tenant in {"support", "maintenance", "upkeep"}:
        return "maintenance"
    body = (getattr(task, "body", None) or "").lower()
    if any(word in body for word in ("maintenance", "refresh", "monitor", "repair", "follow-up", "follow up", "upkeep")):
        return "maintenance"
    return "growth"


def _card_type(sections: dict[str, str], stream: str) -> str:
    explicit = _section_value(sections, "card type")
    normalized = _norm_key(explicit or "").replace(" ", "_").replace("-", "_")
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


def _requested_kpis(team: str, stream: str, sections: dict[str, str]) -> list[str]:
    explicit = _items(
        _section_value(
            sections,
            "requested kpis",
            "kpis",
            "success metrics",
            "primary metric",
            "reporting kpis",
        )
    )
    if explicit:
        return explicit[:8]
    defaults = {
        "seo": ["qualified organic visits", "target keyword movement", "CTA clicks"],
        "social": ["qualified replies", "profile visits", "post engagement rate"],
        "email": ["open rate", "click rate", "conversion to next step"],
        "video": ["watch-through rate", "CTA clicks", "qualified comments"],
        "partnerships": ["positive reply rate", "pilot acceptances", "partner-sourced visits"],
        "growth": ["activation rate", "invite/share rate", "trial-to-success conversion"],
        "analytics": ["dashboard coverage", "metric freshness", "unexplained anomaly count"],
    }
    if stream == "maintenance":
        return [
            "items kept current",
            "broken links or stale assets found",
            "response SLA met",
        ]
    return defaults.get(team, ["primary success metric", "secondary signal", "guardrail metric"])


def _deliverables(team: str, stream: str, sections: dict[str, str]) -> list[str]:
    explicit = _items(
        _section_value(
            sections,
            "expected deliverables",
            "expected output",
            "deliverables",
            "definition of done",
        )
    )
    if explicit:
        return explicit[:8]
    if stream == "maintenance":
        return ["maintenance checklist", "issue list", "recommended next actions"]
    defaults = {
        "seo": ["content brief", "keyword cluster", "CTA plan"],
        "social": ["post package", "hook variants", "metric map"],
        "email": ["email sequence", "subject variants", "instrumentation plan"],
        "video": ["storyboard", "script", "asset list"],
        "partnerships": ["partner shortlist", "outreach copy", "pilot criteria"],
        "growth": ["experiment spec", "event taxonomy", "decision rule"],
    }
    return defaults.get(team, ["execution brief", "measurement plan"])


def _approval(body: str, stream: str, sections: dict[str, str]) -> dict[str, Any]:
    lowered = body.lower()
    explicit = _section_value(sections, "approval required")
    explicit_required: bool | None = None
    if explicit is not None:
        explicit_normalized = explicit.strip().lower()
        if (
            explicit_normalized in {"true", "yes", "required", "human"}
            or "human-approved" in explicit_normalized
            or "human approval required" in explicit_normalized
            or explicit_normalized.startswith("human")
        ):
            explicit_required = True
        elif (
            explicit_normalized in {"false", "no", "none", "not required"}
            or explicit_normalized.startswith("auto-approved")
            or explicit_normalized.startswith("auto approved")
        ):
            explicit_required = False
    external_action = any(
        phrase in lowered
        for phrase in (
            "send email",
            "send emails",
            "post to",
            "publish",
            "paid ad",
            "spend",
            "outreach",
            "contact",
            "customer data",
            "credentials",
        )
    )
    spend_required = bool(re.search(r"\$\d+|\bpaid\b|\bspend\b|\bbudget\b", lowered))
    approval_required = explicit_required if explicit_required is not None else external_action or spend_required
    tier = "human" if approval_required else ("profile" if stream == "growth" else "automatic")
    return {
        "required_before_external_action": approval_required,
        "tier": tier,
        "reason": (
            "External-world action, spend, credentials, or customer data may be involved."
            if approval_required
            else "Draft, planning, analysis, and mock execution are safe to run without human approval."
        ),
        "allowed_without_approval": [
            "research",
            "drafting",
            "planning",
            "mock execution",
            "internal analysis",
        ],
    }


def _reported_kpi(kpi: str, index: int, measurement_window: str, rng: random.Random) -> dict[str, Any]:
    return {
        "name": kpi,
        "measurement_window": measurement_window,
        "mock_baseline": rng.randint(1, 50) * index,
        "mock_target": rng.randint(55, 180) * index,
        "status": rng.choice(["needs_real_data", "ready_to_measure", "instrumentation_required"]),
    }


def _evidence(team: str, stream: str, deliverables: list[str]) -> list[str]:
    evidence = [f"mock remote {team} board entry", f"{stream} task contract"]
    evidence.extend(deliverables[:3])
    return evidence


def _default_review_cadence(card_type: str) -> str:
    if card_type == "campaign_cycle":
        return "daily status report; full review at the end of the cycle"
    if card_type == "support_cycle":
        return "daily support report; weekly maintenance review"
    if card_type == "direction":
        return "weekly direction review"
    return ""


def _main_card_update(
    *,
    card_type: str,
    status: str,
    cycle_window: str,
    review_cadence: str,
    continue_rule: str,
    stop_rule: str,
    next_report_due_at: str,
) -> dict[str, Any]:
    action = _main_card_action(card_type, status=status)
    return {
        "action": action,
        "status": _main_card_status(action),
        "card_type": card_type,
        "remote_status": "blocked" if status != "success" else "reported",
        "business_phase": _business_phase(card_type, action),
        "kpi_state": _kpi_state(card_type, action),
        "cycle_window": cycle_window,
        "review_cadence": review_cadence,
        "next_report_due_at": next_report_due_at,
        "continue_rule": continue_rule,
        "stop_rule": stop_rule,
        "reason": _main_card_reason(card_type, action=action, status=status),
    }


def _main_card_action(card_type: str, *, status: str) -> str:
    if status != "success":
        return "block"
    if card_type in {"campaign_cycle", "support_cycle", "direction"}:
        return "keep_running"
    return "complete"


def _main_card_status(action: str) -> str:
    return {
        "block": "blocked",
        "keep_running": "running",
        "complete": "done",
    }.get(action, "running")


def _business_phase(card_type: str, action: str) -> str:
    if action == "block":
        return "blocked"
    if action == "complete":
        return "completed"
    if card_type == "support_cycle":
        return "support_active"
    if card_type == "direction":
        return "direction_active"
    return "campaign_active"


def _kpi_state(card_type: str, action: str) -> str:
    if action == "block":
        return "blocked"
    if action == "complete":
        return "reported"
    if card_type in {"campaign_cycle", "support_cycle", "direction"}:
        return "collecting"
    return "ready_to_measure"


def _main_card_reason(card_type: str, *, action: str, status: str) -> str:
    if action == "block":
        return f"Remote team returned {status}."
    if action == "keep_running":
        return (
            f"{card_type} is an active cycle; keep the main card running "
            "until the cycle window, stop rule, continue rule, or a blocker resolves it."
        )
    return "Remote task satisfied the card's finite Definition of Done."


def _next_recommendation(
    status: str,
    stream: str,
    approval: dict[str, Any],
    main_update: dict[str, Any],
) -> str:
    if status != "success":
        return "Revise the task contract, reduce scope, and retry with clearer KPI requirements."
    if main_update["action"] == "keep_running":
        return "Keep the main card running and continue KPI/support reporting on the configured cadence."
    if approval["required_before_external_action"]:
        return "Request human approval before publishing, spending, outreach, or credentialed execution."
    if stream == "maintenance":
        return "Schedule the next maintenance check and escalate only broken or stale assets."
    return "Review the KPI contract, then approve execution or promote the best deliverable to launch."


def _default_measurement_window(stream: str) -> str:
    return "weekly recurring check" if stream == "maintenance" else "7 days after launch"


def _default_decision_rule(stream: str) -> str:
    if stream == "maintenance":
        return "Escalate if any critical asset is stale, broken, or missing an owner."
    return "Continue if the primary KPI beats baseline without violating guardrails."


def _maintenance_watch_items(team: str) -> list[str]:
    defaults = {
        "seo": ["ranking decay", "broken internal links", "stale screenshots"],
        "social": ["unanswered qualified replies", "stale content calendar", "negative sentiment"],
        "email": ["deliverability drift", "broken links", "segment decay"],
        "video": ["thumbnail decay", "low retention", "missing cutdowns"],
        "partnerships": ["stale follow-ups", "blocked partner assets", "unowned next steps"],
        "growth": ["funnel drop-offs", "broken activation events", "stale onboarding copy"],
    }
    return defaults.get(team, ["stale work", "missing owner", "broken metric"])


def _load_remote_board(kb: Any, team: str, board: str) -> dict[str, Any]:
    path = _board_path(kb, team, board)
    if not path.exists():
        return {
            "team": team,
            "source_board": board,
            "next_id": 1,
            "tasks": {},
            "created_at": _now(),
            "updated_at": _now(),
        }
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"mock remote board must be a JSON object: {path}")
    return payload


def _save_remote_board(kb: Any, team: str, board: str, payload: dict[str, Any]) -> None:
    payload["updated_at"] = _now()
    path = _board_path(kb, team, board)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temp_path = Path(handle.name)
    temp_path.replace(path)


def _board_path(kb: Any, team: str, board: str) -> Path:
    safe_board = _slug(board)
    safe_team = _slug(team)
    return kb.kanban_home() / "mock-remote-kanban" / safe_board / safe_team / "board.json"


def _team_name(assignee: str) -> str:
    return _slug(str(assignee)[len(TEAM_PREFIX) :])


def _source_board(kb: Any, board: str | None) -> str:
    if board:
        return _slug(board)
    env_board = os.environ.get("HERMES_KANBAN_BOARD")
    if env_board:
        return _slug(env_board)
    try:
        current = kb.get_current_board()
        if current:
            return _slug(current)
    except Exception:
        pass
    return "default"


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(value).strip().lower()).strip("-_")
    return slug or "default"


def _rng(task_id: str, attempt: int) -> random.Random:
    seed = os.environ.get("HERMES_MOCK_KANBAN_SEED")
    if seed:
        return random.Random(f"{seed}:{task_id}:{attempt}")
    return random.Random()


def _success_rate() -> float:
    raw = os.environ.get("HERMES_MOCK_KANBAN_SUCCESS_RATE", str(DEFAULT_SUCCESS_RATE))
    try:
        return max(0.0, min(1.0, float(raw)))
    except ValueError:
        return DEFAULT_SUCCESS_RATE


def _active_cycle_ttl_seconds() -> int:
    raw = os.environ.get(
        "HERMES_MOCK_KANBAN_ACTIVE_TTL_SECONDS",
        str(DEFAULT_ACTIVE_CYCLE_TTL_SECONDS),
    )
    try:
        return max(60, int(raw))
    except ValueError:
        return DEFAULT_ACTIVE_CYCLE_TTL_SECONDS


def _now() -> int:
    return int(time.time())
