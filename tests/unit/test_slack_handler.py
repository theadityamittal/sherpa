# tests/unit/test_slack_handler.py
"""Tests for the Slack Handler Lambda entry point."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from slack.handler import lambda_handler


def _make_api_gw_event(
    path: str,
    body: dict,
    method: str = "POST",
    headers: dict | None = None,
) -> dict:
    return {
        "path": path,
        "httpMethod": method,
        "headers": headers or {},
        "body": json.dumps(body),
        "requestContext": {},
    }


class TestSlackHandlerLambda:
    @patch("slack.handler._get_signing_secret")
    @patch("slack.handler.verify_slack_signature")
    def test_url_verification_challenge(self, mock_verify, mock_secret):
        """Slack URL verification returns the challenge token."""
        mock_secret.return_value = "secret"
        event = _make_api_gw_event(
            path="/slack/events",
            body={"type": "url_verification", "challenge": "abc123"},
        )
        result = lambda_handler(event, {})
        assert result["statusCode"] == 200
        assert json.loads(result["body"])["challenge"] == "abc123"

    @patch("slack.handler._get_signing_secret")
    @patch("slack.handler.verify_slack_signature")
    @patch("slack.handler._enqueue_to_sqs")
    @patch("slack.handler._build_middleware_chain")
    def test_event_passes_middleware_and_enqueues(
        self, mock_chain_builder, mock_enqueue, mock_verify, mock_secret
    ):
        mock_secret.return_value = "secret"
        mock_chain = MagicMock()
        mock_chain.run.return_value = MagicMock(allowed=True)
        mock_chain_builder.return_value = mock_chain

        event = _make_api_gw_event(
            path="/slack/events",
            body={
                "type": "event_callback",
                "event": {
                    "type": "message",
                    "user": "U123",
                    "channel": "C789",
                    "text": "Hello",
                    "ts": "123.456",
                    "event_ts": "123.456",
                },
                "event_id": "Ev001",
                "team_id": "W456",
            },
        )
        result = lambda_handler(event, {})
        assert result["statusCode"] == 200
        mock_enqueue.assert_called_once()

    @patch("slack.handler._get_signing_secret")
    @patch("slack.handler.verify_slack_signature")
    @patch("slack.handler._build_middleware_chain")
    def test_event_blocked_by_middleware(
        self, mock_chain_builder, mock_verify, mock_secret
    ):
        mock_secret.return_value = "secret"
        mock_chain = MagicMock()
        mock_chain.run.return_value = MagicMock(
            allowed=False, should_respond=True, reason="Rate limited"
        )
        mock_chain_builder.return_value = mock_chain

        event = _make_api_gw_event(
            path="/slack/events",
            body={
                "type": "event_callback",
                "event": {
                    "type": "message",
                    "user": "U123",
                    "channel": "C789",
                    "text": "Hello",
                    "ts": "123.456",
                    "event_ts": "123.456",
                },
                "event_id": "Ev001",
                "team_id": "W456",
            },
        )
        result = lambda_handler(event, {})
        assert result["statusCode"] == 200

    @patch("slack.handler._get_signing_secret")
    @patch("slack.handler.verify_slack_signature")
    @patch("slack.handler._get_state_store")
    def test_slash_command_routed(self, mock_get_store, mock_verify, mock_secret):
        mock_secret.return_value = "secret"
        mock_get_store.return_value = MagicMock()
        event = _make_api_gw_event(
            path="/slack/commands",
            body={
                "command": "/onboard-help",
                "user_id": "U123",
                "team_id": "W456",
                "channel_id": "C789",
                "trigger_id": "T001",
                "text": "",
                "response_url": "https://hooks.slack.com/commands/xxx",
            },
        )
        result = lambda_handler(event, {})
        assert result["statusCode"] == 200
