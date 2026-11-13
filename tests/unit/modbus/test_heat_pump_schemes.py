import pytest

from boneio.modbus.heat_pump import SCHEMES, Write, state

lg = SCHEMES["lg_therma"]
phnix = SCHEMES["phnix"]


@pytest.mark.parametrize(
    "v,expected",
    [
        ({"power": "OFF", "mode": 4}, "off"),
        ({"power": "ON", "mode": 3}, "auto"),
        ({"power": "ON", "mode": 4}, "heat"),
        ({"power": "ON", "mode": 0}, "cool"),
        ({"mode": 4}, "heat"),
        ({"power": "ON"}, None),
    ],
)
def test_lg_hvac_mode(v, expected):
    assert lg.hvac_mode(v) == expected


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("heat", [Write("mode", 4), Write("power", "ON")]),
        ("cool", [Write("mode", 0), Write("power", "ON")]),
        ("auto", [Write("mode", 3), Write("power", "ON")]),
        ("off", [Write("power", "OFF")]),
    ],
)
def test_lg_set_hvac_mode(mode, expected):
    assert lg.set_hvac_mode({"power": "OFF", "mode": 4}, mode) == expected


@pytest.mark.parametrize(
    "v,expected",
    [
        ({"power": "ON", "defrost": "ON", "compressor": "ON", "outdoor_cycle": 2}, "defrosting"),
        ({"power": "ON", "defrost": "0", "compressor": "1", "outdoor_cycle": 2}, "heating"),
        ({"power": "ON", "compressor": True, "outdoor_cycle": 1}, "cooling"),
        ({"power": "ON", "compressor": "OFF", "outdoor_cycle": 2}, "idle"),
        ({"power": "ON"}, "idle"),
        ({"power": "OFF", "defrost": "ON", "compressor": "ON"}, "off"),
    ],
)
def test_lg_hvac_action(v, expected):
    assert lg.hvac_action(v) == expected


@pytest.mark.parametrize(
    "method,expected",
    [(0, 35.0), (1, 30.0), (2, 21.5), (None, None), (9, None)],
)
def test_lg_current_by_control_method(method, expected):
    v = {"control_method": method, "room": 21.5, "supply": 35.0, "return": 30.0}
    assert lg.current(v) == expected


def test_lg_target_and_dhw():
    v = {"heating_target": 40, "mode": 0}
    assert lg.target_role(v) == "heating_target"
    assert lg.target(v) == 40.0
    assert lg.target({}) is None
    assert lg.dhw_mode({"dhw_enable": "ON"}) == "heat_pump"
    assert lg.dhw_mode({"dhw_enable": "OFF"}) == "off"
    assert lg.set_dhw_mode({}, "heat_pump") == [Write("dhw_enable", "ON")]
    assert lg.set_dhw_mode({}, "off") == [Write("dhw_enable", "OFF")]


@pytest.mark.parametrize(
    "v,mode,expected",
    [
        ({"power": "ON", "mode": 0}, "heat", [Write("mode", 3)]),
        ({"power": "ON", "mode": 2}, "heat", [Write("mode", 1)]),
        ({"power": "ON", "mode": 1}, "cool", [Write("mode", 2)]),
        ({"power": "ON", "mode": 3}, "cool", [Write("mode", 4)]),
        ({"power": "ON", "mode": 3}, "off", [Write("mode", 0)]),
        ({"power": "ON", "mode": 1}, "off", [Write("power", "OFF")]),
        ({"power": "OFF", "mode": 1}, "heat", [Write("mode", 1), Write("power", "ON")]),
        ({"power": "OFF", "mode": 0}, "heat", [Write("mode", 1), Write("power", "ON")]),
        ({"power": "OFF", "mode": 3}, "heat", [Write("mode", 1), Write("power", "ON")]),
        ({"power": "OFF", "mode": 4}, "cool", [Write("mode", 2), Write("power", "ON")]),
    ],
)
def test_phnix_set_hvac_mode(v, mode, expected):
    assert phnix.set_hvac_mode(v, mode) == expected


def test_phnix_rejects_auto():
    with pytest.raises(ValueError):
        phnix.set_hvac_mode({"power": "ON", "mode": 1}, "auto")


