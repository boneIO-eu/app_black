"""Comprehensive tests for the IrrigationController state machine."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from boneio.components.irrigation.controller import (
    ControllerState,
    IrrigationController,
    IrrigationZone,
    _next_fire_time,
)
from boneio.components.irrigation.water_source import WaterSource
from boneio.const import IRRIGATION, OFF, ON

# ── Helpers ──────────────────────────────────────────────────────────────────

FIXED_NOW = datetime(2026, 4, 7, 10, 0, 0, tzinfo=UTC)
MODULE = "boneio.components.irrigation.controller"


def _mock_valve(name: str = "valve") -> MagicMock:
    v = MagicMock(name=name)
    v.async_turn_on = AsyncMock(return_value=True)
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


# ── Pause timeout ────────────────────────────────────────────────────────────


class TestPauseTimeout:
    """Verify auto-shutdown when paused too long."""

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_pause_timeout_shuts_down_controller(self, _utc, _timer):
        """Controller should auto-shutdown after pause timeout expires."""
        ctrl = _make_controller(pause_timeout_s=60)
        await ctrl.start_full_cycle()
        await ctrl.pause()

        assert ctrl.state == ControllerState.PAUSED
        # Simulate timeout callback firing
        await ctrl._pause_timeout_callback(FIXED_NOW)

        assert ctrl.state == ControllerState.IDLE
        assert ctrl._active_zone_idx is None

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_resume_cancels_pause_timeout(self, _utc, _timer):
        """Resuming should cancel the pause timeout timer."""
        ctrl = _make_controller(pause_timeout_s=60)
        await ctrl.start_full_cycle()
        await ctrl.pause()

        assert ctrl._pause_timer_cancel is not None
        await ctrl.resume()

        assert ctrl._pause_timer_cancel is None
        assert ctrl.state == ControllerState.RUNNING

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_pause_timeout_disabled_with_zero(self, _utc, _timer):
        """Setting pause_timeout_s=0 should disable auto-shutdown."""
        ctrl = _make_controller(pause_timeout_s=0)
        await ctrl.start_full_cycle()
        await ctrl.pause()

        # No pause timer should be armed
        assert ctrl._pause_timer_cancel is None
        assert ctrl.state == ControllerState.PAUSED

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_pause_timeout_callback_ignored_if_not_paused(self, _utc, _timer):
        """If state changed before timeout fires, callback should be a no-op."""
        ctrl = _make_controller(pause_timeout_s=60)
        await ctrl.start_full_cycle()
        assert ctrl.state == ControllerState.RUNNING

        # Simulate stale callback firing while running (not paused)
        await ctrl._pause_timeout_callback(FIXED_NOW)

        # Should remain running — callback was ignored
        assert ctrl.state == ControllerState.RUNNING

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_shutdown_cancels_pause_timer(self, _utc, _timer):
        """Shutdown should cancel any active pause timer."""
        ctrl = _make_controller(pause_timeout_s=60)
        await ctrl.start_full_cycle()
        await ctrl.pause()

        assert ctrl._pause_timer_cancel is not None
        await ctrl.shutdown()

        assert ctrl._pause_timer_cancel is None


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
        ctrl._zones[1].valve.async_turn_on = AsyncMock(side_effect=lambda **kw: (call_order.append("next_on"), True)[-1])
        mock_sleep.side_effect = lambda s: call_order.append(f"sleep_{s}")
        ctrl._zones[0].valve.async_turn_off = AsyncMock(side_effect=lambda **kw: call_order.append("current_off"))

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
        master.async_turn_on = AsyncMock(side_effect=lambda **kw: (call_order.append("pump_on"), True)[-1])
        mock_sleep.side_effect = lambda s: call_order.append(f"sleep_{s}")
        ctrl._zones[0].valve.async_turn_on = AsyncMock(side_effect=lambda **kw: (call_order.append("valve_on"), True)[-1])

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
        ctrl._zones[0].valve.async_turn_on = AsyncMock(side_effect=lambda **kw: (call_order.append("valve_on"), True)[-1])
        mock_sleep.side_effect = lambda s: call_order.append(f"sleep_{s}")
        master.async_turn_on = AsyncMock(side_effect=lambda **kw: (call_order.append("pump_on"), True)[-1])

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
        master.async_turn_off = AsyncMock(side_effect=lambda **kw: call_order.append("pump_off"))

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


# ── Mid-cycle water source change (regression) ──────────────────────────────


class TestMidCycleWaterSourceChange:
    """Regression: changing water source via HA select during an active cycle
    must still deactivate the OLD source's outputs on shutdown.

    Bug scenario (before fix):
      1. Cycle starts with source A → A outputs ON
      2. User changes HA select to source B → _active_water_source_idx changes
      3. Cycle ends → shutdown() calls _deactivate_source() which used
         self.active_water_source (now source B) → B outputs turned OFF (never ON)
      4. Source A outputs stay ON forever → interlock blocks source B next cycle
    """

    @patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock)
    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_shutdown_deactivates_old_source_after_select_change(self, _utc, _timer, _sleep):
        """After mid-cycle HA select change, shutdown must turn off the source that was activated."""
        old_output = _mock_valve("old_valve")
        new_output = _mock_valve("new_valve")

        ws_old = _make_water_source(source_id="deszczowa", outputs=[old_output])
        ws_new = _make_water_source(source_id="wodociagowa", outputs=[new_output])

        ctrl = _make_controller(water_sources=[ws_old, ws_new])
        assert ctrl.active_water_source is ws_old

        # Start cycle with "deszczowa"
        await ctrl.start_full_cycle()
        old_output.async_turn_on.assert_awaited_once()
        new_output.async_turn_on.assert_not_awaited()

        # User changes HA select mid-cycle
        await ctrl.set_water_source("wodociagowa")
        assert ctrl.active_water_source is ws_new  # select updated
        assert ctrl._running_water_source is ws_old  # but running source unchanged

        # Shutdown → must turn off OLD source, not new
        old_output.reset_mock()
        new_output.reset_mock()
        await ctrl.shutdown()

        old_output.async_turn_off.assert_awaited()  # OLD source deactivated
        new_output.async_turn_off.assert_not_awaited()  # NEW source was never ON

    @patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock)
    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_running_water_source_reset_after_shutdown(self, _utc, _timer, _sleep):
        """After shutdown, _running_water_source must be None."""
        output = _mock_valve("valve")
        ws = _make_water_source(source_id="src", outputs=[output])
        ctrl = _make_controller(water_sources=[ws])

        await ctrl.start_full_cycle()
        assert ctrl._running_water_source is ws

        await ctrl.shutdown()
        assert ctrl._running_water_source is None

    @patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock)
    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_next_cycle_uses_new_source_after_select_change(self, _utc, _timer, _sleep):
        """After shutdown + source change, next cycle uses the new source."""
        old_output = _mock_valve("old_valve")
        new_output = _mock_valve("new_valve")

        ws_old = _make_water_source(source_id="deszczowa", outputs=[old_output])
        ws_new = _make_water_source(source_id="wodociagowa", outputs=[new_output])

        ctrl = _make_controller(water_sources=[ws_old, ws_new])

        # First cycle with old source
        await ctrl.start_full_cycle()
        await ctrl.shutdown()

        # Change source
        await ctrl.set_water_source("wodociagowa")
        old_output.reset_mock()
        new_output.reset_mock()

        # Second cycle should use new source
        await ctrl.start_full_cycle()
        new_output.async_turn_on.assert_awaited_once()
        old_output.async_turn_on.assert_not_awaited()
        assert ctrl._running_water_source is ws_new

    @patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock)
    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_mid_cycle_change_logs_deferred_message(self, _utc, _timer, _sleep):
        """Changing water source while running should log that it's deferred."""
        old_output = _mock_valve("old_valve")
        new_output = _mock_valve("new_valve")

        ws_old = _make_water_source(source_id="deszczowa", outputs=[old_output])
        ws_new = _make_water_source(source_id="wodociagowa", outputs=[new_output])

        ctrl = _make_controller(water_sources=[ws_old, ws_new])
        await ctrl.start_full_cycle()
        assert ctrl.state == ControllerState.RUNNING

        # Source change persisted but running source stays
        await ctrl.set_water_source("wodociagowa")
        assert ctrl._active_water_source_idx == 1
        assert ctrl._running_water_source is ws_old


