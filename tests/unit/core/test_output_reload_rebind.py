"""After an output reload, everything that holds an output must hold the current one.

The reload rebuilds every local output and group as a new object under the
same id. Covers, irrigation, thermostats, gates, alarms and virtual energy
sensors looked theirs up once at setup, so they went on driving and reading
the old object, whose state no longer changed: a virtual energy sensor stopped
counting, and the interlock checked objects nobody switched any more.
"""

from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

mock_gpiod = MagicMock()
sys.modules.setdefault("gpiod", mock_gpiod)
sys.modules.setdefault("gpiod.line", mock_gpiod.line)

from boneio.components.irrigation import IrrigationZone, WaterSource  # noqa: E402
from boneio.components.sensor.virtual_energy import VirtualEnergySensor  # noqa: E402
from boneio.components.template.alarm_panel import AlarmOutput, BoneIOAlarmPanel  # noqa: E402
from boneio.components.template.gate_cover import BoneIOGateCover  # noqa: E402
from boneio.components.template.thermostat import BoneIOThermostat  # noqa: E402
from boneio.core.manager.covers import CoverManager  # noqa: E402
from boneio.core.manager.irrigation import IrrigationManager  # noqa: E402
from boneio.core.manager.outputs import OutputManager  # noqa: E402
from boneio.core.manager.sensors import SensorManager  # noqa: E402
from boneio.core.manager.templates import TemplateManager  # noqa: E402


class _Out:
    def __init__(self, output_id: str):
        self.id = output_id


def _output_manager(outputs: dict, groups: dict | None = None) -> OutputManager:
    om = OutputManager.__new__(OutputManager)
    om._manager = SimpleNamespace()
    om._outputs = dict(outputs)
    om._configured_output_groups = dict(groups or {})
    return om


OLD = {name: _Out(name) for name in ("out_01", "out_02", "out_03", "pump", "grupa")}


def _after_reload() -> tuple[OutputManager, dict]:
    new = {name: _Out(name) for name in ("out_01", "out_02", "out_03", "pump")}
    om = _output_manager(new, {"grupa": _Out("grupa")})
    return om, {**new, "grupa": om._configured_output_groups["grupa"]}


# ── resolve_current ──────────────────────────────────────────────────────────


def test_resolve_returns_the_object_registered_now():
    om, new = _after_reload()
    assert om.resolve_current(OLD["out_01"]) is new["out_01"]


def test_resolve_keeps_the_old_object_when_its_id_is_gone():
    om, _ = _after_reload()
    gone = _Out("deleted")
    assert om.resolve_current(gone) is gone


def test_resolve_finds_groups_only_when_asked():
    om, new = _after_reload()
    assert om.resolve_current(OLD["grupa"]) is OLD["grupa"]
    assert om.resolve_current(OLD["grupa"], include_groups=True) is new["grupa"]


def test_resolve_none_is_none():
    om, _ = _after_reload()
    assert om.resolve_current(None) is None


# ── reload_outputs triggers it ───────────────────────────────────────────────


def test_reload_rebinds_after_groups_are_rebuilt():
    om = _output_manager({})
    om._interlock_manager = MagicMock()
    om._ha_topics = set()
    order: list[str] = []
    owners = {
        name: SimpleNamespace(rebind_outputs=lambda n=name: order.append(n))
        for name in ("covers", "irrigation", "templates", "sensors")
    }
    om._manager = SimpleNamespace(
        _config_helper=SimpleNamespace(get_config=lambda: {"output": [], "output_group": []}),
        **owners,
    )
    with (
        patch.object(om, "_initialize_outputs", side_effect=lambda **kw: order.append("outputs")),
        patch.object(om, "_configure_output_groups", side_effect=lambda: order.append("groups")),
        patch.object(om, "_broadcast_all_states"),
    ):
        asyncio.new_event_loop().run_until_complete(om.reload_outputs())

    assert order == ["outputs", "groups", "covers", "irrigation", "templates", "sensors"]


def test_one_failing_owner_does_not_stop_the_others():
    om = _output_manager({})
    done: list[str] = []

    def boom():
        raise RuntimeError("boom")

    om._manager = SimpleNamespace(
        covers=SimpleNamespace(rebind_outputs=boom),
        sensors=SimpleNamespace(rebind_outputs=lambda: done.append("sensors")),
    )
    om._rebind_dependents()

    assert done == ["sensors"]


