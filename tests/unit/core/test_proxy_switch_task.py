"""When the controller moves itself to the packaged Caddy, and when it must not."""

from __future__ import annotations

import asyncio
import json

import pytest

from boneio.core import containers, proxy_switch
from boneio.core.containers import Result


@pytest.fixture(autouse=True)
def _fresh_recovery(monkeypatch):
    monkeypatch.setattr(proxy_switch, "_recovered_at", object())


class Helper:
    """A stand-in for the root helper and the network."""

    def __init__(self, monkeypatch, state=None, native=False, online=True):
        self.state = state or {"state": None, "running": False, "attempts": 0, "error": None}
        self.calls: list[str] = []
        self.polls_left = 1
        monkeypatch.setattr(containers, "helper_supports", lambda verb: True)
        monkeypatch.setattr(containers, "proxy_mode", lambda: "native" if native else "container")
        monkeypatch.setattr(containers, "proxy_switch_state", self._state)
        monkeypatch.setattr(containers, "proxy_switch_start", self._start)
        monkeypatch.setattr(containers, "proxy_switch_recover", self._recover)
        monkeypatch.setattr(proxy_switch, "has_default_route", lambda: online)
        monkeypatch.setattr(proxy_switch, "repo_resolves", lambda: online)
        monkeypatch.setattr(proxy_switch, "POLL", 0)

    def _state(self, timeout=30):
        return Result(0, json.dumps(self.state), "", True)

    def _start(self, timeout=60):
        self.calls.append("start")
        self.state = {**self.state, "running": True}
        return Result(0, "{}", "", True)

    def _recover(self, timeout=300):
        self.calls.append("recover")
        self.state = {**self.state, "state": "rolled_back", "error": "x", "running": False}
        return Result(0, "", "", True)

    def finish_after_poll(self, monkeypatch):
        real = self._state

        def state(timeout=30):
            if self.state["running"]:
                self.polls_left -= 1
                if self.polls_left < 0:
                    self.state = {**self.state, "running": False, "state": "done"}
            return real()

        monkeypatch.setattr(containers, "proxy_switch_state", state)


def test_it_starts_and_waits_until_the_run_ends(monkeypatch):
    helper = Helper(monkeypatch)
    helper.finish_after_poll(monkeypatch)
    assert asyncio.run(proxy_switch.attempt_switch()) is True
    assert helper.calls == ["start"]
    assert helper.state["state"] == "done"


def test_three_failed_runs_are_enough(monkeypatch):
    helper = Helper(monkeypatch, {"state": "failed", "running": False, "attempts": 3, "error": "x"})
    assert asyncio.run(proxy_switch.attempt_switch()) is True
    assert helper.calls == []


def test_two_failed_runs_leave_room_for_a_third(monkeypatch):
    helper = Helper(monkeypatch, {"state": "failed", "running": False, "attempts": 2, "error": "x"})
    helper.finish_after_poll(monkeypatch)
    assert asyncio.run(proxy_switch.attempt_switch()) is True


def test_offline_it_does_not_start(monkeypatch):
    helper = Helper(monkeypatch, online=False)
    assert asyncio.run(proxy_switch.attempt_switch()) is False
    assert helper.calls == []


@pytest.mark.parametrize("state", [{"state": "done", "running": False, "attempts": 1}, {"running": True}])
def test_a_finished_or_running_switch_is_left_alone(monkeypatch, state):
    helper = Helper(monkeypatch, state)
    assert asyncio.run(proxy_switch.attempt_switch()) is (not state.get("running"))
    assert helper.calls == []


def test_native_is_left_alone(monkeypatch):
    helper = Helper(monkeypatch, native=True)
    assert asyncio.run(proxy_switch.attempt_switch()) is True
    assert helper.calls == []


def test_an_old_helper_is_left_alone(monkeypatch):
    helper = Helper(monkeypatch)
    monkeypatch.setattr(containers, "helper_supports", lambda verb: False)
    assert asyncio.run(proxy_switch.attempt_switch()) is False
    assert helper.calls == []


def test_a_run_cut_short_is_undone_once_before_anything_else(monkeypatch):
    helper = Helper(
        monkeypatch, {"state": "failed", "running": False, "attempts": 1, "error": "interrupted"}
    )
    helper.finish_after_poll(monkeypatch)
    assert asyncio.run(proxy_switch.attempt_switch()) is True
    assert helper.calls == ["recover", "start"]


def test_nothing_starts_before_five_minutes(monkeypatch):
    helper = Helper(monkeypatch)
    sleeps: list[float] = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 1:
            assert helper.calls == []
        else:
            raise asyncio.CancelledError

    monkeypatch.setattr(proxy_switch.asyncio, "sleep", fake_sleep)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(proxy_switch.run())
    assert sleeps[0] == 300
    assert helper.calls == ["start"]


def test_a_unit_stopped_by_hand_during_the_watch_is_undone_at_once(monkeypatch):
    """The poll loop ends on an interrupted record; nothing else may wait for a reboot."""
    helper = Helper(monkeypatch, {"state": None, "running": False, "attempts": 2, "error": None})
    real_start = helper._start

    def start(timeout=60):
        real_start()
        helper.state = {**helper.state, "running": False, "state": "failed",
                        "error": "interrupted", "attempts": 3, "at": "t1"}
        return Result(0, "{}", "", True)

    monkeypatch.setattr(containers, "proxy_switch_start", start)
    assert asyncio.run(proxy_switch.attempt_switch()) is True
    assert helper.calls == ["start", "recover"]


def test_one_interrupted_record_is_undone_once(monkeypatch):
    state = {"state": "failed", "running": False, "attempts": 1, "error": "interrupted", "at": "t1"}
    helper = Helper(monkeypatch, state, online=False)
    # The helper keeps reporting the same record (e.g. the undo changed nothing).
    monkeypatch.setattr(helper, "_recover", lambda timeout=300: helper.calls.append("recover") or Result(0, "", "", True))
    monkeypatch.setattr(containers, "proxy_switch_recover", helper._recover)
    asyncio.run(proxy_switch.attempt_switch())
    asyncio.run(proxy_switch.attempt_switch())
    assert helper.calls == ["recover"]
    helper.state = {**state, "at": "t2"}
    asyncio.run(proxy_switch.attempt_switch())
    assert helper.calls == ["recover", "recover"]


def test_the_task_ends_when_attempts_are_used_up(monkeypatch):
    Helper(monkeypatch, {"state": "failed", "running": False, "attempts": 3, "error": "x"})

    async def fake_sleep(seconds):
        pass

    monkeypatch.setattr(proxy_switch.asyncio, "sleep", fake_sleep)
    asyncio.run(proxy_switch.run())
