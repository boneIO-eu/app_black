"""Helper dir for BoneIO."""
from typing import Callable, TypeVar, Any

from boneio.helper.gpio import (
    edge_detect,
    setup_input,
    setup_output,
    read_input,
    write_output,
    GpioBaseClass,
    configure_pin,
)
from boneio.helper.oled import make_font
from boneio.helper.mqtt import BasicMqtt
from boneio.helper.stats import HostData, host_stats
from boneio.helper.yaml_util import (
    CustomValidator,
    load_yaml_file,
    schema_file,
    load_config_from_string,
    load_config_from_file,
)
from boneio.helper.state_manager import StateManager
from boneio.helper.ha_discovery import (
    ha_light_availabilty_message,
    ha_switch_availabilty_message,
    ha_sensor_temp_availabilty_message,
    ha_button_availabilty_message,
    ha_binary_sensor_availabilty_message,
    ha_input_availabilty_message,
    ha_sensor_availabilty_message,
    ha_adc_sensor_availabilty_message,
)
from boneio.helper.exceptions import GPIOInputException, I2CError
from boneio.helper.queue import UniqueQueue
from boneio.helper.timeperiod import TimePeriod

CALLABLE_T = TypeVar("CALLABLE_T", bound=Callable[..., Any])
CALLBACK_TYPE = Callable[[], None]


def callback(func: CALLABLE_T) -> CALLABLE_T:
    """Annotation to mark method as safe to call from within the event loop."""
    setattr(func, "_boneio_callback", True)
    return func


def is_callback(func: Callable[..., Any]) -> bool:
    """Check if function is safe to be called in the event loop."""
    return getattr(func, "_boneio_callback", False) is True


__all__ = [
    "CustomValidator",
    "load_yaml_file",
    "HostData",
    "host_stats",
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
    "ha_input_availabilty_message",
    "GPIOInputException",
    "I2CError",
    "GpioBaseClass",
    "StateManager",
    "configure_pin",
    "BasicMqtt",
    "UniqueQueue",
    "schema_file",
    "load_config_from_string",
    "load_config_from_file",
    "TimePeriod",
]
