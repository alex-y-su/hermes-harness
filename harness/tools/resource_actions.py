from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from harness import db
from harness.resources import get_resource, normalize_resource_id
from harness.tools import resource_gate
from harness.tools.common import add_factory_args, paths


ACTIVE_STATES = ("pending", "approval-required", "ready")
TERMINAL_STATES = ("completed", "released", "failed", "needs-human")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Process hub-side resource action cards.")
    add_factory_args(parser)
    sub = parser.add_subparsers(dest="command", required=True)

    list_cmd = sub.add_parser("list", help="List resource action cards.")
    list_cmd.add_argument("--state", default="active", help="active, all, or an exact card state.")
    list_cmd.add_argument("--json", action="store_true")

    get_cmd = sub.add_parser("get", help="Inspect one resource action card.")
    get_cmd.add_argument("card")
    get_cmd.add_argument("--json", action="store_true")

    process = sub.add_parser("process", help="Gate, request approval for, and execute ready cards.")
    process.add_argument("--limit", type=int, default=20)
    process.add_argument("--no-execute", action="store_true", help="Do not execute ready cards.")
    process.add_argument("--loop", action="store_true")
    process.add_argument("--poll-seconds", type=int, default=30)
    process.add_argument("--holder", default=None)
    process.add_argument("--json", action="store_true")

    return parser


def run(args: argparse.Namespace) -> dict[str, Any]:
    factory, db_path = paths(args)
    if args.command == "list":
        cards = list_cards(factory, state=args.state)
        return {"count": len(cards), "cards": cards}
    if args.command == "get":
        path = _resolve_card_path(factory, args.card)
        return {"card": _read_card(path), "path": str(path)}
    if args.command == "process":
        if args.loop:
            return _loop(args, factory, db_path)
        return process_once(
            factory=factory,
            db_path=db_path,
            limit=args.limit,
            execute=not args.no_execute,
            holder=args.holder,
        )
    raise SystemExit(f"unknown command: {args.command}")


def _loop(args: argparse.Namespace, factory: Path, db_path: Path) -> dict[str, Any]:
    holder = args.holder or f"resource-actions:{os.getpid()}"
    last: dict[str, Any] = {}
    while True:
        last = process_once(
            factory=factory,
            db_path=db_path,
            limit=args.limit,
            execute=not args.no_execute,
            holder=holder,
        )
        time.sleep(max(1, int(args.poll_seconds)))
    return last


def process_once(
    *,
    factory: Path,
    db_path: Path,
    limit: int = 20,
    execute: bool = True,
    holder: str | None = None,
) -> dict[str, Any]:
    holder = holder or f"resource-actions:{os.getpid()}"
    with db.session(db_path) as conn:
        if not db.acquire_lease(conn, resource_type="resource-actions", resource_id="global", holder=holder, ttl_seconds=60):
            return {"processed": [], "skipped": [{"reason": "lease_held"}], "count": 0}
    processed: list[dict[str, Any]] = []
    harvested: list[dict[str, Any]] = []
    try:
        harvested = harvest_cards(factory)
        for state in ACTIVE_STATES:
            for card in list_cards(factory, state=state):
                if len(processed) >= limit:
                    break
                result = _process_card(factory=factory, db_path=db_path, card=card, execute=execute)
                processed.append(result)
            if len(processed) >= limit:
                break
    finally:
        with db.session(db_path) as conn:
            db.release_lease(conn, resource_type="resource-actions", resource_id="global", holder=holder)
    return {"processed": processed, "harvested": harvested, "count": len(processed)}


def harvest_cards(factory: Path) -> list[dict[str, Any]]:
    root = factory / "teams"
    if not root.exists():
        return []
    harvested: list[dict[str, Any]] = []
    for path in _iter_outbox_artifacts(factory):
        if not path.is_file() or path.name.startswith("."):
            continue
        cards = _cards_from_outbox_artifact(path, factory=factory)
        for card in cards:
            if _card_exists(factory, str(card["card_id"])):
                continue
            pending = factory / "resource_action_cards" / "pending" / f"{card['card_id']}.json"
            pending.parent.mkdir(parents=True, exist_ok=True)
            pending.write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            harvested.append({"card_id": card["card_id"], "path": str(pending), "source": str(path)})
    return harvested


