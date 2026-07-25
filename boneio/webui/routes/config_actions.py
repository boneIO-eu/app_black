"""Quick actions and device type validation routes for BoneIO Web UI."""

from __future__ import annotations

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
from boneio.core.manager import Manager
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
    """Merge legacy ``actions_<click>`` keys into the nested ``actions`` dict.

    Args:
        entry: Input entry to normalize in place.
        section: Config section the entry belongs to.
    """
    if section not in ("event", "remote_inputs"):
        return
    for act_type in EVENT_CLICK_TYPES:
        flat_key = f"actions_{act_type}"
        if flat_key in entry:
            if not isinstance(entry.get("actions"), dict):
                entry["actions"] = {}
            existing = entry["actions"].get(act_type, [])
            entry["actions"][act_type] = existing + entry.pop(flat_key)


def _uses_binary_actions(entry: dict, section: str) -> bool:
    """Return True when the entry stores actions in on_press/on_release lists.

    Args:
        entry: Input entry.
        section: Config section the entry belongs to.

    Returns:
        True for binary_sensor style storage, False for the nested actions dict.
    """
    if section == "binary_sensor":
        return True
    if section == "remote_inputs":
        return entry.get("mode", "event") == "binary_sensor"
    return False


def _binary_actions_key(click_type: str) -> str:
    """Map a click type to the binary_sensor action list key.

    Args:
        click_type: Click type such as ``pressed`` or ``released``.

    Returns:
        Either ``actions_on_press`` or ``actions_on_release``.
    """
    return "actions_on_press" if click_type in ("pressed", "single") else "actions_on_release"


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
    if _uses_binary_actions(entry, section):
        key = _binary_actions_key(click_type)
        if key not in entry:
            if not create:
                return []
            entry[key] = []
        return entry[key]

    if not isinstance(entry.get("actions"), dict):
        if not create:
            return []
        entry["actions"] = {}
    actions = entry["actions"]
    if click_type not in actions:
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
        "raw": act,
    }


def _assert_no_duplicate(
    target_list: list,
    new_action: dict,
    entity_id: str,
    click_type: str,
    *,
    skip_index: int | None = None,
) -> None:
    """Reject an action that already targets the same output/cover.

    Args:
        target_list: Existing actions for this click type.
        new_action: Action about to be stored.
        entity_id: Input entity id (used in the error message).
        click_type: Click type (used in the error message).
        skip_index: Index to ignore, used when updating an action in place.

    Raises:
        HTTPException: 409 when an equivalent action already exists.
    """
    for idx, existing in enumerate(target_list):
        if skip_index is not None and idx == skip_index:
            continue
        same_output = (
            existing.get("boneio_output") and existing.get("boneio_output") == new_action.get("boneio_output")
        )
        same_cover = (
            existing.get("boneio_cover") and existing.get("boneio_cover") == new_action.get("boneio_cover")
        )
        same_remote_output = (
            existing.get("remote_device") == new_action.get("remote_device")
            and existing.get("output_id") and existing.get("output_id") == new_action.get("output_id")
        )
        same_remote_cover = (
            existing.get("remote_device") == new_action.get("remote_device")
            and existing.get("cover_id") and existing.get("cover_id") == new_action.get("cover_id")
        )
        if same_output or same_cover or same_remote_output or same_remote_cover:
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
        raw_actions = entry.get("actions", {})
        if not raw_actions and _uses_binary_actions(entry, section):
            raw_actions = {
                "pressed": entry.get("actions_on_press", []),
                "released": entry.get("actions_on_release", []),
            }
        parsed = manager.parse_actions(
            getattr(input_device, "pin", entity_id), raw_actions
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
        HTTPException: 422 when the resulting section fails validation.
    """
    errors = _validate_section_actions(section, entries)
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
    import copy

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
        entry = dict(config[section][input_index])
        _migrate_flat_action_keys(entry, section)

        binary_mode = _uses_binary_actions(entry, section)
        actions: list[dict] = []

        if binary_mode:
            for click_type, key in (("pressed", "actions_on_press"), ("released", "actions_on_release")):
                for idx, act in enumerate(entry.get(key) or []):
                    if isinstance(act, dict):
                        actions.append({"click_type": click_type, "index": idx, **_describe_action(act)})
        else:
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
            "actions": actions,
        }

    except HTTPException:
        raise
    except Exception as e:
        _LOGGER.error("Error listing input actions: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error listing input actions: {e}") from e


@router.post("/config/quick-action")
async def add_quick_action(payload: dict = Body(...)):
    """Add a single action to an input's click type without full section save."""
    entity_id = payload.get("entity_id", "").strip()
    if not entity_id:
        raise HTTPException(status_code=422, detail="entity_id is required")
    click_type = _validate_click_type(payload.get("click_type", "").strip())
    new_action = _build_action(payload)

    try:
        app_state, section, entries, input_index, entry = _load_entry_for_edit(entity_id)

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


@router.put("/config/quick-action")
async def update_quick_action(payload: dict = Body(...)):
    """Replace an existing action of an input, optionally moving its click type.

    Args:
        payload: Must contain ``entity_id``, ``click_type``, ``index`` and the
            action fields. An optional ``new_click_type`` moves the action to a
            different click type.

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
    if not isinstance(index, int) or index < 0:
        raise HTTPException(status_code=422, detail="index must be a non-negative integer")

    new_action = _build_action(payload)

    try:
        app_state, section, entries, input_index, entry = _load_entry_for_edit(entity_id)

        source_list = _get_target_list(entry, section, click_type, create=False)
        if index >= len(source_list):
            raise HTTPException(
                status_code=404,
                detail=f"No action at index {index} for {entity_id} ({click_type})",
            )

        if new_click_type == click_type:
            _assert_no_duplicate(
                source_list, new_action, entity_id, click_type, skip_index=index
            )
            source_list[index] = new_action
        else:
            target_list = _get_target_list(entry, section, new_click_type)
            _assert_no_duplicate(target_list, new_action, entity_id, new_click_type)
            source_list.pop(index)
            target_list.append(new_action)

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
        }

    except HTTPException:
        raise
    except Exception as e:
        _LOGGER.error("Error updating quick action: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error updating quick action: {e}") from e


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
    if not isinstance(index, int) or index < 0:
        raise HTTPException(status_code=422, detail="index must be a non-negative integer")

    try:
        app_state, section, entries, input_index, entry = _load_entry_for_edit(entity_id)

        target_list = _get_target_list(entry, section, click_type, create=False)
        if index >= len(target_list):
            raise HTTPException(
                status_code=404,
                detail=f"No action at index {index} for {entity_id} ({click_type})",
            )

        removed = target_list.pop(index)

        # Drop empty containers so the YAML stays clean
        if not target_list:
            if _uses_binary_actions(entry, section):
                entry.pop(_binary_actions_key(click_type), None)
            else:
                actions = entry.get("actions")
                if isinstance(actions, dict):
                    actions.pop(click_type, None)
                    if not actions:
                        entry.pop("actions", None)

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

