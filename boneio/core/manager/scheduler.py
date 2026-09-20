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
from datetime import datetime, timedelta
from datetime import time as dt_time
from typing import TYPE_CHECKING, Any

from boneio.core.events.bus import async_track_point_in_time
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
        return datetime.combine(local.date(), dt_time(hour, minute), tzinfo=tz)

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
        "trigger",
        "on_missed",
        "catch_up",
        "actions",
        "condition",
        "cancel",
        "next_fire",
        "last_fire",
        "last_error",
    )

    def __init__(self, config: dict, index: int) -> None:
        self.id = config.get("id") or f"schedule_{index + 1}"
        self.name = config.get("name") or self.id
        self.enabled = config.get("enabled", True)
        self.trigger = config.get("trigger") or {}
        self.on_missed = config.get("on_missed", "skip")
        self.catch_up = float(config.get("catch_up") or 0.0)
        self.actions: list[dict] = []
        self.condition: Any = None
        self.cancel: Any = None
        self.next_fire: datetime | None = None
        self.last_fire: datetime | None = None
        self.last_error: str | None = None

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
            if not entry.actions:
                _LOGGER.warning(
                    "Schedule '%s' has no usable actions; it will not be armed.", entry.id
                )
                entry.enabled = False
            entry.condition = precompile_conditions(config, self._manager.sun)
            self._entries.append(entry)

        if self._entries:
            _LOGGER.info(
                "Loaded %d schedule(s): %s",
                len(self._entries),
                [e.id for e in self._entries],
            )

    async def reload(self, schedules: list[dict] | None) -> None:
        """Adopt a new ``schedule:`` section, disarming the old one first."""
        for entry in self._entries:
            entry.disarm()
        self._load(schedules or [])
        self._skipped_today.clear()
        if self._running:
            self._plan()

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
            base = datetime.combine(day, dt_time(hour, minute), tzinfo=tz)
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
                self._manager.loop.create_task(self._run(entry, catching_up=True))

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

    async def _run(self, entry: _Entry, catching_up: bool = False) -> None:
        """Check the schedule's own conditions and execute its actions."""
        now = datetime.now().astimezone()

        if entry.condition is not None and not should_execute_action(
            entry.condition, now, self._manager._resolve_entity_state
        ):
            _LOGGER.info("Schedule '%s': conditions not met, nothing run.", entry.name)
            return

        _LOGGER.info(
            "Schedule '%s' firing%s (%d action(s)).",
            entry.name,
            " (catch-up)" if catching_up else "",
            len(entry.actions),
        )
        entry.last_fire = now
        try:
            await self._manager.execute_actions(entry.actions)
            entry.last_error = None
        except Exception as err:  # noqa: BLE001 - one schedule must not stop the rest
            entry.last_error = str(err)
            _LOGGER.error("Schedule '%s' failed: %s", entry.id, err, exc_info=True)

    # ── introspection ────────────────────────────────────────────────────

    def status(self) -> list[dict]:
        """What the panel shows: what is armed, and when it next fires."""
        return [
            {
                "id": entry.id,
                "name": entry.name,
                "enabled": entry.enabled,
                "trigger": dict(entry.trigger),
                "actions": len(entry.actions),
                "next_fire": entry.next_fire.isoformat() if entry.next_fire else None,
                "last_fire": entry.last_fire.isoformat() if entry.last_fire else None,
                "last_error": entry.last_error,
            }
            for entry in self._entries
        ]
