"""Quick actions and device type validation routes for BoneIO Web UI."""

from __future__ import annotations

import copy
import logging
import os
import threading

from fastapi import Body, HTTPException

from boneio.core.config.yaml_util import (
    decrement_pending_yaml_saves,
    get_board_config_path,
    get_pending_yaml_saves_count,
    increment_pending_yaml_saves,
    load_config_from_file,
    load_yaml_file,
    normalize_board_name,
    normalize_version,
    update_config_section,
    yaml_saves_pending,
)
from boneio.core.config.input_bindings import (
    INPUT_MODE_COVERS,
    INPUT_MODE_COVERS_AND_OUTPUTS,
    INPUT_MODE_NONE,
    INPUT_MODE_OUTPUTS,
    INPUT_MODES,
    bindable_targets,
    board_input_ids,
    plan_input_bindings,
    taken_inputs,
)
from boneio.core.manager import Manager
from boneio.core.utils import TimePeriod
from boneio.webui.action_validation import (
    ACTION_ALLOWED_FIELDS,
    SHARED_FIELDS,
    clean_action_fields,
    validate_action_fields,
)
from boneio.webui.action_validation import validate_section_actions as _validate_section_actions
from boneio.webui.routes.config_core import (
    _get_app_state,
    invalidate_config_cache,
    router,
)

_LOGGER = logging.getLogger(__name__)


@router.get("/config/save-status")
async def get_save_status():
    """Check if background YAML saves are in progress.

    Returns:
        Dictionary with saving status and pending count.
    """
    return {
        "saving": yaml_saves_pending(),
        "pending_count": get_pending_yaml_saves_count(),
    }


@router.post("/config/validate_device_type_change")
async def validate_device_type_change(request: dict = Body(...)):
    """Validate if changing device_type will cause compatibility issues."""
    new_device_type = request.get("new_device_type")
    version = request.get("version", "0.8")

    if not new_device_type:
        raise HTTPException(status_code=400, detail="new_device_type is required")

    normalized_type = normalize_board_name(new_device_type)
    normalized_version = normalize_version(version)

    try:
        config_file = _get_app_state().yaml_config_file
        current_config = load_config_from_file(config_file)
    except Exception as e:
        _LOGGER.error("Failed to load current config: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to load config: {e}") from e

    try:
        board_file = get_board_config_path(f"output_{normalized_type}", normalized_version)
        input_file = get_board_config_path("input", normalized_version)
        board_config = load_yaml_file(board_file)
        input_config = load_yaml_file(input_file)
    except Exception as e:
        _LOGGER.error("Failed to load board config for %s: %s", normalized_type, e)
        raise HTTPException(
            status_code=400, detail=f"Board config not found for {new_device_type} version {version}"
        ) from e

    output_mapping = board_config.get("output_mapping", {})
    input_mapping = input_config.get("input_mapping", {})

    incompatible_outputs = []
    for output in (current_config or {}).get("output", []):
        boneio_output = output.get("boneio_output")
        if boneio_output and boneio_output.lower() not in output_mapping:
            incompatible_outputs.append(
                {
                    "boneio_output": boneio_output,
                    "id": output.get("id", boneio_output),
                    "name": output.get("name", output.get("id", boneio_output)),
                }
            )

    incompatible_inputs = []
    config_data = current_config or {}
    for section in ["event", "binary_sensor"]:
        for input_item in config_data.get(section, []):
            boneio_input = input_item.get("boneio_input")
            if boneio_input and boneio_input.lower() not in input_mapping:
                incompatible_inputs.append(
                    {
                        "boneio_input": boneio_input,
                        "id": input_item.get("id", boneio_input),
                        "section": section,
                    }
                )

    boneio_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    example_folder_name = normalized_type.replace("_", "x")
    example_dir = os.path.join(boneio_path, "example_config", example_folder_name)

    available_example_files = []
    if os.path.isdir(example_dir):
        for filename in os.listdir(example_dir):
            if filename.endswith(".yaml"):
                base_name = filename.replace(".yaml", "")
                if "output" in base_name.lower():
                    category = "output"
                elif "cover" in base_name.lower() and "output" not in base_name.lower():
                    category = "cover"
                elif "event" in base_name.lower():
                    category = "event"
                elif "binary_sensor" in base_name.lower():
                    category = "binary_sensor"
                elif "mqtt" in base_name.lower():
                    category = "mqtt"
                elif "config" in base_name.lower():
                    category = "config"
                elif "adc" in base_name.lower():
                    category = "adc"
                else:
                    category = "other"

                available_example_files.append(
                    {
                        "filename": filename,
                        "category": category,
                        "path": os.path.join(example_dir, filename),
                    }
                )

    compatible = len(incompatible_outputs) == 0 and len(incompatible_inputs) == 0

    return {
        "compatible": compatible,
        "incompatible_outputs": incompatible_outputs,
        "incompatible_inputs": incompatible_inputs,
        "available_example_files": available_example_files,
        "new_device_type": new_device_type,
        "normalized_type": normalized_type,
    }