def _iter_outbox_artifacts(factory: Path) -> list[Path]:
    root = factory / "teams"
    seen: set[Path] = set()
    paths: list[Path] = []
    for pattern in ("*/outbox/*", "*/factory/teams/*/outbox/*"):
        for path in root.glob(pattern):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            paths.append(path)
    return sorted(paths)


def list_cards(factory: Path, *, state: str = "active") -> list[dict[str, Any]]:
    states = ACTIVE_STATES if state == "active" else tuple(resource_gate.CARD_STATES) if state == "all" else (state,)
    cards: list[dict[str, Any]] = []
    for item_state in states:
        root = factory / "resource_action_cards" / item_state
        if not root.exists():
            continue
        for path in sorted(root.glob("*.json"), key=lambda item: (item.stat().st_mtime, item.name)):
            card = _read_card(path)
            card["_path"] = str(path)
            card["_state_dir"] = item_state
            cards.append(card)
    return cards


def _process_card(*, factory: Path, db_path: Path, card: dict[str, Any], execute: bool) -> dict[str, Any]:
    state = str(card.get("status") or card.get("_state_dir") or "")
    if state == "pending":
        gated = resource_gate.gate_card(factory=factory, card_ref=str(card.get("_path") or card["card_id"]))
        gated_card = gated["card"]
        if gated_card["status"] == "approval-required":
            _ensure_approval_request(factory, db_path, gated_card, Path(gated["path"]))
        _sync_ticket_for_card(db_path, gated_card)
        return {"card_id": gated_card["card_id"], "action": "gated", "status": gated_card["status"], "path": gated["path"]}
    if state == "approval-required":
        return _process_approval_required(factory=factory, db_path=db_path, card=card)
    if state == "ready":
        if not execute:
            return {"card_id": card["card_id"], "action": "ready", "status": "ready", "path": card.get("_path")}
        return _execute_ready_card(factory=factory, db_path=db_path, card=card)
    return {"card_id": card.get("card_id"), "action": "skipped", "status": state, "path": card.get("_path")}


def _cards_from_outbox_artifact(path: Path, *, factory: Path | None = None) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".json" and (
        path.name.endswith(".resource-action.json")
        or path.name.endswith(".resource-action-card.json")
        or path.name.endswith(".resource-actions.json")
    ):
        data = json.loads(path.read_text(encoding="utf-8"))
        values = data if isinstance(data, list) else [data]
        cards = []
        for value in values:
            if isinstance(value, dict):
                card = _normalize_outbox_card(value, source_path=path, factory=factory)
                if card:
                    cards.append(card)
        return cards
    if path.suffix.lower() == ".md":
        text = path.read_text(encoding="utf-8", errors="replace")
        if not _is_explicit_markdown_card(text):
            return []
        parsed = _parse_markdown_card(text, source_path=path, factory=factory)
        return [parsed] if parsed else []
    return []


def _normalize_outbox_card(raw: dict[str, Any], *, source_path: Path, factory: Path | None = None) -> dict[str, Any] | None:
    resource_id = raw.get("resource_id") or raw.get("resource") or raw.get("target_resource")
    action = raw.get("action") or raw.get("resource_action")
    ticket_id = raw.get("ticket_id") or raw.get("assignment_id") or _ticket_id_from_source(source_path)
    artifact = raw.get("artifact") or raw.get("artifact_path") or raw.get("patch_artifact") or str(source_path)
    if not resource_id or not action or not ticket_id:
        return None
    team = raw.get("team") or _team_from_source_path(source_path, factory=factory)
    metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    for key in ("blast_radius", "rollback", "fallback", "preconditions", "expected_impact"):
        if raw.get(key) is not None and key not in metadata:
            metadata[key] = raw[key]
    card_id = str(raw.get("card_id") or _card_id(str(ticket_id), str(resource_id), str(action)))
    return {
        "card_id": card_id,
        "status": "pending",
        "ticket_id": str(ticket_id),
        "team": str(team),
        "resource_id": normalize_resource_id(str(resource_id)),
        "action": str(action),
        "artifact": str(artifact),
        "why": str(raw.get("why") or raw.get("reason") or raw.get("title") or "resource action requested by team artifact"),
        "title": str(raw.get("title") or f"{action} on {resource_id}"),
        "created_at": _iso_now(),
        "source_artifact": str(source_path),
        "metadata": metadata,
    }


