"""Tests for MockModbusCoordinator and future card template generation.

Verifies that:
1. MockModbusCoordinator.from_json() correctly reads all device JSONs
2. Entities have proper metadata (entity_type, device_class, unit)
3. Entity decoded_names match expected format
4. get_all_entities() returns the same structure as real coordinator
5. All 26 device models can be loaded without errors
"""

import json
import os

import pytest
import yaml

from tests.mocks.modbus_coordinator import (
    MockModbusCoordinator,
    MockModbusEntity,
    _find_device_json,
)

# Get list of all device model keys
DEVICES_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "../../../boneio/modbus/devices")
)


def _all_model_keys() -> list[str]:
    """Collect all model keys from device JSON files."""
    models = []
    for root, _dirs, files in os.walk(DEVICES_DIR):
        for fname in sorted(files):
            if fname.endswith(".json"):
                models.append(fname[:-5])
    return models


ALL_MODELS = _all_model_keys()


# ---------------------------------------------------------------------------
# MockModbusEntity
# ---------------------------------------------------------------------------


class TestMockModbusEntity:
    """Test MockModbusEntity data class."""

    def test_decoded_name_removes_spaces(self):
        """decoded_name should be lowercase with no spaces."""
        entity = MockModbusEntity(name="Temperatura zewnętrzna")
        assert entity.decoded_name == "temperaturazewnętrzna"

    def test_decoded_name_lowercase(self):
        """decoded_name should be lowercased."""
        entity = MockModbusEntity(name="Bypass Letni")
        assert entity.decoded_name == "bypassletni"

    def test_display_name_returns_name(self):
        """display_name returns name when no custom label."""
        entity = MockModbusEntity(name="Test Sensor")
        assert entity.display_name == "Test Sensor"

    def test_display_name_returns_custom_label(self):
        """display_name returns custom_label when set."""
        entity = MockModbusEntity(name="Test Sensor")
        entity.set_custom_label("My Custom Name")
        assert entity.display_name == "My Custom Name"

    def test_device_class_alias(self):
        """_device_class property should match device_class."""
        entity = MockModbusEntity(name="Temp", device_class="temperature")
        assert entity._device_class == "temperature"

    def test_default_entity_type(self):
        """Default entity_type should be 'sensor'."""
        entity = MockModbusEntity(name="Test")
        assert entity.entity_type == "sensor"


# ---------------------------------------------------------------------------
# MockModbusCoordinator.from_json()
# ---------------------------------------------------------------------------


