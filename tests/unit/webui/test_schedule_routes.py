"""Tests for the schedule routes.

The status endpoint exists because a schedule is the one thing in boneIO you
cannot test by pressing a button: the only way to know it is armed is to ask.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException

from boneio.core.manager.scheduler import Scheduler
from boneio.core.manager.sun import SunProvider
from boneio.webui.routes import schedule as schedule_routes

WARSAW = ZoneInfo("Europe/Warsaw")

SCHEDULE = {
    "id": "evening",
    "name": "Evening covers",
    "enabled": True,
    "trigger": {"type": "time", "at": "21:00", "days": "daily"},
    "on_missed": "skip",
    "catch_up": 900,
    "actions": [{"action": "mqtt", "topic": "t", "action_mqtt_msg": "go"}],
}


@pytest.fixture
def manager(monkeypatch):
    monkeypatch.setattr("boneio.core.manager.sun.local_timezone", lambda: WARSAW)
    fake = MagicMock()
    fake.sun = SunProvider({"latitude": 52.2297, "longitude": 21.0122})
    fake.parse_actions = lambda _id, actions: {k: list(v) for k, v in actions.items()}
    fake.executed = []

    async def execute_actions(actions, **kwargs):
        fake.executed.append(list(actions))

    fake.execute_actions = execute_actions
    fake.scheduler = Scheduler(fake, [SCHEDULE])
    fake.scheduler._plan()
    return fake


def test_status_lists_what_is_armed(manager):
    payload = asyncio.run(schedule_routes.get_schedule_status(manager=manager))
    assert len(payload["schedules"]) == 1
    entry = payload["schedules"][0]
    assert entry["id"] == "evening"
    assert entry["enabled"] is True
    assert entry["next_fire"].endswith("+01:00") or entry["next_fire"].endswith("+02:00")


def test_status_on_a_device_with_no_scheduler():
    """Older configs and the onboarding path have no scheduler at all; the panel
    should get an empty list, not a 500."""
    bare = MagicMock()
    del bare.scheduler
    assert asyncio.run(schedule_routes.get_schedule_status(manager=bare)) == {"schedules": []}


def test_running_a_schedule_now_executes_its_actions(manager):
    payload = asyncio.run(
        schedule_routes.run_schedule_now(schedule_id="evening", manager=manager)
    )
    assert payload["status"] == "success"
    assert manager.executed == [SCHEDULE["actions"]]


def test_running_now_leaves_the_armed_timer_alone(manager):
    """Testing a schedule must not cost you its next real firing."""
    before = manager.scheduler._entries[0].next_fire
    asyncio.run(schedule_routes.run_schedule_now(schedule_id="evening", manager=manager))
    assert manager.scheduler._entries[0].next_fire == before


def test_an_unknown_schedule_is_a_404(manager):
    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(schedule_routes.run_schedule_now(schedule_id="nope", manager=manager))
    assert excinfo.value.status_code == 404


def test_running_now_is_recorded_as_a_manual_run(manager):
    """So the history can say "somebody pressed the button" rather than
    implying the timer went off at a time it did not."""
    asyncio.run(schedule_routes.run_schedule_now(schedule_id="evening", manager=manager))
    assert manager.scheduler._entries[0].history[-1]["source"] == "manual"


def test_running_now_returns_the_full_status(manager):
    payload = asyncio.run(
        schedule_routes.run_schedule_now(schedule_id="evening", manager=manager)
    )
    assert payload["last_outcome"] == "ran"
    assert payload["next_fire"] is not None
    assert len(payload["history"]) == 1


def test_disabling_a_schedule_through_the_api(manager):
    payload = asyncio.run(
        schedule_routes.set_schedule_enabled(
            schedule_id="evening",
            body=schedule_routes.EnableRequest(enabled=False),
            manager=manager,
        )
    )
    assert payload["enabled"] is False
    assert manager.scheduler._entries[0].next_fire is None, "it should be disarmed too"


def test_enabling_it_again_re_arms_it(manager):
    asyncio.run(
        schedule_routes.set_schedule_enabled(
            schedule_id="evening",
            body=schedule_routes.EnableRequest(enabled=False),
            manager=manager,
        )
    )
    manager.scheduler._running = True
    payload = asyncio.run(
        schedule_routes.set_schedule_enabled(
            schedule_id="evening",
            body=schedule_routes.EnableRequest(enabled=True),
            manager=manager,
        )
    )
    assert payload["enabled"] is True
    assert manager.scheduler._entries[0].next_fire is not None


def test_enabling_an_unknown_schedule_is_a_404(manager):
    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(
            schedule_routes.set_schedule_enabled(
                schedule_id="nope",
                body=schedule_routes.EnableRequest(enabled=True),
                manager=manager,
            )
        )
    assert excinfo.value.status_code == 404


def test_history_endpoint_returns_the_runs(manager):
    asyncio.run(schedule_routes.run_schedule_now(schedule_id="evening", manager=manager))
    payload = asyncio.run(
        schedule_routes.get_schedule_history(schedule_id="evening", manager=manager)
    )
    assert payload["id"] == "evening"
    assert len(payload["history"]) == 1
    assert payload["history"][0]["outcome"] == "ran"


def test_history_for_an_unknown_schedule_is_a_404(manager):
    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(
            schedule_routes.get_schedule_history(schedule_id="nope", manager=manager)
        )
    assert excinfo.value.status_code == 404
