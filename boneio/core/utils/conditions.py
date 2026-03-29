"""Conditional action execution logic.

Provides condition evaluation for boneIO action system.
Supports three condition types:
  - time: Check if current time is within a range (HH:MM, midnight crossover)
  - date: Check if current date is within a range (MM-DD, new year crossover)
  - state: Check if a boneIO entity is in a specific state

Multiple conditions can be combined with AND/OR logic.

Example usage:
    >>> from boneio.core.utils.conditions import evaluate_conditions
    >>> condition = {"type": "time", "after": "05:00", "before": "22:00"}
    >>> evaluate_conditions(condition=condition)
    True
"""

from __future__ import annotations

import logging
from datetime import datetime, time, date
from typing import Any, Callable

_LOGGER = logging.getLogger(__name__)


def _parse_time(time_str: str) -> time:
    """Parse time string in HH:MM or HH:MM:SS format.
    
    Args:
        time_str: Time string (e.g., "05:00", "22:30", "06:00:30")
        
    Returns:
        datetime.time object
        
    Raises:
        ValueError: If format is invalid
    """
    parts = time_str.strip().split(":")
    if len(parts) == 2:
        return time(int(parts[0]), int(parts[1]))
    elif len(parts) == 3:
        return time(int(parts[0]), int(parts[1]), int(parts[2]))
    raise ValueError(f"Invalid time format: '{time_str}'. Expected HH:MM or HH:MM:SS")


def _parse_date(date_str: str) -> tuple[int, int]:
    """Parse date string in MM-DD format.
    
    Args:
        date_str: Date string (e.g., "11-01", "03-31")
        
    Returns:
        Tuple of (month, day)
        
    Raises:
        ValueError: If format is invalid
    """
    parts = date_str.strip().split("-")
    if len(parts) == 2:
        month, day = int(parts[0]), int(parts[1])
        if 1 <= month <= 12 and 1 <= day <= 31:
            return (month, day)
    raise ValueError(f"Invalid date format: '{date_str}'. Expected MM-DD (e.g., 11-01)")


def _check_time_condition(condition: dict, now: datetime | None = None) -> bool:
    """Check if current time is within the specified range.
    
    Supports midnight crossover: after="22:00" before="06:00" means 22:00-05:59.
    If only 'after' is specified, checks if current time >= after.
    If only 'before' is specified, checks if current time < before.
    
    Args:
        condition: Dict with 'after' and/or 'before' keys (HH:MM format)
        now: Optional datetime for testing (default: datetime.now())
        
    Returns:
        True if current time satisfies the condition
    """
    if now is None:
        now = datetime.now()
    current_time = now.time()
    
    after_str = condition.get("after")
    before_str = condition.get("before")
    
    if not after_str and not before_str:
        _LOGGER.warning("Time condition has neither 'after' nor 'before' — always true")
        return True
    
    try:
        after_time = _parse_time(after_str) if after_str else None
        before_time = _parse_time(before_str) if before_str else None
    except ValueError as e:
        _LOGGER.error("Invalid time condition: %s", e)
        return True  # Don't block action on config error
    
    if after_time and before_time:
        if after_time <= before_time:
            # Normal range: e.g., 05:00 - 22:00
            result = after_time <= current_time < before_time
        else:
            # Midnight crossover: e.g., 22:00 - 06:00
            result = current_time >= after_time or current_time < before_time
    elif after_time:
        result = current_time >= after_time
    else:
        result = current_time < before_time
    
    _LOGGER.debug(
        "Time condition: after=%s, before=%s, current=%s → %s",
        after_str, before_str, current_time.strftime("%H:%M:%S"), result
    )
    return result


def _check_date_condition(condition: dict, now: datetime | None = None) -> bool:
    """Check if current date is within the specified range.
    
    Supports new year crossover: after="11-01" before="03-31" means Nov 1 - Mar 31.
    If only 'after' is specified, checks if current date >= after.
    If only 'before' is specified, checks if current date <= before.
    
    Args:
        condition: Dict with 'after' and/or 'before' keys (MM-DD format)
        now: Optional datetime for testing (default: datetime.now())
        
    Returns:
        True if current date satisfies the condition
    """
    if now is None:
        now = datetime.now()
    current = (now.month, now.day)
    
    after_str = condition.get("after")
    before_str = condition.get("before")
    
    if not after_str and not before_str:
        _LOGGER.warning("Date condition has neither 'after' nor 'before' — always true")
        return True
    
    try:
        after_date = _parse_date(after_str) if after_str else None
        before_date = _parse_date(before_str) if before_str else None
    except ValueError as e:
        _LOGGER.error("Invalid date condition: %s", e)
        return True  # Don't block action on config error
    
    if after_date and before_date:
        if after_date <= before_date:
            # Normal range: e.g., 03-01 to 10-31
            result = after_date <= current <= before_date
        else:
            # New year crossover: e.g., 11-01 to 03-31
            result = current >= after_date or current <= before_date
    elif after_date:
        result = current >= after_date
    else:
        result = current <= before_date
    
    _LOGGER.debug(
        "Date condition: after=%s, before=%s, current=%02d-%02d → %s",
        after_str, before_str, current[0], current[1], result
    )
    return result