# ── owners ───────────────────────────────────────────────────────────────────


def test_covers_take_the_current_relays_and_skip_remote_ones():
    om, new = _after_reload()
    local = SimpleNamespace(_open_relay=OLD["out_01"], _close_relay=OLD["out_02"], is_remote=False)
    remote = SimpleNamespace(is_remote=True)
    cm = CoverManager.__new__(CoverManager)
    cm._manager = SimpleNamespace(outputs=om)
    cm._covers = {"salon": local, "remote": remote}

    cm.rebind_outputs()

    assert local._open_relay is new["out_01"]
    assert local._close_relay is new["out_02"]
    assert not hasattr(remote, "_open_relay")


def test_irrigation_takes_the_current_valves_and_pump_without_stopping():
    om, new = _after_reload()
    zone = IrrigationZone(id="trawnik", name="Trawnik", valve=OLD["out_03"], run_duration=60)
    pump_outputs = [OLD["pump"]]
    source = WaterSource.__new__(WaterSource)
    source.outputs = pump_outputs
    ctrl = MagicMock(zones=[zone], water_sources=[source])
    im = IrrigationManager.__new__(IrrigationManager)
    im._manager = SimpleNamespace(outputs=om)
    im._controllers = {"ogrod": ctrl}

    im.rebind_outputs()

    assert zone.valve is new["out_03"]
    assert source.outputs is pump_outputs, "a running activate() iterates this very list"
    assert pump_outputs == [new["pump"]]
    ctrl.full_stop.assert_not_called()


def _thermostat(output) -> BoneIOThermostat:
    t = BoneIOThermostat.__new__(BoneIOThermostat)
    t._output = output
    return t


def _gate(**outputs) -> BoneIOGateCover:
    g = BoneIOGateCover.__new__(BoneIOGateCover)
    g._pulse_output = outputs.get("pulse")
    g._open_output = outputs.get("open")
    g._close_output = outputs.get("close")
    g._stop_output = outputs.get("stop")
    return g


def _alarm(*outputs) -> BoneIOAlarmPanel:
    a = BoneIOAlarmPanel.__new__(BoneIOAlarmPanel)
    a._outputs = [AlarmOutput(o) for o in outputs]
    return a


def _templates(om, thermostats=(), gates=(), alarms=()) -> TemplateManager:
    tm = TemplateManager.__new__(TemplateManager)
    tm._manager = SimpleNamespace(outputs=om)
    tm._thermostats = SimpleNamespace(items=list(thermostats))
    tm._gates = SimpleNamespace(items=list(gates))
    tm._alarms = SimpleNamespace(items=list(alarms))
    return tm


def test_thermostat_takes_the_current_output_or_group():
    om, new = _after_reload()
    on_output = _thermostat(OLD["out_01"])
    on_group = _thermostat(OLD["grupa"])

    _templates(om, thermostats=[on_output, on_group]).rebind_outputs()

    assert on_output._output is new["out_01"]
    assert on_group._output is new["grupa"]


def test_gate_takes_the_current_relays_and_keeps_missing_ones_missing():
    om, new = _after_reload()
    gate = _gate(open=OLD["out_01"], close=OLD["out_02"])

    _templates(om, gates=[gate]).rebind_outputs()

    assert gate._open_output is new["out_01"]
    assert gate._close_output is new["out_02"]
    assert gate._pulse_output is None
    assert gate._stop_output is None


def test_alarm_takes_the_current_sirens():
    om, new = _after_reload()
    alarm = _alarm(OLD["out_01"], OLD["out_02"])

    _templates(om, alarms=[alarm]).rebind_outputs()

    assert [ao.output for ao in alarm.outputs] == [new["out_01"], new["out_02"]]


def test_virtual_energy_sensor_takes_the_current_output():
    om, new = _after_reload()
    sensor = VirtualEnergySensor.__new__(VirtualEnergySensor)
    sensor._output = OLD["out_02"]
    sm = SensorManager.__new__(SensorManager)
    sm._manager = SimpleNamespace(outputs=om)
    sm._virtual_energy_sensors = [sensor]

    sm.rebind_outputs()

    assert sensor._output is new["out_02"]
