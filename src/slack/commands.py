"""Slash command handlers for Slack.

/onboard-status -- show onboarding progress
/onboard-help -- list available commands
/onboard-restart -- confirm and restart onboarding
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from state.models import StepStatus

if TYPE_CHECKING:
    from slack.models import SlackCommand
    from state.dynamo import DynamoStateStore

logger = logging.getLogger(__name__)


def handle_command(
    command: SlackCommand,
    *,
    state_store: DynamoStateStore,
) -> dict[str, Any]:
    handlers = {
        "/onboard-status": _handle_status,
        "/onboard-help": _handle_help,
        "/onboard-restart": _handle_restart,
    }
    handler = handlers.get(command.command, _handle_unknown)
    return handler(command, state_store=state_store)


def _handle_status(
    command: SlackCommand,
    *,
    state_store: DynamoStateStore,
) -> dict[str, Any]:
    plan = state_store.get_plan(
        workspace_id=command.workspace_id,
        user_id=command.user_id,
    )
    if plan is None:
        return _response("You have no active onboarding plan.")

    status_icons = {
        StepStatus.COMPLETED: "✅",
        StepStatus.IN_PROGRESS: "🔄",
        StepStatus.PENDING: "⬜",
        StepStatus.BLOCKED: "⏸️",
    }
    completed = sum(1 for s in plan.steps if s.status == StepStatus.COMPLETED)
    total = len(plan.steps)
    lines = [f"*Onboarding Progress — {plan.user_name}*\n"]
    for step in plan.steps:
        icon = status_icons.get(step.status, "⬜")
        lines.append(f"{icon} {step.title}")
    pct = int(completed / total * 100) if total else 0
    lines.append(f"\nProgress: {completed}/{total} steps ({pct}%)")
    return _response("\n".join(lines))


def _handle_help(
    command: SlackCommand,
    *,
    state_store: DynamoStateStore,
) -> dict[str, Any]:
    text = (
        "*Onboard Assist Commands*\n"
        "• `/onboard-status` — View your onboarding progress\n"
        "• `/onboard-help` — Show this help message\n"
        "• `/onboard-restart` — Restart your onboarding (with confirmation)"
    )
    return _response(text)


def _handle_restart(
    command: SlackCommand,
    *,
    state_store: DynamoStateStore,
) -> dict[str, Any]:
    text = (
        "⚠️ *Are you sure you want to restart onboarding?*\n"
        "Your current progress will be reset. "
        "Reply with `confirm restart` to proceed."
    )
    return _response(text)


def _handle_unknown(
    command: SlackCommand,
    *,
    state_store: DynamoStateStore,
) -> dict[str, Any]:
    return _response(
        f"Unknown command: `{command.command}`. "
        "Try `/onboard-help` for available commands."
    )


def _response(text: str) -> dict[str, Any]:
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"response_type": "ephemeral", "text": text}),
    }
