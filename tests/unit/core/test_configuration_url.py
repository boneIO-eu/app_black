"""Where a link to this panel should point.

Home Assistant shows a device link built from these two properties, and so now
does the panel itself. The case that was wrong: a controller whose own port has
been taken off the network still handed out a link to that port, which answers
nothing.
"""

from __future__ import annotations

import pytest

from boneio.core.config.config_helper import ConfigHelper


def _helper(**kwargs) -> ConfigHelper:
    return ConfigHelper(name="x", version="1", web_port=8090, **kwargs)


def test_the_panel_s_own_port_by_default():
    """Unchanged for every device that has not asked for anything else."""
    helper = _helper()
    assert helper.http_proto == "http"
    assert helper.web_configuration_port == 8090


def test_a_configured_proxy_port_wins():
    helper = _helper(proxy_port=9443)
    assert helper.http_proto == "https"
    assert helper.web_configuration_port == 9443


def test_a_panel_behind_the_proxy_is_not_linked_to_a_dead_port():
    """The bug.

    With web.expose set to proxy the panel's own port answers on the loopback
    and nothing else, so a link to it is a link to nowhere — and it is exactly
    the device where somebody is most likely to click it.
    """
    helper = _helper(expose="proxy")
    assert helper.http_proto == "https"
    assert helper.web_configuration_port == 8443


def test_an_explicit_port_still_wins_behind_the_proxy():
    """Somebody fronting the panel with their own proxy has said where it is."""
    helper = _helper(proxy_port=9443, expose="proxy")
    assert helper.web_configuration_port == 9443


@pytest.mark.parametrize("expose", ["all", "", None, "lopback"])
def test_anything_but_proxy_keeps_the_old_answer(expose):
    """A typo in config.yaml must not move where Home Assistant points."""
    helper = _helper(expose=expose) if expose is not None else _helper()
    assert helper.web_configuration_port == 8090
    assert helper.http_proto == "http"


def test_a_configured_proxy_port_is_still_honoured_though_the_panel_hides_it():
    """The field left the interface; it did not leave the product.

    Removing it from the schema would be worse than leaving it: the validator
    purges unknown keys, so the next save would delete it from the config.yaml
    of the few people who set one and move their Home Assistant link without
    telling them.
    """
    import yaml

    from pathlib import Path

    helper = _helper(proxy_port=9443)
    assert helper.web_configuration_port == 9443

    schema = Path(__file__).resolve().parents[3] / "boneio" / "schema" / "schema.yaml"
    text = schema.read_text(encoding="utf-8")
    assert "proxy_port:" in text, "dropping it from the schema deletes it from configs"


# ------------------------------------------------- one address, one decision


def _addressable(**kwargs):
    return ConfigHelper(
        name="x",
        version="1",
        web_port=8090,
        is_web_active=True,
        network_info={"ip": "192.168.50.220"},
        **kwargs,
    )


def test_the_url_follows_every_setting_that_changes_it():
    assert _addressable().configuration_url == "http://192.168.50.220:8090"
    assert (
        _addressable(proxy_port=8443).configuration_url
        == "https://192.168.50.220:8443"
    )
    assert (
        _addressable(expose="proxy").configuration_url == "https://192.168.50.220:8443"
    )


def test_cloud_registration_wins():
    """It is the only address with a certificate a browser accepts, so nothing
    local beats it — and the panel used to claim otherwise."""
    helper = _addressable(cloud_registration=True, proxy_port=8443)
    assert helper.configuration_url.startswith("https://")
    assert ".black.boneio.app:8443" in helper.configuration_url


def test_no_address_means_no_url():
    """A device with no network information has nothing truthful to publish."""
    helper = ConfigHelper(name="x", version="1", web_port=8090, is_web_active=True)
    assert helper.configuration_url is None


def test_discovery_publishes_exactly_this():
    """The panel described the rule instead of asking, and was wrong about a
    device with cloud registration on within a day of being written. Both read
    the same property now — this keeps them that way."""
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[3]
        / "boneio" / "integration" / "homeassistant.py"
    ).read_text(encoding="utf-8")
    assert "config_helper.configuration_url" in source
    assert "black.boneio.app" not in source, (
        "discovery is building the address again instead of reading it"
    )


