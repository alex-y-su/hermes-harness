#!/usr/bin/env python3
"""
Reviewer runtime — the truth-checker for the verifiable-outcome card model.

The reviewer is the only piece of code that decides a card's done vs killed.
It reads a card JSON from stdin (or a file), walks `outcome.verification_steps`,
fetches reality (HTTP for URLs, filesystem for paths, log-grep for delivery
logs), attaches evidence to each step, writes an audit log under
`/factory/reviews/`, and prints a single JSON line on stdout describing the
overall outcome.

Stdout contract:
    {"success": true|false, "verification_steps": [...], "audit_path": "...",
     "card_id": "...", "reviewed_at_utc": "..."}

The reviewer NEVER writes to the board itself. The operator reads the
stdout, then performs the board update — keeping the reviewer side-effect-free
on card state (only reads card from stdin, writes audit log, returns JSON).

Dispatch is locator-type-driven by default:
  - locator value starts with "http://" or "https://" → HTTP fetch
  - locator value starts with "/" or "./"             → file check
  - otherwise → REVIEWER_NO_DISPATCH (failed step with a clear message)

Each verification_step.describe is parsed for `contains '<x>'` or `contains "<x>"`
to extract an expected substring. The check then verifies that string against
the fetched reality. This is a deterministic baseline; an LLM-driven dispatch
fallback can be layered on top when needed.

Usable two ways:
    1. Module:
         from harness.cards.reviewer_runtime import run_review
         result = run_review(card_dict)
    2. CLI (stdin):
         echo '<card json>' | python3 /factory/lib/reviewer_runtime.py
"""

from __future__ import annotations
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ============================================================
# Reality checks
# ============================================================


def check_http_url(url: str, expect_in_body: str | None = None) -> tuple[bool, str]:
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "hermes-reviewer/1.0", "Cache-Control": "no-cache"},
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            status = r.status
            body = r.read(120000).decode("utf-8", errors="replace")
        ok = status == 200 and (
            expect_in_body is None or expect_in_body.lower() in body.lower()
        )
        evidence = f"HTTP {status} from {url}; body sample: {body[:200]!r}"
        if expect_in_body is not None:
            evidence += (
                f"; expect_in_body={expect_in_body!r} found="
                f"{(expect_in_body.lower() in body.lower())}"
            )
        return ok, evidence
    except Exception as e:
        return False, f"FETCH_ERROR for {url}: {type(e).__name__}: {e}"


def check_file_exists(path: str, expect_in_content: str | None = None) -> tuple[bool, str]:
    p = Path(path)
    if not p.exists():
        return False, f"file does not exist: {path}"
    try:
        content = p.read_text(errors="replace")
    except Exception as e:
        return False, f"file_read_error {path}: {e!r}"
    ok = expect_in_content is None or expect_in_content in content
    evidence = f"file at {path} exists ({len(content)} bytes); body[:200]={content[:200]!r}"
    if expect_in_content is not None:
        evidence += f"; expect_in_content={expect_in_content!r} found={ok}"
    return ok, evidence


# ============================================================
# Locator + step → check dispatch
# ============================================================


def _resolve_locator(card: dict, field_path: str) -> Any:
    obj: Any = card
    for p in field_path.split("."):
        if isinstance(obj, dict):
            obj = obj.get(p)
        else:
            return None
    return obj


_EXPECT_RE = re.compile(
    r"contains?\s+'([^']+)'|contains?\s+\"([^\"]+)\"", re.IGNORECASE
)


def _extract_expected(describe: str) -> str | None:
    m = _EXPECT_RE.search(describe)
    if not m:
        return None
    return m.group(1) or m.group(2)


def _check_one_step(locator_value: Any, step: dict) -> tuple[bool, str]:
    describe = step.get("describe", "")
    expect = _extract_expected(describe)

    if isinstance(locator_value, str) and locator_value.startswith(("http://", "https://")):
        return check_http_url(locator_value, expect_in_body=expect)
    if isinstance(locator_value, str) and (
        locator_value.startswith("/") or locator_value.startswith("./")
    ):
        return check_file_exists(locator_value, expect_in_content=expect)
    return False, (
        f"REVIEWER_NO_DISPATCH: locator value {locator_value!r} is neither URL nor "
        f"path; step.describe={describe[:80]!r}"
    )


# ============================================================
# Public API
# ============================================================


def run_review(card: dict) -> dict:
    """Walk verification_steps; attach evidence + pass; return per-step + overall.

    The card dict is read-only; this function returns a new dict and does NOT
    mutate `card` in place. Callers may copy the returned `verification_steps`
    back into the card if they want the steps annotated for audit.
    """
    o = card.get("outcome") or {}
    steps_in = list(o.get("verification_steps") or [])
    locator_field = o.get("locator_field") or "result.unknown"
    locator_value = _resolve_locator(card, locator_field)

    annotated: list[dict] = []
    all_passed = True
    for step in steps_in:
        s = dict(step)
        ok, evidence = _check_one_step(locator_value, s)
        s["passed"] = ok
        s["evidence"] = evidence
        s["checked_at_utc"] = datetime.now(timezone.utc).isoformat()
        annotated.append(s)
        if not ok:
            all_passed = False

    return {
        "all_passed": all_passed,
        "verification_steps": annotated,
        "locator_field": locator_field,
        "locator_value": locator_value,
    }


def review_and_audit(card: dict, audit_root: str | Path = "/factory/reviews") -> dict:
    """Run review + persist an audit log.

    Returns a stdout-shaped dict. Does NOT modify the card.
    """
    review = run_review(card)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    audit_root = Path(audit_root)
    audit_root.mkdir(parents=True, exist_ok=True)
    audit_path = audit_root / f"{card.get('id','unknown')}-{ts}.json"
    audit = {
        "card_id": card.get("id"),
        "card_title": card.get("title"),
        "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
        "review": review,
    }
    audit_path.write_text(json.dumps(audit, indent=2) + "\n")

    return {
        "success": review["all_passed"],
        "verification_steps": review["verification_steps"],
        "locator_field": review["locator_field"],
        "locator_value": review["locator_value"],
        "audit_path": str(audit_path),
        "card_id": card.get("id"),
        "reviewed_at_utc": audit["reviewed_at_utc"],
    }


# ============================================================
# CLI: read card from stdin, print JSON to stdout
# ============================================================


def _cli_main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        sys.stderr.write("reviewer_runtime: empty stdin\n")
        return 2
    try:
        card = json.loads(raw)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"reviewer_runtime: stdin not valid JSON: {e}\n")
        return 2
    audit_root = os.environ.get("HERMES_REVIEWS_DIR", "/factory/reviews")
    result = review_and_audit(card, audit_root=audit_root)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(_cli_main())
