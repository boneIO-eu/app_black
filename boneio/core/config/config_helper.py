"""
Module to provide basic config options.
"""
from __future__ import annotations

import logging
from _collections_abc import dict_values
from typing import Any

from boneio.const import (
    BINARY_SENSOR,
    BONEIO,
    BUTTON,
    COVER,
    EVENT_ENTITY,
    HOMEASSISTANT,
    LIGHT,
    NUMERIC,
    SELECT,
    SENSOR,
    SWITCH,
    TEXT_SENSOR,
    VALVE,
)
from boneio.core.utils.util import sanitize_mqtt_topic

_LOGGER = logging.getLogger(__name__)


class ConfigHelper:
    def __init__(
        self,
        topic_prefix: str,
        name: str = BONEIO,
        device_type: str = "boneIO Black",
        ha_discovery: bool = True,
        ha_discovery_prefix: str = HOMEASSISTANT,
        network_info: dict = None,
        is_web_active: bool = False,
        config_file_path: str | None = None,
    ):
        self._name = name
        sanitized_topic_prefix = sanitize_mqtt_topic(topic_prefix) if topic_prefix else sanitize_mqtt_topic(name)
        self._topic_prefix = sanitized_topic_prefix
        self._ha_discovery = ha_discovery
        self._ha_discovery_prefix = ha_discovery_prefix
        self._device_type = device_type
        self._fetch_old_discovery = None
        self._autodiscovery_messages = {
            SWITCH: {},
            LIGHT: {},
            BINARY_SENSOR: {},
            SENSOR: {},
            COVER: {},
            BUTTON: {},
            EVENT_ENTITY: {},
            VALVE: {},
            TEXT_SENSOR: {},
            SELECT: {},
            NUMERIC: {},
        }
        self.manager_ready: bool = False
        self._network_info = network_info
        self._is_web_active = is_web_active
        
        # Config caching
        self._config_file_path = config_file_path
        self._config_cache: dict[str, Any] | None = None

    @property
    def network_info(self) -> dict:
        return self._network_info

    @property
    def is_web_active(self) -> bool:
        return self._is_web_active

    @property
    def topic_prefix(self) -> str:
        return self._topic_prefix

    @property
    def name(self) -> str:
        return self._name

    @property
    def ha_discovery(self) -> bool:
        return self._ha_discovery

    @property
    def ha_discovery_prefix(self) -> str:
        return self._ha_discovery_prefix

    @property
    def device_type(self) -> str:
        return self._device_type

    @property
    def cmd_topic_prefix(self) -> str:
        return f"{self.topic_prefix}/cmd/"

    @property
    def subscribe_topic(self) -> str:
        return f"{self.cmd_topic_prefix}+/+/#"

    def add_autodiscovery_msg(self, ha_type: str, topic: str, payload: str | dict | None):
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

    def get_autodiscovery_topics_for_id(self, entity_id: str) -> list[tuple[str, str]]:
        """Get all autodiscovery topics that contain a specific entity ID.
        
        Args:
            entity_id: Entity ID to search for
            
        Returns:
            List of tuples (ha_type, topic) for matching autodiscovery messages
        """
        matching = []
        for ha_type, messages in self._autodiscovery_messages.items():
            for topic in messages.keys():
                # Topic format: homeassistant/{ha_type}/{topic_prefix}/{entity_id}/config
                if f"/{entity_id}/config" in topic:
                    matching.append((ha_type, topic))
        return matching

    def remove_autodiscovery_msg(self, ha_type: str, topic: str):
        """Remove autodiscovery message from internal cache.
        
        Args:
            ha_type: HA entity type
            topic: Discovery topic
        """
        if ha_type in self._autodiscovery_messages and topic in self._autodiscovery_messages[ha_type]:
            del self._autodiscovery_messages[ha_type][topic]

    def get_config(self, force_reload: bool = False) -> dict[str, Any]:
        """Get cached config or load from file if not cached.
        
        Args:
            force_reload: If True, reload config from file even if cached
            
        Returns:
            dict: Configuration dictionary
            
        Raises:
            ValueError: If config_file_path is not set
        """
        if self._config_file_path is None:
            raise ValueError("config_file_path not set in ConfigHelper")
        
        if self._config_cache is None or force_reload:
            from boneio.core.config.yaml_util import load_config_from_file
            _LOGGER.debug("Loading config from file: %s", self._config_file_path)
            self._config_cache = load_config_from_file(self._config_file_path)
        
        return self._config_cache

    def reload_config(self) -> dict[str, Any]:
        """Reload configuration from file and update cache.
        
        Returns:
            dict: Reloaded configuration dictionary
            
        Raises:
            ValueError: If config_file_path is not set
        """
        _LOGGER.info("Reloading config from file: %s", self._config_file_path)
        return self.get_config(force_reload=True)

    def get_section(self, section_name: str, force_reload: bool = False) -> Any:
        """Get a specific configuration section.
        
        Args:
            section_name: Name of the configuration section to retrieve
            force_reload: If True, reload config from file before getting section
            
        Returns:
            Configuration section value (dict, list, or other type)
            
        Raises:
            ValueError: If config_file_path is not set
        """
        config = self.get_config(force_reload=force_reload)
        return config.get(section_name)



    @property
    def autodiscovery_msgs(self) -> dict_values:
        """Get autodiscovery messages"""
        output = {}
        for ha_type in self._autodiscovery_messages:
            output.update(self._autodiscovery_messages[ha_type])
        return output.values()
