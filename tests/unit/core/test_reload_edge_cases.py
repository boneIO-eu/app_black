"""Three reload paths that left something behind.

- A cover whose platform changed was dropped mid-movement with its relay on.
- A virtual energy sensor kept tracking its old output when output_id changed.
- Deleted or moved outputs stayed in grouped_outputs_by_expander, so on the OLED.
"""

from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

mock_gpiod = MagicMock()
sys.modules.setdefault("gpiod", mock_gpiod)
sys.modules.setdefault("gpiod.line", mock_gpiod.line)

from boneio.const import OFF, ON  # noqa: E402
from boneio.core.manager.covers import CoverManager  # noqa: E402
from boneio.core.manager.outputs import OutputManager  # noqa: E402
from boneio.core.manager.sensors import SensorManager  # noqa: E402


# ── cover platform change ────────────────────────────────────────────────────


def _moving_cover() -> MagicMock:
    cover = MagicMock()
    cover.kind = "time"
    cover.is_remote = False
    cover._movement_thread.is_alive.return_value = True
    return cover


def test_cover_changing_platform_is_stopped_before_it_is_dropped():
    old = _moving_cover()
    cm = CoverManager.__new__(CoverManager)
    cm._manager = SimpleNamespace(
        outputs=MagicMock(),
        _config_helper=MagicMock(get_autodiscovery_topics_for_id=MagicMock(return_value=[])),
        send_message=MagicMock(),
    )
    cm._covers = {"salon": old}
    cm._config_covers = []
    config = {"cover": [{"id": "salon", "open_relay": "o1", "close_relay": "o2", "platform": "venetian"}]}

    with (
        patch.object(cm._manager._config_helper, "get_config", return_value=config),
        patch.object(cm, "_configure_cover", return_value=MagicMock()) as recreate,
    ):
        cm._configure_covers(reload_config=True)

    old._stop_event.set.assert_called_once()
    old._movement_thread.join.assert_called_once()
    old._open_relay.turn_off.assert_called_once()
    old._close_relay.turn_off.assert_called_once()
    recreate.assert_called_once()
    assert cm._covers["salon"] is recreate.return_value


def test_a_failing_halt_does_not_stop_the_reload():
    cover = _moving_cover()
    cover._open_relay.turn_off.side_effect = OSError("i2c")

    CoverManager._halt_cover(cover)

    cover._stop_event.set.assert_called_once()


# ── virtual energy sensor output change ──────────────────────────────────────


def _sensor_manager(outputs: dict) -> tuple[SensorManager, MagicMock]:
    sensor = MagicMock()
    sensor.id = "licznik"
    sensor.name = "Licznik"
    sensor.output_id = "out_01"
    sensor._power_usage = 30
    bus = MagicMock()
    sm = SensorManager.__new__(SensorManager)
    sm._manager = SimpleNamespace(
        _config_helper=MagicMock(),
        _event_bus=bus,
        outputs=SimpleNamespace(get_output=outputs.get),
    )
    sm._virtual_energy_sensors = [sensor]
    sm._virtual_energy_sensor_configs = []
    return sm, sensor


def _reload_sensors(sm, output_id: str) -> None:
    config = {
        "virtual_energy_sensor": [
            {"id": "licznik", "name": "Licznik", "output_id": output_id, "sensor_type": "power", "power_usage": 30}
        ]
    }
    with (
        patch.object(sm._manager._config_helper, "get_config", return_value=config),
        patch.object(sm, "_publish_virtual_energy_discovery"),
        patch.object(sm, "_broadcast_virtual_energy_states", new=MagicMock(return_value=asyncio.sleep(0))),
    ):
        asyncio.new_event_loop().run_until_complete(sm.reload_virtual_energy_sensors())


def test_sensor_follows_a_changed_output_id():
    new_output = SimpleNamespace(id="out_02", state=ON)
    sm, sensor = _sensor_manager({"out_02": new_output})

    _reload_sensors(sm, "out_02")

    sensor.stop_tracking.assert_called_once()
    resolve = sensor.rebind_output.call_args.args[0]
    assert resolve(object()) is new_output
    bus = sm._manager._event_bus
    bus.remove_event_listener.assert_called_once_with(event_type="output", listener_id="virtual_energy_licznik")
    assert bus.add_event_listener.call_args.kwargs["entity_id"] == "out_02"
    assert bus.add_event_listener.call_args.kwargs["listener_id"] == "virtual_energy_licznik"
    sensor.start_tracking.assert_called_once()


def test_sensor_on_an_output_that_is_off_waits_for_it():
    sm, sensor = _sensor_manager({"out_02": SimpleNamespace(id="out_02", state=OFF)})

    _reload_sensors(sm, "out_02")

    sensor.rebind_output.assert_called_once()
    sensor.start_tracking.assert_not_called()


def test_sensor_keeps_its_output_when_the_new_one_does_not_exist():
    sm, sensor = _sensor_manager({})

    _reload_sensors(sm, "nope")

    sensor.rebind_output.assert_not_called()
    sm._manager._event_bus.add_event_listener.assert_not_called()


def test_unchanged_output_id_touches_nothing():
    sm, sensor = _sensor_manager({"out_01": SimpleNamespace(id="out_01", state=ON)})

    _reload_sensors(sm, "out_01")

    sensor.rebind_output.assert_not_called()
    sensor.stop_tracking.assert_not_called()


# ── grouped_outputs_by_expander ──────────────────────────────────────────────


def test_reload_drops_deleted_and_moved_outputs_from_the_expander_groups():
    kept, moved_old, moved_new, deleted = (SimpleNamespace(id=i) for i in ("k", "m", "m", "d"))
    shared = {"mcp1": {"k": kept, "m": moved_old, "d": deleted}, "mcp2": {"m": moved_new}}
    om = OutputManager.__new__(OutputManager)
    om.grouped_outputs_by_expander = shared
    om._outputs = {"k": kept, "m": moved_new}

    om._prune_expander_groups()

    assert om.grouped_outputs_by_expander is shared, "HostData holds this very dict"
    assert shared == {"mcp1": {"k": kept}, "mcp2": {"m": moved_new}}


def test_a_group_being_read_is_replaced_not_changed():
    """The OLED thread may be iterating the old dict while the reload runs."""
    out = SimpleNamespace(id="k")
    group = {"k": out, "d": SimpleNamespace(id="d")}
    om = OutputManager.__new__(OutputManager)
    om.grouped_outputs_by_expander = {"mcp1": group}
    om._outputs = {"k": out}

    om._prune_expander_groups()

    assert set(group) == {"k", "d"}
    assert om.grouped_outputs_by_expander["mcp1"] is not group


def test_initialize_outputs_on_reload_prunes():
    om = OutputManager.__new__(OutputManager)
    om._manager = SimpleNamespace(_event_bus=MagicMock(), loop=MagicMock())
    om._outputs = {"d": SimpleNamespace(id="d", output_type="switch", is_remote=False)}
    om._interlock_manager = MagicMock()
    om._ha_topics = set()
    om.grouped_outputs_by_expander = {"mcp1": {"d": om._outputs["d"]}}

    om._initialize_outputs(relay_pins=[], reload_config=True)

    assert om.grouped_outputs_by_expander == {"mcp1": {}}
