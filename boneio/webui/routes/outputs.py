"""Output and group control routes for BoneIO Web UI."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from boneio.core.manager import Manager

_LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["outputs"])


def get_manager():
    """Get manager instance - will be overridden by app initialization."""
    raise NotImplementedError("Manager not initialized")


@router.post("/outputs/{output_id}/toggle")
async def toggle_output(output_id: str, manager: Manager = Depends(get_manager)):
    """
    Toggle output state.
    
    Args:
        output_id: ID of the output to toggle.
        manager: Manager instance.
        
    Returns:
        Status response with current state or error.
        
    Raises:
        HTTPException: 404 if output not found.
    """
    if output_id not in manager.outputs.get_all_outputs():
        raise HTTPException(status_code=404, detail="Output not found")
    status = await manager.outputs.toggle_output(output_id=output_id)
    if status:
        return {"status": status}
    else:
        return {"status": "error"}


@router.post("/outputs/{output_id}/turn_on")
async def turn_on_output(output_id: str, manager: Manager = Depends(get_manager)):
    """
    Turn on output.
    
    Args:
        output_id: ID of the output to turn on.
        manager: Manager instance.
        
    Returns:
        Status response.
        
    Raises:
        HTTPException: 404 if output not found.
    """
    output = manager.outputs.get_output(output_id)
    if not output:
        raise HTTPException(status_code=404, detail="Output not found")
    await output.async_turn_on()
    return {"status": "ok"}


@router.post("/outputs/{output_id}/turn_off")
async def turn_off_output(output_id: str, manager: Manager = Depends(get_manager)):
    """
    Turn off output.
    
    Args:
        output_id: ID of the output to turn off.
        manager: Manager instance.
        
    Returns:
        Status response.
        
    Raises:
        HTTPException: 404 if output not found.
    """
    output = manager.outputs.get_output(output_id)
    if not output:
        raise HTTPException(status_code=404, detail="Output not found")
    await output.async_turn_off()
    return {"status": "ok"}


@router.post("/groups/{group_id}/toggle")
async def toggle_group(group_id: str, manager: Manager = Depends(get_manager)):
    """
    Toggle output group state.
    
    Args:
        group_id: ID of the output group to toggle.
        manager: Manager instance.
        
    Returns:
        Status response with 'ok' or error.
        
    Raises:
        HTTPException: 404 if output group not found.
    """
    group = manager.outputs.get_output_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Output group not found")
    
    await group.async_toggle()
    return {"status": "ok"}


@router.post("/outputs/{output_id}/set_duration")
async def set_output_duration(
    output_id: str,
    body: dict,
    manager: Manager = Depends(get_manager),
):
    """Set the adjustable duration for an output.

    Args:
        output_id: ID of the output.
        body: Request body with 'value' key (duration in seconds).
        manager: Manager instance.

    Returns:
        Status response with new duration value.

    Raises:
        HTTPException: 404 if output not found, 400 if invalid request.
    """
    output = manager.outputs.get_output(output_id)
    if not output:
        raise HTTPException(status_code=404, detail="Output not found")

    if not output.adjustable_duration_enabled:
        raise HTTPException(status_code=400, detail="Output does not support adjustable duration")

    value = body.get("value")
    if value is None:
        raise HTTPException(status_code=400, detail="Missing 'value' in request body")

    try:
        seconds = int(float(value))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid duration value") from None

    output.set_adjustable_duration(seconds)

    # Persist to state manager (always in seconds)
    manager._state_manager.save_attribute(
        attr_type="adjustable_duration",
        attribute=output_id,
        value=output.adjustable_duration,
    )

    # Publish via MQTT (in the user's selected unit for HA)
    from boneio.const import OUTPUT
    if output.duration_unit == "min":
        publish_value = round(output.adjustable_duration / 60, 2)
    else:
        publish_value = output.adjustable_duration
    manager._message_bus.send_message(
        topic=f"{manager._topic_prefix}/{OUTPUT}/{output_id}/duration",
        payload={"value": publish_value},
        retain=True,
    )

    # Trigger WebSocket state update so frontend gets the new value
    await output.async_send_state()

    return {"status": "ok", "value": output.adjustable_duration}


@router.post("/outputs/{output_id}/set_brightness")
async def set_output_brightness(
    output_id: str,
    body: dict,
    manager: Manager = Depends(get_manager),
):
    """Set brightness on a remote light output.

    Args:
        output_id: ID of the output.
        body: Request body with 'brightness' key (0-255).
        manager: Manager instance.

    Returns:
        Status response with new brightness value.

    Raises:
        HTTPException: 404 if output not found, 400 if invalid request.
    """
    output = manager.outputs.get_output(output_id)
    if not output:
        raise HTTPException(status_code=404, detail="Output not found")

    if not getattr(output, "is_remote", False):
        raise HTTPException(status_code=400, detail="Brightness control only supported for remote outputs")

    brightness = body.get("brightness")
    if brightness is None:
        raise HTTPException(status_code=400, detail="Missing 'brightness' in request body")

    try:
        brightness_int = max(0, min(255, int(float(brightness))))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid brightness value") from None

    if not hasattr(output, "async_set_brightness"):
        raise HTTPException(status_code=400, detail="This output does not support brightness control")

    await output.async_set_brightness(brightness_int)  # type: ignore[attr-defined]

    return {"status": "ok", "brightness": brightness_int}


# ============================================================================
# Generate HA Dashboard YAML for outputs (grouped by area)
# ============================================================================

from collections import defaultdict
from typing import Any

from boneio.const import COVER, LED, LIGHT, NONE, SWITCH, VALVE
from boneio.webui.dashboard_cards import (
    cards_to_yaml,
    heading_card,
    tile_card,
)

# Map output_type -> HA entity type for entity_id construction
_OUTPUT_TYPE_TO_HA_ENTITY = {
    SWITCH: "switch",
    LIGHT: "light",
    LED: "light",
    VALVE: "valve",
}

# Map output_type -> MDI icon for tile cards
_OUTPUT_TYPE_ICON = {
    SWITCH: "mdi:toggle-switch-outline",
    LIGHT: "mdi:lightbulb",
    LED: "mdi:led-on",
    VALVE: "mdi:valve",
}

# Map output_type -> emoji for area heading
_OUTPUT_TYPE_EMOJI = {
    SWITCH: "🔌",
    LIGHT: "💡",
    LED: "💡",
    VALVE: "🚿",
}


def _generate_output_dashboard_cards(
    outputs: dict[str, Any],
    serial: str,
    area_filter: str | None = None,
) -> list[dict]:
    """Generate HA dashboard cards for outputs grouped by area.

    Layout per area:
      1. Heading card with area name (title style)
      2. Sub-heading per output_type (lights, switches, valves)
      3. Tile card per output with toggle action

    Args:
        outputs: Dict of output_id -> output object.
        serial: Device serial number.
        area_filter: Optional area to filter by. None = all areas.

    Returns:
        List of HA card dicts.
    """
    # Group outputs by area, then by output_type
    grouped: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))

    for output_id, output in outputs.items():
        out_type = getattr(output, "output_type", None)
        # Skip types that don't show in HA dashboards
        if out_type in (NONE, COVER, None):
            continue

        area = getattr(output, "area", None) or "other"

        if area_filter and area != area_filter:
            continue

        grouped[area][out_type].append((output_id, output))

    cards: list[dict] = []

    # Sort areas alphabetically, but "other" always last
    sorted_areas = sorted(
        grouped.keys(),
        key=lambda a: (a == "other", a),
    )

    for area in sorted_areas:
        area_types = grouped[area]

        # Area heading
        area_display = area.replace("_", " ").title() if area != "other" else "Other"
        cards.append(heading_card(f"🏠 {area_display}", style="title"))

        # Sort by output_type: lights first, then switches, then valves
        type_order = [LIGHT, LED, SWITCH, VALVE]
        sorted_types = sorted(
            area_types.keys(),
            key=lambda t: type_order.index(t) if t in type_order else 99,
        )

        for out_type in sorted_types:
            output_list = area_types[out_type]

            # Sub-heading for output type
            emoji = _OUTPUT_TYPE_EMOJI.get(out_type, "⚡")
            type_label = out_type.title() if out_type != LED else "LED"
            cards.append(heading_card(
                f"{emoji} {type_label}",
                style="subtitle",
            ))

            # Sort outputs by name for consistent ordering
            output_list.sort(key=lambda x: getattr(x[1], "name", None) or x[0])

            for output_id, output in output_list:
                ha_entity_type = _OUTPUT_TYPE_TO_HA_ENTITY.get(out_type, "switch")
                entity_id = f"{ha_entity_type}.{serial}_{output_id}".lower()
                name = getattr(output, "name", None) or output_id
                icon = _OUTPUT_TYPE_ICON.get(out_type, "mdi:toggle-switch-outline")

                cards.append(tile_card(
                    entity=entity_id,
                    name=name,
                    icon=icon,
                    state_content=["state", "last_changed"],
                ))

    return cards


@router.get("/outputs/dashboard")
async def generate_outputs_dashboard(
    manager: Manager = Depends(get_manager),
    area: str | None = None,
):
    """Generate HA dashboard YAML for outputs grouped by area.

    Args:
        area: Optional area filter. When provided, generates
            dashboard for only that area. Otherwise generates
            for all areas.

    Returns:
        Dict with 'yaml' key containing the dashboard YAML string,
        'areas' list of available area names, and 'outputs_count'.
    """
    serial = manager.config_helper.serial_number
    all_outputs = manager.outputs.get_all_outputs()

    cards = _generate_output_dashboard_cards(all_outputs, serial, area_filter=area)

    if not cards:
        return {
            "yaml": "# No outputs found",
            "areas": [],
            "outputs_count": 0,
        }

    # Collect available areas for UI dropdown
    areas = sorted({
        getattr(o, "area", None) or "other"
        for o in all_outputs.values()
        if getattr(o, "output_type", None) not in (NONE, COVER, None)
    })

    return {
        "yaml": cards_to_yaml(cards),
        "areas": areas,
        "outputs_count": sum(
            1 for o in all_outputs.values()
            if getattr(o, "output_type", None) not in (NONE, COVER, None)
            and (not area or (getattr(o, "area", None) or "other") == area)
        ),
    }