@pytest.mark.parametrize(
    "v,mode,expected",
    [
        ({"power": "ON", "mode": 1}, "heat_pump", [Write("mode", 3)]),
        ({"power": "ON", "mode": 2}, "heat_pump", [Write("mode", 4)]),
        ({"power": "ON", "mode": 3}, "heat_pump", []),
        ({"power": "ON", "mode": 0}, "off", [Write("power", "OFF")]),
        ({"power": "ON", "mode": 3}, "off", [Write("mode", 1)]),
        ({"power": "ON", "mode": 4}, "off", [Write("mode", 2)]),
        ({"power": "ON", "mode": 1}, "off", []),
        ({"power": "OFF", "mode": 1}, "heat_pump", [Write("mode", 0), Write("power", "ON")]),
        ({"power": "OFF", "mode": 3}, "heat_pump", [Write("mode", 0), Write("power", "ON")]),
        ({"power": "OFF", "mode": 3}, "off", []),
    ],
)
def test_phnix_set_dhw_mode(v, mode, expected):
    assert phnix.set_dhw_mode(v, mode) == expected


@pytest.mark.parametrize(
    "v,expected",
    [
        ({"power": "OFF", "mode": 3}, "off"),
        ({"power": "ON", "mode": 0}, "off"),
        ({"power": "ON", "mode": 1}, "heat"),
        ({"power": "ON", "mode": 3}, "heat"),
        ({"power": "ON", "mode": 2}, "cool"),
        ({"power": "ON", "mode": 4}, "cool"),
        ({"power": "ON"}, None),
    ],
)
def test_phnix_hvac_mode(v, expected):
    assert phnix.hvac_mode(v) == expected


@pytest.mark.parametrize(
    "v,expected",
    [
        ({"power": "OFF", "operating_state": 1, "compressor": "ON"}, "off"),
        ({"power": "ON", "operating_state": 2, "compressor": "OFF"}, "defrosting"),
        ({"power": "ON", "operating_state": 1, "compressor": "ON"}, "heating"),
        ({"power": "ON", "operating_state": 0, "compressor": "1"}, "cooling"),
        ({"power": "ON", "operating_state": 1, "compressor": "OFF"}, "idle"),
        ({"power": "ON", "operating_state": 1}, "heating"),
        ({"power": "ON", "operating_state": 3, "compressor": "ON"}, "idle"),
        ({"power": "ON", "operating_state": 4, "compressor": "ON"}, "idle"),
        ({"power": "ON"}, "idle"),
    ],
)
def test_phnix_hvac_action(v, expected):
    assert phnix.hvac_action(v) == expected


def test_phnix_targets_and_dhw_mode():
    assert phnix.target_role({"mode": 4}) == "cooling_target"
    assert phnix.target_role({"mode": 2}) == "cooling_target"
    assert phnix.target_role({"mode": 3}) == "heating_target"
    assert phnix.target_role({"power": "OFF", "mode": 4}) == "heating_target"
    v = {"mode": 2, "heating_target": 40, "cooling_target": 12, "supply": 14.5}
    assert phnix.target(v) == 12.0
    assert phnix.current(v) == 14.5
    assert phnix.dhw_mode({"power": "ON", "mode": 3}) == "heat_pump"
    assert phnix.dhw_mode({"power": "ON", "mode": 1}) == "off"
    assert phnix.dhw_mode({"power": "OFF", "mode": 3}) == "off"


def test_state_payload_with_unknowns():
    assert state(phnix, {}) == {
        "mode": None,
        "action": "idle",
        "current_temperature": None,
        "target_temperature": None,
        "dhw_mode": "off",
        "dhw_current": None,
        "dhw_target": None,
    }
    s = state(lg, {"power": "ON", "mode": 4, "control_method": 0, "supply": 33, "heating_target": 35,
                   "dhw_enable": "ON", "dhw_current": 48.5, "dhw_target": 50})
    assert s["mode"] == "heat" and s["current_temperature"] == 33.0 and s["target_temperature"] == 35.0
    assert s["dhw_mode"] == "heat_pump" and s["dhw_current"] == 48.5 and s["dhw_target"] == 50.0
