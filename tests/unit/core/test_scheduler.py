"""Tests for the schedule runtime.

A schedule acts on the house with nobody present, so the interesting cases are
all the ones where it should *not* act: a clock that has not been set, a day the
Sun never reaches the angle, a firing missed while the device was off, a day
filter that excludes today.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from boneio.core.manager.scheduler import Scheduler
from boneio.core.manager.sun import SunProvider

WARSAW = ZoneInfo("Europe/Warsaw")
OSLO = ZoneInfo("Europe/Oslo")

# Warsaw, 20 March 2025 (a Thursday): sunrise 05:38, sunset 17:49 local.
EQUINOX = date(2025, 3, 20)

ACTION = {"action": "mqtt", "topic": "test/fire", "action_mqtt_msg": "go"}


def make_manager(monkeypatch, location=None, tz=WARSAW):
    """A manager stub: real SunProvider, recording execute_actions."""
    monkeypatch.setattr("boneio.core.manager.sun.local_timezone", lambda: tz)
    manager = MagicMock()
    manager.sun = SunProvider(location or {"latitude": 52.2297, "longitude": 21.0122})
    manager.parse_actions = lambda _id, actions: {
        key: list(value) for key, value in actions.items()
    }
    manager.executed = []

    async def execute_actions(actions, **kwargs):
        manager.executed.append(list(actions))

    manager.execute_actions = execute_actions
    return manager


def schedule(**overrides) -> dict:
    base = {
        "id": "test",
        "name": "Test schedule",
        "enabled": True,
        "trigger": {"type": "sun", "event": "sunset", "days": "daily"},
        "on_missed": "skip",
        "catch_up": 900,
        "actions": [ACTION],
    }
    base.update(overrides)
    return base


def at(iso: str, tz=WARSAW) -> datetime:
    return datetime.fromisoformat(iso).replace(tzinfo=tz)


# ── when it fires ────────────────────────────────────────────────────────


def test_a_sun_trigger_fires_at_the_anchor(monkeypatch):
    scheduler = Scheduler(make_manager(monkeypatch), [schedule()])
    entry = scheduler._entries[0]

    when = scheduler._fire_time_on(entry, EQUINOX, at("2025-03-20 12:00"))
    assert when.astimezone(WARSAW).strftime("%H:%M") == "17:49"


def test_an_offset_moves_it(monkeypatch):
    scheduler = Scheduler(
        make_manager(monkeypatch),
        [schedule(trigger={"type": "sun", "event": "sunset", "offset": -900, "days": "daily"})],
    )
    when = scheduler._fire_time_on(scheduler._entries[0], EQUINOX, at("2025-03-20 12:00"))
    assert when.astimezone(WARSAW).strftime("%H:%M") == "17:34"


def test_a_time_trigger_fires_at_the_clock_time(monkeypatch):
    scheduler = Scheduler(
        make_manager(monkeypatch),
        [schedule(trigger={"type": "time", "at": "22:30", "days": "daily"})],
    )
    when = scheduler._fire_time_on(scheduler._entries[0], EQUINOX, at("2025-03-20 12:00"))
    assert when.astimezone(WARSAW).strftime("%H:%M") == "22:30"


def test_the_next_firing_is_strictly_in_the_future(monkeypatch):
    scheduler = Scheduler(
        make_manager(monkeypatch),
        [schedule(trigger={"type": "time", "at": "10:00", "days": "daily"})],
    )
    entry = scheduler._entries[0]

    before = scheduler._next_fire(entry, at("2025-03-20 09:00"))
    assert before.astimezone(WARSAW).date() == EQUINOX

    after = scheduler._next_fire(entry, at("2025-03-20 11:00"))
    assert after.astimezone(WARSAW).date() == EQUINOX + timedelta(days=1)


# ── day filters ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("days", "expected"),
    [
        ("daily", True),
        ("weekdays", True),   # 20 March 2025 is a Thursday
        ("thu", True),
        ("weekend", False),
        ("sat", False),
    ],
)
def test_the_day_filter(monkeypatch, days, expected):
    scheduler = Scheduler(
        make_manager(monkeypatch),
        [schedule(trigger={"type": "time", "at": "10:00", "days": days})],
    )
    when = scheduler._fire_time_on(scheduler._entries[0], EQUINOX, at("2025-03-20 08:00"))
    assert (when is not None) is expected


def test_the_filter_applies_to_the_day_the_firing_lands_on(monkeypatch):
    """An offset that pushes past midnight counts as the day it happens on,
    which is what someone reading "weekdays" expects."""
    # Friday 23:30 + 1 h lands on Saturday, so a weekdays filter excludes it.
    scheduler = Scheduler(
        make_manager(monkeypatch),
        [schedule(trigger={"type": "time", "at": "23:30", "offset": 3600, "days": "weekdays"})],
    )
    friday = date(2025, 3, 21)
    assert scheduler._fire_time_on(scheduler._entries[0], friday, at("2025-03-21 08:00")) is None


# ── jitter ───────────────────────────────────────────────────────────────


def test_jitter_stays_inside_its_bound(monkeypatch):
    scheduler = Scheduler(
        make_manager(monkeypatch),
        [schedule(trigger={"type": "time", "at": "10:00", "jitter": 600, "days": "daily"})],
    )
    entry = scheduler._entries[0]
    base = at("2025-03-20 10:00")
    when = scheduler._fire_time_on(entry, EQUINOX, at("2025-03-20 08:00"))
    delta = (when - base).total_seconds()
    assert 0 <= delta <= 600


def test_jitter_is_stable_for_a_given_day(monkeypatch):
    """Re-planning happens every minute. A fresh draw each time would walk the
    firing forwards and it would never arrive."""
    scheduler = Scheduler(
        make_manager(monkeypatch),
        [schedule(trigger={"type": "time", "at": "10:00", "jitter": 600, "days": "daily"})],
    )
    entry = scheduler._entries[0]
    first = scheduler._fire_time_on(entry, EQUINOX, at("2025-03-20 08:00"))
    second = scheduler._fire_time_on(entry, EQUINOX, at("2025-03-20 09:00"))
    assert first == second


def test_jitter_differs_between_days(monkeypatch):
    scheduler = Scheduler(
        make_manager(monkeypatch),
        [schedule(trigger={"type": "time", "at": "10:00", "jitter": 3600, "days": "daily"})],
    )
    entry = scheduler._entries[0]
    times = {
        scheduler._fire_time_on(entry, EQUINOX + timedelta(days=n), at("2025-03-20 08:00")).time()
        for n in range(5)
    }
    assert len(times) > 1


# ── polar and other absences ─────────────────────────────────────────────


def test_a_sun_event_that_does_not_happen_that_day_is_skipped(monkeypatch):
    """Tromsø in June has no sunset; the schedule moves to a day that has one
    instead of inventing a time."""
    manager = make_manager(
        monkeypatch, location={"latitude": 69.6492, "longitude": 18.9553}, tz=OSLO
    )
    scheduler = Scheduler(manager, [schedule()])
    entry = scheduler._entries[0]

    june = datetime(2025, 6, 21, 12, tzinfo=OSLO)
    assert scheduler._fire_time_on(entry, june.date(), june) is None

    following = scheduler._next_fire(entry, june)
    assert following is not None
    assert following > june


def test_a_sun_trigger_without_a_location_is_an_error_not_a_guess(monkeypatch):
    manager = make_manager(monkeypatch)
    manager.sun = SunProvider(None)
    scheduler = Scheduler(manager, [schedule()])
    with pytest.raises(ValueError, match="location"):
        scheduler._fire_time_on(scheduler._entries[0], EQUINOX, at("2025-03-20 12:00"))


def test_a_schedule_with_no_usable_actions_is_disabled(monkeypatch):
    scheduler = Scheduler(make_manager(monkeypatch), [schedule(actions=[])])
    assert scheduler._entries[0].enabled is False


# ── the clock ────────────────────────────────────────────────────────────


def test_nothing_is_armed_before_the_clock_is_set(monkeypatch, caplog):
    """The board has no RTC. Arming a timer against 1970 would fire everything
    at once the moment NTP corrects it."""
    monkeypatch.setattr("boneio.core.manager.sun._CLOCK_SANE_FROM", date(2999, 1, 1))
    scheduler = Scheduler(make_manager(monkeypatch), [schedule()])
    with caplog.at_level("WARNING"):
        scheduler._plan()
    assert scheduler._entries[0].next_fire is None
    assert any("clock is not set" in record.message for record in caplog.records)


# ── catch-up ─────────────────────────────────────────────────────────────


def test_a_missed_firing_is_skipped_by_default(monkeypatch):
    manager = make_manager(monkeypatch)
    scheduler = Scheduler(manager, [schedule(trigger={"type": "time", "at": "10:00", "days": "daily"})])
    scheduler._catch_up()
    assert manager.executed == []


def test_catch_up_runs_a_recent_miss(monkeypatch):
    manager = make_manager(monkeypatch)
    entry_config = schedule(
        trigger={"type": "time", "at": "10:00", "days": "daily"},
        on_missed="run",
        catch_up=3600,
    )
    scheduler = Scheduler(manager, [entry_config])
    entry = scheduler._entries[0]

    now = at("2025-03-20 10:05")
    previous = scheduler._previous_fire(entry, now)
    assert previous is not None
    assert (now - previous).total_seconds() == 300


def test_catch_up_ignores_an_old_miss(monkeypatch):
    """A device that was off all day must not close the covers at breakfast."""
    manager = make_manager(monkeypatch)
    scheduler = Scheduler(
        manager,
        [schedule(trigger={"type": "time", "at": "10:00", "days": "daily"}, on_missed="run", catch_up=900)],
    )
    entry = scheduler._entries[0]

    now = at("2025-03-20 18:00")
    previous = scheduler._previous_fire(entry, now)
    assert (now - previous).total_seconds() > entry.catch_up


# ── running ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_firing_executes_the_actions(monkeypatch):
    manager = make_manager(monkeypatch)
    scheduler = Scheduler(manager, [schedule()])
    await scheduler._run(scheduler._entries[0])
    assert manager.executed == [[ACTION]]
    assert scheduler._entries[0].last_fire is not None


@pytest.mark.asyncio
async def test_a_schedule_condition_can_block_the_firing(monkeypatch):
    """The schedule's own condition gates the whole firing, separately from any
    condition on an individual action."""
    manager = make_manager(monkeypatch)
    scheduler = Scheduler(
        manager,
        [schedule(condition={"type": "sun", "phase": "day"})],
    )
    entry = scheduler._entries[0]

    # Force the provider to report night, so a "day" condition must not pass.
    monkeypatch.setattr(
        "boneio.core.manager.sun.SunProvider.in_phase",
        lambda self, phase, now=None: False,
    )
    await scheduler._run(entry)
    assert manager.executed == []


@pytest.mark.asyncio
async def test_a_failing_action_does_not_break_the_schedule(monkeypatch):
    manager = make_manager(monkeypatch)

    async def boom(actions, **kwargs):
        raise RuntimeError("relay on fire")

    manager.execute_actions = boom
    scheduler = Scheduler(manager, [schedule()])
    await scheduler._run(scheduler._entries[0])  # must not raise
    assert scheduler._entries[0].last_error == "relay on fire"


@pytest.mark.asyncio
async def test_a_disabled_schedule_is_never_armed(monkeypatch):
    scheduler = Scheduler(make_manager(monkeypatch), [schedule(enabled=False)])
    scheduler._plan()
    assert scheduler._entries[0].next_fire is None


# ── introspection ────────────────────────────────────────────────────────


def test_status_reports_what_is_armed(monkeypatch):
    scheduler = Scheduler(
        make_manager(monkeypatch),
        [schedule(trigger={"type": "time", "at": "10:00", "days": "daily"})],
    )
    scheduler._plan()
    status = scheduler.status()
    assert len(status) == 1
    assert status[0]["id"] == "test"
    assert status[0]["enabled"] is True
    assert status[0]["actions"] == 1
    assert status[0]["next_fire"] is not None


@pytest.mark.asyncio
async def test_reload_disarms_the_previous_set(monkeypatch):
    manager = make_manager(monkeypatch)
    scheduler = Scheduler(manager, [schedule(id="old")])
    scheduler._plan()

    await scheduler.reload([schedule(id="new")])
    assert [entry.id for entry in scheduler._entries] == ["new"]


def test_timers_are_armed_for_the_computed_moment(monkeypatch):
    """_plan hands the instant to async_track_point_in_time; this checks the
    wiring, not the timer library."""
    manager = make_manager(monkeypatch)
    armed: list[datetime] = []
    monkeypatch.setattr(
        "boneio.core.manager.scheduler.async_track_point_in_time",
        lambda loop, job, point_in_time, **kw: armed.append(point_in_time) or (lambda: None),
    )
    scheduler = Scheduler(
        manager, [schedule(trigger={"type": "time", "at": "10:00", "days": "daily"})]
    )
    scheduler._plan()
    assert len(armed) == 1
    assert armed[0].astimezone(WARSAW).strftime("%H:%M") == "10:00"


def test_replanning_does_not_rearm_the_same_moment(monkeypatch):
    manager = make_manager(monkeypatch)
    armed: list[datetime] = []
    monkeypatch.setattr(
        "boneio.core.manager.scheduler.async_track_point_in_time",
        lambda loop, job, point_in_time, **kw: armed.append(point_in_time) or (lambda: None),
    )
    scheduler = Scheduler(
        manager, [schedule(trigger={"type": "time", "at": "10:00", "days": "daily"})]
    )
    for _ in range(5):
        scheduler._plan()
    assert len(armed) == 1
