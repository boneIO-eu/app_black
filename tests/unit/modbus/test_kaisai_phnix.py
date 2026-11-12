"""Kaisai (Phnix) keeps temperatures in tenths of a degree.

A setpoint written without the x10 would set 4.5 °C instead of 45 °C.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.unit.modbus.test_modbus_coils import _coordinator

DEVICE = Path(__file__).parents[3] / "boneio/modbus/devices/hvac/kaisai-phnix.json"


def _entities() -> dict:
    coordinator = _coordinator(json.loads(DEVICE.read_text())["registers_base"])
    return {name: e for block in coordinator._modbus_entities for name, e in block.items()}


def test_targets_are_written_in_tenths():
    targets = [e for name, e in _entities().items() if name.endswith("targettemperature")]

    assert len(targets) == 3
    assert {e.encode_value(45.5) for e in targets} == {455}


def test_temperatures_are_read_in_tenths():
    entities = _entities()
    for name, raw, value in [("heatingtargettemperature", 455, 45.5), ("ambienttemperature", -75, -7.5)]:
        entities[name].set_value(raw, timestamp=1.0)
        assert entities[name].get_value() == value
