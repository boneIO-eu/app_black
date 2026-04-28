"""Unit tests for Manager.republish_all_entity_states.

Tests verify that after HA discovery re-send, the system correctly
re-publishes current entity states to MQTT (only) so Home Assistant
doesn't show 'unknown' for entities. WebSocket/EventBus must NOT
be triggered to avoid unnecessary frontend state churn.
"""

from __future__ import annotations

import asyncio
import json
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
sys.modules["gpiod"] = mock_gpiod
sys.modules["gpiod.line"] = mock_gpiod.line


def _make_mock_output(output_id: str, output_type: str = "switch", is_active: bool = False) -> MagicMock:
    """Create a mock output.

    Args:
        output_id: Output identifier.
        output_type: HA entity type (switch, light, etc.).
        is_active: Whether output is currently on.

    Returns:
        Mock output with id, output_type, and is_active.
    """
    output = MagicMock()
    output.id = output_id
    output.output_type = output_type
    output.is_active = is_active
    return output


def _make_mock_cover(cover_id: str, state: str = "open", position: int = 100) -> MagicMock:
    """Create a mock cover.

    Args:
        cover_id: Cover identifier.
        state: Current state (open/closed/opening/closing).
        position: Current position (0-100).

    Returns:
        Mock cover with id, state, json_position.
    """
    cover = MagicMock()
    cover.id = cover_id
    cover.state = state
    cover.json_position = {"position": position}
    return cover


def _make_mock_manager() -> MagicMock:
    """Create a mock Manager with all required sub-managers.

    Returns:
        MagicMock mimicking the Manager class with outputs, covers,
        inputs, sensors, and message_bus for MQTT-only publishing.
    """
    manager = MagicMock()
    manager._config_helper = MagicMock()
    manager._config_helper.topic_prefix = "boneio"
    manager._message_bus = MagicMock()
    manager.send_message = MagicMock()
    manager._event_bus = MagicMock()
    manager.loop = asyncio.new_event_loop()

    # Outputs sub-manager (empty by default)
    manager.outputs = MagicMock()
    manager.outputs.get_all_outputs.return_value = {}
    manager.outputs.get_all_output_groups.return_value = {}

    # Covers sub-manager (empty by default)
    manager.covers = MagicMock()
    manager.covers.get_all_covers.return_value = {}

    # Inputs sub-manager (empty by default)
    manager.inputs = MagicMock()
    manager.inputs.get_all_inputs.return_value = {}

    # Sensors sub-manager
    manager.sensors = MagicMock()
    manager.sensors.get_all_temp_sensors.return_value = []

    # _republish_sensor_states_mqtt is an async method called internally
    manager._republish_sensor_states_mqtt = AsyncMock()

    return manager


