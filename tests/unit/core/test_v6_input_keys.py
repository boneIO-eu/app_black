"""Tests for Migration v6: gpio_mode and clear_message removed from inputs."""

from __future__ import annotations

import yaml

from boneio.core.config.migrations import _has_legacy_fields, run_migrations
from boneio.core.config.migrations.v6_input_keys import (
    _persist_input_keys,
    migrate_v6_input_keys,
)


def test_migrate_v6_dict():
    doc = {
        "event": [{"name": "IN_01", "pin": "P8_37", "gpio_mode": "gpio_pu", "clear_message": True}],
        "binary_sensor": [{"name": "IN_02", "pin": "P8_38", "clear_message": False}],
        "output": [{"id": "OUT_01", "gpio_mode": "keep-me"}],
    }
    result = migrate_v6_input_keys(doc)
    assert result["event"] == [{"name": "IN_01", "pin": "P8_37"}]
    assert result["binary_sensor"] == [{"name": "IN_02", "pin": "P8_38"}]
    # Only inputs are touched.
    assert result["output"] == [{"id": "OUT_01", "gpio_mode": "keep-me"}]


def test_legacy_detection():
    assert _has_legacy_fields({"event": [{"name": "a", "gpio_mode": "gpio_pu"}]})
    assert _has_legacy_fields({"binary_sensor": [{"name": "a", "clear_message": False}]})
    assert not _has_legacy_fields({"event": [{"name": "a"}]})


def test_migrate_v6_file_inline_sections(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "boneio:\n"
        "  name: test\n"
        "output:\n"
        "  - id: OUT_01\n"
        "    gpio_mode: untouched\n"
        "event:\n"
        "  - name: IN_01\n"
        "    pin: P8_37\n"
        "    gpio_mode: gpio_pu\n"
        "  - gpio_mode: gpio_pu  # first key of the item\n"
        "    clear_message: true\n"
        "    name: IN_02\n"
        "    pin: P8_38\n"
        "binary_sensor:\n"
        "- name: IN_03\n"
        "  clear_message: false\n"
    )
    _persist_input_keys(str(config_file))
    data = yaml.safe_load(config_file.read_text())
    assert data["event"] == [
        {"name": "IN_01", "pin": "P8_37"},
        {"name": "IN_02", "pin": "P8_38"},
    ]
    assert data["binary_sensor"] == [{"name": "IN_03"}]
    assert data["output"] == [{"id": "OUT_01", "gpio_mode": "untouched"}]


def test_migrate_v6_file_follows_include(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "boneio:\n"
        "  name: test\n"
        "event: !include event.yaml\n"
        "binary_sensor: !include binary_sensor.yaml  # inputs\n"
    )
    (tmp_path / "event.yaml").write_text(
        "- name: IN_01\n"
        "  pin: P8_37\n"
        "  gpio_mode: gpio_pu\n"
        "  clear_message: true\n"
        "  actions:\n"
        "    single:\n"
        "      - action: output\n"
        "        pin: OUT_01\n"
    )
    (tmp_path / "binary_sensor.yaml").write_text("- name: IN_02\n  gpio_mode: gpio\n")
    before = config_file.read_text()

    _persist_input_keys(str(config_file))

    assert config_file.read_text() == before
    event = yaml.safe_load((tmp_path / "event.yaml").read_text())
    assert event == [
        {
            "name": "IN_01",
            "pin": "P8_37",
            "actions": {"single": [{"action": "output", "pin": "OUT_01"}]},
        }
    ]
    assert yaml.safe_load((tmp_path / "binary_sensor.yaml").read_text()) == [{"name": "IN_02"}]


def test_run_migrations_from_v5_persists(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "boneio:\n"
        "  name: test\n"
        "  config_version: 5\n"
        "event:\n"
        "  - name: IN_01\n"
        "    gpio_mode: gpio_pu\n"
        "    clear_message: true\n"
    )
    doc = yaml.safe_load(config_file.read_text())
    doc, version = run_migrations(doc, config_file=str(config_file))
    assert version == 6
    assert doc["event"] == [{"name": "IN_01"}]
    content = config_file.read_text()
    assert "gpio_mode" not in content
    assert "clear_message" not in content
    assert "config_version: 6" in content
