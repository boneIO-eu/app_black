"""Simulated heat pump physics: setpoints and modes are inputs, measurements follow."""

from __future__ import annotations

import pytest

from boneio.modbus.definition import load_definition
from boneio.modbus.simulator import COMPRESSOR_ON_K, SimulatedDevice, _start_words

LG = "lg-therma-v-r290"
PHNIX = "kaisai-phnix"


def _lg(power=True, mode=4, setpoint=35.0, dhw=False, dhw_target=50.0) -> SimulatedDevice:
    d = SimulatedDevice(load_definition(LG))
    d.coil[0], d.coil[1] = int(power), int(dhw)
    d.holding[0] = mode
    d.holding[2] = _start_words(d._roles["heating_target"][1], setpoint)[0]
    d.holding[8] = _start_words(d._roles["dhw_target"][1], dhw_target)[0]
    return d


def _run(d: SimulatedDevice, seconds: int, dt: float = 10) -> None:
    for _ in range(int(seconds / dt)):
        d.step(dt)


def test_supply_moves_toward_setpoint_when_heating():
    d = _lg(setpoint=35.0)
    _run(d, 1800)
    supply = d._get("supply")
    assert 20.5 < supply < 35.0
    assert d.discrete[3] == 1  # compressor
    assert d.input[1] == 2  # outdoor unit cycle: heating
    _run(d, 6 * 3600)
    assert d._get("supply") == pytest.approx(35.0, abs=COMPRESSOR_ON_K)


def test_compressor_has_hysteresis():
    d = _lg(setpoint=30.0)
    approach = []
    for _ in range(3000):
        err = abs(30.0 - d._supply)
        d.step(10)
        if not d.discrete[3]:
            break
        approach.append(err)
    else:
        pytest.fail("compressor never stopped")
    # on through the whole dead band, off only once below 0.5 K
    assert approach[0] > 2.0 and min(approach) < 1.0
    assert err < 0.5


def test_nothing_moves_when_power_off():
    d = _lg(power=False, setpoint=45.0)
    _run(d, 3600)
    assert d._get("supply") == pytest.approx(20.0)
    assert d.discrete[3] == 0 and d.input[1] == 0


def test_dhw_heats_only_when_enabled():
    d = _lg(power=False, dhw=False, dhw_target=40.0)
    _run(d, 600)
    assert d._get("dhw_current") == pytest.approx(20.0)
    d.coil[1] = 1
    _run(d, 600)
    assert d._get("dhw_current") == pytest.approx(30.0, abs=0.2)  # +1 K/min
    assert d.discrete[3] == 1 and d.discrete[5] == 1


def test_defrost_runs_60s_every_40_minutes_in_the_cold():
    d = _lg(setpoint=60.0)
    d._elapsed = 4.5 * 3600  # outdoor at its coldest
    flags = []
    for _ in range(2 * 3600 // 10):
        d.step(10)
        flags.append(d.discrete[4])
    assert 60 <= sum(flags) * 10 <= 3 * 70


def test_phnix_cooling_uses_cooling_target():
    d = SimulatedDevice(load_definition(PHNIX))
    r = d._roles
    d.holding[1011], d.holding[1012] = 1, 2
    d.holding[1159] = _start_words(r["cooling_target"][1], 10.0)[0]
    _run(d, 3600)
    assert d._get("supply") < 15.0
    assert d._get("operating_state") == 0


def test_temperature_sensors_without_heat_pump_only_jitter():
    from tests.unit.modbus.definitions import definition

    d = SimulatedDevice(
        definition(
            [
                {
                    "base": 0,
                    "length": 1,
                    "register_type": "input",
                    "registers": [
                        {"name": "Temp", "address": 0, "value_type": "S_WORD", "device_class": "temperature",
                         "filters": [{"multiply": 0.1}]}
                    ],
                }
            ]
        )
    )
    for _ in range(50):
        d.step(1)
        assert abs(d.input[0] / 10 - 20.0) <= 0.1 + 1e-9


def test_phnix_idle_state_matches_mode_and_power_state_follows_power():
    d = SimulatedDevice(load_definition(PHNIX))
    d.holding[1011], d.holding[1012] = 1, 1
    d.holding[1158] = _start_words(d._roles["heating_target"][1], 20.0)[0]
    d.step(10)
    assert d.holding[2012] == 1 and d.holding[2011] == 1  # heating, idle
    d.holding[1012] = 2
    d.step(10)
    assert d.holding[2012] == 0
    d.holding[1012] = 0
    d.step(10)
    assert d.holding[2012] == 4
    d.holding[1011] = 0
    d.step(10)
    assert d.holding[2011] == 0


def test_dhw_heating_resumes_one_kelvin_below_target():
    d = _lg(power=False, dhw=True, dhw_target=25.0)
    _run(d, 302, dt=1)  # reaches 25 and stops
    assert d._dhw == pytest.approx(25.0, abs=0.1) and d.discrete[5] == 0
    _run(d, 300, dt=1)  # loses only 0.5 K: still off
    assert d.discrete[5] == 0
    for _ in range(1000):
        d.step(1)
        if d.discrete[5]:
            break
    else:
        pytest.fail("DHW heating never resumed")
    assert 23.9 < d._dhw < 24.1


def test_setpoint_below_supply_does_not_run_compressor_when_heating():
    d = _lg(setpoint=10.0)
    d.step(10)
    assert d.discrete[3] == 0
