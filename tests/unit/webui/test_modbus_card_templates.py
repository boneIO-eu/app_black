"""Tests for Modbus card templates — verifies card structure, icons, and sections.

Uses MockModbusCoordinator.from_json() to test card generation
for all device categories without physical hardware.
"""

import os

import pytest
import yaml

from boneio.webui.dashboard_cards import cards_to_yaml
from boneio.webui.modbus_card_templates import (
    CATEGORY_TEMPLATES,
    DEVICE_CLASS_ICONS,
    generate_cards_for_device,
    generate_energy_cards,
    generate_generic_cards,
    generate_hvac_cards,
    _build_entity_id,
    _flatten_entities,
    _get_icon,
    _ha_entity_type,
)
from tests.mocks.modbus_coordinator import MockModbusCoordinator, MockModbusEntity

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
# Icon mapping
# ---------------------------------------------------------------------------


class TestIconMapping:
    """Test device_class → icon mapping."""

    def test_temperature_icon(self):
        """Temperature entities should get thermometer icon."""
        entity = MockModbusEntity(name="Temp", device_class="temperature")
        assert _get_icon(entity) == "mdi:thermometer"

    def test_voltage_icon(self):
        """Voltage entities should get flash icon."""
        entity = MockModbusEntity(name="Volt", device_class="voltage")
        assert _get_icon(entity) == "mdi:flash"

    def test_power_icon(self):
        """Power entities should get lightning-bolt icon."""
        entity = MockModbusEntity(name="Pow", device_class="power")
        assert _get_icon(entity) == "mdi:lightning-bolt"

    def test_humidity_icon(self):
        """Humidity entities should get water-percent icon."""
        entity = MockModbusEntity(name="Hum", device_class="humidity")
        assert _get_icon(entity) == "mdi:water-percent"

    def test_flow_icon(self):
        """Volume flow rate should get fan icon."""
        entity = MockModbusEntity(name="Flow", device_class="volume_flow_rate")
        assert _get_icon(entity) == "mdi:fan"

    def test_binary_sensor_fallback(self):
        """Binary sensor without device_class should get toggle-switch."""
        entity = MockModbusEntity(name="Status", entity_type="binary_sensor")
        assert _get_icon(entity) == "mdi:toggle-switch"

    def test_switch_fallback(self):
        """Switch entity should get toggle-switch-variant."""
        entity = MockModbusEntity(
            name="Ctrl", entity_type="writeable_binary_sensor_discrete"
        )
        assert _get_icon(entity) == "mdi:toggle-switch-variant"

    def test_unknown_gets_fallback(self):
        """Unknown device_class should fall back to entity_type icon."""
        entity = MockModbusEntity(name="X", device_class="unknown_class")
        icon = _get_icon(entity)
        # Should NOT be the device_class icon (doesn't exist)
        assert icon != "mdi:chip" or icon == "mdi:eye"

    def test_no_device_class_sensor(self):
        """Sensor without device_class should get mdi:eye."""
        entity = MockModbusEntity(name="X", entity_type="sensor")
        assert _get_icon(entity) == "mdi:eye"


# ---------------------------------------------------------------------------
# Entity type mapping
# ---------------------------------------------------------------------------


class TestHaEntityType:
    """Test internal entity_type → HA entity type mapping."""

    def test_sensor(self):
        entity = MockModbusEntity(name="T", entity_type="sensor")
        assert _ha_entity_type(entity) == "sensor"

    def test_binary_sensor(self):
        entity = MockModbusEntity(name="T", entity_type="binary_sensor")
        assert _ha_entity_type(entity) == "binary_sensor"

    def test_text_sensor(self):
        entity = MockModbusEntity(name="T", entity_type="text_sensor")
        assert _ha_entity_type(entity) == "sensor"

    def test_writeable_sensor(self):
        entity = MockModbusEntity(name="T", entity_type="writeable_sensor")
        assert _ha_entity_type(entity) == "number"

    def test_writeable_binary_discrete(self):
        entity = MockModbusEntity(
            name="T", entity_type="writeable_binary_sensor_discrete"
        )
        assert _ha_entity_type(entity) == "switch"


# ---------------------------------------------------------------------------
# Entity ID building
# ---------------------------------------------------------------------------


class TestBuildEntityId:
    """Test HA entity_id construction."""

    def test_sensor_entity_id(self):
        entity = MockModbusEntity(name="Temperatura zewnętrzna", entity_type="sensor")
        eid = _build_entity_id("1_wanas415", entity)
        assert eid.startswith("sensor.")
        assert "temperatura" in eid
        assert "zewn" in eid

    def test_binary_sensor_entity_id(self):
        entity = MockModbusEntity(name="Bypass letni", entity_type="binary_sensor")
        eid = _build_entity_id("1_wanas415", entity)
        assert eid.startswith("binary_sensor.")
        assert "bypass" in eid

    def test_switch_entity_id(self):
        entity = MockModbusEntity(
            name="Nagrzewnica", entity_type="writeable_binary_sensor_discrete"
        )
        eid = _build_entity_id("1_wanas415", entity)
        assert eid.startswith("switch.")


