"""Remote devices routes for BoneIO Web UI."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from boneio.core.manager import Manager

if TYPE_CHECKING:
    pass

_LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/remote-devices", tags=["remote_devices"])


def get_manager():
    """Get manager instance - will be overridden by app initialization."""
    raise NotImplementedError("Manager not initialized")


class RemoteOutputAction(BaseModel):
    """Model for remote output action request."""
    
    action: str  # ON, OFF, TOGGLE


class RemoteCoverAction(BaseModel):
    """Model for remote cover action request."""
    
    action: str  # OPEN, CLOSE, STOP, TOGGLE
    position: int | None = None
    tilt_position: int | None = None


@router.get("")
async def get_remote_devices(manager: Manager = Depends(get_manager)):
    """
    Get all configured remote devices.
    
    Returns:
        List of remote device configurations.
    """
    if not manager.remote_devices:
        return {"devices": []}
    
    return {"devices": list(manager.remote_devices.to_dict().values())}


@router.get("/autodiscovered")
async def get_autodiscovered_devices(manager: Manager = Depends(get_manager)):
    """
    Get all autodiscovered remote devices.
    
    These are BoneIO devices discovered via MQTT autodiscovery (boneio/+/discovery/#).
    Autodiscovered devices can be used for actions without manual configuration.
    
    Returns:
        List of autodiscovered device configurations with their outputs and covers.
    """
    if not manager.remote_devices:
        return {"devices": []}
    
    return {"devices": list(manager.remote_devices.autodiscovered_to_dict().values())}


@router.get("/managed-by")
async def get_managed_by_devices(manager: Manager = Depends(get_manager)):
    """
    Get devices that manage this boneIO.
    
    These are other BoneIO devices that have configured this device as a remote device.
    They publish to boneio/{this_device}/discovery/managed_by/{their_serial}.
    
    Returns:
        List of devices that manage this boneIO.
    """
    if not manager.remote_devices:
        return {"devices": []}
    
    return {"devices": list(manager.remote_devices.get_managed_by_devices().values())}


@router.get("/all")
async def get_all_available_devices(manager: Manager = Depends(get_manager)):
    """
    Get all available remote devices (configured + autodiscovered).
    
    Configured devices take precedence over autodiscovered ones with the same ID.
    
    Returns:
        List of all available device configurations.
    """
    if not manager.remote_devices:
        return {"devices": []}
    
    all_devices = manager.remote_devices.get_all_available_devices()
    return {"devices": [device.to_dict() for device in all_devices.values()]}


@router.get("/{device_id}")
async def get_remote_device(device_id: str, manager: Manager = Depends(get_manager)):
    """
    Get a specific remote device by ID.
    
    Args:
        device_id: ID of the remote device.
        
    Returns:
        Remote device configuration.
        
    Raises:
        HTTPException: 404 if device not found.
    """
    if not manager.remote_devices:
        raise HTTPException(status_code=404, detail="Remote devices not configured")
    
    device = manager.remote_devices.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Remote device not found")
    
    return device.to_dict()


@router.get("/{device_id}/outputs")
async def get_remote_device_outputs(device_id: str, manager: Manager = Depends(get_manager)):
    """
    Get available outputs for a remote device.
    
    Args:
        device_id: ID of the remote device.
        
    Returns:
        List of available outputs.
        
    Raises:
        HTTPException: 404 if device not found.
    """
    if not manager.remote_devices:
        raise HTTPException(status_code=404, detail="Remote devices not configured")
    
    device = manager.remote_devices.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Remote device not found")
    
    return {"outputs": device.outputs}


@router.get("/{device_id}/covers")
async def get_remote_device_covers(device_id: str, manager: Manager = Depends(get_manager)):
    """
    Get available covers for a remote device.
    
    Args:
        device_id: ID of the remote device.
        
    Returns:
        List of available covers.
        
    Raises:
        HTTPException: 404 if device not found.
    """
    if not manager.remote_devices:
        raise HTTPException(status_code=404, detail="Remote devices not configured")
    
    device = manager.remote_devices.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Remote device not found")
    
    return {"covers": device.covers}


@router.post("/{device_id}/output/{output_id}/action")
async def control_remote_output(
    device_id: str,
    output_id: str,
    action_data: RemoteOutputAction,
    manager: Manager = Depends(get_manager),
):
    """
    Control an output on a remote device.
    
    Args:
        device_id: ID of the remote device.
        output_id: ID of the output to control.
        action_data: Action to perform (ON, OFF, TOGGLE).
        
    Returns:
        Status response.
        
    Raises:
        HTTPException: 404 if device not found, 400 if invalid action.
    """
    if not manager.remote_devices:
        raise HTTPException(status_code=404, detail="Remote devices not configured")
    
    action = action_data.action.upper()
    if action not in ["ON", "OFF", "TOGGLE"]:
        raise HTTPException(status_code=400, detail="Invalid action. Must be ON, OFF, or TOGGLE")
    
    success = await manager.remote_devices.control_output(
        device_id=device_id,
        output_id=output_id,
        action=action,
    )
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send command to remote device")
    
    return {"status": "success"}


@router.post("/{device_id}/cover/{cover_id}/action")
async def control_remote_cover(
    device_id: str,
    cover_id: str,
    action_data: RemoteCoverAction,
    manager: Manager = Depends(get_manager),
):
    """
    Control a cover on a remote device.
    
    Args:
        device_id: ID of the remote device.
        cover_id: ID of the cover to control.
        action_data: Action to perform (OPEN, CLOSE, STOP, TOGGLE) and optional position.
        
    Returns:
        Status response.
        
    Raises:
        HTTPException: 404 if device not found, 400 if invalid action.
    """
    if not manager.remote_devices:
        raise HTTPException(status_code=404, detail="Remote devices not configured")
    
    action = action_data.action.upper()
    valid_actions = ["OPEN", "CLOSE", "STOP", "TOGGLE", "TOGGLE_OPEN", "TOGGLE_CLOSE"]
    if action not in valid_actions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid action. Must be one of: {', '.join(valid_actions)}"
        )
    
    kwargs: dict[str, Any] = {}
    if action_data.position is not None:
        kwargs["position"] = action_data.position
    if action_data.tilt_position is not None:
        kwargs["tilt_position"] = action_data.tilt_position
    
    success = await manager.remote_devices.control_cover(
        device_id=device_id,
        cover_id=cover_id,
        action=action,
        **kwargs,
    )
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send command to remote device")
    
    return {"status": "success"}
