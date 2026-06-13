"""Tests for IrrigationManager lifecycle — ensures reconnect() starts schedules.

This test file covers the integration gap between IrrigationManager and
IrrigationController that allowed a bug where schedule tasks were never started
after system boot (commit c8a0841).

The key invariants tested:
1. First reconnect() call must start schedule tasks for all controllers.
2. Subsequent reconnect() calls must NOT restart schedule tasks.
3. Controllers without schedules are unaffected.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Pre-mock gpiod and submodules before any boneio import can trigger them.
# The conftest.py autouse fixture only mocks 'gpiod' but not 'gpiod.line',
# and fixtures run after collection-time imports. Since our helper does
# a lazy import of IrrigationManager (which transitively imports gpiod.line
# via the Manager __init__.py chain), we must mock all submodules here.
_gpiod_mock = MagicMock()
for mod in ("gpiod", "gpiod.line", "gpiod.chip", "gpiod.edge_event"):
    sys.modules.setdefault(mod, _gpiod_mock)

if TYPE_CHECKING:
    from boneio.core.manager.irrigation import IrrigationManager


def _mock_controller(
    ctrl_id: str = "ctrl_1",
    has_schedule: bool = True,
    schedule_tasks_running: bool = False,
) -> MagicMock:
    """Create a mock IrrigationController with controllable schedule state.

    Args:
        ctrl_id: Controller identifier.
        has_schedule: Whether the controller has schedule entries.
        schedule_tasks_running: Whether schedule tasks are already running.

    Returns:
        MagicMock mimicking IrrigationController interface.
    """
    ctrl = MagicMock()
    ctrl.id = ctrl_id
    ctrl._schedule = [{"time": "06:00", "days": "daily"}] if has_schedule else []
    ctrl._schedule_tasks = (
        {0: MagicMock()} if schedule_tasks_running else {}
    )
    ctrl.start_schedules = MagicMock()
    ctrl.publish_all_states = AsyncMock()
    ctrl.zones = []
    return ctrl


def _make_manager_with_controllers(
    controllers: dict[str, MagicMock],
) -> IrrigationManager:  # noqa: F821
    """Create an IrrigationManager with pre-injected controllers.

    Bypasses __init__ config parsing by creating the object without calling
    __init__ and injecting controllers and a mock manager directly.

    Args:
        controllers: Dict of controller_id -> mock controller.

    Returns:
        IrrigationManager with injected controllers.
    """
    from boneio.core.manager.irrigation import IrrigationManager as _IrrigationManager
    mgr = object.__new__(_IrrigationManager)
    mgr._controllers = controllers
    mgr._subscribed_topics = set()
    mgr._manager = MagicMock()
    mgr._manager.message_bus = MagicMock()
    mgr._manager.message_bus.subscribe_and_listen = AsyncMock()
    return mgr


class TestReconnectStartsSchedules:
    """Verify that reconnect() starts schedules on first connection."""

    async def test_first_reconnect_starts_schedule_tasks(self):
        """First reconnect() call must start schedule tasks for all controllers."""
        ctrl = _mock_controller(has_schedule=True, schedule_tasks_running=False)
        mgr = _make_manager_with_controllers({"ctrl_1": ctrl})

        await mgr.reconnect()

        ctrl.start_schedules.assert_called_once()
        ctrl.publish_all_states.assert_awaited_once()

    async def test_second_reconnect_does_not_restart_schedules(self):
        """Subsequent reconnect() calls must NOT restart schedule tasks."""
        ctrl = _mock_controller(has_schedule=True, schedule_tasks_running=True)
        mgr = _make_manager_with_controllers({"ctrl_1": ctrl})

        await mgr.reconnect()

        ctrl.start_schedules.assert_not_called()
        ctrl.publish_all_states.assert_awaited_once()

    async def test_first_then_second_reconnect(self):
        """Simulate full lifecycle: first connect starts, second doesn't restart."""
        ctrl = _mock_controller(has_schedule=True, schedule_tasks_running=False)
        mgr = _make_manager_with_controllers({"ctrl_1": ctrl})

        # First connect
        await mgr.reconnect()
        ctrl.start_schedules.assert_called_once()

        # Simulate tasks now running (as start_schedules() would do)
        ctrl._schedule_tasks = {0: MagicMock()}
        ctrl.start_schedules.reset_mock()

        # Second connect (MQTT reconnect)
        await mgr.reconnect()
        ctrl.start_schedules.assert_not_called()

    async def test_controller_without_schedule_not_started(self):
        """Controllers with no schedule should never have start_schedules called."""
        ctrl = _mock_controller(has_schedule=False, schedule_tasks_running=False)
        mgr = _make_manager_with_controllers({"ctrl_1": ctrl})

        await mgr.reconnect()

        ctrl.start_schedules.assert_not_called()
        ctrl.publish_all_states.assert_awaited_once()

    async def test_multiple_controllers_all_started_on_first_connect(self):
        """All controllers with schedules should start on first connection."""
        ctrl_a = _mock_controller("ctrl_a", has_schedule=True, schedule_tasks_running=False)
        ctrl_b = _mock_controller("ctrl_b", has_schedule=True, schedule_tasks_running=False)
        ctrl_c = _mock_controller("ctrl_c", has_schedule=False, schedule_tasks_running=False)

        mgr = _make_manager_with_controllers({
            "ctrl_a": ctrl_a,
            "ctrl_b": ctrl_b,
            "ctrl_c": ctrl_c,
        })

        await mgr.reconnect()

        ctrl_a.start_schedules.assert_called_once()
        ctrl_b.start_schedules.assert_called_once()
        ctrl_c.start_schedules.assert_not_called()

    async def test_mixed_state_controllers_on_reconnect(self):
        """If one controller has tasks and another doesn't, only the missing one starts."""
        ctrl_running = _mock_controller("ctrl_running", has_schedule=True, schedule_tasks_running=True)
        ctrl_new = _mock_controller("ctrl_new", has_schedule=True, schedule_tasks_running=False)

        mgr = _make_manager_with_controllers({
            "ctrl_running": ctrl_running,
            "ctrl_new": ctrl_new,
        })

        await mgr.reconnect()

        # first_connect is True because ctrl_new has schedule but no tasks
        # But only ctrl_new should actually get start_schedules called
        ctrl_running.start_schedules.assert_not_called()
        ctrl_new.start_schedules.assert_called_once()


class TestReconnectPublishesStates:
    """Verify that reconnect() always publishes states regardless of schedule status."""

    async def test_states_published_on_first_connect(self):
        """States should be published on first connection."""
        ctrl = _mock_controller(has_schedule=True, schedule_tasks_running=False)
        mgr = _make_manager_with_controllers({"ctrl_1": ctrl})

        await mgr.reconnect()
        ctrl.publish_all_states.assert_awaited_once()

    async def test_states_published_on_reconnect(self):
        """States should be published on reconnection too."""
        ctrl = _mock_controller(has_schedule=True, schedule_tasks_running=True)
        mgr = _make_manager_with_controllers({"ctrl_1": ctrl})

        await mgr.reconnect()
        ctrl.publish_all_states.assert_awaited_once()

    async def test_states_published_no_schedule(self):
        """States published even for controllers without schedules."""
        ctrl = _mock_controller(has_schedule=False)
        mgr = _make_manager_with_controllers({"ctrl_1": ctrl})

        await mgr.reconnect()
        ctrl.publish_all_states.assert_awaited_once()
