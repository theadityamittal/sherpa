"""Tests for slash command handlers."""

from __future__ import annotations

from unittest.mock import MagicMock

from slack.commands import handle_command
from slack.models import SlackCommand
from state.models import OnboardingPlan, PlanStatus, PlanStep, StepStatus


def _make_command(command: str, user_id: str = "U1") -> SlackCommand:
    return SlackCommand(
        command=command,
        user_id=user_id,
        workspace_id="W1",
        channel_id="C1",
        trigger_id="T1",
        text="",
        response_url="https://hooks.slack.com/commands/xxx",
    )


class TestHandleCommand:
    def test_status_with_active_plan(self):
        mock_store = MagicMock()
        mock_store.get_plan.return_value = OnboardingPlan(
            workspace_id="W1",
            user_id="U1",
            user_name="Jane",
            role="events",
            status=PlanStatus.IN_PROGRESS,
            version=1,
            steps=[
                PlanStep(id=1, title="Welcome", status=StepStatus.COMPLETED),
                PlanStep(id=2, title="Intake", status=StepStatus.IN_PROGRESS),
                PlanStep(id=3, title="Training", status=StepStatus.PENDING),
            ],
        )
        response = handle_command(
            _make_command("/onboard-status"), state_store=mock_store
        )
        assert response["statusCode"] == 200
        body = response["body"]
        assert "Jane" in body or "Progress" in body

    def test_status_with_no_plan(self):
        mock_store = MagicMock()
        mock_store.get_plan.return_value = None
        response = handle_command(
            _make_command("/onboard-status"), state_store=mock_store
        )
        assert response["statusCode"] == 200
        assert "no active" in response["body"].lower()

    def test_help_returns_static(self):
        mock_store = MagicMock()
        response = handle_command(
            _make_command("/onboard-help"), state_store=mock_store
        )
        assert response["statusCode"] == 200
        assert "/onboard-status" in response["body"]

    def test_restart_returns_confirmation(self):
        mock_store = MagicMock()
        response = handle_command(
            _make_command("/onboard-restart"), state_store=mock_store
        )
        assert response["statusCode"] == 200
        assert (
            "confirm" in response["body"].lower()
            or "restart" in response["body"].lower()
        )

    def test_unknown_command(self):
        mock_store = MagicMock()
        response = handle_command(_make_command("/unknown"), state_store=mock_store)
        assert response["statusCode"] == 200
        assert (
            "unknown" in response["body"].lower() or "help" in response["body"].lower()
        )
