"""Modbus routes for BoneIO Web UI."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Protocol, runtime_checkable

from fastapi import APIRouter, Body, Depends, HTTPException
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


class ModbusSetMultipleRequest(BaseModel):
    """Request model for Modbus SET multiple registers operation (FC16).

    Writes a list of 16-bit values to consecutive registers starting
    at ``register_address``.
    """
    address: int
    register_address: int
    values: list[int]


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
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/modbus/get")
async def modbus_get(
    request: ModbusGetRequest,
    boneio_manager: Manager = Depends(get_manager)
):
    """
    Read a register from a Modbus device.
    
    Automatically suspends coordinator polling during the operation
    and uses the direct read path that bypasses suspend checks.
    
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
    
    modbus_client.suspend()
    async with _modbus_helper_lock:
        try:
            value_size = 1 if request.value_type in ["S_WORD", "U_WORD"] else 2
            if request.value_type in ["U_QWORD", "S_QWORD", "U_QWORD_R"]:
                value_size = 4
            
            result = await modbus_client.read_registers_direct(
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
    
    Automatically suspends coordinator polling during the operation.
    
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
    
    modbus_client.suspend()
    async with _modbus_helper_lock:
        try:
            result = await modbus_client.write_register_direct(
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


@router.post("/modbus/set_multiple")
async def modbus_set_multiple(
    request: ModbusSetMultipleRequest,
    boneio_manager: Manager = Depends(get_manager)
):
    """Write multiple registers to a Modbus device (FC16).

    Sends a Write Multiple Registers (FC16) request to write a list
    of 16-bit values to consecutive registers starting at
    ``register_address``.

    Args:
        request: ModbusSetMultipleRequest with device address, starting
            register and list of values.

    Returns:
        Success status with number of registers written.
    """
    modbus_client = boneio_manager.modbus.get_modbus_client()
    if not modbus_client:
        return {
            "success": False,
            "error": "Modbus is not configured. Add 'modbus' section to your config.",
        }

    if not request.values:
        return {
            "success": False,
            "error": "Values list cannot be empty.",
        }

    # Validate each value fits in 16-bit unsigned range
    for i, val in enumerate(request.values):
        if val < 0 or val > 65535:
            return {
                "success": False,
                "error": f"Value at index {i} ({val}) is out of 16-bit range (0-65535).",
            }

    modbus_client.suspend()
    async with _modbus_helper_lock:
        try:
            result = await modbus_client.write_registers_direct(
                unit=request.address,
                address=request.register_address,
                values=request.values,
            )

            if result:
                return {
                    "success": True,
                    "message": f"{len(request.values)} register(s) written successfully (FC16).",
                    "message_key": "write_multiple_success",
                    "count": len(request.values),
                }
            else:
                return {
                    "success": False,
                    "error": "FC16 write operation failed - no response from device",
                }

        except Exception as e:
            _LOGGER.error("Modbus SET_MULTIPLE (FC16) error: %s", e)
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
        
        modbus_client.suspend()
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


@router.post("/modbus/pause")
async def modbus_pause(
    boneio_manager: Manager = Depends(get_manager),
):
    """Suspend coordinator polling.

    Called by the frontend when the Tools Modbus page is opened.
    Coordinators will skip their update cycles until resume is called.
    A safety timeout auto-resumes after 5 minutes.

    Returns:
        Current suspended status.
    """
    modbus_client = boneio_manager.modbus.get_modbus_client()
    if not modbus_client:
        return {"success": False, "error": "Modbus is not configured."}
    modbus_client.suspend()
    return {"success": True, "suspended": True}


@router.post("/modbus/resume")
async def modbus_resume(
    boneio_manager: Manager = Depends(get_manager),
):
    """Resume coordinator polling.

    Called by the frontend when the Tools Modbus page is closed.

    Returns:
        Current suspended status.
    """
    modbus_client = boneio_manager.modbus.get_modbus_client()
    if not modbus_client:
        return {"success": False, "error": "Modbus is not configured."}
    modbus_client.resume()
    return {"success": True, "suspended": False}


@router.get("/modbus/status")
async def modbus_status(
    boneio_manager: Manager = Depends(get_manager),
):
    """Get current Modbus status including suspend state.

    Returns:
        Dictionary with configured and suspended flags.
    """
    modbus_client = boneio_manager.modbus.get_modbus_client()
    coordinators = boneio_manager.modbus.get_all_coordinators()

    polling_status = {
        cid: {
            "name": coord.name,
            "polling_enabled": coord.polling_enabled,
        }
        for cid, coord in coordinators.items()
    }

    return {
        "configured": modbus_client is not None,
        "suspended": modbus_client.is_suspended if modbus_client else False,
        "coordinators": polling_status,
    }


class ModbusPollingRequest(BaseModel):
    """Request model for Modbus polling toggle."""
    enabled: bool


@router.post("/modbus/{coordinator_id}/polling")
async def set_modbus_polling(
    coordinator_id: str,
    request: ModbusPollingRequest,
    manager: Manager = Depends(get_manager),
):
    """Enable or disable polling for a specific Modbus device.

    This is a runtime-only toggle — state does NOT persist across restarts.
    When disabled, the coordinator keeps last known sensor values but
    stops reading registers.

    Args:
        coordinator_id: Modbus coordinator ID.
        request: Body with 'enabled' boolean.

    Returns:
        Updated polling state.
    """
    coordinator = manager.modbus.get_all_coordinators().get(coordinator_id.lower())
    if not coordinator:
        raise HTTPException(
            status_code=404,
            detail=f"Modbus coordinator '{coordinator_id}' not found",
        )

    coordinator.set_polling_enabled(request.enabled)
    _LOGGER.info(
        "Modbus polling for %s set to %s via REST API",
        coordinator_id,
        "enabled" if request.enabled else "disabled",
    )
    return {
        "coordinator_id": coordinator_id,
        "polling_enabled": coordinator.polling_enabled,
    }


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


@router.get("/modbus/models")
async def get_modbus_models():
    """Get all available Modbus models with their capabilities.

    Scans JSON model definition files and extracts capabilities
    based on device_class fields in registers (e.g. temperature, humidity).

    Returns:
        Dictionary mapping model file names to their capabilities.
    """
    devices_dir = os.path.join(
        os.path.dirname(__file__), "..", "..", "modbus", "devices"
    )
    devices_dir = os.path.normpath(devices_dir)
    models: dict[str, dict[str, Any]] = {}

    if not os.path.isdir(devices_dir):
        _LOGGER.warning("Modbus devices directory not found: %s", devices_dir)
        return {"models": models}

    for root, _dirs, files in os.walk(devices_dir):
        for fname in files:
            if not fname.endswith(".json"):
                continue
            model_key = fname[:-5]  # strip .json
            try:
                with open(os.path.join(root, fname)) as fh:
                    db = json.load(fh)
            except Exception as exc:
                _LOGGER.debug("Failed to read model file %s: %s", fname, exc)
                continue

            device_classes: set[str] = set()
            temperature_sensors: list[dict[str, str]] = []
            for reg_base in db.get("registers_base", []):
                for reg in reg_base.get("registers", []):
                    dc = reg.get("device_class")
                    if dc:
                        device_classes.add(dc)
                    # Only include actual measurement sensors, not
                    # config/diagnostic registers (e.g. calibration offsets)
                    entity_category = reg.get("entity_category")
                    if dc == "temperature" and entity_category not in ("config", "diagnostic"):
                        name = reg.get("name", "Temperature")
                        # Match entity ID suffix generation from BaseEntity:
                        # _decoded_name_low = name.replace(" ", "").lower()
                        # _id suffix = _decoded_name_low.replace("_", "")
                        suffix = name.replace(" ", "").lower().replace("_", "")
                        temperature_sensors.append({
                            "name": name,
                            "suffix": suffix,
                        })

            models[model_key] = {
                "display_name": db.get("model", model_key),
                "has_temperature": "temperature" in device_classes,
                "has_humidity": "humidity" in device_classes,
                "has_energy": "energy" in device_classes or "power" in device_classes,
                "device_classes": sorted(device_classes),
                "temperature_sensors": temperature_sensors,
            }

    return {"models": models}


@router.get("/modbus/models/{model_name}/entities")
async def get_model_entities(model_name: str):
    """Get entity names defined in a Modbus model JSON file.

    Reads the model definition and extracts all entity names from
    registers_base and additional_entities sections.

    Args:
        model_name: Model file name (without .json extension).

    Returns:
        List of entity definitions with name and decoded_name.
    """
    devices_dir = os.path.join(
        os.path.dirname(__file__), "..", "..", "modbus", "devices"
    )
    devices_dir = os.path.normpath(devices_dir)

    # Find model JSON file
    filename = f"{model_name}.json"
    db = None
    for root, _dirs, files in os.walk(devices_dir):
        if filename in files:
            try:
                with open(os.path.join(root, filename)) as fh:
                    db = json.load(fh)
                break
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"Failed to read model file: {exc}") from exc

    if db is None:
        raise HTTPException(status_code=404, detail=f"Model '{model_name}' not found")

    entities = []
    seen: set[str] = set()

    # Base register entities
    for reg_base in db.get("registers_base", []):
        for reg in reg_base.get("registers", []):
            name = reg.get("name", "")
            if name:
                decoded_name = name.replace(" ", "").lower()
                entity_type = reg.get("entity_type", "sensor")
                if decoded_name not in seen:
                    seen.add(decoded_name)
                    entities.append({
                        "name": name,
                        "decoded_name": decoded_name,
                        "entity_type": entity_type,
                    })

    # Additional (derived) entities
    # decoded_name comes from their JSON "name" field (same logic as BaseEntity)
    # Skip duplicates — derived entities share label with their source register
    for entity in db.get("additional_entities", []):
        name = entity.get("name", "")
        if name:
            decoded_name = name.replace(" ", "").lower()
            entity_type = entity.get("entity_type", "sensor")
            if decoded_name not in seen:
                seen.add(decoded_name)
                entities.append({
                    "name": name,
                    "decoded_name": decoded_name,
                    "entity_type": entity_type,
                })

    return {"model": model_name, "entities": entities}


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
    
    modbus_client.suspend()
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
            
            devices_dir = os.path.normpath(
                os.path.join(os.path.dirname(__file__), "..", "..", "modbus", "devices")
            )
            device_file = f"{request.device}.json"
            device_path = None
            for root, _dirs, files in os.walk(devices_dir):
                if device_file in files:
                    device_path = root
                    break

            if device_path is None:
                return {
                    "success": False,
                    "error_key": "configure_error_not_found",
                    "error_params": {"device": request.device}
                }

            _db = open_json(
                path=device_path,
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
                result = await modbus_client.write_register_direct(
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
                result = await modbus_client.write_register_direct(
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


@router.get("/modbus/{coordinator_id}/entity_labels")
async def get_entity_labels(
    coordinator_id: str,
    manager: Manager = Depends(get_manager),
):
    """Get custom entity labels for a Modbus coordinator.

    Args:
        coordinator_id: Coordinator ID.

    Returns:
        Dictionary of entity labels.
    """
    coordinator = manager.modbus.get_all_coordinators().get(coordinator_id.lower())
    if not coordinator:
        raise HTTPException(status_code=404, detail=f"Coordinator '{coordinator_id}' not found")

    return {"coordinator_id": coordinator_id, "labels": coordinator.entity_labels}


@router.put("/modbus/{coordinator_id}/entity_labels")
async def set_entity_labels(
    coordinator_id: str,
    labels: dict[str, str] = Body(...),
    manager: Manager = Depends(get_manager),
):
    """Set custom entity labels for a Modbus coordinator.

    Updates labels in running coordinator immediately and saves to YAML config.

    Args:
        coordinator_id: Coordinator ID.
        labels: Dictionary mapping decoded_name to custom label string.

    Returns:
        Confirmation with saved labels.
    """
    from boneio.core.config.yaml_util import update_config_section

    coordinator = manager.modbus.get_all_coordinators().get(coordinator_id.lower())
    if not coordinator:
        raise HTTPException(status_code=404, detail=f"Coordinator '{coordinator_id}' not found")

    # Apply labels to running coordinator immediately
    coordinator.update_entity_labels(labels)

    # Save to YAML config
    try:
        config = manager.config_helper.get_config()
        modbus_devices = config.get("modbus_devices", [])

        # Find matching device config entry
        updated = False
        for device_config in modbus_devices:
            from boneio.const import ADDRESS, ID, MODEL
            has_custom_id = bool(device_config.get(ID))
            if has_custom_id:
                device_id = str(device_config[ID]).replace(" ", "").lower()
            else:
                addr = device_config.get(ADDRESS, "")
                model = device_config.get(MODEL, "")
                device_id = f"{addr}_{model}".lower().replace(" ", "_")

            if device_id == coordinator_id.lower():
                device_config["entity_labels"] = labels if labels else {}
                updated = True
                break

        if not updated:
            raise HTTPException(
                status_code=404,
                detail=f"Device config for '{coordinator_id}' not found in YAML"
            )

        # Write back to YAML
        config_file = manager._config_file_path
        result = update_config_section(config_file, "modbus_devices", modbus_devices)
        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail=result.get("message", "Failed to save config"))

        # Invalidate disk cache and refresh in-memory config
        from boneio.webui.routes.config import invalidate_config_cache
        invalidate_config_cache()
        manager.config_helper.get_config(force_reload=True)

    except HTTPException:
        raise
    except Exception as e:
        _LOGGER.error("Failed to save entity labels to YAML: %s", e)
        # Labels are already applied in memory, just log the error
        return {
            "coordinator_id": coordinator_id,
            "labels": labels,
            "warning": f"Labels applied but failed to save to YAML: {e}"
        }

    _LOGGER.info("Entity labels saved for %s: %s", coordinator_id, labels)
    return {"coordinator_id": coordinator_id, "labels": labels}


@router.get("/modbus/used-addresses")
async def get_used_addresses(
    manager: Manager = Depends(get_manager),
):
    """Return Modbus addresses currently configured in config.yaml.

    Used by the frontend wizard to prevent address conflicts.
    """
    config = manager.config_helper.get_config()
    used = []
    for device in config.get("modbus_devices", []):
        addr = device.get("address")
        if addr is not None:
            used.append({
                "address": int(addr),
                "model": device.get("model", ""),
                "id": device.get("id", ""),
                "name": device.get("name", ""),
            })
    return {"used_addresses": used}
