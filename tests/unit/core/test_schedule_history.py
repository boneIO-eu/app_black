"""What a schedule leaves behind after it runs.

The complaint these tests exist for: from outside, "the schedule never fired"
and "it fired and its condition correctly told it to do nothing" used to look
identical. Only the log could tell them apart, and the log is not where anyone
looks first.

So every exit from a run is recorded, the record survives a restart, and a
switch in Home Assistant and an ``enabled:`` line in the config have a stated
rule for which of them wins.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from boneio.core.manager.scheduler import (
    OUTCOME_FAILED,
    OUTCOME_RAN,
    OUTCOME_SKIPPED,
    SOURCE_CATCH_UP,
    SOURCE_MANUAL,
    SOURCE_TIMER,
    _HISTORY_LIMIT,
    Scheduler,
)
from boneio.core.manager.sun import SunProvider

WARSAW = ZoneInfo("Europe/Warsaw")
ACTION = {"action": "mqtt", "topic": "test/fire", "action_mqtt_msg": "go"}


class FakeStore:
    """A state store that keeps what it is given, like the real one does."""

    def __init__(self, initial: dict | None = None) -> None:
        self.data: dict[str, dict] = dict(initial or {})
        self.writes = 0

    def save_attribute(self, attr_type: str, attribute: str, value) -> None:
        self.writes += 1
        self.data.setdefault(attr_type, {})[attribute] = value

    def get(self, attr_type: str, attr: str, default_value=None):
        return self.data.get(attr_type, {}).get(attr, default_value)


def make_manager(monkeypatch, store: FakeStore | None = None):
    monkeypatch.setattr("boneio.core.manager.sun.local_timezone", lambda: WARSAW)
    manager = MagicMock()
    manager.sun = SunProvider({"latitude": 52.2297, "longitude": 21.0122})
    manager.parse_actions = lambda _id, actions: {
        key: list(value) for key, value in actions.items()
    }
    manager.executed = []
    manager._state_manager = store if store is not None else FakeStore()

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
        "actions": [ACTION],
    }
    base.update(overrides)
    return base


# ── what a run records ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_successful_run_is_recorded(monkeypatch):
    scheduler = Scheduler(make_manager(monkeypatch), [schedule()])
    entry = scheduler._entries[0]

    await scheduler._run(entry)

    assert entry.last_outcome == OUTCOME_RAN
    assert entry.last_error is None
    assert len(entry.history) == 1
    assert entry.history[-1]["outcome"] == OUTCOME_RAN
    assert entry.history[-1]["source"] == SOURCE_TIMER
    assert entry.history[-1]["actions"] == 1
    assert entry.history[-1]["duration_ms"] >= 0


@pytest.mark.asyncio
async def test_a_condition_that_blocks_still_leaves_a_record(monkeypatch):
    """The whole point. Before this, a blocked firing was indistinguishable
    from a schedule that never fired at all."""
    manager = make_manager(monkeypatch)
    scheduler = Scheduler(manager, [schedule(condition={"type": "sun", "phase": "day"})])
    entry = scheduler._entries[0]
    monkeypatch.setattr(
        "boneio.core.manager.sun.SunProvider.in_phase",
        lambda self, phase, now=None: False,
    )

    await scheduler._run(entry)

    assert manager.executed == []
    assert entry.last_outcome == OUTCOME_SKIPPED
    assert entry.last_fire is not None, "it fired; it just decided not to act"
    assert entry.history[-1]["outcome"] == OUTCOME_SKIPPED


@pytest.mark.asyncio
async def test_a_failure_is_recorded_with_its_message(monkeypatch):
    manager = make_manager(monkeypatch)

    async def boom(actions, **kwargs):
        raise RuntimeError("relay on fire")

    manager.execute_actions = boom
    scheduler = Scheduler(manager, [schedule()])
    entry = scheduler._entries[0]

    await scheduler._run(entry)

    assert entry.last_outcome == OUTCOME_FAILED
    assert entry.last_error == "relay on fire"
    assert entry.history[-1]["error"] == "relay on fire"


@pytest.mark.asyncio
async def test_last_fire_means_the_timer_fired_not_that_it_succeeded(monkeypatch):
    manager = make_manager(monkeypatch)

    async def boom(actions, **kwargs):
        raise RuntimeError("nope")

    manager.execute_actions = boom
    scheduler = Scheduler(manager, [schedule()])
    entry = scheduler._entries[0]

    await scheduler._run(entry)

    assert entry.last_fire is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("source", [SOURCE_TIMER, SOURCE_CATCH_UP, SOURCE_MANUAL])
async def test_the_source_of_a_run_is_kept(monkeypatch, source):
    """A catch-up and a button press are the two people ask about, and the log
    line alone does not tell them apart afterwards."""
    scheduler = Scheduler(make_manager(monkeypatch), [schedule()])
    entry = scheduler._entries[0]

    await scheduler._run(entry, source=source)

    assert entry.history[-1]["source"] == source


@pytest.mark.asyncio
async def test_history_stops_at_the_limit(monkeypatch):
    scheduler = Scheduler(make_manager(monkeypatch), [schedule()])
    entry = scheduler._entries[0]

    for _ in range(_HISTORY_LIMIT + 5):
        await scheduler._run(entry)

    assert len(entry.history) == _HISTORY_LIMIT


# ── surviving a restart ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_run_is_written_to_the_state_store(monkeypatch):
    store = FakeStore()
    scheduler = Scheduler(make_manager(monkeypatch, store), [schedule()])

    await scheduler._run(scheduler._entries[0])

    saved = store.get("schedule", "test")
    assert saved["enabled"] is True
    assert saved["enabled_from_config"] is True
    assert len(saved["history"]) == 1
    assert saved["history"][0]["outcome"] == OUTCOME_RAN


@pytest.mark.asyncio
async def test_history_comes_back_after_a_restart(monkeypatch):
    store = FakeStore()
    first = Scheduler(make_manager(monkeypatch, store), [schedule()])
    await first._run(first._entries[0])

    # A restart is a fresh Scheduler over the same store.
    second = Scheduler(make_manager(monkeypatch, store), [schedule()])
    entry = second._entries[0]

    assert len(entry.history) == 1
    assert entry.last_outcome == OUTCOME_RAN
    assert entry.last_fire is not None


def test_nothing_is_written_before_the_clock_is_set(monkeypatch):
    """The board boots in 1970. A history of runs stamped with a year that
    never happened is worse than a gap."""
    store = FakeStore()
    manager = make_manager(monkeypatch, store)
    monkeypatch.setattr(
        "boneio.core.manager.sun.SunProvider.clock_ready",
        lambda self, now=None: False,
    )
    scheduler = Scheduler(manager, [schedule()])
    entry = scheduler._entries[0]

    scheduler._record(
        entry, datetime.now().astimezone(), SOURCE_TIMER, OUTCOME_RAN, 5, None
    )

    assert len(entry.history) == 1, "it is still visible while the device is up"
    assert store.get("schedule", "test") is None


def test_a_broken_store_does_not_stop_the_boot(monkeypatch):
    class Angry(FakeStore):
        def get(self, *args, **kwargs):
            raise OSError("state.json is a directory somehow")

    scheduler = Scheduler(make_manager(monkeypatch, Angry()), [schedule()])
    assert scheduler._entries[0].enabled is True


# ── who wins: the switch or the config ────────────────────────────────────


def test_a_stored_override_survives_when_the_config_has_not_moved(monkeypatch):
    store = FakeStore(
        {"schedule": {"test": {"enabled": False, "enabled_from_config": True, "history": []}}}
    )
    scheduler = Scheduler(make_manager(monkeypatch, store), [schedule(enabled=True)])

    assert scheduler._entries[0].enabled is False, "somebody switched it off; keep it off"


def test_editing_the_config_beats_a_stale_override(monkeypatch):
    """Someone opened the YAML and wrote a different answer. That is the more
    deliberate of the two statements, so it wins and the override goes."""
    store = FakeStore(
        {"schedule": {"test": {"enabled": True, "enabled_from_config": True, "history": []}}}
    )
    scheduler = Scheduler(make_manager(monkeypatch, store), [schedule(enabled=False)])

    assert scheduler._entries[0].enabled is False


def test_an_override_for_a_schedule_with_no_actions_is_ignored(monkeypatch):
    store = FakeStore(
        {"schedule": {"test": {"enabled": True, "enabled_from_config": True, "history": []}}}
    )
    scheduler = Scheduler(make_manager(monkeypatch, store), [schedule(actions=[])])

    assert scheduler._entries[0].enabled is False


def test_set_enabled_persists_and_disarms(monkeypatch):
    store = FakeStore()
    scheduler = Scheduler(make_manager(monkeypatch, store), [schedule()])
    scheduler._plan()
    assert scheduler._entries[0].next_fire is not None

    assert scheduler.set_enabled("test", False) is True

    assert scheduler._entries[0].enabled is False
    assert scheduler._entries[0].next_fire is None
    assert store.get("schedule", "test")["enabled"] is False


def test_set_enabled_on_an_unknown_id_says_so(monkeypatch):
    scheduler = Scheduler(make_manager(monkeypatch), [schedule()])
    assert scheduler.set_enabled("nope", False) is False


# ── what Home Assistant is told ───────────────────────────────────────────


def test_every_schedule_is_announced_with_its_diagnostics(monkeypatch):
    manager = make_manager(monkeypatch)
    manager._config_helper.topic_prefix = "boneio"
    scheduler = Scheduler(manager, [schedule()])

    scheduler.publish_discovery()

    types = [call.kwargs["ha_type"] for call in manager.publish_ha_discovery.call_args_list]
    ids = [call.kwargs["id"] for call in manager.publish_ha_discovery.call_args_list]
    assert types == ["switch", "sensor", "sensor", "sensor"]
    assert ids == ["test", "test_next_fire", "test_last_fire", "test_last_outcome"]


def test_a_disabled_schedule_is_still_announced(monkeypatch):
    """A schedule that disappears from the panel when it is switched off is the
    thing that makes people ask whether it ever existed."""
    manager = make_manager(monkeypatch)
    manager._config_helper.topic_prefix = "boneio"
    scheduler = Scheduler(manager, [schedule(enabled=False)])

    scheduler.publish_discovery()

    assert manager.publish_ha_discovery.call_count == 4


@pytest.mark.asyncio
async def test_the_state_message_carries_every_entity_at_once(monkeypatch):
    manager = make_manager(monkeypatch)
    manager._config_helper.topic_prefix = "boneio"
    scheduler = Scheduler(manager, [schedule()])

    await scheduler._run(scheduler._entries[0])

    sent = manager.send_message.call_args
    assert sent.kwargs["topic"] == "boneio/schedule/test"
    assert sent.kwargs["retain"] is True
    payload = sent.kwargs["payload"]
    assert payload["state"] == "ON"
    assert payload["last_outcome"] == OUTCOME_RAN
    assert payload["last_error"] == ""


def test_a_missing_time_is_published_as_empty_not_none(monkeypatch):
    """An empty string is how the irrigation countdown already says "nothing to
    show", and it is what HA reads as unknown instead of failing to parse a
    timestamp out of the word None."""
    manager = make_manager(monkeypatch)
    manager._config_helper.topic_prefix = "boneio"
    scheduler = Scheduler(manager, [schedule()])

    scheduler._announce(scheduler._entries[0])

    payload = manager.send_message.call_args.kwargs["payload"]
    assert payload["next_fire"] == ""
    assert payload["last_fire"] == ""
    assert payload["last_outcome"] == "never"
