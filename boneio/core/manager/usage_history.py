"""How the house is used, by the hour, for an AI assistant to learn from.

Off unless ``usage_history.enabled``. When on, it counts per local day and
hour: an output switched on or off (and how long it stayed on), a cover
opening or closing, an input clicked. Nothing finer - no timestamps, no
sequence - and it stays on the controller in ``usage_history.json``,
written once an hour. Turning it off deletes the file: a log of when
somebody is at home is not something to keep by accident.

:meth:`UsageHistory.summary` folds the days into what a model can use in a
few hundred tokens: for each entity, how often, at which hours, on weekdays
and at weekends.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from boneio.const import CLOSING, COVER, NONE, ON, OPENING
from boneio.core.atomic_file import write_atomically

if TYPE_CHECKING:
    from boneio.core.manager import Manager

_LOGGER = logging.getLogger(__name__)

FILENAME = "usage_history.json"
_LISTENER = "usage_history"
_PERSIST_EVERY_S = 3600
#: Clicks worth counting; "pressed"/"released" of a binary sensor is a state,
#: and a contact that opens and closes would drown everything else.
_CLICKS = {"single", "double", "triple", "long", "double_then_long", "single_then_long", "double_then_single"}


class UsageHistory:
    """Counts usage while enabled, and summarises it."""

    def __init__(self, manager: Manager, path: Path) -> None:
        self._manager = manager
        self._path = path
        self.enabled = False
        self.days = 30
        # day -> entity key -> kind -> hour -> count
        self._data: dict[str, dict[str, dict[str, dict[str, int]]]] = {}
        self._names: dict[str, str] = {}
        self._on_since: dict[str, float] = {}
        self._last_output: dict[str, str] = {}
        self._last_cover: dict[str, str] = {}
        self._dirty = False
        self._task_started = False

    # ── configuration ────────────────────────────────────────────────────

    def configure(self, section: dict | None) -> None:
        """Adopt the ``usage_history`` section; start, or stop and forget."""
        section = section or {}
        enabled = bool(section.get("enabled", False))
        self.days = int(section.get("days", 30) or 30)
        bus = self._manager.event_bus
        if enabled and not self.enabled:
            self._load()
            for event_type in ("output", "cover", "input"):
                bus.add_event_listener(event_type=event_type, entity_id="", listener_id=_LISTENER,
                                       target=self._on_event)
            if not self._task_started:
                # Once per process: the loop and the shutdown write outlive an
                # off-and-on, and do nothing while off.
                self._task_started = True
                bus.add_sigterm_listener(self.persist)
                self._manager.append_task(coro=self._persist_loop, name=_LISTENER)
            _LOGGER.info("Usage history on, keeping %d days in %s", self.days, self._path)
        elif not enabled and self.enabled:
            bus.remove_event_listener(listener_id=_LISTENER)
            self._data, self._names, self._on_since = {}, {}, {}
            self._path.unlink(missing_ok=True)
            _LOGGER.info("Usage history off; what it had collected is deleted")
        self.enabled = enabled
        if enabled:
            self._prune()

    # ── recording ────────────────────────────────────────────────────────

    def _count(self, key: str, kind: str, when: datetime | None = None) -> None:
        when = when or datetime.now()
        day = self._data.setdefault(when.date().isoformat(), {})
        hours = day.setdefault(key, {}).setdefault(kind, {})
        hours[str(when.hour)] = hours.get(str(when.hour), 0) + 1
        self._dirty = True

    def _add_seconds(self, key: str, seconds: float) -> None:
        day = self._data.setdefault(date.today().isoformat(), {})
        entry = day.setdefault(key, {})
        entry["on_seconds"] = {"total": round(entry.get("on_seconds", {}).get("total", 0) + seconds)}
        self._dirty = True

    @staticmethod
    def _now_s() -> float:
        return time.time()

    def _on_event(self, event: Any) -> None:
        if not self.enabled:
            return
        state = getattr(event, "state", None)
        entity = getattr(event, "entity_id", "")
        if event.event_type == "output" and state is not None:
            if getattr(state, "type", None) in (COVER, NONE):
                return  # a cover's relays: the cover is counted instead
            key = f"output:{entity}"
            self._names[key] = state.name
            if self._last_output.get(entity) == state.state:
                return  # a republish, not a change
            self._last_output[entity] = state.state
            if state.state == ON:
                self._count(key, "on")
                self._on_since[entity] = self._now_s()
            else:
                self._count(key, "off")
                started = self._on_since.pop(entity, None)
                if started is not None:
                    self._add_seconds(key, self._now_s() - started)
        elif event.event_type == "cover" and state is not None:
            operation = state.current_operation
            key = f"cover:{entity}"
            self._names[key] = state.name
            if operation in (OPENING, CLOSING) and self._last_cover.get(entity) != operation:
                self._count(key, "open" if operation == OPENING else "close")
            self._last_cover[entity] = operation
        elif event.event_type == "input" and event.click_type in _CLICKS:
            key = f"input:{entity}"
            if state is not None:
                self._names[key] = state.name
            self._count(key, event.click_type)

    # ── storage ──────────────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            self._data, self._names = raw.get("days", {}), raw.get("names", {})
        except FileNotFoundError:
            self._data, self._names = {}, {}
        except (OSError, ValueError) as err:
            _LOGGER.warning("Cannot read %s, starting usage history afresh: %s", self._path, err)
            self._data, self._names = {}, {}

    def _prune(self) -> None:
        oldest = (date.today() - timedelta(days=self.days - 1)).isoformat()
        for day in [d for d in self._data if d < oldest]:
            del self._data[day]
            self._dirty = True

    def persist(self, *_: Any) -> None:
        """Write the counts, if anything changed. Called hourly and at shutdown."""
        if not (self.enabled and self._dirty):
            return
        self._prune()
        payload = json.dumps({"version": 1, "names": self._names, "days": self._data}, separators=(",", ":"))
        try:
            write_atomically(self._path, payload, mode=0o600)
            self._dirty = False
        except OSError as err:
            _LOGGER.warning("Could not write %s: %s", self._path, err)

    async def _persist_loop(self) -> None:
        while True:
            await asyncio.sleep(_PERSIST_EVERY_S)
            await asyncio.to_thread(self.persist)

    # ── summary ──────────────────────────────────────────────────────────

    def summary(self, days: int = 14) -> dict[str, Any]:
        """The last ``days`` folded per entity: counts, busiest hours, weekday or weekend."""
        if not self.enabled:
            return {"enabled": False}
        oldest = (date.today() - timedelta(days=days - 1)).isoformat()
        chosen = sorted(d for d in self._data if d >= oldest)
        totals: dict[str, dict[str, dict[str, Counter]]] = defaultdict(
            lambda: defaultdict(lambda: {"weekday": Counter(), "weekend": Counter()})
        )
        on_seconds: Counter = Counter()
        on_days: dict[str, set[str]] = defaultdict(set)
        for day in chosen:
            part = "weekend" if date.fromisoformat(day).weekday() >= 5 else "weekday"
            for key, kinds in self._data[day].items():
                for kind, hours in kinds.items():
                    if kind == "on_seconds":
                        on_seconds[key] += hours.get("total", 0)
                        continue
                    totals[key][kind][part].update({int(h): n for h, n in hours.items()})
                    if kind == "on":
                        on_days[key].add(day)

        entities = []
        for key in sorted(totals):
            kind_of, entity_id = key.split(":", 1)
            entry: dict[str, Any] = {"type": kind_of, "id": entity_id, "name": self._names.get(key, entity_id)}
            for kind, parts in totals[key].items():
                described = {}
                for part, hours in parts.items():
                    if hours:
                        described[part] = {
                            "count": sum(hours.values()),
                            "busiest_hours": [h for h, _ in hours.most_common(3)],
                        }
                entry[kind] = described
            if on_seconds[key] and on_days[key]:
                switched_on = sum(sum(p.values()) for p in totals[key]["on"].values()) or 1
                entry["average_on_minutes"] = round(on_seconds[key] / switched_on / 60, 1)
            entities.append(entry)
        return {
            "enabled": True,
            "days": len(chosen),
            "from": chosen[0] if chosen else None,
            "to": chosen[-1] if chosen else None,
            "hours_are": "local time, 0-23; counts are summed over the days",
            "entities": entities,
        }
