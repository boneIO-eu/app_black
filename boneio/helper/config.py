"""
Module to provide basic config options.
"""
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
