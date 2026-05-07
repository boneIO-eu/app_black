"""Action condition evaluation for boneIO.

Provides fast condition checking for the action execution pipeline.
Pre-parses conditions at config load time to avoid repeated dict lookups
and string parsing at button-press time.

Optimisations over the generic conditions.py:
  - datetime.now() is called ONCE per execute_actions() batch
  - time/date strings are parsed once (at config load) rather than each press
  - state_resolver results can be cached within an evaluation cycle
  - dedicated logger `boneio.action_conditions` for easy filtering

Usage:
    from boneio.core.manager.action_conditions import (
        precompile_conditions,
        should_execute_action,
    )
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from datetime import time as dt_time
from typing import Any

_LOGGER = logging.getLogger("boneio.action_conditions")


# ── Pre-compiled condition types ──────────────────────────────────────────

class _TimeCondition:
    """Pre-parsed time condition for fast evaluation."""

    __slots__ = ("after", "before", "crosses_midnight")

    def __init__(self, after: dt_time | None, before: dt_time | None) -> None:
        self.after = after
        self.before = before
        self.crosses_midnight = (
            after is not None
            and before is not None
            and after > before
        )

    def evaluate(self, now: datetime) -> bool:
        """Check if *now* satisfies this time window."""
        current = now.time()
        if self.after and self.before:
            if self.crosses_midnight:
                return current >= self.after or current < self.before
            return self.after <= current < self.before
        if self.after:
            return current >= self.after
        if self.before:
            return current < self.before
        return True  # no bounds


class _DateCondition:
    """Pre-parsed date condition for fast evaluation."""

    __slots__ = ("after", "before", "crosses_year")

    def __init__(
        self,
        after: tuple[int, int] | None,
        before: tuple[int, int] | None,
    ) -> None:
        self.after = after
        self.before = before
        self.crosses_year = (
            after is not None
            and before is not None
            and after > before
        )

    def evaluate(self, now: datetime) -> bool:
        """Check if *now* satisfies this date window."""
        current = (now.month, now.day)
        if self.after and self.before:
            if self.crosses_year:
                return current >= self.after or current <= self.before
            return self.after <= current <= self.before
        if self.after:
            return current >= self.after
        if self.before:
            return current <= self.before
        return True


class _StateCondition:
    """Pre-parsed state condition with compile-time resolved evaluator.
    
    Instead of doing a chain of getattr() calls on every button press,
    we resolve the correct property to check once at config-load time
    and store a tiny evaluator function.
    """

    __slots__ = ("entity_type", "entity_id", "_check")

    def __init__(self, entity_type: str, entity_id: str, expected_state: str) -> None:
        self.entity_type = entity_type
        self.entity_id = entity_id
        # Resolve evaluator at compile-time based on entity_type + expected_state
        self._check = _STATE_EVALUATORS.get(
            (entity_type, expected_state),
            _STATE_EVALUATORS.get(("_any", expected_state)),
        )
        if self._check is None:
            _LOGGER.error(
                "No evaluator for entity_type=%s, expected_state=%s",
                entity_type, expected_state,
            )

    def evaluate(
        self,
        state_resolver: Callable[[str, str], Any] | None,
    ) -> bool:
        """Resolve entity and compare state — single property read."""
        if state_resolver is None or self._check is None:
            return True

        entity = state_resolver(self.entity_type, self.entity_id)
        if entity is None:
            _LOGGER.warning(
                "Entity %s/%s not found, allowing action",
                self.entity_type, self.entity_id,
            )
            return True

        return self._check(entity)


# ── Compile-time evaluator functions (one direct attribute read each) ────

def _check_is_active(entity: Any) -> bool:
    """output/light/binary_sensor: entity.is_active == True"""
    return entity.is_active

def _check_is_not_active(entity: Any) -> bool:
    """output/light/binary_sensor: entity.is_active == False"""
    return not entity.is_active

def _check_is_open(entity: Any) -> bool:
    """cover: entity.is_open == True"""
    return entity.is_open

def _check_is_closed(entity: Any) -> bool:
    """cover: entity.is_open == False"""
    return not entity.is_open


# Mapping: (entity_type, expected_state) → evaluator function
# "_any" is a fallback for entity types that share the same property
_STATE_EVALUATORS: dict[tuple[str, str], Callable[[Any], bool]] = {
    # output / light → is_active
    ("output", "is_on"): _check_is_active,
    ("output", "is_off"): _check_is_not_active,
    ("light", "is_on"): _check_is_active,
    ("light", "is_off"): _check_is_not_active,
    # binary_sensor → is_active
    ("binary_sensor", "is_on"): _check_is_active,
    ("binary_sensor", "is_off"): _check_is_not_active,
    # cover → is_open
    ("cover", "is_open"): _check_is_open,
    ("cover", "is_closed"): _check_is_closed,
    ("cover", "is_on"): _check_is_open,    # alias: is_on ≡ is_open for covers
    ("cover", "is_off"): _check_is_closed,  # alias: is_off ≡ is_closed for covers
}


# Pre-compiled "group of conditions" (AND / OR list)
class _ConditionGroup:
    """A compiled group of conditions with mode (and/or)."""

    __slots__ = ("items", "use_all")

    def __init__(
        self,
        items: list[_TimeCondition | _DateCondition | _StateCondition],
        use_all: bool,
    ) -> None:
        self.items = items
        self.use_all = use_all  # True = AND, False = OR

    def evaluate(
        self,
        now: datetime,
        state_resolver: Callable[[str, str], Any] | None,
    ) -> bool:
        """Evaluate all items with AND/OR logic."""
        if not self.items:
            return True

        if self.use_all:
            return all(_eval_single(item, now, state_resolver) for item in self.items)
        # OR mode
        return any(_eval_single(item, now, state_resolver) for item in self.items)


def _eval_single(
    cond: _TimeCondition | _DateCondition | _StateCondition,
    now: datetime,
    state_resolver: Callable[[str, str], Any] | None,
) -> bool:
    """Evaluate a single pre-compiled condition."""
    if isinstance(cond, _TimeCondition):
        return cond.evaluate(now)
    if isinstance(cond, _DateCondition):
        return cond.evaluate(now)
    if isinstance(cond, _StateCondition):
        return cond.evaluate(state_resolver)
    return True


# ── Parsing helpers ───────────────────────────────────────────────────────

def _parse_time(s: str) -> dt_time:
    """Parse HH:MM or HH:MM:SS."""
    parts = s.strip().split(":")
    if len(parts) == 2:
        return dt_time(int(parts[0]), int(parts[1]))
    if len(parts) == 3:
        return dt_time(int(parts[0]), int(parts[1]), int(parts[2]))
    raise ValueError(f"Invalid time format: '{s}'")


def _parse_date(s: str) -> tuple[int, int]:
    """Parse MM-DD."""
    parts = s.strip().split("-")
    if len(parts) == 2:
        m, d = int(parts[0]), int(parts[1])
        if 1 <= m <= 12 and 1 <= d <= 31:
            return (m, d)
    raise ValueError(f"Invalid date format: '{s}'")


def _compile_single(raw: dict) -> _TimeCondition | _DateCondition | _StateCondition | None:
    """Compile a single condition dict into a fast evaluator.

    Returns None if the condition is invalid (logs a warning).
    """
    ctype = raw.get("type")
    try:
        if ctype == "time":
            after = _parse_time(raw["after"]) if raw.get("after") else None
            before = _parse_time(raw["before"]) if raw.get("before") else None
            return _TimeCondition(after, before)
        if ctype == "date":
            after = _parse_date(raw["after"]) if raw.get("after") else None
            before = _parse_date(raw["before"]) if raw.get("before") else None
            return _DateCondition(after, before)
        if ctype == "state":
            et = raw.get("entity")
            eid = raw.get("entity_id")
            es = raw.get("state")
            if et and eid and es:
                return _StateCondition(et, eid, es)
            _LOGGER.error("State condition missing fields: %s", raw)
            return None
    except (ValueError, KeyError) as exc:
        _LOGGER.error("Failed to compile condition %s: %s", raw, exc)
        return None

    _LOGGER.error("Unknown condition type: %s", ctype)
    return None


# ── Public API ────────────────────────────────────────────────────────────

def precompile_conditions(
    action_definition: dict,
) -> _ConditionGroup | _TimeCondition | _DateCondition | _StateCondition | None:
    """Pre-compile conditions from a parsed action definition.

    Call this once (at config load / parse_actions time) and store the
    result on the action_definition dict as ``_compiled_conditions``.

    Args:
        action_definition: A single action dict that may contain
            ``condition`` (single) or ``conditions`` (group).

    Returns:
        A compiled condition object, or None if there are no conditions.
    """
    single = action_definition.get("condition")
    multi = action_definition.get("conditions")

    if single:
        return _compile_single(single)

    if multi:
        mode = multi.get("mode", "and")
        cond_list = multi.get("list", [])
        if not cond_list:
            return None
        compiled = []
        for raw in cond_list:
            item = _compile_single(raw)
            if item is not None:
                compiled.append(item)
        if not compiled:
            return None
        return _ConditionGroup(compiled, use_all=(mode == "and"))

    return None


def should_execute_action(
    compiled_condition: _ConditionGroup
    | _TimeCondition
    | _DateCondition
    | _StateCondition
    | None,
    now: datetime,
    state_resolver: Callable[[str, str], Any] | None = None,
) -> bool:
    """Check whether an action's conditions are satisfied.

    This is the hot-path function called on every button press.
    It receives a pre-compiled condition and a *single* ``now``
    timestamp shared across all actions in the batch.

    Args:
        compiled_condition: Output of ``precompile_conditions``, or None.
        now: The current datetime (compute once per ``execute_actions``).
        state_resolver: Callback ``(entity_type, entity_id) -> entity``.

    Returns:
        True if the action should execute.
    """
    if compiled_condition is None:
        return True

    if isinstance(compiled_condition, _ConditionGroup):
        result = compiled_condition.evaluate(now, state_resolver)
    else:
        result = _eval_single(compiled_condition, now, state_resolver)

    if not result:
        _LOGGER.debug("Condition not met: %s", compiled_condition)

    return result