INPUT_SECTIONS = ("event", "binary_sensor", "remote_inputs")

VALID_CLICK_TYPES = {
    "single", "double", "triple", "long",
    "pressed", "released",
    "double_then_long", "single_then_long", "double_then_single",
}

EVENT_CLICK_TYPES = (
    "single", "double", "triple", "long",
    "double_then_long", "single_then_long", "double_then_single",
)

BINARY_CLICK_TYPES = ("pressed", "released")

# Where a binary input kept its actions before they moved under ``actions``.
# Only this module ever wrote them, and the config loader purges unknown keys,
# so an action saved there vanished at the next restart. Read and moved on edit.
_LEGACY_BINARY_KEYS = {"actions_on_press": "pressed", "actions_on_release": "released"}

# Fields that name what an action drives, per action type. A full action from
# the editor must carry them: the section validator checks which fields are
# allowed, not which are present, and an action without a target loads as a
# warning and then does nothing.
_ACTION_TARGET_FIELDS: dict[str, tuple[str, ...]] = {
    "output": ("boneio_output",),
    "cover": ("boneio_cover",),
    "virtual_switch": ("boneio_virtual_switch",),
    "mqtt": ("topic",),
    "output_over_mqtt": ("boneio_id", "boneio_output"),
    "cover_over_mqtt": ("boneio_id", "boneio_cover"),
    "remote_output": ("remote_device", "output_id"),
    "remote_cover": ("remote_device", "cover_id"),
}

VALID_ACTION_TYPES = {
    "output", "cover", "remote_output", "remote_cover",
    "mqtt", "output_over_mqtt", "cover_over_mqtt",
}


def _validate_click_type(click_type: str) -> str:
    """Validate a click type against the supported set.

    Args:
        click_type: Click type from the request payload.

    Returns:
        The validated click type.

    Raises:
        HTTPException: If the click type is empty or unsupported.
    """
    if not click_type:
        raise HTTPException(status_code=422, detail="click_type is required")
    if click_type not in VALID_CLICK_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid click_type: '{click_type}'. Must be one of {sorted(VALID_CLICK_TYPES)}",
        )
    return click_type


def _build_action(payload: dict) -> dict:
    """Build a single YAML action dict from a quick-action payload.

    Args:
        payload: Request payload with action_type and its target fields.

    Returns:
        The action dict ready to be stored in the config.

    Raises:
        HTTPException: If the action type or its required fields are invalid.
    """
    action_type = payload.get("action_type", "output").strip()
    output_id = payload.get("output_id", "").strip()
    cover_id = payload.get("cover_id", "").strip()
    action = payload.get("action", "TOGGLE").strip()
    remote_device = payload.get("remote_device", "").strip()
    boneio_id = payload.get("boneio_id", "").strip()
    topic = payload.get("topic", "").strip()
    mqtt_msg = payload.get("action_mqtt_msg", "").strip()

    if action_type not in VALID_ACTION_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid action_type: '{action_type}'. Must be one of {sorted(VALID_ACTION_TYPES)}",
        )

    new_action: dict = {"action": action_type}

    if action_type == "output":
        if not output_id:
            raise HTTPException(status_code=422, detail="output_id is required for output action")
        new_action.update({"boneio_output": output_id, "action_output": action})

    elif action_type == "cover":
        if not cover_id:
            raise HTTPException(status_code=422, detail="cover_id is required for cover action")
        new_action.update({"boneio_cover": cover_id, "action_cover": action})

    elif action_type == "remote_output":
        if not remote_device or not output_id:
            raise HTTPException(status_code=422, detail="remote_device and output_id are required for remote_output")
        new_action.update({"remote_device": remote_device, "output_id": output_id, "action_output": action})

    elif action_type == "remote_cover":
        if not remote_device or not cover_id:
            raise HTTPException(status_code=422, detail="remote_device and cover_id are required for remote_cover")
        new_action.update({"remote_device": remote_device, "cover_id": cover_id, "action_cover": action})

    elif action_type == "mqtt":
        if not topic:
            raise HTTPException(status_code=422, detail="topic is required for mqtt action")
        new_action.update({"topic": topic, "action_mqtt_msg": mqtt_msg})

    elif action_type == "output_over_mqtt":
        if not boneio_id or not output_id:
            raise HTTPException(status_code=422, detail="boneio_id and output_id are required for output_over_mqtt")
        new_action.update({"boneio_id": boneio_id, "boneio_output": output_id, "action_output": action})

    elif action_type == "cover_over_mqtt":
        if not boneio_id or not cover_id:
            raise HTTPException(status_code=422, detail="boneio_id and cover_id are required for cover_over_mqtt")
        new_action.update({"boneio_id": boneio_id, "boneio_cover": cover_id, "action_cover": action})

    return new_action


