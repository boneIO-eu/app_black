"""Modbus routes for BoneIO Web UI."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Protocol, runtime_checkable

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from boneio.core.manager import Manager
from boneio.modbus.client import FC06_MAX, FC06_MIN, fits_register
from boneio.modbus.coordinator import ModbusWriteFailed, ModbusWriteRejected
from boneio.modbus.definition import device_models, load_definition
from boneio.modbus.heat_pump import SCHEMES

_LOGGER = logging.getLogger(__name__)


@runtime_checkable
class WriteableEntity(Protocol):
    """Protocol for entities that support writing values."""
    async def write_value(self, value: float) -> None: ...

router = APIRouter(prefix="/api", tags=["modbus"])

_HEAT_PUMP_FIELDS = frozenset({"mode", "temperature", "dhw_mode", "dhw_temperature"})

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
    register_type: str = "holding"


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


def _heat_pump_coordinator(manager: Manager, coordinator_id: str):
    """The coordinator of a heat pump, or 404 for an unknown one or one without the section."""
    coordinator = manager.modbus.get_all_coordinators().get(coordinator_id.lower())
    if not coordinator:
        raise HTTPException(status_code=404, detail=f"Modbus coordinator '{coordinator_id}' not found")
    if coordinator.definition.heat_pump is None:
        raise HTTPException(status_code=404, detail=f"'{coordinator_id}' is not a heat pump")
    return coordinator


def _refuse_read_only_unit(manager: Manager, unit: int) -> None:
    """A raw Tools write must not reach a device configured read only."""
    for coordinator in manager.modbus.get_all_coordinators().values():
        if coordinator.read_only and str(coordinator.address) == str(unit):
            raise HTTPException(
                status_code=400,
                detail=f"Device {unit} is {coordinator.name}, which is set read only. "
                "Turn read only off in its settings to write to it.",
            )


@router.get("/modbus/{coordinator_id}/heat_pump")
async def get_heat_pump(coordinator_id: str, manager: Manager = Depends(get_manager)):
    """Heat pump scheme, modes, role -> entity id map and thermostat state."""
    coordinator = _heat_pump_coordinator(manager, coordinator_id)
    spec = coordinator.definition.heat_pump

    def entity_id(role: str, ref: str) -> str | None:
        entity = coordinator._role_entity(role, ref)
        return entity.id if entity else None

    roles = {
        role: entity_id(role, ref) if isinstance(ref, str) else [entity_id(role, r) for r in ref]
        for role, ref in spec.roles.items()
    }
    return {
        "scheme": spec.scheme,
        "modes": list(SCHEMES[spec.scheme].modes),
        "roles": roles,
        "state": coordinator.heat_pump_state(),
    }


@router.post("/modbus/{coordinator_id}/heat_pump/{field}")
async def set_heat_pump(
    coordinator_id: str,
    field: str,
    value_data: dict = Body(...),
    manager: Manager = Depends(get_manager),
):
    """Thermostat or hot water command: mode, temperature, dhw_mode or dhw_temperature."""
    if field not in _HEAT_PUMP_FIELDS:
        raise HTTPException(status_code=400, detail=f"Unknown heat pump field '{field}'")
    value = value_data.get("value")
    if value is None:
        raise HTTPException(status_code=400, detail="Value is required")
    coordinator = _heat_pump_coordinator(manager, coordinator_id)
    try:
        await coordinator.set_heat_pump(field, value)
        return {"status": "success", "message": f"{field} set to {value}"}
    except ModbusWriteRejected as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ModbusWriteFailed as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


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
    except ModbusWriteRejected as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ModbusWriteFailed as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
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
    
    _refuse_read_only_unit(boneio_manager, request.address)
    if request.register_type != "coil" and not fits_register(request.value):
        raise HTTPException(
            status_code=400,
            detail=f"{request.value} does not fit one register: allowed {FC06_MIN}..{FC06_MAX}",
        )

    modbus_client.suspend()
    async with _modbus_helper_lock:
        try:
            result = await modbus_client.write_register_direct(
                unit=request.address,
                address=request.register_address,
                value=int(request.value),
                coil=request.register_type == "coil",
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

    _refuse_read_only_unit(boneio_manager, request.address)

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
            "failing": coord.failing,
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
        "register_types": ["holding", "input", "coil", "discrete_input"],
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
    models: dict[str, dict[str, Any]] = {}

    for model_key in device_models():
        try:
            definition = load_definition(model_key)
        except Exception as exc:
            _LOGGER.debug("Failed to read model file %s: %s", model_key, exc)
            continue

        device_classes: set[str] = set()
        temperature_sensors: list[dict[str, str]] = []
        for block in definition.registers_base:
            for reg in block.registers:
                dc = reg.device_class
                if dc:
                    device_classes.add(dc)
                # Only include actual measurement sensors, not
                # config/diagnostic registers (e.g. calibration offsets)
                if dc == "temperature" and reg.entity_category not in ("config", "diagnostic"):
                    # Match entity ID suffix generation from BaseEntity:
                    # _decoded_name_low = name.replace(" ", "").lower()
                    # _id suffix = _decoded_name_low.replace("_", "")
                    temperature_sensors.append({
                        "name": reg.name,
                        "suffix": reg.decoded_name.replace("_", ""),
                    })

        models[model_key] = {
            "display_name": definition.model,
            "has_temperature": "temperature" in device_classes,
            "has_humidity": "humidity" in device_classes,
            "has_energy": "energy" in device_classes or "power" in device_classes,
            "device_classes": sorted(device_classes),
            "temperature_sensors": temperature_sensors,
            "has_heat_pump": definition.heat_pump is not None,
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
    try:
        definition = load_definition(model_name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Model '{model_name}' not found")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read model file: {exc}") from exc

    entities = []
    seen: set[str] = set()

    hidden_registers = {
        reg.decoded_name: reg.hidden
        for block in definition.registers_base
        for reg in block.registers
    }

    # Base register entities
    for block in definition.registers_base:
        for reg in block.registers:
            if reg.name and reg.decoded_name not in seen:
                seen.add(reg.decoded_name)
                entities.append({
                    "name": reg.name,
                    "decoded_name": reg.decoded_name,
                    "entity_type": reg.entity_type,
                    "hidden": reg.hidden,
                })

    # Additional (derived) entities
    # decoded_name comes from their JSON "name" field (same logic as BaseEntity)
    # Skip duplicates — derived entities share label with their source register
    for entity in definition.additional_entities:
        decoded_name = entity.name.replace(" ", "").lower()
        if entity.name and decoded_name not in seen:
            seen.add(decoded_name)
            source = entity.source.replace("_", "") if isinstance(entity.source, str) else None
            entities.append({
                "name": entity.name,
                "decoded_name": decoded_name,
                "entity_type": entity.entity_type,
                # A derived entity is as hidden as the register it reads, and
                # without its own visibility entry it takes the register's.
                "hidden": hidden_registers.get(source, False),
                "source": source if source in hidden_registers else None,
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
            
            try:
                definition = load_definition(request.device)
            except FileNotFoundError:
                return {
                    "success": False,
                    "error_key": "configure_error_not_found",
                    "error_params": {"device": request.device}
                }

            set_base = definition.set_base

            if not set_base:
                return {
                    "success": False,
                    "error_key": "configure_error_no_support",
                    "error_params": {"device": request.device}
                }
            
            if request.new_address is not None:
                address_register = set_base.set_address_address
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
                baudrate_config = set_base.set_baudrate
                if not baudrate_config:
                    return {
                        "success": False,
                        "error_key": "configure_error_no_baudrate",
                        "error_params": {"device": request.device}
                    }
                
                baudrate_register = baudrate_config.address
                possible_baudrates = baudrate_config.possible_baudrates
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


def _config_device_id(device_config: dict) -> str:
    """The coordinator id a ``modbus_devices`` entry runs under."""
    from boneio.const import ADDRESS, ID, MODEL

    if device_config.get(ID):
        return str(device_config[ID]).replace(" ", "").lower()
    addr = device_config.get(ADDRESS, "")
    model = device_config.get(MODEL, "")
    return f"{addr}_{model}".lower().replace(" ", "_")


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
    from boneio.core.config.yaml_util import edit_config_section
    from boneio.webui.routes.config import invalidate_config_cache

    coordinator = manager.modbus.get_all_coordinators().get(coordinator_id.lower())
    if not coordinator:
        raise HTTPException(status_code=404, detail=f"Coordinator '{coordinator_id}' not found")

    # Apply labels to running coordinator immediately
    coordinator.update_entity_labels(labels)

    # From the file: the running config has the schema's defaults filled in,
    # and writing it back put them into the user's file.
    def set_labels(file_config: dict) -> tuple[str, None]:
        for device_config in file_config.get("modbus_devices") or []:
            if isinstance(device_config, dict) and _config_device_id(device_config) == coordinator_id.lower():
                device_config["entity_labels"] = labels if labels else {}
                return "modbus_devices", None
        raise HTTPException(
            status_code=404,
            detail=f"Device config for '{coordinator_id}' not found in YAML"
        )

    try:
        section, section_data, _ = await asyncio.to_thread(
            edit_config_section, manager._config_file_path, set_labels
        )
        invalidate_config_cache(section=section, section_data=section_data)

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
