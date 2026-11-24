"""Tests for Migration v9: the single modbus section becomes a list of buses."""

from __future__ import annotations

import glob

from boneio.core.config.migrations import CURRENT_SCHEMA_VERSION, _has_legacy_fields, run_migrations
from boneio.core.config.migrations.v9_modbus_buses import _persist, migrate_v9_modbus_buses
from boneio.core.config.yaml_util import load_yaml_file, validate_section

BONEIO = "boneio:\n  name: test\n  config_version: 8\n  version: 1.1\n  device_type: 24x16A\n"

MODBUS = """\
modbus:
  # RS485 on the board
  uart: uart4  # built-in
  baudrate: 19200
  parity: E

# Meters
modbus_devices:
  - address: 1
    model: sdm120
"""

BUS = [{"id": "rs485", "port": "uart4", "baudrate": 19200, "parity": "E"}]


def test_dict_becomes_single_bus():
    out = migrate_v9_modbus_buses({"modbus": {"uart": "uart4", "baudrate": 19200, "parity": "E"}})
    assert out["modbus"] == BUS


def test_list_left_alone():
    doc = {"modbus": [{"id": "usb", "port": "/dev/ttyUSB0"}]}
    assert migrate_v9_modbus_buses(doc) == {"modbus": [{"id": "usb", "port": "/dev/ttyUSB0"}]}


def test_no_modbus_section_left_alone():
    assert migrate_v9_modbus_buses({"mqtt": {"host": "h"}}) == {"mqtt": {"host": "h"}}


def test_uart1_config_keeps_its_port():
    assert migrate_v9_modbus_buses({"modbus": {"uart": "uart1"}})["modbus"] == [{"id": "rs485", "port": "uart1"}]


def test_an_unversioned_config_with_the_old_section_is_migrated():
    assert _has_legacy_fields({"modbus": {"uart": "uart4"}})
    assert not _has_legacy_fields({"modbus": [{"id": "rs485", "port": "uart4"}]})


def test_file_migration_keeps_comments(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(BONEIO + MODBUS)
    _persist(str(config))
    text = config.read_text()
    assert "modbus:\n  # RS485 on the board\n  - id: rs485\n    port: uart4  # built-in\n" in text
    assert "\n# Meters\nmodbus_devices:\n  - address: 1\n" in text
    doc = load_yaml_file(str(config))
    assert doc["modbus"] == BUS
    assert doc["modbus_devices"] == [{"address": 1, "model": "sdm120"}]
    assert validate_section("modbus", doc["modbus"], None) == []


def test_file_migration_follows_include(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(BONEIO + "modbus: !include modbus.yaml\n")
    (tmp_path / "modbus.yaml").write_text("# bus\nuart: uart1\nbaudrate: !secret baud\n")
    (tmp_path / "secrets.yaml").write_text("baud: 19200\n")
    _persist(str(config))
    assert "modbus: !include modbus.yaml\n" in config.read_text()
    assert (tmp_path / "modbus.yaml").read_text() == "# bus\n- id: rs485\n  port: uart1\n  baudrate: !secret baud\n"
    assert load_yaml_file(str(config))["modbus"] == [{"id": "rs485", "port": "uart1", "baudrate": 19200}]
    assert not (tmp_path / "backups" / "config.yaml.pre-v9").exists()


def test_file_backup_written(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(BONEIO + MODBUS)
    _persist(str(config))
    assert (tmp_path / "backups" / "config.yaml.pre-v9").read_text() == BONEIO + MODBUS


def test_a_list_in_the_file_is_not_touched(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(BONEIO + "modbus:\n  - id: rs485\n    port: uart4\n")
    _persist(str(config))
    assert config.read_text() == BONEIO + "modbus:\n  - id: rs485\n    port: uart4\n"
    assert not (tmp_path / "backups").exists()


def test_a_flow_mapping_is_left_for_the_recovery_panel(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(BONEIO + "modbus: {uart: uart4}\n")
    _persist(str(config))
    assert config.read_text() == BONEIO + "modbus: {uart: uart4}\n"


def test_a_version_8_config_is_migrated_on_load(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(BONEIO + MODBUS)
    doc, version = run_migrations(load_yaml_file(str(config)), config_file=str(config))
    assert version == CURRENT_SCHEMA_VERSION == 9
    assert doc["modbus"] == BUS
    assert load_yaml_file(str(config))["modbus"] == BUS
    assert "config_version: 9" in config.read_text()


def test_factory_configs_validate():
    paths = glob.glob("boneio/factory_config/*/*/config.yaml")
    assert paths
    for f in paths:
        assert validate_section("modbus", load_yaml_file(f)["modbus"], None) == [], f


def test_an_edit_that_does_not_read_back_is_undone(tmp_path, monkeypatch):
    from boneio.core.config.migrations import v9_modbus_buses

    monkeypatch.setattr(v9_modbus_buses, "_as_list", lambda lines, node: [line.replace("uart4", "uart2") for line in lines])
    config = tmp_path / "config.yaml"
    config.write_text(BONEIO + MODBUS)
    _persist(str(config))
    assert config.read_text() == BONEIO + MODBUS
