"""Schedules: actions that fire on their own.

Everything else in boneIO starts with a person or an input. A schedule is the
exception — it runs at a clock time, or at a moment the Sun defines, with
nobody present. That is the whole value and also the reason this module is
careful: a bug here acts on the house at four in the morning.

Three things it refuses to guess at:

* **A clock that has not been set.** The board has no battery-backed RTC, so
  between power-on and the first NTP reply it believes it is 1970. Nothing is
  armed until the date is plausible.
* **A day when the Sun does not reach the angle.** Above the Arctic Circle
  `sunset` simply does not happen for weeks. The schedule skips to the next day
  that has one rather than inventing a time.
* **A firing that was missed while the device was off.** Silently catching up
  hours later is worse than not firing, so catching up is opt-in and bounded.

Timers are re-planned every minute from the current wall clock. That is not
paranoia: NTP steps the clock at boot, and a timer armed before the step points
at the wrong instant afterwards.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
import time as _time
from collections import deque
from datetime import datetime, timedelta, timezone
from datetime import time as dt_time
from typing import TYPE_CHECKING, Any

from boneio.core.events.bus import async_track_point_in_time
from boneio.core.utils.naming import resolve_id
from boneio.core.manager.action_conditions import (
    precompile_conditions,
    should_execute_action,
)

if TYPE_CHECKING:
    from boneio.core.manager import Manager

_LOGGER = logging.getLogger("boneio.scheduler")

#: How often the plan is rebuilt from the current wall clock.
_SUPERVISE_INTERVAL = 60.0

#: How far ahead to look for a day this schedule can actually fire on. Covers a
#: weekday filter (7) and a sun event missing for a stretch; beyond that the
#: honest answer is "not soon" rather than a date months out.
_MAX_LOOKAHEAD_DAYS = 400

#: How many past runs are kept per schedule. Twenty covers "did it work this
#: week" for anything that fires daily, and keeps ``state.json`` small enough
#: that the whole file is still rewritten in one go without anyone noticing.
_HISTORY_LIMIT = 20

#: The section of ``state.json`` this module owns.
_STATE_SECTION = "schedule"

#: What a run can end as. Three outcomes, because a schedule that fired and
#: then declined to act on its condition is neither a success nor a failure —
#: and telling those apart is the whole reason this record exists.
OUTCOME_RAN = "ran"
OUTCOME_SKIPPED = "skipped_condition"
OUTCOME_FAILED = "failed"

#: Where a run came from. A catch-up and a button press look identical in the
#: log otherwise, and they are the two people ask about.
SOURCE_TIMER = "timer"
SOURCE_CATCH_UP = "catch_up"
SOURCE_MANUAL = "manual"

#: The MQTT topic segment schedules publish under, kept here so this module
#: does not import the const table just for one string.
_SCHEDULE_TOPIC = "schedule"

#: The diagnostic sensors each schedule publishes: (suffix, state key,
#: HA device class, icon).
_HA_SENSORS: tuple[tuple[str, str, str | None, str | None], ...] = (
    ("next_fire", "next_fire", "timestamp", "mdi:clock-outline"),
    ("last_fire", "last_fire", "timestamp", "mdi:history"),
    ("last_outcome", "last_outcome", None, "mdi:check-circle-outline"),
)

#: Day filters, matching the vocabulary the irrigation schedules already use.
#: Monday is 0, as ``datetime.weekday()`` has it.
_DAYS_MAP: dict[str, frozenset[int]] = {
    "daily": frozenset(range(7)),
    "weekdays": frozenset({0, 1, 2, 3, 4}),
    "weekend": frozenset({5, 6}),
    "mon": frozenset({0}),
    "tue": frozenset({1}),
    "wed": frozenset({2}),
    "thu": frozenset({3}),
    "fri": frozenset({4}),
    "sat": frozenset({5}),
    "sun": frozenset({6}),
}




def _local_exists(candidate: datetime) -> bool:
    """Whether this wall-clock time happens at all in its own zone.

    The round trip goes through UTC on purpose: ``astimezone()`` into the zone
    a value already carries is a no-op in CPython, so it never renormalises
    and would report a time inside a DST gap as fine.
    """
    tz = candidate.tzinfo
    normalized = candidate.astimezone(timezone.utc).astimezone(tz)
    return normalized.replace(tzinfo=None) == candidate.replace(tzinfo=None)


def _local_instant(day, clock: dt_time, tz) -> datetime:
    """The first instant at or after ``clock`` on ``day``, in ``tz``.

    One rule for both ends of the year, which is the reason to state it that
    way. In spring an hour goes missing — Poland has no 02:30 on the last
    Sunday in March — and ``datetime.combine`` does not refuse it: it attaches
    the offset from *before* the change, producing an instant that is really
    an hour later than asked, while still printing the time that was asked
    for. A schedule set for 02:30 fired at 03:30 and said 02:30 in the log.
    Here it fires at 03:00, the first moment that exists.

    In autumn the hour happens twice and both instants are real; the earlier
    one is taken, so the schedule fires once rather than twice.

    Args:
        day: The local date.
        clock: The local wall-clock time asked for.
        tz: The local zone.

    Returns:
        An aware datetime whose offset is the one actually in force.
    """
    candidate = datetime.combine(day, clock, tzinfo=tz)
    if _local_exists(candidate):
        return candidate

    # Walk to the first minute that does exist. Gaps are an hour wherever this
    # runs; the bound is only so a pathological zone cannot spin.
    for minutes in range(1, 24 * 60):
        probe = candidate + timedelta(minutes=minutes)
        probe = datetime.combine(probe.date(), probe.time(), tzinfo=tz)
        if _local_exists(probe):
            _LOGGER.info(
                "%s does not exist on %s in this timezone (the clocks go "
                "forward); firing at %s instead.",
                clock.strftime("%H:%M"),
                day,
                probe.strftime("%H:%M"),
            )
            return probe
    return candidate


def _clamp_to_window(when: datetime, trigger: dict, tz) -> datetime:
    """Hold a sun anchor inside ``earliest``/``latest``, if it was given any.

    Both are clock times on the local date the firing lands on, which is the
    date after ``offset`` — an anchor pushed past midnight is clamped against
    the day it actually happens on, the same rule the day filter uses.

    Applied before ``jitter`` on purpose. Clamping afterwards would put every
    midsummer evening at exactly the same minute, which is the pattern jitter
    exists to break; so a clamped firing can still land up to ``jitter`` later
    than ``latest``.

    Args:
        when: The anchor, already shifted by ``offset``.
        trigger: The schedule's trigger.
        tz: The local timezone.

    Returns:
        ``when``, or the bound it crossed.
    """
    local = when.astimezone(tz)

    def bound(key: str) -> datetime | None:
        value = trigger.get(key)
        if not value:
            return None
        hour, minute = (int(part) for part in str(value).split(":", 1))
        return _local_instant(local.date(), dt_time(hour, minute), tz)

    earliest, latest = bound("earliest"), bound("latest")
    if earliest is not None and local < earliest:
        return earliest
    if latest is not None and local > latest:
        return latest
    return when


class _Entry:
    """One configured schedule, with its parsed actions and armed timer."""

    __slots__ = (
        "id",
        "name",
        "enabled",
        "config_enabled",
        "trigger",
        "on_missed",
        "catch_up",
        "actions",
        "condition",
        "cancel",
        "next_fire",
        "last_fire",
        "last_error",
        "last_outcome",
        "last_duration_ms",
        "history",
    )

    def __init__(self, config: dict, index: int) -> None:
        # An explicit id wins; otherwise it is made from the name, so a config
        # written as `name: Rolety o zmierzchu` says the same words the panel
        # does. The positional fallback is for an entry with neither.
        self.id = resolve_id(config) or f"schedule_{index + 1}"
        self.name = config.get("name") or self.id
        # What the YAML says, kept apart from what is in force: a switch in
        # Home Assistant can disagree with the file, and deciding which of the
        # two wins needs both values. See Scheduler._restore.
        self.config_enabled = bool(config.get("enabled", True))
        self.enabled = self.config_enabled
        self.trigger = config.get("trigger") or {}
        self.on_missed = config.get("on_missed", "skip")
        self.catch_up = float(config.get("catch_up") or 0.0)
        self.actions: list[dict] = []
        self.condition: Any = None
        self.cancel: Any = None
        self.next_fire: datetime | None = None
        # When the timer last fired, whatever came of it — not "when it last
        # succeeded". A schedule stopped by its own condition has fired.
        self.last_fire: datetime | None = None
        self.last_error: str | None = None
        self.last_outcome: str | None = None
        self.last_duration_ms: int | None = None
        self.history: deque[dict] = deque(maxlen=_HISTORY_LIMIT)

    @property
    def days(self) -> frozenset[int]:
        return _DAYS_MAP.get(self.trigger.get("days", "daily"), _DAYS_MAP["daily"])

    def disarm(self) -> None:
        """Cancel the armed timer, if any."""
        if self.cancel is not None:
            # An already-fired timer has nothing to cancel.
            with contextlib.suppress(Exception):
                self.cancel()
            self.cancel = None
        self.next_fire = None


class Scheduler:
    """Owns every configured schedule and the timers behind them.

    Args:
        manager: The manager, for actions, the Sun and the event loop.
        schedules: The parsed ``schedule:`` section.
    """

    def __init__(self, manager: Manager, schedules: list[dict] | None = None) -> None:
        self._manager = manager
        self._entries: list[_Entry] = []
        self._task: asyncio.Task | None = None
        self._running = False
        self._warned_clock = False
        self._skipped_today: set[str] = set()
        self._load(schedules or [])

    # ── configuration ────────────────────────────────────────────────────

    def _load(self, schedules: list[dict]) -> None:
        """Build entries and parse their actions once."""
        self._entries = []
        for index, config in enumerate(schedules or []):
            entry = _Entry(config, index)
            # The same parser the inputs use, so a schedule's actions support
            # exactly what a button's do — including their own conditions.
            parsed = self._manager.parse_actions(entry.id, {"fire": config.get("actions", [])})
            entry.actions = parsed.get("fire", [])
            self._restore(entry)
            if not entry.actions:
                _LOGGER.warning(
                    "Schedule '%s' has no usable actions; it will not be armed.", entry.id
                )
                # After the restore, deliberately: a schedule with nothing to
                # do stays unarmed no matter what anyone switched on.
                entry.enabled = False
            entry.condition = precompile_conditions(config, self._manager.sun)
            self._entries.append(entry)

        if self._entries:
            _LOGGER.info(
                "Loaded %d schedule(s): %s",
                len(self._entries),
                [e.id for e in self._entries],
            )

    # ── persistence ──────────────────────────────────────────────────────

    def _state_manager(self) -> Any:
        """The state store, or None when there is none to talk to.

        Tests build the manager as a stub and the scheduler has to survive
        that, so every use of the store goes through here.
        """
        store = getattr(self._manager, "_state_manager", None)
        if store is None or not hasattr(store, "save_attribute"):
            return None
        return store

    def _restore(self, entry: _Entry) -> None:
        """Bring back what this schedule did last time, and whether it is on.

        The interesting half is ``enabled``. A switch in Home Assistant and an
        ``enabled:`` line in the YAML can disagree, and whichever answer we
        pick blindly is wrong half the time: honour the stored value always and
        editing the file appears to do nothing; honour the file always and
        every reload throws away what someone just switched. So we also store
        what the file said when the override was written. If the file still
        says that, nobody touched it and the override stands. If it changed,
        that is a person expressing an opinion in the file, and it wins.
        """
        store = self._state_manager()
        if store is None:
            return
        try:
            stored = store.get(_STATE_SECTION, entry.id, None)
        except Exception:  # noqa: BLE001 - a broken store must not stop the boot
            return
        if not isinstance(stored, dict):
            return

        if stored.get("enabled_from_config") == entry.config_enabled:
            entry.enabled = bool(stored.get("enabled", entry.config_enabled))
        elif "enabled_from_config" in stored:
            _LOGGER.info(
                "Schedule '%s': enabled: changed in the config to %s, dropping the "
                "stored override.",
                entry.id,
                entry.config_enabled,
            )

        history = stored.get("history")
        if isinstance(history, list):
            entry.history = deque(
                (item for item in history if isinstance(item, dict)),
                maxlen=_HISTORY_LIMIT,
            )
            if entry.history:
                last = entry.history[-1]
                entry.last_outcome = last.get("outcome")
                entry.last_error = last.get("error")
                entry.last_duration_ms = last.get("duration_ms")
                with contextlib.suppress(TypeError, ValueError):
                    entry.last_fire = datetime.fromisoformat(last["at"])

    def _persist(self, entry: _Entry) -> None:
        """Write one schedule's state out. Debounced by the store itself."""
        store = self._state_manager()
        if store is None:
            return
        with contextlib.suppress(Exception):
            store.save_attribute(
                attr_type=_STATE_SECTION,
                attribute=entry.id,
                value={
                    "enabled": entry.enabled,
                    "enabled_from_config": entry.config_enabled,
                    "history": list(entry.history),
                },
            )

    # ── Home Assistant ───────────────────────────────────────────────────

    def publish_discovery(self) -> None:
        """Announce every schedule to Home Assistant.

        A disabled schedule is announced too. "Disabled" is a state worth
        seeing — a schedule that vanishes from the panel when it is switched
        off is exactly the thing that makes people ask whether it ever
        existed.
        """
        if not hasattr(self._manager, "publish_ha_discovery"):
            return
        from boneio.integration.homeassistant import (
            ha_schedule_sensor_message,
            ha_schedule_switch_message,
        )

        helper = self._manager._config_helper
        for entry in self._entries:
            with contextlib.suppress(Exception):
                self._manager.publish_ha_discovery(
                    id=entry.id,
                    ha_type="switch",
                    payload=ha_schedule_switch_message(
                        id=entry.id, name=entry.name, config_helper=helper
                    ),
                )
                for suffix, key, device_class, icon in _HA_SENSORS:
                    self._manager.publish_ha_discovery(
                        id=f"{entry.id}_{suffix}",
                        ha_type="sensor",
                        payload=ha_schedule_sensor_message(
                            id=entry.id,
                            name=entry.name,
                            suffix=suffix,
                            key=key,
                            config_helper=helper,
                            device_class=device_class,
                            icon=icon,
                        ),
                    )

    def _announce(self, entry: _Entry) -> None:
        """Publish one schedule's state, retained.

        All four entities read this one message, so they move together.
        """
        send = getattr(self._manager, "send_message", None)
        if send is None:
            return
        helper = getattr(self._manager, "_config_helper", None)
        prefix = getattr(helper, "topic_prefix", None)
        if not isinstance(prefix, str):
            return
        with contextlib.suppress(Exception):
            send(
                topic=f"{prefix}/{_SCHEDULE_TOPIC}/{entry.id}",
                payload={
                    "state": "ON" if entry.enabled else "OFF",
                    # Empty string, not null: the irrigation countdown already
                    # says "nothing to show" this way and HA reads it as
                    # unknown instead of failing to parse a timestamp.
                    "next_fire": entry.next_fire.isoformat() if entry.next_fire else "",
                    "last_fire": entry.last_fire.isoformat() if entry.last_fire else "",
                    "last_outcome": entry.last_outcome or "never",
                    "last_error": entry.last_error or "",
                },
                retain=True,
            )

    def announce_all(self) -> None:
        """Re-publish every schedule's state. Used after a reload."""
        for entry in self._entries:
            self._announce(entry)

    def _notify_panel(self, entry: _Entry) -> None:
        """Push this schedule's status to any open web UI.

        Without it the panel shows whatever was true when the page was opened,
        which is worse than showing nothing: it looks current.
        """
        bus = getattr(self._manager, "event_bus", None)
        trigger = getattr(bus, "trigger_event", None)
        if trigger is None:
            return
        with contextlib.suppress(Exception):
            from boneio.models.events import ScheduleEvent
            from boneio.models.state import ScheduleState

            status = self.status_for(entry.id)
            if status is None:
                return
            trigger(
                ScheduleEvent(
                    entity_id=entry.id, state=ScheduleState.model_validate(status)
                )
            )

    # ── control ──────────────────────────────────────────────────────────

    def set_enabled(self, schedule_id: str, enabled: bool) -> bool:
        """Turn one schedule on or off at runtime.

        This is what both the web UI and the Home Assistant switch call. The
        change is persisted, so it survives a restart; see :meth:`_restore` for
        what happens when the config disagrees afterwards.

        Args:
            schedule_id: The schedule's id.
            enabled: The new state.

        Returns:
            True if a schedule with that id exists, False otherwise.
        """
        entry = next((e for e in self._entries if e.id == schedule_id), None)
        if entry is None:
            return False
        if not entry.actions and enabled:
            _LOGGER.warning(
                "Schedule '%s' has no usable actions; leaving it off.", schedule_id
            )
            return True
        if entry.enabled == enabled:
            return True

        entry.enabled = enabled
        _LOGGER.info("Schedule '%s' %s.", schedule_id, "enabled" if enabled else "disabled")
        if not enabled:
            entry.disarm()
        elif self._running:
            self._plan()
        self._persist(entry)
        self._announce(entry)
        self._notify_panel(entry)
        return True

    async def reload(self, schedules: list[dict] | None) -> None:
        """Adopt a new ``schedule:`` section, disarming the old one first."""
        for entry in self._entries:
            entry.disarm()
        self._load(schedules or [])
        self._skipped_today.clear()
        if self._running:
            self._plan()
            self.publish_discovery()
            self.announce_all()

    # ── lifecycle ────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Arm the schedules and keep them armed.

        Catch-up runs here and only here: a schedule due while the device was
        off is a startup question, and re-asking it every minute would fire it
        repeatedly.
        """
        if self._running:
            return
        self._running = True
        if not self._entries:
            return
        self._catch_up()
        self._plan()
        self.publish_discovery()
        self.announce_all()
        self._task = self._manager.append_task(coro=self._supervise, name="scheduler")

    def stop(self) -> None:
        """Disarm everything and stop supervising."""
        self._running = False
        for entry in self._entries:
            entry.disarm()
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _supervise(self) -> None:
        """Re-plan from the current wall clock, forever.

        Rebuilding every minute is what makes this survive the clock being
        stepped by NTP, a schedule whose day has ticked over, and a timer that
        fired while the loop was busy.
        """
        try:
            while self._running:
                await asyncio.sleep(_SUPERVISE_INTERVAL)
                try:
                    self._plan()
                except Exception as err:  # noqa: BLE001 - never kill the supervisor
                    _LOGGER.error("Scheduler planning failed: %s", err, exc_info=True)
        except asyncio.CancelledError:
            raise

    # ── planning ─────────────────────────────────────────────────────────

    def _clock_ready(self, now: datetime) -> bool:
        """Whether the system clock is plausible enough to schedule against.

        Also the place the clock being *set* is noticed. The board has no
        battery-backed RTC, so it boots in the year 2000 and stays there until
        NTP answers — which needs the network up first, and on a site where the
        NTP server is a minute behind the switch, that can be well after boot.
        When the step finally lands, every cached sun anchor was computed
        against a date that never happened, so they go.

        The timers themselves need no help here: the plan is rebuilt from the
        wall clock every minute anyway, which is what that interval is for.
        """
        if self._manager.sun.clock_ready(now):
            if self._warned_clock:
                self._warned_clock = False
                _LOGGER.info(
                    "System clock is set (%s); recomputing sun times and arming "
                    "schedules.",
                    now.isoformat(timespec="seconds"),
                )
                self._manager.sun.invalidate()
            return True
        if not self._warned_clock:
            self._warned_clock = True
            _LOGGER.warning(
                "System clock is not set yet; no schedule is armed. They come up "
                "once NTP synchronises."
            )
        return False

    def _plan(self) -> None:
        """Make each enabled schedule's armed timer match its next firing."""
        now = datetime.now().astimezone()
        if not self._clock_ready(now):
            return

        for entry in self._entries:
            if not entry.enabled:
                entry.disarm()
                continue

            try:
                when = self._next_fire(entry, now)
            except Exception as err:  # noqa: BLE001 - one bad entry, not all
                entry.last_error = str(err)
                _LOGGER.error("Schedule '%s': cannot compute next firing: %s", entry.id, err)
                entry.disarm()
                continue

            if when is None:
                if entry.id not in self._skipped_today:
                    self._skipped_today.add(entry.id)
                    _LOGGER.warning(
                        "Schedule '%s' has no firing in the next %d days — the Sun "
                        "may not reach that angle at this latitude.",
                        entry.id,
                        _MAX_LOOKAHEAD_DAYS,
                    )
                entry.disarm()
                continue

            self._skipped_today.discard(entry.id)
            if entry.next_fire is not None and abs((entry.next_fire - when).total_seconds()) < 1:
                continue  # already armed for this instant

            entry.disarm()
            entry.next_fire = when
            entry.cancel = async_track_point_in_time(
                loop=self._manager.loop,
                job=self._fire,
                point_in_time=when,
                entry_id=entry.id,
            )
            _LOGGER.debug("Schedule '%s' armed for %s", entry.id, when.isoformat())
            # The "next firing" sensor in Home Assistant is only worth having
            # if it moves when the plan does, and the panel shows the same
            # value from the same place.
            self._announce(entry)
            self._notify_panel(entry)

    def _next_fire(self, entry: _Entry, now: datetime) -> datetime | None:
        """The next instant this schedule should fire, or None if not soon.

        Args:
            entry: The schedule.
            now: Aware current time.

        Returns:
            An aware datetime strictly after *now*, or None.
        """
        for offset_days in range(_MAX_LOOKAHEAD_DAYS):
            when = self._fire_time_on(entry, (now + timedelta(days=offset_days)).date(), now)
            if when is not None and when > now:
                return when
        return None

    def _fire_time_on(self, entry: _Entry, day, now: datetime) -> datetime | None:
        """This schedule's firing on one local date, or None if it has none."""
        provider = self._manager.sun
        tz = provider.timezone if provider.configured else now.tzinfo

        trigger = entry.trigger
        if trigger.get("type", "sun") == "time":
            at = trigger.get("at") or "00:00"
            hour, minute = (int(part) for part in at.split(":", 1))
            base = _local_instant(day, dt_time(hour, minute), tz)
        else:
            if not provider.configured:
                raise ValueError(
                    "a sun trigger needs the location: section, which is not configured"
                )
            anchors = provider._anchors_for(day)  # noqa: SLF001 - same package
            base = anchors.get(trigger.get("event", ""))
            if base is None:
                return None

        # The day filter applies to the *local day the firing lands on*, so an
        # offset that pushes past midnight counts as the day it happens on —
        # which is what someone reading "weekdays" expects.
        when = base + timedelta(seconds=float(trigger.get("offset") or 0.0))
        when = _clamp_to_window(when, trigger, tz)
        if when.astimezone(tz).weekday() not in entry.days:
            return None

        jitter = float(trigger.get("jitter") or 0.0)
        if jitter > 0:
            # Drawn per firing, deterministically per (schedule, day) so that
            # re-planning the same firing does not walk the time forwards.
            rng = random.Random(f"{entry.id}:{day.isoformat()}")
            when = when + timedelta(seconds=rng.uniform(0, jitter))
        return when

    # ── firing ───────────────────────────────────────────────────────────

    def _catch_up(self) -> None:
        """Run schedules that were due while the device was off.

        Only those that asked for it, and only within their own window. A
        controller that was off all day must not close the covers at breakfast.
        """
        now = datetime.now().astimezone()
        if not self._clock_ready(now):
            return

        for entry in self._entries:
            if not entry.enabled or entry.on_missed != "run" or entry.catch_up <= 0:
                continue
            try:
                previous = self._previous_fire(entry, now)
            except Exception:  # noqa: BLE001
                continue
            if previous is None:
                continue
            missed_by = (now - previous).total_seconds()
            if 0 <= missed_by <= entry.catch_up:
                _LOGGER.info(
                    "Schedule '%s' was due %.0fs ago and asked to catch up; running it.",
                    entry.id,
                    missed_by,
                )
                self._manager.loop.create_task(self._run(entry, source=SOURCE_CATCH_UP))

    def _previous_fire(self, entry: _Entry, now: datetime) -> datetime | None:
        """The most recent firing at or before *now*, within the catch-up window."""
        # Only today and yesterday can be inside a window capped at six hours.
        for offset_days in (0, 1):
            when = self._fire_time_on(entry, (now - timedelta(days=offset_days)).date(), now)
            if when is not None and when <= now:
                return when
        return None

    async def _fire(self, _point_in_time: datetime, entry_id: str) -> None:
        """Timer callback: run the schedule and arm the next one."""
        entry = next((e for e in self._entries if e.id == entry_id), None)
        if entry is None:
            return
        entry.cancel = None
        entry.next_fire = None
        await self._run(entry)
        self._plan()

    async def _run(self, entry: _Entry, source: str = SOURCE_TIMER) -> None:
        """Check the schedule's own conditions and execute its actions.

        Every exit from here is recorded, including the one where the condition
        says no. Without that, "it did not run" and "it ran and correctly chose
        to do nothing" are the same observation from outside, which is the
        thing that makes a schedule impossible to trust.
        """
        now = datetime.now().astimezone()
        started = _time.monotonic()

        def elapsed_ms() -> int:
            return int((_time.monotonic() - started) * 1000)

        if entry.condition is not None and not should_execute_action(
            entry.condition, now, self._manager._resolve_entity_state
        ):
            _LOGGER.info("Schedule '%s': conditions not met, nothing run.", entry.name)
            self._record(entry, now, source, OUTCOME_SKIPPED, elapsed_ms(), None)
            return

        _LOGGER.info(
            "Schedule '%s' firing%s (%d action(s)).",
            entry.name,
            "" if source == SOURCE_TIMER else f" ({source.replace('_', '-')})",
            len(entry.actions),
        )
        try:
            await self._manager.execute_actions(entry.actions)
        except Exception as err:  # noqa: BLE001 - one schedule must not stop the rest
            _LOGGER.error("Schedule '%s' failed: %s", entry.id, err, exc_info=True)
            self._record(entry, now, source, OUTCOME_FAILED, elapsed_ms(), str(err))
        else:
            self._record(entry, now, source, OUTCOME_RAN, elapsed_ms(), None)

    def _record(
        self,
        entry: _Entry,
        at: datetime,
        source: str,
        outcome: str,
        duration_ms: int,
        error: str | None,
    ) -> None:
        """Note what one run came to, in memory and on disk.

        Nothing is written to disk before the clock is set. The board boots in
        1970 and a manual run from the web UI can happen in that window; a
        history full of timestamps from a year that never happened is worse
        than a history with a gap.
        """
        entry.last_fire = at
        entry.last_outcome = outcome
        entry.last_error = error
        entry.last_duration_ms = duration_ms

        record = {
            "at": at.isoformat(),
            "source": source,
            "outcome": outcome,
            "actions": len(entry.actions),
            "duration_ms": duration_ms,
            "error": error,
        }
        entry.history.append(record)

        if self._manager.sun.clock_ready(at):
            self._persist(entry)
        else:
            _LOGGER.debug(
                "Schedule '%s': clock not set, keeping this run in memory only.",
                entry.id,
            )
        self._announce(entry)
        self._notify_panel(entry)

    # ── introspection ────────────────────────────────────────────────────

    def status(self) -> list[dict]:
        """What the panel shows: what is armed, when it next fires, and what
        happened the last times it did.

        Note ``last_fire``: it is when the timer last fired, whatever came of
        it. Until 1.6.x it was set only when the conditions passed, which made
        a schedule blocked by its own condition indistinguishable from one that
        never ran.
        """
        return [
            {
                "id": entry.id,
                "name": entry.name,
                "enabled": entry.enabled,
                "config_enabled": entry.config_enabled,
                "trigger": dict(entry.trigger),
                "actions": len(entry.actions),
                "next_fire": entry.next_fire.isoformat() if entry.next_fire else None,
                "last_fire": entry.last_fire.isoformat() if entry.last_fire else None,
                "last_outcome": entry.last_outcome,
                "last_error": entry.last_error,
                "last_duration_ms": entry.last_duration_ms,
                "history": list(entry.history),
            }
            for entry in self._entries
        ]

    def status_for(self, schedule_id: str) -> dict | None:
        """One schedule's status, or None when there is no such schedule."""
        return next((s for s in self.status() if s["id"] == schedule_id), None)
