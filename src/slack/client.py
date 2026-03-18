"""Thin wrapper around Slack WebClient for sending messages."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from slack_sdk import WebClient

logger = logging.getLogger(__name__)


class SlackClient:
    """Wrapper around slack_sdk WebClient."""

    def __init__(self, *, web_client: WebClient) -> None:
        self._client = web_client

    def send_message(
        self,
        *,
        channel: str,
        text: str,
        blocks: list[dict[str, Any]] | None = None,
        thread_ts: str | None = None,
    ) -> str:
        kwargs: dict[str, Any] = {"channel": channel, "text": text}
        if blocks is not None:
            kwargs["blocks"] = blocks
        if thread_ts is not None:
            kwargs["thread_ts"] = thread_ts
        response = self._client.chat_postMessage(**kwargs)
        ts: str = response.get("ts", "")
        return ts

    def send_ephemeral(self, *, channel: str, user: str, text: str) -> None:
        self._client.chat_postEphemeral(channel=channel, user=user, text=text)

    def update_message(
        self,
        *,
        channel: str,
        ts: str,
        text: str,
        blocks: list[dict[str, Any]] | None = None,
    ) -> None:
        kwargs: dict[str, Any] = {"channel": channel, "ts": ts, "text": text}
        if blocks is not None:
            kwargs["blocks"] = blocks
        self._client.chat_update(**kwargs)
