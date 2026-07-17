"""Sensor routes for BoneIO Web UI."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from boneio.core.manager import Manager

_LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["sensors"])


def get_manager():
    """Get manager instance - will be overridden by app initialization."""
    raise NotImplementedError("Manager not initialized")


@router.get("/dallas/available")
async def get_available_dallas_sensors():
    """
    Get list of available Dallas 1-Wire temperature sensors.
    
    Scans for connected DS18B20 and other Dallas sensors.
    
    Returns:
        Dictionary with list of available sensors.
    """
    try:
        from w1thermsensor import W1ThermSensor
        
        sensors = []
        for sensor in W1ThermSensor.get_available_sensors():
            sensors.append({
                "address": sensor.id,
                "type": sensor.type.name if hasattr(sensor.type, 'name') else str(sensor.type),
            })
        
        return {"sensors": sensors, "count": len(sensors)}
    except ImportError:
        _LOGGER.warning("w1thermsensor library not installed")
        return {"sensors": [], "count": 0, "error": "w1thermsensor library not installed"}
    except Exception as e:
        _LOGGER.error(f"Error scanning for Dallas sensors: {e}")
        return {"sensors": [], "count": 0, "error": str(e)}


@router.get("/sensors/loaded")
async def get_loaded_sensors(manager: Manager = Depends(get_manager)):
    """
    Get list of currently loaded sensors.
    
    Returns information about all sensors that are currently active.
    
    Args:
        manager: Manager instance.
        
    Returns:
        Dictionary with sensor information by type.
    """
    result = {
        "dallas": [],
        "temp": [],
        "modbus_temp": [],
        "ina219": [],
        "adc": [],
        "system": [],
    }
    
    # Dallas sensors
    for sensor in manager.sensors.get_dallas_sensors():
        result["dallas"].append({
            "id": sensor.id,
            "name": sensor.name,
            "address": sensor.address if hasattr(sensor, 'address') else None,
            "state": sensor.state,
            "unit": sensor.unit_of_measurement,
            "timestamp": sensor.last_timestamp,
        })
    
    # All temp sensors (includes Dallas + I2C temp sensors)
    for sensor in manager.sensors.get_all_temp_sensors():
        result["temp"].append({
            "id": sensor.id,
            "name": sensor.name,
            "state": sensor.state,
            "unit": sensor.unit_of_measurement,
        })

    # Modbus temperature sensors (CWT, R4DCB08, N4DSC08, boneIO Edge, etc.)
    for coordinator in manager.modbus.get_all_coordinators().values():
        if not coordinator:
            continue
        for entities in coordinator.get_all_entities():
            for entity in entities.values():
                if getattr(entity, '_device_class', None) == "temperature":
                    result["modbus_temp"].append({
                        "id": entity.id,
                        "name": entity.name,
                        "state": entity.state,
                        "unit": entity.unit_of_measurement,
                        "device_group": coordinator.name,
                    })
    
    # INA219 sensors
    for ina_device in manager.sensors.get_ina219_sensors():
        for sensor in ina_device.sensors.values():
            result["ina219"].append({
                "id": sensor.id,
                "name": sensor.name,
                "state": sensor.state,
                "unit": sensor.unit_of_measurement,
            })
    
    # ADC sensors
    for sensor in manager.sensors.get_adc_sensors():
        result["adc"].append({
            "id": sensor.id,
            "name": sensor.name,
            "state": sensor.state,
        })
    
    # System sensors
    for sensor in manager.sensors.get_system_sensors():
        entry: dict = {
            "id": sensor.id,
            "name": sensor.name,
            "state": sensor.state,
            "unit": sensor.unit_of_measurement,
        }
        if hasattr(sensor, "_attributes") and sensor._attributes:
            entry["attributes"] = sensor._attributes
        result["system"].append(entry)
    
    return result


@router.get("/sensors/screen_available")
async def get_screen_available_sensors(manager: Manager = Depends(get_manager)):
    """Get available sensors for OLED extra_screen_sensors configuration.

    Returns modbus coordinators with their sensor entities and dallas sensors
    so the frontend can present selects instead of free-text inputs.

    Returns:
        Dictionary with modbus and dallas sensor lists.
    """
    modbus: list[dict] = []
    if hasattr(manager, "modbus") and hasattr(manager.modbus, "get_all_coordinators"):
        for dev_id, coordinator in manager.modbus.get_all_coordinators().items():
            if not coordinator:
                continue
            entities: list[dict] = []
            for entities_dict in coordinator.get_all_entities():
                for decoded_name, entity in entities_dict.items():
                    entities.append({
                        "decoded_name": decoded_name,
                        "name": entity.name,
                        "unit": entity.unit_of_measurement,
                        "state": entity.state,
                    })
            modbus.append({
                "id": dev_id,
                "name": coordinator.name,
                "model": getattr(coordinator, "_model_name", dev_id),
                "entities": entities,
            })

    dallas: list[dict] = []
    for sensor in manager.sensors.get_dallas_sensors():
        dallas.append({
            "id": sensor.id,
            "name": sensor.name,
            "state": sensor.state,
        })

    return {"modbus": modbus, "dallas": dallas}
