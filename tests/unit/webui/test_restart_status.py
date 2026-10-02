"""The restart status route reports the flag the config routes set.

Settings asks this route on open, so a restart still pending from an earlier
save brings the banner back instead of being forgotten.
"""

from __future__ import annotations

from boneio.core.config.config_helper import ConfigHelper
from boneio.webui.routes import system


async def test_nothing_saved_needs_no_restart(monkeypatch):
    helper = ConfigHelper()
    monkeypatch.setattr(system, "_config_helper_getter", lambda: helper)

    assert await system.get_restart_status() == {"restart_required": False}


async def test_a_section_needing_a_restart_is_reported(monkeypatch):
    helper = ConfigHelper()
    helper.set_restart_required("mqtt")
    monkeypatch.setattr(system, "_config_helper_getter", lambda: helper)

    assert await system.get_restart_status() == {"restart_required": True}


async def test_no_config_helper_yet_reports_no_restart(monkeypatch):
    monkeypatch.setattr(system, "_config_helper_getter", None)

    assert await system.get_restart_status() == {"restart_required": False}


async def test_a_failing_getter_reports_no_restart(monkeypatch):
    def getter():
        raise AttributeError("config_helper")

    monkeypatch.setattr(system, "_config_helper_getter", getter)

    assert await system.get_restart_status() == {"restart_required": False}
