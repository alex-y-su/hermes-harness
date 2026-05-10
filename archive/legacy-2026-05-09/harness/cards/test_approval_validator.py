#!/usr/bin/env python3
"""Tests for the approval-card validator.

Run from repo root:
    python3 -m unittest harness.cards.test_approval_validator -v
"""

from __future__ import annotations
import unittest

from harness.cards.approval_validator import (
    ApprovalValidationError,
    validate_approval_shape,
)


def _valid_tweet_approval() -> dict:
    return {
        "approval_id": "appr-20260508T220045Z-7bcb",
        "schema_version": "1",
        "kind": "tweet",
        "status": "pending",
        "source_card_id": "card-prayer-circle-tweet",
        "proposed_at_utc": "2026-05-08T22:00:45Z",
        "decided_at_utc": None,
        "decided_by": None,
        "decision_note": None,
        "payload": {
            "text": "Pray with us tonight at 8pm — peaceful, free, open to all. roomcord.com/jesuscord",
            "intended_url_substrings": ["roomcord.com", "Jesuscord"],
        },
        "resulting_artifact": None,
        "audit_trail": [
            {
                "event": "proposed",
                "at_utc": "2026-05-08T22:00:45Z",
                "by": "operator-pulse",
                "note": "card-XYZ proposed via propose-tweet",
            }
        ],
    }


class TestApprovalValidatorHappyPath(unittest.TestCase):
    def test_valid_tweet_approval_pending(self):
        """Baseline pending tweet approval — must validate clean."""
        validate_approval_shape(_valid_tweet_approval())

    def test_valid_posted_with_artifact(self):
        """Posted state with a populated resulting_artifact dict is valid."""
        c = _valid_tweet_approval()
        c["status"] = "posted"
        c["decided_at_utc"] = "2026-05-08T22:05:11Z"
        c["decided_by"] = "user"
        c["resulting_artifact"] = {
            "tweet_id": "1789000000000000001",
            "live_url": "https://twitter.com/i/status/1789000000000000001",
            "posted_at_utc": "2026-05-08T22:05:13Z",
        }
        validate_approval_shape(c)

    def test_valid_non_tweet_kind(self):
        """Free-text kind (e.g., email) bypasses the tweet-only payload.text check."""
        c = _valid_tweet_approval()
        c["kind"] = "email"
        c["payload"] = {"to": "list@roomcord.com", "subject": "hi", "body": "..."}
        validate_approval_shape(c)


class TestApprovalValidatorRequiredFields(unittest.TestCase):
    def _expect_error(self, card: dict, substr: str) -> None:
        with self.assertRaises(ApprovalValidationError) as cm:
            validate_approval_shape(card)
        self.assertIn(substr, str(cm.exception).lower())

    def test_approval_id_bad_format(self):
        c = _valid_tweet_approval()
        c["approval_id"] = "appr-bad"
        self._expect_error(c, "approval_id")

    def test_approval_id_missing(self):
        c = _valid_tweet_approval()
        del c["approval_id"]
        self._expect_error(c, "approval_id")

    def test_schema_version_wrong(self):
        c = _valid_tweet_approval()
        c["schema_version"] = "2"
        self._expect_error(c, "schema_version")

    def test_kind_empty_string_rejected(self):
        c = _valid_tweet_approval()
        c["kind"] = ""
        self._expect_error(c, "kind")

    def test_kind_missing_rejected(self):
        c = _valid_tweet_approval()
        del c["kind"]
        self._expect_error(c, "kind")

    def test_status_not_in_enum(self):
        c = _valid_tweet_approval()
        c["status"] = "wat"
        self._expect_error(c, "status")

    def test_source_card_id_empty(self):
        c = _valid_tweet_approval()
        c["source_card_id"] = ""
        self._expect_error(c, "source_card_id")

    def test_proposed_at_utc_bad_format(self):
        c = _valid_tweet_approval()
        c["proposed_at_utc"] = "yesterday"
        self._expect_error(c, "proposed_at_utc")

    def test_payload_not_dict(self):
        c = _valid_tweet_approval()
        c["payload"] = "just a string"
        self._expect_error(c, "payload")

    def test_payload_empty_dict(self):
        c = _valid_tweet_approval()
        c["payload"] = {}
        self._expect_error(c, "payload")

    def test_tweet_payload_text_too_long(self):
        c = _valid_tweet_approval()
        c["payload"] = {"text": "x" * 281}
        self._expect_error(c, "payload.text")

    def test_tweet_payload_text_empty(self):
        c = _valid_tweet_approval()
        c["payload"] = {"text": ""}
        self._expect_error(c, "payload.text")

    def test_tweet_payload_text_missing(self):
        c = _valid_tweet_approval()
        c["payload"] = {"intended_url_substrings": ["roomcord.com"]}
        self._expect_error(c, "payload.text")

    def test_audit_trail_empty(self):
        c = _valid_tweet_approval()
        c["audit_trail"] = []
        self._expect_error(c, "audit_trail")

    def test_audit_trail_missing(self):
        c = _valid_tweet_approval()
        del c["audit_trail"]
        self._expect_error(c, "audit_trail")

    def test_audit_entry_missing_event(self):
        c = _valid_tweet_approval()
        c["audit_trail"][0].pop("event")
        self._expect_error(c, "event")

    def test_audit_entry_bad_at_utc(self):
        c = _valid_tweet_approval()
        c["audit_trail"][0]["at_utc"] = "soon"
        self._expect_error(c, "at_utc")

    def test_audit_entry_empty_by(self):
        c = _valid_tweet_approval()
        c["audit_trail"][0]["by"] = ""
        self._expect_error(c, "by")

    def test_decided_at_utc_bad_format_when_present(self):
        c = _valid_tweet_approval()
        c["decided_at_utc"] = "not-a-utc"
        self._expect_error(c, "decided_at_utc")

    def test_resulting_artifact_not_dict(self):
        c = _valid_tweet_approval()
        c["resulting_artifact"] = "should be dict or null"
        self._expect_error(c, "resulting_artifact")


if __name__ == "__main__":
    unittest.main()
