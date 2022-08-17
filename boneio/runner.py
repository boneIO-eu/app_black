"""Runner code for boneIO. Based on HA runner."""
import asyncio
import logging
import os

from boneio.const import (
    ADC,
    COVER,
    DALLAS,
    DS2482,
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
    ONEWIRE,
    OUTPUT,
    PASSWORD,
    PORT,
    SENSOR,
    TOPIC_PREFIX,
    USERNAME,
)
from boneio.helper import StateManager
from boneio.helper.config import ConfigHelper
from boneio.manager import Manager
from boneio.mqtt_client import MQTTClient

_LOGGER = logging.getLogger(__name__)


async def async_run(
    config: dict,
    config_file: str,
    mqttusername: str = "",
    mqttpassword: str = "",
):
    """Run BoneIO."""

    _config_helper = ConfigHelper(
        topic_prefix=config[MQTT].pop(TOPIC_PREFIX),
        ha_discovery=config[MQTT][HA_DISCOVERY].pop(ENABLED),
        ha_discovery_prefix=config[MQTT][HA_DISCOVERY].pop(TOPIC_PREFIX),
    )

    client = MQTTClient(
        host=config[MQTT][HOST],
        username=config[MQTT].get(USERNAME, mqttusername),
        password=config[MQTT].get(PASSWORD, mqttpassword),
        port=config[MQTT].get(PORT, 1883),
        config_helper=_config_helper,
    )

    manager = Manager(
        send_message=client.send_message,
        relay_pins=config.get(OUTPUT, []),
        input_pins=config.get(INPUT, []),
        config_file_path=config_file,
        state_manager=StateManager(
            state_file=f"{os.path.split(config_file)[0]}state.json"
        ),
        config_helper=_config_helper,
        sensors={
            LM75: config.get(LM75, []),
            MCP_TEMP_9808: config.get(MCP_TEMP_9808, []),
            MODBUS: config.get("modbus_sensors"),
            ONEWIRE: config.get(SENSOR, []),
        },
        mcp23017=config.get(MCP23017, []),
        ds2482=config.get(DS2482, []),
        dallas=config.get(DALLAS),
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