# ── Settings persistence ────────────────────────────────────────────────────


class TestSettingsPersistence:
    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    async def test_set_multiplier(self, _timer):
        ctrl = _make_controller()
        await ctrl.set_multiplier(2.5)
        assert ctrl._multiplier == 2.5
        ctrl._state_manager.save_attribute.assert_any_call(IRRIGATION, "test_ctrl/multiplier", 2.5)

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
        ctrl._state_manager.save_attribute.assert_any_call(IRRIGATION, "test_ctrl/zone/zone_1/enabled", False)

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
        sm.get = MagicMock(side_effect=lambda section, key, default: (1 if "zone_0/skip_count" in key else default))

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
        sm.get = MagicMock(side_effect=lambda section, key, default: (1 if "zone_0/skip_count" in key else default))

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


# ── Multi-cycle skip counter synchronization ─────────────────────────────────


def _dict_state_manager() -> MagicMock:
    """State manager backed by a real dict so saves persist across calls."""
    store: dict[str, Any] = {}
    sm = MagicMock()
    sm.get = MagicMock(side_effect=lambda section, key, default: store.get(key, default))
    sm.save_attribute = MagicMock(side_effect=lambda section, key, value: store.__setitem__(key, value))
    sm._store = store  # expose for assertions
    return sm


