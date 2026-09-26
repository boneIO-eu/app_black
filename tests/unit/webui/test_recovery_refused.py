"""When the recovery panel cannot run, the next start is a normal one.

A fresh controller has no administrator account, so recovery refuses to
start there. Before this, the refusal was an exit that systemd answered with
another start straight back into recovery, forever, behind a black screen.
"""

from __future__ import annotations

import errno
import logging
import time

import pytest

from boneio.core.auth.models import Role
from boneio.core.auth.store import USERS_FILENAME, UserStore
from boneio.core.recovery import CRASH_LOOP_THRESHOLD, StartupFailures
from boneio.hardware.display import early_oled
from boneio.webui.recovery import server


class _Time:
    """Stands in for ``time`` in the server module; sleeping is only recorded."""

    monotonic = staticmethod(time.monotonic)

    def __init__(self) -> None:
        self.slept: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)


@pytest.fixture
def config_file(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("boneio:\n  name: x\nweb:\n  port: 8090\n")
    return str(path)


@pytest.fixture
def crash_loop(config_file):
    failures = StartupFailures(config_file)
    for _ in range(CRASH_LOOP_THRESHOLD):
        try:
            raise PermissionError(errno.EACCES, "Permission denied", "/dev/i2c-2")
        except PermissionError as err:
            failures.record(err)
    assert failures.in_crash_loop()
    return failures


@pytest.fixture
def clock(monkeypatch):
    clock = _Time()
    monkeypatch.setattr(server, "time", clock)
    return clock


@pytest.fixture
def oled(monkeypatch):
    drawn: list[dict] = []
    kept: list[bool] = []
    monkeypatch.setattr(early_oled, "draw_recovery", lambda **kw: drawn.append(kw))
    monkeypatch.setattr(early_oled, "keep_on_exit", lambda: kept.append(True))
    return drawn, kept


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    import boneio.core.system as system

    monkeypatch.setattr(system, "get_network_info", lambda: {"ip": "192.0.2.10"})


def test_no_admin_hands_back_to_a_normal_start(monkeypatch, config_file, crash_loop, clock, oled, caplog):
    monkeypatch.setenv("INVOCATION_ID", "test")
    drawn, kept = oled

    with caplog.at_level(logging.ERROR, logger=server.__name__):
        code = server.run_recovery(config_file, crash_loop.last_reason())

    assert code == 1
    assert crash_loop.count == CRASH_LOOP_THRESHOLD - 1
    assert not crash_loop.in_crash_loop()
    assert clock.slept == [server.REFUSED_RETRY_SECONDS]

    assert len(drawn) == 1
    assert drawn[0]["title"] == "Start failed"
    assert drawn[0]["message"].startswith(f"Retrying in {server.REFUSED_RETRY_SECONDS} s.")
    assert "/dev/i2c-2" in drawn[0]["message"]
    assert kept == [True]

    errors = " ".join(r.getMessage() for r in caplog.records if r.levelno == logging.ERROR)
    assert "no administrator account" in errors
    assert "PermissionError" in errors and "/dev/i2c-2" in errors


def test_outside_systemd_it_does_not_wait(monkeypatch, config_file, crash_loop, clock, oled):
    monkeypatch.delenv("INVOCATION_ID", raising=False)
    drawn, _ = oled

    assert server.run_recovery(config_file, crash_loop.last_reason()) == 1

    assert clock.slept == []
    assert crash_loop.count == CRASH_LOOP_THRESHOLD - 1
    assert not drawn[0]["message"].startswith("Retrying")


def test_no_web_section_hands_back_too(monkeypatch, tmp_path, clock, oled):
    monkeypatch.setenv("INVOCATION_ID", "test")
    config_file = tmp_path / "config.yaml"
    config_file.write_text("boneio:\n  name: x\n")
    failures = StartupFailures(str(config_file))
    for _ in range(CRASH_LOOP_THRESHOLD):
        failures.record(RuntimeError("boom"))

    assert server.run_recovery(str(config_file), failures.last_reason()) == 1
    assert failures.count == CRASH_LOOP_THRESHOLD - 1


def test_with_an_admin_the_panel_runs_as_before(monkeypatch, config_file, crash_loop, clock, oled):
    monkeypatch.setenv("INVOCATION_ID", "test")
    store = UserStore.for_config_file(config_file)
    store.load()
    store.add_user("pawel", "haslo-admina", Role.ADMIN)
    assert (crash_loop.path.parent / USERS_FILENAME).exists()

    served: list[str] = []

    async def fake_serve(config_file, reason, settings, store, jwt_secret):
        served.append(reason.message)
        return False  # stopped, not asked to leave

    monkeypatch.setattr(server, "_serve", fake_serve)
    drawn, kept = oled

    assert server.run_recovery(config_file, crash_loop.last_reason()) == 0

    assert served and "/dev/i2c-2" in served[0]
    assert crash_loop.count == CRASH_LOOP_THRESHOLD
    assert clock.slept == []
    assert kept == []
    assert drawn and drawn[0]["title"] == "Recovery mode"


def test_a_panel_that_fails_to_serve_keeps_the_crash_loop(monkeypatch, config_file, crash_loop, clock, oled):
    # With an account on the device the next start should offer the panel
    # again, not drive outputs.
    monkeypatch.setenv("INVOCATION_ID", "test")
    store = UserStore.for_config_file(config_file)
    store.load()
    store.add_user("pawel", "haslo-admina", Role.ADMIN)

    async def broken_serve(*args, **kwargs):
        raise OSError(errno.EADDRINUSE, "Address already in use")

    monkeypatch.setattr(server, "_serve", broken_serve)

    assert server.run_recovery(config_file, crash_loop.last_reason()) == 1
    assert crash_loop.count == CRASH_LOOP_THRESHOLD
    assert clock.slept == []
