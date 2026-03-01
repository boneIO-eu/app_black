"""Unit tests for InputManager MQTT publishing.

These tests verify that binary sensor and event button events
are correctly published to MQTT.

Note: These tests mock hardware dependencies (gpiod) to run on non-BeagleBone systems.
"""

from __future__ import annotations

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
sys.modules['gpiod'] = mock_gpiod
sys.modules['gpiod.line'] = mock_gpiod.line

from boneio.const import INPUT, INPUT_SENSOR, PRESSED, RELEASED
from boneio.models import InputState
from boneio.models.events import InputEvent


class MockInput:
    """Mock input device for testing."""
    
    def __init__(
        self,
        id: str,
        name: str,
        input_type: str,
        mqtt_sequences: dict | None = None,
    ):
        self._id = id
        self._name = name
        self._input_type = input_type
        self._actions = {}
        self._mqtt_sequences = mqtt_sequences or {}
    
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
        return self._mqtt_sequences.get(sequence_type, False)


class TestInputManagerMQTTPublish:
    """Tests for InputManager._publish_input_event_to_mqtt method."""

    @pytest.fixture
    def mock_manager(self):
        """Create a mock Manager with send_message capability."""
        manager = MagicMock()
        manager.send_message = MagicMock()
        manager._config_helper = MagicMock()
        manager._config_helper.topic_prefix = "boneio"
        return manager

    @pytest.fixture
    def input_manager(self, mock_manager):
        """Create InputManager with mocked dependencies."""
        from boneio.core.manager.inputs import InputManager
        
        with patch.object(InputManager, '_configure_inputs'):
            with patch.object(InputManager, '__init__', lambda self, *args, **kwargs: None):
                im = InputManager.__new__(InputManager)
                im._manager = mock_manager
                im._inputs = {}
                im._event_pins = []
                im._binary_pins = []
                im._long_press_mqtt_last_ts = {}
                return im

    def test_binary_sensor_publishes_pressed_state(self, input_manager, mock_manager):
        """Test that binary sensor publishes 'pressed' state to MQTT."""
        # Setup
        binary_sensor = MockInput(
            id="in_01",
            name="Test Sensor",
            input_type=INPUT_SENSOR,
        )
        input_manager._inputs["in_01"] = binary_sensor
        
        event = InputEvent(
            entity_id="in_01",
            click_type=PRESSED,
            duration=None,
            state=InputState(
                name="Test Sensor",
                pin="P8_30",
                state=PRESSED,
                type=INPUT_SENSOR,
                timestamp=1234567890.0,
                boneio_input="in_01",
                area=None,
            ),
        )
        
        # Execute
        input_manager._publish_input_event_to_mqtt(binary_sensor, event)
        
        # Verify
        mock_manager.send_message.assert_called_once_with(
            topic="boneio/input/in_01",
            payload="pressed",
        )

    def test_binary_sensor_publishes_released_state(self, input_manager, mock_manager):
        """Test that binary sensor publishes 'released' state to MQTT."""
        # Setup
        binary_sensor = MockInput(
            id="in_01",
            name="Test Sensor",
            input_type=INPUT_SENSOR,
        )
        input_manager._inputs["in_01"] = binary_sensor
        
        event = InputEvent(
            entity_id="in_01",
            click_type=RELEASED,
            duration=None,
            state=InputState(
                name="Test Sensor",
                pin="P8_30",
                state=RELEASED,
                type=INPUT_SENSOR,
                timestamp=1234567890.0,
                boneio_input="in_01",
                area=None,
            ),
        )
        
        # Execute
        input_manager._publish_input_event_to_mqtt(binary_sensor, event)
        
        # Verify
        mock_manager.send_message.assert_called_once_with(
            topic="boneio/input/in_01",
            payload="released",
        )

    def test_event_button_publishes_json_event(self, input_manager, mock_manager):
        """Test that event button publishes JSON event to MQTT."""
        import json
        
        # Setup
        event_button = MockInput(
            id="btn_01",
            name="Test Button",
            input_type=INPUT,
        )
        input_manager._inputs["btn_01"] = event_button
        
        event = InputEvent(
            entity_id="btn_01",
            click_type="single",
            duration=None,
            state=InputState(
                name="Test Button",
                pin="P8_30",
                state="single",
                type=INPUT,
                timestamp=1234567890.0,
                boneio_input="btn_01",
                area=None,
            ),
        )
        
        # Execute
        input_manager._publish_input_event_to_mqtt(event_button, event)
        
        # Verify
        mock_manager.send_message.assert_called_once()
        call_args = mock_manager.send_message.call_args
        assert call_args.kwargs["topic"] == "boneio/input/btn_01"
        
        payload = json.loads(call_args.kwargs["payload"])
        assert payload["event_type"] == "single"

    def test_event_button_publishes_long_with_duration(self, input_manager, mock_manager):
        """Test that long press event includes duration in payload."""
        import json
        
        # Setup
        event_button = MockInput(
            id="btn_01",
            name="Test Button",
            input_type=INPUT,
        )
        input_manager._inputs["btn_01"] = event_button
        
        event = InputEvent(
            entity_id="btn_01",
            click_type="long",
            duration=1.5,
            state=InputState(
                name="Test Button",
                pin="P8_30",
                state="long",
                type=INPUT,
                timestamp=1234567890.0,
                boneio_input="btn_01",
                area=None,
            ),
        )
        
        # Execute
        input_manager._publish_input_event_to_mqtt(event_button, event)
        
        # Verify
        call_args = mock_manager.send_message.call_args
        payload = json.loads(call_args.kwargs["payload"])
        assert payload["event_type"] == "long"
        assert payload["duration"] == 1.5

    def test_sequence_not_published_when_not_enabled(self, input_manager, mock_manager):
        """Test that sequence events are not published when not enabled in mqtt_sequences."""
        # Setup
        event_button = MockInput(
            id="btn_01",
            name="Test Button",
            input_type=INPUT,
            mqtt_sequences={},  # No sequences enabled
        )
        input_manager._inputs["btn_01"] = event_button
        
        event = InputEvent(
            entity_id="btn_01",
            click_type="double_then_long",
            duration=None,
            state=InputState(
                name="Test Button",
                pin="P8_30",
                state="double_then_long",
                type=INPUT,
                timestamp=1234567890.0,
                boneio_input="btn_01",
                area=None,
            ),
        )
        
        # Execute
        input_manager._publish_input_event_to_mqtt(event_button, event)
        
        # Verify - should NOT publish
        mock_manager.send_message.assert_not_called()

    def test_sequence_published_when_enabled(self, input_manager, mock_manager):
        """Test that sequence events are published when enabled in mqtt_sequences."""
        import json
        
        # Setup
        event_button = MockInput(
            id="btn_01",
            name="Test Button",
            input_type=INPUT,
            mqtt_sequences={"double_then_long": True},
        )
        input_manager._inputs["btn_01"] = event_button
        
        event = InputEvent(
            entity_id="btn_01",
            click_type="double_then_long",
            duration=None,
            state=InputState(
                name="Test Button",
                pin="P8_30",
                state="double_then_long",
                type=INPUT,
                timestamp=1234567890.0,
                boneio_input="btn_01",
                area=None,
            ),
        )
        
        # Execute
        input_manager._publish_input_event_to_mqtt(event_button, event)
        
        # Verify - should publish
        mock_manager.send_message.assert_called_once()
        call_args = mock_manager.send_message.call_args
        payload = json.loads(call_args.kwargs["payload"])
        assert payload["event_type"] == "double_then_long"


