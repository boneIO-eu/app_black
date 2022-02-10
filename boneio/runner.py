"""Runner code for boneIO. Based on HA runner."""
import asyncio
import logging

from boneio.const import (
    ADC,
    COVER,
    ENABLED,
    HA_DISCOVERY,
    HOST,
    INPUT,
    LM75,
    MCP23017,
    MCP_TEMP_9808,
    MODBUS,
    MQTT,
    OLED,
    OUTPUT,
    PASSWORD,
    TOPIC_PREFIX,
    USERNAME,
    PAHO,
    PYMODBUS,
)

_LOGGER = logging.getLogger(__name__)
from boneio.helper import StateManager
from boneio.manager import Manager
from boneio.mqtt_client import MQTTClient
from boneio.version import __version__

_nameToLevel = {
    "CRITICAL": logging.CRITICAL,
    "FATAL": logging.FATAL,
    "ERROR": logging.ERROR,
    "WARN": logging.WARNING,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
    "NOTSET": logging.NOTSET,
}


def configure_logger(log_config: dict, debug: int) -> None:
    """Configure logger based on config yaml."""

    def debug_logger():
        if debug == 0:
            logging.getLogger().setLevel(logging.INFO)
        if debug > 0:
            logging.getLogger().setLevel(logging.DEBUG)
            _LOGGER.info("Debug mode active")
            _LOGGER.debug(f"Lib version is {__version__}")
        if debug > 1:
            logging.getLogger(PAHO).setLevel(logging.DEBUG)
            logging.getLogger(PYMODBUS).setLevel(logging.DEBUG)
            logging.getLogger("pymodbus.client").setLevel(logging.DEBUG)

    if not log_config:
        debug_logger()
        return
    default = log_config.get("default", "").upper()
    if default in _nameToLevel:
        _LOGGER.info("Setting default log level to %s", default)
        logging.getLogger().setLevel(_nameToLevel[default])
    for k, v in log_config.get("logs", {}).items():
        logger = logging.getLogger(k)
        val = v.upper()
        if val in _nameToLevel and logger:
            _LOGGER.info("Setting %s log level to %s", k, val)
            logger.setLevel(_nameToLevel[val])
    debug_logger()


async def async_run(
    config: dict,
    config_path: str,
    mqttusername: str = "",
    mqttpassword: str = "",
):
    """Run BoneIO."""

    client = MQTTClient(
        host=config[MQTT][HOST],
        username=config[MQTT].get(USERNAME, mqttusername),
        password=config[MQTT].get(PASSWORD, mqttpassword),
    )

    manager = Manager(
        send_message=client.send_message,
        topic_prefix=config[MQTT][TOPIC_PREFIX],
        relay_pins=config.get(OUTPUT, []),
        input_pins=config.get(INPUT, []),
        state_manager=StateManager(state_file=f"{config_path[0]}state.json"),
        ha_discovery=config[MQTT][HA_DISCOVERY][ENABLED],
        ha_discovery_prefix=config[MQTT][HA_DISCOVERY][TOPIC_PREFIX],
        sensors={
            LM75: config.get(LM75),
            MCP_TEMP_9808: config.get(MCP_TEMP_9808),
            MODBUS: config.get("modbus_sensors"),
        },
        mcp23017=config.get(MCP23017, []),
        modbus=config.get(MODBUS),
        oled=config.get(OLED),
        adc_list=config.get(ADC, []),
        covers=config.get(COVER, []),
    )
    tasks = set()
    tasks.update(manager.get_tasks())
    _LOGGER.info("Connecting to MQTT.")
    tasks.add(client.start_client(manager))
    return await asyncio.gather(*tasks)