def _check_state_condition(
    condition: dict,
    state_resolver: Callable[[str, str], Any] | None = None,
) -> bool:
    """Check if a boneIO entity is in the expected state.
    
    Args:
        condition: Dict with 'entity', 'entity_id', and 'state' keys
        state_resolver: Callback to resolve entity state.
                       Signature: (entity_type: str, entity_id: str) -> entity object or None
        
    Returns:
        True if entity is in the expected state
    """
    entity_type = condition.get("entity")
    entity_id = condition.get("entity_id")
    expected_state = condition.get("state")
    
    if not entity_type or not entity_id or not expected_state:
        _LOGGER.error(
            "State condition missing required fields: entity=%s, entity_id=%s, state=%s",
            entity_type, entity_id, expected_state
        )
        return True  # Don't block action on config error
    
    if state_resolver is None:
        _LOGGER.error("State condition cannot be evaluated — no state_resolver provided")
        return True
    
    entity = state_resolver(entity_type, entity_id)
    if entity is None:
        _LOGGER.warning("Entity %s/%s not found for state condition", entity_type, entity_id)
        return True  # Entity not found — don't block
    
    # Resolve actual state based on expected_state keyword
    if expected_state == "is_on":
        result = getattr(entity, "is_active", None) or getattr(entity, "state", None) in ("ON", "on", True)
    elif expected_state == "is_off":
        is_active = getattr(entity, "is_active", None)
        if is_active is not None:
            result = not is_active
        else:
            result = getattr(entity, "state", None) in ("OFF", "off", False, None)
    elif expected_state == "is_open":
        result = getattr(entity, "is_open", None) is True
    elif expected_state == "is_closed":
        is_open = getattr(entity, "is_open", None)
        result = is_open is False if is_open is not None else False
    else:
        _LOGGER.error("Unknown state condition: %s", expected_state)
        return True
    
    _LOGGER.debug(
        "State condition: %s/%s expected=%s, actual=%s → %s",
        entity_type, entity_id, expected_state, 
        getattr(entity, "state", "?"), result
    )
    return result


def check_single_condition(
    condition: dict,
    state_resolver: Callable[[str, str], Any] | None = None,
    now: datetime | None = None,
) -> bool:
    """Evaluate a single condition.
    
    Args:
        condition: Condition dictionary with 'type' key
        state_resolver: Callback to resolve entity states
        now: Optional datetime override for testing
        
    Returns:
        True if condition is met
    """
    cond_type = condition.get("type")
    
    if cond_type == "time":
        return _check_time_condition(condition, now=now)
    elif cond_type == "date":
        return _check_date_condition(condition, now=now)
    elif cond_type == "state":
        return _check_state_condition(condition, state_resolver=state_resolver)
    else:
        _LOGGER.error("Unknown condition type: %s", cond_type)
        return True  # Don't block on unknown condition


def evaluate_conditions(
    condition: dict | None = None,
    conditions: dict | None = None,
    state_resolver: Callable[[str, str], Any] | None = None,
    now: datetime | None = None,
) -> bool:
    """Evaluate action conditions.
    
    Supports both single 'condition' and multiple 'conditions' with AND/OR logic.
    
    Args:
        condition: Single condition dict (mutually exclusive with conditions)
        conditions: Multiple conditions dict with 'mode' and 'list' keys
        state_resolver: Callback to resolve entity states for state conditions
        now: Optional datetime override for testing
        
    Returns:
        True if conditions are met (or no conditions specified)
    """
    # No conditions — always execute
    if not condition and not conditions:
        return True
    
    # Single condition
    if condition:
        return check_single_condition(condition, state_resolver=state_resolver, now=now)
    
    # Multiple conditions
    mode = conditions.get("mode", "and")
    cond_list = conditions.get("list", [])
    
    if not cond_list:
        return True
    
    if mode == "and":
        result = all(
            check_single_condition(c, state_resolver=state_resolver, now=now)
            for c in cond_list
        )
    elif mode == "or":
        result = any(
            check_single_condition(c, state_resolver=state_resolver, now=now)
            for c in cond_list
        )
    else:
        _LOGGER.error("Unknown conditions mode: %s (expected 'and' or 'or')", mode)
        return True
    
    _LOGGER.debug(
        "Conditions (mode=%s, count=%d) → %s",
        mode, len(cond_list), result
    )
    return result