def _strip_empty(value):
    """Drop ``None`` and empty-string values, recursively.

    The editor leaves a cleared field as ``""`` and the YAML should not carry
    it — the section save strips the same way before Cerberus sees it.

    Args:
        value: Any JSON value.

    Returns:
        The value without empty leaves.
    """
    if isinstance(value, dict):
        return {k: _strip_empty(v) for k, v in value.items() if v is not None and v != ""}
    if isinstance(value, list):
        return [_strip_empty(v) for v in value if v is not None and v != ""]
    return value


def _plain_time_periods(value):
    """Turn every time period into the string the YAML carries ("800ms").

    Actions are read from the parsed config, where a duration is a TimePeriod
    object. JSON-encoded it becomes a dict of its internals, which the editor
    cannot show and which, sent back, the config loader refuses — the device
    would not start. The input editor converts these on load; this makes the
    routes safe without depending on that.

    Args:
        value: Any value from an action.

    Returns:
        The value with each TimePeriod (object, or its JSON dict) as a string.
    """
    if isinstance(value, TimePeriod):
        return str(value)
    if isinstance(value, dict):
        if "_total_in_seconds" in value:
            total = value.get("_total_in_seconds")
            if isinstance(total, (int, float)) and not isinstance(total, bool):
                whole_seconds = float(total).is_integer()
                return str(TimePeriod(seconds=total) if whole_seconds else TimePeriod(milliseconds=total * 1000))
        return {k: _plain_time_periods(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain_time_periods(v) for v in value]
    return value


def _normalize_action_def(raw) -> dict:
    """Accept a whole action as the settings editor builds it.

    This is what lets Teach Mode and the quick action offer everything the
    input editor does — conditions, delays, repeat, brightness, tilt, presets —
    instead of the handful of fields ``_build_action`` knows how to assemble.

    Args:
        raw: The ``action_def`` object from the request.

    Returns:
        A cleaned copy, ready to store.

    Raises:
        HTTPException: 422 when it is not an action this device can run.
    """
    if not isinstance(raw, dict):
        raise HTTPException(status_code=422, detail="action_def must be an object")

    action = _plain_time_periods(_strip_empty(copy.deepcopy(raw)))
    action_type = str(action.get("action") or "").strip().lower()
    if action_type not in ACTION_ALLOWED_FIELDS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid action type: '{action_type}'. Must be one of {sorted(ACTION_ALLOWED_FIELDS)}",
        )
    action["action"] = action_type

    # Leftovers from a type the user switched away from, not a mistake worth
    # refusing; the section save drops them the same way.
    clean_action_fields(action)
    error = validate_action_fields(action)
    if error:
        raise HTTPException(status_code=422, detail=error)

    missing = [f for f in _ACTION_TARGET_FIELDS.get(action_type, ()) if not action.get(f)]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"{', '.join(missing)} required for {action_type} action",
        )
    return action


def _action_from_payload(payload: dict) -> dict:
    """The action a quick-action request asks to store.

    Args:
        payload: Request body. ``action_def`` carries a whole action; without
            it the flat fields (``action_type``, ``output_id``...) are used.

    Returns:
        The action dict.
    """
    if "action_def" in payload:
        return _normalize_action_def(payload["action_def"])
    return _build_action(payload)


def _find_input_entry(config: dict, entity_id: str) -> tuple[str, int]:
    """Locate an input entry by entity id across all input sections.

    Args:
        config: Full parsed configuration.
        entity_id: Input entity id, ``boneio_input`` name or pin.

    Returns:
        Tuple of (section name, index in that section).

    Raises:
        HTTPException: 404 when the input cannot be found.
    """
    for sec_name in INPUT_SECTIONS:
        entries = config.get(sec_name, [])
        if not isinstance(entries, list):
            continue
        for idx, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            eid = entry.get("id", entry.get("pin", ""))
            boneio_in = entry.get("boneio_input", "")
            if (
                str(eid) == entity_id
                or str(eid).lower() == entity_id.lower()
                or str(boneio_in).lower() == entity_id.lower()
            ):
                return sec_name, idx

    _LOGGER.warning(
        "Quick action: input '%s' not found. Available sections: %s",
        entity_id,
        {s: len(config.get(s, [])) for s in INPUT_SECTIONS},
    )
    raise HTTPException(
        status_code=404,
        detail=f"Input '{entity_id}' not found in event, binary_sensor, or remote_inputs sections",
    )


