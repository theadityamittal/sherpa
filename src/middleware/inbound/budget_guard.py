# src/middleware/inbound/budget_guard.py
"""Token budget enforcement middleware.

Checks per-user daily and per-workspace monthly limits
before allowing message processing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from slack.models import MiddlewareResult, SlackEvent

if TYPE_CHECKING:
    from state.dynamo import DynamoStateStore


class TokenBudgetGuard:
    """Enforce daily and monthly usage limits."""

    def __init__(
        self,
        *,
        state_store: DynamoStateStore,
        max_turns_per_day: int,
        max_monthly_cost: float,
    ) -> None:
        self._store = state_store
        self._max_turns_per_day = max_turns_per_day
        self._max_monthly_cost = max_monthly_cost

    def check(self, event: SlackEvent) -> MiddlewareResult:
        daily_turns = self._store.get_daily_usage_turns(
            workspace_id=event.workspace_id,
            user_id=event.user_id,
        )
        if daily_turns >= self._max_turns_per_day:
            return MiddlewareResult.reject(
                "Daily limit reached. I'll be back tomorrow!"
            )

        monthly_cost = self._store.get_monthly_usage_cost(
            workspace_id=event.workspace_id,
        )
        if monthly_cost >= self._max_monthly_cost:
            return MiddlewareResult.reject(
                "Monthly limit reached. Service resumes next month."
            )

        return MiddlewareResult.allow()
