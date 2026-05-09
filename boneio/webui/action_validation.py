"""Action field validation helpers for WebUI config routes.

Standalone module (no FastAPI / router dependencies) so it can be imported
in unit tests without triggering python-multipart or other optional deps.
"""

from __future__ import annotations

import logging

_LOGGER = logging.getLogger(__name__)

# Fields allowed per action type. When an action is saved, only these fields
# (plus SHARED_FIELDS) are valid. Mirrors frontend ActionFields/helpers.ts.
ACTION_ALLOWED_FIELDS: dict[str, set[str]] = {
    "output": {"boneio_output", "action_output"},
    "cover": {"boneio_cover", "action_cover", "data"},
    "mqtt": {"topic", "action_mqtt_msg"},
    "output_over_mqtt": {"boneio_id", "boneio_output", "action_output", "action_mqtt_msg"},
    "cover_over_mqtt": {"boneio_id", "boneio_cover", "action_cover", "action_mqtt_msg"},
    "remote_output": {
        "remote_device", "output_id", "action_output",
        "brightness","brightness_step", "color_temp", "rgb", "transition",
        "effect", "palette", "effect_speed", "effect_intensity",
        "colors", "presets",
    },
    "remote_cover": {"remote_device", "cover_id", "action_cover", "data"},
}

SHARED_FIELDS: set[str] = {"action", "min_duration", "max_duration", "repeat", "repeat_interval", "condition", "conditions"}

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


def validate_section_actions(section: str, data: list) -> list[str]:
    """Sanitize and validate all action objects in an event or binary_sensor section.

    First cleans stale fields from each action (e.g. ``data`` left over from
    a previous cover action type).  Then validates remaining fields.
    Also checks for self-referencing conditions in binary_sensor entities.

    Args:
        section: Config section name ('event' or 'binary_sensor').
        data: List of entity dicts from the section.

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
                    _LOGGER.info(
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
    return errors

