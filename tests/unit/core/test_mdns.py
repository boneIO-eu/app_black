"""What the controller announces over mDNS, and that the announcement is kept up."""

from __future__ import annotations

import asyncio

import pytest

from boneio.core.config.config_helper import ConfigHelper
from boneio.core.net import mdns


def _helper(**kwargs) -> ConfigHelper:
    return ConfigHelper(
        name="garaż 1",
        version="1.1",
        web_port=8090,
        is_web_active=True,
        network_info={"ip": "192.168.1.10", "mac": "aa:bb:cc:8c:7d:f0"},
        **kwargs,
    )


def test_announces_the_panel_under_the_serial():
    assert mdns.publish_command(_helper()) == [
        "avahi-publish",
        "--service",
        "blk8c7df0",
        "_boneio._tcp",
        "8090",
        "serial=blk8c7df0",
        "name=garaż 1",
        "device_type=boneIO Black",
        "board=1.1",
        "proto=http",
    ]


def test_behind_the_proxy_announces_the_proxy_port():
    command = mdns.publish_command(_helper(expose="proxy"))
    assert command[4] == "8443"
    assert command[-1] == "proto=https"


def test_nothing_to_announce_without_a_panel():
    assert mdns.publish_command(ConfigHelper(name="x", version="1")) is None


class FakeProc:
    def __init__(self, argv, log):
        self.argv = argv
        self.returncode = None
        self._log = log

    def terminate(self):
        self._log.append(("terminate", self.argv[4]))
        self.returncode = -15

    async def wait(self):
        return self.returncode


async def test_restarted_on_change_and_on_exit_and_stopped_on_cancel(monkeypatch):
    helper = _helper()
    log: list[tuple] = []
    procs: list[FakeProc] = []

    async def spawn(*argv, **_):
        log.append(("start", argv[4]))
        procs.append(FakeProc(argv, log))
        return procs[-1]

    # Each check moves the controller on one step; the last one ends the loop.
    steps = iter(
        [
            lambda: None,  # unchanged: nothing happens
            lambda: setattr(helper, "_web_port", 8091),  # new port: restart
            lambda: setattr(procs[-1], "returncode", 1),  # avahi went away: restart
        ]
    )

    async def tick(_):
        try:
            next(steps)()
        except StopIteration:
            raise asyncio.CancelledError from None

    monkeypatch.setattr(mdns.shutil, "which", lambda _: "/usr/bin/avahi-publish")
    monkeypatch.setattr(mdns.asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setattr(mdns.asyncio, "sleep", tick)

    with pytest.raises(asyncio.CancelledError):
        await mdns.advertise(helper)

    assert log == [
        ("start", "8090"),
        ("terminate", "8090"),
        ("start", "8091"),
        ("start", "8091"),
        ("terminate", "8091"),
    ]


async def test_quiet_without_avahi(monkeypatch):
    monkeypatch.setattr(mdns.shutil, "which", lambda _: None)
    await mdns.advertise(_helper())