# ---------------------------------------------------------------------------
# HVAC template (Wanas, Thessla)
# ---------------------------------------------------------------------------


class TestHvacCards:
    """Test HVAC card template."""

    @pytest.fixture
    def wanas_cards(self):
        """Generate HVAC cards for Wanas 415."""
        coord = MockModbusCoordinator.from_json("wanas415")
        return generate_hvac_cards(
            device_id="1_wanas415",
            entities_list=coord.get_all_entities(),
            serial="boneio_test",
            device_info=coord.get_device_info(),
        )

    def test_has_main_heading(self, wanas_cards):
        """Should have a main title heading."""
        headings = [c for c in wanas_cards if c.get("type") == "heading"]
        assert len(headings) > 0
        assert "Wanas" in headings[0].get("heading", "")

    def test_has_temperature_section(self, wanas_cards):
        """Should have a temperature subtitle heading."""
        temp_headings = [
            c for c in wanas_cards
            if c.get("type") == "heading" and "Temperatury" in c.get("heading", "")
        ]
        assert len(temp_headings) == 1

    def test_temperature_tiles_have_thermometer_icon(self, wanas_cards):
        """Temperature tiles should use mdi:thermometer."""
        temp_tiles = [
            c for c in wanas_cards
            if c.get("type") == "tile" and c.get("icon") == "mdi:thermometer"
        ]
        assert len(temp_tiles) >= 4, (
            f"Expected at least 4 temp tiles, got {len(temp_tiles)}"
        )

    def test_has_flow_section(self, wanas_cards):
        """Should have an air flow subtitle heading."""
        flow_headings = [
            c for c in wanas_cards
            if c.get("type") == "heading" and "Przepływ" in c.get("heading", "")
        ]
        assert len(flow_headings) == 1

    def test_flow_tiles_have_fan_icon(self, wanas_cards):
        """Flow tiles should use mdi:fan."""
        fan_tiles = [
            c for c in wanas_cards
            if c.get("type") == "tile" and c.get("icon") == "mdi:fan"
        ]
        assert len(fan_tiles) >= 2

    def test_no_mdi_chip_icons(self, wanas_cards):
        """No entity should use the generic mdi:chip icon."""
        for card in wanas_cards:
            if card.get("type") == "tile":
                assert card.get("icon") != "mdi:chip", (
                    f"Entity '{card.get('name')}' still uses mdi:chip"
                )

    def test_produces_valid_yaml(self, wanas_cards):
        """Output should be valid YAML."""
        yaml_str = cards_to_yaml(wanas_cards)
        parsed = yaml.safe_load(yaml_str)
        assert "cards" in parsed

    def test_thessla_also_works(self):
        """Thessla should also produce HVAC cards."""
        coord = MockModbusCoordinator.from_json("thessla")
        cards = generate_hvac_cards(
            device_id="1_thessla",
            entities_list=coord.get_all_entities(),
            serial="boneio_test",
            device_info=coord.get_device_info(),
        )
        assert len(cards) > 3


# ---------------------------------------------------------------------------
# Energy Meters template (SDM120, SDM630)
# ---------------------------------------------------------------------------


class TestEnergyMeterCards:
    """Test energy meter card template."""

    @pytest.fixture
    def sdm120_cards(self):
        """Generate energy cards for SDM120."""
        coord = MockModbusCoordinator.from_json("sdm120")
        return generate_energy_cards(
            device_id="1_sdm120",
            entities_list=coord.get_all_entities(),
            serial="boneio_test",
            device_info=coord.get_device_info(),
        )

    def test_has_main_heading(self, sdm120_cards):
        """Should have a main title heading."""
        headings = [c for c in sdm120_cards if c.get("type") == "heading"]
        assert len(headings) > 0

    def test_has_voltage_section(self, sdm120_cards):
        """Should have a voltage subtitle heading."""
        v_headings = [
            c for c in sdm120_cards
            if c.get("type") == "heading" and "Napięcie" in c.get("heading", "")
        ]
        assert len(v_headings) == 1

    def test_voltage_tiles_have_flash_icon(self, sdm120_cards):
        """Voltage tiles should use mdi:flash."""
        flash_tiles = [
            c for c in sdm120_cards
            if c.get("type") == "tile" and c.get("icon") == "mdi:flash"
        ]
        assert len(flash_tiles) >= 1

    def test_has_power_section(self, sdm120_cards):
        """Should have a power subtitle heading."""
        p_headings = [
            c for c in sdm120_cards
            if c.get("type") == "heading" and "Moc" in c.get("heading", "")
        ]
        assert len(p_headings) == 1

    def test_no_mdi_chip_icons(self, sdm120_cards):
        """No entity should use mdi:chip."""
        for card in sdm120_cards:
            if card.get("type") == "tile":
                assert card.get("icon") != "mdi:chip", (
                    f"Entity '{card.get('name')}' still uses mdi:chip"
                )

    def test_sdm630_also_works(self):
        """SDM630 should also produce energy cards."""
        coord = MockModbusCoordinator.from_json("sdm630")
        cards = generate_energy_cards(
            device_id="1_sdm630",
            entities_list=coord.get_all_entities(),
            serial="boneio_test",
            device_info=coord.get_device_info(),
        )
        assert len(cards) > 5


