"""The security page's slow system reads, kept warm.

The SSH login state (a sudo call and a yescrypt check) and the OS update state
took 2.3 s and 1.8 s on a BeagleBone, one after the other, on every open of
the security page and the SSH card.
"""

from __future__ import annotations

import threading
import time

from boneio.webui.routes import security as security_module
from boneio.webui.routes.security import _Refreshing


def _counter(values):
    calls = []

    def read():
        calls.append(time.monotonic())
        return values[min(len(calls) - 1, len(values) - 1)]

    return read, calls


def test_the_first_read_waits_for_the_answer():
    read, calls = _counter(["set"])
    cache = _Refreshing("x", read, ttl=60)
    assert cache.get() == "set"
    assert len(calls) == 1


def test_within_the_ttl_the_answer_is_reused():
    read, calls = _counter(["set", "shipped"])
    cache = _Refreshing("x", read, ttl=60)
    cache.get()
    assert cache.get() == "set"
    assert len(calls) == 1


def test_past_the_ttl_the_old_answer_comes_back_at_once_and_refreshes_behind():
    started = threading.Event()
    release = threading.Event()
    calls = []

    def read():
        # With ttl=0 every get() below starts another refresh; each answers
        # "shipped" after the first, and only the first of those blocks.
        calls.append(1)
        if len(calls) == 1:
            return "set"
        if len(calls) == 2:
            started.set()
            release.wait(5)
        return "shipped"

    cache = _Refreshing("x", read, ttl=0)
    assert cache.get() == "set"
    # Stale: served at once, while the refresh is still blocked.
    assert cache.get() == "set"
    assert started.wait(5)
    release.set()
    for _ in range(100):
        if cache.get() == "shipped":
            break
        time.sleep(0.01)
    assert cache.get() == "shipped"


def test_one_refresh_at_a_time():
    release = threading.Event()
    calls = []

    def read():
        calls.append(1)
        if len(calls) > 1:
            release.wait(5)
        return "set"

    cache = _Refreshing("x", read, ttl=0)
    cache.get()
    for _ in range(5):
        cache.get()
    release.set()
    time.sleep(0.05)
    assert len(calls) == 2


def test_a_failing_read_is_none_not_an_error():
    def read():
        raise RuntimeError("helper gone")

    assert _Refreshing("x", read, ttl=60).get() is None


def test_forget_makes_the_next_read_ask_again():
    read, calls = _counter(["set", "shipped"])
    cache = _Refreshing("x", read, ttl=60)
    cache.get()
    cache.forget()
    assert cache.get() == "shipped"


def test_both_unknown_reads_run_side_by_side(monkeypatch):
    def slow(value):
        def read():
            time.sleep(0.3)
            return value
        return read

    monkeypatch.setattr(security_module, "_service_password", _Refreshing("ssh", slow("set"), 60))
    monkeypatch.setattr(security_module, "_os_update", _Refreshing("os", slow({"running": False}), 60))
    started = time.monotonic()
    ssh, os_update = security_module._system_states()
    elapsed = time.monotonic() - started
    assert (ssh, os_update) == ("set", {"running": False})
    assert elapsed < 0.55


def test_warming_asks_nothing_where_the_helper_is_not_installed(monkeypatch):
    monkeypatch.setattr(security_module.system_ops, "HELPER_PATH", "/nonexistent/boneio-system")
    called = []
    monkeypatch.setattr(security_module, "_service_password", _Refreshing("ssh", lambda: called.append(1), 60))
    monkeypatch.setattr(security_module, "_os_update", _Refreshing("os", lambda: called.append(1), 60))
    security_module.warm_system_state()
    time.sleep(0.05)
    assert called == []


def test_warming_leaves_the_server_alone_while_it_starts(monkeypatch, tmp_path):
    """Both reads are sudo calls on one core; started with the server they held
    the first page back by over ten seconds on a BeagleBone."""
    helper = tmp_path / "boneio-system"
    helper.write_text("")
    monkeypatch.setattr(security_module.system_ops, "HELPER_PATH", str(helper))
    called = []
    monkeypatch.setattr(security_module, "_service_password", _Refreshing("ssh", lambda: called.append("ssh"), 60))
    monkeypatch.setattr(security_module, "_os_update", _Refreshing("os", lambda: called.append("os"), 60))
    security_module.warm_system_state(delay=0.2)
    time.sleep(0.05)
    assert called == []
    time.sleep(0.4)
    assert sorted(called) == ["os", "ssh"]
