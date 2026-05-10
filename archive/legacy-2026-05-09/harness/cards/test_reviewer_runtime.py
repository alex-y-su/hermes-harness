#!/usr/bin/env python3
"""
Tests for reviewer_runtime.

Run from repo root:    python3 -m harness.cards.test_reviewer_runtime
Run from /factory/lib: python3 /factory/lib/test_reviewer_runtime.py

Exits 0 on all pass, 1 on any fail.

Tests use a workdir under /tmp/reviewer-test-* and a real public URL
(roomcord.com/jesuscord) for the URL check; if network is unavailable
the URL test will fail, which is the right behavior.
"""

from __future__ import annotations
import json
import sys
import tempfile
from pathlib import Path

try:
    from harness.cards.reviewer_runtime import run_review, review_and_audit  # type: ignore
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        from reviewer_runtime import run_review, review_and_audit  # type: ignore[no-redef]
    except ImportError:
        from reviewer_runtime import run_review, review_and_audit  # type: ignore[no-redef]


def _file_card(path: str, expect: str | None = None) -> dict:
    steps = [{
        "describe": "The file should exist on disk at the locator path",
        "evidence_required": "byte size of the file plus first 200 bytes of content",
    }]
    if expect:
        steps.append({
            "describe": f"The file body should contain '{expect}' as a substring",
            "evidence_required": "the substring search result over the file body content",
        })
    return {
        "id": "card-file",
        "title": "Local file artifact for testing",
        "outcome": {
            "describe_artifact": "A local markdown file with contents matching expectations",
            "locator_field": "result.path",
            "verification_steps": steps,
        },
        "result": {"path": path},
    }


def _url_card(url: str, expect: str | None = None) -> dict:
    steps = [{
        "describe": "The URL fetch should return HTTP 200 from a real GET",
        "evidence_required": "HTTP status code from a real GET",
    }]
    if expect:
        steps.append({
            "describe": f"The page body should contain '{expect}' substring",
            "evidence_required": "200-char excerpt of the response body",
        })
    return {
        "id": "card-url",
        "title": "URL artifact for testing",
        "outcome": {
            "describe_artifact": "A live public web URL",
            "locator_field": "result.url",
            "verification_steps": steps,
        },
        "result": {"url": url},
    }


def _expect_overall(name: str, card: dict, expected_pass: bool) -> bool:
    review = run_review(card)
    actual = review["all_passed"]
    if actual == expected_pass:
        print(f"PASS  {name}: all_passed={actual}")
        return True
    print(f"FAIL  {name}: expected all_passed={expected_pass}, got {actual}")
    for s in review["verification_steps"]:
        print(f"      step.passed={s['passed']}: {s['describe'][:80]}")
        print(f"        evidence: {s.get('evidence','')[:160]}")
    return False


def main() -> int:
    rs: list[bool] = []

    # --- positive: real file ---
    tmp = Path(tempfile.mkdtemp(prefix="reviewer-test-"))
    p = tmp / "intro.md"
    p.write_text("# Hello\nThis file mentions Roomcord.\n")
    rs.append(_expect_overall("file_exists_with_substring", _file_card(str(p), "Roomcord"), True))
    rs.append(_expect_overall("file_exists_no_expect", _file_card(str(p), None), True))

    # --- negative: missing file ---
    rs.append(_expect_overall("file_missing", _file_card(str(tmp / "absent.md"), None), False))

    # --- negative: file exists but expected substring absent ---
    rs.append(_expect_overall("file_substring_absent", _file_card(str(p), "Quantum-Computing-Buzzword-2026"), False))

    # --- positive: real public URL with substring known to be there ---
    rs.append(_expect_overall("url_with_known_substring",
                              _url_card("https://roomcord.com/jesuscord", "Jesuscord"), True))

    # --- negative: URL real but expected substring absent ---
    rs.append(_expect_overall("url_substring_absent",
                              _url_card("https://roomcord.com/jesuscord", "Quantum-Computing-Buzzword-2026"), False))

    # --- audit log path returned ---
    audit_card = _file_card(str(p), "Roomcord")
    audit_card["id"] = "card-audit-test"
    audit_dir = tmp / "reviews"
    out = review_and_audit(audit_card, audit_root=audit_dir)
    audit_files = list(audit_dir.glob("card-audit-test-*.json"))
    if out["success"] and len(audit_files) == 1:
        rs.append(True); print(f"PASS  audit_log_written: {audit_files[0]}")
    else:
        rs.append(False); print(f"FAIL  audit_log_written: success={out['success']} files={audit_files}")

    # --- locator that's neither URL nor path → no dispatch ---
    weird = _file_card("not-a-path-or-url", None)
    rs.append(_expect_overall("locator_no_dispatch", weird, False))

    n_pass = sum(1 for r in rs if r)
    n_total = len(rs)
    print(f"\n{n_pass}/{n_total} tests passed")
    return 0 if n_pass == n_total else 1


if __name__ == "__main__":
    sys.exit(main())