class TestInputManagerHandleEvent:
    """Tests for InputManager.handle_input_event method."""

    @pytest.fixture
    def mock_manager(self):
        """Create a mock Manager."""
        manager = MagicMock()
        manager.send_message = MagicMock()
        manager._config_helper = MagicMock()
        manager._config_helper.topic_prefix = "boneio"
        manager.execute_actions = AsyncMock(return_value=set())
        return manager

    @pytest.fixture
    def input_manager(self, mock_manager):
        """Create InputManager with mocked dependencies."""
        from boneio.core.manager.inputs import InputManager
        
        with patch.object(InputManager, '_configure_inputs'):
            with patch.object(InputManager, '__init__', lambda self, *args, **kwargs: None):
                im = InputManager.__new__(InputManager)
                im._manager = mock_manager
                im._inputs = {}
                im._event_pins = []
                im._binary_pins = []
                im._long_press_mqtt_last_ts = {}
                return im

    @pytest.mark.asyncio
    async def test_publish_only_skips_action_execution(self, input_manager, mock_manager):
        """Test that publish_only=True events skip action execution."""
        # Setup
        binary_sensor = MockInput(
            id="in_01",
            name="Test Sensor",
            input_type=INPUT_SENSOR,
        )
        binary_sensor._actions = {PRESSED: [{"action": "test_action"}]}
        input_manager._inputs["in_01"] = binary_sensor
        
        event = InputEvent(
            entity_id="in_01",
            click_type=PRESSED,
            duration=None,
            state=InputState(
                name="Test Sensor",
                pin="P8_30",
                state=PRESSED,
                type=INPUT_SENSOR,
                timestamp=1234567890.0,
                boneio_input="in_01",
                area=None,
            ),
            publish_only=True,
        )
        
        # Execute
        await input_manager.handle_input_event(event)
        
        # Verify - MQTT should be published
        mock_manager.send_message.assert_called_once()
        
        # Verify - actions should NOT be executed
        mock_manager.execute_actions.assert_not_called()

    @pytest.mark.asyncio
    async def test_normal_event_executes_actions(self, input_manager, mock_manager):
        """Test that normal events (publish_only=False) execute actions."""
        # Setup
        binary_sensor = MockInput(
            id="in_01",
            name="Test Sensor",
            input_type=INPUT_SENSOR,
        )
        binary_sensor._actions = {PRESSED: [{"action": "test_action"}]}
        input_manager._inputs["in_01"] = binary_sensor
        
        event = InputEvent(
            entity_id="in_01",
            click_type=PRESSED,
            duration=None,
            state=InputState(
                name="Test Sensor",
                pin="P8_30",
                state=PRESSED,
                type=INPUT_SENSOR,
                timestamp=1234567890.0,
                boneio_input="in_01",
                area=None,
            ),
            publish_only=False,
        )
        
        # Execute
        await input_manager.handle_input_event(event)
        
        # Verify - MQTT should be published
        mock_manager.send_message.assert_called_once()
        
        # Verify - actions should be executed
        mock_manager.execute_actions.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_entity_id_logs_warning(self, input_manager, mock_manager):
        """Test that missing entity_id logs warning and returns early."""
        event = InputEvent(
            entity_id="",
            click_type=PRESSED,
            duration=None,
            state=InputState(
                name="Test",
                pin="P8_30",
                state=PRESSED,
                type=INPUT_SENSOR,
                timestamp=1234567890.0,
                boneio_input="",
                area=None,
            ),
        )
        
        # Execute - should not raise
        await input_manager.handle_input_event(event)
        
        # Verify - no MQTT publish
        mock_manager.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_click_type_logs_warning(self, input_manager, mock_manager):
        """Test that missing click_type logs warning and returns early."""
        event = InputEvent(
            entity_id="in_01",
            click_type=None,
            duration=None,
            state=InputState(
                name="Test",
                pin="P8_30",
                state="",
                type=INPUT_SENSOR,
                timestamp=1234567890.0,
                boneio_input="in_01",
                area=None,
            ),
        )
        
        # Execute - should not raise
        await input_manager.handle_input_event(event)
        
        # Verify - no MQTT publish
        mock_manager.send_message.assert_not_called()
