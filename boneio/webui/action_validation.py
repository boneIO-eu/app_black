"""Action field validation helpers for WebUI config routes.

Standalone module (no FastAPI / router dependencies) so it can be imported
in unit tests without triggering python-multipart or other optional deps.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

_LOGGER = logging.getLogger(__name__)

# Fields allowed per action type. When an action is saved, only these fields
# (plus SHARED_FIELDS) are valid. Mirrors frontend ActionFields/helpers.ts.
ACTION_ALLOWED_FIELDS: dict[str, set[str]] = {
    "output": {"boneio_output", "action_output"},
    "cover": {"boneio_cover", "action_cover", "data", "restore_tilt"},
    "mqtt": {"topic", "action_mqtt_msg"},
    # Sets a flag that conditions read. Offered by the input editor since
    # virtual switches landed, but missing here, so saving an input that used
    # it was refused as an unknown action type.
    "virtual_switch": {"boneio_virtual_switch", "action_output"},
    "output_over_mqtt": {"boneio_id", "boneio_output", "action_output", "action_mqtt_msg"},
    "cover_over_mqtt": {"boneio_id", "boneio_cover", "action_cover", "action_mqtt_msg"},
    "remote_output": {
        "remote_device", "output_id", "action_output",
        "brightness","brightness_step", "color_temp", "rgb", "transition",
        "effect", "palette", "effect_speed", "effect_intensity",
        "colors", "presets",
    },
    "remote_cover": {"remote_device", "cover_id", "action_cover", "data", "restore_tilt"},
}

SHARED_FIELDS: set[str] = {
    "action", "min_duration", "max_duration", "repeat", "repeat_interval",
    "condition", "conditions", "delay", "delay_cancel_on",
}

_EVENT_CLICK_TYPES = (
    "single", "double", "triple", "long",
    "double_then_long", "single_then_long", "double_then_single",
)
_BINARY_SENSOR_CLICK_TYPES = ("pressed", "released")


def clean_action_fields(action: dict) -> list[str]:
    """Remove fields from an action that don't belong to its action type.

    Mutates the action dict in place. Also strips empty/falsy condition
    and conditions fields.

    Args:
        action: Action dictionary to clean.

    Returns:
        List of removed field names (empty if no cleanup was needed).
    """
    action_type = (action.get("action") or "").lower()
    if not action_type:
        return []

    allowed = ACTION_ALLOWED_FIELDS.get(action_type)
    if allowed is None:
        return []

    valid_keys = SHARED_FIELDS | allowed
    removed: list[str] = []
    for key in list(action.keys()):
        if key not in valid_keys:
            del action[key]
            removed.append(key)

    # Strip empty/falsy condition fields so they don't pollute the YAML
    if "condition" in action and not action["condition"]:
        del action["condition"]
        if "condition" not in removed:
            removed.append("condition")
    if "conditions" in action:
        cond = action["conditions"]
        if not cond or (isinstance(cond, dict) and not cond.get("list")):
            del action["conditions"]
            if "conditions" not in removed:
                removed.append("conditions")

    return removed


def validate_action_fields(action: dict) -> str | None:
    """Validate that an action object does not mix fields from different action types.

    Args:
        action: Action dictionary as stored in config.

    Returns:
        Error message string if invalid, None if valid.
    """
    action_type = (action.get("action") or "").lower()
    if not action_type:
        return "Action missing 'action' field."

    allowed = ACTION_ALLOWED_FIELDS.get(action_type)
    if allowed is None:
        return f"Unknown action type: '{action_type}'."

    valid_keys = SHARED_FIELDS | allowed
    stale_keys = [k for k in action if k not in valid_keys]
    if stale_keys:
        return (
            f"Action '{action_type}' contains fields not allowed for this type: "
            f"{stale_keys}. Remove them or switch to the correct action type."
        )
    return None


def _get_conditions_from_action(action: dict) -> list[dict]:
    """Extract all condition dicts from an action.

    Args:
        action: Action dictionary.

    Returns:
        List of condition dicts (may be empty).
    """
    conditions: list[dict] = []
    if action.get("condition") and isinstance(action["condition"], dict):
        conditions.append(action["condition"])
    if action.get("conditions") and isinstance(action["conditions"], dict):
        for c in action["conditions"].get("list") or []:
            if isinstance(c, dict):
                conditions.append(c)
    return conditions


def _check_condition_self_reference(
    entity: dict, action: dict, section: str
) -> str | None:
    """Check if a condition references the entity's own binary_sensor state.

    Self-referencing conditions would create infinite loops (e.g. IN_48
    checking whether IN_48 is_on before executing its own action).

    Only applies to binary_sensor section entities.

    Args:
        entity: The entity dict containing the action.
        action: The action dict to check.
        section: Config section name.

    Returns:
        Error message if self-reference found, None otherwise.
    """
    if section != "binary_sensor":
        return None

    entity_input = entity.get("boneio_input", "")
    if not entity_input:
        return None

    for cond in _get_conditions_from_action(action):
        if cond.get("type") != "state":
            continue
        if cond.get("entity") != "binary_sensor":
            continue
        cond_entity_id = cond.get("entity_id", "")
        if cond_entity_id and cond_entity_id == entity_input:
            return (
                f"Self-referencing condition: binary_sensor '{entity_input}' "
                f"cannot check its own state (would cause an infinite loop)."
            )
    return None


def _check_sun_condition(action: dict, has_location: bool | None) -> str | None:
    """Check a sun condition's shape, and that the device knows where it is.

    A sun condition without a ``location:`` section is the worst kind of
    misconfiguration: at runtime it fails open, so the action keeps firing and
    the operator sees a feature that appears to work and never actually gates
    anything. Catching it at save time is the only place it is obvious.

    Args:
        action: The action dict to check.
        has_location: Whether the config has coordinates. None skips that part
            of the check (the caller could not tell).

    Returns:
        An error message, or None when the conditions are fine.
    """
    from boneio.core.utils.sun import ANCHOR_NAMES, PHASE_NAMES

    for cond in _get_conditions_from_action(action):
        if cond.get("type") != "sun":
            continue

        if has_location is False:
            return (
                "This action has a sun condition, but no location is "
                "configured. Set the coordinates in Settings → Device → "
                "Location first, or the condition will never block anything."
            )

        window = [key for key in ("after", "before") if cond.get(key)]
        phase = cond.get("phase")
        elevation = [key for key in ("above", "below") if cond.get(key) is not None]
        modes = [bool(window), bool(phase), bool(elevation)]

        if sum(modes) == 0:
            return (
                "Sun condition is empty: choose a window (after/before), a "
                "phase, or an elevation range."
            )
        if sum(modes) > 1:
            return (
                "Sun condition mixes a window, a phase and/or an elevation "
                "range. Use one of them."
            )

        for key in ("after", "before"):
            anchor = cond.get(key)
            if anchor and anchor not in ANCHOR_NAMES:
                return f"Unknown sun anchor '{anchor}' in '{key}'."

        if phase and phase not in PHASE_NAMES:
            return f"Unknown sun phase '{phase}'."

        above, below = cond.get("above"), cond.get("below")
        # A non-number is the schema's to report; compared here it would raise.
        numbers = all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in (above, below))
        if numbers and above >= below:
            return (
                f"Sun elevation range is inverted: 'above' ({above}) must be "
                f"lower than 'below' ({below})."
            )

    return None


def validate_section_actions(
    section: str, data: list, has_location: bool | None = None
) -> list[str]:
    """Sanitize and validate all action objects in an event or binary_sensor section.

    First cleans stale fields from each action (e.g. ``data`` left over from
    a previous cover action type).  Then validates remaining fields.
    Also checks for self-referencing conditions in binary_sensor entities,
    and for sun conditions on a device with no configured location.

    Args:
        section: Config section name ('event' or 'binary_sensor').
        data: List of entity dicts from the section.
        has_location: Whether the config has a ``location:`` section, so sun
            conditions can be rejected before they reach a device that cannot
            evaluate them. None means the caller could not tell.

    Returns:
        List of error message strings (empty if all valid).
    """
    errors: list[str] = []
    click_types = (
        _EVENT_CLICK_TYPES if section == "event" else _BINARY_SENSOR_CLICK_TYPES
    )
    for entity in data:
        name = entity.get("name", entity.get("boneio_input", "unknown"))
        actions_block = entity.get("actions") or {}
        for click_type in click_types:
            for idx, action in enumerate(actions_block.get(click_type) or []):
                # Auto-clean stale fields first
                removed = clean_action_fields(action)
                if removed:
                    _LOGGER.warning(
                        "Entity '%s', %s[%d]: auto-stripped stale fields: %s",
                        name, click_type, idx, removed,
                    )
                # Then validate remaining fields
                err = validate_action_fields(action)
                if err:
                    errors.append(f"Entity '{name}', {click_type}[{idx}]: {err}")
                # Check for self-referencing conditions
                self_ref = _check_condition_self_reference(entity, action, section)
                if self_ref:
                    errors.append(f"Entity '{name}', {click_type}[{idx}]: {self_ref}")
                sun_err = _check_sun_condition(action, has_location)
                if sun_err:
                    errors.append(f"Entity '{name}', {click_type}[{idx}]: {sun_err}")
    return errors



#: The fields an action names its target with, by action type, as the runtime
#: looks the target up. ``*_over_mqtt`` point at another controller and
#: ``mqtt`` at a topic: nothing here to check them against.
_TARGET_FIELDS: dict[str, tuple[str, ...]] = {
    "output": ("boneio_output",),
    "cover": ("boneio_cover",),
    "virtual_switch": ("boneio_virtual_switch",),
    "remote_output": ("remote_device", "output_id"),
    "remote_cover": ("remote_device", "cover_id"),
}

_TARGET_NAMES = {
    "output": "no output or output group '{0}'",
    "cover": "no cover '{0}'",
    "virtual_switch": "no virtual switch '{0}'",
    "remote_output": "remote device '{0}' has no output '{1}'",
    "remote_cover": "remote device '{0}' has no cover '{1}'",
}


def _action_targets(section_data: object):
    """Yield (entry index, path in the entry, target) for each targeted action."""
    if not isinstance(section_data, list):
        return
    for index, entry in enumerate(section_data):
        actions = entry.get("actions") if isinstance(entry, dict) else None
        if not isinstance(actions, dict):
            continue
        for click_type, items in actions.items():
            for position, action in enumerate(items if isinstance(items, list) else []):
                if not isinstance(action, dict):
                    continue
                kind = str(action.get("action") or "").lower()
                fields = _TARGET_FIELDS.get(kind)
                if not fields or not all(action.get(f) for f in fields):
                    continue
                where = f"actions.{click_type}[{position}].{fields[-1]}"
                yield index, where, (kind, *(str(action[f]) for f in fields))


def unknown_targets(
    section: str,
    data: object,
    stored: object,
    exists: Callable[[tuple[str, ...]], bool],
) -> list[str]:
    """Actions that point at something that does not exist, brought in by this save.

    The runtime skips such an action with a warning in the log, so nothing
    breaks and the button does nothing. A target the stored section already
    pointed at is let through even if it is gone: an output removed after its
    binding was made must not block every later save of the section.

    Args:
        section: Section name, for the error paths.
        data: The section being saved.
        stored: The section as stored, for the targets already there.
        exists: Whether a target, as ``(action type, *ids)``, exists.

    Returns:
        One ``path: message`` line per unknown target.
    """
    known = {target for _, _, target in _action_targets(stored)}
    return [
        f"{section}[{index}].{where}: {_TARGET_NAMES[target[0]].format(*target[1:])}"
        for index, where, target in _action_targets(data)
        if target not in known and not exists(target)
    ]


def target_check(manager) -> Callable[[tuple[str, ...]], bool]:
    """``exists`` for :func:`unknown_targets`, asking the running manager."""
    from boneio.core.utils import strip_accents

    def exists(target: tuple[str, ...]) -> bool:
        kind, *ids = target
        if kind == "output":
            key = strip_accents(ids[0])
            return bool(manager.outputs.get_output(key) or manager.outputs.get_output_group(key))
        if kind == "cover":
            return bool(manager.covers.get_cover(strip_accents(ids[0])))
        if kind == "virtual_switch":
            return bool(manager.virtual_switches.get(ids[0]))
        device = manager.remote_devices.get_all_available_devices().get(ids[0])
        if device is None:
            return False
        listed = device.outputs if kind == "remote_output" else device.covers
        known = {str(e.get("id")) for e in listed or [] if isinstance(e, dict)}
        # A device that has not reported what it has yet cannot be checked.
        return not known or ids[1] in known

    return exists
