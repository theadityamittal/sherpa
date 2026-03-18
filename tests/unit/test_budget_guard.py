"""Tests for token budget enforcement middleware."""

from __future__ import annotations

from unittest.mock import MagicMock

from middleware.inbound.budget_guard import TokenBudgetGuard
from slack.models import EventType, SlackEvent


def _make_event(user_id: str = "U1", workspace_id: str = "W1") -> SlackEvent:
    return SlackEvent(
        event_id="Ev001",
        workspace_id=workspace_id,
        user_id=user_id,
        channel_id="C1",
        text="hello",
        event_type=EventType.MESSAGE,
        timestamp="123",
    )


class TestTokenBudgetGuard:
    def test_allows_when_under_daily_limit(self):
        mock_store = MagicMock()
        mock_store.get_daily_usage_turns.return_value = 10
        mock_store.get_monthly_usage_cost.return_value = 1.0
        guard = TokenBudgetGuard(
            state_store=mock_store,
            max_turns_per_day=50,
            max_monthly_cost=5.0,
        )
        result = guard.check(_make_event())
        assert result.allowed is True

    def test_rejects_when_daily_limit_exceeded(self):
        mock_store = MagicMock()
        mock_store.get_daily_usage_turns.return_value = 50
        mock_store.get_monthly_usage_cost.return_value = 1.0
        guard = TokenBudgetGuard(
            state_store=mock_store,
            max_turns_per_day=50,
            max_monthly_cost=5.0,
        )
        result = guard.check(_make_event())
        assert result.allowed is False
        assert "daily" in result.reason.lower()

    def test_rejects_when_monthly_limit_exceeded(self):
        mock_store = MagicMock()
        mock_store.get_daily_usage_turns.return_value = 10
        mock_store.get_monthly_usage_cost.return_value = 5.5
        guard = TokenBudgetGuard(
            state_store=mock_store,
            max_turns_per_day=50,
            max_monthly_cost=5.0,
        )
        result = guard.check(_make_event())
        assert result.allowed is False
        assert "monthly" in result.reason.lower()

    def test_daily_checked_before_monthly(self):
        mock_store = MagicMock()
        mock_store.get_daily_usage_turns.return_value = 50
        mock_store.get_monthly_usage_cost.return_value = 6.0
        guard = TokenBudgetGuard(
            state_store=mock_store,
            max_turns_per_day=50,
            max_monthly_cost=5.0,
        )
        result = guard.check(_make_event())
        assert "daily" in result.reason.lower()
