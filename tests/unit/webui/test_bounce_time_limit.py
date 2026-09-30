"""Bounce time past 1000 ms: refused when a save sets it, tolerated when stored.

The panel caps the field at 1000 ms, and the save route refuses a longer
value the panel did not stop (an API call, an older frontend). A config that
already carries one keeps loading — with a warning — and keeps saving, since
the section goes back whole every time another input in it is edited.
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from boneio.hardware.gpio.input.base import warn_if_bounce_too_long
from boneio.webui.input_validation import (
    bounce_time_ms,
    has_long_bounce_time,
    validate_bounce_times,
)
from boneio.webui.routes import config_core


class TestBounceTimeMs:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (120, 120),
            ("120ms", 120),
            ("2s", 2000),
            ({"_total_in_seconds": 1.5, "milliseconds": None}, 1500),
            ({"milliseconds": 80}, 80),
            (None, None),
            ("", None),
        ],
    )
    def test_reads_every_shape_a_save_carries(self, value, expected):
        assert bounce_time_ms(value) == expected


class TestValidateBounceTimes:
    def test_a_new_long_value_is_refused(self):
        errors = validate_bounce_times(
            [{"boneio_input": "in_01", "bounce_time": 1500}],
            [{"boneio_input": "in_01", "bounce_time": "120ms"}],
        )
        assert len(errors) == 1
        assert "in_01" in errors[0] and "1500ms" in errors[0]

    def test_the_limit_itself_passes(self):
        assert validate_bounce_times([{"boneio_input": "in_01", "bounce_time": 1000}], []) == []

    def test_a_long_value_already_stored_for_that_input_passes(self):
        assert validate_bounce_times(
            [{"boneio_input": "IN_01", "bounce_time": 2000}],
            [{"boneio_input": "in_01", "bounce_time": "2s"}],
        ) == []

    def test_a_stored_long_value_moved_to_another_input_is_refused(self):
        errors = validate_bounce_times(
            [{"boneio_input": "in_02", "bounce_time": 2000}],
            [{"boneio_input": "in_01", "bounce_time": "2s"}],
        )
        assert len(errors) == 1

    def test_nothing_is_refused_without_a_baseline(self):
        assert validate_bounce_times([{"boneio_input": "in_01", "bounce_time": 5000}], None) == []

    def test_the_cheap_check_only_fires_past_the_limit(self):
        assert not has_long_bounce_time([{"bounce_time": 1000}, {"bounce_time": "30ms"}, {}])
        assert has_long_bounce_time([{"bounce_time": "1001ms"}])


class TestStartupWarning:
    def test_a_long_bounce_time_is_logged(self, caplog):
        with caplog.at_level(logging.WARNING):
            warn_if_bounce_too_long(1.5, "Hall", "P8_10")
        assert "1500ms" in caplog.text and "Hall" in caplog.text

    def test_the_limit_itself_is_quiet(self, caplog):
        with caplog.at_level(logging.WARNING):
            warn_if_bounce_too_long(1.0, "Hall", "P8_10")
        assert caplog.text == ""


@pytest.fixture
def device(tmp_path):
    """The config routes, with one binary sensor stored at 2 s."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "binary_sensor:\n"
        "  - boneio_input: in_01\n"
        "    bounce_time: 2s\n",
        encoding="utf-8",
    )
    stored = [{"boneio_input": "in_01", "bounce_time": "2s"}]

    state = MagicMock()
    state.yaml_config_file = str(config_file)
    state.manager.reload_config = AsyncMock(return_value={"status": "success"})
    state.manager.config_helper.restart_required_sections = []
    state.manager.config_helper.get_section.return_value = stored
    config_core.set_app_state(state)

    config_core._config_cache["data"] = {"binary_sensor": stored}
    config_core._config_cache["mtime"] = float("inf")
    yield state
    config_core._config_cache["data"] = None
    config_core._config_cache["mtime"] = 0


@pytest.mark.asyncio
async def test_the_route_refuses_a_new_long_bounce_time(device):
    with pytest.raises(HTTPException) as err:
        await config_core.update_section_content(
            "binary_sensor",
            [
                {"boneio_input": "in_01", "bounce_time": "2s"},
                {"boneio_input": "in_02", "bounce_time": 1500},
            ],
        )
    assert err.value.status_code == 422
    assert any("in_02" in e for e in err.value.detail["errors"])
    assert not any("in_01" in e for e in err.value.detail["errors"])


@pytest.mark.asyncio
async def test_the_route_saves_a_section_whose_long_value_was_already_there(device):
    await config_core.update_section_content(
        "binary_sensor",
        [
            {"boneio_input": "in_01", "bounce_time": "2s"},
            {"boneio_input": "in_02", "bounce_time": 120},
        ],
    )
    assert "in_02" in Path(device.yaml_config_file).read_text(encoding="utf-8")
