"""
Module to provide basic config options.
"""
from __future__ import annotations
from _collections_abc import dict_values
from typing import Union
from boneio.const import BONEIO, HOMEASSISTANT, LIGHT, SENSOR, COVER, BUTTON, SWITCH, BINARY_SENSOR, EVENT_ENTITY


class ConfigHelper:
    def __init__(
        self,
        topic_prefix: str = BONEIO,
        ha_discovery: bool = True,
        ha_discovery_prefix: str = HOMEASSISTANT,
    ):
        self._topic_prefix = topic_prefix
        self._ha_discovery = ha_discovery
        self._ha_discovery_prefix = ha_discovery_prefix
        self._fetch_old_discovery = None
        self._autodiscovery_messages = {
            SWITCH: {},
            LIGHT: {},
            BINARY_SENSOR: {},
            SENSOR: {},
            COVER: {},
            BUTTON: {},
            EVENT_ENTITY: {}
        }
        self.manager_ready: bool = False

    @property
    def topic_prefix(self) -> str:
        return self._topic_prefix

    @property
    def ha_discovery(self) -> bool:
        return self._ha_discovery

    @property
    def ha_discovery_prefix(self) -> str:
        return self._ha_discovery_prefix

    @property
    def cmd_topic_prefix(self) -> str:
        return f"{self.topic_prefix}/cmd/"

    @property
    def subscribe_topic(self) -> str:
        return f"{self.cmd_topic_prefix}+/+/#"

    def add_autodiscovery_msg(self, ha_type: str, topic: str, payload: Union[str, dict, None]):
        """Add autodiscovery message."""
        self._autodiscovery_messages[ha_type][topic] = {"topic": topic, "payload": payload}

    @property
    def ha_types(self) -> list[str]:
        return list(self._autodiscovery_messages.keys())

    def is_topic_in_autodiscovery(self, topic: str) -> bool:
        topic_parts_raw = topic[len(f"{self._ha_discovery_prefix}/") :].split("/")
        ha_type = topic_parts_raw[0]
        if ha_type in self._autodiscovery_messages:
            if topic in self._autodiscovery_messages[ha_type]:
                return True
        return False
    
    def clear_autodiscovery_type(self, ha_type: str):
        self._autodiscovery_messages[ha_type] = {}



    @property
    def autodiscovery_msgs(self) -> dict_values:
        """Get autodiscovery messages"""
        output = {}
        for ha_type in self._autodiscovery_messages:
            output.update(self._autodiscovery_messages[ha_type])
        return output.values()
