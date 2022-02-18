"""Runner code for boneIO. Based on HA runner."""
import asyncio
import logging
import os
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
    PORT,
    TOPIC_PREFIX,
    USERNAME,
)

_LOGGER = logging.getLogger(__name__)
from boneio.helper import StateManager
from boneio.manager import Manager
from boneio.mqtt_client import MQTTClient


async def async_run(
    config: dict,
    config_file: str,
    mqttusername: str = "",
    mqttpassword: str = "",
):
    """Run BoneIO."""

    client = MQTTClient(
        host=config[MQTT][HOST],
        username=config[MQTT].get(USERNAME, mqttusername),
        password=config[MQTT].get(PASSWORD, mqttpassword),
        port=config[MQTT].get(PORT, 1883),
    )

    manager = Manager(
        send_message=client.send_message,
        topic_prefix=config[MQTT][TOPIC_PREFIX],
        relay_pins=config.get(OUTPUT, []),
        input_pins=config.get(INPUT, []),
        config_file_path=config_file,
        state_manager=StateManager(
            state_file=f"{os.path.split(config_file)[0]}state.json"
        ),
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