def _migrate_flat_action_keys(entry: dict, section: str) -> None:
    """Move actions stored under legacy keys into the nested ``actions`` dict.

    Event inputs had ``actions_<click>`` keys; binary inputs had
    ``actions_on_press``/``actions_on_release``, which the config loader purges
    as unknown, so actions saved there were lost at the next restart.

    Args:
        entry: Input entry to normalize in place.
        section: Config section the entry belongs to.
    """
    if _uses_binary_actions(entry, section):
        legacy = _LEGACY_BINARY_KEYS
    elif section in ("event", "remote_inputs"):
        legacy = {f"actions_{act_type}": act_type for act_type in EVENT_CLICK_TYPES}
    else:
        return
    for flat_key, click_type in legacy.items():
        if flat_key not in entry:
            continue
        moved = entry.pop(flat_key)
        if not isinstance(moved, list) or not moved:
            continue
        if not isinstance(entry.get("actions"), dict):
            entry["actions"] = {}
        existing = entry["actions"].get(click_type) or []
        entry["actions"][click_type] = existing + moved


def _uses_binary_actions(entry: dict, section: str) -> bool:
    """Return True when the entry is a binary input (pressed/released).

    Args:
        entry: Input entry.
        section: Config section the entry belongs to.

    Returns:
        True for a binary sensor, False for an event input.
    """
    if section == "binary_sensor":
        return True
    if section == "remote_inputs":
        return entry.get("mode", "event") == "binary_sensor"
    return False


def _click_type_for_entry(entry: dict, section: str, click_type: str) -> str:
    """Check a click type against the kind of input it is stored on.

    An event input has no ``pressed`` and a binary one no ``double``: an action
    filed under the wrong one is never fired and the validator never looks at
    it. ``single`` on a binary input is taken as ``pressed``, which is what the
    quick action used to do.

    Args:
        entry: Input entry.
        section: Config section the entry belongs to.
        click_type: Requested click type.

    Returns:
        The click type to use.

    Raises:
        HTTPException: 422 when the input has no such click type.
    """
    if _uses_binary_actions(entry, section):
        if click_type == "single":
            return "pressed"
        allowed = BINARY_CLICK_TYPES
    else:
        allowed = EVENT_CLICK_TYPES
    if click_type not in allowed:
        raise HTTPException(
            status_code=422,
            detail=f"Click type '{click_type}' does not apply to this input. Use one of {list(allowed)}",
        )
    return click_type


def _get_target_list(entry: dict, section: str, click_type: str, *, create: bool = True) -> list:
    """Return the action list for a click type, optionally creating it.

    Args:
        entry: Input entry (already normalized).
        section: Config section the entry belongs to.
        click_type: Click type whose action list is requested.
        create: When True, missing lists are created in the entry.

    Returns:
        The list of actions for this click type (empty list when missing and
        *create* is False).
    """
    if not isinstance(entry.get("actions"), dict):
        if not create:
            return []
        entry["actions"] = {}
    actions = entry["actions"]
    if not isinstance(actions.get(click_type), list):
        if not create:
            return []
        actions[click_type] = []
    return actions[click_type]


def _describe_action(act: dict) -> dict:
    """Summarize a raw action dict for the Web UI.

    Args:
        act: Raw action dict from the config.

    Returns:
        Dict with action_type, target, action and the raw action payload.
    """
    return {
        "action_type": act.get("action", "?"),
        "target": (
            act.get("boneio_output")
            or act.get("boneio_cover")
            or act.get("output_id")
            or act.get("cover_id")
            or act.get("boneio_virtual_switch")
            or act.get("switch_id")
            or act.get("light_id")
            or act.get("topic")
            or "?"
        ),
        "action": (
            act.get("action_output")
            or act.get("action_cover")
            or act.get("action_switch")
            or act.get("action_light")
            or act.get("action_mqtt_msg")
            or "?"
        ),
        "remote_device": act.get("remote_device") or act.get("boneio_id") or None,
        # As the YAML spells it, so an editor can load it and send it back.
        "raw": _plain_time_periods(act),
    }