class TestMultiCycleSkipCounterSync:
    """Regression tests for run_every_n across multiple full cycles.

    These test the exact scenario from production: multiple zones with
    the same run_every_n in one controller, running daily schedule over
    multiple days. Before the fix, _eligible_zones() had side effects
    that desynchronized counters.

    Flow per scheduled cycle:
      1. ``_eligible_zones()`` reads current skip_count to decide eligibility
      2. ``_apply_skip_counters()`` then modifies counters for the NEXT cycle
    """

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_9_zones_run_every_4_stays_synchronized(self, _utc, _timer):
        """9 zones: 1 always + 8 with run_every_n=4. After N cycles all
        run_every_n=4 zones must have identical skip_count."""
        zones = _make_zones(9, duration=10)
        zones[0].run_every_n = 1  # warzywnik — always
        for z in zones[1:]:
            z.run_every_n = 4  # trawniki

        sm = _dict_state_manager()
        ctrl = _make_controller(zones=zones, state_manager=sm, auto_advance=True)

        for cycle_num in range(1, 9):
            # Replicate the production flow: eligible FIRST, then apply
            eligible = ctrl._eligible_zones()
            ctrl._apply_skip_counters()

            if cycle_num in (1, 2, 3, 5, 6, 7):
                # Not eligible — only zone_0 (always) eligible
                assert len(eligible) == 1, f"Cycle {cycle_num}: expected 1 eligible, got {len(eligible)}"
                assert eligible[0][1].id == "zone_0"
            elif cycle_num in (4, 8):
                # Eligible — all 9 zones should run
                assert len(eligible) == 9, f"Cycle {cycle_num}: expected 9 eligible, got {len(eligible)}"

            # Verify all run_every_n=4 zones have the SAME skip_count
            skip_counts = {}
            for z in zones[1:]:
                key = f"test_ctrl/zone/{z.id}/skip_count"
                skip_counts[z.id] = sm._store.get(key, 0)
            values = list(skip_counts.values())
            assert len(set(values)) == 1, (
                f"Cycle {cycle_num}: skip_counts desynchronized: {skip_counts}"
            )

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_apply_skip_counters_increments_correctly(self, _utc, _timer):
        """Verify counter progression with eligible-first, apply-after flow.

        run_every_n=4: eligible when skip_count >= 3.
        Flow: check eligible → apply → check eligible → apply → ...
        """
        zones = _make_zones(2, duration=10)
        zones[0].run_every_n = 4
        zones[1].run_every_n = 1

        sm = _dict_state_manager()
        ctrl = _make_controller(zones=zones, state_manager=sm)

        # (expected_eligible, expected_skip_after_apply)
        expectations = [
            (False, 1),  # cycle 1: skip=0 < 3 → not eligible; apply: 0→1
            (False, 2),  # cycle 2: skip=1 < 3 → not eligible; apply: 1→2
            (False, 3),  # cycle 3: skip=2 < 3 → not eligible; apply: 2→3
            (True, 0),   # cycle 4: skip=3 >= 3 → eligible; apply: reset→0
            (False, 1),  # cycle 5: skip=0 < 3 → not eligible; apply: 0→1
            (False, 2),  # cycle 6: skip=1 < 3 → not eligible; apply: 1→2
            (False, 3),  # cycle 7: skip=2 < 3 → not eligible; apply: 2→3
            (True, 0),   # cycle 8: skip=3 >= 3 → eligible; apply: reset→0
        ]
        for cycle_num, (expect_eligible, expect_skip) in enumerate(expectations, 1):
            eligible = ctrl._eligible_zones()
            ctrl._apply_skip_counters()
            zone0_eligible = any(z.id == "zone_0" for _, z in eligible)
            key = "test_ctrl/zone/zone_0/skip_count"
            actual_skip = sm._store.get(key, 0)
            assert zone0_eligible == expect_eligible, (
                f"Cycle {cycle_num}: expected eligible={expect_eligible}, got {zone0_eligible}"
            )
            assert actual_skip == expect_skip, (
                f"Cycle {cycle_num}: expected skip_count={expect_skip}, got {actual_skip}"
            )

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_eligible_zones_is_pure_no_side_effects(self, _utc, _timer):
        """_eligible_zones() must NOT modify state — calling it multiple
        times must return the same result."""
        zones = _make_zones(3, duration=10)
        for z in zones:
            z.run_every_n = 3

        sm = _dict_state_manager()
        ctrl = _make_controller(zones=zones, state_manager=sm)

        # Set skip_count=1 for all zones
        for z in zones:
            sm._store[f"test_ctrl/zone/{z.id}/skip_count"] = 1

        result1 = ctrl._eligible_zones()
        result2 = ctrl._eligible_zones()
        result3 = ctrl._eligible_zones()

        # All calls should return the same result
        assert len(result1) == len(result2) == len(result3)
        # State should be unchanged
        for z in zones:
            assert sm._store[f"test_ctrl/zone/{z.id}/skip_count"] == 1

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_mixed_run_every_n_zones_independent(self, _utc, _timer):
        """Zones with different run_every_n values track independently."""
        zones = _make_zones(3, duration=10)
        zones[0].run_every_n = 2  # runs every 2nd cycle
        zones[1].run_every_n = 3  # runs every 3rd cycle
        zones[2].run_every_n = 1  # runs every cycle

        sm = _dict_state_manager()
        ctrl = _make_controller(zones=zones, state_manager=sm)

        # Cycle 1: zone_0 skip=0<1→skip, zone_1 skip=0<2→skip
        eligible = ctrl._eligible_zones()
        ctrl._apply_skip_counters()
        eligible_ids = {z.id for _, z in eligible}
        assert eligible_ids == {"zone_2"}

        # Cycle 2: zone_0 skip=1>=1→eligible, zone_1 skip=1<2→skip
        eligible = ctrl._eligible_zones()
        ctrl._apply_skip_counters()
        eligible_ids = {z.id for _, z in eligible}
        assert eligible_ids == {"zone_0", "zone_2"}

        # Cycle 3: zone_0 skip=0<1→skip, zone_1 skip=2>=2→eligible
        eligible = ctrl._eligible_zones()
        ctrl._apply_skip_counters()
        eligible_ids = {z.id for _, z in eligible}
        assert eligible_ids == {"zone_1", "zone_2"}

        # Cycle 4: zone_0 skip=1>=1→eligible, zone_1 skip=0<2→skip
        eligible = ctrl._eligible_zones()
        ctrl._apply_skip_counters()
        eligible_ids = {z.id for _, z in eligible}
        assert eligible_ids == {"zone_0", "zone_2"}

        # Cycle 5: zone_0 skip=0<1→skip, zone_1 skip=1<2→skip
        eligible = ctrl._eligible_zones()
        ctrl._apply_skip_counters()
        eligible_ids = {z.id for _, z in eligible}
        assert eligible_ids == {"zone_2"}

        # Cycle 6: zone_0 skip=1>=1→eligible, zone_1 skip=2>=2→eligible
        eligible = ctrl._eligible_zones()
        ctrl._apply_skip_counters()
        eligible_ids = {z.id for _, z in eligible}
        assert eligible_ids == {"zone_0", "zone_1", "zone_2"}


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


