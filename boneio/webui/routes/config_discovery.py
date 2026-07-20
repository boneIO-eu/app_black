"""Home Assistant Discovery, Loxone and Interlock helper routes for BoneIO Web UI."""

from __future__ import annotations

import asyncio
import io
import logging

from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from boneio.core.config.yaml_util import load_config_from_file
from boneio.core.manager import Manager
from boneio.webui.routes.config_core import _get_app_state, router

_LOGGER = logging.getLogger(__name__)


@router.post("/config/remove_ha_discovery")
async def remove_ha_discovery():
    """Remove all Home Assistant discovery entries for this device."""
    manager: Manager = _get_app_state().manager
    config_helper = manager.config_helper

    if not config_helper.ha_discovery:
        raise HTTPException(
            status_code=400,
            detail="HA Discovery is not enabled",
        )

    removed = 0
    for ha_type in config_helper.ha_types:
        topics = dict(config_helper._autodiscovery_messages.get(ha_type, {}))
        for topic in topics:
            _LOGGER.info("Removing HA discovery topic: %s", topic)
            manager.send_message(topic=topic, payload=None, retain=True)
            removed += 1
        config_helper.clear_autodiscovery_type(ha_type)

    manager.send_message(
        topic=f"{config_helper.topic_prefix}/state",
        payload="offline",
        retain=False,
    )

    _LOGGER.info("Removed %d HA discovery topics", removed)
    return {
        "status": "success",
        "removed_topics": removed,
        "message": f"Removed {removed} discovery entries from Home Assistant.",
    }


@router.post("/config/resend_ha_discovery")
async def resend_ha_discovery():
    """Remove and re-send all Home Assistant discovery entries."""
    manager: Manager = _get_app_state().manager
    config_helper = manager.config_helper

    if not config_helper.ha_discovery:
        raise HTTPException(
            status_code=400,
            detail="HA Discovery is not enabled",
        )

    all_messages: list[tuple[str, dict]] = []
    for ha_type in config_helper.ha_types:
        for topic, entry in config_helper._autodiscovery_messages.get(ha_type, {}).items():
            all_messages.append((topic, entry.get("payload")))

    removed = 0
    for topic, _ in all_messages:
        manager.send_message(topic=topic, payload=None, retain=True)
        removed += 1

    resent = 0
    for topic, payload in all_messages:
        if payload:
            manager.send_message(topic=topic, payload=payload, retain=True)
            resent += 1

    async def _delayed_republish():
        await asyncio.sleep(2)
        await manager.republish_all_entity_states()

    asyncio.ensure_future(_delayed_republish())

    _LOGGER.info("HA Discovery resend: removed %d, re-sent %d topics", removed, resent)
    return {
        "status": "success",
        "removed_topics": removed,
        "resent_topics": resent,
        "message": f"Removed {removed} and re-sent {resent} discovery entries.",
    }


@router.get("/interlock-groups")
async def get_interlock_groups():
    """Get list of all registered interlock group names."""
    groups: set[str] = set()

    manager = _get_app_state().manager
    if manager and hasattr(manager, "outputs"):
        output_manager = manager.outputs
        if output_manager and hasattr(output_manager, "_interlock_manager"):
            for g in output_manager._interlock_manager.get_all_groups():
                groups.add(g)

    try:
        config = load_config_from_file(config_file=_get_app_state().yaml_config_file)
        for section_key in ("output", "remote_outputs"):
            for item in (config or {}).get(section_key, []):
                ig = item.get("interlock_group")
                if isinstance(ig, list):
                    for g in ig:
                        if g:
                            groups.add(g)
                elif isinstance(ig, str) and ig:
                    groups.add(ig)
    except Exception:
        pass

    return {"groups": sorted(groups)}


@router.get("/config/lox-template")
async def get_lox_template():
    """Generate and download Lox Config XML template."""
    from boneio.integration.lox_template import generate_lox_template

    manager: Manager = _get_app_state().manager

    try:
        xml_content = generate_lox_template(manager)
        serial = manager.config_helper.serial_number or "boneio"
        filename = f"boneio_{serial}_lox_template.xml"

        return StreamingResponse(
            io.BytesIO(xml_content.encode("utf-8")),
            media_type="application/xml",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except Exception as e:
        _LOGGER.error("Failed to generate Lox template: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate Lox template: {e}") from e


@router.get("/config/lox-commands")
async def get_lox_commands():
    """Get JSON summary of all available Lox UDP commands."""
    from boneio.integration.lox_template import generate_lox_summary

    manager: Manager = _get_app_state().manager

    try:
        return generate_lox_summary(manager)
    except Exception as e:
        _LOGGER.error("Failed to generate Lox commands: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate Lox commands: {e}") from e
