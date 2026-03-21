"""Action field validation helpers for WebUI config routes.

Standalone module (no FastAPI / router dependencies) so it can be imported
in unit tests without triggering python-multipart or other optional deps.
"""

from __future__ import annotations

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
        "brightness", "color_temp", "rgb", "transition",
        "effect", "palette", "effect_speed", "effect_intensity",
        "colors", "presets",
    },
    "remote_cover": {"remote_device", "cover_id", "action_cover", "data"},
}

SHARED_FIELDS: set[str] = {"action", "min_duration", "max_duration", "repeat", "repeat_interval"}

_EVENT_CLICK_TYPES = (
    "single", "double", "triple", "long",
    "double_then_long", "single_then_long", "double_then_single",
)
_BINARY_SENSOR_CLICK_TYPES = ("pressed", "released")


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


def validate_section_actions(section: str, data: list) -> list[str]:
    """Validate all action objects in an event or binary_sensor section.

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
                err = validate_action_fields(action)
                if err:
                    errors.append(f"Entity '{name}', {click_type}[{idx}]: {err}")
    return errors