class TestMockModbusCoordinatorFromJson:
    """Test building coordinators from device JSON files."""

    def test_wanas_loads_successfully(self):
        """Wanas 415 should load with entities."""
        coord = MockModbusCoordinator.from_json("wanas415")
        assert coord._name == "Wanas 415"
        assert coord.model_key == "wanas415"
        assert coord.category == "hvac"
        assert coord.manufacturer == "Wanas"
        assert coord.base_entity_count > 0

    def test_sdm120_loads_successfully(self):
        """SDM120 should load with entities."""
        coord = MockModbusCoordinator.from_json("sdm120")
        assert coord.model_key == "sdm120"
        assert coord.category == "energy_meters"
        assert coord.base_entity_count > 0

    def test_sht30_loads_successfully(self):
        """SHT30 should load with entities."""
        coord = MockModbusCoordinator.from_json("sht30")
        assert coord.model_key == "sht30"
        assert coord.category == "sensors"

    def test_custom_address(self):
        """Custom address should appear in device ID."""
        coord = MockModbusCoordinator.from_json("sdm120", address=5)
        assert coord._id == "5_sdm120"

    def test_custom_device_id(self):
        """Custom device_id should override default."""
        coord = MockModbusCoordinator.from_json("sdm120", device_id="my_meter")
        assert coord._id == "my_meter"

    def test_custom_name(self):
        """Custom name should override JSON model name."""
        coord = MockModbusCoordinator.from_json("sdm120", name="Kitchen Meter")
        assert coord._name == "Kitchen Meter"

    def test_nonexistent_model_raises(self):
        """Unknown model should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="Device JSON not found"):
            MockModbusCoordinator.from_json("nonexistent_device_xyz")

    def test_get_device_info(self):
        """get_device_info() should return all metadata."""
        coord = MockModbusCoordinator.from_json("wanas415")
        info = coord.get_device_info()
        assert info["model"] == "Wanas 415"
        assert info["manufacturer"] == "Wanas"
        assert info["category"] == "hvac"
        assert info["model_key"] == "wanas415"
        assert "description" in info


# ---------------------------------------------------------------------------
# Entity structure matches real coordinator
# ---------------------------------------------------------------------------


class TestEntityStructure:
    """Test that get_all_entities() matches real coordinator format."""

    def test_returns_list_of_dicts(self):
        """get_all_entities() should return list[dict[str, entity]]."""
        coord = MockModbusCoordinator.from_json("wanas415")
        entities = coord.get_all_entities()
        assert isinstance(entities, list)
        assert len(entities) > 0
        assert isinstance(entities[0], dict)

    def test_dict_keys_are_decoded_names(self):
        """Dict keys should be decoded_name (lowercase, no spaces)."""
        coord = MockModbusCoordinator.from_json("wanas415")
        entities = coord.get_all_entities()
        for entities_dict in entities:
            for key, entity in entities_dict.items():
                assert key == entity.decoded_name
                assert " " not in key
                assert key == key.lower()

    def test_wanas_has_temperature_entities(self):
        """Wanas should have entities with device_class='temperature'."""
        coord = MockModbusCoordinator.from_json("wanas415")
        entities = coord.get_all_entities()
        temp_entities = [
            e
            for d in entities
            for e in d.values()
            if e.device_class == "temperature"
        ]
        assert len(temp_entities) >= 4, (
            f"Wanas should have at least 4 temperature entities, "
            f"found {len(temp_entities)}"
        )

    def test_wanas_has_flow_entities(self):
        """Wanas should have entities with device_class='volume_flow_rate'."""
        coord = MockModbusCoordinator.from_json("wanas415")
        entities = coord.get_all_entities()
        flow_entities = [
            e
            for d in entities
            for e in d.values()
            if e.device_class == "volume_flow_rate"
        ]
        assert len(flow_entities) >= 2

    def test_sdm120_has_voltage_entity(self):
        """SDM120 should have at least one voltage entity."""
        coord = MockModbusCoordinator.from_json("sdm120")
        entities = coord.get_all_entities()
        voltage = [
            e
            for d in entities
            for e in d.values()
            if e.device_class == "voltage"
        ]
        assert len(voltage) >= 1

    def test_sdm120_has_power_entity(self):
        """SDM120 should have at least one power entity."""
        coord = MockModbusCoordinator.from_json("sdm120")
        entities = coord.get_all_entities()
        power = [
            e
            for d in entities
            for e in d.values()
            if e.device_class == "power"
        ]
        assert len(power) >= 1

    def test_sht30_has_humidity_entity(self):
        """SHT30 should have at least one humidity entity."""
        coord = MockModbusCoordinator.from_json("sht30")
        entities = coord.get_all_entities()
        humidity = [
            e
            for d in entities
            for e in d.values()
            if e.device_class == "humidity"
        ]
        assert len(humidity) >= 1


# ---------------------------------------------------------------------------
# All models load correctly
# ---------------------------------------------------------------------------


class TestAllModels:
    """Test that every device JSON can be loaded."""

    @pytest.mark.parametrize("model_key", ALL_MODELS)
    def test_model_loads(self, model_key):
        """Every model should load without errors."""
        coord = MockModbusCoordinator.from_json(model_key)
        assert coord.base_entity_count > 0, (
            f"Model {model_key} has no base entities"
        )
        assert coord.category in {
            "energy_meters", "hvac", "inverters", "sensors", "other"
        }
        assert coord.manufacturer
        assert coord._model

    @pytest.mark.parametrize("model_key", ALL_MODELS)
    def test_model_entity_types_are_valid(self, model_key):
        """All entity_types should be recognized HA types."""
        valid_types = {
            "sensor", "binary_sensor", "text_sensor",
            "writeable_sensor", "writeable_sensor_discrete",
            "writeable_binary_sensor_discrete",
            "select", "switch", "number",  # derived additional_entities
        }
        coord = MockModbusCoordinator.from_json(model_key)
        for entities_dict in coord.get_all_entities():
            for entity in entities_dict.values():
                assert entity.entity_type in valid_types, (
                    f"Model {model_key}, entity {entity.name}: "
                    f"unknown entity_type '{entity.entity_type}'"
                )

    @pytest.mark.parametrize("model_key", ALL_MODELS)
    def test_model_repr(self, model_key):
        """__repr__ should not crash."""
        coord = MockModbusCoordinator.from_json(model_key)
        repr_str = repr(coord)
        assert model_key in repr_str

    @pytest.mark.parametrize("model_key", ALL_MODELS)
    def test_list_entities_returns_dicts(self, model_key):
        """list_entities() should return valid summary dicts."""
        coord = MockModbusCoordinator.from_json(model_key)
        summary = coord.list_entities()
        assert isinstance(summary, list)
        assert len(summary) > 0
        for item in summary:
            assert "name" in item
            assert "entity_type" in item
            assert "decoded_name" in item


# ---------------------------------------------------------------------------
# _find_device_json
# ---------------------------------------------------------------------------


class TestFindDeviceJson:
    """Test device JSON file discovery."""

    def test_finds_wanas(self):
        """Should find wanas415.json."""
        path = _find_device_json("wanas415")
        assert path.exists()
        assert path.name == "wanas415.json"
        assert "hvac" in str(path)

    def test_finds_sdm120(self):
        """Should find sdm120.json."""
        path = _find_device_json("sdm120")
        assert path.exists()
        assert "energy_meters" in str(path)

    def test_raises_for_unknown(self):
        """Should raise for unknown model."""
        with pytest.raises(FileNotFoundError, match="Available models"):
            _find_device_json("nonexistent_xyz")
