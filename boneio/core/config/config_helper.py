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
from boneio.core.system import get_serial_from_mac

_LOGGER = logging.getLogger(__name__)


class ConfigHelper:
    def __init__(
        self,
        name: str = BONEIO,
        device_type: str = "boneIO Black",
        ha_discovery: bool = True,
        ha_discovery_prefix: str = HOMEASSISTANT,
        network_info: dict = {},
        is_web_active: bool = False,
        web_port: int = 8090,
        proxy_port: int | None = None,
        config_file_path: str | None = None,
        send_boneio_autodiscovery: bool = True,
        receive_boneio_autodiscovery: bool = True,
    ):
        self._name = name
        
        # Generate serial number from MAC - always required for topic prefix
        self._serial_no = get_serial_from_mac(network_info)
        
        # Build fixed topic prefix: boneio/blk_{serial}
        # This is no longer configurable - always uses this format
        if self._serial_no:
            self._topic_prefix = f"boneio/{self._serial_no}"
        else:
            # Fallback if MAC not available (should rarely happen)
            self._topic_prefix = "boneio/blk_unknown"
            _LOGGER.warning("Could not determine serial number from MAC, using fallback topic prefix")
        self._ha_discovery = ha_discovery
        self._ha_discovery_prefix = ha_discovery_prefix
        self._send_boneio_autodiscovery = send_boneio_autodiscovery
        self._receive_boneio_autodiscovery = receive_boneio_autodiscovery
        self._device_type = device_type
        self._web_port = web_port
        self._proxy_port = proxy_port
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
        
        # Areas mapping: id -> name
        self._areas: dict[str, str] = {}
        
        # Restart required flag - set when config sections requiring restart are modified
        self._restart_required: bool = False
        self._restart_required_sections: set[str] = set()

    @property
    def restart_required(self) -> bool:
        """Check if application restart is required."""
        return self._restart_required

    @property
    def restart_required_sections(self) -> list[str]:
        """Get list of sections that were modified and require restart."""
        return list(self._restart_required_sections)

    def set_restart_required(self, section: str) -> None:
        """Mark that a restart is required due to changes in given section."""
        self._restart_required = True
        self._restart_required_sections.add(section)
        _LOGGER.warning(
            "Restart required: section '%s' was modified. Total sections requiring restart: %s",
            section,
            list(self._restart_required_sections)
        )

    def clear_restart_required(self) -> None:
        """Clear restart required flag (called after restart)."""
        self._restart_required = False
        self._restart_required_sections.clear()

    @property
    def network_info(self) -> dict:
        return self._network_info

    @property
    def is_web_active(self) -> bool:
        return self._is_web_active

    @property
    def web_port(self) -> int:
        return self._web_port

    @property
    def serial_number(self) -> str:
        return self._serial_no

    @property
    def proxy_port(self) -> int | None:
        """Get nginx proxy port if configured."""
        return self._proxy_port

    @property
    def http_proto(self) -> str:
        return "https" if self._proxy_port else "http"

    @property
    def ha_configuration_port(self) -> int:
        """Get port for HA discovery URL. Uses proxy_port if set, otherwise web_port."""
        return self._proxy_port if self._proxy_port else self._web_port

    @property
    def topic_prefix(self) -> str:
        return self._topic_prefix

    @property
    def serial_no(self) -> str:
        """Get device serial number (e.g., 'blk_abc123')."""
        return self._serial_no or "blk_unknown"

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
    def send_boneio_autodiscovery(self) -> bool:
        """Check if BoneIO autodiscovery publishing is enabled."""
        return self._send_boneio_autodiscovery

    @property
    def receive_boneio_autodiscovery(self) -> bool:
        """Check if BoneIO autodiscovery receiving is enabled."""
        return self._receive_boneio_autodiscovery

    @property
    def device_type(self) -> str:
        return self._device_type

    @property
    def areas(self) -> dict[str, str]:
        """Get areas mapping (id -> name)."""
        return self._areas
    
    def set_areas(self, areas_config: list[dict]) -> None:
        """Set areas from config.
        
        Args:
            areas_config: List of area dicts with 'id' and 'name' keys
        """
        self._areas = {}
        for area in areas_config or []:
            area_id = area.get("id")
            area_name = area.get("name")
            if area_id and area_name:
                self._areas[area_id] = area_name
        _LOGGER.debug("Loaded %d areas: %s", len(self._areas), list(self._areas.keys()))
    
    def get_area_name(self, area_id: str | None) -> str | None:
        """Get area display name by ID.
        
        Args:
            area_id: Area ID to look up
            
        Returns:
            Area display name or None if not found
        """
        if not area_id:
            return None
        return self._areas.get(area_id)

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

    def get_autodiscovery_topics_for_id(
        self, entity_id: str, device_identifier: str | None = None
    ) -> list[tuple[str, str]]:
        """Get all autodiscovery topics that contain a specific entity ID.
        
        Args:
            entity_id: Entity ID to search for
            device_identifier: Optional device identifier to filter by (e.g., topic_prefix or topic_prefix_area).
                              When provided, only returns topics where the payload's device.identifiers
                              contains this value. Used when entity moved between areas/devices.
            
        Returns:
            List of tuples (ha_type, topic) for matching autodiscovery messages
        """
        matching = []
        for ha_type, messages in self._autodiscovery_messages.items():
            for topic, payload_data in messages.items():
                # Topic format: homeassistant/{ha_type}/{topic_prefix}/{entity_id}/config
                if f"/{entity_id}/config" in topic:
                    # If device_identifier is provided, filter by device identifiers in payload
                    if device_identifier:
                        payload = payload_data.get("payload") if isinstance(payload_data, dict) else None
                        if isinstance(payload, dict) and "device" in payload:
                            device_identifiers = payload["device"].get("identifiers", [])
                            if device_identifier in device_identifiers:
                                matching.append((ha_type, topic))
                    else:
                        # No filter, return all matching topics
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
            config = load_config_from_file(self._config_file_path)
            if config is None:
                raise ValueError(f"Failed to load config from file: {self._config_file_path}")
            self._config_cache = config
        
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