def test_a_lease_that_arrives_after_boot_is_picked_up():
    """The snapshot is taken at startup; DHCP does not always oblige by then."""
    helper = ConfigHelper(name="x", version="1", web_port=8090, is_web_active=True)
    assert helper.configuration_url is None

    helper.update_network_info({"ip": "192.168.50.220"})
    assert helper.configuration_url == "http://192.168.50.220:8090"

    helper.update_network_info({"ip": "192.168.50.7"})
    assert helper.configuration_url == "http://192.168.50.7:8090"


def test_a_missing_address_is_not_published_as_an_address():
    """get_network_info reports a missing address as the string "none", which
    is truthy — unchecked it went out as https://none:8443."""
    helper = ConfigHelper(
        name="x",
        version="1",
        web_port=8090,
        is_web_active=True,
        network_info={"ip": "none"},
    )
    assert helper.configuration_url is None


def test_an_update_without_an_address_keeps_the_last_good_one():
    """A link to where the device was beats a link to nowhere."""
    helper = _addressable()
    assert helper.configuration_url == "http://192.168.50.220:8090"

    helper.update_network_info({"ip": "none"})
    helper.update_network_info({})
    helper.update_network_info(None)
    assert helper.configuration_url == "http://192.168.50.220:8090"


class _FakeManager:
    def __init__(self, helper, is_web_on=True):
        self.config_helper = helper
        self.is_web_on = is_web_on


def _oled_url(helper, is_web_on=True):
    """The URL the QR code on the display encodes."""
    from boneio.core.system.host_data import HostData

    fake = object.__new__(HostData)
    fake._manager = _FakeManager(helper, is_web_on)
    return HostData.web_url.fget(fake)


def test_the_display_and_home_assistant_agree():
    """They were assembled separately, so a cloud-registered device showed its
    certificate name in Home Assistant and a bare IP on the OLED."""
    helper = _addressable(cloud_registration=True, proxy_port=8443)
    assert _oled_url(helper) == helper.configuration_url
    assert ".black.boneio.app:8443" in _oled_url(helper)


def test_the_display_follows_the_proxy_too():
    helper = _addressable(expose="proxy")
    assert _oled_url(helper) == "https://192.168.50.220:8443"


def test_no_qr_code_when_the_panel_is_off():
    helper = _addressable(expose="proxy")
    assert _oled_url(helper, is_web_on=False) is None


def test_the_display_needs_no_network_screen():
    """The old code read _data[NETWORK], which does not exist when that screen
    is switched off — enabling the web screen alone raised KeyError."""
    helper = _addressable(expose="proxy")
    assert _oled_url(helper) is not None


def test_the_network_poll_keeps_the_snapshot_current(monkeypatch):
    """The OLED's network poll already runs every 60s; it is what carries a new
    lease into the snapshot Home Assistant's link is built from."""
    from boneio.core.system import host_data as host_data_module

    helper = ConfigHelper(name="x", version="1", web_port=8090, is_web_active=True)
    fake = object.__new__(host_data_module.HostData)
    fake._manager = _FakeManager(helper)

    monkeypatch.setattr(
        host_data_module, "get_network_info", lambda: {"ip": "10.0.0.5"}
    )
    returned = host_data_module.HostData._refresh_network_info(fake)

    # The screen still gets its data …
    assert returned == {"ip": "10.0.0.5"}
    # … and the link followed it.
    assert helper.configuration_url == "http://10.0.0.5:8090"


def test_the_network_poll_survives_a_manager_without_a_helper():
    """Early in startup the attribute may not be there yet; the screen must not
    take the device down over it."""
    from boneio.core.system import host_data as host_data_module

    fake = object.__new__(host_data_module.HostData)
    fake._manager = object()
    assert isinstance(host_data_module.HostData._refresh_network_info(fake), dict)
