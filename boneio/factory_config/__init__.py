"""The configuration a controller starts from, per board revision and type.

``<revision>/<type>/`` holds what a board of that revision and type is set up
with: the system image copies it at build time, and a factory reset copies it
back. Each revision keeps its own copy even where two are identical today,
because the boards are not: 1.1 has a buzzer 1.0 lacks, 0.8 other sensors.

They ship with the app rather than the image so a reset follows the app's
configuration format as it moves on.
"""

from __future__ import annotations

from pathlib import Path

FACTORY_CONFIG_DIR = Path(__file__).parent

#: Revisions older than these have no templates of their own; a reset fits the
#: oldest one to them (see update._adjust_config_for_hardware_version).
OLDEST_REVISION = "0.8"

# Hardware version to sensor mapping
# Different hardware versions have different temperature sensors, power monitoring, and UART for modbus
HARDWARE_SENSORS = {
    "0.2": {"temp_sensor": "mcp9808", "temp_address": 0x18, "has_ina219": False, "power_sensor": None, "modbus_uart": "uart1"},
    "0.3": {"temp_sensor": "mcp9808", "temp_address": 0x18, "has_ina219": False, "power_sensor": None, "modbus_uart": "uart1"},
    "0.4": {"temp_sensor": "lm75", "temp_address": 0x48, "has_ina219": True, "power_sensor": "ina219", "modbus_uart": "uart4"},
    "0.5": {"temp_sensor": "lm75", "temp_address": 0x48, "has_ina219": True, "power_sensor": "ina219", "modbus_uart": "uart4"},
    "0.6": {"temp_sensor": "lm75", "temp_address": 0x48, "has_ina219": True, "power_sensor": "ina219", "modbus_uart": "uart4"},
    "0.7": {"temp_sensor": "lm75", "temp_address": 0x48, "has_ina219": True, "power_sensor": "ina219", "modbus_uart": "uart4"},
    "0.8": {"temp_sensor": "lm75", "temp_address": 0x48, "has_ina219": True, "power_sensor": "ina219", "modbus_uart": "uart4"},
    "1.0": {"temp_sensor": "lm75", "temp_address": 0x48, "has_ina219": False, "power_sensor": "ina226", "modbus_uart": "uart4"},
    # 1.1 differs from 1.0 only by the buzzer, which touches neither the
    # sensors nor the UART.
    "1.1": {"temp_sensor": "lm75", "temp_address": 0x48, "has_ina219": False, "power_sensor": "ina226", "modbus_uart": "uart4"},
}

_FOLDERS = {"32_10": "32x10", "24_16": "24x16", "48_4": "48x4"}


def type_folder(normalized_type: str) -> str:
    """The folder name for a board type as normalize_board_name returns it."""
    return _FOLDERS.get(normalized_type, normalized_type)


def template_dir(folder: str, revision: str) -> Path | None:
    """The templates for a board type and revision, or None when there are none.

    Args:
        folder: Type folder, e.g. ``32x10`` or ``cover_mix``.
        revision: Board revision, e.g. ``1.1``.

    Returns:
        The directory, or None when this revision or type has no templates.
    """
    path = FACTORY_CONFIG_DIR / revision / folder
    return path if (path / "config.yaml").is_file() else None
