"""Unit tests for Home Assistant integration messages.

These tests verify that HA discovery messages are correctly formed.
They would catch bugs like duplicate kwargs (entity_id passed twice).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from boneio.const import ID, MODEL, NAME
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
from boneio.modbus.entities.derived.select import ModbusDerivedSelect


@pytest.fixture
def config_helper():
    """Provide a mock ConfigHelper for HA integration tests."""
    helper = MagicMock()
    helper.topic_prefix = "boneio"
    helper.ha_discovery = True
    helper.ha_discovery_prefix = "homeassistant"
    helper.ha_child_devices = False
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


class TestHAChildDevicesMode:
    """Tests for experimental ha_child_devices mode."""

    @pytest.fixture
    def child_config_helper(self):
        """Provide a mock ConfigHelper with ha_child_devices enabled."""
        helper = MagicMock()
        helper.topic_prefix = "boneio/blk_abc123"
        helper.ha_discovery = True
        helper.ha_discovery_prefix = "homeassistant"
        helper.ha_child_devices = True
        helper.serial_number = "blk_abc123"
        helper.name = "boneIO Black"
        helper.device_type = "32x10a"
        helper.is_web_active = False
        helper.network_info = {}
        helper.areas = {"salon": "Salon", "kuchnia": "Kuchnia"}
        helper.get_area_name = lambda area_id: helper.areas.get(area_id)
        return helper

    def test_child_device_created_per_entity(self, child_config_helper):
        """Test that each entity gets its own child device."""
        msg = ha_availabilty_message(
            id="out_01",
            name="OUT 01",
            entity_type="light",
            config_helper=child_config_helper,
            device_type="output",
        )

        # Entity name should be empty
        assert msg["name"] == ""
        # Device name should be the output name
        assert msg["device"]["name"] == "OUT 01"
        # Device should be a child of the main device
        assert msg["device"]["via_device"] == "boneio/blk_abc123"
        # Device identifier should be unique per output
        assert msg["device"]["identifiers"] == ["boneio/blk_abc123_output_out_01"]

    def test_child_device_no_area(self, child_config_helper):
        """Test child device without area has no suggested_area."""
        msg = ha_availabilty_message(
            id="out_01",
            name="OUT 01",
            entity_type="light",
            config_helper=child_config_helper,
            device_type="output",
        )

        assert "suggested_area" not in msg["device"]

    def test_child_device_with_area(self, child_config_helper):
        """Test child device with area gets suggested_area but no area in name."""
        msg = ha_availabilty_message(
            id="out_01",
            name="OUT 01",
            entity_type="light",
            config_helper=child_config_helper,
            device_type="output",
            area="salon",
        )

        # Device name is still just the output name (no area in name)
        assert msg["device"]["name"] == "OUT 01"
        # Area is set via suggested_area
        assert msg["device"]["suggested_area"] == "Salon"
        # Entity name is empty
        assert msg["name"] == ""

    def test_child_device_switch(self, child_config_helper):
        """Test child device mode with switch entity."""
        msg = ha_switch_availabilty_message(
            id="out_05",
            name="OUT 05",
            config_helper=child_config_helper,
        )

        assert msg["name"] == ""
        assert msg["device"]["name"] == "OUT 05"
        assert "command_topic" in msg

    def test_disabled_mode_uses_standard_device(self, config_helper):
        """Test that ha_child_devices=False uses standard device grouping."""
        msg = ha_availabilty_message(
            id="out_01",
            name="OUT 01",
            entity_type="light",
            config_helper=config_helper,
        )

        # Entity name should be the output name (not empty)
        assert msg["name"] == "OUT 01"


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

    def test_modbus_select_no_duplicate_kwargs(self, config_helper):
        """Test that modbus_select doesn't fail with duplicate entity_id."""
        msg = modbus_select_availabilty_message(
            entity_id="test_entity",
            entity_name="Test Entity",
            device_id="device1",
            device_name="Device 1",
            manufacturer="Test",
            state_topic_base="0",
            config_helper=config_helper,
            model="TestModel",
            entity_id_legacy="ignored",
            value_template="{{ value_json.test }}",
        )

        assert msg is not None
        assert "state_topic" in msg
        assert msg.get("value_template") == "{{ value_json.test }}"

    def test_modbus_select_filters_duplicate_entity_id_from_kwargs(self, config_helper):
        """Test that explicit entity_id wins over value from kwargs."""
        msg = modbus_select_availabilty_message(
            entity_id="proper_entity",
            entity_name="Test Entity",
            device_id="device1",
            device_name="Device 1",
            manufacturer="Test",
            state_topic_base="0",
            config_helper=config_helper,
            model="TestModel",
            options=["Auto", "Manual"],
            command_topic="boneio/cmd/test",
        )

        assert msg["default_entity_id"].endswith("proper_entity")
        assert msg.get("command_topic") == "boneio/cmd/test"


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


class TestModbusDerivedSelect:
    """Regression tests for derived Modbus select entities."""

    def test_discovery_message_does_not_pass_duplicate_entity_id(self, config_helper):
        """Test derived select discovery generation does not duplicate entity_id."""
        message_bus = MagicMock()
        parent = {
            ID: "SDM120",
            NAME: "SDM120 Meter",
            MODEL: "SDM120",
            "manufacturer": "Eastron",
            "area": None,
        }
        entity = ModbusDerivedSelect(
            name="Operating Mode",
            parent=parent,
            message_bus=message_bus,
            context_config={},
            config_helper=config_helper,
            source_sensor_base_address=10,
            source_sensor_decoded_name="operatingmode",
            value_mapping={"0": "Auto", "1": "Manual"},
        )

        msg = entity.discovery_message()

        assert msg is not None
        assert msg["name"] == "Operating Mode"
        assert msg["state_topic"] == "boneio/modbus/SDM120/10"
        assert msg["command_topic"] == "boneio/cmd/modbus/sdm120/set"
        assert msg["options"] == ["Auto", "Manual"]


class TestModbusCoordinatorDiscovery:
    """Regression tests for coordinator discovery flow."""

    def test_send_discovery_for_all_registers_with_derived_select(self, config_helper):
        """Test coordinator discovery sends discovery for derived select without TypeError."""
        base_sensor = MagicMock()
        base_sensor.send_ha_discovery = MagicMock()
        message_bus = MagicMock()

        derived_select = ModbusDerivedSelect(
            name="Operating Mode",
            parent={
                ID: "SDM120",
                NAME: "SDM120 Meter",
                MODEL: "SDM120",
                "manufacturer": "Eastron",
                "area": None,
            },
            message_bus=message_bus,
            context_config={},
            config_helper=config_helper,
            source_sensor_base_address=10,
            source_sensor_decoded_name="operatingmode",
            value_mapping={"0": "Auto", "1": "Manual"},
        )

        coordinator = MagicMock()
        coordinator._modbus_entities = [{"operatingmode": base_sensor}]
        coordinator._additional_entities = [{derived_select.decoded_name: derived_select}]

        from boneio.modbus.coordinator import ModbusCoordinator

        ModbusCoordinator._send_discovery_for_all_registers(coordinator)

        base_sensor.send_ha_discovery.assert_called_once()
        config_helper.add_autodiscovery_msg.assert_called_once()

        send_calls = message_bus.send_message.call_args_list
        assert len(send_calls) == 1
        assert send_calls[0].kwargs["payload"]["name"] == "Operating Mode"
        assert send_calls[0].kwargs["payload"]["command_topic"] == "boneio/cmd/modbus/sdm120/set"