class TestRepublishAllEntityStates:
    """Tests for Manager.republish_all_entity_states — MQTT-only publishing."""

    @pytest.fixture
    def event_loop(self):
        """Provide an event loop for tests that need asyncio."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        yield loop
        loop.close()

    def test_output_state_published_to_mqtt(self, event_loop):
        """Test that output ON/OFF state is published directly to MQTT."""
        from boneio.core.manager.manager import Manager

        manager = _make_mock_manager()
        output = _make_mock_output("OUT_01", is_active=True)
        manager.outputs.get_all_outputs.return_value = {"OUT_01": output}

        event_loop.run_until_complete(Manager.republish_all_entity_states(manager))

        # Should publish to MQTT via message_bus, NOT via EventBus
        manager._message_bus.send_message.assert_any_call(
            topic="boneio/output/OUT_01",
            payload={"state": "ON"},
            retain=True,
        )

    def test_output_off_state_published(self, event_loop):
        """Test that OFF outputs correctly publish OFF state."""
        from boneio.core.manager.manager import Manager

        manager = _make_mock_manager()
        output = _make_mock_output("OUT_02", is_active=False)
        manager.outputs.get_all_outputs.return_value = {"OUT_02": output}

        event_loop.run_until_complete(Manager.republish_all_entity_states(manager))

        manager._message_bus.send_message.assert_any_call(
            topic="boneio/output/OUT_02",
            payload={"state": "OFF"},
            retain=True,
        )

    def test_cover_outputs_skipped(self, event_loop):
        """Test that COVER-type outputs are NOT re-published (they have their own path)."""
        from boneio.core.manager.manager import Manager

        manager = _make_mock_manager()
        cover_output = _make_mock_output("COVER_RELAY", output_type="cover")
        manager.outputs.get_all_outputs.return_value = {"COVER_RELAY": cover_output}

        event_loop.run_until_complete(Manager.republish_all_entity_states(manager))

        # message_bus should NOT be called for cover output state
        # (only for cover position/state topics and online status)
        for call in manager._message_bus.send_message.call_args_list:
            topic = call.kwargs.get("topic") or call.args[0] if call.args else call.kwargs.get("topic")
            assert "output/COVER_RELAY" not in str(topic)

    def test_cover_state_published_to_mqtt(self, event_loop):
        """Test that cover state + position are published to MQTT."""
        from boneio.core.manager.manager import Manager

        manager = _make_mock_manager()
        cover = _make_mock_cover("my_cover", state="open", position=75)
        manager.covers.get_all_covers.return_value = {"my_cover": cover}

        event_loop.run_until_complete(Manager.republish_all_entity_states(manager))

        manager._message_bus.send_message.assert_any_call(
            topic="boneio/cover/my_cover/state",
            payload="open",
        )
        manager._message_bus.send_message.assert_any_call(
            topic="boneio/cover/my_cover/pos",
            payload=json.dumps({"position": 75}),
        )

    def test_no_eventbus_triggered(self, event_loop):
        """Test that EventBus is NOT triggered (no WebSocket noise)."""
        from boneio.core.manager.manager import Manager

        manager = _make_mock_manager()
        output = _make_mock_output("OUT_01", is_active=True)
        manager.outputs.get_all_outputs.return_value = {"OUT_01": output}
        cover = _make_mock_cover("my_cover")
        manager.covers.get_all_covers.return_value = {"my_cover": cover}

        event_loop.run_until_complete(Manager.republish_all_entity_states(manager))

        # EventBus trigger_event should NOT be called
        manager._event_bus.trigger_event.assert_not_called()

    def test_online_status_published(self, event_loop):
        """Test that online status is published."""
        from boneio.core.manager.manager import Manager

        manager = _make_mock_manager()

        event_loop.run_until_complete(Manager.republish_all_entity_states(manager))

        manager.send_message.assert_called_with(
            topic="boneio/state",
            payload="online",
            retain=True,
        )

    def test_group_state_published(self, event_loop):
        """Test that output group states are published."""
        from boneio.core.manager.manager import Manager

        manager = _make_mock_manager()
        group = MagicMock()
        group.id = "group_1"
        group.is_active = True
        manager.outputs.get_all_output_groups.return_value = {"group_1": group}

        event_loop.run_until_complete(Manager.republish_all_entity_states(manager))

        manager._message_bus.send_message.assert_any_call(
            topic="boneio/output/group_1",
            payload={"state": "ON"},
            retain=True,
        )


class TestRepublishBinarySensorStates:
    """Tests for Manager._republish_binary_sensor_states method."""

    @pytest.fixture
    def event_loop(self):
        """Provide an event loop for tests that need asyncio."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        yield loop
        loop.close()

    def test_binary_sensor_state_published_to_mqtt(self, event_loop):
        """Test that binary sensor states are published to MQTT."""
        from boneio.components.input.binary_sensor import GpioInputBinarySensor
        from boneio.core.manager.manager import Manager

        manager = _make_mock_manager()

        binary_sensor = MagicMock(spec=GpioInputBinarySensor)
        binary_sensor.last_state = "pressed"

        manager.inputs.get_all_inputs.return_value = {
            "sensor_1": binary_sensor,
        }

        Manager._republish_binary_sensor_states(manager)

        manager.send_message.assert_called_with(
            topic="boneio/input/sensor_1",
            payload="pressed",
        )

    def test_binary_sensor_no_state_skipped(self, event_loop):
        """Test that binary sensors with no state are skipped."""
        from boneio.components.input.binary_sensor import GpioInputBinarySensor
        from boneio.core.manager.manager import Manager

        manager = _make_mock_manager()

        binary_sensor = MagicMock(spec=GpioInputBinarySensor)
        binary_sensor.last_state = None

        manager.inputs.get_all_inputs.return_value = {
            "sensor_1": binary_sensor,
        }

        Manager._republish_binary_sensor_states(manager)

        manager.send_message.assert_not_called()

    def test_event_inputs_not_published(self, event_loop):
        """Test that event-type inputs (not binary sensors) are NOT re-published."""
        from boneio.core.manager.manager import Manager

        manager = _make_mock_manager()

        event_input = MagicMock()
        event_input.last_state = "single"

        manager.inputs.get_all_inputs.return_value = {
            "event_1": event_input,
        }

        Manager._republish_binary_sensor_states(manager)

        manager.send_message.assert_not_called()

    def test_multiple_binary_sensors_published(self, event_loop):
        """Test that multiple binary sensors are all published."""
        from boneio.components.input.binary_sensor import GpioInputBinarySensor
        from boneio.core.manager.manager import Manager

        manager = _make_mock_manager()

        sensor_a = MagicMock(spec=GpioInputBinarySensor)
        sensor_a.last_state = "pressed"
        sensor_b = MagicMock(spec=GpioInputBinarySensor)
        sensor_b.last_state = "released"

        manager.inputs.get_all_inputs.return_value = {
            "sensor_a": sensor_a,
            "sensor_b": sensor_b,
        }

        Manager._republish_binary_sensor_states(manager)

        assert manager.send_message.call_count == 2

    def test_binary_sensor_error_does_not_crash(self, event_loop):
        """Test that an error in one sensor doesn't prevent others from publishing."""
        from boneio.components.input.binary_sensor import GpioInputBinarySensor
        from boneio.core.manager.manager import Manager

        manager = _make_mock_manager()

        sensor_ok = MagicMock(spec=GpioInputBinarySensor)
        sensor_ok.last_state = "pressed"

        sensor_bad = MagicMock(spec=GpioInputBinarySensor)
        type(sensor_bad).last_state = property(lambda self: (_ for _ in ()).throw(RuntimeError("GPIO error")))

        manager.inputs.get_all_inputs.return_value = {
            "sensor_bad": sensor_bad,
            "sensor_ok": sensor_ok,
        }

        # Should not raise
        Manager._republish_binary_sensor_states(manager)

        manager.send_message.assert_called_once_with(
            topic="boneio/input/sensor_ok",
            payload="pressed",
        )
