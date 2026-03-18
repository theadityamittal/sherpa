# src/slack/signature.py
"""Slack request signature verification (HMAC-SHA256)."""

from __future__ import annotations

import hashlib
import hmac
import time


class InvalidSignatureError(Exception):
    """Raised when Slack signature verification fails."""


_MAX_TIMESTAMP_AGE_SECONDS = 300


def verify_slack_signature(
    *,
    signing_secret: str,
    body: str,
    timestamp: str,
    signature: str,
) -> None:
    try:
        ts = int(timestamp)
    except (ValueError, TypeError) as e:
        raise InvalidSignatureError("Invalid timestamp") from e

    if abs(time.time() - ts) > _MAX_TIMESTAMP_AGE_SECONDS:
        raise InvalidSignatureError("Timestamp expired")

    sig_basestring = f"v0:{timestamp}:{body}"
    expected = (
        "v0="
        + hmac.new(
            signing_secret.encode(),
            sig_basestring.encode(),
            hashlib.sha256,
        ).hexdigest()
    )

    if not hmac.compare_digest(expected, signature):
        raise InvalidSignatureError("Signature mismatch")
