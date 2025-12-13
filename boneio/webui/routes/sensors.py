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
        result["system"].append({
            "id": sensor.id,
            "name": sensor.name,
            "state": sensor.state,
            "unit": sensor.unit_of_measurement,
        })
    
    return result
