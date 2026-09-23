"""Saving the mqtt section adopts new credentials instead of asking for a restart.

The broker credentials are read once, when the MQTT client is built, and the
whole section was marked restart-required. So typing a new password into the
MQTT form wrote it to the file and changed nothing until the service was
restarted — the other half of "changing the mosquitto password does not work".
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from boneio.webui.routes import config_core


@pytest.fixture
def device(tmp_path):
    """The config routes, pointed at a throwaway config.yaml."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "mqtt:\n"
        "  host: localhost\n"
        "  username: boneio\n"
        "  password: boneio123\n"
        "  topic_prefix: boneio\n",
        encoding="utf-8",
    )

    stored = {
        "mqtt": {
            "host": "localhost",
            "username": "boneio",
            "password": "boneio123",
            "topic_prefix": "boneio",
        }
    }

    state = MagicMock()
    state.yaml_config_file = str(config_file)
    state.manager.reload_config = AsyncMock(return_value={"status": "success"})
    state.manager.config_helper.restart_required_sections = ["mqtt"]
    config_core.set_app_state(state)

    config_core._config_cache["data"] = stored
    config_core._config_cache["mtime"] = float("inf")
    yield state
    config_core._config_cache["data"] = None
    config_core._config_cache["mtime"] = 0


def _section(**changes) -> dict:
    """The mqtt section as the panel posts it back, with changes applied."""
    section = {
        "host": "localhost",
        "username": "boneio",
        "password": "boneio123",
        "topic_prefix": "boneio",
    }
    section.update(changes)
    return section


@pytest.mark.asyncio
async def test_a_new_password_is_adopted_without_a_restart(device):
    result = await config_core.update_section_content(
        "mqtt", _section(password="nowe-haslo")
    )

    assert result["mqtt"] == "reconnecting"
    assert not result.get("restart_required")
    device.manager.reload_config.assert_awaited_once_with(reload_sections=["mqtt"])


@pytest.mark.asyncio
async def test_moving_to_another_broker_is_adopted_too(device):
    result = await config_core.update_section_content(
        "mqtt", _section(host="192.168.1.50", port=8883)
    )

    assert result["mqtt"] == "reconnecting"
    assert not result.get("restart_required")


@pytest.mark.asyncio
async def test_the_topic_prefix_still_takes_a_restart(device):
    """It is read into entity names and subscriptions all over the
    application while it starts; a reconnect does not revisit any of that."""
    result = await config_core.update_section_content(
        "mqtt", _section(topic_prefix="dom")
    )

    assert result["restart_required"] is True
    device.manager.reload_config.assert_not_awaited()


@pytest.mark.asyncio
async def test_changing_both_reconnects_and_still_asks_for_the_restart(device):
    result = await config_core.update_section_content(
        "mqtt", _section(password="nowe-haslo", topic_prefix="dom")
    )

    assert result["mqtt"] == "reconnecting"
    assert result["restart_required"] is True


@pytest.mark.asyncio
async def test_saving_nothing_new_leaves_the_connection_alone(device):
    """Saving the form untouched must not drop a healthy broker connection."""
    result = await config_core.update_section_content("mqtt", _section())

    assert "mqtt" not in result
    device.manager.reload_config.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_failed_reconnect_does_not_fail_the_save(device):
    """The file is written either way. Reporting a save that did happen as
    broken is how a panel teaches people not to trust it."""
    device.manager.reload_config.side_effect = RuntimeError("bus is gone")

    result = await config_core.update_section_content(
        "mqtt", _section(password="nowe-haslo")
    )

    assert result["status"] == "success"
    assert result["mqtt"] == "failed"
    # Nothing was adopted, so the restart is back on the table.
    assert result["restart_required"] is True
