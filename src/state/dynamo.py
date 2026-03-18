"""DynamoDB CRUD operations for single-table design."""

from __future__ import annotations

import logging
import time
from typing import Any

from botocore.exceptions import ClientError
from state.models import CompletionRecord, OnboardingPlan
from state.ttl import ttl_for_lock, ttl_for_plan

logger = logging.getLogger(__name__)


class DynamoStateStore:
    """DynamoDB operations using single-table design.

    All operations use pk/sk access patterns.
    """

    def __init__(self, *, table: Any) -> None:
        """Initialize with a boto3 DynamoDB Table resource."""
        self._table = table

    def get_plan(self, *, workspace_id: str, user_id: str) -> OnboardingPlan | None:
        """Retrieve an active onboarding plan."""
        response = self._table.get_item(
            Key={
                "pk": f"WORKSPACE#{workspace_id}",
                "sk": f"PLAN#{user_id}",
            }
        )
        item = response.get("Item")
        if not item:
            return None
        return OnboardingPlan.from_dynamo_item(item)

    def save_plan(self, plan: OnboardingPlan) -> None:
        """Save or update an onboarding plan with TTL."""
        item = plan.to_dynamo_item()
        item["ttl"] = ttl_for_plan()
        self._table.put_item(Item=item)

    def save_completion_record(self, record: CompletionRecord) -> None:
        """Save a completion record (no TTL -- permanent)."""
        item = record.to_dynamo_item()
        self._table.put_item(Item=item)

    def acquire_lock(self, *, workspace_id: str, user_id: str) -> bool:
        """Acquire a processing lock. Returns True if acquired, False if held."""
        try:
            self._table.put_item(
                Item={
                    "pk": f"WORKSPACE#{workspace_id}",
                    "sk": f"LOCK#{user_id}",
                    "ttl": ttl_for_lock(),
                },
                ConditionExpression="attribute_not_exists(pk)",
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise

    def release_lock(self, *, workspace_id: str, user_id: str) -> None:
        """Release a processing lock."""
        self._table.delete_item(
            Key={
                "pk": f"WORKSPACE#{workspace_id}",
                "sk": f"LOCK#{user_id}",
            }
        )

    def get_kill_switch_status(self) -> bool:
        """Check if the global kill switch is active."""
        response = self._table.get_item(Key={"pk": "SYSTEM", "sk": "KILL_SWITCH"})
        item = response.get("Item")
        if not item:
            return False
        result: bool = item.get("active", False)
        return result

    def set_kill_switch(self, *, active: bool) -> None:
        """Set the global kill switch status."""
        self._table.put_item(
            Item={
                "pk": "SYSTEM",
                "sk": "KILL_SWITCH",
                "active": active,
                "updated_at": int(time.time()),
            }
        )
