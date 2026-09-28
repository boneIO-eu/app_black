"""Relay timing and position tracking of the time-based covers.

The movement thread runs for real here, with short cover times, and the mock
relays record when they were switched. That checks the two things a unit test
can: how long the relay is held on, and that the reported position matches
that on-time — including a stop between polls and the actuator activation
delay, during which the motor has not started yet.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from boneio.components.cover.time_based import TimeBasedCover
from boneio.components.cover.venetian import VenetianCover
from boneio.const import CLOSING, IDLE, OPENING
from boneio.core.utils import TimePeriod

# Thread wake-up and scheduling jitter on a loaded test machine.
TIMING_SLACK_MS = 40


def _relay(name: str) -> MagicMock:
    """A relay that records the monotonic time of every switch."""
    relay = MagicMock()
    relay.id = name
    relay.switched: list[tuple[str, float]] = []
    relay.turn_on = MagicMock(side_effect=lambda: relay.switched.append(("on", time.monotonic())))
    relay.turn_off = MagicMock(side_effect=lambda: relay.switched.append(("off", time.monotonic())))
    relay.async_send_state = AsyncMock()
    return relay


def _switch_time(relay: MagicMock, kind: str) -> float:
    """Monotonic time of the relay's first ``kind`` ("on"/"off") switch."""
    return next(t for k, t in relay.switched if k == kind)


def _on_time_ms(relay: MagicMock) -> float:
    """How long the relay was held on during its first on/off cycle."""
    on = next(t for kind, t in relay.switched if kind == "on")
    off = next(t for kind, t in relay.switched if kind == "off" and t >= on)
    return (off - on) * 1000


def _common_kwargs() -> dict:
    event_bus = MagicMock()
    event_bus.add_sigterm_listener = MagicMock()
    return {
        "id": "cover_test",
        "name": "Cover test",
        "open_relay": _relay("open"),
        "close_relay": _relay("close"),
        "state_save": MagicMock(),
        "event_bus": event_bus,
        "message_bus": MagicMock(),
        "topic_prefix": "boneio",
        "open_time": TimePeriod(milliseconds=1000),
        "close_time": TimePeriod(milliseconds=1000),
    }


def _time_based(position: float, activation_ms: float = 0, **extra) -> TimeBasedCover:
    return TimeBasedCover(
        restored_state={"position": position},
        actuator_activation_duration=TimePeriod(milliseconds=activation_ms),
        **_common_kwargs(),
        **extra,
    )


def _venetian(position: float, tilt: float, activation_ms: float = 0) -> VenetianCover:
    return VenetianCover(
        tilt_duration=TimePeriod(milliseconds=1000),
        actuator_activation_duration=TimePeriod(milliseconds=activation_ms),
        restored_state={"position": position, "tilt": tilt},
        **_common_kwargs(),
    )


async def _finish(cover) -> None:
    """Wait for the movement thread without blocking the event loop."""
    await asyncio.get_running_loop().run_in_executor(None, cover._movement_thread.join, 5)
    assert not cover._movement_thread.is_alive()
    assert cover.current_operation == IDLE


class TestPositionFollowsRelayOnTime:
    async def test_tilt_step_holds_relay_for_the_travel(self):
        """A 10% step of a 1s tilt: 100ms of relay, not rounded up to the 50ms poll."""
        cover = _venetian(position=50, tilt=50)

        await cover.set_tilt(60)
        await _finish(cover)

        on_ms = _on_time_ms(cover._open_relay)
        assert 100 <= on_ms <= 100 + TIMING_SLACK_MS
        assert cover._tilt_position == pytest.approx(50 + on_ms / 10, abs=0.5)

    async def test_stop_between_polls_is_not_lost(self):
        """Position after a stop matches the time the relay was really on.

        Polling every 50ms used to drop the time from the last poll to the
        relay turn-off — up to 5% of a 1s cover per stop.
        """
        cover = _time_based(position=0)

        await cover.run_cover(current_operation=OPENING)
        await asyncio.sleep(0.33)
        await cover.stop()

        on_ms = _on_time_ms(cover._open_relay)
        assert cover._position == pytest.approx(on_ms / 1000 * 100, abs=1.0)

    async def test_venetian_turns_slats_before_travelling(self):
        """From tilt 0, reaching position 30 takes the full tilt plus 30% of travel."""
        cover = _venetian(position=0, tilt=0)

        await cover.set_cover_position(30)
        await _finish(cover)

        on_ms = _on_time_ms(cover._open_relay)
        assert 1300 <= on_ms <= 1300 + TIMING_SLACK_MS
        assert cover._tilt_position == 100
        assert cover._position == pytest.approx((on_ms - 1000) / 10, abs=0.5)

    async def test_venetian_stop_mid_tilt_keeps_position(self):
        cover = _venetian(position=40, tilt=100)

        await cover.run_cover(current_operation=CLOSING)
        await asyncio.sleep(0.25)
        await cover.stop()

        on_ms = _on_time_ms(cover._close_relay)
        assert cover._tilt_position == pytest.approx(100 - on_ms / 1000 * 100, abs=1.0)
        assert cover._position == 40


