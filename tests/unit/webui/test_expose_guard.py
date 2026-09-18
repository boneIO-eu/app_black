"""Taking the panel off the local network, safely.

`web.expose: proxy` is the fix for the panel being served in the clear. It is
also the one setting whose failure mode is a controller in a cabinet answering
on no port at all, so it is refused unless something else is demonstrably
serving the panel first.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from boneio.webui import bind
from boneio.webui.routes.config_core import _guard_expose_change


@pytest.fixture
def proxy(monkeypatch):
    def answer(serving: bool, reason: str = "nothing is serving HTTPS"):
        calls: list[int] = []

        def check(port, timeout=5.0):
            calls.append(port)
            return (serving, "" if serving else reason)

        monkeypatch.setattr(bind, "proxy_is_serving", check)
        return calls

    return answer


def _guard(previous, current):
    return asyncio.run(_guard_expose_change(previous, current))


def test_switching_to_proxy_needs_a_working_proxy(proxy):
    proxy(serving=True)
    _guard({"expose": "all"}, {"expose": "proxy"})  # does not raise


def test_a_proxy_that_is_not_serving_stops_the_change(proxy):
    """Caddy listens whether or not it can reach the application behind it, so
    "the port is open" is not the question being asked."""
    proxy(serving=False, reason="the proxy answered 502 on port 8443")
    with pytest.raises(HTTPException) as err:
        _guard({"expose": "all"}, {"expose": "proxy"})
    assert err.value.status_code == 409
    assert "502" in err.value.detail
    assert "no port at all" in err.value.detail


def test_going_back_to_all_is_never_blocked(proxy):
    """The way out has to work even when the proxy is broken — that is exactly
    when somebody needs it."""
    calls = proxy(serving=False)
    _guard({"expose": "proxy"}, {"expose": "all"})
    assert calls == [], "asked the proxy before allowing a device back onto the network"


def test_a_save_that_does_not_touch_exposure_is_not_delayed(proxy):
    """Every save of the web section would otherwise pay for an HTTPS round
    trip it has no use for."""
    calls = proxy(serving=True)
    _guard({"expose": "all", "port": 8090}, {"expose": "all", "port": 9000})
    assert calls == []


def test_already_behind_the_proxy_is_not_rechecked(proxy):
    calls = proxy(serving=True)
    _guard({"expose": "proxy"}, {"expose": "proxy", "port": 8090})
    assert calls == []


def test_the_configured_proxy_port_is_the_one_tested(proxy):
    calls = proxy(serving=True)
    _guard({"expose": "all"}, {"expose": "proxy", "proxy_port": 9443})
    assert calls == [9443]


def test_without_a_configured_port_the_published_one_is_tested(proxy):
    calls = proxy(serving=True)
    _guard({"expose": "all"}, {"expose": "proxy"})
    assert calls == [bind.DEFAULT_PROXY_PORT]


def test_a_first_ever_web_section_is_still_guarded(proxy):
    """No previous section at all — a config that never had one."""
    proxy(serving=False)
    with pytest.raises(HTTPException):
        _guard(None, {"expose": "proxy"})
