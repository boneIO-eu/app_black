"""Which broker account the application actually uses.

The panel warns on the row boneIO signs in with, because changing that
password without updating the configuration stops the device reporting. That
warning is a claim about this device, and the endpoint behind it was not
checking: it opened `~/.boneio/mqtt.yaml`, a path that exists on no device,
looked for a `mqtt:` key inside a file whose contents *are* the mqtt section,
and fell through both failures to a hard-coded "boneio".

So the warning sat on the boneio row always — right by luck on a default
device, wrong for anyone who had changed the username, and wrong for everyone
whose broker is in Home Assistant, where none of these accounts is boneIO's.
"""

from __future__ import annotations

import pytest

from boneio.webui.routes import system as system_route
from boneio.webui.routes import update as update_route


class _Helper:
    def __init__(self, config):
        self._config = config

    def get_config(self, force_reload: bool = False):
        return self._config


@pytest.fixture
def configured(monkeypatch):
    """Point the route at a configuration of the caller's choosing."""

    def use(config):
        monkeypatch.setattr(
            system_route, "_config_helper_getter", lambda: _Helper(config), raising=False
        )

    return use


async def test_reports_the_configured_username(configured):
    """Not a default — the name that is actually in config.yaml."""
    configured({"mqtt": {"host": "localhost", "username": "pawel"}})
    body = await update_route.get_mqtt_username()

    assert body["username"] == "pawel"
    assert body["known"] is True


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "::1", "LOCALHOST", ""])
async def test_a_broker_on_this_device_is_recognised(configured, host):
    configured({"mqtt": {"host": host, "username": "boneio"}})
    assert (await update_route.get_mqtt_username())["uses_local_broker"] is True


async def test_a_broker_in_home_assistant_is_not_ours(configured):
    """The case that makes the warning wrong for most people.

    With boneIO pointed at someone else's broker, none of the accounts on this
    controller is the one it signs in with.
    """
    configured({"mqtt": {"host": "192.168.1.50", "username": "boneio"}})
    body = await update_route.get_mqtt_username()

    assert body["uses_local_broker"] is False
    assert body["host"] == "192.168.1.50"


async def test_the_same_username_on_a_remote_broker_is_still_not_ours(configured):
    """`boneio` on Home Assistant's broker is a different account entirely.

    Matching on the name alone would put the warning back on the wrong row.
    """
    configured({"mqtt": {"host": "ha.local", "username": "boneio"}})
    assert (await update_route.get_mqtt_username())["uses_local_broker"] is False


async def test_no_mqtt_section_claims_nothing(configured):
    configured({"web": {"port": 8090}})
    body = await update_route.get_mqtt_username()

    assert body["known"] is False
    assert body["uses_local_broker"] is False


async def test_an_unreadable_config_claims_nothing(monkeypatch):
    """The panel still works; it just does not mark a row it cannot vouch for."""

    def boom():
        raise RuntimeError("no config helper")

    monkeypatch.setattr(system_route, "_config_helper_getter", boom, raising=False)
    body = await update_route.get_mqtt_username()

    assert body["status"] == "success"
    assert body["known"] is False


async def test_it_does_not_read_a_path_that_exists_on_no_device(configured, monkeypatch):
    """Pins the defect: the answer came from ~/.boneio/mqtt.yaml, or rather did not."""
    opened: list[str] = []
    real_open = open

    def watched(path, *args, **kwargs):
        opened.append(str(path))
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", watched)
    configured({"mqtt": {"host": "localhost", "username": "boneio"}})
    await update_route.get_mqtt_username()

    assert not any(".boneio" in path for path in opened)


class TestThisDevicesOwnAddress:
    """`host:` set to the controller's own address reaches the same broker."""

    def test_the_hostname_counts(self, monkeypatch):
        monkeypatch.setattr(update_route.socket, "gethostname", lambda: "boneio-black")
        assert update_route.is_local_broker_host("boneio-black")
        assert update_route.is_local_broker_host("BoneIO-Black.local")
        assert not update_route.is_local_broker_host("homeassistant.local")

    def test_an_address_bound_here_counts(self):
        assert update_route.is_local_broker_host("127.0.0.2")
        assert update_route.is_local_broker_host("[::1]")

    def test_an_address_elsewhere_does_not(self):
        # TEST-NET-3: never assigned to a real interface.
        assert not update_route.is_local_broker_host("203.0.113.7")

    def test_one_of_this_machines_own_addresses_counts(self, monkeypatch):
        import socket

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            try:
                s.connect(("203.0.113.7", 9))
            except OSError:
                pytest.skip("no route to find an own address")
            own = s.getsockname()[0]
        if own.startswith("127."):
            pytest.skip("only loopback here")
        assert update_route.is_local_broker_host(own)

    async def test_the_panel_is_told(self, configured, monkeypatch):
        monkeypatch.setattr(update_route.socket, "gethostname", lambda: "boneio-black")
        configured({"mqtt": {"host": "boneio-black.local", "username": "boneio"}})
        assert (await update_route.get_mqtt_username())["uses_local_broker"] is True
