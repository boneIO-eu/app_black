"""Tests for delayed action execution and cancellation.

Covers the delay/delay_cancel_on system used by motion sensor patterns:
- execute_actions with delay schedules a task instead of executing immediately
- cancel_delayed_actions cancels all pending tasks for an input
- InputManager._cancel_delayed_if_matching cancels when event matches delay_cancel_on
- _execute_single_action dispatches each action type correctly
"""

from __future__ import annotations

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mock gpiod before importing boneio modules
mock_gpiod = MagicMock()
mock_gpiod.line = MagicMock()
mock_gpiod.line.Bias = MagicMock()
mock_gpiod.line.Direction = MagicMock()
mock_gpiod.line.Edge = MagicMock()
mock_gpiod.EdgeEvent = MagicMock()
mock_gpiod.LineRequest = MagicMock()
sys.modules.setdefault("gpiod", mock_gpiod)
sys.modules.setdefault("gpiod.line", mock_gpiod.line)

from boneio.const import INPUT_SENSOR, PRESSED, RELEASED
from boneio.models import InputState
from boneio.models.events import InputEvent


class MockInput:
    """Minimal mock of a binary sensor input for testing delay cancel logic."""

    def __init__(self, id: str, name: str, actions: dict | None = None):
        self._id = id
        self._name = name
        self._input_type = INPUT_SENSOR
        self._actions = actions or {}
        self._mqtt_sequences = {}

    @property
    def id(self) -> str:
        return self._id

    @property
    def name(self) -> str:
        return self._name

    @property
    def input_type(self) -> str:
        return self._input_type

    @property
    def mqtt_sequences(self) -> dict:
        return self._mqtt_sequences

    def get_actions_of_click(self, click_type: str) -> list:
        return self._actions.get(click_type, [])

    def should_publish_sequence_to_mqtt(self, sequence_type: str) -> bool:
        return False


def _make_event(entity_id: str, click_type: str) -> InputEvent:
    """Helper to create an InputEvent for testing."""
    return InputEvent(
        entity_id=entity_id,
        click_type=click_type,
        duration=None,
        state=InputState(
            name="Test",
            pin="P8_30",
            state=click_type,
            type=INPUT_SENSOR,
            timestamp=1234567890.0,
            boneio_input=entity_id,
            area=None,
        ),
    )


# ---------------------------------------------------------------------------
# Manager.execute_actions — delay support
# ---------------------------------------------------------------------------