def _team_from_source_path(source_path: Path, *, factory: Path | None = None) -> str:
    if factory is not None:
        try:
            parts = source_path.relative_to(factory / "teams").parts
            if parts:
                return parts[0]
        except ValueError:
            pass
    try:
        return source_path.parents[1].name
    except IndexError:
        return "resource-manager"


def _parse_markdown_card(text: str, *, source_path: Path, factory: Path | None = None) -> dict[str, Any] | None:
    fields = _markdown_fields(text)
    resource_id = fields.get("resource_id") or fields.get("resource") or fields.get("target_resource")
    action = fields.get("action") or fields.get("resource_action")
    if not resource_id or not action:
        return None
    return _normalize_outbox_card(
        {
            "resource_id": resource_id,
            "action": action,
            "ticket_id": fields.get("ticket_id") or fields.get("assignment_id"),
            "team": fields.get("team"),
            "artifact": fields.get("artifact") or fields.get("artifact_path") or fields.get("patch_artifact"),
            "why": fields.get("why") or fields.get("reason"),
            "title": _markdown_title(text),
            "blast_radius": fields.get("blast_radius"),
            "rollback": fields.get("rollback"),
            "fallback": fields.get("fallback"),
        },
        source_path=source_path,
        factory=factory,
    )


def _markdown_fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip().lstrip("-").strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().strip("`").lower().replace("-", "_").replace(" ", "_")
        value = value.strip().strip("`")
        if key and value and key not in fields:
            fields[key] = value
    return fields


def _markdown_title(text: str) -> str | None:
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return None


def _is_explicit_markdown_card(text: str) -> bool:
    for raw in text.splitlines()[:20]:
        line = raw.strip()
        if line.startswith("#") and "Resource-Action Card" in line:
            return True
        normalized = line.lower().replace("-", "_").replace(" ", "_")
        if normalized in {"resource_action_card:true", "resource_action_card:yes"}:
            return True
    return False


def _ticket_id_from_source(path: Path) -> str:
    name = path.name
    if name.startswith("tkt-"):
        return name.split(".", 1)[0].removesuffix("-prepare").removesuffix("-patch").removesuffix("-verify")
    return path.stem


def _card_exists(factory: Path, card_id: str) -> bool:
    for state in resource_gate.CARD_STATES:
        if (factory / "resource_action_cards" / state / f"{card_id}.json").exists():
            return True
    return False


def _card_id(ticket_id: str, resource_id: str, action: str) -> str:
    return f"{_slug(ticket_id)}__{_slug(resource_id)}__{_slug(action)}"


def _slug(value: str) -> str:
    import re

    return re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value).strip("/")).strip("-").lower()


def _process_approval_required(*, factory: Path, db_path: Path, card: dict[str, Any]) -> dict[str, Any]:
    path = Path(str(card["_path"]))
    request_id = str(card.get("approval_request_id") or _approval_request_id(card))
    request = None
    with db.session(db_path) as conn:
        row = conn.execute("SELECT * FROM approval_requests WHERE request_id = ?", (request_id,)).fetchone()
        request = dict(row) if row else None
    if request is None:
        _ensure_approval_request(factory, db_path, card, path)
        return {"card_id": card["card_id"], "action": "approval-request-created", "status": "approval-required", "request_id": request_id}
    response = _decode_json(request.get("response_json"), default=None)
    if request["status"] == "denied" or (isinstance(response, dict) and response.get("approved") is False):
        _release_card_reservation(factory, card, reason="approval denied")
        updated = {**card, "status": "released", "released_at": _iso_now(), "approval_status": "denied"}
        target = _move_card(path, updated, "released")
        _sync_ticket_for_card(db_path, updated, override_status="canceled")
        return {"card_id": card["card_id"], "action": "released", "status": "released", "path": str(target)}
    if request["status"] in {"supplied", "resolved", "resuming"} and _approved(response):
        updated = {**card, "status": "ready", "approved_at": request.get("resolved_at") or _iso_now(), "approval_status": request["status"]}
        target = _move_card(path, updated, "ready")
        _sync_ticket_for_card(db_path, updated, override_status="ready")
        return {"card_id": card["card_id"], "action": "approved", "status": "ready", "path": str(target)}
    return {"card_id": card["card_id"], "action": "waiting-for-approval", "status": "approval-required", "request_id": request_id}


