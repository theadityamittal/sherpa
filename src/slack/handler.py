# src/slack/handler.py
"""Slack Handler Lambda — entry point for all Slack HTTP events.

Routes:
- POST /slack/events — Slack Events API (messages, mentions, team_join)
- POST /slack/commands — Slash commands (/onboard-status, -help, -restart)
- POST /slack/interactions — Interactive component callbacks

Strategy:
1. Verify Slack signature (sync, <1ms)
2. Return 200 immediately for events
3. Run middleware chain + enqueue to SQS
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any
from urllib.parse import parse_qs

import boto3
from slack.commands import handle_command
from slack.models import SlackCommand, SlackEvent, SQSMessage
from slack.signature import InvalidSignatureError, verify_slack_signature

logger = logging.getLogger(__name__)


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Main Lambda handler for Slack events, commands, and interactions."""
    body_str = event.get("body", "")
    headers = event.get("headers", {})
    path = event.get("path", "")

    # Verify Slack signature
    signing_secret = _get_signing_secret()
    try:
        verify_slack_signature(
            signing_secret=signing_secret,
            body=body_str,
            timestamp=headers.get("X-Slack-Request-Timestamp", ""),
            signature=headers.get("X-Slack-Signature", ""),
        )
    except InvalidSignatureError:
        logger.warning("Invalid Slack signature")
        return _json_response(401, {"error": "Invalid signature"})

    # Route by path
    if path == "/slack/commands":
        return _handle_slash_command(body_str)
    elif path == "/slack/interactions":
        return _handle_interaction(body_str)
    else:
        return _handle_event(body_str)


def _handle_event(body_str: str) -> dict[str, Any]:
    """Handle Slack Events API callbacks."""
    body = json.loads(body_str)

    # URL verification challenge
    if body.get("type") == "url_verification":
        return _json_response(200, {"challenge": body["challenge"]})

    # Parse event
    slack_event = SlackEvent.from_event_body(body)

    # Run middleware chain
    chain = _build_middleware_chain()
    result = chain.run(slack_event)

    if not result.allowed:
        logger.info(
            "Event blocked by middleware: %s (reason: %s)",
            slack_event.event_id,
            result.reason,
        )
        return _json_response(200, {"ok": True})

    # Enqueue to SQS
    sqs_msg = SQSMessage(
        version="1.0",
        event_id=slack_event.event_id,
        workspace_id=slack_event.workspace_id,
        user_id=slack_event.user_id,
        channel_id=slack_event.channel_id,
        event_type=slack_event.event_type,
        text=slack_event.text,
        timestamp=slack_event.timestamp,
        is_dm=slack_event.channel_id.startswith("D"),
        thread_ts=slack_event.thread_ts,
    )
    _enqueue_to_sqs(sqs_msg)

    return _json_response(200, {"ok": True})


def _handle_slash_command(body_str: str) -> dict[str, Any]:
    """Handle slash commands (form-encoded body)."""
    try:
        body = json.loads(body_str)
    except json.JSONDecodeError:
        # Slash commands are form-encoded in production
        parsed = parse_qs(body_str)
        body = {k: v[0] for k, v in parsed.items()}

    command = SlackCommand.from_command_body(body)
    state_store = _get_state_store()
    result: dict[str, Any] = handle_command(command, state_store=state_store)
    return result


def _handle_interaction(body_str: str) -> dict[str, Any]:
    """Handle interactive component callbacks (buttons, modals).

    Stub for Phase 2 — will be implemented when agent brain is added.
    """
    return _json_response(200, {"ok": True})


def _build_middleware_chain() -> Any:
    """Build the inbound middleware chain with real dependencies."""
    from middleware.inbound.chain import InboundMiddlewareChain

    state_store = _get_state_store()
    return InboundMiddlewareChain(state_store=state_store)


def _get_state_store() -> Any:
    """Get or create the DynamoDB state store."""
    from state.dynamo import DynamoStateStore

    table_name = os.environ.get("DYNAMODB_TABLE_NAME", "onboard-assist")
    table = boto3.resource("dynamodb").Table(table_name)
    return DynamoStateStore(table=table)


def _get_signing_secret() -> str:
    """Retrieve Slack signing secret from Secrets Manager."""
    secret_arn = os.environ.get("SLACK_SIGNING_SECRET_ARN", "")
    if not secret_arn:
        # Fallback for local dev
        return os.environ.get("SLACK_SIGNING_SECRET", "")

    client = boto3.client("secretsmanager")
    response = client.get_secret_value(SecretId=secret_arn)
    secret_str: str = response["SecretString"]
    try:
        secret_data = json.loads(secret_str)
        return str(secret_data.get("signing_secret", secret_str))
    except json.JSONDecodeError:
        return secret_str


def _enqueue_to_sqs(msg: SQSMessage) -> None:
    """Send a normalized message to the SQS FIFO queue."""
    queue_url = os.environ.get("SQS_QUEUE_URL", "")
    if not queue_url:
        logger.error("SQS_QUEUE_URL not set")
        return

    sqs = boto3.client("sqs")
    sqs.send_message(
        QueueUrl=queue_url,
        MessageBody=json.dumps(msg.to_dict()),
        MessageGroupId=f"{msg.workspace_id}#{msg.user_id}",
        MessageDeduplicationId=msg.event_id,
    )
    logger.info("Enqueued event %s to SQS", msg.event_id)


def _json_response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    """Build an API Gateway proxy response."""
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }
