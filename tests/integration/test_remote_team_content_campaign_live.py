from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

import pytest

from hermes_harness.remote_team.transports import call_team
from tests.integration.test_remote_team_compressed_campaign_live import (
    _has_autonomy_contract,
    _hub_delete,
    _hub_json,
    _hub_post,
    _main_update,
    _posts,
    _write_json,
)


pytestmark = [pytest.mark.integration, pytest.mark.smoke]


DOMAIN_TERMS = {
    "hermes",
    "kanban",
    "remote",
    "team",
    "sub-team",
    "agent",
    "delegation",
    "kpi",
    "report",
    "maintenance",
    "loop",
    "hosted",
    "accountability",
    "a2a",
    "approval",
    "boss",
    "conductor",
    "critic",
    "durable",
    "e2b",
    "forcing",
    "goal",
    "hr",
    "profile",
    "queue",
    "soul",
    "supervisor",
    "watchdog",
}

FORBIDDEN_COPY_TERMS = {
    "$hermes_home",
    "campaign_should_complete",
    "cron/jobs.json",
    "external_id",
    "jsonl",
    "keep_running",
    "mock-x",
    "next_report_due_at",
    "source_task_id",
}


def test_live_vm203_compressed_x_content_matches_docs_domain(repo_root: Path, tmp_path: Path) -> None:
    if os.environ.get("HERMES_HUB_CONTENT_CAMPAIGN_TEST") != "1":
        pytest.skip("set HERMES_HUB_CONTENT_CAMPAIGN_TEST=1 to run the live content campaign")
    base_url = (os.environ.get("HERMES_HUB_URL") or "").rstrip("/")
    token = os.environ.get("HERMES_HUB_API_TOKEN")
    if not base_url or not token:
        pytest.skip("HERMES_HUB_URL and HERMES_HUB_API_TOKEN are required")

    docs_root = _docs_root(repo_root)
    domain_context = _docs_domain_context(repo_root, docs_root)
    run_id = time.strftime("%Y%m%d%H%M%S", time.gmtime())
    tenant_id = os.environ.get("HERMES_HUB_CONTENT_TENANT", "xteam_content_campaign")
    board = "x-content-campaign"
    evidence_dir = Path(os.environ.get("HERMES_HUB_CONTENT_EVIDENCE_DIR", str(tmp_path / "evidence")))
    evidence_dir.mkdir(parents=True, exist_ok=True)

    _hub_delete(base_url, token, f"/v1/tenants/{tenant_id}")
    registry = _write_registry(
        evidence_dir=evidence_dir,
        base_url=base_url,
        tenant_id=tenant_id,
        board=board,
        domain_context=domain_context,
    )
    request = _content_campaign_request(run_id=run_id, docs_label=str(docs_root.relative_to(repo_root)))
    _write_json(evidence_dir / "request.json", request)
    health = call_team(registry_path=registry, team="x", operation="health", request=request, timeout=60)
    _write_json(evidence_dir / "health-response.json", health)
    reset = _reset_tenant_content_state(base_url, token, tenant_id, evidence_dir)

    timeline: list[dict[str, Any]] = []
    try:
        submit = call_team(registry_path=registry, team="x", operation="submit_or_get", request=request, timeout=480)
        _write_json(evidence_dir / "submit-response.json", submit)
        timeline.append(_timeline_entry("submit", submit))

        final: dict[str, Any] | None = None
        active_reports = 0
        for index in range(1, 3):
            status_request = _status_request(
                request,
                board=board,
                remote_task_id=submit.get("remote_task_id"),
                poll_index=index,
                should_complete=index >= 2,
            )
            _write_json(evidence_dir / f"status-request-{index}.json", status_request)
            status = call_team(
                registry_path=registry,
                team="x",
                operation="status",
                request=status_request,
                timeout=480,
            )
            _write_json(evidence_dir / f"status-response-{index}.json", status)
            timeline.append(_timeline_entry(f"status-{index}", status))
            action = _main_update(status).get("action")
            if action == "complete":
                final = status
                break
            if action == "keep_running":
                active_reports += 1

        inspection = _inspect_tenant(base_url, token, tenant_id, evidence_dir)
        final_post_texts = _post_texts(final or {})
        inspected_post_texts = inspection.get("post_texts")
        post_texts = inspected_post_texts if isinstance(inspected_post_texts, list) else final_post_texts
        relevance = _relevance_report(post_texts)
        quality = _quality_report(post_texts)
        summary = {
            "tenant_id": tenant_id,
            "domain_doc_files": _doc_files(repo_root, docs_root),
            "timeline": timeline,
            "active_reports_before_completion": active_reports,
            "final_action": _main_update(final or {}).get("action"),
            "final_report_post_texts": final_post_texts,
            "post_texts": post_texts,
            "relevance": relevance,
            "quality": quality,
            "submit_has_autonomy_contract": _has_autonomy_contract(submit),
            "final_has_autonomy_contract": _has_autonomy_contract(final or {}),
            "remote_posts_count_on_disk": inspection.get("posts_count"),
            "remote_post_ids_on_disk": inspection.get("post_ids"),
            "remote_post_texts_on_disk": inspection.get("post_texts"),
            "inspection": inspection,
        }
        _write_json(evidence_dir / "summary.json", summary)
    finally:
        _hub_post(base_url, token, f"/v1/tenants/{tenant_id}/agent/stop")

    assert reset.get("status") == "completed", reset
    assert submit["ok"] is True, submit
    assert final is not None, timeline
    assert all(item["ok"] is True for item in timeline), timeline
    assert _main_update(final).get("action") == "complete", final
    assert _has_autonomy_contract(submit), submit
    assert _has_autonomy_contract(final), final
    assert active_reports >= 1, timeline
    assert len(post_texts) >= 3, post_texts
    assert inspection.get("posts_count", 0) >= len(_post_texts(final or {})), inspection
    assert relevance["related_posts"] >= len(post_texts) - 1, relevance
    assert relevance["average_term_hits"] >= 2.0, relevance
    assert quality["passing_posts"] == len(post_texts), quality


