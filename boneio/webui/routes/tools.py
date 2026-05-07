"""Tools routes for BoneIO Web UI (I2C scan, test-action, etc.)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from boneio.core.manager import Manager

_LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["tools"])


def get_manager():
    """Get manager instance - will be overridden by app initialization."""
    raise NotImplementedError("Manager not initialized")


class TestActionRequest(BaseModel):
    """Request body for testing a single action.

    The action dict uses the same format as YAML config actions,
    e.g. {"action": "output", "boneio_output": "light_kitchen", "action_output": "TOGGLE"}
    """

    action: dict[str, Any]


@router.post("/test-action")
async def test_action(
    request: TestActionRequest,
    manager: Manager = Depends(get_manager),
):
    """Execute a single action for testing purposes.

    Parses the action through the same code path as real button presses
    (manager.parse_actions → manager.execute_actions) so the test is
    identical to production behaviour.

    Args:
        request: Action definition dict (same format as YAML config).
        manager: Manager instance.

    Returns:
        Status response with success or error detail.

    Raises:
        HTTPException: 400 if action is invalid, 500 if execution fails.
    """
    action_def = request.action
    action_type = action_def.get("action")
    if not action_type:
        raise HTTPException(status_code=400, detail="Missing 'action' field")

    _LOGGER.info("Test-action request: %s", action_def)

    # Wrap single action in the format parse_actions expects:
    # {"<click_type>": [<action_def>, ...]}
    fake_actions = {"single": [action_def]}

    try:
        parsed = manager.parse_actions(pin="__test__", actions=fake_actions)
    except Exception as e:
        _LOGGER.warning("Test-action parse error: %s", e)
        raise HTTPException(status_code=400, detail=f"Failed to parse action: {e}") from None

    actions_list = parsed.get("single", [])
    if not actions_list:
        raise HTTPException(
            status_code=400,
            detail="Action could not be resolved. Check that the target entity exists and is saved.",
        )

    try:
        await manager.execute_actions(actions=actions_list)
    except Exception as e:
        _LOGGER.error("Test-action execution error: %s", e)
        raise HTTPException(status_code=500, detail=f"Action execution failed: {e}") from None

    return {"status": "success"}

# boneIO Black on-board I2C devices (from schema.yaml)
# For these addresses we show ONLY the boneIO device, no alternatives.
BONEIO_I2C_DEVICES: dict[int, str] = {
    0x18: "MCP9808 temp sensor (boneIO on-board) / DS2482 1-wire bridge",
    0x20: "MCP23017 GPIO expander (boneIO on-board)",
    0x21: "MCP23017 GPIO expander (boneIO on-board)",
    0x22: "MCP23017 GPIO expander",
    0x23: "MCP23017 GPIO expander",
    0x24: "MCP23017 GPIO expander",
    0x25: "MCP23017 GPIO expander",
    0x26: "MCP23017 GPIO expander",
    0x27: "MCP23017 GPIO expander",
    0x40: "INA219 current/voltage/power sensor (boneIO on-board)",
    0x48: "LM75 temp sensor (boneIO on-board)",
}

# Known I2C device addresses and their descriptions
# Sources: Linux kernel docs, Adafruit, various datasheets
# Addresses present in BONEIO_I2C_DEVICES are excluded from this map
# because they are identified as boneIO hardware.
I2C_KNOWN_DEVICES: dict[int, list[str]] = {
    0x28: ["BNO055 IMU"],
    0x29: ["VL53L0X distance sensor", "TSL2591 light sensor", "BNO055 IMU"],
    0x38: ["AHT10/AHT20 temp+humidity", "PCF8574A GPIO expander", "FT6236 touch"],
    0x39: ["APDS-9960 gesture sensor", "TSL2561 light sensor", "PCF8574A GPIO expander"],
    0x3A: ["PCF8574A GPIO expander"],
    0x3B: ["PCF8574A GPIO expander"],
    0x3C: ["SSD1306 OLED display (128x64)", "SH1106 OLED display"],
    0x3D: ["SSD1306 OLED display (128x32)"],
    0x3E: ["PCF8574A GPIO expander"],
    0x3F: ["PCF8574A GPIO expander (LCD)"],
    0x41: ["INA219 current sensor", "PCA9685 PWM driver", "STMPE610 touch"],
    0x44: ["SHT30/SHT31 temp+humidity", "ISL29125 color sensor"],
    0x45: ["SHT30/SHT31 temp+humidity"],
    0x49: ["ADS1115 ADC", "TMP102 temp sensor", "LM75 (alt addr)"],
    0x4A: ["ADS1115 ADC", "MAX44009 light sensor", "LM75 (alt addr)"],
    0x4B: ["ADS1115 ADC", "LM75 (alt addr)"],
    0x4C: ["LM75 (alt addr)"],
    0x4D: ["LM75 (alt addr)"],
    0x4E: ["LM75 (alt addr)"],
    0x4F: ["LM75 (alt addr)"],
    0x50: ["AT24C32/AT24C256 EEPROM", "MB85RC256V FRAM"],
    0x51: ["AT24C32 EEPROM", "PCF8563 RTC"],
    0x52: ["AT24C32 EEPROM"],
    0x53: ["ADXL345 accelerometer", "AT24C32 EEPROM"],
    0x57: ["AT24C32 EEPROM (DS3231 module)", "MAX30102 pulse oximeter"],
    0x58: ["SGP30 air quality"],
    0x5A: ["MLX90614 IR temp", "MPR121 touch sensor", "CCS811 air quality"],
    0x5B: ["MPR121 touch sensor", "CCS811 air quality"],
    0x5C: ["BH1750 light sensor", "AM2320 temp+humidity"],
    0x60: ["MCP4725 DAC", "ATECC608A crypto", "SI1145 UV sensor"],
    0x61: ["MCP4725 DAC"],
    0x62: ["SCD40/SCD41 CO2 sensor"],
    0x68: ["DS3231 RTC", "MPU6050/MPU9250 IMU", "DS1307 RTC", "PCF8523 RTC"],
    0x69: ["MPU6050/MPU9250 IMU"],
    0x70: ["PCA9685 PWM driver (all-call)"],
    0x76: ["BME280/BMP280 temp+pressure", "BME680 air quality", "MS5611 pressure"],
    0x77: ["BME280/BMP280 temp+pressure", "BME680 air quality", "BMP180 pressure"],
}


class I2CDevice(BaseModel):
    """Represents a detected I2C device."""

    address: int
    address_hex: str
    known_devices: list[str]
    is_boneio: bool = False


class I2CScanResponse(BaseModel):
    """Response from I2C bus scan."""

    bus: int
    devices: list[I2CDevice]
    raw_output: str
    error: str | None = None


@router.get("/i2c/scan")
async def scan_i2c(bus: int = 2) -> I2CScanResponse:
    """
    Scan I2C bus using i2cdetect and identify known devices.

    Args:
        bus: I2C bus number to scan (default: 2 for boneIO Black).

    Returns:
        I2CScanResponse with detected devices and raw output.
    """
    cmd = ["i2cdetect", "-y", "-r", str(bus)]
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_msg = stderr.decode().strip() if stderr else f"i2cdetect exited with code {process.returncode}"
            _LOGGER.warning("i2cdetect failed on bus %d: %s", bus, error_msg)
            return I2CScanResponse(bus=bus, devices=[], raw_output="", error=error_msg)

        raw_output = stdout.decode()
        devices = _parse_i2cdetect_output(raw_output)

        return I2CScanResponse(bus=bus, devices=devices, raw_output=raw_output)

    except FileNotFoundError:
        error_msg = "i2cdetect not found. Install i2c-tools package."
        _LOGGER.warning(error_msg)
        return I2CScanResponse(bus=bus, devices=[], raw_output="", error=error_msg)
    except Exception as e:
        _LOGGER.warning("Error scanning I2C bus %d: %s", bus, e)
        raise HTTPException(status_code=500, detail=str(e)) from None


def _parse_i2cdetect_output(output: str) -> list[I2CDevice]:
    """
    Parse i2cdetect output and identify devices.

    The output format is a grid where detected addresses show as hex values
    and undetected ones show as '--'.

    Args:
        output: Raw stdout from i2cdetect -y -r <bus>.

    Returns:
        List of I2CDevice objects for detected addresses.
    """
    devices = []
    for line in output.strip().split("\n"):
        # Skip header line (starts with spaces and column numbers)
        if not line or line.startswith(" "):
            continue
        # Each data line starts with "XX:" where XX is the row base address
        parts = line.split(":")
        if len(parts) != 2:
            continue
        try:
            row_base = int(parts[0].strip(), 16)
        except ValueError:
            continue

        cells = parts[1].split()
        for _col, cell in enumerate(cells):
            cell = cell.strip()
            if cell == "--" or cell == "UU" or not cell:
                continue
            try:
                addr = int(cell, 16)
            except ValueError:
                continue

            # boneIO on-board devices take priority — show only boneIO name
            if addr in BONEIO_I2C_DEVICES:
                devices.append(
                    I2CDevice(
                        address=addr,
                        address_hex=f"0x{addr:02X}",
                        known_devices=[BONEIO_I2C_DEVICES[addr]],
                        is_boneio=True,
                    )
                )
            else:
                devices.append(
                    I2CDevice(
                        address=addr,
                        address_hex=f"0x{addr:02X}",
                        known_devices=I2C_KNOWN_DEVICES.get(addr, []),
                    )
                )

    return devices
