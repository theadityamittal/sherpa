"""Tests for admin setup state machine."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from admin.setup import SetupDependencies, _is_valid_url, process_setup_message
from state.models import OnboardingPlan, PlanStatus, PlanStep, SetupState, StepStatus


def _make_state(
    step: str = "welcome",
    admin_user_id: str = "U_ADMIN",
    workspace_id: str = "W1",
    **kwargs,
) -> SetupState:
    return SetupState(
        step=step,
        admin_user_id=admin_user_id,
        workspace_id=workspace_id,
        created_at="2025-01-01T00:00:00+00:00",
        updated_at="2025-01-01T00:00:00+00:00",
        **kwargs,
    )


def _make_deps(**overrides) -> SetupDependencies:
    defaults = {
        "state_store": MagicMock(),
        "slack_client": MagicMock(),
        "encryptor": MagicMock(),
        "sqs_queue_url": "https://sqs.us-east-1.amazonaws.com/123/queue",
        "google_client_id": "test-client-id",
        "google_oauth_redirect_uri": "https://example.com/callback",
        "lambda_context": MagicMock(),
        "sqs_client": MagicMock(),
        "s3_client": MagicMock(),
        "s3_bucket": "test-bucket",
    }
    defaults.update(overrides)
    # Default: plenty of time remaining
    defaults["lambda_context"].get_remaining_time_in_millis.return_value = 300_000
    return SetupDependencies(**defaults)


class TestAdminSetup:
    def test_welcome_step_sends_greeting(self):
        state = _make_state(step="welcome")
        deps = _make_deps()

        result = process_setup_message(
            text="", action_id=None, setup_state=state, deps=deps
        )

        deps.slack_client.send_message.assert_called_once()
        msg = deps.slack_client.send_message.call_args[1]["text"]
        assert "welcome" in msg.lower()
        assert result.step == "awaiting_url"
        deps.state_store.save_setup_state.assert_called()

    def test_awaiting_url_validates_url(self):
        state = _make_state(step="awaiting_url")
        deps = _make_deps()
        # list_usergroups returns empty so we go through teams path
        deps.slack_client.list_usergroups.return_value = []

        with patch("rag.scraper.scrape_site", side_effect=Exception("no network")):
            result = process_setup_message(
                text="https://example.com",
                action_id=None,
                setup_state=state,
                deps=deps,
            )

        assert result.website_url == "https://example.com"
        # Should have progressed past scraping to teams
        assert result.step == "teams"

    def test_awaiting_url_rejects_non_url(self):
        state = _make_state(step="awaiting_url")
        deps = _make_deps()

        result = process_setup_message(
            text="not a url at all",
            action_id=None,
            setup_state=state,
            deps=deps,
        )

        # State should remain unchanged
        assert result.step == "awaiting_url"
        msg = deps.slack_client.send_message.call_args[1]["text"]
        assert "valid url" in msg.lower()

    def test_scraping_sends_progress_updates(self):
        state = _make_state(step="awaiting_url")
        deps = _make_deps()
        deps.slack_client.list_usergroups.return_value = []

        mock_pages = [MagicMock() for _ in range(3)]
        with patch("rag.scraper.scrape_site", return_value=mock_pages):
            process_setup_message(
                text="https://example.com",
                action_id=None,
                setup_state=state,
                deps=deps,
            )

        # Should have sent scraping progress message
        messages = [c[1]["text"] for c in deps.slack_client.send_message.call_args_list]
        assert any("3 pages" in m for m in messages)

    def test_scraping_self_enqueues_on_timeout(self):
        state = _make_state(step="awaiting_url")
        deps = _make_deps()
        # Simulate low remaining time
        deps.lambda_context.get_remaining_time_in_millis.return_value = 30_000

        with patch("rag.scraper.scrape_site"):
            result = process_setup_message(
                text="https://example.com",
                action_id=None,
                setup_state=state,
                deps=deps,
            )

        # Should have saved manifest and enqueued SQS message
        assert result.scrape_manifest_key != ""
        deps.sqs_client.send_message.assert_called()
        sqs_body = json.loads(deps.sqs_client.send_message.call_args[1]["MessageBody"])
        assert sqs_body["type"] == "setup_resume"

    def test_scraping_resumes_from_manifest(self):
        state = _make_state(
            step="scraping",
            website_url="https://example.com",
            scrape_manifest_key="scrape-manifest/W1.json",
        )
        deps = _make_deps()
        deps.slack_client.list_usergroups.return_value = []

        result = process_setup_message(
            text="", action_id=None, setup_state=state, deps=deps
        )

        # Should resume and eventually transition to teams
        assert result.step == "teams"
        messages = [c[1]["text"] for c in deps.slack_client.send_message.call_args_list]
        assert any("resum" in m.lower() for m in messages)

    def test_teams_step_auto_detects_usergroups(self):
        state = _make_state(step="awaiting_url")
        deps = _make_deps()
        deps.slack_client.list_usergroups.return_value = [
            {"name": "Engineering", "handle": "engineering"},
            {"name": "Marketing", "handle": "marketing"},
        ]

        with patch("rag.scraper.scrape_site", side_effect=Exception("no network")):
            result = process_setup_message(
                text="https://example.com",
                action_id=None,
                setup_state=state,
                deps=deps,
            )

        assert result.step == "teams"
        assert "Engineering" in result.teams
        assert "Marketing" in result.teams
        # Should have sent team_confirmation blocks
        block_calls = [
            c
            for c in deps.slack_client.send_message.call_args_list
            if c[1].get("blocks") is not None
        ]
        assert len(block_calls) >= 1

    def test_teams_step_fallback_manual_input(self):
        # When no usergroups detected, admin types team names
        state = _make_state(step="teams", teams=())
        deps = _make_deps()
        deps.slack_client.list_channels.return_value = [
            {"id": "C1", "name": "general"},
        ]

        result = process_setup_message(
            text="Engineering, Marketing, Sales",
            action_id=None,
            setup_state=state,
            deps=deps,
        )

        assert "Engineering" in result.teams
        assert "Marketing" in result.teams
        assert "Sales" in result.teams
        assert result.step == "channels"

    def test_channels_step_fetches_conversations(self):
        state = _make_state(
            step="teams",
            teams=("Engineering",),
        )
        deps = _make_deps()
        deps.slack_client.list_channels.return_value = [
            {"id": "C1", "name": "general"},
            {"id": "C2", "name": "engineering"},
        ]

        # Confirm teams to transition to channels
        result = process_setup_message(
            text="", action_id="teams_confirm", setup_state=state, deps=deps
        )

        assert result.step == "channels"
        deps.slack_client.list_channels.assert_called_once()
        # Should have sent channel_mapping blocks
        block_calls = [
            c
            for c in deps.slack_client.send_message.call_args_list
            if c[1].get("blocks") is not None
        ]
        assert len(block_calls) >= 1

    def test_calendar_enable_sends_oauth_url(self):
        state = _make_state(step="calendar")
        deps = _make_deps()
        deps.state_store.get_pending_users.return_value = []
        # complete_setup needs a workspace config
        deps.state_store.complete_setup.return_value = None

        result = process_setup_message(
            text="", action_id="calendar_enable", setup_state=state, deps=deps
        )

        messages = [c[1]["text"] for c in deps.slack_client.send_message.call_args_list]
        assert any("accounts.google.com" in m for m in messages)
        assert result.calendar_enabled is True

    def test_calendar_skip_sets_disabled(self):
        state = _make_state(step="calendar")
        deps = _make_deps()
        deps.state_store.get_pending_users.return_value = []
        deps.state_store.complete_setup.return_value = None

        result = process_setup_message(
            text="", action_id="calendar_skip_setup", setup_state=state, deps=deps
        )

        assert result.calendar_enabled is False
        assert result.step == "done"

    def test_confirmation_writes_config(self):
        state = _make_state(
            step="confirmation",
            website_url="https://example.com",
            teams=("Eng",),
            channel_mapping={"eng": "C1"},
            calendar_enabled=True,
        )
        deps = _make_deps()
        deps.state_store.get_pending_users.return_value = []

        process_setup_message(text="", action_id=None, setup_state=state, deps=deps)

        deps.state_store.complete_setup.assert_called_once_with(
            workspace_id="W1",
            config_updates={
                "admin_user_id": "U_ADMIN",
                "website_url": "https://example.com",
                "teams": ["Eng"],
                "channel_mapping": {"eng": "C1"},
                "calendar_enabled": True,
            },
        )

    def test_confirmation_deletes_setup_record(self):
        """complete_setup internally deletes the SETUP record."""
        state = _make_state(step="confirmation")
        deps = _make_deps()
        deps.state_store.get_pending_users.return_value = []

        process_setup_message(text="", action_id=None, setup_state=state, deps=deps)

        # complete_setup is called which internally calls delete_setup_state
        deps.state_store.complete_setup.assert_called_once()

    def test_pending_users_enqueued_after_setup(self):
        state = _make_state(step="confirmation")
        deps = _make_deps()

        pending_plan = OnboardingPlan(
            workspace_id="W1",
            user_id="U_PENDING",
            user_name="Bob",
            role="engineer",
            status=PlanStatus.PENDING_SETUP,
            version=1,
            steps=[PlanStep(id=1, title="Welcome", status=StepStatus.PENDING)],
        )
        deps.state_store.get_pending_users.return_value = [pending_plan]

        process_setup_message(text="", action_id=None, setup_state=state, deps=deps)

        deps.sqs_client.send_message.assert_called()
        sqs_body = json.loads(deps.sqs_client.send_message.call_args[1]["MessageBody"])
        assert sqs_body["type"] == "onboard_user"
        assert sqs_body["user_id"] == "U_PENDING"


class TestUrlValidation:
    def test_valid_https_url(self):
        assert _is_valid_url("https://example.com") is True

    def test_valid_http_url(self):
        assert _is_valid_url("http://example.com") is True

    def test_valid_url_with_path(self):
        assert _is_valid_url("https://example.com/about") is True

    def test_rejects_plain_text(self):
        assert _is_valid_url("not a url") is False

    def test_rejects_no_scheme(self):
        assert _is_valid_url("example.com") is False

    def test_rejects_empty_string(self):
        assert _is_valid_url("") is False

    def test_rejects_ftp(self):
        assert _is_valid_url("ftp://example.com") is False


class TestUnknownStep:
    def test_unknown_step_returns_state_unchanged(self):
        state = _make_state(step="nonexistent_step")
        deps = _make_deps()

        result = process_setup_message(
            text="", action_id=None, setup_state=state, deps=deps
        )

        assert result is state
