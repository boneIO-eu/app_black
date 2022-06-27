"""
Module to provide basic config options.
"""
from _collections_abc import dict_values

from boneio.const import BONEIO, HOMEASSISTANT


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
        self._autodiscovery_messages = {}

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

    def add_autodiscovery_msg(self, topic: str, payload: str):
        """Add autodiscovery message."""
        self._autodiscovery_messages[topic] = {"topic": topic, "payload": payload}

    @property
    def autodiscovery_msgs(self) -> dict_values:
        """Get autodiscovery messages"""
        return self._autodiscovery_messages.values()