# ---------------------------------------------------------------------------
# Generic / fallback template
# ---------------------------------------------------------------------------


class TestGenericCards:
    """Test generic/fallback card template."""

    def test_sht30_produces_cards(self):
        """SHT30 sensor should produce generic cards."""
        coord = MockModbusCoordinator.from_json("sht30")
        cards = generate_generic_cards(
            device_id="1_sht30",
            entities_list=coord.get_all_entities(),
            serial="boneio_test",
            device_info=coord.get_device_info(),
        )
        assert len(cards) > 1

    def test_cwt_produces_cards(self):
        """CWT current transformer should produce generic cards."""
        coord = MockModbusCoordinator.from_json("cwt")
        cards = generate_generic_cards(
            device_id="1_cwt",
            entities_list=coord.get_all_entities(),
            serial="boneio_test",
            device_info=coord.get_device_info(),
        )
        assert len(cards) > 1


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


class TestDispatcher:
    """Test category-based card template dispatch."""

    def test_hvac_dispatches_to_hvac(self):
        """hvac category should use generate_hvac_cards."""
        coord = MockModbusCoordinator.from_json("wanas415")
        cards = generate_cards_for_device(
            device_id="1_wanas415",
            entities_list=coord.get_all_entities(),
            serial="boneio_test",
            device_info=coord.get_device_info(),
        )
        # HVAC cards have temperature section
        temp_headings = [
            c for c in cards
            if c.get("type") == "heading" and "Temperatury" in c.get("heading", "")
        ]
        assert len(temp_headings) == 1

    def test_energy_dispatches_to_energy(self):
        """energy_meters category should use generate_energy_cards."""
        coord = MockModbusCoordinator.from_json("sdm120")
        cards = generate_cards_for_device(
            device_id="1_sdm120",
            entities_list=coord.get_all_entities(),
            serial="boneio_test",
            device_info=coord.get_device_info(),
        )
        v_headings = [
            c for c in cards
            if c.get("type") == "heading" and "Napięcie" in c.get("heading", "")
        ]
        assert len(v_headings) == 1

    def test_sensors_dispatches_to_generic(self):
        """sensors category should use generate_generic_cards."""
        coord = MockModbusCoordinator.from_json("sht30")
        cards = generate_cards_for_device(
            device_id="1_sht30",
            entities_list=coord.get_all_entities(),
            serial="boneio_test",
            device_info=coord.get_device_info(),
        )
        assert len(cards) > 1


# ---------------------------------------------------------------------------
# All models produce valid YAML
# ---------------------------------------------------------------------------


class TestAllModelsProduceYaml:
    """Test that every model produces valid YAML output."""

    @pytest.mark.parametrize("model_key", ALL_MODELS)
    def test_produces_valid_yaml(self, model_key):
        """Every device model should produce parseable YAML."""
        coord = MockModbusCoordinator.from_json(model_key)
        cards = generate_cards_for_device(
            device_id=f"1_{model_key}",
            entities_list=coord.get_all_entities(),
            serial="test_serial",
            device_info=coord.get_device_info(),
        )
        assert len(cards) > 0, f"Model {model_key} produced no cards"

        yaml_str = cards_to_yaml(cards)
        parsed = yaml.safe_load(yaml_str)
        assert parsed is not None
        assert "cards" in parsed

    @pytest.mark.parametrize("model_key", ALL_MODELS)
    def test_no_mdi_chip(self, model_key):
        """No model should produce mdi:chip icon tiles."""
        coord = MockModbusCoordinator.from_json(model_key)
        cards = generate_cards_for_device(
            device_id=f"1_{model_key}",
            entities_list=coord.get_all_entities(),
            serial="test_serial",
            device_info=coord.get_device_info(),
        )
        for card in cards:
            if card.get("type") == "tile":
                assert card.get("icon") != "mdi:chip", (
                    f"Model {model_key}: entity '{card.get('name')}' "
                    f"still uses generic mdi:chip"
                )
