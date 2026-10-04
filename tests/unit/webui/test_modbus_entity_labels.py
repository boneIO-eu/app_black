"""Saving Modbus entity labels writes them into the file's own entry.

The route used to write back the running config's modbus_devices, which
has the schema's defaults filled in, so naming one sensor put every default
of every device into the user's file.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import yaml

from boneio.webui.routes import modbus


def test_the_file_gains_only_the_labels(tmp_path):
    on_disk = {"modbus_devices": [{"id": "Licznik", "address": 1, "model": "sdm630"}]}
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.safe_dump(on_disk), encoding="utf-8")

    manager = MagicMock()
    manager._config_file_path = str(config_file)
    manager.config_helper.get_config.return_value = {
        "modbus_devices": [{**on_disk["modbus_devices"][0], "update_interval": "30s", "data_bits": 8}]
    }

    with patch("boneio.webui.routes.config.invalidate_config_cache") as invalidate:
        result = asyncio.run(modbus.set_entity_labels("licznik", {"power": "Moc"}, manager))

    assert "warning" not in result
    written = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    assert written["modbus_devices"] == [{**on_disk["modbus_devices"][0], "entity_labels": {"power": "Moc"}}]
    invalidate.assert_called_once_with(section="modbus_devices", section_data=written["modbus_devices"])
    manager.config_helper.get_config.assert_not_called()
