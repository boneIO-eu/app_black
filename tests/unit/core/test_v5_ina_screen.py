"""Tests for Migration v5: ina219 -> ina in oled.screens."""

from __future__ import annotations

from boneio.core.config.migrations.v5_ina_screen import (
    _persist_ina_screen,
    migrate_v5_ina_screen,
)


def test_migrate_v5_dict():
    doc = {
        "oled": {
            "enabled": True,
            "screens": ["uptime", "network", "ina219", "cpu"],
        }
    }
    result = migrate_v5_ina_screen(doc)
    assert result["oled"]["screens"] == ["uptime", "network", "ina", "cpu"]


def test_migrate_v5_file(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "oled:\n"
        "  enabled: yes\n"
        "  screens:\n"
        "    - uptime\n"
        "    - network\n"
        "    - ina219\n"
        "    - cpu\n"
    )
    _persist_ina_screen(str(config_file))
    content = config_file.read_text()
    assert "- ina\n" in content
    assert "- ina219" not in content