def _assert_no_duplicate(
    target_list: list,
    new_action: dict,
    entity_id: str,
    click_type: str,
    *,
    skip_index: int | None = None,
) -> None:
    """Reject an action identical to one the click type already runs.

    Only an exact copy is refused — linking the same button twice in Teach
    Mode. Two different actions on one target are legitimate, and the input
    editor allows them: ON while it is dark and OFF otherwise, or a toggle plus
    a delayed OFF.

    Args:
        target_list: Existing actions for this click type.
        new_action: Action about to be stored.
        entity_id: Input entity id (used in the error message).
        click_type: Click type (used in the error message).
        skip_index: Index to ignore, used when updating an action in place.

    Raises:
        HTTPException: 409 when an identical action already exists.
    """
    for idx, existing in enumerate(target_list):
        if skip_index is not None and idx == skip_index:
            continue
        if existing == new_action:
            raise HTTPException(
                status_code=409,
                detail=f"This action already exists for {entity_id} ({click_type})",
            )


def _hot_update_input(app_state, section: str, entry: dict, entity_id: str) -> None:
    """Apply changed actions to the running input device, if present.

    Args:
        app_state: Web UI application state holding the manager.
        section: Config section the entry belongs to.
        entry: Updated input entry.
        entity_id: Input entity id.
    """
    try:
        manager: Manager = app_state.manager
        input_device = manager.inputs._inputs.get(entity_id.lower())
        if not input_device:
            _LOGGER.debug(
                "Input %s not in memory — actions will apply after restart", entity_id
            )
            return
        parsed = manager.parse_actions(
            getattr(input_device, "pin", entity_id), entry.get("actions") or {}
        )
        input_device.set_actions(actions=parsed)
        _LOGGER.info("Hot-updated actions for input %s", entity_id)
    except Exception as hot_err:
        _LOGGER.warning("Quick action saved but hot-update failed: %s", hot_err)


def _persist_entry_change(
    app_state,
    section: str,
    entries: list,
    entry: dict,
    entity_id: str,
    click_type: str,
) -> None:
    """Validate, cache, hot-update and asynchronously persist a changed entry.

    Args:
        app_state: Web UI application state.
        section: Config section that was modified.
        entries: Full list of entries for that section.
        entry: The modified entry.
        entity_id: Input entity id (for logging).
        click_type: Click type that was modified (for logging).

    Raises:
        HTTPException: 422 when the changed entry fails validation.
    """
    # Only the entry being changed: a problem in another input is not this
    # request's to report, and would block every quick action until someone
    # found it. Validated as what it is — a remote input can be either kind,
    # and the validator walks the click types of the section it is told.
    kind = "binary_sensor" if _uses_binary_actions(entry, section) else "event"
    config = _load_config_from_cache_or_disk(app_state) or {}
    errors = _validate_section_actions(kind, [entry], has_location=bool(config.get("location")))
    if errors:
        raise HTTPException(
            status_code=422,
            detail={"message": "Invalid action configuration", "errors": errors},
        )

    # 1. Update in-memory cache immediately (instant)
    invalidate_config_cache(section=section, section_data=entries)

    # 2. Hot-update input device actions in-memory
    _hot_update_input(app_state, section, entry, entity_id)

    # 3. Fire YAML save in background (don't block response)
    config_file = app_state.yaml_config_file

    increment_pending_yaml_saves()

    def _background_yaml_save() -> None:
        """Persist quick-action to YAML on disk in a background thread."""
        try:
            result = update_config_section(config_file, section, entries)
            if result["status"] == "error":
                _LOGGER.error(
                    "Background YAML save failed for quick action: %s",
                    result["message"],
                )
            else:
                _LOGGER.info(
                    "Background YAML save completed for quick action: %s -> %s",
                    entity_id, click_type,
                )
        except Exception as bg_err:
            _LOGGER.error(
                "Background YAML save error for quick action: %s",
                bg_err, exc_info=True,
            )
        finally:
            decrement_pending_yaml_saves()

    threading.Thread(
        target=_background_yaml_save,
        name=f"yaml-save-quick-action-{entity_id}",
        daemon=True,
    ).start()


def _load_config_from_cache_or_disk(app_state) -> dict:
    """Load config preferring the in-memory ConfigHelper cache over disk.

    The in-memory cache is patched immediately by ``invalidate_config_cache``
    after each quick-action change, so it always has the latest data even while
    a background YAML save is still in progress.

    Args:
        app_state: Web UI application state.

    Returns:
        Parsed config dict.
    """
    try:
        manager: Manager = app_state.manager
        config = manager.config_helper.get_config()
        if config:
            return config
    except Exception:
        pass
    return load_yaml_file(app_state.yaml_config_file)


def _load_entry_for_edit(entity_id: str) -> tuple:
    """Load config and locate a normalized input entry for modification.

    Reads from the in-memory ConfigHelper cache (which is updated
    immediately after each quick-action change) rather than from disk,
    avoiding race conditions with background YAML saves.

    Args:
        entity_id: Input entity id.

    Returns:
        Tuple of (app_state, section, entries, input_index, entry).
    """
    app_state = _get_app_state()
    config = _load_config_from_cache_or_disk(app_state)
    section, input_index = _find_input_entry(config, entity_id)
    # Deep-copy the entries list so we don't mutate the in-memory cache
    entries = copy.deepcopy(config[section])
    entry = entries[input_index]
    _migrate_flat_action_keys(entry, section)
    return app_state, section, entries, input_index, entry