def _write_registry(
    *,
    evidence_dir: Path,
    base_url: str,
    tenant_id: str,
    board: str,
    domain_context: str,
) -> Path:
    registry = evidence_dir / "remote_teams.json"
    registry.write_text(
        json.dumps(
            {
                "remote_teams": {
                    "x": {
                        "transport": "hermes-hub",
                        "base_url": base_url,
                        "api_token_env": "HERMES_HUB_API_TOKEN",
                        "tenant_id": tenant_id,
                        "display_name": "Content domain X campaign verification",
                        "ensure_tenant": True,
                        "idle_timeout_seconds": 300,
                        "board": board,
                        "state_path": str(evidence_dir / "hub-state.json"),
                        "poll_interval_seconds": 2,
                        "product_context": domain_context,
                        "team_prompt": _content_team_prompt(),
                    }
                }
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return registry


def _content_campaign_request(*, run_id: str, docs_label: str) -> dict[str, Any]:
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    source_task_id = f"card-{run_id}"
    return {
        "protocol_version": "1",
        "source_team": "main",
        "target_team": "x",
        "external_id": f"main:x-content-campaign:{source_task_id}",
        "source_board": "main",
        "source_task_id": source_task_id,
        "task": {
            "title": "[x][growth] Docs-grounded compressed content campaign",
            "tenant": "growth",
            "priority": 9,
            "body": f"""Card type
Campaign cycle

Stream
Growth

Strategic outcome
Use the domain area in {docs_label} to create a short X campaign that makes Hermes Harness feel useful and understandable to AI builders and founder-operators.

Main-team strategy
Position Hermes Harness as the operating layer that turns agent work from one-off chat into accountable, durable execution. The main team is not prescribing exact post topics or wording; the X sub-team owns channel strategy, angles, copy, and editorial judgment.

Campaign start at
{now}

Time compression
1 campaign day = 1 minute.

Cycle window
3 compressed days / 3 minutes.

Poll interval
15 seconds

Heartbeat schedule
Every 15 seconds while the card remains running.

Content grounding rule
Use the supplied docs as source material, but translate internal architecture into audience-facing ideas. Posts should be understandable without reading the docs. Avoid protocol field names, file paths, schema names, and raw implementation jargon. Technical terms are allowed only when they create a sharper point.

Editorial bar
Each post needs a clear hook, one concrete idea, plain-language payoff, and a reason an AI builder or founder-operator would care. Do not publish keyword-stuffed architecture summaries.

Audience
AI builders, founder-operators, and agent operations teams.

Expected deliverables
1. Content strategy derived from the supplied docs
2. X posts that translate the docs into strong audience-facing copy
3. KPI checks plus content-quality self-review
4. Final report with post text, angle rationale, and quality/relevance explanation

Requested KPIs
Qualified replies; Profile clicks; Content-topic fit; Hook clarity; Low-jargon readability

Approval required
Auto-approved for this mock X gateway test only.

Stop rule
On a status poll where poll.campaign_should_complete=true, stop posting and return main_card_update.action='complete' and main_card_update.status='done'.

Reporting format
Return only JSON using the requested remote-team protocol response schema.
""",
        },
    }


def _status_request(
    request: dict[str, Any],
    *,
    board: str,
    remote_task_id: object,
    poll_index: int,
    should_complete: bool,
) -> dict[str, Any]:
    return {
        "protocol_version": "1",
        "source_team": "main",
        "target_team": "x",
        "external_id": request["external_id"],
        "source_board": request["source_board"],
        "source_task_id": request["source_task_id"],
        "remote_task_id": remote_task_id,
        "board": board,
        "force_report": True,
        "poll": {
            "force_report": True,
            "owner": "main-dashboard",
            "current_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "compressed_day_index": poll_index,
            "campaign_should_complete": should_complete,
            "interval_seconds": 15,
            "reason": "docs-grounded content campaign heartbeat",
            "main_card_status": "running",
        },
        "task": request["task"],
    }


def _content_team_prompt() -> str:
    return (
        "You are the Social Media X content sub-team. Treat $HERMES_HOME/mock-x/posts.jsonl as the real X API "
        "for this environment. You own X strategy and copy quality. Use the provided docs domain context as source "
        "material, but translate it into plain-language, audience-facing posts for AI builders and founder-operators. "
        "Do not treat docs terms as a keyword checklist. Avoid protocol field names, file paths, JSON/schema names, "
        "and internal identifiers in public copy. Prefer hooks about pain, contrast, consequence, or a concrete "
        "operating insight. Technical terms such as A2A, E2B, boss team, durable delegation, or KPI are allowed only "
        "when the post explains why the reader should care. Before recording any post, perform an editorial pass and "
        "reject candidates that are generic, jargon-stuffed, purely descriptive, or understandable only to repo insiders. "
        "On submit_or_get, create a content strategy with 2-3 audience-facing angles and at least two approved X posts. "
        "On each active status poll, add at least one new approved post, verify content-topic fit, hook clarity, and "
        "low-jargon readability. On final poll, return all post text, cumulative ledger, strategy decisions, execution "
        "plan, self-review, quality rationale, and complete/done."
    )


def _docs_root(repo_root: Path) -> Path:
    raw = os.environ.get("HERMES_HUB_CONTENT_DOCS_DIR", "docs")
    path = Path(raw)
    return path if path.is_absolute() else repo_root / path


def _docs_domain_context(repo_root: Path, docs_root: Path) -> str:
    files = [repo_root / path for path in _doc_files(repo_root, docs_root)]
    if not files:
        raise AssertionError(f"{docs_root} must contain at least one Markdown domain file")
    parts = []
    for path in files:
        parts.append(f"# Source: {path.relative_to(repo_root)}\n" + path.read_text(encoding="utf-8"))
    return "\n\n".join(parts)[:12000]


def _doc_files(repo_root: Path, docs_root: Path) -> list[str]:
    return [str(path.relative_to(repo_root)) for path in sorted(docs_root.glob("**/*.md")) if path.is_file()]


def _inspect_tenant(base_url: str, token: str, tenant_id: str, evidence_dir: Path) -> dict[str, Any]:
    prompt = (
        "Read-only inspection. Do not create, edit, append, delete, schedule, or post anything. "
        "Inspect $HERMES_HOME/mock-x/posts.jsonl. Return only JSON with keys posts_count, post_ids, "
        "post_texts, posts_path, explanation."
    )
    run = _hub_json(
        base_url,
        token,
        "POST",
        f"/v1/tenants/{tenant_id}/runs",
        {"input": prompt, "session_id": "content-campaign-readonly-inspect", "model": "hermes-agent"},
    )
    _write_json(evidence_dir / "readonly-inspect-start.json", run)
    run_id = run.get("run_id") or run.get("id")
    status = run
    for _ in range(90):
        if status.get("status") in {"completed", "failed", "cancelled", "canceled"}:
            break
        time.sleep(2)
        status = _hub_json(base_url, token, "GET", f"/v1/tenants/{tenant_id}/runs/{run_id}", None)
    _write_json(evidence_dir / "readonly-inspect-status.json", status)
    try:
        parsed = json.loads(status.get("output") or "{}")
    except json.JSONDecodeError:
        parsed = {"raw_output": status.get("output")}
    return parsed if isinstance(parsed, dict) else {"raw_output": parsed}


def _reset_tenant_content_state(base_url: str, token: str, tenant_id: str, evidence_dir: Path) -> dict[str, Any]:
    prompt = (
        "Test setup only. Do not post to X and do not create campaign content. "
        "Delete $HERMES_HOME/mock-x/posts.jsonl if it exists. Ensure $HERMES_HOME/mock-x exists. "
        "Reset $HERMES_HOME/cron/jobs.json to {\"jobs\": []}. Return only JSON with keys "
        "ok, reset_posts, reset_cron, posts_path, cron_path."
    )
    run = _hub_json(
        base_url,
        token,
        "POST",
        f"/v1/tenants/{tenant_id}/runs",
        {"input": prompt, "session_id": "content-campaign-reset", "model": "hermes-agent"},
    )
    _write_json(evidence_dir / "reset-start.json", run)
    run_id = run.get("run_id") or run.get("id")
    status = run
    for _ in range(90):
        if status.get("status") in {"completed", "failed", "cancelled", "canceled"}:
            break
        time.sleep(2)
        status = _hub_json(base_url, token, "GET", f"/v1/tenants/{tenant_id}/runs/{run_id}", None)
    _write_json(evidence_dir / "reset-status.json", status)
    return status


def _timeline_entry(label: str, response: dict[str, Any]) -> dict[str, Any]:
    return {
        "label": label,
        "ok": response.get("ok"),
        "status": response.get("status"),
        "remote_task_id": response.get("remote_task_id"),
        "hub_job_id": (response.get("hub") or {}).get("job_id"),
        "main_card_update": _main_update(response),
        "post_count": len(_posts(response)),
        "post_texts": _post_texts(response),
    }


def _post_texts(response: dict[str, Any]) -> list[str]:
    texts = []
    for post in _posts(response):
        if isinstance(post, dict) and post.get("text"):
            texts.append(str(post["text"]))
    return texts


def _relevance_report(post_texts: list[str]) -> dict[str, Any]:
    per_post = []
    for text in post_texts:
        lowered = text.lower()
        hits = sorted(term for term in DOMAIN_TERMS if _term_match(lowered, term))
        per_post.append({"text": text, "term_hits": hits, "related": len(hits) >= 2})
    related = sum(1 for item in per_post if item["related"])
    average = (sum(len(item["term_hits"]) for item in per_post) / len(per_post)) if per_post else 0.0
    return {
        "domain_terms": sorted(DOMAIN_TERMS),
        "posts_count": len(post_texts),
        "related_posts": related,
        "average_term_hits": average,
        "per_post": per_post,
    }


def _quality_report(post_texts: list[str]) -> dict[str, Any]:
    per_post = []
    for text in post_texts:
        lowered = text.lower()
        forbidden = sorted(term for term in FORBIDDEN_COPY_TERMS if term in lowered)
        too_long = len(text) > 280
        has_hook = _has_hook_shape(text)
        passing = not forbidden and not too_long and has_hook
        per_post.append(
            {
                "text": text,
                "forbidden_terms": forbidden,
                "has_hook_shape": has_hook,
                "length": len(text),
                "passing": passing,
                "too_long": too_long,
            }
        )
    return {
        "forbidden_terms": sorted(FORBIDDEN_COPY_TERMS),
        "passing_posts": sum(1 for item in per_post if item["passing"]),
        "posts_count": len(post_texts),
        "per_post": per_post,
    }


def _has_hook_shape(text: str) -> bool:
    first_sentence = re.split(r"(?<=[.!?])\s+", text.strip(), maxsplit=1)[0].lower()
    hook_terms = {
        "avoid",
        "beat",
        "copying",
        "durable",
        "hard",
        "if",
        "instead",
        "jump",
        "most",
        "not",
        "problem",
        "should",
        "stop",
        "turns",
        "without",
        "worth",
    }
    return "?" in first_sentence or any(re.search(rf"\b{re.escape(term)}\b", first_sentence) for term in hook_terms)


def _term_match(text: str, term: str) -> bool:
    if "-" in term:
        return term in text or term.replace("-", " ") in text
    return re.search(rf"\b{re.escape(term)}s?\b", text) is not None
