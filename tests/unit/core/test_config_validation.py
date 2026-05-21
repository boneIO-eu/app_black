import pytest
from boneio.core.config.yaml_util import load_config_from_string, ConfigurationException

def test_remote_outputs_interlock_group_string():
    config_str = """
boneio:
  name: test
remote_outputs:
  - remote_source: esphome_api
    device_id: test_device
    output_id: relay1
    interlock_group: pumps
"""
    # This should fail with the current schema, but pass after our changes.
    # We will test both states.
    try:
        config = load_config_from_string(config_str)
        assert config is not None
        assert config["remote_outputs"][0]["interlock_group"] == "pumps"
    except ConfigurationException as e:
        pytest.fail(f"Configuration validation failed: {e}")

def test_remote_outputs_interlock_group_list():
    config_str = """
boneio:
  name: test
remote_outputs:
  - remote_source: esphome_api
    device_id: test_device
    output_id: relay1
    interlock_group:
      - pumps
      - heating
"""
    config = load_config_from_string(config_str)
    assert config is not None
    assert config["remote_outputs"][0]["interlock_group"] == ["pumps", "heating"]
