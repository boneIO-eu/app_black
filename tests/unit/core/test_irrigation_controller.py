"""Comprehensive tests for the IrrigationController state machine."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from boneio.components.irrigation.controller import (
    ControllerState,
    IrrigationController,
    IrrigationZone,
    _next_fire_time,
)
from boneio.components.irrigation.water_source import WaterSource
from boneio.const import IRRIGATION, ON, OFF


# ── Helpers ──────────────────────────────────────────────────────────────────

FIXED_NOW = datetime(2026, 4, 7, 10, 0, 0, tzinfo=timezone.utc)
MODULE = "boneio.components.irrigation.controller"


def _mock_valve(name: str = "valve") -> MagicMock:
    v = MagicMock(name=name)
    v.async_turn_on = AsyncMock()
    v.async_turn_off = AsyncMock()
    return v


def _mock_state_manager() -> MagicMock:
    sm = MagicMock()
    sm.get = MagicMock(side_effect=lambda section, key, default: default)
    sm.save_attribute = MagicMock()
    return sm


def _mock_message_bus() -> MagicMock:
    mb = MagicMock()
    mb.send_message = MagicMock()
    return mb


def _mock_event_bus() -> MagicMock:
    eb = MagicMock()
    eb.loop = asyncio.get_event_loop()
    return eb


def _make_zones(count: int = 3, duration: int = 60) -> list[IrrigationZone]:
    zones = []
    for i in range(count):
        zones.append(
            IrrigationZone(
                id=f"zone_{i}",
                name=f"Zone {i}",
                valve=_mock_valve(f"valve_{i}"),
                run_duration=duration,
                enabled=True,
                run_every_n=1,
            )
        )
    return zones


def _make_water_source(
    source_id: str = "ws_default",
    name: str = "Default Source",
    outputs: list | None = None,
    **kwargs,
) -> WaterSource:
    """Create a WaterSource with mock outputs for testing."""
    return WaterSource(
        id=source_id,
        name=name,
        outputs=outputs or [],
        **kwargs,
    )


def _make_controller(
    zones: list[IrrigationZone] | None = None,
    water_sources: list[WaterSource] | None = None,
    **kwargs,
) -> IrrigationController:
    """Create a controller with common mocks. Extra kwargs forwarded to constructor."""
    if zones is None:
        zones = _make_zones()
    defaults = dict(
        id="test_ctrl",
        name="Test Controller",
        topic_prefix="boneio",
        message_bus=_mock_message_bus(),
        event_bus=_mock_event_bus(),
        state_manager=_mock_state_manager(),
        zones=zones,
        schedule=[],
        water_sources=water_sources,
    )
    defaults.update(kwargs)
    with patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock()):
        return IrrigationController(**defaults)


# ── Basic lifecycle ──────────────────────────────────────────────────────────


class TestBasicLifecycle:
    """Initial state, start, stop cycles."""

    async def test_initial_state_is_idle(self):
        ctrl = _make_controller()
        assert ctrl.state == ControllerState.IDLE
        assert ctrl._active_zone_idx is None

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_start_full_cycle_activates_first_zone(self, _utc, _timer):
        ctrl = _make_controller()
        await ctrl.start_full_cycle()

        assert ctrl.state == ControllerState.RUNNING
        assert ctrl._active_zone_idx == 0
        ctrl._zones[0].valve.async_turn_on.assert_awaited_once()

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_shutdown_turns_off_active_zone(self, _utc, _timer):
        ctrl = _make_controller()
        await ctrl.start_full_cycle()
        await ctrl.shutdown()

        assert ctrl.state == ControllerState.IDLE
        assert ctrl._active_zone_idx is None
        ctrl._zones[0].valve.async_turn_off.assert_awaited()

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_start_full_cycle_no_eligible_zones_stays_idle(self, _utc, _timer):
        zones = _make_zones(2)
        for z in zones:
            z.enabled = False
        ctrl = _make_controller(zones=zones)
        await ctrl.start_full_cycle()

        assert ctrl.state == ControllerState.IDLE

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_start_single_zone(self, _utc, _timer):
        ctrl = _make_controller()
        await ctrl.start_single_zone("zone_1")

        assert ctrl.state == ControllerState.RUNNING
        assert ctrl._active_zone_idx == 1
        assert ctrl._single_zone_mode is True
        ctrl._zones[1].valve.async_turn_on.assert_awaited_once()

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_start_single_zone_unknown_does_nothing(self, _utc, _timer):
        ctrl = _make_controller()
        await ctrl.start_single_zone("nonexistent")

        assert ctrl.state == ControllerState.IDLE


# ── Pause / Resume ──────────────────────────────────────────────────────────


class TestPauseResume:

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_pause_stops_zone_and_pauses(self, _utc, _timer):
        ctrl = _make_controller()
        await ctrl.start_full_cycle()
        await ctrl.pause()

        assert ctrl.state == ControllerState.PAUSED
        ctrl._zones[0].valve.async_turn_off.assert_awaited()

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_resume_restarts_zone(self, _utc, _timer):
        ctrl = _make_controller()
        await ctrl.start_full_cycle()
        await ctrl.pause()
        await ctrl.resume()

        assert ctrl.state == ControllerState.RUNNING
        # Valve turned on twice: initial + resume
        assert ctrl._zones[0].valve.async_turn_on.await_count == 2

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_pause_while_idle_does_nothing(self, _utc, _timer):
        ctrl = _make_controller()
        await ctrl.pause()
        assert ctrl.state == ControllerState.IDLE

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_resume_while_idle_does_nothing(self, _utc, _timer):
        ctrl = _make_controller()
        await ctrl.resume()
        assert ctrl.state == ControllerState.IDLE


# ── Auto-advance & zone transitions ─────────────────────────────────────────


class TestAutoAdvance:

    @patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock)
    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_advance_moves_to_next_zone(self, _utc, _timer, _sleep):
        ctrl = _make_controller(auto_advance=True)
        await ctrl.start_full_cycle()
        assert ctrl._active_zone_idx == 0

        await ctrl._advance_to_next_zone(force=False)
        assert ctrl._active_zone_idx == 1
        ctrl._zones[1].valve.async_turn_on.assert_awaited()

    @patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock)
    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_no_auto_advance_shuts_down(self, _utc, _timer, _sleep):
        ctrl = _make_controller(auto_advance=False)
        await ctrl.start_full_cycle()
        await ctrl._advance_to_next_zone(force=False)

        assert ctrl.state == ControllerState.IDLE

    @patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock)
    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_force_advance_overrides_no_auto_advance(self, _utc, _timer, _sleep):
        ctrl = _make_controller(auto_advance=False)
        await ctrl.start_full_cycle()
        await ctrl._advance_to_next_zone(force=True)

        assert ctrl.state == ControllerState.RUNNING
        assert ctrl._active_zone_idx == 1

    @patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock)
    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_advance_past_last_zone_shuts_down(self, _utc, _timer, _sleep):
        ctrl = _make_controller(auto_advance=True)
        await ctrl.start_full_cycle()
        # Advance through all zones
        await ctrl._advance_to_next_zone()  # 0 -> 1
        await ctrl._advance_to_next_zone()  # 1 -> 2
        await ctrl._advance_to_next_zone()  # 2 -> shutdown

        assert ctrl.state == ControllerState.IDLE

    @patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock)
    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_single_zone_mode_shuts_down_after_zone(self, _utc, _timer, _sleep):
        ctrl = _make_controller()
        await ctrl.start_single_zone("zone_1")
        await ctrl._advance_to_next_zone()

        assert ctrl.state == ControllerState.IDLE
        # zone_2 should NOT have been started
        ctrl._zones[2].valve.async_turn_on.assert_not_awaited()


# ── Next valve command ───────────────────────────────────────────────────────


class TestNextValve:

    @patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock)
    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_next_valve_advances(self, _utc, _timer, _sleep):
        ctrl = _make_controller()
        await ctrl.start_full_cycle()
        await ctrl.next_valve()

        assert ctrl._active_zone_idx == 1

    @patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock)
    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_next_valve_from_paused_resumes_then_advances(self, _utc, _timer, _sleep):
        ctrl = _make_controller()
        await ctrl.start_full_cycle()
        await ctrl.pause()
        await ctrl.next_valve()

        # Should have resumed, then advanced
        assert ctrl.state == ControllerState.RUNNING
        assert ctrl._active_zone_idx == 1

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    async def test_next_valve_while_idle_does_nothing(self, _timer):
        ctrl = _make_controller()
        await ctrl.next_valve()
        assert ctrl.state == ControllerState.IDLE


# ── Reverse order ────────────────────────────────────────────────────────────


class TestReverse:

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_reverse_starts_from_last_zone(self, _utc, _timer):
        ctrl = _make_controller(reverse=True)
        await ctrl.start_full_cycle()

        # With reverse, eligible zones come in reverse order → last zone first
        assert ctrl._active_zone_idx == 2

    @patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock)
    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_reverse_advance_goes_backwards(self, _utc, _timer, _sleep):
        ctrl = _make_controller(reverse=True)
        await ctrl.start_full_cycle()
        assert ctrl._active_zone_idx == 2

        await ctrl._advance_to_next_zone()
        assert ctrl._active_zone_idx == 1

        await ctrl._advance_to_next_zone()
        assert ctrl._active_zone_idx == 0


# ── Repeat cycle ─────────────────────────────────────────────────────────────


class TestRepeat:

    @patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock)
    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_repeat_restarts_cycle(self, _utc, _timer, _sleep):
        zones = _make_zones(2)
        ctrl = _make_controller(zones=zones, repeat=1, auto_advance=True)

        await ctrl.start_full_cycle()
        assert ctrl._active_zone_idx == 0

        await ctrl._advance_to_next_zone()  # 0 -> 1
        assert ctrl._active_zone_idx == 1

        await ctrl._advance_to_next_zone()  # 1 -> repeat → restart from 0
        assert ctrl._active_zone_idx == 0
        assert ctrl._current_repeat_index == 1

        await ctrl._advance_to_next_zone()  # 0 -> 1 (2nd cycle)
        assert ctrl._active_zone_idx == 1

        await ctrl._advance_to_next_zone()  # 1 -> done (no more repeats)
        assert ctrl.state == ControllerState.IDLE


# ── Multiplier ───────────────────────────────────────────────────────────────


class TestMultiplier:

    def test_scaled_duration_applies_multiplier(self):
        ctrl = _make_controller(multiplier=2.0)
        assert ctrl._scaled_duration(60) == 120

    def test_scaled_duration_minimum_is_one(self):
        ctrl = _make_controller(multiplier=0.001)
        assert ctrl._scaled_duration(1) >= 1

    def test_multiplier_clamped_to_minimum(self):
        ctrl = _make_controller(multiplier=0.01)
        assert ctrl._multiplier >= 0.1


# ── Standby mode ─────────────────────────────────────────────────────────────


class TestStandby:

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_standby_blocks_full_cycle(self, _utc, _timer):
        ctrl = _make_controller(standby=True)
        await ctrl.start_full_cycle()

        assert ctrl.state == ControllerState.IDLE
        for z in ctrl._zones:
            z.valve.async_turn_on.assert_not_awaited()

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_standby_blocks_single_zone(self, _utc, _timer):
        ctrl = _make_controller(standby=True)
        await ctrl.start_single_zone("zone_0")

        assert ctrl.state == ControllerState.IDLE

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_set_standby_while_running_shuts_down(self, _utc, _timer):
        ctrl = _make_controller()
        await ctrl.start_full_cycle()
        assert ctrl.state == ControllerState.RUNNING

        await ctrl.set_standby(True)
        assert ctrl.state == ControllerState.IDLE
        assert ctrl._standby is True


# ── Skip next run ────────────────────────────────────────────────────────────


class TestSkipNextRun:

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_skip_next_run_blocks_one_cycle(self, _utc, _timer):
        ctrl = _make_controller()
        await ctrl.set_skip_next_run(True)
        await ctrl.start_full_cycle()

        # Should not have started
        assert ctrl.state == ControllerState.IDLE
        for z in ctrl._zones:
            z.valve.async_turn_on.assert_not_awaited()

        # Flag auto-clears
        assert ctrl._skip_next_run is False

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_skip_cleared_after_use(self, _utc, _timer):
        ctrl = _make_controller()
        await ctrl.set_skip_next_run(True)
        await ctrl.start_full_cycle()

        # Next start should work normally
        await ctrl.start_full_cycle()
        assert ctrl.state == ControllerState.RUNNING


# ── Water source activation ──────────────────────────────────────────────────


class TestWaterSource:

    @patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock)
    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_water_source_on_before_zone(self, _utc, _timer, _sleep):
        master = _mock_valve("master")
        ws = _make_water_source(outputs=[master])
        ctrl = _make_controller(water_sources=[ws])
        await ctrl.start_full_cycle()

        master.async_turn_on.assert_awaited_once()
        ctrl._zones[0].valve.async_turn_on.assert_awaited_once()

    @patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock)
    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_water_source_off_on_shutdown(self, _utc, _timer, _sleep):
        master = _mock_valve("master")
        ws = _make_water_source(outputs=[master])
        ctrl = _make_controller(water_sources=[ws])
        await ctrl.start_full_cycle()
        await ctrl.shutdown()

        master.async_turn_off.assert_awaited()

    @patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock)
    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_no_water_source_no_error(self, _utc, _timer, _sleep):
        ctrl = _make_controller(water_sources=None)
        await ctrl.start_full_cycle()
        await ctrl.shutdown()  # Should not raise


# ── Valve open delay ─────────────────────────────────────────────────────────


class TestValveOpenDelay:

    @patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock)
    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_valve_open_delay_on_start_with_source(self, _utc, _timer, mock_sleep):
        master = _mock_valve("master")
        ws = _make_water_source(outputs=[master])
        ctrl = _make_controller(water_sources=[ws], valve_open_delay_s=5)
        await ctrl.start_full_cycle()

        # Sleep called with delay
        mock_sleep.assert_any_await(5)
        master.async_turn_on.assert_awaited_once()

    @patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock)
    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_valve_open_delay_between_zones(self, _utc, _timer, mock_sleep):
        master = _mock_valve("master")
        ws = _make_water_source(outputs=[master])
        ctrl = _make_controller(water_sources=[ws], valve_open_delay_s=3)
        await ctrl.start_full_cycle()
        mock_sleep.reset_mock()

        await ctrl._advance_to_next_zone()
        mock_sleep.assert_any_await(3)

    @patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock)
    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_pump_off_during_valve_open_delay(self, _utc, _timer, mock_sleep):
        master = _mock_valve("master")
        ws = _make_water_source(
            outputs=[master],
            pump_switch_off_during_valve_open_delay=True,
        )
        ctrl = _make_controller(water_sources=[ws], valve_open_delay_s=3)
        await ctrl.start_full_cycle()
        master.reset_mock()
        mock_sleep.reset_mock()

        await ctrl._advance_to_next_zone()

        # Master turned OFF before delay, ON after
        calls = master.async_turn_off.await_args_list + master.async_turn_on.await_args_list
        master.async_turn_off.assert_awaited()
        master.async_turn_on.assert_awaited()
        mock_sleep.assert_any_await(3)

    @patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock)
    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_no_pump_off_during_delay_by_default(self, _utc, _timer, mock_sleep):
        master = _mock_valve("master")
        ws = _make_water_source(
            outputs=[master],
            pump_switch_off_during_valve_open_delay=False,
        )
        ctrl = _make_controller(water_sources=[ws], valve_open_delay_s=3)
        await ctrl.start_full_cycle()
        master.reset_mock()

        await ctrl._advance_to_next_zone()

        # Master should NOT have been turned off between zones
        # It stays on, only the zone valve switches
        # The only master off would be during shutdown
        assert master.async_turn_off.await_count == 0


# ── Valve overlap ────────────────────────────────────────────────────────────


class TestValveOverlap:

    @patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock)
    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_valve_overlap_starts_next_before_stopping_current(self, _utc, _timer, mock_sleep):
        ctrl = _make_controller(valve_overlap_s=2)
        await ctrl.start_full_cycle()
        assert ctrl._active_zone_idx == 0

        await ctrl._advance_to_next_zone()

        # Both zone_0 and zone_1 should have had turn_on called
        ctrl._zones[1].valve.async_turn_on.assert_awaited()
        # Sleep for overlap
        mock_sleep.assert_any_await(2)
        # Then zone_0 turned off
        ctrl._zones[0].valve.async_turn_off.assert_awaited()
        # Active is now zone_1
        assert ctrl._active_zone_idx == 1

    @patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock)
    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_overlap_order_next_on_sleep_current_off(self, _utc, _timer, mock_sleep):
        """Verify exact sequence: next.on → sleep → current.off."""
        ctrl = _make_controller(valve_overlap_s=1)
        await ctrl.start_full_cycle()

        call_order = []
        ctrl._zones[1].valve.async_turn_on = AsyncMock(
            side_effect=lambda **kw: call_order.append("next_on")
        )
        mock_sleep.side_effect = lambda s: call_order.append(f"sleep_{s}")
        ctrl._zones[0].valve.async_turn_off = AsyncMock(
            side_effect=lambda **kw: call_order.append("current_off")
        )

        await ctrl._advance_to_next_zone()

        assert call_order == ["next_on", "sleep_1", "current_off"]


# ── Pump start delays ───────────────────────────────────────────────────────


class TestPumpStartDelays:

    @patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock)
    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_pump_start_valve_delay_pump_first(self, _utc, _timer, mock_sleep):
        """pump_start_valve_delay: pump on → delay → valve on."""
        master = _mock_valve("master")
        ws = _make_water_source(outputs=[master], pump_start_valve_delay_s=3)
        ctrl = _make_controller(water_sources=[ws])

        call_order = []
        master.async_turn_on = AsyncMock(
            side_effect=lambda **kw: call_order.append("pump_on")
        )
        mock_sleep.side_effect = lambda s: call_order.append(f"sleep_{s}")
        ctrl._zones[0].valve.async_turn_on = AsyncMock(
            side_effect=lambda **kw: call_order.append("valve_on")
        )

        await ctrl.start_full_cycle()

        assert call_order == ["pump_on", "sleep_3", "valve_on"]

    @patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock)
    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_pump_start_pump_delay_valve_first(self, _utc, _timer, mock_sleep):
        """pump_start_pump_delay: valve on → delay → pump on."""
        master = _mock_valve("master")
        ws = _make_water_source(outputs=[master], pump_start_pump_delay_s=4)
        ctrl = _make_controller(water_sources=[ws])

        call_order = []
        ctrl._zones[0].valve.async_turn_on = AsyncMock(
            side_effect=lambda **kw: call_order.append("valve_on")
        )
        mock_sleep.side_effect = lambda s: call_order.append(f"sleep_{s}")
        master.async_turn_on = AsyncMock(
            side_effect=lambda **kw: call_order.append("pump_on")
        )

        await ctrl.start_full_cycle()

        assert call_order == ["valve_on", "sleep_4", "pump_on"]


# ── Pump stop delays ────────────────────────────────────────────────────────


class TestPumpStopDelays:

    @patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock)
    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_pump_stop_valve_delay_pump_off_first(self, _utc, _timer, mock_sleep):
        """pump_stop_valve_delay: pump off → delay → (valve already off from _stop_current_zone)."""
        master = _mock_valve("master")
        ws = _make_water_source(outputs=[master], pump_stop_valve_delay_s=2)
        ctrl = _make_controller(water_sources=[ws])
        await ctrl.start_full_cycle()

        master.reset_mock()
        mock_sleep.reset_mock()

        await ctrl.shutdown()

        master.async_turn_off.assert_awaited_once()
        mock_sleep.assert_any_await(2)

    @patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock)
    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_pump_stop_pump_delay_valve_off_first(self, _utc, _timer, mock_sleep):
        """pump_stop_pump_delay: valve off (from _stop_current_zone) → delay → pump off."""
        master = _mock_valve("master")
        ws = _make_water_source(outputs=[master], pump_stop_pump_delay_s=5)
        ctrl = _make_controller(water_sources=[ws])
        await ctrl.start_full_cycle()

        master.reset_mock()
        mock_sleep.reset_mock()

        call_order = []
        mock_sleep.side_effect = lambda s: call_order.append(f"sleep_{s}")
        master.async_turn_off = AsyncMock(
            side_effect=lambda **kw: call_order.append("pump_off")
        )

        await ctrl.shutdown()

        assert "sleep_5" in call_order
        assert "pump_off" in call_order
        # Sleep BEFORE pump off
        assert call_order.index("sleep_5") < call_order.index("pump_off")

    @patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock)
    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_default_pump_stop_no_delay(self, _utc, _timer, mock_sleep):
        """Without delays, pump just turns off immediately."""
        master = _mock_valve("master")
        ws = _make_water_source(outputs=[master])
        ctrl = _make_controller(water_sources=[ws])
        await ctrl.start_full_cycle()
        master.reset_mock()
        mock_sleep.reset_mock()

        await ctrl.shutdown()

        master.async_turn_off.assert_awaited_once()
        mock_sleep.assert_not_awaited()

    @patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock)
    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_pump_stop_sequence_on_advance_single_zone(self, _utc, _timer, mock_sleep):
        """After single zone finishes, pump stop sequence should run."""
        master = _mock_valve("master")
        ws = _make_water_source(outputs=[master], pump_stop_pump_delay_s=3)
        ctrl = _make_controller(water_sources=[ws])
        await ctrl.start_single_zone("zone_0")
        master.reset_mock()
        mock_sleep.reset_mock()

        await ctrl._advance_to_next_zone()

        # In single zone mode, advance → shutdown incl. pump stop
        mock_sleep.assert_any_await(3)
        master.async_turn_off.assert_awaited()
        assert ctrl.state == ControllerState.IDLE


# ── Settings persistence ────────────────────────────────────────────────────


class TestSettingsPersistence:

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    async def test_set_multiplier(self, _timer):
        ctrl = _make_controller()
        await ctrl.set_multiplier(2.5)
        assert ctrl._multiplier == 2.5
        ctrl._state_manager.save_attribute.assert_any_call(
            IRRIGATION, "test_ctrl/multiplier", 2.5
        )

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    async def test_set_repeat(self, _timer):
        ctrl = _make_controller()
        await ctrl.set_repeat(3)
        assert ctrl._repeat == 3

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    async def test_set_auto_advance(self, _timer):
        ctrl = _make_controller()
        await ctrl.set_auto_advance(False)
        assert ctrl._auto_advance is False

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    async def test_set_reverse(self, _timer):
        ctrl = _make_controller()
        await ctrl.set_reverse(True)
        assert ctrl._reverse is True

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    async def test_set_zone_enabled(self, _timer):
        ctrl = _make_controller()
        await ctrl.set_zone_enabled("zone_1", False)
        assert ctrl._zones[1].enabled is False
        ctrl._state_manager.save_attribute.assert_any_call(
            IRRIGATION, "test_ctrl/zone/zone_1/enabled", False
        )

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    async def test_set_schedule_skip(self, _timer):
        ctrl = _make_controller(schedule=[{"time": "06:00", "days": "daily"}])
        await ctrl.set_schedule_skip(0, True)
        assert ctrl._schedule[0]["skip"] is True

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    async def test_set_schedule_skip_out_of_range(self, _timer):
        ctrl = _make_controller(schedule=[{"time": "06:00", "days": "daily"}])
        await ctrl.set_schedule_skip(5, True)  # Should not raise


# ── MQTT command handlers ────────────────────────────────────────────────────


class TestMQTTCommands:

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_handle_main_command_on(self, _utc, _timer):
        ctrl = _make_controller()
        await ctrl.handle_main_command("ON")
        assert ctrl.state == ControllerState.RUNNING

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_handle_main_command_off(self, _utc, _timer):
        ctrl = _make_controller()
        await ctrl.start_full_cycle()
        await ctrl.handle_main_command("OFF")
        assert ctrl.state == ControllerState.IDLE

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_handle_main_command_pause(self, _utc, _timer):
        ctrl = _make_controller()
        await ctrl.start_full_cycle()
        await ctrl.handle_main_command("PAUSE")
        assert ctrl.state == ControllerState.PAUSED

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_handle_main_command_resume(self, _utc, _timer):
        ctrl = _make_controller()
        await ctrl.start_full_cycle()
        await ctrl.handle_main_command("PAUSE")
        await ctrl.handle_main_command("RESUME")
        assert ctrl.state == ControllerState.RUNNING

    @patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock)
    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_handle_main_command_next_valve(self, _utc, _timer, _sleep):
        ctrl = _make_controller()
        await ctrl.start_full_cycle()
        await ctrl.handle_main_command("NEXT_VALVE")
        assert ctrl._active_zone_idx == 1

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_handle_zone_command_on(self, _utc, _timer):
        ctrl = _make_controller()
        await ctrl.handle_zone_command("zone_2", "ON")
        assert ctrl.state == ControllerState.RUNNING
        assert ctrl._active_zone_idx == 2

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_handle_zone_duration_command(self, _utc, _timer):
        ctrl = _make_controller()
        # payload is in minutes (from HA number entity), internally stored as seconds
        await ctrl.handle_zone_duration_command("zone_0", "2")
        assert ctrl._zones[0].run_duration == 120

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    async def test_handle_zone_duration_invalid(self, _timer):
        ctrl = _make_controller()
        await ctrl.handle_zone_duration_command("zone_0", "abc")
        assert ctrl._zones[0].run_duration == 60  # unchanged

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    async def test_handle_zone_duration_negative(self, _timer):
        ctrl = _make_controller()
        await ctrl.handle_zone_duration_command("zone_0", "-10")
        assert ctrl._zones[0].run_duration == 60  # unchanged


# ── Eligible zones / run_every_n ─────────────────────────────────────────────


class TestEligibleZones:

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_all_zones_eligible_first_run(self, _utc, _timer):
        ctrl = _make_controller()
        eligible = ctrl._eligible_zones()
        assert len(eligible) == 3

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_disabled_zone_not_eligible(self, _utc, _timer):
        zones = _make_zones(3)
        zones[1].enabled = False
        ctrl = _make_controller(zones=zones)
        eligible = ctrl._eligible_zones()
        assert len(eligible) == 2
        assert all(z.id != "zone_1" for _, z in eligible)

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_run_every_n_skips_zone(self, _utc, _timer):
        """Zone with run_every_n=3 and skip_count=1 should be skipped (needs 2)."""
        zones = _make_zones(2)
        zones[0].run_every_n = 3

        sm = _mock_state_manager()
        # skip_count=1, needs 2 to be eligible → NOT eligible
        sm.get = MagicMock(
            side_effect=lambda section, key, default: (
                1 if "zone_0/skip_count" in key else default
            )
        )

        ctrl = _make_controller(zones=zones, state_manager=sm)
        eligible = ctrl._eligible_zones()
        eligible_ids = [z.id for _, z in eligible]
        assert "zone_0" not in eligible_ids
        assert "zone_1" in eligible_ids

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_run_every_n_eligible_after_enough_skips(self, _utc, _timer):
        """Zone with run_every_n=2 and skip_count=1 should be eligible."""
        zones = _make_zones(1)
        zones[0].run_every_n = 2

        sm = _mock_state_manager()
        # skip_count=1 >= run_every_n-1=1 → eligible
        sm.get = MagicMock(
            side_effect=lambda section, key, default: (
                1 if "zone_0/skip_count" in key else default
            )
        )

        ctrl = _make_controller(zones=zones, state_manager=sm)
        eligible = ctrl._eligible_zones()
        assert len(eligible) == 1

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_run_every_n_1_always_eligible(self, _utc, _timer):
        """Zone with run_every_n=1 (default) is always eligible."""
        zones = _make_zones(1)
        zones[0].run_every_n = 1
        ctrl = _make_controller(zones=zones)
        eligible = ctrl._eligible_zones()
        assert len(eligible) == 1


# ── Topic generation ─────────────────────────────────────────────────────────


class TestTopics:

    def test_state_topic(self):
        ctrl = _make_controller()
        assert ctrl._state_topic() == "boneio/irrigation/test_ctrl"

    def test_cmd_topic(self):
        ctrl = _make_controller()
        assert ctrl._cmd_topic() == "boneio/cmd/irrigation/test_ctrl/set"

    def test_zone_state_topic(self):
        ctrl = _make_controller()
        assert ctrl._zone_state_topic("zone_0") == "boneio/irrigation/test_ctrl/zone/zone_0"

    def test_setting_topic(self):
        ctrl = _make_controller()
        assert ctrl._setting_state_topic("multiplier") == "boneio/irrigation/test_ctrl/multiplier"


# ── Publish states ───────────────────────────────────────────────────────────


class TestPublishStates:

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    async def test_publish_all_states_sends_controller_state(self, _timer):
        ctrl = _make_controller()
        await ctrl.publish_all_states()

        ctrl._message_bus.send_message.assert_any_call(
            topic="boneio/irrigation/test_ctrl",
            payload={"state": OFF},
            retain=True,
        )

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    async def test_publish_all_states_sends_standby(self, _timer):
        ctrl = _make_controller(standby=True)
        await ctrl.publish_all_states()

        ctrl._message_bus.send_message.assert_any_call(
            topic="boneio/irrigation/test_ctrl/standby",
            payload={"state": ON},
            retain=True,
        )

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_publish_running_state(self, _utc, _timer):
        ctrl = _make_controller()
        await ctrl.start_full_cycle()

        ctrl._message_bus.send_message.assert_any_call(
            topic="boneio/irrigation/test_ctrl",
            payload={"state": ON},
            retain=True,
        )


# ── Valve error handling ────────────────────────────────────────────────────


class TestValveErrors:

    @patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock)
    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_zone_valve_turn_on_error_triggers_shutdown(self, _utc, _timer, _sleep):
        zones = _make_zones(2)
        zones[0].valve.async_turn_on = AsyncMock(side_effect=Exception("relay fault"))
        ctrl = _make_controller(zones=zones)

        await ctrl.start_full_cycle()
        assert ctrl.state == ControllerState.IDLE

    @patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock)
    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_zone_valve_turn_off_error_does_not_crash(self, _utc, _timer, _sleep):
        zones = _make_zones(2)
        zones[0].valve.async_turn_off = AsyncMock(side_effect=Exception("relay fault"))
        ctrl = _make_controller(zones=zones)

        await ctrl.start_full_cycle()
        await ctrl.shutdown()  # Should not raise

    @patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock)
    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_water_source_error_does_not_crash(self, _utc, _timer, _sleep):
        master = _mock_valve("master")
        master.async_turn_on = AsyncMock(side_effect=Exception("pump fault"))
        ws = _make_water_source(outputs=[master])
        ctrl = _make_controller(water_sources=[ws])
        # Should not raise — water source errors are caught
        await ctrl.start_full_cycle()


# ── _next_fire_time helper ───────────────────────────────────────────────────


class TestNextFireTime:

    @patch(f"{MODULE}.utcnow")
    def test_next_fire_time_today_future(self, mock_utc):
        # Monday 2026-04-06 at 05:00 → next 06:00 is today
        mock_utc.return_value = datetime(2026, 4, 6, 5, 0, 0, tzinfo=timezone.utc)
        result = _next_fire_time("06:00", "daily")
        assert result.hour == 6
        assert result.minute == 0
        assert result.day == 6

    @patch(f"{MODULE}.utcnow")
    def test_next_fire_time_today_past(self, mock_utc):
        # Monday 2026-04-06 at 07:00 → next 06:00 is tomorrow
        mock_utc.return_value = datetime(2026, 4, 6, 7, 0, 0, tzinfo=timezone.utc)
        result = _next_fire_time("06:00", "daily")
        assert result.day == 7

    @patch(f"{MODULE}.utcnow")
    def test_next_fire_time_weekdays_only(self, mock_utc):
        # Saturday 2026-04-11 → next weekday 06:00 is Monday 2026-04-13
        mock_utc.return_value = datetime(2026, 4, 11, 7, 0, 0, tzinfo=timezone.utc)
        result = _next_fire_time("06:00", "weekdays")
        assert result.weekday() in {0, 1, 2, 3, 4}  # Mon-Fri
        assert result > mock_utc.return_value

    @patch(f"{MODULE}.utcnow")
    def test_next_fire_time_weekend_only(self, mock_utc):
        # Wednesday 2026-04-08 → next weekend 06:00 is Saturday 2026-04-11
        mock_utc.return_value = datetime(2026, 4, 8, 7, 0, 0, tzinfo=timezone.utc)
        result = _next_fire_time("06:00", "weekend")
        assert result.weekday() in {5, 6}  # Sat-Sun

    @patch(f"{MODULE}.utcnow")
    def test_next_fire_time_specific_day(self, mock_utc):
        # Monday 2026-04-06 → next "wed" is 2026-04-08
        mock_utc.return_value = datetime(2026, 4, 6, 7, 0, 0, tzinfo=timezone.utc)
        result = _next_fire_time("06:00", "wed")
        assert result.weekday() == 2

    @patch(f"{MODULE}.utcnow")
    def test_next_fire_time_invalid_time_defaults(self, mock_utc):
        mock_utc.return_value = datetime(2026, 4, 6, 5, 0, 0, tzinfo=timezone.utc)
        result = _next_fire_time("bad:time", "daily")
        assert result.hour == 6
        assert result.minute == 0


# ── State loading ────────────────────────────────────────────────────────────


class TestStateLoading:

    def test_load_state_restores_multiplier(self):
        sm = _mock_state_manager()
        sm.get = MagicMock(
            side_effect=lambda section, key, default: 3.0 if "multiplier" in key else default
        )
        ctrl = _make_controller(state_manager=sm)
        assert ctrl._multiplier == 3.0

    def test_load_state_restores_standby(self):
        sm = _mock_state_manager()
        sm.get = MagicMock(
            side_effect=lambda section, key, default: True if "standby" in key else default
        )
        ctrl = _make_controller(state_manager=sm)
        assert ctrl._standby is True

    def test_load_state_restores_zone_enabled(self):
        sm = _mock_state_manager()
        sm.get = MagicMock(
            side_effect=lambda section, key, default: (
                False if "zone/zone_1/enabled" in key else default
            )
        )
        zones = _make_zones(2)
        ctrl = _make_controller(zones=zones, state_manager=sm)
        assert ctrl._zones[1].enabled is False


# ── Edge cases ───────────────────────────────────────────────────────────────


class TestEdgeCases:

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_start_cycle_while_running_shuts_down_first(self, _utc, _timer):
        ctrl = _make_controller()
        await ctrl.start_full_cycle()
        assert ctrl.state == ControllerState.RUNNING

        # Starting again should shutdown then restart
        await ctrl.start_full_cycle()
        assert ctrl.state == ControllerState.RUNNING

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_single_zone_while_running_shuts_down_first(self, _utc, _timer):
        ctrl = _make_controller()
        await ctrl.start_full_cycle()
        await ctrl.start_single_zone("zone_2")
        assert ctrl._active_zone_idx == 2
        assert ctrl._single_zone_mode is True

    def test_zero_valve_overlap_and_delay(self):
        ctrl = _make_controller(valve_open_delay_s=0, valve_overlap_s=0)
        assert ctrl._valve_open_delay_s == 0
        assert ctrl._valve_overlap_s == 0

    def test_negative_delays_clamped_to_zero(self):
        """Controller clamps valve_open_delay and valve_overlap; pump delays are on WaterSource."""
        ws = _make_water_source(
            pump_start_pump_delay_s=-1,
            pump_start_valve_delay_s=-2,
            pump_stop_pump_delay_s=-4,
            pump_stop_valve_delay_s=-6,
        )
        ctrl = _make_controller(
            valve_open_delay_s=-5,
            valve_overlap_s=-3,
            water_sources=[ws],
        )
        assert ctrl._valve_open_delay_s == 0
        assert ctrl._valve_overlap_s == 0
        # Pump delays live on WaterSource — negative values accepted as-is by dataclass
        # (no clamping in WaterSource), but controller reads them via src.pump_start_*
        assert ws.pump_start_pump_delay_s == -1
        assert ws.pump_start_valve_delay_s == -2
        assert ws.pump_stop_pump_delay_s == -4
        assert ws.pump_stop_valve_delay_s == -6

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_advance_from_none_active_zone_shuts_down(self, _utc, _timer):
        ctrl = _make_controller()
        ctrl._active_zone_idx = None
        await ctrl._advance_to_next_zone()
        assert ctrl.state == ControllerState.IDLE