class TestActuatorActivation:
    async def test_tilt_step_holds_relay_for_activation_plus_travel(self):
        """A 10% tilt step with 1s tilt and 200ms activation needs ~300ms of relay."""
        cover = _venetian(position=50, tilt=50, activation_ms=200)

        await cover.set_tilt(60)
        await _finish(cover)

        on_ms = _on_time_ms(cover._open_relay)
        assert 300 <= on_ms <= 300 + TIMING_SLACK_MS
        assert cover._tilt_position == pytest.approx(50 + (on_ms - 200) / 10, abs=0.5)
        assert cover._position == 50

    async def test_time_based_position_includes_activation(self):
        cover = _time_based(position=0, activation_ms=150)

        await cover.set_cover_position(20)
        await _finish(cover)

        on_ms = _on_time_ms(cover._open_relay)
        assert 350 <= on_ms <= 350 + TIMING_SLACK_MS
        assert cover._position == pytest.approx((on_ms - 150) / 10, abs=0.5)

    async def test_stop_during_activation_moves_nothing(self):
        """The motor had not started yet, so neither position nor tilt changes."""
        cover = _venetian(position=50, tilt=50, activation_ms=300)

        await cover.run_cover(current_operation=CLOSING)
        await asyncio.sleep(0.1)
        await cover.stop()

        assert cover._close_relay.turn_off.called
        assert cover._position == 50
        assert cover._tilt_position == 50


class TestActivationConfigReload:
    async def test_reload_sets_and_clears_activation(self):
        cover = _time_based(position=0)
        assert cover._actuator_activation_ms == 0

        cover.update_config_times({"actuator_activation_duration": "200ms"})
        assert cover._actuator_activation_ms == 200

        cover.update_config_times({"open_time": TimePeriod(seconds=20)})
        assert cover._actuator_activation_ms == 0
        assert cover._open_time == 20000

    async def test_venetian_reload_keeps_tilt_handling(self):
        cover = _venetian(position=0, tilt=0)

        cover.update_config_times({"actuator_activation_duration": TimePeriod(milliseconds=250), "tilt_duration": "2s"})

        assert cover._actuator_activation_ms == 250
        assert cover._tilt_duration == 2000


class TestEndstopOverrun:
    async def test_full_close_runs_past_zero_by_overrun(self):
        """50% of a 1s cover plus the default 10% overrun: 600ms of relay."""
        cover = _time_based(position=50)

        await cover.close()
        await _finish(cover)

        on_ms = _on_time_ms(cover._close_relay)
        assert 600 <= on_ms <= 600 + TIMING_SLACK_MS
        assert cover._position == 0

    async def test_position_target_at_the_end_also_overruns(self):
        cover = _time_based(position=50, endstop_overrun=20)

        await cover.set_cover_position(100)
        await _finish(cover)

        on_ms = _on_time_ms(cover._open_relay)
        assert 700 <= on_ms <= 700 + TIMING_SLACK_MS
        assert cover._position == 100

    async def test_overrun_zero_stops_at_computed_time(self):
        cover = _time_based(position=50, endstop_overrun=0)

        await cover.close()
        await _finish(cover)

        on_ms = _on_time_ms(cover._close_relay)
        assert 500 <= on_ms <= 500 + TIMING_SLACK_MS

    async def test_closed_cover_is_not_driven_again(self):
        cover = _time_based(position=0)

        await cover.close()

        cover._close_relay.turn_on.assert_not_called()
        assert cover._movement_thread is None

    async def test_venetian_overrun_after_slats_and_travel(self):
        """Tilt 100→0 (1s) + 30% of travel (300ms) + 10% overrun (100ms)."""
        cover = _venetian(position=30, tilt=100)

        await cover.close()
        await _finish(cover)

        on_ms = _on_time_ms(cover._close_relay)
        assert 1400 <= on_ms <= 1400 + TIMING_SLACK_MS
        assert cover._position == 0
        assert cover._tilt_position == 0

    async def test_reload_sets_and_resets_overrun(self):
        cover = _time_based(position=50)

        cover.update_config_times({"endstop_overrun": 0})
        assert cover._endstop_overrun == 0

        cover.update_config_times({})
        assert cover._endstop_overrun == 10