class TestExecuteActionsDelay:
    """Tests for Manager.execute_actions with delay field."""

    @pytest.fixture
    def manager(self):
        """Create a minimal Manager mock with the real execute_actions method."""
        from boneio.core.manager.manager import Manager

        mgr = MagicMock(spec=Manager)
        mgr._pending_delayed_actions = {}
        mgr.send_message = MagicMock()
        mgr.outputs = MagicMock()
        mgr.covers = MagicMock()
        mgr.remote_devices = MagicMock()

        # Bind real methods
        mgr.execute_actions = Manager.execute_actions.__get__(mgr, Manager)
        mgr._execute_single_action = Manager._execute_single_action.__get__(mgr, Manager)
        mgr._run_delayed_action = Manager._run_delayed_action.__get__(mgr, Manager)
        mgr.cancel_delayed_actions = Manager.cancel_delayed_actions.__get__(mgr, Manager)
        mgr._resolve_entity_state = MagicMock(return_value=None)
        return mgr

    @pytest.mark.asyncio
    async def test_action_without_delay_executes_immediately(self, manager):
        """Actions without delay field should execute immediately."""
        mock_output = MagicMock()
        mock_output.name = "OUT_01"
        mock_output.turn_on = AsyncMock()
        manager.outputs.get_output.return_value = mock_output
        manager.outputs.get_output_group.return_value = None

        actions = [{"action": "output", "pin": "OUT_01", "action_to_execute": "turn_on"}]
        executed = await manager.execute_actions(actions=actions, input_id="in_01")

        assert 0 in executed
        mock_output.turn_on.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_action_with_delay_schedules_task(self, manager):
        """Actions with delay should schedule a task, not execute immediately."""
        mock_output = MagicMock()
        mock_output.name = "OUT_01"
        mock_output.turn_off = AsyncMock()
        manager.outputs.get_output.return_value = mock_output
        manager.outputs.get_output_group.return_value = None

        actions = [
            {
                "action": "output",
                "pin": "OUT_01",
                "action_to_execute": "turn_off",
                "delay": 120.0,  # 2 minutes
            }
        ]

        executed = await manager.execute_actions(actions=actions, input_id="motion_01")

        # Action should NOT be in executed set (it's pending)
        assert 0 not in executed
        # Should NOT have been called yet
        mock_output.turn_off.assert_not_awaited()
        # Should have a pending task
        assert "motion_01" in manager._pending_delayed_actions
        assert len(manager._pending_delayed_actions["motion_01"]) == 1

        # Clean up
        for task in manager._pending_delayed_actions.get("motion_01", []):
            task.cancel()
        await asyncio.sleep(0.01)

    @pytest.mark.asyncio
    async def test_action_with_delay_no_input_id_executes_immediately(self, manager):
        """Delay is ignored when input_id is not provided (e.g. test-action API)."""
        mock_output = MagicMock()
        mock_output.name = "OUT_01"
        mock_output.turn_off = AsyncMock()
        manager.outputs.get_output.return_value = mock_output
        manager.outputs.get_output_group.return_value = None

        actions = [
            {
                "action": "output",
                "pin": "OUT_01",
                "action_to_execute": "turn_off",
                "delay": 120.0,
            }
        ]

        # No input_id => delay should be ignored
        executed = await manager.execute_actions(actions=actions)

        assert 0 in executed
        mock_output.turn_off.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delayed_action_executes_after_sleep(self, manager):
        """Delayed action should execute after the sleep completes."""
        mock_output = MagicMock()
        mock_output.name = "OUT_01"
        mock_output.turn_off = AsyncMock()
        manager.outputs.get_output.return_value = mock_output
        manager.outputs.get_output_group.return_value = None

        actions = [
            {
                "action": "output",
                "pin": "OUT_01",
                "action_to_execute": "turn_off",
                "delay": 0.05,  # 50ms for fast test
            }
        ]

        await manager.execute_actions(actions=actions, input_id="motion_01")
        mock_output.turn_off.assert_not_awaited()

        # Wait for the delay to complete
        await asyncio.sleep(0.15)

        mock_output.turn_off.assert_awaited_once()
        # Pending tasks should be cleaned up
        assert "motion_01" not in manager._pending_delayed_actions


# ---------------------------------------------------------------------------
# Manager.cancel_delayed_actions
# ---------------------------------------------------------------------------


class TestCancelDelayedActions:
    """Tests for Manager.cancel_delayed_actions."""

    @pytest.fixture
    def manager(self):
        from boneio.core.manager.manager import Manager

        mgr = MagicMock(spec=Manager)
        mgr._pending_delayed_actions = {}
        mgr.cancel_delayed_actions = Manager.cancel_delayed_actions.__get__(mgr, Manager)
        return mgr

    def test_cancel_with_no_pending_returns_zero(self, manager):
        """Cancelling with no pending tasks should return 0."""
        result = manager.cancel_delayed_actions("unknown_input")
        assert result == 0

    def test_cancel_pending_tasks(self, manager):
        """Should cancel all pending tasks for the input and return count."""
        task1 = MagicMock()
        task1.done.return_value = False
        task2 = MagicMock()
        task2.done.return_value = False
        manager._pending_delayed_actions["in_01"] = [task1, task2]

        result = manager.cancel_delayed_actions("in_01")

        assert result == 2
        task1.cancel.assert_called_once()
        task2.cancel.assert_called_once()
        assert "in_01" not in manager._pending_delayed_actions

    def test_cancel_skips_done_tasks(self, manager):
        """Tasks that are already done should not be cancelled."""
        done_task = MagicMock()
        done_task.done.return_value = True
        pending_task = MagicMock()
        pending_task.done.return_value = False
        manager._pending_delayed_actions["in_01"] = [done_task, pending_task]

        result = manager.cancel_delayed_actions("in_01")

        assert result == 1
        done_task.cancel.assert_not_called()
        pending_task.cancel.assert_called_once()


# ---------------------------------------------------------------------------
# Manager._run_delayed_action — cancellation handling
# ---------------------------------------------------------------------------


