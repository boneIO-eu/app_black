"""Wanas 415 register map follows the ST-340 V2 manual.

The manual numbers holding registers from 4001; on the wire that is address
0 (a working Grenton setup reads "Bieg nawiewu" 4003 at 2 and "Temp.
nawiewowa" 4007 at 6).
"""

import json
from pathlib import Path

import boneio.modbus.devices as devices

WANAS = Path(devices.__file__).parent / "hvac" / "wanas415.json"


def _registers() -> dict[str, dict]:
    data = json.loads(WANAS.read_text(encoding="utf-8"))
    (block,) = data["registers_base"]
    assert block["base"] == 0
    assert block["register_type"] == "holding"
    return {r["name"]: r for r in block["registers"]}


def test_addresses_are_manual_number_minus_4001():
    regs = _registers()
    assert regs["Wydatek nawiewu"]["address"] == 0
    assert regs["Bieg nawiewu"]["address"] == 2
    assert regs["Temperatura zewnętrzna"]["address"] == 4
    assert regs["Temperatura wyrzutowa"]["address"] == 5
    assert regs["Temperatura nawiewu"]["address"] == 6
    assert regs["Temperatura pomieszczenia"]["address"] == 7
    assert regs["Bieg strefy 1"]["address"] == 14
    assert regs["Temperatura strefy 5"]["address"] == 23
    for r in regs.values():
        assert r.get("write_address", r["address"]) == r["address"]


def test_flows_and_zone_temperatures_are_unscaled():
    regs = _registers()
    for name in ("Wydatek nawiewu", "Wydatek wywiewu", "Temperatura strefy 1"):
        assert "filters" not in regs[name]
