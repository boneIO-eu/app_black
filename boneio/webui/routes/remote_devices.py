"""Remote devices routes for BoneIO Web UI."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from boneio.core.manager import Manager
from boneio.core.remote.esphome import (
    discover_esphome_entities, 
    scan_esphome_devices,
    ESPHOME_API_AVAILABLE,
    ZEROCONF_AVAILABLE,
)

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
        _LOGGER.debug("No remote_devices manager")
        return {"devices": []}
    
    devices = manager.remote_devices.autodiscovered_to_dict()
    _LOGGER.debug("Autodiscovered devices: %s", list(devices.keys()))
    return {"devices": list(devices.values())}


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


class ESPHomeDiscoverRequest(BaseModel):
    """Model for ESPHome discovery request."""
    
    host: str
    port: int = 6053
    password: str = ""
    encryption_key: str = ""


@router.post("/discover-esphome")
async def discover_esphome(request: ESPHomeDiscoverRequest):
    """
    Discover entities on an ESPHome device.
    
    Connects to the ESPHome device via native API and retrieves
    available switches, lights, and covers with their capabilities.
    
    Args:
        request: ESPHome connection parameters (host, port, password, encryption_key)
        
    Returns:
        Dictionary with 'switches', 'lights', 'covers' lists.
        Each entity includes id, name, key, and capability flags.
        
    Raises:
        HTTPException: 400 if aioesphomeapi not installed, 500 if discovery fails.
    """
    if not ESPHOME_API_AVAILABLE:
        raise HTTPException(
            status_code=400, 
            detail="aioesphomeapi not installed - ESPHome API support disabled"
        )
    
    _LOGGER.info("Discovering ESPHome entities at %s:%d", request.host, request.port)
    
    result = await discover_esphome_entities(
        host=request.host,
        port=request.port,
        password=request.password,
        encryption_key=request.encryption_key,
    )
    
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    
    _LOGGER.info(
        "Discovered %d switches, %d lights, %d covers at %s",
        len(result.get("switches", [])),
        len(result.get("lights", [])),
        len(result.get("covers", [])),
        request.host
    )
    
    return result


@router.get("/scan-esphome")
async def scan_esphome_network(timeout: float = 3.0):
    """
    Scan the local network for ESPHome devices using mDNS.
    
    Args:
        timeout: How long to scan in seconds (default 3.0, max 10.0)
        
    Returns:
        Dictionary with 'devices' list containing found devices.
        Each device has 'name', 'host', 'ip', 'port' fields.
        
    Raises:
        HTTPException: 400 if zeroconf not installed, 500 if scan fails.
    """
    if not ZEROCONF_AVAILABLE:
        raise HTTPException(
            status_code=400, 
            detail="zeroconf not installed - mDNS discovery disabled"
        )
    
    # Limit timeout to reasonable range
    timeout = min(max(timeout, 1.0), 10.0)
    
    _LOGGER.info("Scanning network for ESPHome devices (timeout: %.1fs)", timeout)
    
    result = await scan_esphome_devices(timeout=timeout)
    
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    
    _LOGGER.info("Found %d ESPHome device(s)", len(result.get("devices", [])))
    
    return result


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
