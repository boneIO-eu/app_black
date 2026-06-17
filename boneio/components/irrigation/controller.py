from __future__ import annotations

import asyncio
import datetime as dt
import logging
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum, StrEnum
from typing import Any

from boneio.components.irrigation.water_source import WaterSource
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


class ControllerState(StrEnum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"


@dataclass
class IrrigationZone:
    """Represents a single irrigation zone.

    Attributes:
        id: Unique zone identifier.
        name: Display name.
        valve: Output controlling the zone valve.
        run_duration: How long to run this zone (seconds).
        enabled: Whether the zone is active.
        run_every_n: Run this zone every Nth scheduled cycle. 1 = every time (default).
    """

    id: str
    name: str
    valve: Any
    run_duration: int
    enabled: bool = True
    run_every_n: int = 1


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
        water_sources: list[WaterSource] | None = None,
        valve_open_delay_s: int = 0,
        valve_overlap_s: int = 0,
        standby: bool = False,
        multiplier: float = 1.0,
        repeat: int = 0,
        auto_advance: bool = True,
        reverse: bool = False,
        pause_timeout_s: int = 1800,
        area_id: str | None = None,
    ) -> None:
        """Initialize irrigation controller.

        Args:
            id: Unique controller identifier.
            name: Human-readable name.
            topic_prefix: MQTT topic prefix.
            message_bus: MQTT message bus for publishing.
            event_bus: Event bus for timers.
            state_manager: Persistent state storage.
            zones: List of irrigation zones.
            schedule: Optional list of schedule entries.
            water_sources: List of water sources (valves/pumps to activate).
            valve_open_delay_s: Delay between source activation and zone valve open.
            valve_overlap_s: Overlap between zone transitions.
            standby: Whether controller starts in standby mode.
            multiplier: Duration multiplier.
            repeat: Number of cycle repeats.
            auto_advance: Automatically advance to next zone.
            reverse: Run zones in reverse order.
            pause_timeout_s: Auto-shutdown after this many seconds in PAUSED state.
                Default 1800 (30 minutes). Set 0 to disable.
        """
        self.id = id
        self.name = name
        self.area_id = area_id
        self._topic_prefix = topic_prefix
        self._message_bus = message_bus
        self._event_bus = event_bus
        self._state_manager = state_manager

        self._zones = zones
        self._schedule = schedule or []
        self._water_sources = water_sources or []
        self._active_water_source_idx: int = 0
        self._valve_open_delay_s = max(0, valve_open_delay_s)
        self._valve_overlap_s = max(0, valve_overlap_s)
        self._standby = standby

        self._state = ControllerState.IDLE
        self._auto_advance = auto_advance
        self._reverse = reverse
        self._multiplier = max(0.1, multiplier)
        self._repeat = max(0, repeat)
        self._skip_next_run = False

        self._zone_timer_cancel = None
        self._pause_timer_cancel = None
        self._pause_timeout_s = max(0, pause_timeout_s)
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
    def water_sources(self) -> list[WaterSource]:
        """Return list of configured water sources."""
        return self._water_sources

    @property
    def active_water_source(self) -> WaterSource | None:
        """Return the currently selected water source."""
        if not self._water_sources:
            return None
        idx = min(self._active_water_source_idx, len(self._water_sources) - 1)
        return self._water_sources[idx]

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

    def _event_topic(self) -> str:
        """MQTT topic for HA event entity notifications."""
        return f"{self._topic_prefix}/{IRRIGATION}/{self.id}/event"

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
        # Restore active water source
        saved_source_id = self._get("active_water_source", None)
        if saved_source_id and self._water_sources:
            for i, ws in enumerate(self._water_sources):
                if ws.id == saved_source_id:
                    self._active_water_source_idx = i
                    break

        for idx, zone in enumerate(self._zones):
            zone.enabled = bool(self._get(f"zone/{zone.id}/enabled", zone.enabled))
            zone.run_duration = int(self._get(f"zone/{zone.id}/duration", zone.run_duration))
            if zone.run_every_n <= 0:
                zone.run_every_n = 1
            zone.run_every_n = int(self._get(f"zone/{zone.id}/run_every_n", zone.run_every_n))
            if zone.run_every_n <= 0:
                zone.run_every_n = 1
            self._save(f"zone/{zone.id}/order", idx)

        for idx, sched in enumerate(self._schedule):
            skip = bool(self._get(f"schedule/{idx}/skip", False))
            sched["skip"] = skip

    def _publish(self, topic: str, payload: Any, retain: bool = True) -> None:
        _LOGGER.debug("Irrigation MQTT publish: topic='%s' payload=%s retain=%s", topic, payload, retain)
        self._message_bus.send_message(topic=topic, payload=payload, retain=retain)

    def _publish_event(self, event_type: str, **attributes: Any) -> None:
        """Publish an event to the HA event entity topic.

        The payload follows the HA MQTT event entity format:
        ``{"event_type": "...", ...extra attributes}``.

        Events are NOT retained — they are instantaneous notifications.

        Args:
            event_type: One of the registered event types
                (interlock_fault, cycle_complete, standby_blocked).
            **attributes: Additional key-value pairs included in the event payload.
        """
        import json

        payload = {"event_type": event_type, **attributes}
        self._publish(self._event_topic(), json.dumps(payload), retain=False)

    def _ordered_zones(self) -> list[tuple[int, IrrigationZone]]:
        indexed = list(enumerate(self._zones))
        if self._reverse:
            indexed.reverse()
        return indexed

    def _eligible_zones(self) -> list[tuple[int, IrrigationZone]]:
        """Determine which zones are eligible to run in this cycle.

        This is a **pure** function — it does NOT modify skip counters.
        Use :meth:`_apply_skip_counters` once at the start of a scheduled
        cycle to advance counters.

        Uses a counter-based system: each zone has a skip counter that
        increments every scheduled cycle. When the counter reaches
        run_every_n - 1, the zone is eligible and the counter resets.
        """
        eligible: list[tuple[int, IrrigationZone]] = []
        for idx, zone in self._ordered_zones():
            if not zone.enabled:
                continue
            if zone.run_every_n <= 1:
                eligible.append((idx, zone))
                continue
            counter_key = f"zone/{zone.id}/skip_count"
            skip_count = int(self._get(counter_key, 0))
            if skip_count >= zone.run_every_n - 1:
                eligible.append((idx, zone))
        return eligible

    def _apply_skip_counters(self) -> None:
        """Advance skip counters for all zones at the start of a scheduled cycle.

        For each enabled zone with ``run_every_n > 1``:
        - If the zone IS eligible (skip_count >= run_every_n - 1),
          reset counter to 0 (zone will run this cycle).
        - If the zone is NOT eligible, increment the counter.

        Must be called **exactly once** per scheduled cycle, before
        ``_eligible_zones()`` is used to build the run list.
        """
        for _idx, zone in self._ordered_zones():
            if not zone.enabled or zone.run_every_n <= 1:
                continue
            counter_key = f"zone/{zone.id}/skip_count"
            skip_count = int(self._get(counter_key, 0))
            if skip_count >= zone.run_every_n - 1:
                # Zone is eligible — reset counter
                self._save(counter_key, 0)
                _LOGGER.debug(
                    "Irrigation %s: zone %s counter reset (was %d, eligible)",
                    self.id,
                    zone.id,
                    skip_count,
                )
            else:
                skip_count += 1
                self._save(counter_key, skip_count)
                _LOGGER.debug(
                    "Irrigation %s: zone %s counter incremented to %d/%d",
                    self.id,
                    zone.id,
                    skip_count,
                    zone.run_every_n - 1,
                )

    async def publish_all_states(self) -> None:
        controller_state = ON if self._state in (ControllerState.RUNNING, ControllerState.PAUSED) else OFF
        _LOGGER.debug(
            "Irrigation %s publish_all_states: controller=%s (state=%s, active_zone=%s)",
            self.id,
            controller_state,
            self._state.value,
            self._active_zone_idx,
        )
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
        self._publish(
            self._setting_state_topic("skip_next_run"),
            {"state": ON if self._skip_next_run else OFF},
        )
        # Publish active water source for HA select entity
        src = self.active_water_source
        if self._water_sources:
            self._publish(
                self._setting_state_topic("water_source"),
                {"value": src.id if src else self._water_sources[0].id},
            )

        for idx, zone in enumerate(self._zones):
            active = ON if self._active_zone_idx == idx and self._state == ControllerState.RUNNING else OFF
            _LOGGER.debug(
                "Irrigation %s: zone %s idx=%d active=%s (active_zone_idx=%s)",
                self.id,
                zone.id,
                idx,
                active,
                self._active_zone_idx,
            )
            zone_payload: dict[str, Any] = {"state": active}
            # Add next_run attributes for zones with run_every_n > 1
            if zone.run_every_n > 1:
                zone_next_dt = self._compute_zone_next_run_time(zone)
                counter_key = f"zone/{zone.id}/skip_count"
                skip_count = int(self._get(counter_key, 0))
                zone_payload["run_every_n"] = zone.run_every_n
                zone_payload["skip_count"] = skip_count
                if zone_next_dt is not None:
                    local_tz = _local_now().tzinfo
                    next_local = zone_next_dt.astimezone(local_tz)
                    zone_payload["next_run_iso"] = zone_next_dt.isoformat()
                    zone_payload["next_run_pretty"] = next_local.strftime("%d %b %Y, %H:%M")
                else:
                    zone_payload["next_run_iso"] = ""
                    zone_payload["next_run_pretty"] = ""
            self._publish(self._zone_state_topic(zone.id), zone_payload)
            self._publish(
                self._setting_state_topic(f"zone/{zone.id}/enabled"),
                {"state": ON if zone.enabled else OFF},
            )
            self._publish(self._zone_duration_topic(zone.id), {"value": max(1, round(zone.run_duration / 60))})

        for idx, sched in enumerate(self._schedule):
            self._publish(
                self._schedule_skip_topic(idx),
                {"state": ON if bool(sched.get("skip", False)) else OFF},
            )

        # Publish zone end time for HA countdown sensor
        end_time_value = ""
        if (
            self._state == ControllerState.RUNNING
            and self._run_start_utc is not None
            and self._active_zone_remaining_s is not None
        ):
            end_dt = self._run_start_utc + timedelta(seconds=self._active_zone_remaining_s)
            end_time_value = end_dt.isoformat()
        self._publish(
            self._setting_state_topic("zone_end_time"),
            {"value": end_time_value},
        )

        # Publish next scheduled run time
        next_run_value = ""
        next_run_dt = self._compute_next_run_time()
        if next_run_dt is not None:
            next_run_value = next_run_dt.isoformat()
        self._publish(
            self._setting_state_topic("next_run_time"),
            {"value": next_run_value},
        )

    async def shutdown(self) -> None:
        """Stop the active irrigation cycle without killing schedule tasks.

        This method is safe to call from within a schedule task — it does NOT
        cancel schedule loops.  Use :meth:`full_stop` to tear down the
        controller completely (including schedule tasks).
        """
        _LOGGER.debug(
            "Irrigation %s shutdown called (state=%s, active_zone=%s). Caller: %s",
            self.id,
            self._state.value,
            self._active_zone_idx,
            "".join(traceback.format_stack(limit=5)),
        )
        self._cancel_pause_timer()
        await self._stop_current_zone()
        await self._handle_pump_stop_sequence()
        self._state = ControllerState.IDLE
        self._active_zone_idx = None
        self._active_zone_remaining_s = None
        self._single_zone_mode = False
        self._single_zone_target_idx = None
        await self.publish_all_states()

    async def full_stop(self) -> None:
        """Fully stop the controller including schedule tasks.

        Should only be called by the IrrigationManager when stopping
        or reloading controllers — never from within a schedule task.
        """
        _LOGGER.info("Irrigation %s full_stop: stopping schedules and active cycle", self.id)
        self.stop_schedules()
        await self.shutdown()

    async def pause(self) -> None:
        if self._state != ControllerState.RUNNING or self._active_zone_idx is None:
            return

        remaining = self._remaining_seconds()
        self._active_zone_remaining_s = max(1, remaining)
        self._cancel_zone_timer()
        await self._stop_current_zone()
        self._state = ControllerState.PAUSED
        self._arm_pause_timer()
        await self.publish_all_states()

    async def resume(self) -> None:
        if self._state != ControllerState.PAUSED or self._active_zone_idx is None:
            return
        self._cancel_pause_timer()
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
        _LOGGER.info(
            "Irrigation %s start_full_cycle: state=%s standby=%s skip_next=%s",
            self.id,
            self._state.value,
            self._standby,
            self._skip_next_run,
        )
        if self._standby:
            _LOGGER.info("Irrigation %s is in standby mode, not starting", self.id)
            self._publish_event(
                "standby_blocked",
                controller=self.id,
                message=f"Irrigation '{self.name}' start blocked: standby mode is active",
            )
            return

        if self._state in (ControllerState.RUNNING, ControllerState.PAUSED):
            _LOGGER.info(
                "Irrigation %s: already %s, shutting down before new cycle",
                self.id,
                self._state.value,
            )
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

        await self._start_cycle_from_eligible(scheduled=True)

    async def start_single_zone(self, zone_id: str) -> None:
        _LOGGER.debug(
            "Irrigation %s start_single_zone('%s') state=%s standby=%s",
            self.id,
            zone_id,
            self._state.value,
            self._standby,
        )
        if self._standby:
            _LOGGER.info("Irrigation %s is in standby mode, not starting zone", self.id)
            self._publish_event(
                "standby_blocked",
                controller=self.id,
                zone=zone_id,
                message=f"Irrigation '{self.name}' zone '{zone_id}' blocked: standby mode is active",
            )
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
            _LOGGER.debug("Irrigation %s shutting down before starting zone '%s'", self.id, zone_id)
            await self.shutdown()

        self._single_zone_mode = True
        self._single_zone_target_idx = match_idx
        _LOGGER.debug("Irrigation %s calling _start_zone(%d) for zone '%s'", self.id, match_idx, zone_id)
        await self._start_zone(match_idx)

    async def _start_cycle_from_eligible(self, scheduled: bool = False) -> None:
        """Build the eligible zone list and start the first zone.

        When ``scheduled`` is True (i.e. triggered by the daily schedule,
        not a repeat), skip counters are advanced **after** reading
        eligibility so that the current counter values decide this cycle
        and the increments prepare counters for the next one.
        """
        eligible = self._eligible_zones()
        if scheduled:
            self._apply_skip_counters()
        _LOGGER.info(
            "Irrigation %s _start_cycle_from_eligible: %d eligible zones: %s",
            self.id,
            len(eligible),
            [(idx, z.id) for idx, z in eligible],
        )
        if not eligible:
            _LOGGER.info("Irrigation %s: no eligible zones in this cycle", self.id)
            self._state = ControllerState.IDLE
            self._active_zone_idx = None
            await self.publish_all_states()
            return

        first_idx = eligible[0][0]
        await self._start_zone(first_idx)

    async def _advance_to_next_zone(self, force: bool = False) -> None:
        _LOGGER.debug(
            "Irrigation %s _advance_to_next_zone(force=%s) active_zone=%s single_zone=%s",
            self.id,
            force,
            self._active_zone_idx,
            self._single_zone_mode,
        )
        if self._active_zone_idx is None:
            _LOGGER.debug("Irrigation %s: no active zone, shutting down", self.id)
            await self.shutdown()
            return

        finished_idx = self._active_zone_idx
        finished_zone = self._zones[finished_idx]

        if self._single_zone_mode:
            _LOGGER.debug("Irrigation %s: single zone mode complete for zone '%s'", self.id, finished_zone.id)
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

        # Only look at zones AFTER the current position — no wrap-around.
        # Wrapping would cause the cycle to never complete.
        tail = ordered[current_pos + 1 :]
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
                self._active_zone_remaining_s = max(1, duration)
                self._run_start_utc = utcnow()
                self._arm_zone_timer(self._active_zone_remaining_s)
                await self.publish_all_states()
                return

            await self._stop_current_zone()

            # Handle valve_open_delay between zones
            src = self.active_water_source
            if self._valve_open_delay_s > 0:
                if src and src.pump_switch_off_during_valve_open_delay:
                    await self._deactivate_source()
                await asyncio.sleep(self._valve_open_delay_s)
                if src and src.pump_switch_off_during_valve_open_delay:
                    await self._activate_source()

            await self._start_zone(next_idx)
            return

        if self._current_repeat_index < self._repeat:
            self._current_repeat_index += 1
            await self._start_cycle_from_eligible()
            return

        self._publish_event(
            "cycle_complete",
            controller=self.id,
            message=f"Irrigation '{self.name}' cycle completed",
        )
        await self.shutdown()

    def _ordered_zone_indices(self) -> list[int]:
        idxs = list(range(len(self._zones)))
        if self._reverse:
            idxs.reverse()
        return idxs

    async def _start_zone(self, idx: int, override_duration: int | None = None) -> None:
        """Start a specific zone by index.

        Activates the water source outputs (if any), then opens the zone valve,
        respecting per-source pump timing delays.

        If any output is blocked by an interlock, the controller shuts down
        and publishes an interlock fault notification.
        """
        if idx < 0 or idx >= len(self._zones):
            _LOGGER.error("Irrigation %s _start_zone: invalid index %d (zones=%d)", self.id, idx, len(self._zones))
            return

        zone = self._zones[idx]
        duration = override_duration if override_duration is not None else self._scaled_duration(zone.run_duration)
        duration = max(1, duration)
        src = self.active_water_source

        _LOGGER.debug(
            "Irrigation %s _start_zone: idx=%d, zone=%s, valve=%s, duration=%ds, source=%s",
            self.id,
            idx,
            zone.id,
            zone.valve.id if zone.valve else "NONE",
            duration,
            src.id if src else "NONE",
        )

        self._active_zone_idx = idx
        self._active_zone_remaining_s = duration
        self._state = ControllerState.RUNNING

        # Publish state immediately so the UI (frontend + HA) shows
        # RUNNING right away, before any pump/valve delay sleeps.
        # The timer has not been armed yet so zone_end_time will be
        # empty, but a second publish happens after hardware activation.
        self._run_start_utc = utcnow()
        await self.publish_all_states()

        if src is not None:
            if src.pump_start_valve_delay_s > 0:
                # Source first (pump+valve), then zone valve after delay
                _LOGGER.debug(
                    "Irrigation %s: source '%s' ON, then wait %ds", self.id, src.id, src.pump_start_valve_delay_s
                )
                source_ok = await self._activate_source()
                if not source_ok:
                    await self._handle_interlock_fault(zone.id, src.id)
                    return
                await asyncio.sleep(src.pump_start_valve_delay_s)
            elif src.pump_start_pump_delay_s > 0:
                # Zone valve first, then source after delay
                _LOGGER.debug(
                    "Irrigation %s: zone valve ON first, then source '%s' after %ds",
                    self.id,
                    src.id,
                    src.pump_start_pump_delay_s,
                )
                try:
                    valve_ok = await zone.valve.async_turn_on(timestamp=time.time())
                    if not valve_ok:
                        await self._handle_interlock_fault(zone.id, src.id)
                        return
                except Exception as err:
                    _LOGGER.error("Failed to turn on zone %s: %s", zone.id, err)
                    await self.shutdown()
                    return
                await asyncio.sleep(src.pump_start_pump_delay_s)
                source_ok = await self._activate_source()
                if not source_ok:
                    # Valve was already ON — turn it off before shutting down
                    await zone.valve.async_turn_off(timestamp=time.time())
                    await self._handle_interlock_fault(zone.id, src.id)
                    return
                try:
                    self._run_start_utc = utcnow()
                    self._arm_zone_timer(duration)
                    _LOGGER.info("Irrigation %s: zone %s running, timer armed for %ds", self.id, zone.id, duration)
                    await self.publish_all_states()
                except BaseException as err:
                    _LOGGER.error(
                        "Irrigation %s: CRITICAL error after valve ON (pump delay path): %s (%s)",
                        self.id,
                        err,
                        type(err).__name__,
                        exc_info=True,
                    )
                return
            else:
                # No delay — activate source, then optional valve_open_delay
                _LOGGER.debug("Irrigation %s: source '%s' ON (no delay)", self.id, src.id)
                source_ok = await self._activate_source()
                if not source_ok:
                    await self._handle_interlock_fault(zone.id, src.id)
                    return
                if self._valve_open_delay_s > 0:
                    await asyncio.sleep(self._valve_open_delay_s)

        try:
            _LOGGER.debug("Irrigation %s: turning ON valve %s", self.id, zone.valve.id)
            valve_ok = await zone.valve.async_turn_on(timestamp=time.time())
            if not valve_ok:
                await self._deactivate_source()
                await self._handle_interlock_fault(zone.id, src.id if src else None)
                return
            _LOGGER.debug("Irrigation %s: valve %s turned ON successfully", self.id, zone.valve.id)
        except Exception as err:
            _LOGGER.error("Failed to turn on zone %s valve %s: %s", zone.id, zone.valve.id, err, exc_info=True)
            await self.shutdown()
            return
        try:
            _LOGGER.debug("Irrigation %s: arming zone timer...", self.id)
            self._run_start_utc = utcnow()
            self._arm_zone_timer(duration)
            _LOGGER.info("Irrigation %s: zone %s running, timer armed for %ds", self.id, zone.id, duration)
            await self.publish_all_states()
            _LOGGER.debug("Irrigation %s: publish_all_states completed", self.id)
        except BaseException as err:
            _LOGGER.error(
                "Irrigation %s: CRITICAL error after valve ON: %s (%s)",
                self.id,
                err,
                type(err).__name__,
                exc_info=True,
            )

    async def _stop_current_zone(self) -> None:
        self._cancel_zone_timer()
        if self._active_zone_idx is None:
            return
        zone = self._zones[self._active_zone_idx]
        try:
            await zone.valve.async_turn_off(timestamp=time.time())
        except Exception as err:
            _LOGGER.error("Failed to turn off zone %s: %s", zone.id, err)

    async def _activate_source(self) -> bool:
        """Turn ON all outputs of the active water source.

        Returns:
            True if source was activated, False if blocked by interlock.
        """
        src = self.active_water_source
        if src is None:
            return True
        try:
            _LOGGER.debug("Irrigation %s: activating source '%s' outputs=%s", self.id, src.id, src.output_ids)
            return await src.activate(timestamp=time.time())
        except Exception as err:
            _LOGGER.error("Failed to activate water source '%s' for %s: %s", src.id, self.id, err)
            return False

    async def _deactivate_source(self) -> None:
        """Turn OFF all outputs of the active water source."""
        src = self.active_water_source
        if src is None:
            return
        try:
            _LOGGER.debug("Irrigation %s: deactivating source '%s' outputs=%s", self.id, src.id, src.output_ids)
            await src.deactivate(timestamp=time.time())
        except Exception as err:
            _LOGGER.error("Failed to deactivate water source '%s' for %s: %s", src.id, self.id, err)

    async def _handle_interlock_fault(self, zone_id: str, source_id: str | None) -> None:
        """Handle interlock-blocked activation.

        Shuts down the controller and publishes both a retained fault status
        message and a non-retained HA event notification via the event entity.
        Home Assistant automations can listen to the event entity to trigger
        mobile push notifications, Telegram messages, etc.

        Args:
            zone_id: ID of the zone that was being started.
            source_id: ID of the water source (if any) whose output was blocked.
        """
        source_info = f" (source '{source_id}')" if source_id else ""
        _LOGGER.error(
            "Irrigation %s: INTERLOCK FAULT — could not start zone '%s'%s. "
            "Another controller or output in the same interlock group is active. Shutting down.",
            self.id,
            zone_id,
            source_info,
        )

        fault_message = f"Irrigation '{self.name}' stopped: output blocked by interlock (zone: {zone_id})"

        # Publish retained fault status on MQTT (legacy topic)
        fault_payload = {
            "fault": "interlock_blocked",
            "controller": self.id,
            "zone": zone_id,
            "source": source_id or "",
            "message": fault_message,
        }
        self._publish(
            f"{self._topic_prefix}/{IRRIGATION}/{self.id}/fault",
            fault_payload,
            retain=False,
        )

        # Publish HA event entity notification (non-retained, instantaneous)
        self._publish_event(
            "interlock_fault",
            controller=self.id,
            zone=zone_id,
            source=source_id or "",
            message=fault_message,
        )

        await self.shutdown()
        await self.publish_all_states()

    async def _handle_pump_stop_sequence(self) -> None:
        """Handle pump stop timing according to active water source's delays."""
        src = self.active_water_source
        if src is None:
            return
        if src.pump_stop_valve_delay_s > 0:
            # Source off first, then wait
            await self._deactivate_source()
            await asyncio.sleep(src.pump_stop_valve_delay_s)
        elif src.pump_stop_pump_delay_s > 0:
            # Zone valve already off, source off after delay
            await asyncio.sleep(src.pump_stop_pump_delay_s)
            await self._deactivate_source()
        else:
            await self._deactivate_source()

    def _scaled_duration(self, seconds: int) -> int:
        return max(1, round(seconds * self._multiplier))

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
        point = utcnow() + timedelta(seconds=max(1, seconds))
        self._zone_timer_cancel = async_track_point_in_time(
            loop=self._event_bus._loop,
            job=self._zone_timer_callback,
            point_in_time=point,
        )

    async def _zone_timer_callback(self, _timestamp: datetime) -> None:
        await self._advance_to_next_zone(force=False)

    def _cancel_pause_timer(self) -> None:
        """Cancel the pause timeout timer if active."""
        if self._pause_timer_cancel is not None:
            self._pause_timer_cancel()
            self._pause_timer_cancel = None

    def _arm_pause_timer(self) -> None:
        """Arm an auto-shutdown timer for the PAUSED state.

        If pause_timeout_s is 0, no timer is set (pause lasts indefinitely).
        Otherwise, the controller will auto-shutdown after the configured timeout.
        """
        self._cancel_pause_timer()
        if self._pause_timeout_s <= 0:
            return
        point = utcnow() + timedelta(seconds=self._pause_timeout_s)
        self._pause_timer_cancel = async_track_point_in_time(
            loop=self._event_bus._loop,
            job=self._pause_timeout_callback,
            point_in_time=point,
        )
        _LOGGER.info(
            "Irrigation %s: pause timeout armed for %d seconds",
            self.id,
            self._pause_timeout_s,
        )

    async def _pause_timeout_callback(self, _timestamp: datetime) -> None:
        """Handle pause timeout — auto-shutdown the controller."""
        if self._state != ControllerState.PAUSED:
            return
        _LOGGER.warning(
            "Irrigation %s: pause timeout expired after %d seconds, shutting down",
            self.id,
            self._pause_timeout_s,
        )
        await self.shutdown()

    async def handle_main_command(self, payload: str) -> None:
        cmd = payload.strip()
        upper = cmd.upper()
        _LOGGER.debug("Irrigation %s handle_main_command: payload='%s' → upper='%s'", self.id, payload, upper)

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
        _LOGGER.debug(
            "Irrigation %s handle_zone_command: zone='%s' payload='%s' → upper='%s'", self.id, zone_id, payload, upper
        )
        if upper == ON:
            await self.start_single_zone(zone_id)
        elif upper == OFF:
            await self.shutdown()

    async def handle_zone_duration_command(self, zone_id: str, payload: str) -> None:
        """Handle duration change from HA (value in minutes)."""
        try:
            minutes = int(float(payload))
        except (TypeError, ValueError):
            return
        if minutes <= 0:
            return

        duration_s = minutes * 60
        for zone in self._zones:
            if zone.id == zone_id:
                zone.run_duration = duration_s
                self._save(f"zone/{zone.id}/duration", duration_s)
                break
        await self.publish_all_states()

    async def set_auto_advance(self, value: bool) -> None:
        self._auto_advance = value
        self._save("auto_advance", self._auto_advance)
        await self.publish_all_states()

    async def set_reverse(self, value: bool) -> None:
        self._reverse = value
        self._save("reverse", self._reverse)
        await self.publish_all_states()

    async def set_standby(self, value: bool) -> None:
        self._standby = value
        self._save("standby", self._standby)
        if self._standby and self._state in (ControllerState.RUNNING, ControllerState.PAUSED):
            await self.shutdown()
        await self.publish_all_states()

    async def set_multiplier(self, value: float) -> None:
        self._multiplier = max(0.1, value)
        self._save("multiplier", self._multiplier)
        await self.publish_all_states()

    async def set_repeat(self, value: int) -> None:
        self._repeat = max(0, value)
        self._save("repeat", self._repeat)
        await self.publish_all_states()

    async def set_zone_enabled(self, zone_id: str, value: bool) -> None:
        for zone in self._zones:
            if zone.id == zone_id:
                zone.enabled = value
                self._save(f"zone/{zone.id}/enabled", zone.enabled)
                break
        await self.publish_all_states()

    async def set_skip_next_run(self, value: bool) -> None:
        self._skip_next_run = value
        self._save("skip_next_run", self._skip_next_run)
        await self.publish_all_states()

    async def set_water_source(self, source_id: str) -> None:
        """Switch active water source by ID.

        Args:
            source_id: ID of the water source to activate.
        """
        for i, ws in enumerate(self._water_sources):
            if ws.id == source_id:
                self._active_water_source_idx = i
                self._save("active_water_source", source_id)
                _LOGGER.info("Irrigation %s: water source changed to '%s'", self.id, source_id)
                await self.publish_all_states()
                return
        _LOGGER.warning("Irrigation %s: unknown water source '%s'", self.id, source_id)

    async def set_schedule_skip(self, schedule_idx: int, value: bool) -> None:
        if schedule_idx < 0 or schedule_idx >= len(self._schedule):
            return
        self._schedule[schedule_idx]["skip"] = value
        self._save(f"schedule/{schedule_idx}/skip", value)
        await self.publish_all_states()

    def _compute_next_run_time(self) -> datetime | None:
        """Compute the next scheduled run time across all schedules.

        Returns the earliest upcoming fire time, or None if no schedules
        are configured or the controller is in standby.
        """
        if not self._schedule or self._standby:
            return None

        earliest: datetime | None = None
        for schedule in self._schedule:
            time_str = schedule.get("time", "06:00")
            days = str(schedule.get("days", "daily")).strip().lower()
            candidate = _next_fire_time(time_str, days)
            if earliest is None or candidate < earliest:
                earliest = candidate
        return earliest

    def _compute_zone_next_run_time(self, zone: IrrigationZone) -> datetime | None:
        """Compute when a specific zone will actually run next.

        Accounts for ``run_every_n``: if the zone needs 2 more skipped
        cycles before it's eligible, this returns the fire time of the
        (skip_remaining + 1)th upcoming schedule.

        Args:
            zone: The irrigation zone to compute for.

        Returns:
            Timezone-aware UTC datetime of the zone's next actual run,
            or None if no schedules are configured or the controller
            is in standby or the zone is disabled.
        """
        if not self._schedule or self._standby or not zone.enabled:
            return None

        if zone.run_every_n <= 1:
            # Runs every cycle — same as controller next_run_time
            return self._compute_next_run_time()

        counter_key = f"zone/{zone.id}/skip_count"
        skip_count = int(self._get(counter_key, 0))
        remaining_skips = max(0, (zone.run_every_n - 1) - skip_count)

        # The zone will run on the (remaining_skips + 1)th cycle
        cycles_until_run = remaining_skips + 1

        # Find the Nth fire time across all schedules
        # Strategy: collect fire times from all schedules, sort, pick Nth
        earliest: datetime | None = None
        for schedule in self._schedule:
            time_str = schedule.get("time", "06:00")
            days = str(schedule.get("days", "daily")).strip().lower()
            candidate = _nth_fire_time(time_str, days, n=cycles_until_run)
            if earliest is None or candidate < earliest:
                earliest = candidate
        return earliest

    def start_schedules(self) -> None:
        """Start all schedule loops as asyncio tasks.

        Cancels any existing schedule tasks first, then creates new ones.
        Each schedule entry gets its own long-lived asyncio.Task that
        sleeps until the next fire time.
        """
        self.stop_schedules()
        if not self._schedule:
            _LOGGER.debug("Irrigation %s: no schedules configured", self.id)
            return
        for idx, schedule in enumerate(self._schedule):
            task = asyncio.create_task(
                self._run_schedule_loop(idx, schedule),
                name=f"irrigation_{self.id}_schedule_{idx}",
            )
            self._schedule_tasks.append(task)
            _LOGGER.info(
                "Irrigation %s: schedule task #%d started (time=%s, days=%s)",
                self.id,
                idx,
                schedule.get("time", "06:00"),
                schedule.get("days", "daily"),
            )

    def stop_schedules(self) -> None:
        """Cancel all schedule tasks."""
        if self._schedule_tasks:
            _LOGGER.info(
                "Irrigation %s: stopping %d schedule task(s)",
                self.id,
                len(self._schedule_tasks),
            )
        for task in self._schedule_tasks:
            task.cancel()
        self._schedule_tasks = []

    async def _run_schedule_loop(self, schedule_idx: int, schedule: dict[str, Any]) -> None:
        """Run a single schedule entry in a loop.

        Sleeps until the next fire time, then starts a full irrigation cycle.
        This task runs for the entire lifetime of the controller.

        CRITICAL: This method must NEVER raise an unhandled exception,
        as that would permanently kill the schedule task with no recovery.
        All exceptions are caught, logged, and the loop continues with
        a back-off delay.

        Args:
            schedule_idx: Index of this schedule in the schedule list.
            schedule: Schedule configuration dict with 'time' and 'days'.
        """
        time_str = schedule.get("time", "06:00")
        days = str(schedule.get("days", "daily")).strip().lower()
        consecutive_errors = 0

        _LOGGER.info(
            "Irrigation %s: schedule loop #%d started (time=%s, days=%s)",
            self.id,
            schedule_idx,
            time_str,
            days,
        )

        while True:
            try:
                next_run = _next_fire_time(time_str, days)
                now = utcnow()
                wait_s = max(1.0, (next_run - now).total_seconds())

                # Convert to local for human-readable log
                local_tz = _local_now().tzinfo
                next_run_local = next_run.astimezone(local_tz)
                _LOGGER.info(
                    "Irrigation %s: schedule #%d next fire at %s (in %.0f seconds)",
                    self.id,
                    schedule_idx,
                    next_run_local.strftime("%Y-%m-%d %H:%M:%S %Z"),
                    wait_s,
                )

                await asyncio.sleep(wait_s)

                # Reset error counter on successful wake-up
                consecutive_errors = 0

                if bool(schedule.get("skip", False)):
                    _LOGGER.info(
                        "Irrigation %s: schedule #%d skipped (one-time skip)",
                        self.id,
                        schedule_idx,
                    )
                    schedule["skip"] = False
                    self._save(f"schedule/{schedule_idx}/skip", False)
                    await self.publish_all_states()
                    continue

                _LOGGER.info(
                    "Irrigation %s: schedule #%d firing — starting full cycle",
                    self.id,
                    schedule_idx,
                )
                await self.start_full_cycle()

            except asyncio.CancelledError:
                _LOGGER.info(
                    "Irrigation %s: schedule loop #%d cancelled",
                    self.id,
                    schedule_idx,
                )
                raise
            except Exception:
                consecutive_errors += 1
                backoff_s = min(300, 30 * consecutive_errors)
                _LOGGER.exception(
                    "Irrigation %s: schedule loop #%d encountered an error "
                    "(attempt %d, retrying in %ds)",
                    self.id,
                    schedule_idx,
                    consecutive_errors,
                    backoff_s,
                )
                await asyncio.sleep(backoff_s)