# ── Interlock fault handling ─────────────────────────────────────────────────


class TestInterlockFault:
    """Tests for interlock blocking during irrigation start."""

    @patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock)
    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_source_interlock_shuts_down(self, _utc, _timer, _sleep):
        """When water source output is blocked by interlock, controller shuts down."""
        master = _mock_valve("master")
        master.async_turn_on = AsyncMock(return_value=False)  # Blocked
        ws = _make_water_source(outputs=[master])
        ctrl = _make_controller(water_sources=[ws])

        await ctrl.start_full_cycle()

        assert ctrl.state == ControllerState.IDLE
        # Legacy fault topic published
        ctrl._message_bus.send_message.assert_any_call(
            topic="boneio/irrigation/test_ctrl/fault",
            payload={
                "fault": "interlock_blocked",
                "controller": "test_ctrl",
                "zone": "zone_0",
                "source": "ws_default",
                "message": "Irrigation 'Test Controller' stopped: output blocked by interlock (zone: zone_0)",
            },
            retain=False,
        )
        # HA event entity also published
        event_calls = [
            c for c in ctrl._message_bus.send_message.call_args_list
            if c.kwargs.get("topic", c.args[0] if c.args else "") == "boneio/irrigation/test_ctrl/event"
               or (isinstance(c.kwargs, dict) and c.kwargs.get("topic") == "boneio/irrigation/test_ctrl/event")
        ]
        # Use keyword args matching
        found_event = False
        for c in ctrl._message_bus.send_message.call_args_list:
            topic = c.kwargs.get("topic") if c.kwargs else None
            if topic == "boneio/irrigation/test_ctrl/event":
                payload = json.loads(c.kwargs["payload"])
                assert payload["event_type"] == "interlock_fault"
                assert payload["zone"] == "zone_0"
                assert payload["source"] == "ws_default"
                assert c.kwargs["retain"] is False
                found_event = True
                break
        assert found_event, "Expected interlock_fault event on event topic"

    @patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock)
    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_zone_valve_interlock_deactivates_source(self, _utc, _timer, _sleep):
        """When zone valve is blocked, source outputs are deactivated first."""
        master = _mock_valve("master")
        ws = _make_water_source(outputs=[master])
        zones = _make_zones(2)
        zones[0].valve.async_turn_on = AsyncMock(return_value=False)  # Blocked

        ctrl = _make_controller(zones=zones, water_sources=[ws])

        await ctrl.start_full_cycle()

        assert ctrl.state == ControllerState.IDLE
        # Source was activated then deactivated after valve block
        master.async_turn_on.assert_awaited_once()
        master.async_turn_off.assert_awaited()

    @patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock)
    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_zone_valve_interlock_no_source(self, _utc, _timer, _sleep):
        """When zone valve is blocked with no water source, just shuts down."""
        zones = _make_zones(1)
        zones[0].valve.async_turn_on = AsyncMock(return_value=False)
        ctrl = _make_controller(zones=zones, water_sources=None)

        await ctrl.start_full_cycle()

        assert ctrl.state == ControllerState.IDLE
        ctrl._message_bus.send_message.assert_any_call(
            topic="boneio/irrigation/test_ctrl/fault",
            payload={
                "fault": "interlock_blocked",
                "controller": "test_ctrl",
                "zone": "zone_0",
                "source": "",
                "message": "Irrigation 'Test Controller' stopped: output blocked by interlock (zone: zone_0)",
            },
            retain=False,
        )

    @patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock)
    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_pump_delay_valve_interlock_rolls_back_valve(self, _utc, _timer, _sleep):
        """With pump_start_pump_delay, if source interlock fires after valve ON, valve is turned off."""
        master = _mock_valve("master")
        master.async_turn_on = AsyncMock(return_value=False)  # Source blocked
        ws = _make_water_source(outputs=[master], pump_start_pump_delay_s=2)
        zones = _make_zones(1)
        ctrl = _make_controller(zones=zones, water_sources=[ws])

        await ctrl.start_full_cycle()

        assert ctrl.state == ControllerState.IDLE
        # Valve was turned on (first step), then turned off after source block
        zones[0].valve.async_turn_on.assert_awaited_once()
        zones[0].valve.async_turn_off.assert_awaited()


