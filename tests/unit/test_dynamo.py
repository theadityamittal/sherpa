"""Tests for DynamoDB CRUD operations."""

import json
import time
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


class TestSecretsRecord:
    def _make_store(self, mock_table=None):
        table = mock_table or MagicMock()
        return DynamoStateStore(table=table)

    def _make_encryptor(self, encrypt_return="ENCRYPTED", decrypt_return=None):
        enc = MagicMock()
        enc.encrypt.return_value = encrypt_return
        if decrypt_return is not None:
            enc.decrypt.return_value = decrypt_return
        return enc

    def test_save_secrets_encrypts_and_stores(self):
        mock_table = MagicMock()
        store = self._make_store(mock_table)
        secrets = {"bot_token": "xoxb-123", "google_refresh_token": "1//abc"}
        enc = self._make_encryptor(encrypt_return="ENCRYPTED_BLOB")

        store.save_workspace_secrets(
            workspace_id="W1", secrets_blob=secrets, encryptor=enc
        )

        enc.encrypt.assert_called_once_with(json.dumps(secrets))
        mock_table.put_item.assert_called_once()
        item = mock_table.put_item.call_args[1]["Item"]
        assert item["pk"] == "WORKSPACE#W1"
        assert item["sk"] == "SECRETS"
        assert item["encrypted_data"] == "ENCRYPTED_BLOB"

    def test_save_secrets_updates_ttl(self):
        mock_table = MagicMock()
        store = self._make_store(mock_table)
        enc = self._make_encryptor()

        before = int(time.time())
        store.save_workspace_secrets(
            workspace_id="W1", secrets_blob={"bot_token": "xoxb-999"}, encryptor=enc
        )
        after = int(time.time())

        item = mock_table.put_item.call_args[1]["Item"]
        assert "ttl" in item
        expected_min = before + (90 * 86400)
        expected_max = after + (90 * 86400)
        assert expected_min <= item["ttl"] <= expected_max

    def test_get_secrets_decrypts_and_returns(self):
        mock_table = MagicMock()
        secrets = {"bot_token": "xoxb-123", "google_refresh_token": "1//abc"}
        mock_table.get_item.return_value = {
            "Item": {
                "pk": "WORKSPACE#W1",
                "sk": "SECRETS",
                "encrypted_data": "ENCRYPTED_BLOB",
                "ttl": 9999999999,
            }
        }
        store = self._make_store(mock_table)
        enc = self._make_encryptor(decrypt_return=json.dumps(secrets))

        result = store.get_workspace_secrets(workspace_id="W1", encryptor=enc)

        mock_table.get_item.assert_called_once_with(
            Key={"pk": "WORKSPACE#W1", "sk": "SECRETS"}
        )
        enc.decrypt.assert_called_once_with("ENCRYPTED_BLOB")
        assert result == secrets

    def test_get_secrets_nonexistent_returns_none(self):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}
        store = self._make_store(mock_table)
        enc = self._make_encryptor()

        result = store.get_workspace_secrets(workspace_id="W1", encryptor=enc)

        assert result is None
        enc.decrypt.assert_not_called()

    def test_lazy_migration_moves_bot_token_from_config(self):
        mock_table = MagicMock()
        store = self._make_store(mock_table)
        enc = self._make_encryptor(encrypt_return="ENCRYPTED_TOKEN")

        mock_table.get_item.return_value = {
            "Item": {
                "pk": "WORKSPACE#W1",
                "sk": "CONFIG",
                "workspace_id": "W1",
                "team_name": "Acme",
                "bot_token": "xoxb-original",
                "bot_user_id": "U_BOT",
                "active": True,
                "updated_at": 1000,
            }
        }

        store.migrate_bot_token_to_secrets(workspace_id="W1", encryptor=enc)

        # Should have written to SECRETS
        put_calls = mock_table.put_item.call_args_list
        secrets_calls = [c for c in put_calls if c[1]["Item"].get("sk") == "SECRETS"]
        assert len(secrets_calls) == 1
        secrets_item = secrets_calls[0][1]["Item"]
        assert secrets_item["pk"] == "WORKSPACE#W1"

        # Verify the encrypted data came from the bot_token
        decrypted_secrets = json.loads(enc.encrypt.call_args[0][0])
        assert decrypted_secrets["bot_token"] == "xoxb-original"

        # Should have updated CONFIG to remove bot_token
        update_calls = mock_table.update_item.call_args_list
        assert len(update_calls) == 1
        update_call = update_calls[0][1]
        assert update_call["Key"] == {"pk": "WORKSPACE#W1", "sk": "CONFIG"}
        assert "bot_token" in update_call["UpdateExpression"]
