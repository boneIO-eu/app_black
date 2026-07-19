"""MQTT reference routes for BoneIO Web UI.

Provides per-entity MQTT topic documentation that can be consumed by:
- Frontend (long-press → MQTT Reference dialog)
- Future MCP tool endpoints
- External documentation generators
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from boneio.components.output.basic import BasicOutput
from boneio.const import COVER, OUTPUT
from boneio.core.manager import Manager

_LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["mqtt_reference"])


def get_manager() -> Manager:
    """Get manager instance - will be overridden by app initialization."""
    raise NotImplementedError("Manager not initialized")


def _build_output_reference(
    entity_id: str,
    entity_name: str,
    output_type: str,
    topic_prefix: str,
    is_group: bool = False,
    has_brightness: bool = False,
    has_adjustable_duration: bool = False,
    duration_unit: str = "s",
) -> dict[str, Any]:
    """Build MQTT reference for an output or output group.

    Args:
        entity_id: Output entity ID.
        entity_name: Human-readable name.
        output_type: HA type (switch, light, valve).
        topic_prefix: MQTT topic prefix (e.g. 'boneio/serial').
        is_group: Whether this is an output group.
        has_brightness: Whether the output supports brightness control.
        has_adjustable_duration: Whether the output has adjustable duration.
        duration_unit: Unit for adjustable duration ('s' or 'min').

    Returns:
        Structured MQTT reference dictionary.
    """
    msg_type = "group" if is_group else "output"

    publish: list[dict[str, str]] = [
        {
            "action": "turn_on",
            "topic": f"{topic_prefix}/cmd/{msg_type}/{entity_id}/set",
            "payload": "ON",
            "description": "Turn on the output",
        },
        {
            "action": "turn_off",
            "topic": f"{topic_prefix}/cmd/{msg_type}/{entity_id}/set",
            "payload": "OFF",
            "description": "Turn off the output",
        },
        {
            "action": "toggle",
            "topic": f"{topic_prefix}/cmd/{msg_type}/{entity_id}/set",
            "payload": "TOGGLE",
            "description": "Toggle the output state",
        },
    ]

    if has_brightness:
        publish.append({
            "action": "set_brightness",
            "topic": f"{topic_prefix}/cmd/output/{entity_id}/set_brightness",
            "payload": "0-255",
            "description": "Set brightness (0=off, 255=max)",
        })

    if has_adjustable_duration:
        unit_label = "minutes" if duration_unit == "min" else "seconds"
        publish.append({
            "action": "set_duration",
            "topic": f"{topic_prefix}/cmd/output/{entity_id}/set_duration",
            "payload": f"<number in {unit_label}>",
            "description": f"Set auto-off duration ({unit_label})",
        })

    subscribe: list[dict[str, str]] = [
        {
            "topic": f"{topic_prefix}/{msg_type}/{entity_id}",
            "payload_format": '{"state": "ON"} | {"state": "OFF"}',
            "description": "State change notifications (retained)",
        },
    ]

    if has_adjustable_duration:
        subscribe.append({
            "topic": f"{topic_prefix}/output/{entity_id}/duration",
            "payload_format": '{"value": <number>}',
            "description": "Current duration value (retained)",
        })

    return {
        "entity_id": entity_id,
        "entity_type": "output_group" if is_group else "output",
        "entity_name": entity_name,
        "output_type": output_type,
        "mqtt_enabled": True,
        "publish": publish,
        "subscribe": subscribe,
    }


def _build_cover_reference(
    entity_id: str,
    entity_name: str,
    topic_prefix: str,
    supports_tilt: bool = False,
) -> dict[str, Any]:
    """Build MQTT reference for a cover.

    Args:
        entity_id: Cover entity ID.
        entity_name: Human-readable name.
        topic_prefix: MQTT topic prefix.
        supports_tilt: Whether the cover supports tilt control.

    Returns:
        Structured MQTT reference dictionary.
    """
    publish: list[dict[str, str]] = [
        {
            "action": "open",
            "topic": f"{topic_prefix}/cmd/cover/{entity_id}/set",
            "payload": "OPEN",
            "description": "Open the cover",
        },
        {
            "action": "close",
            "topic": f"{topic_prefix}/cmd/cover/{entity_id}/set",
            "payload": "CLOSE",
            "description": "Close the cover",
        },
        {
            "action": "stop",
            "topic": f"{topic_prefix}/cmd/cover/{entity_id}/set",
            "payload": "STOP",
            "description": "Stop the cover movement",
        },
        {
            "action": "toggle",
            "topic": f"{topic_prefix}/cmd/cover/{entity_id}/set",
            "payload": "TOGGLE",
            "description": "Toggle the cover state",
        },
        {
            "action": "set_position",
            "topic": f"{topic_prefix}/cmd/cover/{entity_id}/pos",
            "payload": "0-100",
            "description": "Set cover position (0=closed, 100=open)",
        },
    ]

    if supports_tilt:
        publish.append({
            "action": "set_tilt",
            "topic": f"{topic_prefix}/cmd/cover/{entity_id}/tilt",
            "payload": "0-100",
            "description": "Set tilt position (0=closed, 100=open)",
        })

    subscribe: list[dict[str, str]] = [
        {
            "topic": f"{topic_prefix}/cover/{entity_id}/state",
            "payload_format": "open | closed | opening | closing",
            "description": "Cover state changes (retained)",
        },
        {
            "topic": f"{topic_prefix}/cover/{entity_id}/pos",
            "payload_format": '{"position": 0-100}',
            "description": "Cover position updates (retained)",
        },
    ]

    if supports_tilt:
        subscribe.append({
            "topic": f"{topic_prefix}/cover/{entity_id}/tilt",
            "payload_format": '{"tilt": 0-100}',
            "description": "Tilt position updates (retained)",
        })

    return {
        "entity_id": entity_id,
        "entity_type": "cover",
        "entity_name": entity_name,
        "output_type": "cover",
        "mqtt_enabled": True,
        "publish": publish,
        "subscribe": subscribe,
    }


def _build_input_reference(
    entity_id: str,
    entity_name: str,
    topic_prefix: str,
    input_type: str = "event",
) -> dict[str, Any]:
    """Build MQTT reference for an input (read-only).

    Args:
        entity_id: Input entity ID.
        entity_name: Human-readable name.
        topic_prefix: MQTT topic prefix.
        input_type: Input type (event or binary_sensor).

    Returns:
        Structured MQTT reference dictionary.
    """
    return {
        "entity_id": entity_id,
        "entity_type": "input",
        "entity_name": entity_name,
        "output_type": input_type,
        "mqtt_enabled": True,
        "publish": [],
        "subscribe": [
            {
                "topic": f"{topic_prefix}/input/{entity_id}",
                "payload_format": '{"state": "PRESSED"} | {"state": "RELEASED"}'
                if input_type == "event"
                else '{"state": "ON"} | {"state": "OFF"}',
                "description": "Input state changes (retained)",
            },
        ],
    }


@router.get("/mqtt_reference/{entity_type}/{entity_id}")
async def get_mqtt_reference(
    entity_type: str,
    entity_id: str,
    manager: Manager = Depends(get_manager),
) -> dict[str, Any]:
    """Get MQTT topic reference for an entity.

    Returns structured MQTT publish/subscribe documentation for the
    given entity. Designed to be consumed by the frontend MQTT Reference
    dialog and future MCP tool endpoints.

    Args:
        entity_type: Type of entity (output, output_group, cover, input).
        entity_id: Entity identifier.
        manager: Manager instance.

    Returns:
        MQTT reference dictionary with publish and subscribe topics.

    Raises:
        HTTPException: 404 if entity not found, 400 if MQTT not enabled.
    """
    # Check MQTT is enabled
    if not manager._message_bus:
        raise HTTPException(status_code=400, detail="MQTT is not configured")

    topic_prefix = manager._topic_prefix

    if entity_type == "output":
        output = manager.outputs.get_output(entity_id)
        if not output:
            raise HTTPException(status_code=404, detail=f"Output '{entity_id}' not found")

        # Outputs that belong to covers are controlled via cover topics
        if output.output_type in (COVER, "none"):
            raise HTTPException(
                status_code=400,
                detail=f"Output '{entity_id}' belongs to a cover and is controlled via cover MQTT commands",
            )

        # Check if set_brightness is actually overridden (BasicOutput has a stub)
        _has_real_brightness = (
            output.output_type == "light"
            and type(output).set_brightness is not BasicOutput.set_brightness
        )
        has_brightness = _has_real_brightness
        has_duration = getattr(output, "adjustable_duration_enabled", False)
        duration_unit = getattr(output, "duration_unit", "s")

        return _build_output_reference(
            entity_id=entity_id,
            entity_name=getattr(output, "_name", entity_id),
            output_type=output.output_type,
            topic_prefix=topic_prefix,
            has_brightness=has_brightness,
            has_adjustable_duration=has_duration,
            duration_unit=duration_unit,
        )

    if entity_type == "output_group":
        group = manager.outputs.get_output_group(entity_id)
        if not group:
            raise HTTPException(status_code=404, detail=f"Output group '{entity_id}' not found")

        return _build_output_reference(
            entity_id=entity_id,
            entity_name=getattr(group, "_name", entity_id),
            output_type=group.output_type,
            topic_prefix=topic_prefix,
            is_group=True,
        )

    if entity_type == "cover":
        cover = manager.covers.get_cover(entity_id)
        if not cover:
            raise HTTPException(status_code=404, detail=f"Cover '{entity_id}' not found")

        supports_tilt = hasattr(cover, "set_tilt")

        return _build_cover_reference(
            entity_id=entity_id,
            entity_name=getattr(cover, "_name", entity_id),
            topic_prefix=topic_prefix,
            supports_tilt=supports_tilt,
        )

    if entity_type == "input":
        input_entity = manager.inputs.get_input(entity_id)
        if not input_entity:
            raise HTTPException(status_code=404, detail=f"Input '{entity_id}' not found")

        input_type = getattr(input_entity, "_type", "event")

        return _build_input_reference(
            entity_id=entity_id,
            entity_name=getattr(input_entity, "_name", entity_id),
            topic_prefix=topic_prefix,
            input_type=input_type,
        )

    if entity_type == "remote_outputs":
        output = manager.outputs.get_output(entity_id)
        if not output:
            raise HTTPException(status_code=404, detail=f"Remote output '{entity_id}' not found")

        # Use the explicit supports_brightness flag set at registration time
        has_brightness = getattr(output, "_supports_brightness", False)

        return _build_output_reference(
            entity_id=entity_id,
            entity_name=getattr(output, "_name", entity_id),
            output_type=output.output_type,
            topic_prefix=topic_prefix,
            has_brightness=has_brightness,
        )

    raise HTTPException(status_code=400, detail=f"Unknown entity type: '{entity_type}'")