# ── _next_fire_time helper ───────────────────────────────────────────────────


class TestNextFireTime:
    """Tests for _next_fire_time.

    _next_fire_time interprets time_str as local time, builds candidate
    in local tz, and returns UTC.  We mock _local_now to provide a
    deterministic local time (UTC+2 simulating CEST).
    """

    CEST = timezone(timedelta(hours=2))

    @patch(f"{MODULE}._local_now")
    def test_next_fire_time_today_future(self, mock_local):
        # Monday 2026-04-06 at 05:00 local (CEST) → next 06:00 local is today
        mock_local.return_value = datetime(2026, 4, 6, 5, 0, 0, tzinfo=self.CEST)
        result = _next_fire_time("06:00", "daily")
        # 06:00 CEST = 04:00 UTC
        assert result.hour == 4
        assert result.minute == 0
        assert result.day == 6

    @patch(f"{MODULE}._local_now")
    def test_next_fire_time_today_past(self, mock_local):
        # Monday 2026-04-06 at 07:00 local (CEST) → next 06:00 local is tomorrow
        mock_local.return_value = datetime(2026, 4, 6, 7, 0, 0, tzinfo=self.CEST)
        result = _next_fire_time("06:00", "daily")
        # Tomorrow 06:00 CEST = 04:00 UTC on 2026-04-07
        assert result.day == 7
        assert result.hour == 4

    @patch(f"{MODULE}._local_now")
    def test_next_fire_time_weekdays_only(self, mock_local):
        # Saturday 2026-04-11 → next weekday 06:00 is Monday 2026-04-13
        mock_local.return_value = datetime(2026, 4, 11, 7, 0, 0, tzinfo=self.CEST)
        result = _next_fire_time("06:00", "weekdays")
        assert result.weekday() in {0, 1, 2, 3, 4}  # Mon-Fri
        assert result > mock_local.return_value.astimezone(UTC)

    @patch(f"{MODULE}._local_now")
    def test_next_fire_time_weekend_only(self, mock_local):
        # Wednesday 2026-04-08 → next weekend 06:00 is Saturday 2026-04-11
        mock_local.return_value = datetime(2026, 4, 8, 7, 0, 0, tzinfo=self.CEST)
        result = _next_fire_time("06:00", "weekend")
        # Result is UTC — convert to local to check weekday
        result_local = result.astimezone(self.CEST)
        assert result_local.weekday() in {5, 6}  # Sat-Sun

    @patch(f"{MODULE}._local_now")
    def test_next_fire_time_specific_day(self, mock_local):
        # Monday 2026-04-06 → next "wed" is 2026-04-08
        mock_local.return_value = datetime(2026, 4, 6, 7, 0, 0, tzinfo=self.CEST)
        result = _next_fire_time("06:00", "wed")
        result_local = result.astimezone(self.CEST)
        assert result_local.weekday() == 2

    @patch(f"{MODULE}._local_now")
    def test_next_fire_time_invalid_time_defaults(self, mock_local):
        mock_local.return_value = datetime(2026, 4, 6, 5, 0, 0, tzinfo=self.CEST)
        result = _next_fire_time("bad:time", "daily")
        # Defaults to 06:00 local = 04:00 UTC
        assert result.hour == 4
        assert result.minute == 0


