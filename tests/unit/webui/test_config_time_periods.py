"""A duration reads and writes as the string config.yaml carries ("60s").

The parsed config holds durations as TimePeriod objects. Encoded as they were,
they reached a client as a dict of the object's internals, and a client that
posted that back wrote something the loader refuses at the next start.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from boneio.core.utils import TimePeriod
from boneio.webui.routes import config_core

AS_JSON = {  # what GET /api/config used to serve for TimePeriod(seconds=60)
    "days": None, "hours": None, "minutes": None, "seconds": 60,
    "milliseconds": None, "microseconds": None,
    "_timedelta": "0:01:00", "_total_in_seconds": 60.0,
}


@pytest.fixture
def device(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("oled:\n  screensaver_timeout: 60s\n", encoding="utf-8")

    state = MagicMock()
    state.yaml_config_file = str(config_file)
    state.manager.reload_config = AsyncMock(return_value={"status": "success"})
    state.manager.config_helper.restart_required_sections = []
    config_core.set_app_state(state)

    config_core._config_cache["data"] = {
        "boneio": {"version": 1.1, "device_type": "24x16A"},
        "oled": {"enabled": True, "screensaver_timeout": TimePeriod(seconds=60)},
        "lm75": [{"id": "t", "address": 72, "update_interval": TimePeriod(milliseconds=1500)}],
    }
    config_core._config_cache["mtime"] = float("inf")
    yield state
    config_core._config_cache["data"] = None
    config_core._config_cache["mtime"] = 0


@pytest.mark.asyncio
async def test_get_serves_the_string_the_file_carries(device):
    config = (await config_core.get_parsed_config())["config"]
    assert config["oled"]["screensaver_timeout"] == "60s"
    assert config["lm75"][0]["update_interval"] == "1500ms"


@pytest.mark.asyncio
async def test_get_leaves_the_cache_holding_time_periods(device):
    await config_core.get_parsed_config()
    assert isinstance(config_core._config_cache["data"]["oled"]["screensaver_timeout"], TimePeriod)


@pytest.mark.asyncio
async def test_what_get_serves_validates_unchanged(device):
    config = (await config_core.get_parsed_config())["config"]
    for section in ("oled", "lm75"):
        result = await config_core.validate_section_content(section, config[section])
        assert result == {"valid": True, "errors": []}, section


@pytest.mark.asyncio
async def test_a_posted_time_period_dict_validates(device):
    result = await config_core.validate_section_content(
        "oled", {"enabled": True, "screensaver_timeout": AS_JSON}
    )
    assert result == {"valid": True, "errors": []}


@pytest.mark.asyncio
async def test_a_posted_time_period_dict_is_saved_as_its_string(device):
    await config_core.update_section_content(
        "oled", {"enabled": True, "screensaver_timeout": AS_JSON}
    )
    text = open(device.yaml_config_file, encoding="utf-8").read()
    assert "screensaver_timeout: 60s" in text
    assert "_total_in_seconds" not in text
