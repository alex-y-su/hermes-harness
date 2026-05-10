#!/usr/bin/env python3
"""Tests for the access-request validator.

Run from repo root:
    python3 -m unittest harness.cards.test_access_request_validator -v
"""

from __future__ import annotations
import unittest

from harness.cards.access_request_validator import (
    AccessRequestValidationError,
    validate_access_request_shape,
)


def _valid_access_request() -> dict:
    # NOTE: contract doc shows blocking_approval_id may be null; test covers both.
    return {
        "request_id": "accr-20260508T220123Z-3f2a",
        "schema_version": "1",
        "kind": "credentials",
        "status": "pending",
        "resource_id": "social/twitter",
        "requested_at_utc": "2026-05-08T22:01:23Z",
        "decided_at_utc": None,
        "what_we_need": (
            "Twitter API v2 OAuth 1.0a user-context credentials so post-twitter-real "
            "can post on behalf of @roomcord. Required keys: api_key, api_key_secret, "
            "access_token, access_token_secret. Install at /factory/secrets/social-twitter.json "
            "(chmod 600, owner dev)."
        ),
        "why": (
            "approval card appr-20260508T220045Z-7bcb was approved for posting but "
            "post-twitter-real returned creds_missing."
        ),
        "blocking_approval_id": "appr-20260508T220045Z-7bcb",
        "decision_note": None,
        "audit_trail": [
            {
                "event": "requested",
                "at_utc": "2026-05-08T22:01:23Z",
                "by": "approve-action",
                "note": "twitter creds missing, raised access-request",
            }
        ],
    }


class TestAccessRequestValidatorHappyPath(unittest.TestCase):
    def test_valid_pending_credentials_request(self):
        """Baseline pending credentials access-request — validates clean."""
        validate_access_request_shape(_valid_access_request())

    def test_valid_with_null_blocking_approval(self):
        """blocking_approval_id may be null when the request is not tied to an approval."""
        r = _valid_access_request()
        r["blocking_approval_id"] = None
        validate_access_request_shape(r)

    def test_valid_with_blocking_approval_field_absent(self):
        """blocking_approval_id is optional; absence is acceptable per contract doc."""
        r = _valid_access_request()
        del r["blocking_approval_id"]
        validate_access_request_shape(r)

    def test_valid_granted_status(self):
        """Granted is a valid terminal status."""
        r = _valid_access_request()
        r["status"] = "granted"
        r["decided_at_utc"] = "2026-05-08T22:30:00Z"
        validate_access_request_shape(r)

    def test_valid_free_text_kind_external_access(self):
        """kind is free-text per contract doc."""
        r = _valid_access_request()
        r["kind"] = "external_access"
        validate_access_request_shape(r)


class TestAccessRequestValidatorRequiredFields(unittest.TestCase):
    def _expect_error(self, req: dict, substr: str) -> None:
        with self.assertRaises(AccessRequestValidationError) as cm:
            validate_access_request_shape(req)
        self.assertIn(substr, str(cm.exception).lower())

    def test_request_id_bad_format(self):
        r = _valid_access_request()
        r["request_id"] = "accr-bad"
        self._expect_error(r, "request_id")

    def test_request_id_uses_appr_prefix_rejected(self):
        r = _valid_access_request()
        r["request_id"] = "appr-20260508T220123Z-3f2a"
        self._expect_error(r, "request_id")

    def test_schema_version_wrong(self):
        r = _valid_access_request()
        r["schema_version"] = 1  # int instead of string "1"
        self._expect_error(r, "schema_version")

    def test_kind_empty(self):
        r = _valid_access_request()
        r["kind"] = ""
        self._expect_error(r, "kind")

    def test_status_not_in_enum(self):
        r = _valid_access_request()
        r["status"] = "approved"  # valid for approval-card, NOT for access-request
        self._expect_error(r, "status")

    def test_resource_id_bad_format_no_slash(self):
        r = _valid_access_request()
        r["resource_id"] = "twitter"
        self._expect_error(r, "resource_id")

    def test_resource_id_bad_format_uppercase(self):
        r = _valid_access_request()
        r["resource_id"] = "Social/Twitter"
        self._expect_error(r, "resource_id")

    def test_requested_at_utc_bad_format(self):
        r = _valid_access_request()
        r["requested_at_utc"] = "2026/05/08"
        self._expect_error(r, "requested_at_utc")

    def test_what_we_need_too_short(self):
        r = _valid_access_request()
        r["what_we_need"] = "twitter creds plz"
        self._expect_error(r, "what_we_need")

    def test_what_we_need_missing(self):
        r = _valid_access_request()
        del r["what_we_need"]
        self._expect_error(r, "what_we_need")

    def test_why_too_short(self):
        r = _valid_access_request()
        r["why"] = "needed"
        self._expect_error(r, "why")

    def test_blocking_approval_id_bad_format(self):
        r = _valid_access_request()
        r["blocking_approval_id"] = "appr-bad"
        self._expect_error(r, "blocking_approval_id")

    def test_audit_trail_empty(self):
        r = _valid_access_request()
        r["audit_trail"] = []
        self._expect_error(r, "audit_trail")

    def test_audit_entry_missing_event(self):
        r = _valid_access_request()
        r["audit_trail"][0].pop("event")
        self._expect_error(r, "event")

    def test_audit_entry_bad_at_utc(self):
        r = _valid_access_request()
        r["audit_trail"][0]["at_utc"] = "later"
        self._expect_error(r, "at_utc")

    def test_audit_entry_empty_by(self):
        r = _valid_access_request()
        r["audit_trail"][0]["by"] = ""
        self._expect_error(r, "by")


if __name__ == "__main__":
    unittest.main()