class TestRunDelayedAction:
    """Tests for Manager._run_delayed_action."""

    @pytest.fixture
    def manager(self):
        from boneio.core.manager.manager import Manager

        mgr = MagicMock(spec=Manager)
        mgr._pending_delayed_actions = {}
        mgr._execute_single_action = AsyncMock()
        mgr._run_delayed_action = Manager._run_delayed_action.__get__(mgr, Manager)
        return mgr

    @pytest.mark.asyncio
    async def test_cancelled_task_does_not_execute(self, manager):
        """A cancelled delayed action should not execute _execute_single_action."""
        action_def = {"action": "output", "pin": "OUT_01", "action_to_execute": "turn_off"}

        task = asyncio.create_task(manager._run_delayed_action("in_01", action_def, 10.0))
        manager._pending_delayed_actions["in_01"] = [task]

        await asyncio.sleep(0.01)
        task.cancel()
        await asyncio.sleep(0.01)

        manager._execute_single_action.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_completed_task_executes_action(self, manager):
        """A non-cancelled delayed action should execute _execute_single_action."""
        action_def = {"action": "output", "pin": "OUT_01", "action_to_execute": "turn_off"}

        task = asyncio.create_task(manager._run_delayed_action("in_01", action_def, 0.02))
        manager._pending_delayed_actions["in_01"] = [task]

        await asyncio.sleep(0.1)

        manager._execute_single_action.assert_awaited_once_with(action_def)

    @pytest.mark.asyncio
    async def test_cleanup_removes_done_tasks(self, manager):
        """After execution, the task should be cleaned up from pending list."""
        action_def = {"action": "output", "pin": "OUT_01", "action_to_execute": "turn_off"}

        task = asyncio.create_task(manager._run_delayed_action("in_01", action_def, 0.02))
        manager._pending_delayed_actions["in_01"] = [task]

        await asyncio.sleep(0.1)

        # Should have been cleaned up
        assert "in_01" not in manager._pending_delayed_actions


# ---------------------------------------------------------------------------
# InputManager._cancel_delayed_if_matching
# ---------------------------------------------------------------------------


class TestCancelDelayedIfMatching:
    """Tests for InputManager._cancel_delayed_if_matching."""

    @pytest.fixture
    def mock_manager(self):
        manager = MagicMock()
        manager.send_message = MagicMock()
        manager._config_helper = MagicMock()
        manager._config_helper.topic_prefix = "boneio"
        manager.execute_actions = AsyncMock(return_value=set())
        manager._pending_delayed_actions = {}
        manager.cancel_delayed_actions = MagicMock(return_value=0)
        return manager

    @pytest.fixture
    def input_manager(self, mock_manager):
        from boneio.core.manager.inputs import InputManager

        with patch.object(InputManager, "_configure_inputs"):
            with patch.object(InputManager, "__init__", lambda self, *args, **kwargs: None):
                im = InputManager.__new__(InputManager)
                im._manager = mock_manager
                im._inputs = {}
                im._event_pins = []
                im._binary_pins = []
                im._long_press_mqtt_last_ts = {}
                return im

    def test_no_pending_tasks_does_nothing(self, input_manager, mock_manager):
        """When no pending tasks exist, cancel should not be called."""
        sensor = MockInput(
            id="in_01",
            name="Motion",
            actions={
                RELEASED: [{"action": "output", "pin": "OUT_01", "delay": 120, "delay_cancel_on": ["pressed"]}],
            },
        )

        input_manager._cancel_delayed_if_matching(sensor, "in_01", PRESSED)
        mock_manager.cancel_delayed_actions.assert_not_called()

    def test_matching_event_cancels_pending(self, input_manager, mock_manager):
        """When pending tasks exist and event matches delay_cancel_on, cancel should be called."""
        sensor = MockInput(
            id="in_01",
            name="Motion",
            actions={
                PRESSED: [{"action": "output", "pin": "OUT_01", "action_to_execute": "turn_on"}],
                RELEASED: [{"action": "output", "pin": "OUT_01", "delay": 120, "delay_cancel_on": ["pressed"]}],
            },
        )

        # Simulate pending task
        mock_manager._pending_delayed_actions["in_01"] = [MagicMock()]

        input_manager._cancel_delayed_if_matching(sensor, "in_01", PRESSED)
        mock_manager.cancel_delayed_actions.assert_called_once_with("in_01")

    def test_non_matching_event_does_not_cancel(self, input_manager, mock_manager):
        """When event does not match any delay_cancel_on, cancel should not be called."""
        sensor = MockInput(
            id="in_01",
            name="Motion",
            actions={
                PRESSED: [{"action": "output", "pin": "OUT_01"}],
                RELEASED: [{"action": "output", "pin": "OUT_01", "delay": 120, "delay_cancel_on": ["pressed"]}],
            },
        )

        # Simulate pending task
        mock_manager._pending_delayed_actions["in_01"] = [MagicMock()]

        # "released" is NOT in delay_cancel_on (only "pressed" is)
        input_manager._cancel_delayed_if_matching(sensor, "in_01", RELEASED)
        mock_manager.cancel_delayed_actions.assert_not_called()


