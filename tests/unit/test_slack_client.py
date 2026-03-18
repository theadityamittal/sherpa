"""Tests for Slack WebClient wrapper."""

from __future__ import annotations

from unittest.mock import MagicMock

from slack.client import SlackClient


class TestSlackClient:
    def test_send_message(self):
        mock_web = MagicMock()
        mock_web.chat_postMessage.return_value = {"ok": True, "ts": "123.456"}
        client = SlackClient(web_client=mock_web)
        ts = client.send_message(channel="C1", text="Hello")
        assert ts == "123.456"
        mock_web.chat_postMessage.assert_called_once_with(channel="C1", text="Hello")

    def test_send_message_with_blocks(self):
        mock_web = MagicMock()
        mock_web.chat_postMessage.return_value = {"ok": True, "ts": "123.456"}
        client = SlackClient(web_client=mock_web)
        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": "Hi"}}]
        client.send_message(channel="C1", text="Hi", blocks=blocks)
        mock_web.chat_postMessage.assert_called_once_with(
            channel="C1", text="Hi", blocks=blocks
        )

    def test_send_ephemeral(self):
        mock_web = MagicMock()
        mock_web.chat_postEphemeral.return_value = {"ok": True}
        client = SlackClient(web_client=mock_web)
        client.send_ephemeral(channel="C1", user="U1", text="Only you can see this")
        mock_web.chat_postEphemeral.assert_called_once_with(
            channel="C1", user="U1", text="Only you can see this"
        )

    def test_update_message(self):
        mock_web = MagicMock()
        mock_web.chat_update.return_value = {"ok": True}
        client = SlackClient(web_client=mock_web)
        client.update_message(channel="C1", ts="123.456", text="Updated")
        mock_web.chat_update.assert_called_once_with(
            channel="C1", ts="123.456", text="Updated"
        )

    def test_send_message_in_thread(self):
        mock_web = MagicMock()
        mock_web.chat_postMessage.return_value = {"ok": True, "ts": "123.789"}
        client = SlackClient(web_client=mock_web)
        ts = client.send_message(channel="C1", text="Reply", thread_ts="123.456")
        mock_web.chat_postMessage.assert_called_once_with(
            channel="C1", text="Reply", thread_ts="123.456"
        )
        assert ts == "123.789"
