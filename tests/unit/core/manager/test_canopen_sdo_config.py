"""A configuration pushed over CAN has to load before it replaces config.yaml.

Anything on the bus can write SDO 0x2001 and trigger 0x2002. The payload was
written over config.yaml as it came — no check, no copy — so a garbled or
hostile frame left a controller that no longer booted, with nothing to go
back to.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from boneio.core.manager import canopen
from boneio.core.manager.canopen import CANopenManager, _store_sdo_config

OLD = "boneio:\n  name: Old\n"
NEW = "boneio:\n  name: New\n"


@pytest.fixture
def config(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(OLD, encoding="utf-8")
    return path


def _files(directory) -> list[str]:
    return sorted(p.name for p in directory.iterdir())


def test_a_valid_configuration_replaces_the_file(config):
    assert _store_sdo_config(str(config), NEW) is True

    assert config.read_text(encoding="utf-8") == NEW


def test_the_replaced_file_is_kept(config):
    _store_sdo_config(str(config), NEW)

    backup = config.with_name("config.yaml.sdo.bak")
    assert backup.read_text(encoding="utf-8") == OLD


def test_nothing_of_the_check_is_left_behind(config):
    """The validation writes a cache next to the file it reads."""
    _store_sdo_config(str(config), NEW)

    assert _files(config.parent) == ["config.yaml", "config.yaml.sdo.bak"]


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param("boneio: [\n", id="not-yaml"),
        pytest.param(OLD + "virtual_switch: [1, 2]\n", id="fails-validation"),
        pytest.param("", id="empty"),
        pytest.param(OLD + "output: !include missing.yaml\n", id="missing-include"),
    ],
)
def test_a_configuration_that_would_not_load_is_refused(config, payload):
    assert _store_sdo_config(str(config), payload) is False

    assert config.read_text(encoding="utf-8") == OLD
    assert _files(config.parent) == ["config.yaml"]


def test_includes_resolve_beside_the_real_file(config):
    """Checked where it will live, so !include finds the device's own files."""
    config.with_name("switches.yaml").write_text("- name: Away\n", encoding="utf-8")
    payload = NEW + "virtual_switch: !include switches.yaml\n"

    assert _store_sdo_config(str(config), payload) is True


async def _slave(config) -> CANopenManager:
    manager = MagicMock()
    manager._config_file_path = str(config)
    manager.reload_config = AsyncMock()
    return CANopenManager(manager=manager, config={"mode": "slave"})


async def _settle(can: CANopenManager) -> None:
    for _ in range(200):
        if not can._background_tasks:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("the SDO config task never finished")


async def test_a_pushed_configuration_is_loaded(config):
    can = await _slave(config)

    can._on_sdo_config_write(NEW)
    await _settle(can)

    assert config.read_text(encoding="utf-8") == NEW
    can._manager.reload_config.assert_awaited_once()


async def test_a_refused_configuration_is_not_loaded(config):
    can = await _slave(config)

    can._on_sdo_config_write("boneio: [\n")
    await _settle(can)

    assert config.read_text(encoding="utf-8") == OLD
    can._manager.reload_config.assert_not_awaited()


async def test_the_check_does_not_run_on_the_event_loop(config, monkeypatch):
    """It is a full validation: a couple of seconds on a BeagleBone."""
    loop_thread = []

    def store(path, payload):
        import threading

        loop_thread.append(threading.current_thread() is threading.main_thread())
        return False

    monkeypatch.setattr(canopen, "_store_sdo_config", store)
    can = await _slave(config)

    can._on_sdo_config_write(NEW)
    await _settle(can)

    assert loop_thread == [False]


async def test_a_master_ignores_a_push(config):
    can = await _slave(config)
    can._mode = "master"

    can._on_sdo_config_write(NEW)

    assert not can._background_tasks
    assert config.read_text(encoding="utf-8") == OLD
