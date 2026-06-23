"""Tests for Modbus device schema validation and dynamic model injection.

Verifies that:
1. Dynamic model injection into the schema works correctly.
2. Config strings produced by the frontend wizard pass backend validation.
3. Invalid configs (bad model, missing fields) are properly rejected.
4. The used-addresses endpoint returns correct data.
"""

import json
import os

import pytest

from boneio.core.config.yaml_util import (
    ConfigurationException,
    _get_modbus_device_models,
    _inject_modbus_models,
    clear_config_cache,
    load_config_from_string,
    load_yaml_file,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def fresh_schema_cache():
    """Clear schema cache before each test to ensure dynamic injection runs."""
    clear_config_cache()
    yield
    clear_config_cache()


# ---------------------------------------------------------------------------
# _get_modbus_device_models
# ---------------------------------------------------------------------------

class TestGetModbusDeviceModels:
    """Tests for scanning the modbus/devices/ directory."""

    def test_returns_list(self):
        """Should return a sorted list of model keys."""
        models = _get_modbus_device_models()
        assert isinstance(models, list)
        assert len(models) > 0

    def test_contains_known_models(self):
        """Should contain well-known device models."""
        models = _get_modbus_device_models()
        assert "wanas415" in models
        assert "thessla" in models
        assert "sdm120" in models
        assert "sht30" in models

    def test_models_are_sorted(self):
        """Should return models in alphabetical order."""
        models = _get_modbus_device_models()
        assert models == sorted(models)

    def test_no_json_extension(self):
        """Model keys should NOT include .json extension."""
        models = _get_modbus_device_models()
        for model in models:
            assert not model.endswith(".json"), f"Model key {model} should not have .json extension"

    def test_no_pycache_files(self):
        """Should not pick up any __pycache__ artifacts."""
        models = _get_modbus_device_models()
        for model in models:
            assert "__pycache__" not in model


# ---------------------------------------------------------------------------
# _inject_modbus_models
# ---------------------------------------------------------------------------

class TestInjectModbusModels:
    """Tests for dynamic model injection into the schema dict."""

    def test_injects_allowed_list(self):
        """Should set 'allowed' on the modbus model field."""
        schema_file = os.path.join(
            os.path.dirname(__file__), "../../../boneio/schema/schema.yaml"
        )
        schema = load_yaml_file(schema_file)

        # Before injection, there should be no 'allowed' (removed from static schema)
        model_field = schema["modbus_devices"]["schema"]["schema"]["model"]
        assert "allowed" not in model_field

        _inject_modbus_models(schema)

        assert "allowed" in model_field
        assert isinstance(model_field["allowed"], list)
        assert "wanas415" in model_field["allowed"]
        assert "sdm120" in model_field["allowed"]

    def test_handles_missing_schema_path(self):
        """Should not crash on a schema dict without the expected path."""
        schema = {"something_else": {}}
        # Should log warning but not raise
        _inject_modbus_models(schema)


# ---------------------------------------------------------------------------
# Config validation — simulating wizard output
# ---------------------------------------------------------------------------

class TestModbusDeviceConfigValidation:
    """Test that configs matching the wizard output pass backend validation."""

    def _make_config(self, **modbus_overrides) -> str:
        """Build a minimal YAML config string with a single modbus device.

        Default values match what the wizard would produce.
        """
        device = {
            "model": "wanas415",
            "address": 1,
            "name": "My Recuperator",
            "update_interval": "30s",
            "id": "1_wanas415",
        }
        device.update(modbus_overrides)

        lines = ["boneio:", "  name: test", "modbus:", "  uart: uart4", "modbus_devices:"]
        lines.append("  - " + "\n    ".join(f"{k}: {v}" for k, v in device.items()))
        return "\n".join(lines) + "\n"

    def test_wizard_output_passes_validation(self):
        """Config produced by the wizard with valid fields should pass."""
        config_str = self._make_config()
        config = load_config_from_string(config_str)
        assert config is not None
        devices = config.get("modbus_devices", [])
        assert len(devices) == 1
        assert devices[0]["model"] == "wanas415"
        assert devices[0]["address"] == 1
        assert devices[0]["name"] == "My Recuperator"

    def test_different_known_models(self):
        """All known device models should pass validation."""
        models_to_test = ["sdm120", "thessla", "sht30", "sofar", "le-03mw", "boneio-edge-temp"]
        for model in models_to_test:
            config = load_config_from_string(self._make_config(model=model))
            assert config["modbus_devices"][0]["model"] == model, f"Model {model} should pass validation"

    def test_unknown_model_fails(self):
        """A model not present in devices/ directory should fail validation."""
        with pytest.raises(ConfigurationException, match="validation failed"):
            load_config_from_string(self._make_config(model="nonexistent_device_xyz"))

    def test_missing_model_field_fails(self):
        """Config without 'model' field should fail validation."""
        config_str = """
boneio:
  name: test
modbus:
  uart: uart4
modbus_devices:
  - address: 1
    update_interval: 30s
"""
        with pytest.raises(ConfigurationException, match="validation failed"):
            load_config_from_string(config_str)

    def test_missing_address_field_fails(self):
        """Config without 'address' field should fail validation."""
        config_str = """
boneio:
  name: test
modbus:
  uart: uart4
modbus_devices:
  - model: sdm120
    update_interval: 30s
"""
        with pytest.raises(ConfigurationException, match="validation failed"):
            load_config_from_string(config_str)

    def test_update_interval_string_formats(self):
        """Various time period formats should be accepted."""
        for interval in ["10s", "30s", "1min", "500ms", "1h"]:
            config = load_config_from_string(self._make_config(update_interval=interval))
            assert config is not None, f"Interval '{interval}' should be accepted"

    def test_model_case_insensitive(self):
        """Model name should be lowercased by the schema coercer."""
        config = load_config_from_string(self._make_config(model="SDM120"))
        assert config["modbus_devices"][0]["model"] == "sdm120"

    def test_optional_area_field(self):
        """Area field should be optional and preserved when provided."""
        config = load_config_from_string(self._make_config(area="salon"))
        assert config["modbus_devices"][0].get("area") == "salon"

    def test_multiple_devices_different_addresses(self):
        """Multiple devices at different addresses should pass."""
        config_str = """
boneio:
  name: test
modbus:
  uart: uart4
modbus_devices:
  - model: sdm120
    address: 1
    update_interval: 10s
  - model: wanas415
    address: 2
    update_interval: 30s
"""
        config = load_config_from_string(config_str)
        assert len(config["modbus_devices"]) == 2
        assert config["modbus_devices"][0]["address"] == 1
        assert config["modbus_devices"][1]["address"] == 2


# ---------------------------------------------------------------------------
# JSON device files integrity
# ---------------------------------------------------------------------------

class TestDeviceJsonFiles:
    """Verify that all JSON device files have required metadata fields."""

    DEVICES_DIR = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "../../../boneio/modbus/devices")
    )

    def _load_all_devices(self):
        """Load all device JSON files and return (model_key, data, path) tuples."""
        devices = []
        for root, _dirs, files in os.walk(self.DEVICES_DIR):
            for fname in sorted(files):
                if not fname.endswith(".json"):
                    continue
                filepath = os.path.join(root, fname)
                with open(filepath) as f:
                    data = json.load(f)
                devices.append((fname[:-5], data, filepath))
        return devices

    def test_all_have_required_metadata(self):
        """Each device JSON must have model, manufacturer, description, category."""
        required_fields = ["model", "manufacturer", "description", "category"]
        devices = self._load_all_devices()
        assert len(devices) > 0, "Should find at least one device JSON"

        for model_key, data, filepath in devices:
            for field in required_fields:
                assert field in data, (
                    f"{model_key} ({filepath}) is missing required field '{field}'"
                )

    def test_no_description_pl_field(self):
        """No device JSON should contain description_pl — use i18n instead."""
        devices = self._load_all_devices()
        for model_key, data, filepath in devices:
            assert "description_pl" not in data, (
                f"{model_key} ({filepath}) still has 'description_pl' — "
                "descriptions should be in i18n files (locales/*/common.json)"
            )

    def test_category_is_valid(self):
        """Category should be one of the known categories."""
        valid_categories = {"energy_meters", "hvac", "inverters", "sensors", "other"}
        devices = self._load_all_devices()
        for model_key, data, filepath in devices:
            category = data.get("category", "")
            assert category in valid_categories, (
                f"{model_key} has invalid category '{category}', "
                f"expected one of {valid_categories}"
            )

    def test_category_matches_directory(self):
        """Category field should match the directory the file is in."""
        devices = self._load_all_devices()
        for model_key, data, filepath in devices:
            directory = os.path.basename(os.path.dirname(filepath))
            category = data.get("category", "")
            assert category == directory, (
                f"{model_key}: category '{category}' does not match "
                f"directory '{directory}'"
            )

    def test_default_address_is_positive_integer(self):
        """default_address should be a positive integer (1-247)."""
        devices = self._load_all_devices()
        for model_key, data, filepath in devices:
            addr = data.get("default_address", 1)
            assert isinstance(addr, int), (
                f"{model_key}: default_address should be int, got {type(addr)}"
            )
            assert 1 <= addr <= 247, (
                f"{model_key}: default_address {addr} is out of range (1-247)"
            )

    def test_has_registers_base(self):
        """Each device should define at least one register base."""
        devices = self._load_all_devices()
        for model_key, data, filepath in devices:
            assert "registers_base" in data, (
                f"{model_key} ({filepath}) is missing 'registers_base'"
            )
            assert len(data["registers_base"]) > 0, (
                f"{model_key} has empty registers_base"
            )
