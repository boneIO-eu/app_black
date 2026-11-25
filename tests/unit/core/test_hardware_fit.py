"""A backup restored on another controller revision keeps this one's hardware."""

from __future__ import annotations

import shutil

import yaml

from boneio.core.config.hardware_fit import _TagBlindLoader, compare_hardware, fit_restored_config, hardware_of
from boneio.core.config.yaml_util import load_config_from_file
from boneio.factory_config import template_dir


def _restored_08_backup(tmp_path, adc_inline=False):
    """config dir as a restore of a 0.8 32x10 backup leaves it, ADC in use."""
    shutil.copytree(template_dir("32x10", "0.8"), tmp_path, dirs_exist_ok=True)
    config = tmp_path / "config.yaml"
    text = config.read_text().replace("# adc: !include adc.yaml", "adc: !include adc.yaml")
    if adc_inline:
        text = text.replace("adc: !include adc.yaml", "adc:\n  - name: adc3\n    pin: P9_37\n  - name: adc5\n    pin: 'P9_35'")
    config.write_text(text)
    return config


def test_08_backup_on_11_takes_this_controllers_hardware(tmp_path):
    config = _restored_08_backup(tmp_path)

    changes, adc_range_changed = fit_restored_config(tmp_path, "1.1")

    text = config.read_text()
    assert hardware_of(text)["version"] == "1.1"
    assert "\nina226:" in text and "ina219" not in text
    # terminal adc3/adc4 and adc5/adc6 sit on swapped AIN pins from 1.0 on
    restored = yaml.safe_load((tmp_path / "adc.yaml").read_text())
    assert restored == yaml.safe_load((template_dir("32x10", "1.1") / "adc.yaml").read_text())
    assert any("ina219" in c for c in changes)
    assert adc_range_changed  # the range can't be fitted, only told
    load_config_from_file(str(config))  # still a valid configuration


def test_inline_adc_pins_follow_too(tmp_path):
    config = _restored_08_backup(tmp_path, adc_inline=True)

    fit_restored_config(tmp_path, "1.0")

    text = config.read_text()
    assert "pin: P9_38" in text and "pin: 'P9_36'" in text
    assert (tmp_path / "adc.yaml").read_text() == (template_dir("32x10", "0.8") / "adc.yaml").read_text()


def test_empty_target_sensor_key_is_not_duplicated(tmp_path):
    """Real 1.6.0 backups of 0.8 carry an empty ``ina226: []`` beside ``ina219``."""
    for empty_first in (True, False):
        config = _restored_08_backup(tmp_path)
        text = config.read_text()
        config.write_text("ina226: []\n" + text if empty_first else text + "\nina226: []\n")

        fit_restored_config(tmp_path, "1.1")

        text = config.read_text()
        assert text.count("\nina226:") + text.startswith("ina226:") == 1, text
        assert "ina226: []" not in text and "ina219" not in text
        load_config_from_file(str(config))


def test_target_sensor_key_with_content_wins(tmp_path):
    config = _restored_08_backup(tmp_path)
    config.write_text(config.read_text() + "\nina226:\n  - address: 0x41\n")

    changes, _ = fit_restored_config(tmp_path, "1.1")

    text = config.read_text()
    assert text.count("ina226:") == 1 and "0x41" in text
    assert not any("ina219" in c for c in changes)


def test_same_revision_is_left_alone(tmp_path):
    config = _restored_08_backup(tmp_path)
    before = config.read_text()

    assert fit_restored_config(tmp_path, "0.8") == ([], False)
    assert fit_restored_config(tmp_path, None) == ([], False)
    assert config.read_text() == before


def test_board_expanders_left_in_the_backup_follow_the_revision(tmp_path):
    # merged board config that leaked into a 0.8 config.yaml: on 1.1 it
    # would override the board's active-low relays
    config = _restored_08_backup(tmp_path)
    config.write_text(
        config.read_text()
        + "mcp23017:\n  - id: mcp_left\n    address: 0x23\n    inverted: false\n"
        + "  - id: extra\n    address: 0x27\n    inverted: false  # user's own\n"
    )

    changes, _ = fit_restored_config(tmp_path, "1.1")

    expanders = {e["address"]: e["inverted"] for e in hardware_yaml(config)["mcp23017"]}
    assert expanders == {0x23: True, 0x27: False}
    assert "mcp23017 0x23: inverted false → true" in changes


def hardware_yaml(config):
    return yaml.load(config.read_text(), Loader=_TagBlindLoader)


def test_compare_reports_revision_and_type():
    backup = 'boneio:\n  version: 0.8\n  device_type: "32x10A"\nmqtt: !include mqtt.yaml\n'
    current = "boneio:\n  version: 1.1\n  device_type: 24x16A\n"

    result = compare_hardware(backup, current)

    assert result["backup_version"] == "0.8" and result["current_version"] == "1.1"
    assert result["version_mismatch"] and result["device_type_mismatch"]
    assert not compare_hardware(backup, backup)["version_mismatch"]
    assert not compare_hardware("not: [yaml", current)["version_mismatch"]
