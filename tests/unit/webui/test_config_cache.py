"""Tests for in-place config cache update in ConfigHelper and invalidate_config_cache."""

from __future__ import annotations

import sys
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


class TestConfigHelperUpdateConfigSection:
    """ConfigHelper.update_config_section patches _config_cache in-place."""

    def _make_helper(self, cache: dict[str, Any] | None = None) -> object:
        from boneio.core.config.config_helper import ConfigHelper

        helper = ConfigHelper.__new__(ConfigHelper)
        helper._config_cache = cache
        return helper

    def test_updates_existing_section(self) -> None:
        helper = self._make_helper({"event": [{"id": "old"}], "output": []})
        new_events = [{"id": "new1"}, {"id": "new2"}]

        helper.update_config_section("event", new_events)

        assert helper._config_cache["event"] == new_events
        # Other sections remain untouched
        assert helper._config_cache["output"] == []

    def test_adds_new_section(self) -> None:
        helper = self._make_helper({"event": []})

        helper.update_config_section("binary_sensor", [{"pin": "P8_07"}])

        assert helper._config_cache["binary_sensor"] == [{"pin": "P8_07"}]
        assert helper._config_cache["event"] == []

    def test_noop_when_cache_is_none(self) -> None:
        helper = self._make_helper(cache=None)

        # Should not raise
        helper.update_config_section("event", [{"id": "x"}])

        assert helper._config_cache is None


@pytest.fixture()
def _ensure_gpiod_line_mock():
    """Ensure gpiod.line submodule is available for config_core import chain."""
    mock = MagicMock()
    originals: dict[str, object] = {}
    for key in ("gpiod", "gpiod.line"):
        if key not in sys.modules:
            originals[key] = None
            sys.modules[key] = mock
    yield
    for key, val in originals.items():
        if val is None:
            sys.modules.pop(key, None)


class TestInvalidateConfigCacheInPlace:
    """invalidate_config_cache with section+section_data patches ConfigHelper."""

    @pytest.fixture()
    def mock_app_state(self) -> MagicMock:
        state = MagicMock()
        state.manager.config_helper._config_cache = {
            "event": [{"id": "old"}],
            "output": [],
        }
        state.yaml_config_file = "/tmp/test_config.yaml"
        return state

    @pytest.mark.usefixtures("_ensure_gpiod_line_mock")
    def test_patches_config_helper_in_place(self, mock_app_state: MagicMock) -> None:
        import boneio.webui.routes.config_core as config_core_mod  # noqa: F811

        new_events = [{"id": "new"}]

        with (
            patch.object(config_core_mod, "_get_app_state", return_value=mock_app_state),
            patch.object(config_core_mod, "clear_config_cache"),
            patch.object(config_core_mod, "_schedule_debounced_cache_rebuild"),
            patch.object(config_core_mod, "_recompute_config_checksum"),
        ):
            # Pre-populate route cache
            config_core_mod._config_cache["data"] = {"old": True}
            config_core_mod._config_cache["mtime"] = 99

            config_core_mod.invalidate_config_cache(
                section="event", section_data=new_events,
            )

            # Route cache is cleared
            assert config_core_mod._config_cache["data"] is None
            assert config_core_mod._config_cache["mtime"] == 0

            # ConfigHelper is patched in-place
            helper = mock_app_state.manager.config_helper
            helper.update_config_section.assert_called_once_with("event", new_events)

    @pytest.mark.usefixtures("_ensure_gpiod_line_mock")
    def test_no_section_does_not_call_update(self, mock_app_state: MagicMock) -> None:
        import boneio.webui.routes.config_core as config_core_mod  # noqa: F811

        with (
            patch.object(config_core_mod, "_get_app_state", return_value=mock_app_state),
            patch.object(config_core_mod, "clear_config_cache"),
            patch.object(config_core_mod, "_schedule_debounced_cache_rebuild"),
            patch.object(config_core_mod, "_recompute_config_checksum"),
        ):
            config_core_mod.invalidate_config_cache()

            helper = mock_app_state.manager.config_helper
            helper.update_config_section.assert_not_called()
