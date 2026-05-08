#!/usr/bin/env python3
"""
Tests for the card validator.

Run from repo root:    python3 -m harness.cards.test_validator
Run from /factory/lib: python3 /factory/lib/test_card_validator.py
Exits 0 on all pass, 1 on any fail.
"""

from __future__ import annotations
import sys
from pathlib import Path

# Support both the repo path (harness.cards.validator) and the prod path
# where the module is installed as card_validator alongside this file.
try:
    from harness.cards.validator import validate_card_shape, CardValidationError
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        from validator import validate_card_shape, CardValidationError  # type: ignore[no-redef]
    except ImportError:
        from card_validator import validate_card_shape, CardValidationError  # type: ignore[no-redef]


def _expect_valid(name: str, card: dict) -> bool:
    try:
        validate_card_shape(card)
        print(f"PASS  {name}: accepted as expected")
        return True
    except CardValidationError as e:
        print(f"FAIL  {name}: rejected unexpectedly\n{e}")
        return False


def _expect_invalid(name: str, card: dict, expect_error_substrs: list[str]) -> bool:
    try:
        validate_card_shape(card)
    except CardValidationError as e:
        msg = str(e)
        missing = [s for s in expect_error_substrs if s.lower() not in msg.lower()]
        if missing:
            print(f"FAIL  {name}: rejected, but expected error substrings missing: {missing}\nactual:\n{e}")
            return False
        print(f"PASS  {name}: rejected as expected")
        return True
    print(f"FAIL  {name}: accepted but should have been rejected")
    return False


def _valid_card_skeleton() -> dict:
    return {
        "id": "card-skel",
        "title": "A perfectly valid card for the test skeleton",
        "outcome": {
            "describe_artifact": "A local markdown file at /tmp/example.md whose body contains 'Roomcord' and is readable on disk",
            "locator_field": "result.example_path",
            "verification_steps": [
                {
                    "describe": "The file should exist at the locator path on disk",
                    "evidence_required": "byte size of the file plus the first 160 bytes of content",
                },
                {
                    "describe": "The file body contains 'Roomcord' substring",
                    "evidence_required": "the substring search result over the file body content",
                },
            ],
        },
        "pipeline": [
            {"role": "writer", "describe_contribution": "Create the example_path file at the input.target_path"},
            {"role": "reviewer", "describe_contribution": "Verify the file exists and contains 'Roomcord'"},
        ],
    }


def main() -> int:
    results: list[bool] = []

    # -------- positive --------
    results.append(_expect_valid("baseline_skeleton", _valid_card_skeleton()))

    c = _valid_card_skeleton()
    c["pipeline"] = [
        {"role": "scenarios", "describe_contribution": "Write a 60-second video script grounded in current youtube_url plans"},
        {"role": "video_production", "describe_contribution": "Produce the AI video file referenced by youtube_url"},
        {"role": "smm", "describe_contribution": "Generate title and description that will land at youtube_url"},
        {"role": "resource_manager", "describe_contribution": "Upload and publish, fill youtube_url"},
        {"role": "reviewer", "describe_contribution": "Fetch the youtube_url and check video is accessible and title matches"},
    ]
    c["outcome"]["locator_field"] = "result.youtube_url"
    c["outcome"]["describe_artifact"] = "A YouTube video at the result.youtube_url URL whose page returns 200 and contains the planned title in HTML"
    c["outcome"]["verification_steps"] = [
        {"describe": "URL fetch should return 200 and HTML contains the planned title substring",
         "evidence_required": "HTTP status code plus page body excerpt confirming the substring"},
    ]
    results.append(_expect_valid("multi_role_video_pipeline", c))

    # -------- negative --------
    results.append(_expect_invalid(
        "missing_id", {**_valid_card_skeleton(), "id": ""},
        ["id"]))

    results.append(_expect_invalid(
        "title_too_short", {**_valid_card_skeleton(), "title": "x"},
        ["title"]))

    c = _valid_card_skeleton()
    c["outcome"]["describe_artifact"] = "too short"
    results.append(_expect_invalid("describe_artifact_too_short", c, ["describe_artifact"]))

    c = _valid_card_skeleton()
    c["outcome"]["locator_field"] = "not_starting_with_result"
    results.append(_expect_invalid("locator_field_bad_pattern", c, ["locator_field"]))

    c = _valid_card_skeleton()
    c["outcome"]["verification_steps"] = []
    results.append(_expect_invalid("empty_verification_steps", c, ["verification_steps"]))

    c = _valid_card_skeleton()
    c["pipeline"][-1]["role"] = "writer"  # remove reviewer at end
    results.append(_expect_invalid("missing_reviewer_at_end", c, ["pipeline[-1].role"]))

    c = _valid_card_skeleton()
    # Nothing references "example_path" in pipeline early steps
    c["pipeline"][0]["describe_contribution"] = "Just write something but don't say what file"
    results.append(_expect_invalid("locator_not_referenced", c, ["locator referenced"]))

    c = _valid_card_skeleton()
    # Subjective verification step: nothing measurable
    c["outcome"]["verification_steps"] = [
        {"describe": "The artifact should feel inspiring and warm to readers",
         "evidence_required": "vibes from the reviewer, please trust"},
    ]
    results.append(_expect_invalid("subjective_step_rejected", c, ["objective marker"]))

    # -------- summary --------
    n_pass = sum(1 for r in results if r)
    n_total = len(results)
    print(f"\n{n_pass}/{n_total} tests passed")
    return 0 if n_pass == n_total else 1


if __name__ == "__main__":
    sys.exit(main())