def _local_now() -> datetime:
    """Return the current time in the system's local timezone.

    Extracted as a module-level function so tests can mock it easily.
    """
    local_tz = dt.datetime.now().astimezone().tzinfo
    return dt.datetime.now(local_tz)


def _next_fire_time(time_str: str, days: str) -> datetime:
    """Compute next fire time for a schedule entry.

    Shorthand for ``_nth_fire_time(time_str, days, n=1)``.
    """
    return _nth_fire_time(time_str, days, n=1)


def _nth_fire_time(time_str: str, days: str, n: int = 1) -> datetime:
    """Compute the Nth upcoming fire time for a schedule entry.

    The user-configured ``time_str`` (e.g. "18:00") is in **local time**.
    We build candidates in the system's local timezone and then convert
    to UTC.

    Args:
        time_str: Schedule time in "HH:MM" format (local time).
        days: Day filter string ("daily", "weekdays", "weekends", etc.).
        n: Which occurrence to return (1 = next, 2 = the one after, etc.).

    Returns:
        Nth fire time as a timezone-aware UTC datetime.
    """
    now_local = _local_now()

    try:
        hh, mm = time_str.split(":", 1)
        target_h = int(hh)
        target_m = int(mm)
    except Exception:
        target_h, target_m = 6, 0

    allowed_days = _DAYS_MAP.get(days, _DAYS_MAP["daily"])
    found = 0

    for plus_days in range(0, 366):
        candidate_local = (now_local + timedelta(days=plus_days)).replace(
            hour=target_h,
            minute=target_m,
            second=0,
            microsecond=0,
        )
        if candidate_local.weekday() in allowed_days and candidate_local > now_local:
            found += 1
            if found >= n:
                return candidate_local.astimezone(dt.UTC)

    # Fallback (should never reach for n <= 365)
    fallback_local = (now_local + timedelta(days=n)).replace(
        hour=target_h,
        minute=target_m,
        second=0,
        microsecond=0,
    )
    return fallback_local.astimezone(dt.UTC)


