"""Tests for Slack Block Kit builder functions."""

from __future__ import annotations

from slack.blocks import (
    calendar_confirmation,
    calendar_setup_prompt,
    channel_mapping,
    relink_calendar,
    team_confirmation,
)


def _find_blocks_of_type(blocks: list[dict], block_type: str) -> list[dict]:
    return [b for b in blocks if b.get("type") == block_type]


def _find_action_ids(blocks: list[dict]) -> list[str]:
    """Collect all action_ids from all actions blocks."""
    ids: list[str] = []
    for block in blocks:
        if block.get("type") == "actions":
            for element in block.get("elements", []):
                action_id = element.get("action_id")
                if action_id:
                    ids.append(action_id)
    return ids


def _find_select_action_ids(blocks: list[dict]) -> list[str]:
    """Collect action_ids from section accessory selects."""
    ids: list[str] = []
    for block in blocks:
        if block.get("type") == "section":
            accessory = block.get("accessory", {})
            action_id = accessory.get("action_id")
            if action_id:
                ids.append(action_id)
    return ids


class TestCalendarConfirmation:
    def test_calendar_confirmation_has_confirm_skip_buttons(self):
        blocks = calendar_confirmation(
            title="Team Sync",
            date="2025-03-20",
            time="10:00 AM",
            attendees=["alice@example.com"],
        )
        action_ids = _find_action_ids(blocks)
        assert "calendar_confirm" in action_ids
        assert "calendar_skip" in action_ids

    def test_calendar_confirmation_includes_event_details(self):
        blocks = calendar_confirmation(
            title="Team Sync",
            date="2025-03-20",
            time="10:00 AM",
            attendees=["alice@example.com", "bob@example.com"],
        )
        # All text across section blocks must include key details
        all_text = " ".join(
            block["text"]["text"]
            for block in _find_blocks_of_type(blocks, "section")
            if "text" in block
        )
        assert "Team Sync" in all_text
        assert "2025-03-20" in all_text
        assert "10:00 AM" in all_text
        assert "alice@example.com" in all_text

    def test_calendar_confirmation_returns_list_of_dicts(self):
        blocks = calendar_confirmation(
            title="Sync", date="2025-01-01", time="9:00 AM", attendees=[]
        )
        assert isinstance(blocks, list)
        assert all(isinstance(b, dict) for b in blocks)

    def test_calendar_confirmation_confirm_button_is_primary(self):
        blocks = calendar_confirmation(
            title="Sync", date="2025-01-01", time="9:00 AM", attendees=[]
        )
        for block in blocks:
            if block.get("type") == "actions":
                for element in block.get("elements", []):
                    if element.get("action_id") == "calendar_confirm":
                        assert element.get("style") == "primary"


class TestCalendarSetupPrompt:
    def test_calendar_setup_prompt_has_enable_skip_buttons(self):
        blocks = calendar_setup_prompt()
        action_ids = _find_action_ids(blocks)
        assert "calendar_enable" in action_ids
        assert "calendar_skip_setup" in action_ids

    def test_calendar_setup_prompt_returns_list_of_dicts(self):
        blocks = calendar_setup_prompt()
        assert isinstance(blocks, list)
        assert all(isinstance(b, dict) for b in blocks)

    def test_calendar_setup_prompt_has_header_text(self):
        blocks = calendar_setup_prompt()
        section_blocks = _find_blocks_of_type(blocks, "section")
        assert len(section_blocks) >= 1
        # Should mention calendar somewhere
        all_text = " ".join(
            b["text"]["text"] for b in section_blocks if "text" in b
        ).lower()
        assert "calendar" in all_text

    def test_calendar_setup_prompt_enable_button_is_primary(self):
        blocks = calendar_setup_prompt()
        for block in blocks:
            if block.get("type") == "actions":
                for element in block.get("elements", []):
                    if element.get("action_id") == "calendar_enable":
                        assert element.get("style") == "primary"


class TestChannelMapping:
    def test_channel_mapping_has_per_team_dropdowns(self):
        teams = ["Engineering", "Marketing"]
        channels = [
            {"id": "C001", "name": "general"},
            {"id": "C002", "name": "engineering"},
        ]
        blocks = channel_mapping(teams=teams, channels=channels)
        select_ids = _find_select_action_ids(blocks)
        assert "channel_map_engineering" in select_ids
        assert "channel_map_marketing" in select_ids

    def test_channel_mapping_slugifies_team_names(self):
        teams = ["Dev Ops", "Customer Support"]
        channels = [{"id": "C001", "name": "general"}]
        blocks = channel_mapping(teams=teams, channels=channels)
        select_ids = _find_select_action_ids(blocks)
        assert "channel_map_dev_ops" in select_ids
        assert "channel_map_customer_support" in select_ids

    def test_channel_mapping_populates_options(self):
        teams = ["Engineering"]
        channels = [
            {"id": "C001", "name": "general"},
            {"id": "C002", "name": "engineering"},
        ]
        blocks = channel_mapping(teams=teams, channels=channels)
        # Find the select for engineering team
        for block in blocks:
            if block.get("type") == "section":
                accessory = block.get("accessory", {})
                if accessory.get("action_id") == "channel_map_engineering":
                    options = accessory.get("options", [])
                    option_values = [o["value"] for o in options]
                    assert "C001" in option_values
                    assert "C002" in option_values

    def test_channel_mapping_returns_list_of_dicts(self):
        blocks = channel_mapping(teams=["Eng"], channels=[])
        assert isinstance(blocks, list)
        assert all(isinstance(b, dict) for b in blocks)


