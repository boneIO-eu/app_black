"""Turning cloud registration on without restarting the controller.

Enabling it used to write a line to config.yaml and ask for a reboot — on a
device whose entire purpose is to keep running. Everything the change needs
was already there: starting registration is starting the loop that registers
the name, fetches the certificate, swaps the compose template and recreates
Caddy.
"""

from __future__ import annotations

import asyncio

import pytest

from boneio.webui.routes.config_core import (
    _cloud_enabled,
    _web_changed_apart_from_cloud,
)


class _Helper:
    def __init__(self, serial="blk123", enabled=False):
        self.serial_number = serial
        self._cloud_registration = enabled
        self._cloud_reg = None


class _Registration:
    instances: list["_Registration"] = []

    def __init__(self, serial_number, local_ip):
        self.serial_number = serial_number
        self.local_ip = local_ip
        self.started = False
        self.stopped = False
        self.restored = False
        _Registration.instances.append(self)

    async def start(self):
        self.started = True

    async def stop(self):
        self.stopped = True

    async def _restore_local_config(self):
        self.restored = True


@pytest.fixture
def cloud(monkeypatch):
    from boneio.core.cloud import registration as module

    _Registration.instances.clear()
    monkeypatch.setattr(module, "CloudRegistration", _Registration)
    # Patched where registration looks it up: it imports the name, so
    # replacing it on the monitor module would not be seen.
    monkeypatch.setattr(module, "get_network_info", lambda: {"ip": "192.168.1.9"})
    return module


# ------------------------------------------------------------- reading intent


@pytest.mark.parametrize(
    "section,expected",
    [
        ({"cloud": {"enabled": True}}, True),
        ({"cloud": {"enabled": False}}, False),
        ({"cloud": {}}, False),
        ({"port": 8090}, False),
        (None, False),
        ("nonsense", False),
    ],
)
def test_reading_the_toggle(section, expected):
    assert _cloud_enabled(section) is expected


def test_a_cloud_only_change_is_recognised():
    before = {"port": 8090, "cloud": {"enabled": False}}
    after = {"port": 8090, "cloud": {"enabled": True}}
    assert _web_changed_apart_from_cloud(before, after) is False


def test_another_setting_alongside_it_still_needs_a_restart():
    """The port is read once, when the server binds."""
    before = {"port": 8090, "cloud": {"enabled": False}}
    after = {"port": 9000, "cloud": {"enabled": True}}
    assert _web_changed_apart_from_cloud(before, after) is True


# ------------------------------------------------------------ starting it


def test_enabling_starts_registration(cloud):
    helper = _Helper()
    assert asyncio.run(cloud.set_enabled(helper, True)) == "started"
    assert helper._cloud_reg is _Registration.instances[0]
    assert _Registration.instances[0].started is True
    assert helper._cloud_registration is True


def test_the_address_is_read_from_the_system_when_not_given(cloud):
    helper = _Helper()
    asyncio.run(cloud.set_enabled(helper, True))
    assert _Registration.instances[0].local_ip == "192.168.1.9"


def test_enabling_twice_starts_one_service(cloud):
    helper = _Helper()
    asyncio.run(cloud.set_enabled(helper, True))
    assert asyncio.run(cloud.set_enabled(helper, True)) == "unchanged"
    assert len(_Registration.instances) == 1


def test_without_an_address_it_defers_rather_than_claiming_success(cloud, monkeypatch):
    """Reporting "started" for a service that did not start is the one answer
    that leaves somebody waiting for a certificate that is not coming."""
    monkeypatch.setattr(cloud, "get_network_info", lambda: {"ip": ""})
    helper = _Helper()
    assert asyncio.run(cloud.set_enabled(helper, True)) == "unavailable"
    assert helper._cloud_registration is True, "the setting is still saved"
    assert _Registration.instances == []


# ------------------------------------------------------------ stopping it


def test_disabling_stops_and_restores_the_local_template(cloud):
    """Left as it was, Caddy keeps serving a certificate for a name nobody is
    renewing any more."""
    helper = _Helper()
    asyncio.run(cloud.set_enabled(helper, True))
    started = _Registration.instances[0]

    assert asyncio.run(cloud.set_enabled(helper, False)) == "stopped"
    assert started.stopped is True
    assert started.restored is True
    assert helper._cloud_reg is None
    assert helper._cloud_registration is False


def test_disabling_what_was_never_running_is_not_an_error(cloud):
    helper = _Helper()
    assert asyncio.run(cloud.set_enabled(helper, False)) == "unchanged"


def test_a_failure_to_stop_does_not_leave_it_attached(cloud):
    """Whatever went wrong, the device is no longer registering — saying it
    still is would be worse than the failure."""
    helper = _Helper()
    asyncio.run(cloud.set_enabled(helper, True))

    async def boom():
        raise RuntimeError("container daemon is down")

    _Registration.instances[0].stop = boom
    assert asyncio.run(cloud.set_enabled(helper, False)) == "stopped"
    assert helper._cloud_reg is None