class TestVenetianCloseAtZero:
    async def test_close_at_zero_with_open_slats_shuts_them(self):
        """Down at 0% with slats at 50%: close turns them shut, no overrun."""
        cover = _venetian(position=0, tilt=50)

        await cover.close()
        await _finish(cover)

        on_ms = _on_time_ms(cover._close_relay)
        assert 500 <= on_ms <= 500 + TIMING_SLACK_MS
        assert cover._tilt_position == pytest.approx(50 - on_ms / 10, abs=0.5)
        assert cover._position == 0

    async def test_close_with_shut_slats_does_nothing(self):
        cover = _venetian(position=0, tilt=0)

        await cover.close()

        cover._close_relay.turn_on.assert_not_called()
        assert cover._movement_thread is None


class TestDirectionChangeWait:
    async def test_reversal_waits_before_the_other_relay(self):
        cover = _time_based(position=50)

        await cover.run_cover(current_operation=OPENING)
        await asyncio.sleep(0.1)
        await cover.run_cover(current_operation=CLOSING)
        await asyncio.sleep(0.6)
        await cover.stop()

        gap_ms = (_switch_time(cover._close_relay, "on") - _switch_time(cover._open_relay, "off")) * 1000
        assert 500 <= gap_ms <= 500 + TIMING_SLACK_MS

    async def test_same_direction_does_not_wait(self):
        cover = _time_based(position=50)

        await cover.run_cover(current_operation=OPENING)
        await asyncio.sleep(0.1)
        await cover.stop()
        await cover.run_cover(current_operation=OPENING)
        await asyncio.sleep(0.05)
        await cover.stop()

        on_times = [t for kind, t in cover._open_relay.switched if kind == "on"]
        off_time = _switch_time(cover._open_relay, "off")
        assert len(on_times) == 2
        assert (on_times[1] - off_time) * 1000 < TIMING_SLACK_MS

    async def test_stop_during_the_wait_never_energises_the_relay(self):
        cover = _time_based(position=50)

        await cover.run_cover(current_operation=OPENING)
        await asyncio.sleep(0.1)
        await cover.run_cover(current_operation=CLOSING)
        position = cover._position
        await asyncio.sleep(0.2)
        await cover.stop()

        cover._close_relay.turn_on.assert_not_called()
        assert cover._position == position
        assert cover.current_operation == IDLE

    async def test_zero_wait_reverses_at_once(self):
        cover = _time_based(position=50, direction_change_wait_time=TimePeriod(milliseconds=0))

        await cover.run_cover(current_operation=OPENING)
        await asyncio.sleep(0.1)
        await cover.run_cover(current_operation=CLOSING)
        await asyncio.sleep(0.05)
        await cover.stop()

        gap_ms = (_switch_time(cover._close_relay, "on") - _switch_time(cover._open_relay, "off")) * 1000
        assert gap_ms < TIMING_SLACK_MS

    async def test_reload_sets_and_resets_wait(self):
        cover = _time_based(position=50)

        cover.update_config_times({"direction_change_wait_time": "1s"})
        assert cover._direction_change_wait_ms == 1000

        cover.update_config_times({})
        assert cover._direction_change_wait_ms == 500
