"""Which addresses the panel's own port answers on.

The pentest finding is that the management interface is served in the clear on
0.0.0.0, and the recommendation is to limit it to 127.0.0.1. Taken literally
that makes the device unreachable: Caddy runs in a container and arrives on the
Docker bridge, not the loopback, so the proxy would get a refused connection
and 8443 would answer 502. These tests are mostly about that.
"""

from __future__ import annotations

import pytest

from boneio.webui import bind
from boneio.webui.bind import Exposure, binds_for


@pytest.fixture
def bridges(monkeypatch):
    def use(addresses):
        monkeypatch.setattr(bind, "docker_bridge_addresses", lambda: list(addresses))

    return use


def test_all_is_what_it_has_always_been(bridges):
    bridges(["172.17.0.1"])
    assert binds_for(Exposure.ALL, 8090) == ["0.0.0.0:8090"]


def test_proxy_keeps_the_loopback(bridges):
    """An SSH tunnel is the way in when the proxy is not working."""
    bridges(["172.17.0.1"])
    assert "127.0.0.1:8090" in binds_for(Exposure.PROXY, 8090)


def test_proxy_keeps_the_bridge_the_proxy_arrives_on(bridges):
    """Without this the change takes the device off the network completely.

    host.docker.internal resolves to the host end of the default bridge —
    172.17.0.1 on a boneIO Black — so a panel bound to the loopback alone
    answers Caddy with a refused connection.
    """
    bridges(["172.17.0.1"])
    assert "172.17.0.1:8090" in binds_for(Exposure.PROXY, 8090)


def test_proxy_does_not_answer_on_the_lan(bridges):
    bridges(["172.17.0.1", "172.18.0.1"])
    assert "0.0.0.0:8090" not in binds_for(Exposure.PROXY, 8090)


def test_every_bridge_is_covered(bridges):
    """A compose project gets its own bridge, and which one the proxy uses is
    Docker's business, not ours."""
    bridges(["172.17.0.1", "172.18.0.1", "172.20.0.1"])
    binds = binds_for(Exposure.PROXY, 8090)
    assert binds == [
        "127.0.0.1:8090",
        "172.17.0.1:8090",
        "172.18.0.1:8090",
        "172.20.0.1:8090",
    ]


def test_no_bridge_still_produces_a_usable_bind(bridges, caplog):
    """Docker removed for good. Binding nothing would be worse than binding
    the loopback, and the log says how to reach it."""
    bridges([])
    binds = binds_for(Exposure.PROXY, 8090, wait=0)
    assert binds == ["127.0.0.1:8090"]
    assert "ssh -L" in caplog.text


def test_a_bridge_that_arrives_late_is_still_used(monkeypatch):
    """The cold-boot case.

    boneIO does not start after docker.service — it drives relays, and waiting
    for a container runtime first is the wrong trade. So on a cold boot the
    panel can be ready before dockerd has made its bridge, and binding then
    would miss the only address the proxy can reach us on.
    """
    answers = [[], [], ["172.17.0.1"]]
    monkeypatch.setattr(bind, "docker_bridge_addresses", lambda: answers.pop(0) if answers else [])
    monkeypatch.setattr(bind, "_BRIDGE_POLL_SECONDS", 0)

    assert binds_for(Exposure.PROXY, 8090, wait=5) == [
        "127.0.0.1:8090",
        "172.17.0.1:8090",
    ]


def test_waiting_does_not_delay_the_usual_case(monkeypatch):
    """A device that has been up for a while already has its bridge."""
    calls = []
    monkeypatch.setattr(
        bind, "docker_bridge_addresses", lambda: calls.append(1) or ["172.17.0.1"]
    )
    binds_for(Exposure.PROXY, 8090, wait=60)
    assert len(calls) == 1, "polled again when the answer was there the first time"


def test_all_never_waits_for_docker(monkeypatch):
    """Nothing about serving on every interface needs a bridge."""
    monkeypatch.setattr(
        bind, "docker_bridge_addresses", lambda: pytest.fail("looked for a bridge")
    )
    assert binds_for(Exposure.ALL, 8090) == ["0.0.0.0:8090"]


def test_the_port_is_carried_through(bridges):
    bridges(["172.17.0.1"])
    assert binds_for(Exposure.PROXY, 9000) == ["127.0.0.1:9000", "172.17.0.1:9000"]


def test_an_unknown_value_is_treated_as_the_old_behaviour(bridges):
    """A typo in config.yaml must not silently take the panel off the network."""
    bridges(["172.17.0.1"])
    assert binds_for("lopback", 8090) == ["0.0.0.0:8090"]


def test_the_default_is_still_every_interface():
    """Opt-in until it has been through a release on hardware: getting this
    wrong means a controller in a cabinet answering on no port at all."""
    import inspect

    from boneio.webui.web_server import WebServer

    assert inspect.signature(WebServer).parameters["expose"].default == Exposure.ALL


def test_bridge_discovery_survives_a_missing_psutil(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("no psutil here")

    monkeypatch.setattr("psutil.net_if_addrs", boom)
    assert bind.docker_bridge_addresses() == []


# ------------------------------------------------------- the USB gadget link


@pytest.fixture
def usb(monkeypatch):
    def use(addresses):
        monkeypatch.setattr(bind, "usb_gadget_addresses", lambda: list(addresses))

    return use


def test_proxy_keeps_the_usb_cable(bridges, usb):
    """A cable is not the network.

    Somebody who has plugged one in already has physical access, and this is
    how the factory station reaches a board with no other address and how a
    controller with broken Ethernet is recovered. Closing it takes away the way
    back and protects nothing.
    """
    bridges(["172.17.0.1"])
    usb(["192.168.7.2"])
    assert "192.168.7.2:8090" in binds_for(Exposure.PROXY, 8090)


def test_no_cable_is_not_an_error(bridges, usb):
    """Most controllers have nothing plugged in, most of the time."""
    bridges(["172.17.0.1"])
    usb([])
    assert binds_for(Exposure.PROXY, 8090) == ["127.0.0.1:8090", "172.17.0.1:8090"]


def test_all_does_not_need_the_cable_enumerated(monkeypatch):
    monkeypatch.setattr(
        bind, "usb_gadget_addresses", lambda: pytest.fail("looked for a cable")
    )
    assert binds_for(Exposure.ALL, 8090) == ["0.0.0.0:8090"]


def test_the_gadget_interface_is_matched_by_name(monkeypatch):
    """usb0 and usb1 on a BeagleBone; nothing else should match."""

    class _Addr:
        def __init__(self, address):
            self.family = 2
            self.address = address

    monkeypatch.setattr(
        "psutil.net_if_addrs",
        lambda: {
            "usb0": [_Addr("192.168.7.2")],
            "usb1": [_Addr("192.168.6.2")],
            "eth0": [_Addr("192.168.50.220")],
            "lo": [_Addr("127.0.0.1")],
        },
    )
    assert bind.usb_gadget_addresses() == ["192.168.6.2", "192.168.7.2"]
