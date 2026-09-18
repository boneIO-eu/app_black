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
    """Docker removed, or not started yet. Binding nothing would be worse than
    binding the loopback, and the log says how to reach it."""
    bridges([])
    binds = binds_for(Exposure.PROXY, 8090)
    assert binds == ["127.0.0.1:8090"]
    assert "ssh -L" in caplog.text


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