@router.get("/config/input-actions")
async def get_input_actions(entity_id: str):
    """List all configured actions of a single input, with stable indexes.

    The indexes returned here address actions inside their click type list and
    are what ``PUT``/``DELETE`` ``/config/quick-action`` expect.

    Args:
        entity_id: Input entity id, ``boneio_input`` name or pin.

    Returns:
        Dict with section, mode and the list of described actions.
    """
    entity_id = (entity_id or "").strip()
    if not entity_id:
        raise HTTPException(status_code=422, detail="entity_id is required")

    try:
        app_state = _get_app_state()
        config = _load_config_from_cache_or_disk(app_state)
        section, input_index = _find_input_entry(config, entity_id)
        # Legacy keys are folded in exactly as an edit would fold them, so the
        # indexes listed here are the ones PUT/DELETE will find.
        entry = copy.deepcopy(config[section][input_index])
        _migrate_flat_action_keys(entry, section)

        binary_mode = _uses_binary_actions(entry, section)
        actions: list[dict] = []
        raw_actions = entry.get("actions")
        if isinstance(raw_actions, dict):
            for click_type, act_list in raw_actions.items():
                if not isinstance(act_list, list):
                    continue
                for idx, act in enumerate(act_list):
                    if isinstance(act, dict):
                        actions.append({"click_type": click_type, "index": idx, **_describe_action(act)})

        return {
            "status": "ok",
            "entity_id": entity_id,
            "section": section,
            "mode": "binary_sensor" if binary_mode else "event",
            "area": entry.get("area"),
            "actions": actions,
        }

    except HTTPException:
        raise
    except Exception as e:
        _LOGGER.error("Error listing input actions: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error listing input actions: {e}") from e


@router.post("/config/quick-action")
async def add_quick_action(payload: dict = Body(...)):
    """Add a single action to an input's click type without full section save.

    Args:
        payload: ``entity_id``, ``click_type`` and either ``action_def`` (a
            whole action, as the input editor builds it) or the flat fields.

    Returns:
        Status dict with the section, click type and index of the new action.
    """
    entity_id = payload.get("entity_id", "").strip()
    if not entity_id:
        raise HTTPException(status_code=422, detail="entity_id is required")
    click_type = _validate_click_type(payload.get("click_type", "").strip())
    new_action = _action_from_payload(payload)

    try:
        app_state, section, entries, input_index, entry = _load_entry_for_edit(entity_id)
        click_type = _click_type_for_entry(entry, section, click_type)

        target_list = _get_target_list(entry, section, click_type)
        _assert_no_duplicate(target_list, new_action, entity_id, click_type)

        target_list.append(new_action)
        entries[input_index] = entry

        _persist_entry_change(app_state, section, entries, entry, entity_id, click_type)

        _LOGGER.info(
            "Quick action added: %s -> %s -> %s %s [section=%s]",
            entity_id, click_type, new_action.get("action"),
            _describe_action(new_action)["target"], section,
        )

        return {
            "status": "ok",
            "message": f"Action added to {entity_id} ({click_type})",
            "section": section,
            "click_type": click_type,
            "index": len(target_list) - 1,
        }

    except HTTPException:
        raise
    except Exception as e:
        _LOGGER.error("Error adding quick action: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error adding quick action: {e}") from e


# What an update in the flat format leaves alone. That format only names a
# target and a command, so everything else on the action — conditions, delay,
# thresholds, repeat, tilt — is kept from the one it replaces instead of being
# silently dropped. ``action_def`` replaces the whole action and skips this.
_PRESERVED_KEYS = (SHARED_FIELDS - {"action"}) | {"data", "restore_tilt"}


