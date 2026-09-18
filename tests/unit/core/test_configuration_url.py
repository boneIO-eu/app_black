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
