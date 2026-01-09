"""Unit tests for Home Assistant integration messages.

These tests verify that HA discovery messages are correctly formed.
They would catch bugs like duplicate kwargs (entity_id passed twice).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from boneio.integration.homeassistant import (
    ha_availabilty_message,
    ha_binary_sensor_availabilty_message,
    ha_cover_availabilty_message,
    ha_sensor_availabilty_message,
    ha_switch_availabilty_message,
    modbus_numeric_availabilty_message,
    modbus_select_availabilty_message,
    modbus_sensor_availabilty_message,
)


@pytest.fixture
def config_helper():
    """Provide a mock ConfigHelper for HA integration tests."""
    helper = MagicMock()
    helper.topic_prefix = "boneio"
    helper.ha_discovery = True
    helper.ha_discovery_prefix = "homeassistant"
    return helper


class TestHAAvailabilityMessage:
    """Tests for ha_availabilty_message function."""

    def test_basic_message_structure(self, config_helper):
        """Test that basic HA message has required fields."""
        msg = ha_availabilty_message(
            id="test_entity",
            name="Test Entity",
            entity_type="switch",
            config_helper=config_helper,
        )
        
        assert "availability" in msg
        assert "device" in msg
        assert "name" in msg
        assert msg["name"] == "Test Entity"

    def test_message_with_area(self, config_helper):
        """Test that area is included when provided."""
        msg = ha_availabilty_message(
            id="test_entity",
            name="Test Entity",
            entity_type="switch",
            config_helper=config_helper,
            area="living_room",
        )
        
        assert "device" in msg

    def test_message_with_kwargs(self, config_helper):
        """Test that additional kwargs are merged into message."""
        msg = ha_availabilty_message(
            id="test_entity",
            name="Test Entity",
            entity_type="switch",
            config_helper=config_helper,
            custom_field="custom_value",
        )
        
        assert msg.get("custom_field") == "custom_value"


class TestHASwitchMessage:
    """Tests for ha_switch_availabilty_message function."""

    def test_switch_message_structure(self, config_helper):
        """Test switch message has correct structure."""
        msg = ha_switch_availabilty_message(
            id="relay_1",
            name="Relay 1",
            config_helper=config_helper,
        )
        
        assert "command_topic" in msg
        assert "state_topic" in msg
        assert "availability" in msg

    def test_switch_message_topics(self, config_helper):
        """Test switch message has correct topics."""
        msg = ha_switch_availabilty_message(
            id="relay_1",
            name="Relay 1",
            config_helper=config_helper,
        )
        
        assert "boneio" in msg["command_topic"]
        assert "boneio" in msg["state_topic"]


class TestHACoverMessage:
    """Tests for ha_cover_availabilty_message function."""

    def test_cover_message_structure(self, config_helper):
        """Test cover message has correct structure."""
        msg = ha_cover_availabilty_message(
            id="cover_1",
            name="Cover 1",
            device_class="shutter",
            config_helper=config_helper,
        )
        
        assert "command_topic" in msg
        assert "state_topic" in msg
        assert "position_topic" in msg

    def test_cover_with_tilt(self, config_helper):
        """Test cover message with tilt support."""
        msg = ha_cover_availabilty_message(
            id="cover_1",
            name="Cover 1",
            device_class="blind",
            config_helper=config_helper,
            tilt_command_topic="boneio/cover/cover_1/tilt/set",
            tilt_status_topic="boneio/cover/cover_1/tilt",
        )
        
        assert msg.get("tilt_command_topic") == "boneio/cover/cover_1/tilt/set"
        assert msg.get("tilt_status_topic") == "boneio/cover/cover_1/tilt"


class TestHASensorMessage:
    """Tests for ha_sensor_availabilty_message function."""

    def test_sensor_message_structure(self, config_helper):
        """Test sensor message has correct structure."""
        msg = ha_sensor_availabilty_message(
            id="temp_1",
            name="Temperature 1",
            entity_type="sensor",
            config_helper=config_helper,
        )
        
        assert "state_topic" in msg
        assert "availability" in msg

    def test_sensor_with_unit(self, config_helper):
        """Test sensor message with unit of measurement."""
        msg = ha_sensor_availabilty_message(
            id="temp_1",
            name="Temperature 1",
            entity_type="sensor",
            config_helper=config_helper,
            unit_of_measurement="°C",
        )
        
        assert msg.get("unit_of_measurement") == "°C"


class TestHABinarySensorMessage:
    """Tests for ha_binary_sensor_availabilty_message function."""

    def test_binary_sensor_message_structure(self, config_helper):
        """Test binary sensor message has correct structure."""
        msg = ha_binary_sensor_availabilty_message(
            id="button_1",
            name="Button 1",
            config_helper=config_helper,
        )
        
        assert "state_topic" in msg
        assert "availability" in msg

    def test_binary_sensor_with_device_class(self, config_helper):
        """Test binary sensor with device class."""
        msg = ha_binary_sensor_availabilty_message(
            id="motion_1",
            name="Motion 1",
            config_helper=config_helper,
            device_class="motion",
        )
        
        assert msg.get("device_class") == "motion"


class TestModbusMessages:
    """Tests for Modbus HA discovery messages."""

    def test_modbus_sensor_message(self, config_helper):
        """Test modbus sensor message structure."""
        msg = modbus_sensor_availabilty_message(
            entity_id="sdm_voltage",
            entity_name="SDM Voltage",
            device_id="sdm120",
            device_name="SDM120 Meter",
            manufacturer="Eastron",
            state_topic_base="0",
            config_helper=config_helper,
            model="SDM120",
        )
        
        assert "state_topic" in msg
        assert "availability" in msg
        assert "device" in msg
        assert msg["device"]["manufacturer"] == "Eastron"

    def test_modbus_select_message(self, config_helper):
        """Test modbus select message structure."""
        msg = modbus_select_availabilty_message(
            entity_id="sdm_mode",
            entity_name="SDM Mode",
            device_id="sdm120",
            device_name="SDM120 Meter",
            manufacturer="Eastron",
            state_topic_base="0",
            config_helper=config_helper,
            model="SDM120",
        )
        
        assert "state_topic" in msg
        assert "device" in msg

    def test_modbus_numeric_message(self, config_helper):
        """Test modbus numeric message structure."""
        msg = modbus_numeric_availabilty_message(
            entity_id="sdm_power",
            entity_name="SDM Power",
            device_id="sdm120",
            device_name="SDM120 Meter",
            manufacturer="Eastron",
            state_topic_base="0",
            config_helper=config_helper,
            model="SDM120",
        )
        
        assert "state_topic" in msg
        assert "device" in msg

    def test_modbus_numeric_no_duplicate_kwargs(self, config_helper):
        """Test that modbus_numeric doesn't fail with duplicate entity_id.
        
        This test would have caught the bug where entity_id was passed
        both as a named parameter and in **kwargs.
        """
        # This should NOT raise TypeError about duplicate kwargs
        msg = modbus_numeric_availabilty_message(
            entity_id="test_entity",
            entity_name="Test Entity",
            device_id="device1",
            device_name="Device 1",
            manufacturer="Test",
            state_topic_base="0",
            config_helper=config_helper,
            model="TestModel",
            value_template="{{ value_json.test }}",
        )
        
        assert msg is not None
        assert "state_topic" in msg

    def test_modbus_numeric_with_extra_kwargs(self, config_helper):
        """Test modbus numeric accepts additional kwargs without conflict."""
        msg = modbus_numeric_availabilty_message(
            entity_id="test_entity",
            entity_name="Test Entity",
            device_id="device1",
            device_name="Device 1",
            manufacturer="Test",
            state_topic_base="0",
            config_helper=config_helper,
            model="TestModel",
            mode="box",
            step=0.1,
            command_topic="boneio/cmd/test",
        )
        
        assert msg.get("mode") == "box"
        assert msg.get("step") == 0.1
        assert msg.get("command_topic") == "boneio/cmd/test"