# ── State loading ────────────────────────────────────────────────────────────


class TestStateLoading:
    def test_load_state_restores_multiplier(self):
        sm = _mock_state_manager()
        sm.get = MagicMock(side_effect=lambda section, key, default: 3.0 if "multiplier" in key else default)
        ctrl = _make_controller(state_manager=sm)
        assert ctrl._multiplier == 3.0

    def test_load_state_restores_standby(self):
        sm = _mock_state_manager()
        sm.get = MagicMock(side_effect=lambda section, key, default: True if "standby" in key else default)
        ctrl = _make_controller(state_manager=sm)
        assert ctrl._standby is True

    def test_load_state_restores_zone_enabled(self):
        sm = _mock_state_manager()
        sm.get = MagicMock(
            side_effect=lambda section, key, default: (False if "zone/zone_1/enabled" in key else default)
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


# ── Event entity publishing ──────────────────────────────────────────────────────


def _find_event(ctrl, event_type: str) -> dict | None:
    """Find a published event of given type from the message bus calls."""
    for c in ctrl._message_bus.send_message.call_args_list:
        topic = c.kwargs.get("topic")
        if topic == f"boneio/irrigation/{ctrl.id}/event":
            payload = json.loads(c.kwargs["payload"])
            if payload.get("event_type") == event_type:
                return payload
    return None


class TestEventPublishing:
    """Tests for HA event entity notifications."""

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_standby_blocked_event_on_full_cycle(self, _utc, _timer):
        """Starting full cycle in standby mode should fire standby_blocked event."""
        ctrl = _make_controller(standby=True)
        await ctrl.start_full_cycle()

        event = _find_event(ctrl, "standby_blocked")
        assert event is not None, "Expected standby_blocked event"
        assert event["controller"] == "test_ctrl"
        assert "standby" in event["message"].lower()

    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_standby_blocked_event_on_single_zone(self, _utc, _timer):
        """Starting single zone in standby mode should fire standby_blocked event with zone."""
        ctrl = _make_controller(standby=True)
        await ctrl.start_single_zone("zone_1")

        event = _find_event(ctrl, "standby_blocked")
        assert event is not None, "Expected standby_blocked event"
        assert event["zone"] == "zone_1"

    @patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock)
    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_cycle_complete_event(self, _utc, _timer, _sleep):
        """Advancing past last zone should fire cycle_complete event."""
        zones = _make_zones(2)
        ctrl = _make_controller(zones=zones, auto_advance=True)
        await ctrl.start_full_cycle()

        await ctrl._advance_to_next_zone()  # 0 -> 1
        # No event yet — still running
        assert _find_event(ctrl, "cycle_complete") is None

        await ctrl._advance_to_next_zone()  # 1 -> done
        event = _find_event(ctrl, "cycle_complete")
        assert event is not None, "Expected cycle_complete event"
        assert event["controller"] == "test_ctrl"

    @patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock)
    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_interlock_fault_event_payload(self, _utc, _timer, _sleep):
        """Interlock fault should fire event with zone and source details."""
        master = _mock_valve("master")
        master.async_turn_on = AsyncMock(return_value=False)
        ws = _make_water_source(source_id="rainwater", outputs=[master])
        ctrl = _make_controller(water_sources=[ws])

        await ctrl.start_full_cycle()

        event = _find_event(ctrl, "interlock_fault")
        assert event is not None, "Expected interlock_fault event"
        assert event["zone"] == "zone_0"
        assert event["source"] == "rainwater"
        assert "interlock" in event["message"].lower()

    @patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock)
    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_event_not_retained(self, _utc, _timer, _sleep):
        """Events should be published with retain=False."""
        ctrl = _make_controller(standby=True)
        await ctrl.start_full_cycle()

        for c in ctrl._message_bus.send_message.call_args_list:
            topic = c.kwargs.get("topic")
            if topic == f"boneio/irrigation/{ctrl.id}/event":
                assert c.kwargs["retain"] is False, "Event should not be retained"

    @patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock)
    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_no_cycle_complete_on_manual_shutdown(self, _utc, _timer, _sleep):
        """Manual shutdown should NOT fire cycle_complete event."""
        ctrl = _make_controller()
        await ctrl.start_full_cycle()
        await ctrl.shutdown()

        assert _find_event(ctrl, "cycle_complete") is None


