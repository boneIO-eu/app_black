"""Quick actions and device type validation routes for BoneIO Web UI."""

from __future__ import annotations

import logging
import os

from fastapi import Body, HTTPException

from boneio.core.config.yaml_util import (
    get_board_config_path,
    load_config_from_file,
    load_yaml_file,
    normalize_board_name,
    normalize_version,
    update_config_section,
)
from boneio.core.manager import Manager
from boneio.webui.action_validation import validate_section_actions as _validate_section_actions
from boneio.webui.routes.config_core import (
    _get_app_state,
    invalidate_config_cache,
    router,
)

_LOGGER = logging.getLogger(__name__)


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


@router.post("/config/quick-action")
async def add_quick_action(payload: dict = Body(...)):
    """Add a single action to an input's click type without full section save."""
    entity_id = payload.get("entity_id", "").strip()
    click_type = payload.get("click_type", "").strip()
    action_type = payload.get("action_type", "output").strip()
    output_id = payload.get("output_id", "").strip()
    cover_id = payload.get("cover_id", "").strip()
    action = payload.get("action", "TOGGLE").strip()
    remote_device = payload.get("remote_device", "").strip()
    boneio_id = payload.get("boneio_id", "").strip()
    topic = payload.get("topic", "").strip()
    mqtt_msg = payload.get("action_mqtt_msg", "").strip()

    if not entity_id:
        raise HTTPException(status_code=422, detail="entity_id is required")
    if not click_type:
        raise HTTPException(status_code=422, detail="click_type is required")

    valid_click_types = {
        "single", "double", "triple", "long",
        "pressed", "released",
        "double_then_long", "single_then_long", "double_then_single",
    }
    if click_type not in valid_click_types:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid click_type: '{click_type}'. Must be one of {sorted(valid_click_types)}",
        )

    valid_action_types = {
        "output", "cover", "remote_output", "remote_cover",
        "mqtt", "output_over_mqtt", "cover_over_mqtt",
    }
    if action_type not in valid_action_types:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid action_type: '{action_type}'. Must be one of {sorted(valid_action_types)}",
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

    try:
        app_state = _get_app_state()
        config = load_yaml_file(app_state.yaml_config_file)

        section = None
        input_index = None
        for sec_name in ("event", "binary_sensor", "remote_inputs"):
            entries = config.get(sec_name, [])
            if isinstance(entries, list):
                for idx, entry in enumerate(entries):
                    if isinstance(entry, dict):
                        eid = entry.get("id", entry.get("pin", ""))
                        boneio_in = entry.get("boneio_input", "")
                        if (
                            str(eid) == entity_id
                            or str(eid).lower() == entity_id.lower()
                            or str(boneio_in).lower() == entity_id.lower()
                        ):
                            section = sec_name
                            input_index = idx
                            break
            if section:
                break

        if section is None or input_index is None:
            _LOGGER.warning(
                "Quick action: input '%s' not found. Available sections: %s",
                entity_id,
                {s: len(config.get(s, [])) for s in ("event", "binary_sensor", "remote_inputs")},
            )
            raise HTTPException(
                status_code=404,
                detail=f"Input '{entity_id}' not found in event, binary_sensor, or remote_inputs sections",
            )

        entries = config[section]
        entry = entries[input_index]

        if section in ("event", "remote_inputs"):
            for act_type in (
                "single", "double", "triple", "long",
                "double_then_long", "single_then_long", "double_then_single",
            ):
                flat_key = f"actions_{act_type}"
                if flat_key in entry:
                    if "actions" not in entry or not isinstance(entry.get("actions"), dict):
                        entry["actions"] = {}
                    existing = entry["actions"].get(act_type, [])
                    entry["actions"][act_type] = existing + entry.pop(flat_key)

        if section == "event":
            if "actions" not in entry or not isinstance(entry.get("actions"), dict):
                entry["actions"] = {}
            if click_type not in entry["actions"]:
                entry["actions"][click_type] = []
            target_list = entry["actions"][click_type]
        elif section == "remote_inputs":
            mode = entry.get("mode", "event")
            if mode == "binary_sensor":
                actions_key = "actions_on_press" if click_type in ("pressed", "single") else "actions_on_release"
                if actions_key not in entry:
                    entry[actions_key] = []
                target_list = entry[actions_key]
            else:
                if "actions" not in entry or not isinstance(entry.get("actions"), dict):
                    entry["actions"] = {}
                if click_type not in entry["actions"]:
                    entry["actions"][click_type] = []
                target_list = entry["actions"][click_type]
        else:
            actions_key = "actions_on_press" if click_type in ("pressed", "single") else "actions_on_release"
            if actions_key not in entry:
                entry[actions_key] = []
            target_list = entry[actions_key]

        for existing in target_list:
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

        target_list.append(new_action)
        entries[input_index] = entry

        errors = _validate_section_actions(section, entries)
        if errors:
            raise HTTPException(
                status_code=422,
                detail={"message": "Invalid action configuration", "errors": errors},
            )

        result = update_config_section(app_state.yaml_config_file, section, entries)
        if result["status"] == "error":
            raise HTTPException(status_code=500, detail=result["message"])

        invalidate_config_cache()

        try:
            manager: Manager = app_state.manager
            input_device = manager.inputs._inputs.get(entity_id.lower())
            if input_device:
                raw_actions = entry.get("actions", {})
                parsed = manager.parse_actions(
                    getattr(input_device, "pin", entity_id), raw_actions
                )
                input_device.set_actions(actions=parsed)
                _LOGGER.info("Hot-updated actions for input %s", entity_id)
            else:
                _LOGGER.debug(
                    "Input %s not in memory — actions will apply after restart",
                    entity_id,
                )
        except Exception as hot_err:
            _LOGGER.warning("Quick action saved but hot-update failed: %s", hot_err)

        _LOGGER.info(
            "Quick action added: %s -> %s -> %s %s (%s) [section=%s]",
            entity_id, click_type, action_type, output_id or cover_id, action, section,
        )

        return {
            "status": "ok",
            "message": f"Action added to {entity_id} ({click_type})",
            "section": section,
            "click_type": click_type,
        }

    except HTTPException:
        raise
    except Exception as e:
        _LOGGER.error("Error adding quick action: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error adding quick action: {e}") from e
