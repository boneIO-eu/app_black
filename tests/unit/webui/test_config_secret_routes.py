"""The config routes must mask secrets and take the mask back (F-03)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from boneio.core.config.secret_masking import MASK
from boneio.webui.routes import config_core


@pytest.fixture
def config_state(tmp_path):
    """Point the config routes at a throwaway config with a real password."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("web:\n  port: 8090\n", encoding="utf-8")

    stored = {
        "mqtt": {"host": "localhost", "username": "boneio", "password": "boneio123"},
        "web": {"port": 8090},
    }

    state = MagicMock()
    state.yaml_config_file = str(config_file)
    state.manager.config_helper.get_config.return_value = stored
    config_core.set_app_state(state)

    config_core._config_cache["data"] = stored
    config_core._config_cache["mtime"] = float("inf")  # always considered fresh
    yield stored
    config_core._config_cache["data"] = None
    config_core._config_cache["mtime"] = 0


@pytest.mark.asyncio
async def test_get_config_masks_the_mqtt_password(config_state):
    """The pentest read this value straight out of the response."""
    body = await config_core.get_parsed_config()
    assert body["config"]["mqtt"]["password"] == MASK


@pytest.mark.asyncio
async def test_get_config_leaves_the_cache_intact(config_state):
    """The cache is shared with the rest of the process, which needs the real
    value — masking it in place would lose it."""
    await config_core.get_parsed_config()
    assert config_core._config_cache["data"]["mqtt"]["password"] == "boneio123"
    assert config_state["mqtt"]["password"] == "boneio123"


@pytest.mark.asyncio
async def test_get_config_keeps_non_secrets(config_state):
    body = await config_core.get_parsed_config()
    assert body["config"]["mqtt"]["host"] == "localhost"
    assert body["config"]["mqtt"]["username"] == "boneio"
