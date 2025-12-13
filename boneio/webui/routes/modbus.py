"""Modbus routes for BoneIO Web UI."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Protocol, runtime_checkable

from fastapi import APIRouter, Body, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from boneio.core.manager import Manager

_LOGGER = logging.getLogger(__name__)


@runtime_checkable
class WriteableEntity(Protocol):
    """Protocol for entities that support writing values."""
    async def write_value(self, value: float) -> None: ...

router = APIRouter(prefix="/api", tags=["modbus"])

# Lock for serializing Modbus operations
_modbus_helper_lock = asyncio.Lock()

# Cancel flag for search operations
_modbus_search_cancel = False


def get_manager():
    """Get manager instance - will be overridden by app initialization."""
    raise NotImplementedError("Manager not initialized")


class ModbusGetRequest(BaseModel):
    """Request model for Modbus GET operation."""
    address: int
    register_address: int
    register_type: str = "holding"
    value_type: str = "S_WORD"


class ModbusSetRequest(BaseModel):
    """Request model for Modbus SET operation."""
    address: int
    register_address: int
    value: int | float


class ModbusSearchRequest(BaseModel):
    """Request model for Modbus SEARCH operation."""
    register_address: int = 1
    register_type: str = "input"
    start_address: int = 1
    end_address: int = 247
    timeout: float = 0.3


class ModbusConfigureDeviceRequest(BaseModel):
    """Request model for Modbus device configuration."""
    device: str
    uart: str
    current_address: int
    current_baudrate: int
    new_address: int | None = None
    new_baudrate: int | None = None


@router.post("/modbus/{coordinator_id}/{entity_id}/set_value")
async def set_modbus_value(
    coordinator_id: str,
    entity_id: str,
    value_data: dict = Body(...),
    manager: Manager = Depends(get_manager)
):
    """
    Set value for Modbus device entity.
    
    Args:
        coordinator_id: Coordinator ID.
        entity_id: Entity ID.
        value_data: Dictionary with 'value' key.
        
    Returns:
        Status response.
    """
    from fastapi import HTTPException
    
    value = value_data.get("value")
    if value is None:
        raise HTTPException(status_code=400, detail="Value is required")
    
    coordinator = manager.modbus.get_all_coordinators().get(coordinator_id.lower())
    if not coordinator:
        raise HTTPException(status_code=404, detail=f"Modbus coordinator '{coordinator_id}' not found")
    
    entity = coordinator.find_entity(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail=f"Entity '{entity_id}' not found")
    
    if not isinstance(entity, WriteableEntity):
        raise HTTPException(status_code=400, detail=f"Entity '{entity_id}' does not support setting values")
    
    try:
        await entity.write_value(value)
        return {"status": "success", "message": f"Value set to {value}"}
    except Exception as e:
        _LOGGER.error(f"Error setting Modbus value: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/modbus/get")
async def modbus_get(
    request: ModbusGetRequest,
    boneio_manager: Manager = Depends(get_manager)
):
    """
    Read a register from a Modbus device.
    
    Args:
        request: ModbusGetRequest with device address and register info.
        
    Returns:
        Read value or error.
    """
    modbus_client = boneio_manager.modbus.get_modbus_client()
    if not modbus_client:
        return {
            "success": False,
            "error": "Modbus is not configured. Add 'modbus' section to your config.",
        }
    
    async with _modbus_helper_lock:
        try:
            value_size = 1 if request.value_type in ["S_WORD", "U_WORD"] else 2
            if request.value_type in ["U_QWORD", "S_QWORD", "U_QWORD_R"]:
                value_size = 4
            
            result = await modbus_client.read_registers(
                unit=request.address,
                address=request.register_address,
                count=value_size,
                method=request.register_type,
            )
            
            if result and hasattr(result, 'registers'):
                payload = result.registers[0:value_size]
                decoded_value = modbus_client.decode_value(payload, request.value_type)
                
                return {
                    "success": True,
                    "value": decoded_value,
                    "raw_registers": list(payload),
                }
            else:
                return {
                    "success": False,
                    "error": "No response from device",
                }
                
        except Exception as e:
            _LOGGER.error(f"Modbus GET error: {e}")
            return {
                "success": False,
                "error": str(e),
            }


@router.post("/modbus/set")
async def modbus_set(
    request: ModbusSetRequest,
    boneio_manager: Manager = Depends(get_manager)
):
    """
    Write to a Modbus device register.
    
    Args:
        request: ModbusSetRequest with device address, register and value.
        
    Returns:
        Success status.
    """
    modbus_client = boneio_manager.modbus.get_modbus_client()
    if not modbus_client:
        return {
            "success": False,
            "error": "Modbus is not configured. Add 'modbus' section to your config.",
        }
    
    async with _modbus_helper_lock:
        try:
            result = await modbus_client.write_register(
                unit=request.address,
                address=request.register_address,
                value=int(request.value),
            )
            
            if result:
                return {
                    "success": True,
                    "message": "Value written successfully.",
                }
            else:
                return {
                    "success": False,
                    "error": "Write operation failed - no response from device",
                }
                
        except Exception as e:
            _LOGGER.error(f"Modbus SET error: {e}")
            return {
                "success": False,
                "error": str(e),
            }


@router.get("/modbus/search/stream")
async def modbus_search_stream(
    start_address: int = 1,
    end_address: int = 247,
    register_address: int = 1,
    register_type: str = "input",
    timeout: float = 0.3,
    boneio_manager: Manager = Depends(get_manager)
):
    """
    Search for Modbus devices with Server-Sent Events.
    
    Args:
        start_address: First address to scan.
        end_address: Last address to scan.
        register_address: Register to read for detection.
        register_type: Type of register.
        timeout: Timeout per device.
        
    Returns:
        SSE stream with progress updates.
    """
    global _modbus_search_cancel
    
    async def event_generator():
        global _modbus_search_cancel
        
        modbus_client = boneio_manager.modbus.get_modbus_client()
        if not modbus_client:
            yield f"data: {json.dumps({'type': 'error', 'error': 'Modbus is not configured'})}\n\n"
            return
        
        _modbus_search_cancel = False
        
        async with _modbus_helper_lock:
            found_devices = []
            total = end_address - start_address + 1
            scanned = 0
            
            yield f"data: {json.dumps({'type': 'start', 'total': total})}\n\n"
            
            for addr in range(start_address, end_address + 1):
                if _modbus_search_cancel:
                    yield f"data: {json.dumps({'type': 'cancelled', 'scanned': scanned, 'total': total, 'devices': found_devices})}\n\n"
                    return
                
                try:
                    found = await modbus_client.scan_device(
                        unit=addr,
                        address=register_address,
                        method=register_type,
                        timeout=timeout,
                    )
                    
                    if found:
                        found_devices.append(addr)
                        _LOGGER.info(f"Found Modbus device at address {addr}")
                        yield f"data: {json.dumps({'type': 'found', 'address': addr, 'devices': list(found_devices), 'scanned': scanned + 1, 'total': total})}\n\n"
                        
                except Exception:
                    pass
                
                scanned += 1
                
                if scanned % 5 == 0:
                    yield f"data: {json.dumps({'type': 'progress', 'scanned': scanned, 'total': total, 'current': addr})}\n\n"
                
                await asyncio.sleep(0.02)
            
            yield f"data: {json.dumps({'type': 'complete', 'devices': found_devices, 'count': len(found_devices), 'scanned': scanned, 'total': total})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@router.post("/modbus/search/cancel")
async def modbus_search_cancel():
    """Cancel an ongoing Modbus search operation."""
    global _modbus_search_cancel
    _modbus_search_cancel = True
    _LOGGER.info("Modbus search cancel requested")
    return {"success": True, "message": "Cancel requested"}


@router.get("/modbus/config")
async def get_modbus_config(boneio_manager: Manager = Depends(get_manager)):
    """Get available Modbus configuration options."""
    modbus_client = boneio_manager.modbus.get_modbus_client()
    
    return {
        "configured": modbus_client is not None,
        "register_types": ["holding", "input"],
        "value_types": [
            "U_WORD", "S_WORD", 
            "U_DWORD", "S_DWORD", "U_DWORD_R", "S_DWORD_R",
            "U_QWORD", "S_QWORD", "U_QWORD_R",
            "FP32", "FP32_R"
        ],
    }


@router.post("/modbus/configure-device")
async def modbus_configure_device(
    request: ModbusConfigureDeviceRequest,
    boneio_manager: Manager = Depends(get_manager)
):
    """
    Configure Modbus device (set new address or baudrate).
    
    Args:
        request: Configuration request.
        
    Returns:
        Success status.
    """
    from boneio.core.utils import open_json
    
    SET_BASE = "set_base"
    
    modbus_client = boneio_manager.modbus.get_modbus_client()
    if not modbus_client:
        return {
            "success": False,
            "error": "Modbus is not configured. Add 'modbus' section to your config.",
        }
    
    async with _modbus_helper_lock:
        original_baudrate = None
        try:
            _LOGGER.info(
                f"Configuring device {request.device} on {request.uart} at address {request.current_address}, "
                f"baudrate {request.current_baudrate}, new_address={request.new_address}, "
                f"new_baudrate={request.new_baudrate}"
            )
            
            if modbus_client.client and hasattr(modbus_client.client, 'baudrate'):
                original_baudrate = modbus_client.client.baudrate
                if original_baudrate != request.current_baudrate:
                    _LOGGER.info(
                        f"Temporarily changing baudrate from {original_baudrate} to {request.current_baudrate}"
                    )
                    if modbus_client.client.connected:
                        modbus_client.client.close()
                    modbus_client.client.baudrate = request.current_baudrate
                    modbus_client.client.connect()
            
            _db = open_json(
                path=os.path.join(os.path.dirname(__file__), "..", "..", "modbus", "devices", "sensors"),
                model=request.device
            )
            set_base = _db.get(SET_BASE, {})
            
            if not set_base:
                return {
                    "success": False,
                    "error_key": "configure_error_no_support",
                    "error_params": {"device": request.device}
                }
            
            if request.new_address is not None:
                address_register = set_base.get("set_address_address")
                if address_register is None:
                    return {
                        "success": False,
                        "error_key": "configure_error_no_address",
                        "error_params": {"device": request.device}
                    }
                
                _LOGGER.info(f"Writing new address {request.new_address} to register {address_register}")
                result = await modbus_client.write_register(
                    unit=request.current_address,
                    address=address_register,
                    value=request.new_address,
                )
                
                if not result:
                    return {
                        "success": False,
                        "error_key": "configure_error_write_address"
                    }
                    
            elif request.new_baudrate is not None:
                baudrate_config = set_base.get("set_baudrate")
                if not baudrate_config:
                    return {
                        "success": False,
                        "error_key": "configure_error_no_baudrate",
                        "error_params": {"device": request.device}
                    }
                
                baudrate_register = baudrate_config.get("address")
                possible_baudrates = baudrate_config.get("possible_baudrates", {})
                baudrate_value = possible_baudrates.get(str(request.new_baudrate))
                
                if baudrate_value is None:
                    return {
                        "success": False,
                        "error_key": "configure_error_baudrate_not_supported",
                        "error_params": {"supported": ", ".join(possible_baudrates.keys())}
                    }
                
                _LOGGER.info(f"Writing baudrate value {baudrate_value} to register {baudrate_register}")
                result = await modbus_client.write_register(
                    unit=request.current_address,
                    address=baudrate_register,
                    value=baudrate_value,
                )
                
                if not result:
                    return {
                        "success": False,
                        "error_key": "configure_error_write_baudrate"
                    }
            else:
                return {
                    "success": False,
                    "error_key": "configure_error_no_operation"
                }
            
            return {
                "success": True,
                "message_key": "configure_success"
            }
                
        except Exception as e:
            _LOGGER.error(f"Modbus configure error: {e}")
            return {
                "success": False,
                "error": str(e),
            }
        finally:
            if original_baudrate is not None and original_baudrate != request.current_baudrate:
                try:
                    _LOGGER.info(f"Restoring original baudrate {original_baudrate}")
                    if modbus_client.client.connected:
                        modbus_client.client.close()
                    modbus_client.client.baudrate = original_baudrate
                    modbus_client.client.connect()
                except Exception as restore_error:
                    _LOGGER.error(f"Failed to restore original baudrate: {restore_error}")