def _execute_ready_card(*, factory: Path, db_path: Path, card: dict[str, Any]) -> dict[str, Any]:
    path = Path(str(card["_path"]))
    resource = get_resource(factory, str(card["resource_id"]))
    if resource is None:
        return _fail_card(factory, db_path, path, card, "resource_not_found")
    execution = _execution_config(resource, str(card["action"]))
    if execution is None:
        return _needs_human(factory, db_path, path, card, "missing_execution_config")
    if not _hub_location_allowed(execution):
        return _needs_human(factory, db_path, path, card, "execution_not_hub_location")
    command = _resolve_command(factory, execution)
    if command is None:
        return _needs_human(factory, db_path, path, card, "missing_hub_skill_command")

    log_path = factory / "resource_action_logs" / f"{card['card_id']}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "HARNESS_FACTORY": str(factory),
        "HARNESS_RESOURCE_ACTION_CARD": str(path),
        "HARNESS_RESOURCE_ID": str(card["resource_id"]),
        "HARNESS_RESOURCE_ACTION": str(card["action"]),
        "HARNESS_RESOURCE_ARTIFACT": str(card.get("artifact") or ""),
        "HARNESS_RESOURCE_TICKET_ID": str(card["ticket_id"]),
    }
    timeout = int(execution.get("timeout_seconds") or 900)
    started = _iso_now()
    with log_path.open("w", encoding="utf-8") as log:
        log.write(f"started_at={started}\ncommand={json.dumps(command)}\n\n")
        try:
            completed = subprocess.run(
                command,
                cwd=str(factory),
                env=env,
                text=True,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return _fail_card(factory, db_path, path, card, "execution_timeout", log_path=log_path)
    if completed.returncode != 0:
        return _fail_card(factory, db_path, path, card, f"execution_exit_{completed.returncode}", log_path=log_path)

    external_ref = _external_ref(log_path) or str(log_path)
    resource_gate.commit_usage(
        factory=factory,
        resource_id=str(card["resource_id"]),
        action=str(card["action"]),
        ticket_id=str(card["ticket_id"]),
        reservation_id=card.get("reservation_id"),
        external_ref=external_ref,
        metadata={"card_id": card["card_id"], "log_path": str(log_path)},
    )
    updated = {
        **card,
        "status": "completed",
        "executed_at": _iso_now(),
        "execution": {"external_ref": external_ref, "log_path": str(log_path), "command_kind": _command_kind(execution)},
    }
    target = _move_card(path, updated, "completed")
    _sync_ticket_for_card(db_path, updated, override_status="completed")
    _record_event(db_path, "resource-action-completed", card, state="completed", payload_path=str(target))
    return {"card_id": card["card_id"], "action": "executed", "status": "completed", "external_ref": external_ref, "path": str(target)}


def _ensure_approval_request(factory: Path, db_path: Path, card: dict[str, Any], path: Path) -> str:
    request_id = str(card.get("approval_request_id") or _approval_request_id(card))
    resource = get_resource(factory, str(card["resource_id"])) or {}
    prompt = _approval_prompt(card, resource)
    with db.session(db_path) as conn:
        db.upsert_approval_request(
            conn,
            request_id=request_id,
            assignment_id=str(card["ticket_id"]),
            team_name=str(card.get("team") or resource.get("owner") or "boss"),
            task_id=None,
            kind="approval-required",
            title=f"Approve resource action: {card.get('title') or card['action']}",
            prompt=prompt,
            required_fields=["decision"],
            metadata={
                "mode": "resource-action",
                "card_id": card["card_id"],
                "card_path": str(path),
                "resource_id": card["resource_id"],
                "action": card["action"],
                "artifact": card.get("artifact"),
                "resources": [card["resource_id"]],
                "reservation_id": card.get("reservation_id"),
            },
        )
    updated = {**card, "approval_request_id": request_id, "status": "approval-required"}
    path.write_text(json.dumps(_strip_runtime(updated), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _sync_ticket_for_card(db_path, updated, override_status="blocked", approval_request_id=request_id)
    _record_event(db_path, "resource-action-approval-requested", updated, state="approval-required", payload_path=str(path))
    return request_id


def _approval_prompt(card: dict[str, Any], resource: dict[str, Any]) -> str:
    decision = card.get("gate_decision") if isinstance(card.get("gate_decision"), dict) else {}
    metadata = card.get("metadata") if isinstance(card.get("metadata"), dict) else {}
    parts = [
        f"Approve hub-side resource action `{card['action']}` for `{card['resource_id']}`.",
        f"Ticket: `{card['ticket_id']}`.",
        f"Artifact: `{card.get('artifact') or 'none'}`.",
        f"Why: {card.get('why') or metadata.get('why') or 'not specified'}",
    ]
    if resource.get("approval_policy"):
        parts.append(f"Resource approval policy: {resource['approval_policy']}")
    for key in ("blast_radius", "rollback", "fallback", "preconditions", "expected_impact"):
        if metadata.get(key):
            parts.append(f"{key.replace('_', ' ').title()}: {metadata[key]}")
    if decision.get("expires_at"):
        parts.append(f"Reservation expires at: {decision['expires_at']}")
    parts.append("If approved, the hub resource-action executor will run the configured hub skill from the main machine and log usage. If denied, the reservation is released and no external action is taken.")
    return "\n\n".join(parts)


def _sync_ticket_for_card(
    db_path: Path,
    card: dict[str, Any],
    *,
    override_status: str | None = None,
    approval_request_id: str | None = None,
) -> None:
    ticket_id = str(card.get("ticket_id") or "")
    if not ticket_id:
        return
    status = override_status or _ticket_status_for_card(str(card.get("status") or ""))
    if status is None:
        return
    with db.session(db_path) as conn:
        row = db.get_execution_ticket(conn, ticket_id)
        if row is None:
            return
        db.set_execution_ticket_status(
            conn,
            ticket_id=ticket_id,
            status=status,
            approval_request_id=approval_request_id or card.get("approval_request_id"),
            terminal=status in {"completed", "failed", "canceled"},
        )


def _ticket_status_for_card(status: str) -> str | None:
    return {
        "approval-required": "blocked",
        "blocked": "blocked",
        "ready": "ready",
        "completed": "completed",
        "failed": "failed",
        "released": "canceled",
        "needs-human": "blocked",
    }.get(status)


def _fail_card(
    factory: Path,
    db_path: Path,
    path: Path,
    card: dict[str, Any],
    reason: str,
    *,
    log_path: Path | None = None,
) -> dict[str, Any]:
    _release_card_reservation(factory, card, reason=reason)
    updated = {**card, "status": "failed", "failed_at": _iso_now(), "failure_reason": reason}
    if log_path:
        updated["execution"] = {"log_path": str(log_path)}
    target = _move_card(path, updated, "failed")
    _sync_ticket_for_card(db_path, updated, override_status="failed")
    _record_event(db_path, "resource-action-failed", updated, state="failed", payload_path=str(target), metadata={"reason": reason})
    return {"card_id": card["card_id"], "action": "failed", "status": "failed", "reason": reason, "path": str(target)}


def _needs_human(factory: Path, db_path: Path, path: Path, card: dict[str, Any], reason: str) -> dict[str, Any]:
    updated = {**card, "status": "needs-human", "needs_human_at": _iso_now(), "needs_human_reason": reason}
    target = _move_card(path, updated, "needs-human")
    _sync_ticket_for_card(db_path, updated, override_status="blocked")
    _record_event(db_path, "resource-action-needs-human", updated, state="needs-human", payload_path=str(target), metadata={"reason": reason})
    with db.session(db_path) as conn:
        db.upsert_operator_alert(
            conn,
            alert_id=f"alert-resource-action-{card['card_id']}",
            dedupe_key=f"resource-action-needs-human:{card['card_id']}",
            severity="warning",
            kind="resource-action-needs-human",
            team_name=str(card.get("team") or "resource-manager"),
            assignment_id=str(card.get("ticket_id") or ""),
            status="open",
            title=f"Resource action needs human: {card.get('title') or card['card_id']}",
            body=f"Card {card['card_id']} cannot execute automatically: {reason}.",
            metadata={"card_id": card["card_id"], "card_path": str(target), "reason": reason},
        )
    return {"card_id": card["card_id"], "action": "needs-human", "status": "needs-human", "reason": reason, "path": str(target)}


def _execution_config(resource: dict[str, Any], action: str) -> dict[str, Any] | None:
    execution = resource.get("execution")
    if not isinstance(execution, dict):
        return None
    actions = execution.get("actions")
    if isinstance(actions, dict) and isinstance(actions.get(action), dict):
        return actions[action]
    if isinstance(execution.get(action), dict):
        return execution[action]
    if execution.get("skill") or execution.get("hub_skill") or execution.get("command"):
        return execution
    return None


def _hub_location_allowed(execution: dict[str, Any]) -> bool:
    location = str(execution.get("location") or execution.get("network") or "hub-main-machine")
    remote_allowed = bool(execution.get("remote_e2b_allowed"))
    return not remote_allowed and location in {"hub-main-machine", "main_machine", "main-machine", "hub", "local"}


def _resolve_command(factory: Path, execution: dict[str, Any]) -> list[str] | None:
    if execution.get("command"):
        return _command_list(execution["command"])
    skill = str(execution.get("hub_skill") or execution.get("skill") or "")
    if not skill:
        return None
    root = factory / "skills" / skill
    manifest = root / "skill.json"
    if manifest.exists():
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("command"):
            return _command_list(data["command"])
    script = root / "execute.sh"
    if script.exists():
        return [str(script)]
    executable = shutil.which(skill)
    if executable:
        return [executable]
    return None


def _command_list(value: Any) -> list[str]:
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    if isinstance(value, str):
        return [value]
    raise SystemExit("resource action command must be a string or string list")


def _command_kind(execution: dict[str, Any]) -> str:
    if execution.get("command"):
        return "resource-command"
    if execution.get("hub_skill") or execution.get("skill"):
        return "hub-skill"
    return "unknown"


def _release_card_reservation(factory: Path, card: dict[str, Any], *, reason: str) -> None:
    reservation_id = card.get("reservation_id")
    if not reservation_id:
        return
    resource_gate.release_usage(
        factory=factory,
        resource_id=str(card["resource_id"]),
        action=str(card["action"]),
        ticket_id=str(card["ticket_id"]),
        reservation_id=str(reservation_id),
        reason=reason,
    )


def _move_card(path: Path, card: dict[str, Any], state: str) -> Path:
    target = path.parents[1] / state / path.name
    target.parent.mkdir(parents=True, exist_ok=True)
    card = {**_strip_runtime(card), "status": state}
    target.write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if path.resolve() != target.resolve():
        path.unlink(missing_ok=True)
    return target


def _read_card(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"resource action card must be an object: {path}")
    return data


def _resolve_card_path(factory: Path, card_ref: str) -> Path:
    path = Path(card_ref)
    if path.exists():
        return path
    for state in resource_gate.CARD_STATES:
        candidate = factory / "resource_action_cards" / state / f"{card_ref}.json"
        if candidate.exists():
            return candidate
    raise SystemExit(f"unknown resource action card: {card_ref}")


def _strip_runtime(card: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in card.items() if not key.startswith("_")}


def _approval_request_id(card: dict[str, Any]) -> str:
    return f"resource-action-{card['card_id']}-approval"


def _approved(response: Any) -> bool:
    if response is True:
        return True
    if isinstance(response, dict):
        decision = str(response.get("decision") or response.get("action") or "").lower()
        return bool(response.get("approved")) or decision in {"approved", "approve", "yes"}
    return False


def _decode_json(raw: str | None, *, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _external_ref(log_path: Path) -> str | None:
    for line in reversed(log_path.read_text(encoding="utf-8", errors="replace").splitlines()):
        if line.startswith("external_ref="):
            return line.split("=", 1)[1].strip() or None
    return None


def _record_event(
    db_path: Path,
    kind: str,
    card: dict[str, Any],
    *,
    state: str,
    payload_path: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    with db.session(db_path) as conn:
        db.record_event(
            conn,
            team_name="resource-manager",
            assignment_id=str(card.get("ticket_id") or ""),
            task_id=None,
            source="harness.resource_actions",
            kind=kind,
            state=state,
            payload_path=payload_path,
            metadata={"card_id": card.get("card_id"), **(metadata or {})},
        )


def _iso_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main() -> None:
    args = build_parser().parse_args()
    result = run(args)
    if getattr(args, "json", False):
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
