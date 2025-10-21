"""Helper dir for BoneIO.

DEPRECATED: This module provides backward compatibility.
New code should import from boneio.core.* instead.
"""

from boneio.helper.async_updater import AsyncUpdater
from boneio.helper.click_timer import ClickTimer
from boneio.helper.exceptions import (
    CoverConfigurationException,
    GPIOInputException,
    GPIOOutputException,
    I2CError,
)
from boneio.helper.ha_discovery import (
    ha_adc_sensor_availabilty_message,
    ha_binary_sensor_availabilty_message,
    ha_button_availabilty_message,
    ha_event_availabilty_message,
    ha_led_availabilty_message,
    ha_light_availabilty_message,
    ha_sensor_availabilty_message,
    ha_sensor_ina_availabilty_message,
    ha_sensor_temp_availabilty_message,
    ha_switch_availabilty_message,
)
from boneio.helper.mqtt import BasicMqtt
from boneio.helper.oled import make_font
from boneio.helper.queue import UniqueQueue
from boneio.helper.stats import HostData

# Re-export from new locations for backward compatibility
from boneio.core.state import StateManager
from boneio.core.utils import TimePeriod, callback
from boneio.core.config.yaml_util import (
    CustomValidator,
    load_config_from_file,
    load_config_from_string,
    load_yaml_file,
    schema_file,
)

__all__ = [
    "CustomValidator",
    "load_yaml_file",
    "HostData",
    "setup_input",
    "setup_output",
    "edge_detect",
    "read_input",
    "write_output",
    "make_font",
    "ha_light_availabilty_message",
    "ha_switch_availabilty_message",
    "ha_sensor_availabilty_message",
    "ha_adc_sensor_availabilty_message",
    "ha_sensor_temp_availabilty_message",
    "ha_binary_sensor_availabilty_message",
    "ha_button_availabilty_message",
    "ha_sensor_ina_availabilty_message",
    "ha_event_availabilty_message",
    "ha_led_availabilty_message",
    "CoverConfigurationException",
    "GPIOInputException",
    "GPIOOutputException",
    "I2CError",
    "GpioBaseClass",
    "StateManager",
    "configure_pin",
    "BasicMqtt",
    "AsyncUpdater",
    "UniqueQueue",
    "schema_file",
    "load_config_from_string",
    "load_config_from_file",
    "TimePeriod",
    "callback",
    "is_callback",
    "ClickTimer",
]
