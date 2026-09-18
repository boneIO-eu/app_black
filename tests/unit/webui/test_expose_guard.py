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
from boneio.webui.routes import config_core
from boneio.webui.routes import security as security_route
from boneio.webui.routes.config_core import _guard_expose_change


@pytest.fixture
def proxy(monkeypatch):
    """Answer the proxy probe, wherever it is looked up.

    Both modules import the function by name, so the object to replace is the
    one bound in them — patching boneio.webui.bind would leave those names
    pointing at the original.
    """

    def answer(serving: bool, reason: str = "nothing is serving HTTPS"):
        calls: list[int] = []

        def check(port, timeout=5.0):
            calls.append(port)
            return (serving, "" if serving else reason)

        for module in (config_core, security_route):
            monkeypatch.setattr(module, "proxy_is_serving", check)
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


# --------------------------------------- advice that matches what we will do


class _Posture:
    """The exposure check, evaluated with a given view of the proxy."""

    @staticmethod
    def check(proxy_serving):
        from boneio.core.security.posture import evaluate

        posture = evaluate(
            {},
            is_provisioned=True,
            anonymous_allowed=False,
            auth_required=True,
            cloud_active=False,
            proxy_serving=proxy_serving,
        )
        return next(c for c in posture.checks if c.id == "web_exposed_in_clear")


def test_a_working_proxy_makes_it_a_warning():
    from boneio.core.security.posture import Severity

    assert _Posture.check(True).severity is Severity.WARNING


def test_a_proxy_that_is_not_serving_makes_it_advice():
    """Otherwise the panel recommends a change the save would refuse, and the
    operator finds that out by clicking."""
    from boneio.core.security.posture import Severity

    check = _Posture.check(False)
    assert check.severity is Severity.INFO
    assert "reachable on nothing" in check.detail
    assert "proxy serving this panel first" in check.remedy


def test_not_having_looked_still_warns():
    """The Home Assistant sensor derives the posture without the web layer, so
    it cannot probe. Something unlocked is still something unlocked."""
    from boneio.core.security.posture import Severity

    assert _Posture.check(None).severity is Severity.WARNING


def test_a_device_behind_the_proxy_passes_whatever_the_probe_says():
    from boneio.core.security.posture import State, evaluate

    for probe in (True, False, None):
        posture = evaluate(
            {"web": {"expose": "proxy"}},
            is_provisioned=True,
            anonymous_allowed=False,
            auth_required=True,
            cloud_active=False,
            proxy_serving=probe,
        )
        check = next(c for c in posture.checks if c.id == "web_exposed_in_clear")
        assert check.state is State.OK


def test_a_device_already_behind_the_proxy_is_not_probed(monkeypatch):
    """Spending an HTTPS round trip to learn what is already true."""
    from boneio.webui.routes import security as route

    monkeypatch.setattr(route, "_proxy_probe", None, raising=False)
    monkeypatch.setattr(
        route, "proxy_is_serving", lambda *a, **k: pytest.fail("probed anyway")
    )
    assert route._proxy_serving({"web": {"expose": "proxy"}}) is None


def test_the_probe_answer_is_reused_briefly(monkeypatch):
    """Three components ask for the posture on one page load."""
    from boneio.webui.routes import security as route

    calls = []
    monkeypatch.setattr(route, "_proxy_probe", None, raising=False)
    monkeypatch.setattr(
        route, "proxy_is_serving", lambda *a, **k: calls.append(1) or (True, "")
    )
    assert route._proxy_serving({}) is True
    assert route._proxy_serving({}) is True
    assert len(calls) == 1
