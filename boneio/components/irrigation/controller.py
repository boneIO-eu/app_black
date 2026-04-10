from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from boneio.const import IRRIGATION, NEXT_VALVE, OFF, ON, PAUSE, RESUME
from boneio.core.events import async_track_point_in_time, utcnow

_LOGGER = logging.getLogger(__name__)

_DAYS_MAP = {
    "daily": {0, 1, 2, 3, 4, 5, 6},
    "weekdays": {0, 1, 2, 3, 4},
    "weekend": {5, 6},
    "mon": {0},
    "tue": {1},
    "wed": {2},
    "thu": {3},
    "fri": {4},
    "sat": {5},
    "sun": {6},
}


class ControllerState(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"


@dataclass
class IrrigationZone:
    id: str
    name: str
    valve: Any
    run_duration: int
    enabled: bool = True
    run_every_days: int = 1


class IrrigationController:
    def __init__(
        self,
        id: str,
        name: str,
        topic_prefix: str,
        message_bus: Any,
        event_bus: Any,
        state_manager: Any,
        zones: list[IrrigationZone],
        schedule: list[dict[str, Any]] | None = None,
        master_valve: Any | None = None,
        valve_open_delay_s: int = 0,
        valve_overlap_s: int = 0,
        standby: bool = False,
        pump_switch_off_during_valve_open_delay: bool = False,
        pump_start_pump_delay_s: int = 0,
        pump_start_valve_delay_s: int = 0,
        pump_stop_pump_delay_s: int = 0,
        pump_stop_valve_delay_s: int = 0,
        multiplier: float = 1.0,
        repeat: int = 0,
        auto_advance: bool = True,
        reverse: bool = False,
    ) -> None:
        self.id = id
        self.name = name
        self._topic_prefix = topic_prefix
        self._message_bus = message_bus
        self._event_bus = event_bus
        self._state_manager = state_manager

        self._zones = zones
        self._schedule = schedule or []
        self._master_valve = master_valve
        self._valve_open_delay_s = max(0, int(valve_open_delay_s))
        self._valve_overlap_s = max(0, int(valve_overlap_s))
        self._standby = standby
        self._pump_switch_off_during_valve_open_delay = pump_switch_off_during_valve_open_delay
        self._pump_start_pump_delay_s = max(0, int(pump_start_pump_delay_s))
        self._pump_start_valve_delay_s = max(0, int(pump_start_valve_delay_s))
        self._pump_stop_pump_delay_s = max(0, int(pump_stop_pump_delay_s))
        self._pump_stop_valve_delay_s = max(0, int(pump_stop_valve_delay_s))

        self._state = ControllerState.IDLE
        self._auto_advance = auto_advance
        self._reverse = reverse
        self._multiplier = max(0.1, float(multiplier))
        self._repeat = max(0, int(repeat))
        self._skip_next_run = False

        self._zone_timer_cancel = None
        self._run_start_utc: datetime | None = None
        self._active_zone_idx: int | None = None
        self._active_zone_remaining_s: int | None = None
        self._current_repeat_index = 0
        self._single_zone_mode = False
        self._single_zone_target_idx: int | None = None

        self._schedule_tasks: list[asyncio.Task] = []

        self._load_state()

    @property
    def zones(self) -> list[IrrigationZone]:
        return self._zones

    @property
    def state(self) -> ControllerState:
        return self._state

    def _state_topic(self) -> str:
        return f"{self._topic_prefix}/{IRRIGATION}/{self.id}"

    def _cmd_topic(self) -> str:
        return f"{self._topic_prefix}/cmd/{IRRIGATION}/{self.id}/set"

    def _zone_state_topic(self, zone_id: str) -> str:
        return f"{self._topic_prefix}/{IRRIGATION}/{self.id}/zone/{zone_id}"

    def _zone_cmd_topic(self, zone_id: str) -> str:
        return f"{self._topic_prefix}/cmd/{IRRIGATION}/{self.id}/zone/{zone_id}/set"

    def _zone_duration_topic(self, zone_id: str) -> str:
        return f"{self._topic_prefix}/{IRRIGATION}/{self.id}/zone/{zone_id}/duration"

    def _zone_duration_cmd_topic(self, zone_id: str) -> str:
        return f"{self._topic_prefix}/cmd/{IRRIGATION}/{self.id}/zone/{zone_id}/duration/set"

    def _setting_state_topic(self, setting: str) -> str:
        return f"{self._topic_prefix}/{IRRIGATION}/{self.id}/{setting}"

    def _setting_cmd_topic(self, setting: str) -> str:
        return f"{self._topic_prefix}/cmd/{IRRIGATION}/{self.id}/{setting}/set"

    def _schedule_skip_topic(self, idx: int) -> str:
        return f"{self._topic_prefix}/{IRRIGATION}/{self.id}/schedule/{idx}/skip"

    def _schedule_skip_cmd_topic(self, idx: int) -> str:
        return f"{self._topic_prefix}/cmd/{IRRIGATION}/{self.id}/schedule/{idx}/skip/set"

    def _state_key(self, suffix: str) -> str:
        return f"{self.id}/{suffix}"

    def _save(self, suffix: str, value: Any) -> None:
        self._state_manager.save_attribute(IRRIGATION, self._state_key(suffix), value)

    def _get(self, suffix: str, default: Any) -> Any:
        return self._state_manager.get(IRRIGATION, self._state_key(suffix), default)

    def _load_state(self) -> None:
        self._multiplier = float(self._get("multiplier", self._multiplier))
        self._repeat = int(self._get("repeat", self._repeat))
        self._auto_advance = bool(self._get("auto_advance", self._auto_advance))
        self._reverse = bool(self._get("reverse", self._reverse))
        self._skip_next_run = bool(self._get("skip_next_run", False))
        self._standby = bool(self._get("standby", self._standby))

        for idx, zone in enumerate(self._zones):
            zone.enabled = bool(self._get(f"zone/{zone.id}/enabled", zone.enabled))
            zone.run_duration = int(self._get(f"zone/{zone.id}/duration", zone.run_duration))
            if zone.run_every_days <= 0:
                zone.run_every_days = 1
            zone.run_every_days = int(self._get(f"zone/{zone.id}/run_every_days", zone.run_every_days))
            if zone.run_every_days <= 0:
                zone.run_every_days = 1
            self._save(f"zone/{zone.id}/order", idx)

        for idx, sched in enumerate(self._schedule):
            skip = bool(self._get(f"schedule/{idx}/skip", False))
            sched["skip"] = skip

    def _publish(self, topic: str, payload: Any, retain: bool = True) -> None:
        self._message_bus.send_message(topic=topic, payload=payload, retain=retain)

    def _ordered_zones(self) -> list[tuple[int, IrrigationZone]]:
        indexed = list(enumerate(self._zones))
        if self._reverse:
            indexed.reverse()
        return indexed

    def _eligible_zones(self) -> list[tuple[int, IrrigationZone]]:
        now = utcnow()
        eligible: list[tuple[int, IrrigationZone]] = []
        for idx, zone in self._ordered_zones():
            if not zone.enabled:
                continue
            key = f"zone/{zone.id}/last_run_utc"
            last_run = self._get(key, None)
            if not last_run:
                eligible.append((idx, zone))
                continue
            try:
                dt = datetime.fromisoformat(str(last_run))
            except ValueError:
                eligible.append((idx, zone))
                continue
            delta = now - dt
            if delta >= timedelta(days=max(1, zone.run_every_days)):
                eligible.append((idx, zone))
        return eligible

    async def publish_all_states(self) -> None:
        controller_state = ON if self._state in (ControllerState.RUNNING, ControllerState.PAUSED) else OFF
        self._publish(self._state_topic(), {"state": controller_state})
        self._publish(
            self._setting_state_topic("auto_advance"),
            {"state": ON if self._auto_advance else OFF},
        )
        self._publish(
            self._setting_state_topic("reverse"),
            {"state": ON if self._reverse else OFF},
        )
        self._publish(
            self._setting_state_topic("standby"),
            {"state": ON if self._standby else OFF},
        )
        self._publish(self._setting_state_topic("multiplier"), {"value": self._multiplier})
        self._publish(self._setting_state_topic("repeat"), {"value": self._repeat})

        for idx, zone in enumerate(self._zones):
            active = ON if self._active_zone_idx == idx and self._state == ControllerState.RUNNING else OFF
            self._publish(self._zone_state_topic(zone.id), {"state": active})
            self._publish(
                self._setting_state_topic(f"zone/{zone.id}/enabled"),
                {"state": ON if zone.enabled else OFF},
            )
            self._publish(self._zone_duration_topic(zone.id), {"value": zone.run_duration})

        for idx, sched in enumerate(self._schedule):
            self._publish(
                self._schedule_skip_topic(idx),
                {"state": ON if bool(sched.get("skip", False)) else OFF},
            )

    async def shutdown(self) -> None:
        self.stop_schedules()
        await self._stop_current_zone()
        await self._handle_pump_stop_sequence()
        self._state = ControllerState.IDLE
        self._active_zone_idx = None
        self._active_zone_remaining_s = None
        self._single_zone_mode = False
        self._single_zone_target_idx = None
        await self.publish_all_states()

    async def pause(self) -> None:
        if self._state != ControllerState.RUNNING or self._active_zone_idx is None:
            return

        remaining = self._remaining_seconds()
        self._active_zone_remaining_s = max(1, remaining)
        self._cancel_zone_timer()
        await self._stop_current_zone()
        self._state = ControllerState.PAUSED
        await self.publish_all_states()

    async def resume(self) -> None:
        if self._state != ControllerState.PAUSED or self._active_zone_idx is None:
            return
        remaining = self._active_zone_remaining_s or self._current_zone_duration_seconds()
        await self._start_zone(self._active_zone_idx, override_duration=remaining)

    async def next_valve(self) -> None:
        if self._state not in (ControllerState.RUNNING, ControllerState.PAUSED):
            return

        if self._state == ControllerState.PAUSED:
            await self.resume()

        if self._active_zone_idx is None:
            return

        await self._advance_to_next_zone(force=True)

    async def start_full_cycle(self) -> None:
        if self._standby:
            _LOGGER.info("Irrigation %s is in standby mode, not starting", self.id)
            return

        if self._state in (ControllerState.RUNNING, ControllerState.PAUSED):
            await self.shutdown()

        self._single_zone_mode = False
        self._single_zone_target_idx = None
        self._current_repeat_index = 0

        if self._skip_next_run:
            self._skip_next_run = False
            self._save("skip_next_run", False)
            await self.publish_all_states()
            _LOGGER.info("Irrigation %s skipped one full cycle", self.id)
            return

        await self._start_cycle_from_eligible()

    async def start_single_zone(self, zone_id: str) -> None:
        if self._standby:
            _LOGGER.info("Irrigation %s is in standby mode, not starting zone", self.id)
            return

        match_idx = None
        for idx, zone in enumerate(self._zones):
            if zone.id == zone_id:
                match_idx = idx
                break
        if match_idx is None:
            _LOGGER.warning("Irrigation %s unknown zone '%s'", self.id, zone_id)
            return

        if self._state in (ControllerState.RUNNING, ControllerState.PAUSED):
            await self.shutdown()

        self._single_zone_mode = True
        self._single_zone_target_idx = match_idx
        await self._start_zone(match_idx)

    async def _start_cycle_from_eligible(self) -> None:
        eligible = self._eligible_zones()
        if not eligible:
            _LOGGER.info("Irrigation %s: no eligible zones in this cycle", self.id)
            self._state = ControllerState.IDLE
            self._active_zone_idx = None
            await self.publish_all_states()
            return

        first_idx = eligible[0][0]
        await self._start_zone(first_idx)

    async def _advance_to_next_zone(self, force: bool = False) -> None:
        if self._active_zone_idx is None:
            await self.shutdown()
            return

        finished_idx = self._active_zone_idx
        finished_zone = self._zones[finished_idx]
        self._save(f"zone/{finished_zone.id}/last_run_utc", utcnow().isoformat())

        if self._single_zone_mode:
            await self._stop_current_zone()
            await self._handle_pump_stop_sequence()
            await self.shutdown()
            return

        if not self._auto_advance and not force:
            await self._stop_current_zone()
            await self._handle_pump_stop_sequence()
            await self.shutdown()
            return

        eligible = [idx for idx, _ in self._eligible_zones()]
        ordered = self._ordered_zone_indices()
        try:
            current_pos = ordered.index(finished_idx)
        except ValueError:
            current_pos = -1

        tail = ordered[current_pos + 1 :] + ordered[: current_pos + 1]
        if force:
            remaining = [idx for idx in tail if idx != finished_idx and self._zones[idx].enabled]
        else:
            remaining = [idx for idx in tail if idx in eligible and idx != finished_idx]

        if remaining:
            next_idx = remaining[0]
            # Handle valve overlap: start next before stopping current
            if self._valve_overlap_s > 0:
                next_zone = self._zones[next_idx]
                try:
                    await next_zone.valve.async_turn_on()
                except Exception as err:
                    _LOGGER.error("Failed to turn on next zone %s: %s", next_zone.id, err)
                await asyncio.sleep(self._valve_overlap_s)
                await self._stop_current_zone()
                self._active_zone_idx = next_idx
                duration = self._scaled_duration(next_zone.run_duration)
                self._active_zone_remaining_s = max(1, int(duration))
                self._run_start_utc = utcnow()
                self._arm_zone_timer(self._active_zone_remaining_s)
                await self.publish_all_states()
                return

            await self._stop_current_zone()

            # Handle valve_open_delay between zones
            if self._valve_open_delay_s > 0:
                if self._pump_switch_off_during_valve_open_delay and self._master_valve is not None:
                    await self._set_master(False)
                await asyncio.sleep(self._valve_open_delay_s)
                if self._pump_switch_off_during_valve_open_delay and self._master_valve is not None:
                    await self._set_master(True)

            await self._start_zone(next_idx)
            return

        if self._current_repeat_index < self._repeat:
            self._current_repeat_index += 1
            await self._start_cycle_from_eligible()
            return

        await self.shutdown()

    def _ordered_zone_indices(self) -> list[int]:
        idxs = list(range(len(self._zones)))
        if self._reverse:
            idxs.reverse()
        return idxs

    async def _start_zone(self, idx: int, override_duration: int | None = None) -> None:
        if idx < 0 or idx >= len(self._zones):
            return

        zone = self._zones[idx]
        duration = override_duration if override_duration is not None else self._scaled_duration(zone.run_duration)
        duration = max(1, int(duration))

        self._active_zone_idx = idx
        self._active_zone_remaining_s = duration
        self._state = ControllerState.RUNNING

        if self._master_valve is not None:
            if self._pump_start_valve_delay_s > 0:
                # Pump first, then valve after delay
                await self._set_master(True)
                await asyncio.sleep(self._pump_start_valve_delay_s)
            elif self._pump_start_pump_delay_s > 0:
                # Valve first, then pump after delay
                try:
                    await zone.valve.async_turn_on()
                except Exception as err:
                    _LOGGER.error("Failed to turn on zone %s: %s", zone.id, err)
                    await self.shutdown()
                    return
                await asyncio.sleep(self._pump_start_pump_delay_s)
                await self._set_master(True)
                self._run_start_utc = utcnow()
                self._arm_zone_timer(duration)
                await self.publish_all_states()
                return
            else:
                await self._set_master(True)
                if self._valve_open_delay_s > 0:
                    await asyncio.sleep(self._valve_open_delay_s)

        try:
            await zone.valve.async_turn_on()
        except Exception as err:
            _LOGGER.error("Failed to turn on zone %s: %s", zone.id, err)
            await self.shutdown()
            return
        self._run_start_utc = utcnow()
        self._arm_zone_timer(duration)
        await self.publish_all_states()

    async def _stop_current_zone(self) -> None:
        self._cancel_zone_timer()
        if self._active_zone_idx is None:
            return
        zone = self._zones[self._active_zone_idx]
        try:
            await zone.valve.async_turn_off()
        except Exception as err:
            _LOGGER.error("Failed to turn off zone %s: %s", zone.id, err)

    async def _set_master(self, state: bool) -> None:
        if self._master_valve is None:
            return
        try:
            if state:
                await self._master_valve.async_turn_on()
            else:
                await self._master_valve.async_turn_off()
        except Exception as err:
            _LOGGER.error("Failed to switch master valve for %s: %s", self.id, err)

    async def _handle_pump_stop_sequence(self) -> None:
        \"\"\"Handle pump stop timing according to configured pump stop delays.\"\"\"
        if self._master_valve is None:
            return
        if self._pump_stop_valve_delay_s > 0:
            # Pump off first, then valve after delay
            await self._set_master(False)
            await asyncio.sleep(self._pump_stop_valve_delay_s)
        elif self._pump_stop_pump_delay_s > 0:
            # Valve already off from _stop_current_zone, pump off after delay
            await asyncio.sleep(self._pump_stop_pump_delay_s)
            await self._set_master(False)
        else:
            await self._set_master(False)

    def _scaled_duration(self, seconds: int) -> int:
        return int(max(1, round(seconds * self._multiplier)))

    def _current_zone_duration_seconds(self) -> int:
        if self._active_zone_idx is None:
            return 1
        zone = self._zones[self._active_zone_idx]
        return self._scaled_duration(zone.run_duration)

    def _remaining_seconds(self) -> int:
        if self._run_start_utc is None:
            return self._current_zone_duration_seconds()
        elapsed = (utcnow() - self._run_start_utc).total_seconds()
        return max(1, self._current_zone_duration_seconds() - int(elapsed))

    def _cancel_zone_timer(self) -> None:
        if self._zone_timer_cancel is not None:
            self._zone_timer_cancel()
            self._zone_timer_cancel = None

    def _arm_zone_timer(self, seconds: int) -> None:
        self._cancel_zone_timer()
        point = utcnow() + timedelta(seconds=max(1, int(seconds)))
        self._zone_timer_cancel = async_track_point_in_time(
            loop=self._event_bus.loop,
            job=self._zone_timer_callback,
            point_in_time=point,
        )

    async def _zone_timer_callback(self, _timestamp: datetime) -> None:
        await self._advance_to_next_zone(force=False)

    async def handle_main_command(self, payload: str) -> None:
        cmd = payload.strip()
        upper = cmd.upper()

        if upper == ON:
            await self.start_full_cycle()
        elif upper == OFF:
            await self.shutdown()
        elif upper == PAUSE:
            await self.pause()
        elif upper == RESUME:
            await self.resume()
        elif upper == NEXT_VALVE:
            await self.next_valve()

    async def handle_zone_command(self, zone_id: str, payload: str) -> None:
        upper = payload.strip().upper()
        if upper == ON:
            await self.start_single_zone(zone_id)
        elif upper == OFF:
            await self.shutdown()

    async def handle_zone_duration_command(self, zone_id: str, payload: str) -> None:
        try:
            duration = int(float(payload))
        except (TypeError, ValueError):
            return
        if duration <= 0:
            return

        for zone in self._zones:
            if zone.id == zone_id:
                zone.run_duration = duration
                self._save(f"zone/{zone.id}/duration", duration)
                break
        await self.publish_all_states()

    async def set_auto_advance(self, value: bool) -> None:
        self._auto_advance = bool(value)
        self._save("auto_advance", self._auto_advance)
        await self.publish_all_states()

    async def set_reverse(self, value: bool) -> None:
        self._reverse = bool(value)
        self._save("reverse", self._reverse)
        await self.publish_all_states()

    async def set_standby(self, value: bool) -> None:
        self._standby = bool(value)
        self._save("standby", self._standby)
        if self._standby and self._state in (ControllerState.RUNNING, ControllerState.PAUSED):
            await self.shutdown()
        await self.publish_all_states()

    async def set_multiplier(self, value: float) -> None:
        self._multiplier = max(0.1, float(value))
        self._save("multiplier", self._multiplier)
        await self.publish_all_states()

    async def set_repeat(self, value: int) -> None:
        self._repeat = max(0, int(value))
        self._save("repeat", self._repeat)
        await self.publish_all_states()

    async def set_zone_enabled(self, zone_id: str, value: bool) -> None:
        for zone in self._zones:
            if zone.id == zone_id:
                zone.enabled = bool(value)
                self._save(f"zone/{zone.id}/enabled", zone.enabled)
                break
        await self.publish_all_states()

    async def set_skip_next_run(self, value: bool) -> None:
        self._skip_next_run = bool(value)
        self._save("skip_next_run", self._skip_next_run)
        await self.publish_all_states()

    async def set_schedule_skip(self, schedule_idx: int, value: bool) -> None:
        if schedule_idx < 0 or schedule_idx >= len(self._schedule):
            return
        self._schedule[schedule_idx]["skip"] = bool(value)
        self._save(f"schedule/{schedule_idx}/skip", bool(value))
        await self.publish_all_states()

    def start_schedules(self) -> None:
        self.stop_schedules()
        for idx, schedule in enumerate(self._schedule):
            task = asyncio.create_task(self._run_schedule_loop(idx, schedule))
            self._schedule_tasks.append(task)

    def stop_schedules(self) -> None:
        for task in self._schedule_tasks:
            task.cancel()
        self._schedule_tasks = []

    async def _run_schedule_loop(self, schedule_idx: int, schedule: dict[str, Any]) -> None:
        time_str = schedule.get("time", "06:00")
        days = str(schedule.get("days", "daily")).strip().lower()
        while True:
            next_run = _next_fire_time(time_str, days)
            wait_s = max(1.0, (next_run - utcnow()).total_seconds())
            await asyncio.sleep(wait_s)

            if bool(schedule.get("skip", False)):
                schedule["skip"] = False
                self._save(f"schedule/{schedule_idx}/skip", False)
                await self.publish_all_states()
                continue

            await self.start_full_cycle()


def _next_fire_time(time_str: str, days: str) -> datetime:
    now = utcnow()
    try:
        hh, mm = time_str.split(":", 1)
        target_h = int(hh)
        target_m = int(mm)
    except Exception:
        target_h, target_m = 6, 0

    allowed_days = _DAYS_MAP.get(days, _DAYS_MAP["daily"])

    for plus_days in range(0, 8):
        candidate = (now + timedelta(days=plus_days)).replace(
            hour=target_h,
            minute=target_m,
            second=0,
            microsecond=0,
        )
        if candidate.weekday() in allowed_days and candidate > now:
            return candidate

    return (now + timedelta(days=1)).replace(
        hour=target_h,
        minute=target_m,
        second=0,
        microsecond=0,
    )
