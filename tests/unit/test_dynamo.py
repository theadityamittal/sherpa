"""Tests for DynamoDB CRUD operations."""

from unittest.mock import MagicMock

from botocore.exceptions import ClientError
from state.dynamo import DynamoStateStore
from state.models import (
    CompletionRecord,
    OnboardingPlan,
    PlanStatus,
    PlanStep,
    StepStatus,
)


class TestDynamoStateStore:
    def _make_store(self, mock_table=None):
        table = mock_table or MagicMock()
        return DynamoStateStore(table=table)

    def test_get_plan_returns_plan(self):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "pk": "WORKSPACE#W1",
                "sk": "PLAN#U1",
                "workspace_id": "W1",
                "user_id": "U1",
                "user_name": "Jane",
                "role": "events",
                "status": "in_progress",
                "plan": {
                    "version": 1,
                    "steps": [{"id": 1, "title": "Welcome", "status": "pending"}],
                },
                "context": {"key_facts": [], "recent_messages": []},
            }
        }

        store = self._make_store(mock_table)
        plan = store.get_plan(workspace_id="W1", user_id="U1")

        assert plan is not None
        assert plan.workspace_id == "W1"
        assert len(plan.steps) == 1

    def test_get_plan_returns_none_when_missing(self):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}

        store = self._make_store(mock_table)
        plan = store.get_plan(workspace_id="W1", user_id="U1")
        assert plan is None

    def test_save_plan_puts_item(self):
        mock_table = MagicMock()
        store = self._make_store(mock_table)

        plan = OnboardingPlan(
            workspace_id="W1",
            user_id="U1",
            user_name="Jane",
            role="events",
            status=PlanStatus.IN_PROGRESS,
            version=1,
            steps=[PlanStep(id=1, title="Welcome", status=StepStatus.PENDING)],
        )
        store.save_plan(plan)
        mock_table.put_item.assert_called_once()

        item = mock_table.put_item.call_args[1]["Item"]
        assert item["pk"] == "WORKSPACE#W1"
        assert item["sk"] == "PLAN#U1"

    def test_save_plan_includes_ttl(self):
        mock_table = MagicMock()
        store = self._make_store(mock_table)

        plan = OnboardingPlan(
            workspace_id="W1",
            user_id="U1",
            user_name="Jane",
            role="events",
            status=PlanStatus.IN_PROGRESS,
            version=1,
            steps=[],
        )
        store.save_plan(plan)

        item = mock_table.put_item.call_args[1]["Item"]
        assert "ttl" in item
        assert isinstance(item["ttl"], int)

    def test_save_completion_record_no_ttl(self):
        mock_table = MagicMock()
        store = self._make_store(mock_table)

        record = CompletionRecord(
            workspace_id="W1",
            user_id="U1",
            role="events",
            plan_version=2,
            steps_completed=5,
            replans=1,
            duration_minutes=120,
            channels_assigned=("events",),
            calendar_events_created=0,
        )
        store.save_completion_record(record)

        item = mock_table.put_item.call_args[1]["Item"]
        assert item["pk"] == "WORKSPACE#W1"
        assert item["sk"] == "COMPLETED#U1"
        assert "ttl" not in item

    def test_acquire_lock_succeeds(self):
        mock_table = MagicMock()
        store = self._make_store(mock_table)

        result = store.acquire_lock(workspace_id="W1", user_id="U1")
        assert result is True
        mock_table.put_item.assert_called_once()

    def test_acquire_lock_fails_on_condition(self):
        mock_table = MagicMock()
        mock_table.put_item.side_effect = ClientError(
            {"Error": {"Code": "ConditionalCheckFailedException"}},
            "PutItem",
        )

        store = self._make_store(mock_table)
        result = store.acquire_lock(workspace_id="W1", user_id="U1")
        assert result is False

    def test_release_lock_deletes_item(self):
        mock_table = MagicMock()
        store = self._make_store(mock_table)

        store.release_lock(workspace_id="W1", user_id="U1")
        mock_table.delete_item.assert_called_once_with(
            Key={"pk": "WORKSPACE#W1", "sk": "LOCK#U1"}
        )

    def test_get_kill_switch_status(self):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {"pk": "SYSTEM", "sk": "KILL_SWITCH", "active": True}
        }

        store = self._make_store(mock_table)
        assert store.get_kill_switch_status() is True

    def test_get_kill_switch_default_false(self):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}

        store = self._make_store(mock_table)
        assert store.get_kill_switch_status() is False

    def test_set_kill_switch_activates(self):
        mock_table = MagicMock()
        store = self._make_store(mock_table)

        store.set_kill_switch(active=True)
        mock_table.put_item.assert_called_once()
        item = mock_table.put_item.call_args[1]["Item"]
        assert item["pk"] == "SYSTEM"
        assert item["sk"] == "KILL_SWITCH"
        assert item["active"] is True

    def test_set_kill_switch_deactivates(self):
        mock_table = MagicMock()
        store = self._make_store(mock_table)

        store.set_kill_switch(active=False)
        item = mock_table.put_item.call_args[1]["Item"]
        assert item["active"] is False
