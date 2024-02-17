"""Runner code for boneIO. Based on HA runner."""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from boneio.const import (
    ADC,
    BINARY_SENSOR,
    COVER,
    DALLAS,
    DS2482,
    ENABLED,
    EVENT_ENTITY,
    HA_DISCOVERY,
    HOST,
    INA219,
    LM75,
    MCP23017,
    MCP_TEMP_9808,
    MODBUS,
    MQTT,
    OLED,
    ONEWIRE,
    OUTPUT,
    OUTPUT_GROUP,
    PASSWORD,
    PCA9685,
    PCF8575,
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

config_modules = [
    {"name": MCP23017, "default": []},
    {"name": PCF8575, "default": []},
    {"name": PCA9685, "default": []},
    {"name": DS2482, "default": []},
    {"name": ADC, "default": []},
    {"name": COVER, "default": []},
    {"name": MODBUS, "default": {}},
    {"name": OLED, "default": {}},
    {"name": DALLAS, "default": None},
    {"name": OUTPUT_GROUP, "default": []},
]


async def async_run(
    config: dict,
    config_file: str,
    mqttusername: str = "",
    mqttpassword: str = "",
) -> list[Any]:
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
    manager_kwargs = {
        item["name"]: config.get(item["name"], item["default"])
        for item in config_modules
    }


    manager = Manager(
        send_message=client.send_message,
        stop_client=client.stop_client,
        mqtt_state=client.state,
        relay_pins=config.get(OUTPUT, []),
        event_pins=config.get(EVENT_ENTITY, []),
        binary_pins=config.get(BINARY_SENSOR, []),
        config_file_path=config_file,
        state_manager=StateManager(
            state_file=f"{os.path.split(config_file)[0]}state.json"
        ),
        config_helper=_config_helper,
        sensors={
            LM75: config.get(LM75, []),
            INA219: config.get(INA219, []),
            MCP_TEMP_9808: config.get(MCP_TEMP_9808, []),
            MODBUS: config.get("modbus_sensors"),
            ONEWIRE: config.get(SENSOR, []),
        },
        **manager_kwargs,
    )
    tasks = set()
    tasks.update(manager.get_tasks())
    _LOGGER.info("Connecting to MQTT.")
    tasks.add(client.start_client(manager))
    return await asyncio.gather(*tasks)