# ── Schedule survival after shutdown ──────────────────────────────────────────


class TestScheduleSurvival:
    """Regression tests: shutdown() must NOT kill schedule tasks.

    Previously, shutdown() called stop_schedules() which cancelled the
    schedule asyncio.Tasks.  When a scheduled cycle completed and called
    shutdown() internally (via _advance_to_next_zone → shutdown), the
    schedule task was killed permanently — the next day's schedule would
    never fire.
    """

    @patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock)
    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_shutdown_preserves_schedule_tasks(self, _utc, _timer, _sleep):
        """shutdown() should NOT cancel schedule tasks."""
        ctrl = _make_controller(schedule=[{"time": "08:00", "days": "daily"}])
        # Simulate schedule tasks being present
        mock_task = MagicMock()
        ctrl._schedule_tasks = [mock_task]

        await ctrl.start_full_cycle()
        await ctrl.shutdown()

        # Schedule tasks must survive
        assert len(ctrl._schedule_tasks) == 1
        mock_task.cancel.assert_not_called()

    @patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock)
    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_full_stop_cancels_schedule_tasks(self, _utc, _timer, _sleep):
        """full_stop() SHOULD cancel schedule tasks (used for teardown)."""
        ctrl = _make_controller(schedule=[{"time": "08:00", "days": "daily"}])
        mock_task = MagicMock()
        ctrl._schedule_tasks = [mock_task]

        await ctrl.full_stop()

        # Schedule tasks must be cancelled and cleared
        mock_task.cancel.assert_called_once()
        assert len(ctrl._schedule_tasks) == 0

    @patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock)
    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_cycle_complete_preserves_schedule(self, _utc, _timer, _sleep):
        """Full cycle completion via _advance_to_next_zone should NOT kill schedule."""
        zones = _make_zones(2)
        ctrl = _make_controller(zones=zones, auto_advance=True)
        mock_task = MagicMock()
        ctrl._schedule_tasks = [mock_task]

        await ctrl.start_full_cycle()
        await ctrl._advance_to_next_zone()  # 0 -> 1
        await ctrl._advance_to_next_zone()  # 1 -> shutdown (cycle complete)

        assert ctrl.state == ControllerState.IDLE
        # Schedule task must survive
        assert len(ctrl._schedule_tasks) == 1
        mock_task.cancel.assert_not_called()

    @patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock)
    @patch(f"{MODULE}.async_track_point_in_time", return_value=MagicMock())
    @patch(f"{MODULE}.utcnow", return_value=FIXED_NOW)
    async def test_start_full_cycle_while_running_preserves_schedule(self, _utc, _timer, _sleep):
        """Starting new cycle while running should shutdown previous but keep schedule."""
        ctrl = _make_controller()
        mock_task = MagicMock()
        ctrl._schedule_tasks = [mock_task]

        await ctrl.start_full_cycle()
        assert ctrl.state == ControllerState.RUNNING

        # Start again — should shutdown previous cycle
        await ctrl.start_full_cycle()
        assert ctrl.state == ControllerState.RUNNING

        # Schedule must survive both cycles
        assert len(ctrl._schedule_tasks) == 1
        mock_task.cancel.assert_not_called()