@router.put("/config/quick-action")
async def update_quick_action(payload: dict = Body(...)):
    """Replace an existing action of an input, optionally moving its click type.

    Args:
        payload: Must contain ``entity_id``, ``click_type``, ``index`` and the
            action — ``action_def`` or the flat fields. An optional
            ``new_click_type`` moves the action to a different click type.

    Returns:
        Status dict with the resulting click type and index.
    """
    entity_id = payload.get("entity_id", "").strip()
    if not entity_id:
        raise HTTPException(status_code=422, detail="entity_id is required")
    click_type = _validate_click_type(payload.get("click_type", "").strip())
    new_click_type = _validate_click_type(
        (payload.get("new_click_type") or click_type).strip()
    )
    index = payload.get("index")
    if not isinstance(index, int) or isinstance(index, bool) or index < 0:
        raise HTTPException(status_code=422, detail="index must be a non-negative integer")

    replaces_whole = "action_def" in payload
    new_action = _action_from_payload(payload)

    try:
        app_state, section, entries, input_index, entry = _load_entry_for_edit(entity_id)
        click_type = _click_type_for_entry(entry, section, click_type)
        new_click_type = _click_type_for_entry(entry, section, new_click_type)

        source_list = _get_target_list(entry, section, click_type, create=False)
        if index >= len(source_list):
            raise HTTPException(
                status_code=404,
                detail=f"No action at index {index} for {entity_id} ({click_type})",
            )

        if not replaces_whole:
            original_action: dict = source_list[index]
            for key in _PRESERVED_KEYS:
                if key in original_action and key not in new_action:
                    new_action[key] = original_action[key]
            clean_action_fields(new_action)

        if new_click_type == click_type:
            _assert_no_duplicate(
                source_list, new_action, entity_id, click_type, skip_index=index
            )
            source_list[index] = new_action
            new_index = index
        else:
            target_list = _get_target_list(entry, section, new_click_type)
            _assert_no_duplicate(target_list, new_action, entity_id, new_click_type)
            source_list.pop(index)
            target_list.append(new_action)
            new_index = len(target_list) - 1
            _drop_empty_action_list(entry, click_type)

        entries[input_index] = entry

        _persist_entry_change(app_state, section, entries, entry, entity_id, new_click_type)

        _LOGGER.info(
            "Quick action updated: %s (%s[%d]) -> %s %s [section=%s]",
            entity_id, click_type, index, new_click_type,
            _describe_action(new_action)["target"], section,
        )

        return {
            "status": "ok",
            "message": f"Action updated for {entity_id} ({new_click_type})",
            "section": section,
            "click_type": new_click_type,
            "index": new_index,
        }

    except HTTPException:
        raise
    except Exception as e:
        _LOGGER.error("Error updating quick action: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error updating quick action: {e}") from e


def _route_ahead_of_section_put() -> None:
    """Put ``PUT /config/quick-action`` ahead of ``PUT /config/{section}``.

    Both live on the same router and Starlette takes the first match. The
    section route is registered first (this module imports it), so every edit
    from Teach Mode was written into config.yaml as a section called
    ``quick-action`` and the action itself never changed. The section route now
    refuses names like that too; this makes the edit reach its handler.
    """
    routes = router.routes

    def _is(route, path: str) -> bool:
        return getattr(route, "path", None) == path and "PUT" in (getattr(route, "methods", None) or ())

    specific = next((r for r in routes if _is(r, "/api/config/quick-action")), None)
    generic = next((r for r in routes if _is(r, "/api/config/{section}")), None)
    if specific is None or generic is None:
        return
    if routes.index(specific) > routes.index(generic):
        routes.remove(specific)
        routes.insert(routes.index(generic), specific)


_route_ahead_of_section_put()


def _drop_empty_action_list(entry: dict, click_type: str) -> None:
    """Remove a click type left with no actions, and ``actions`` if it empties.

    Args:
        entry: Input entry, modified in place.
        click_type: Click type whose list may now be empty.
    """
    actions = entry.get("actions")
    if not isinstance(actions, dict):
        return
    if not actions.get(click_type):
        actions.pop(click_type, None)
    if not actions:
        entry.pop("actions", None)


@router.delete("/config/quick-action")
async def delete_quick_action(payload: dict = Body(...)):
    """Remove a single action from an input's click type.

    Args:
        payload: Must contain ``entity_id``, ``click_type`` and ``index``.

    Returns:
        Status dict describing the removed action.
    """
    entity_id = payload.get("entity_id", "").strip()
    if not entity_id:
        raise HTTPException(status_code=422, detail="entity_id is required")
    click_type = _validate_click_type(payload.get("click_type", "").strip())
    index = payload.get("index")
    if not isinstance(index, int) or isinstance(index, bool) or index < 0:
        raise HTTPException(status_code=422, detail="index must be a non-negative integer")

    try:
        app_state, section, entries, input_index, entry = _load_entry_for_edit(entity_id)
        click_type = _click_type_for_entry(entry, section, click_type)

        target_list = _get_target_list(entry, section, click_type, create=False)
        if index >= len(target_list):
            raise HTTPException(
                status_code=404,
                detail=f"No action at index {index} for {entity_id} ({click_type})",
            )

        removed = target_list.pop(index)
        # Drop empty containers so the YAML stays clean
        _drop_empty_action_list(entry, click_type)

        entries[input_index] = entry

        _persist_entry_change(app_state, section, entries, entry, entity_id, click_type)

        _LOGGER.info(
            "Quick action removed: %s (%s[%d]) -> %s [section=%s]",
            entity_id, click_type, index, _describe_action(removed)["target"], section,
        )

        return {
            "status": "ok",
            "message": f"Action removed from {entity_id} ({click_type})",
            "section": section,
            "click_type": click_type,
            "removed": _describe_action(removed),
        }

    except HTTPException:
        raise
    except Exception as e:
        _LOGGER.error("Error deleting quick action: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error deleting quick action: {e}") from e



