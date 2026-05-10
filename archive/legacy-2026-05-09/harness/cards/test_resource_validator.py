#!/usr/bin/env python3
"""Tests for resource_validator. Exits 0 on all pass, 1 on any fail."""

from __future__ import annotations
import sys
from pathlib import Path

try:
    from harness.cards.resource_validator import validate_resource_shape, ResourceValidationError  # type: ignore
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        from resource_validator import validate_resource_shape, ResourceValidationError  # type: ignore[no-redef]
    except ImportError:
        from card_validator import validate_card_shape  # type: ignore  # only here so import error path is clear
        raise


def _expect_valid(name, res, expected_id_prefix=None):
    try:
        validate_resource_shape(res, expected_id_prefix=expected_id_prefix)
        print(f"PASS  {name}: accepted as expected")
        return True
    except ResourceValidationError as e:
        print(f"FAIL  {name}:\n{e}")
        return False


def _expect_invalid(name, res, must_contain, expected_id_prefix=None):
    try:
        validate_resource_shape(res, expected_id_prefix=expected_id_prefix)
        print(f"FAIL  {name}: accepted but should have been rejected")
        return False
    except ResourceValidationError as e:
        msg = str(e)
        missing = [s for s in must_contain if s.lower() not in msg.lower()]
        if missing:
            print(f"FAIL  {name}: rejected, but expected substrings missing: {missing}\n{e}")
            return False
        print(f"PASS  {name}: rejected as expected")
        return True


def _baseline_real():
    return {
        "id": "website/roomcord-com",
        "kind": "website",
        "title": "roomcord.com (real)",
        "state": "ready",
        "mock": False,
        "auto_approved": True,
        "description": "Real Roomcord landing site; commits + pushes via the publish-website-page skill.",
        "execution": {"publish_page": {"skill": "publish-website-page", "location": "hub-main-machine"}},
    }


def _baseline_mock():
    return {
        "id": "social/twitter",
        "kind": "social_channel",
        "title": "Twitter (mocked)",
        "state": "ready",
        "mock": True,
        "auto_approved": True,
        "description": "Mocked Twitter; appends to /factory/mocks/twitter-feed.json with synthetic engagement.",
        "execution": {"post_tweet": {"skill": "post-twitter", "location": "hub-main-machine"}},
    }


def main():
    rs = []

    rs.append(_expect_valid("baseline_real",   _baseline_real(),   expected_id_prefix="website"))
    rs.append(_expect_valid("baseline_mock_id_prefix_is_dir_not_kind",
                            _baseline_mock(),   expected_id_prefix="social"))

    # state must be in {ready, not_ready, archived}
    bad = _baseline_real(); bad["state"] = "denied"
    rs.append(_expect_invalid("bad_state_value", bad, ["state"]))

    # mock missing
    bad = _baseline_real(); del bad["mock"]
    rs.append(_expect_invalid("mock_absent_rejected", bad, ["mock"]))

    # id pattern
    bad = _baseline_real(); bad["id"] = "WEBSITE/ROOMCORD"
    rs.append(_expect_invalid("id_uppercase", bad, ["id"]))

    # execution must have skill or hub_skill on each action
    bad = _baseline_real(); bad["execution"] = {"publish_page": {"location": "x"}}
    rs.append(_expect_invalid("no_skill_in_execution", bad, ["skill"]))

    # id prefix must match the parent dir name (not kind)
    bad = _baseline_real(); bad["id"] = "social/twitter"  # id prefix "social" but file is in "website/" dir
    rs.append(_expect_invalid("id_prefix_mismatches_dir", bad, ["id prefix"], expected_id_prefix="website"))

    # kind being free-text (different from dir) is allowed
    free = _baseline_real(); free["kind"] = "free_text_descriptor_label"
    rs.append(_expect_valid("kind_free_text_allowed", free, expected_id_prefix="website"))

    # description too short
    bad = _baseline_real(); bad["description"] = "x"
    rs.append(_expect_invalid("description_too_short", bad, ["description"]))

    # archived state allowed
    arc = _baseline_real(); arc["state"] = "archived"
    rs.append(_expect_valid("archived_allowed", arc, expected_id_prefix="website"))

    # not_ready state allowed
    nr = _baseline_real(); nr["state"] = "not_ready"
    rs.append(_expect_valid("not_ready_allowed", nr, expected_id_prefix="website"))

    n_pass = sum(1 for r in rs if r)
    print(f"\n{n_pass}/{len(rs)} tests passed")
    return 0 if n_pass == len(rs) else 1


if __name__ == "__main__":
    sys.exit(main())
