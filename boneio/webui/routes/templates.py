"""Template entity routes for BoneIO Web UI.

Provides REST API endpoints for controlling template entities:
thermostats, alarm panels, and gate covers.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from boneio.core.manager import Manager

_LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/templates", tags=["templates"])


def get_manager():
    """Get manager instance - will be overridden by app initialization."""
    raise NotImplementedError("Manager not initialized")


# ============================================================================
# List all template entities (for frontend initial load)
# ============================================================================


@router.get("")
async def list_templates(manager: Manager = Depends(get_manager)):
    """Return current state of all template entities.

    Returns:
        Dictionary with thermostats, alarms, and gates arrays.
    """
    thermostats = []
    for t in manager.templates.thermostat_manager.items:
        thermostats.append({
            "id": t.id,
            "name": t.name,
            "mode": t.mode,
            "action": t.action,
            "target_temperature": t.target_temperature,
            "current_temperature": t.current_temperature,
        })

    alarms = []
    for a in manager.templates.alarm_manager.items:
        alarm_data = {
            "id": a.id,
            "name": a.name,
            "state": a.state,
            "allow_frontend_control": a.allow_frontend_control,
            "code_required": len(a.codes) > 0,
            "code_arm_required": a.code_arm_required,
        }
        remaining = a.arming_remaining_s
        if remaining is not None:
            alarm_data["arming_remaining_s"] = remaining
        alarms.append(alarm_data)

    gates = []
    for g in manager.templates.gate_manager.items:
        gates.append({
            "id": g.id,
            "name": g.name,
            "state": g.state,
            "device_class": g.device_class,
            "control_mode": g.control_mode,
        })

    return {"thermostats": thermostats, "alarms": alarms, "gates": gates}


# ============================================================================
# Thermostat control
# ============================================================================


@router.post("/thermostats/{entity_id}/mode")
async def set_thermostat_mode(
    entity_id: str,
    data: dict[str, Any] = Body(...),
    manager: Manager = Depends(get_manager),
):
    """Set thermostat mode (off / heat).

    Args:
        entity_id: Thermostat entity ID.
        data: Body with 'mode' field.

    Returns:
        Status response.
    """
    thermostat = manager.templates.thermostat_manager.get(entity_id)
    if not thermostat:
        raise HTTPException(status_code=404, detail="Thermostat not found")

    mode = data.get("mode", "")
    await thermostat.handle_mode_command("", mode)
    return {"status": "ok", "mode": thermostat.mode}


@router.post("/thermostats/{entity_id}/temperature")
async def set_thermostat_temperature(
    entity_id: str,
    data: dict[str, Any] = Body(...),
    manager: Manager = Depends(get_manager),
):
    """Set thermostat target temperature.

    Args:
        entity_id: Thermostat entity ID.
        data: Body with 'temperature' field.

    Returns:
        Status response.
    """
    thermostat = manager.templates.thermostat_manager.get(entity_id)
    if not thermostat:
        raise HTTPException(status_code=404, detail="Thermostat not found")

    temp = str(data.get("temperature", ""))
    await thermostat.handle_temperature_command("", temp)
    return {"status": "ok", "target_temperature": thermostat.target_temperature}


# ============================================================================
# Alarm panel control
# ============================================================================


@router.post("/alarms/{entity_id}/command")
async def alarm_command(
    entity_id: str,
    data: dict[str, Any] = Body(...),
    manager: Manager = Depends(get_manager),
):
    """Send command to alarm panel (ARM_HOME, ARM_AWAY, ARM_NIGHT, DISARM).

    Args:
        entity_id: Alarm panel entity ID.
        data: Body with 'command' and optional 'code' fields.

    Returns:
        Status response.
    """
    alarm = manager.templates.alarm_manager.get(entity_id)
    if not alarm:
        raise HTTPException(status_code=404, detail="Alarm panel not found")

    if not alarm.allow_frontend_control:
        raise HTTPException(
            status_code=403,
            detail="Frontend control is disabled for this alarm panel",
        )

    import json
    payload = json.dumps({
        "action": data.get("command", ""),
        "code": data.get("code"),
    })
    await alarm.handle_command("", payload)
    return {"status": "ok", "state": alarm.state}


# ============================================================================
# Gate cover control
# ============================================================================


@router.post("/gates/{entity_id}/command")
async def gate_command(
    entity_id: str,
    data: dict[str, Any] = Body(...),
    manager: Manager = Depends(get_manager),
):
    """Send command to gate cover (OPEN, CLOSE, STOP).

    Args:
        entity_id: Gate cover entity ID.
        data: Body with 'command' field.

    Returns:
        Status response.
    """
    gate = manager.templates.gate_manager.get(entity_id)
    if not gate:
        raise HTTPException(status_code=404, detail="Gate cover not found")

    command = data.get("command", "")
    await gate.handle_command("", command)
    return {"status": "ok", "state": gate.state}