# --------------------------------------------------------------- input bindings
#
# The first-run wizard offers to wire the inputs to what the board already has.
# Output and cover configs are flashed per model at assembly, so both routes
# below read them rather than assuming any particular hardware.


def _board_inputs(config: dict) -> list[str]:
    """Every input id the assembled board exposes, in board order.

    Args:
        config: The loaded configuration.

    Returns:
        Lower-cased input ids.

    Raises:
        HTTPException: 400 if the board's input map cannot be read.
    """
    boneio = (config or {}).get("boneio") or {}
    version = normalize_version(boneio.get("version", "0.8"))
    try:
        input_config = load_yaml_file(get_board_config_path("input", version))
    except Exception as e:
        _LOGGER.error("Failed to load input map for version %s: %s", version, e)
        raise HTTPException(
            status_code=400, detail=f"Input map not found for board version {version}"
        ) from e
    return board_input_ids(input_config)


@router.get("/config/input-bindings/targets")
async def get_input_binding_targets():
    """Report what this board can bind its inputs to.

    Lets the wizard offer only the modes the hardware supports: a cover board
    has no plain relays, and a relay board has no covers unless someone has
    already paired two of them.

    Returns:
        Counts and the modes that make sense for this device.
    """
    config = load_config_from_file(_get_app_state().yaml_config_file) or {}
    outputs, covers = bindable_targets(config)
    free_inputs = [i for i in _board_inputs(config) if i.lower() not in taken_inputs(config)]

    modes = [INPUT_MODE_NONE]
    if outputs:
        modes.insert(0, INPUT_MODE_OUTPUTS)
    if covers:
        modes.insert(0, INPUT_MODE_COVERS)
    if outputs and covers:
        modes.insert(0, INPUT_MODE_COVERS_AND_OUTPUTS)

    return {
        "device_type": ((config.get("boneio") or {}).get("device_type")),
        "free_inputs": len(free_inputs),
        "outputs": len(outputs),
        "covers": len(covers),
        "available_modes": modes,
    }


@router.post("/config/input-bindings")
async def apply_input_bindings(request: dict = Body(...)):
    """Wire the inputs to the board's outputs and/or covers.

    Replaces the ``event`` section outright — the shipped config ships example
    bindings and a half-merged result would be harder to reason about than a
    clean one. ``none`` leaves the section alone entirely.

    Args:
        request: ``mode`` (see INPUT_MODES) and optional ``restore_state``
            (bool) to apply to relays and covers.

    Returns:
        What was written.

    Raises:
        HTTPException: 400 for an unknown mode, 500 if a write fails.
    """
    mode = request.get("mode")
    if mode not in INPUT_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"mode must be one of {', '.join(INPUT_MODES)}",
        )
    restore_state = request.get("restore_state")
    if restore_state is not None and not isinstance(restore_state, bool):
        raise HTTPException(status_code=400, detail="restore_state must be a boolean")

    config_file = _get_app_state().yaml_config_file
    config = load_config_from_file(config_file) or {}
    outputs, covers = bindable_targets(config)

    written = {}

    if mode != INPUT_MODE_NONE:
        entries = plan_input_bindings(
            mode=mode,
            available_inputs=_board_inputs(config),
            taken_inputs=taken_inputs(config),
            outputs=outputs,
            covers=covers,
        )
        result = update_config_section(config_file, "event", entries)
        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail=result.get("message"))
        invalidate_config_cache(section="event", section_data=entries)
        written["event"] = len(entries)

    if restore_state is not None:
        for section in ("output", "cover"):
            current = [e for e in (config.get(section) or []) if isinstance(e, dict)]
            if not current:
                continue
            updated = [{**entry, "restore_state": restore_state} for entry in current]
            result = update_config_section(config_file, section, updated)
            if result.get("status") == "error":
                raise HTTPException(status_code=500, detail=result.get("message"))
            invalidate_config_cache(section=section, section_data=updated)
            written[section] = len(updated)

    _LOGGER.info("Input bindings applied: mode=%s written=%s", mode, written)
    return {"status": "success", "mode": mode, "written": written}
