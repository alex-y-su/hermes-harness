from __future__ import annotations

import base64
import hashlib
import hmac
import time


COOKIE_NAME = "harness_viewer_session"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _sign(secret: str, value: str) -> str:
    return hmac.new(secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


def issue_session(secret: str, *, now: int | None = None) -> str:
    timestamp = str(now if now is not None else int(time.time()))
    signature = _sign(secret, timestamp)
    return _b64(f"{timestamp}.{signature}".encode("utf-8"))


def verify_session(secret: str, cookie_value: str | None, *, max_age_seconds: int = 86400) -> bool:
    if not cookie_value:
        return False
    try:
        padded = cookie_value + "=" * (-len(cookie_value) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        timestamp, signature = decoded.split(".", 1)
        issued_at = int(timestamp)
    except (ValueError, UnicodeDecodeError):
        return False
    expected = _sign(secret, timestamp)
    if not hmac.compare_digest(signature, expected):
        return False
    return int(time.time()) - issued_at <= max_age_seconds


def code_matches(configured_code: str, submitted_code: str) -> bool:
    return hmac.compare_digest(configured_code.encode("utf-8"), submitted_code.encode("utf-8"))