# ---------------------------------------------------------------------------
# Integration: handle_input_event with delay flow
# ---------------------------------------------------------------------------


class TestHandleInputEventDelayIntegration:
    """Integration tests for the full delay flow through handle_input_event."""

    @pytest.fixture
    def mock_manager(self):
        manager = MagicMock()
        manager.send_message = MagicMock()
        manager._config_helper = MagicMock()
        manager._config_helper.topic_prefix = "boneio"
        manager.execute_actions = AsyncMock(return_value=set())
        manager.templates = MagicMock()
        manager.templates.on_input_event = MagicMock()
        manager._pending_delayed_actions = {}
        manager.cancel_delayed_actions = MagicMock(return_value=0)
        return manager

    @pytest.fixture
    def input_manager(self, mock_manager):
        from boneio.core.manager.inputs import InputManager

        with patch.object(InputManager, "_configure_inputs"):
            with patch.object(InputManager, "__init__", lambda self, *args, **kwargs: None):
                im = InputManager.__new__(InputManager)
                im._manager = mock_manager
                im._inputs = {}
                im._event_pins = []
                im._binary_pins = []
                im._long_press_mqtt_last_ts = {}
                return im

    @pytest.mark.asyncio
    async def test_pressed_event_passes_input_id(self, input_manager, mock_manager):
        """handle_input_event should pass input_id to execute_actions."""
        sensor = MockInput(
            id="motion_01",
            name="PIR",
            actions={
                PRESSED: [{"action": "output", "pin": "OUT_01", "action_to_execute": "turn_on"}],
            },
        )
        input_manager._inputs["motion_01"] = sensor

        event = _make_event("motion_01", PRESSED)
        await input_manager.handle_input_event(event)

        mock_manager.execute_actions.assert_called_once()
        call_kwargs = mock_manager.execute_actions.call_args.kwargs
        assert call_kwargs["input_id"] == "motion_01"

    @pytest.mark.asyncio
    async def test_released_cancels_then_executes(self, input_manager, mock_manager):
        """Released event should first check cancel, then execute actions."""
        sensor = MockInput(
            id="motion_01",
            name="PIR",
            actions={
                PRESSED: [{"action": "output", "pin": "OUT_01", "action_to_execute": "turn_on"}],
                RELEASED: [
                    {
                        "action": "output",
                        "pin": "OUT_01",
                        "action_to_execute": "turn_off",
                        "delay": 120,
                        "delay_cancel_on": ["pressed"],
                    }
                ],
            },
        )
        input_manager._inputs["motion_01"] = sensor

        event = _make_event("motion_01", RELEASED)
        await input_manager.handle_input_event(event)

        # Should have called execute_actions with the released actions
        mock_manager.execute_actions.assert_called_once()
        call_kwargs = mock_manager.execute_actions.call_args.kwargs
        assert call_kwargs["input_id"] == "motion_01"

    @pytest.mark.asyncio
    async def test_pressed_cancels_pending_delayed(self, input_manager, mock_manager):
        """Pressed event should cancel pending delayed OFF actions."""
        sensor = MockInput(
            id="motion_01",
            name="PIR",
            actions={
                PRESSED: [{"action": "output", "pin": "OUT_01", "action_to_execute": "turn_on"}],
                RELEASED: [
                    {
                        "action": "output",
                        "pin": "OUT_01",
                        "action_to_execute": "turn_off",
                        "delay": 120,
                        "delay_cancel_on": ["pressed"],
                    }
                ],
            },
        )
        input_manager._inputs["motion_01"] = sensor

        # Simulate a pending delayed task from a previous "released" event
        mock_manager._pending_delayed_actions["motion_01"] = [MagicMock()]

        event = _make_event("motion_01", PRESSED)
        await input_manager.handle_input_event(event)

        # The cancel should have been called
        mock_manager.cancel_delayed_actions.assert_called_once_with("motion_01")
