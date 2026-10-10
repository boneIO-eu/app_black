"""The factory reset dialog starts from what the controller is now.

Reported on 20 September: a reset offered board 0.8 and no controller type,
whatever the device was, so a 1.1 32x10 was one careless click away from a
0.8 configuration.
"""

from __future__ import annotations

import asyncio

import pytest

from boneio.webui.routes import update


@pytest.fixture
def config(monkeypatch):
    holder = {"boneio": {}}
    monkeypatch.setattr(update, "load_yaml_file", lambda path: holder)
    return holder["boneio"]


@pytest.mark.parametrize(
    "named, expected",
    [("32x10A", "32x10"), ("32x10a", "32x10"), ("cover_mix", "cover_mix"), ("24x16", "24x16"), (None, None)],
)
def test_the_current_type_is_offered(config, named, expected):
    if named:
        config["device_type"] = named
    assert asyncio.run(update.get_device_types())["current"] == expected


def test_the_current_board_version_is_offered(config):
    config["version"] = "1.1"
    assert asyncio.run(update.get_hardware_versions())["current"] == "1.1"


def test_an_unreadable_config_offers_nothing(monkeypatch):
    def broken(path):
        raise OSError("no config")

    monkeypatch.setattr(update, "load_yaml_file", broken)
    assert asyncio.run(update.get_device_types())["current"] is None
    assert asyncio.run(update.get_hardware_versions())["current"] is None