class TestTeamConfirmation:
    def test_team_confirmation_has_confirm_edit_buttons(self):
        blocks = team_confirmation(teams=["Engineering", "Marketing"])
        action_ids = _find_action_ids(blocks)
        assert "teams_confirm" in action_ids
        assert "teams_edit" in action_ids

    def test_team_confirmation_lists_teams(self):
        teams = ["Engineering", "Marketing", "Sales"]
        blocks = team_confirmation(teams=teams)
        all_text = " ".join(
            block["text"]["text"]
            for block in _find_blocks_of_type(blocks, "section")
            if "text" in block
        )
        for team in teams:
            assert team in all_text

    def test_team_confirmation_confirm_button_is_primary(self):
        blocks = team_confirmation(teams=["Eng"])
        for block in blocks:
            if block.get("type") == "actions":
                for element in block.get("elements", []):
                    if element.get("action_id") == "teams_confirm":
                        assert element.get("style") == "primary"

    def test_team_confirmation_returns_list_of_dicts(self):
        blocks = team_confirmation(teams=[])
        assert isinstance(blocks, list)
        assert all(isinstance(b, dict) for b in blocks)


class TestRelinkCalendar:
    def test_relink_calendar_shows_current_email(self):
        blocks = relink_calendar(current_email="admin@example.com")
        all_text = " ".join(
            block["text"]["text"]
            for block in _find_blocks_of_type(blocks, "section")
            if "text" in block
        )
        assert "admin@example.com" in all_text

    def test_relink_calendar_has_relink_cancel_buttons(self):
        blocks = relink_calendar(current_email="admin@example.com")
        action_ids = _find_action_ids(blocks)
        assert "calendar_relink" in action_ids
        assert "calendar_cancel" in action_ids

    def test_relink_calendar_relink_button_is_primary(self):
        blocks = relink_calendar(current_email="admin@example.com")
        for block in blocks:
            if block.get("type") == "actions":
                for element in block.get("elements", []):
                    if element.get("action_id") == "calendar_relink":
                        assert element.get("style") == "primary"

    def test_relink_calendar_returns_list_of_dicts(self):
        blocks = relink_calendar(current_email="test@example.com")
        assert isinstance(blocks, list)
        assert all(isinstance(b, dict) for b in blocks)


class TestAllBuildersReturnValidBlockKit:
    """Verify every builder emits structurally valid Block Kit blocks."""

    VALID_TYPES = {"section", "actions", "divider", "header", "context", "input"}

    def _assert_valid(self, blocks: list[dict]) -> None:
        assert isinstance(blocks, list), "blocks must be a list"
        assert len(blocks) > 0, "blocks must not be empty"
        for block in blocks:
            assert isinstance(block, dict), "each block must be a dict"
            assert "type" in block, f"block missing 'type': {block}"
            assert block["type"] in self.VALID_TYPES, (
                f"unknown block type '{block['type']}'"
            )
            if block["type"] == "section":
                assert "text" in block, "section block must have 'text'"
                assert block["text"]["type"] in (
                    "mrkdwn",
                    "plain_text",
                ), "section text type must be mrkdwn or plain_text"
            if block["type"] == "actions":
                assert "elements" in block, "actions block must have 'elements'"
                for el in block["elements"]:
                    assert "type" in el, "element missing 'type'"
                    assert "action_id" in el, "element missing 'action_id'"

    def test_calendar_confirmation_is_valid(self):
        blocks = calendar_confirmation(
            title="Sync", date="2025-01-01", time="9:00 AM", attendees=["a@b.com"]
        )
        self._assert_valid(blocks)

    def test_calendar_setup_prompt_is_valid(self):
        self._assert_valid(calendar_setup_prompt())

    def test_channel_mapping_is_valid(self):
        blocks = channel_mapping(
            teams=["Eng"],
            channels=[{"id": "C1", "name": "general"}],
        )
        self._assert_valid(blocks)

    def test_team_confirmation_is_valid(self):
        self._assert_valid(team_confirmation(teams=["Eng", "Mkt"]))

    def test_relink_calendar_is_valid(self):
        self._assert_valid(relink_calendar(current_email="x@y.com"))
