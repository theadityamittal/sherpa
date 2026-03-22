"""SQS message enqueue — shared by handler and commands."""

from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING

import boto3

if TYPE_CHECKING:
    from slack.models import SQSMessage

logger = logging.getLogger(__name__)


def enqueue_to_sqs(msg: SQSMessage) -> None:
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
