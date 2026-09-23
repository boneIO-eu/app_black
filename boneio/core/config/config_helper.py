"""
Module to provide basic config options.
"""
from __future__ import annotations

import logging
from _collections_abc import dict_values
from typing import TYPE_CHECKING, Any
import time as _time

if TYPE_CHECKING:
    from boneio.integration.homeassistant import HomeAssistantDiscoveryMessage

from boneio.const import (
    ALARM_CONTROL_PANEL,
    BINARY_SENSOR,
    BONEIO,
    DEFAULT_PROXY_PORT,
    IP,
    BUTTON,
    CLIMATE,
    COVER,
    EVENT_ENTITY,
    HOMEASSISTANT,
    LIGHT,
    NONE,
    NUMERIC,
    SELECT,
    SENSOR,
    SWITCH,
    TEXT_SENSOR,
    VALVE,
)
from boneio.core.system import get_serial_from_mac

_LOGGER = logging.getLogger(__name__)


class ConfigHelper:
    def __init__(
        self,
        name: str = BONEIO,
        device_type: str = "boneIO Black",
        version: str = "0.8",
        ha_discovery: bool = True,
        ha_discovery_prefix: str = HOMEASSISTANT,
        network_info: dict | None = None,
        is_web_active: bool = False,
        web_port: int = 8090,
        proxy_port: int | None = None,
        expose: str = "all",
        config_file_path: str | None = None,
        send_boneio_autodiscovery: bool = True,
        receive_boneio_autodiscovery: bool = True,
        update_channel: str = "stable",
        cloud_registration: bool = False,
        pwa_name: str | None = None,
        ha_child_devices: bool = False,
        ha_child_devices_naming: str = "default",
        serial_override: str | None = None,
    ):
        self._name = name
        self._version = version
        
        # Generate real serial number from MAC - always required for physical identification
        self._real_serial = get_serial_from_mac(network_info or {})
        
        # If override is provided, use it as effective serial, otherwise use real MAC-based serial
        if serial_override:
            self._serial_no = serial_override
            _LOGGER.warning("Serial override active: effective=%s, real=%s", serial_override, self._real_serial)
        else:
            self._serial_no = self._real_serial
        
        # Build fixed topic prefix: boneio/blk_{serial} using effective serial
        # This is no longer configurable - always uses this format
        if self._serial_no:
            self._topic_prefix = f"boneio/{self._serial_no}"
        else:
            # Fallback if MAC not available (should rarely happen)
            self._topic_prefix = "boneio/blk_unknown"
            _LOGGER.warning("Could not determine serial number, using fallback topic prefix")

        # PWA short name for Android home screen (max 12 chars)
        if pwa_name:
            self._pwa_name = pwa_name[:12]
        elif self._serial_no:
            # Default: "bIO " + last 6 chars of serial (e.g. "bIO 8c7df0")
            suffix = self._serial_no.replace("blk_", "").replace("blk", "")
            self._pwa_name = f"bIO {suffix}"
        else:
            self._pwa_name = "boneIO"

        self._ha_discovery = ha_discovery
        self._ha_discovery_prefix = ha_discovery_prefix
        self._send_boneio_autodiscovery = send_boneio_autodiscovery
        self._receive_boneio_autodiscovery = receive_boneio_autodiscovery
        self._update_channel = update_channel
        self._cloud_registration = cloud_registration
        self._ha_child_devices = ha_child_devices
        self._ha_child_devices_naming = ha_child_devices_naming
        self._device_type = device_type
        self._web_port = web_port
        self._proxy_port = proxy_port
        self._expose = expose
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
            "update": {},
            CLIMATE: {},
            ALARM_CONTROL_PANEL: {},
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
        
        # Cloud registration instance (set from runner.py after creation)
        self._cloud_reg: Any = None

    @property
    def config_file_path(self) -> str | None:
        """The config.yaml this application was started with."""
        return self._config_file_path

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
        """Get effective device serial number (e.g., 'blk_abc123')."""
        return self._serial_no or "blk_unknown"

    @property
    def proxy_port(self) -> int | None:
        """Get nginx proxy port if configured."""
        return self._proxy_port

    @property
    def http_proto(self) -> str:
        """The scheme anything linking to this panel should use."""
        return "https" if self._behind_proxy else "http"

    @property
    def _behind_proxy(self) -> bool:
        """Whether the panel is reached through the reverse proxy.

        Either because somebody named its port, or because the panel's own
        port has been taken off the network and the proxy is the only way in.
        """
        return bool(self._proxy_port) or self._expose == "proxy"

    def update_network_info(self, network_info: dict | None) -> None:
        """Refresh the address this device publishes links to.

        The snapshot taken at startup goes stale: on DHCP the lease can arrive
        after boneIO is up, and it can change later. Home Assistant and the OLED
        both build their link from here, so both were handing out whatever was
        true at boot.

        An update without a usable address is ignored rather than stored — a
        link to the last known address beats a link to nothing.

        Args:
            network_info: Fresh mapping from :func:`get_network_info`.
        """
        if self._usable_address(network_info):
            self._network_info = network_info

    @staticmethod
    def _usable_address(network_info: dict | None) -> str | None:
        """The IP from a network mapping, or None when there is not one.

        ``get_network_info`` reports a missing address as the string "none",
        which is truthy — published unchecked it became ``https://none:8443``.

        Args:
            network_info: Mapping to read.

        Returns:
            The address, or None.
        """
        address = (network_info or {}).get(IP)
        if not address or address == NONE:
            return None
        return str(address)

    @property
    def configuration_url(self) -> str | None:
        """The address anything linking to this panel should use.

        Home Assistant puts this on the device page, and the panel shows it so
        an operator can see what was published without opening Home Assistant.
        Both read it here rather than each deciding for itself: the wording in
        the panel drifted away from what discovery actually sends within a day
        of being written, because it described the rule instead of asking.

        Returns:
            The URL, or None when there is no address to build one from.
        """
        if self._cloud_registration and self.serial_number:
            # Registered with the cloud: a real certificate on a public name,
            # pointing at the local address. Nothing else can beat that.
            return f"https://{self.serial_number}.black.boneio.app:{DEFAULT_PROXY_PORT}"
        address = self._usable_address(self._network_info)
        if not (self._is_web_active and address):
            return None
        return f"{self.http_proto}://{address}:{self.web_configuration_port}"

    @property
    def web_configuration_port(self) -> int:
        """The port to put in a link to this panel.

        The configured proxy port when there is one. Otherwise the panel's own
        port — unless that port has been taken off the network, in which case
        it answers nothing and linking to it would hand Home Assistant a dead
        address. Then it is the port the built-in proxy serves on.
        """
        if self._proxy_port:
            return self._proxy_port
        if self._expose == "proxy":
            return DEFAULT_PROXY_PORT
        return self._web_port

    @property
    def topic_prefix(self) -> str:
        return self._topic_prefix

    @property
    def real_serial(self) -> str:
        """Real serial from MAC — for HA device_info and UI display."""
        return self._real_serial or "blk_unknown"

    @property
    def serial_override(self) -> str | None:
        """Return override value if active, None otherwise."""
        if self._serial_no != self._real_serial:
            return self._serial_no
        return None

    @property
    def pwa_name(self) -> str:
        """Get PWA short name for Android home screen (max 12 chars)."""
        return self._pwa_name

    @pwa_name.setter
    def pwa_name(self, value: str):
        """Set PWA short name (truncated to 12 chars)."""
        self._pwa_name = value[:12] if value else self._pwa_name

    @property
    def name(self) -> str:
        return self._name

    @property
    def ha_discovery(self) -> bool:
        return self._ha_discovery

    @property
    def version(self) -> str:
        """Get the board version."""
        return self._version

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
    def update_channel(self) -> str:
        """Get update channel (stable or dev)."""
        return self._update_channel

    @property
    def cloud_registration(self) -> bool:
        """Check if cloud registration (PWA) is enabled."""
        return self._cloud_registration

    @property
    def ha_child_devices(self) -> bool:
        """Check if experimental HA child devices mode is enabled.
        
        When enabled, each output/input/cover becomes its own child device
        in Home Assistant instead of being grouped under one main device.
        """
        return self._ha_child_devices

    @property
    def ha_child_devices_naming(self) -> str:
        """Get the naming style for HA child devices.
        
        Returns:
            'default' — entity name only (e.g. "OUT 17")
            'device_name' — "{device_name} - {name}" (e.g. "boneIO Black - OUT 17")
            'device_name_area' — "{device_name} - {area} - {name}" (e.g. "boneIO Black - Gabinet - OUT 17")
        """
        return self._ha_child_devices_naming

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

    def add_autodiscovery_msg(
        self, 
        ha_type: str, 
        topic: str, 
        payload: str | dict[str, Any] | HomeAssistantDiscoveryMessage | None
    ):
        """Add autodiscovery message."""
        self._autodiscovery_messages[ha_type][topic] = {"topic": topic, "payload": payload}

    @property
    def ha_types(self) -> list[str]:
        return list(self._autodiscovery_messages.keys())

    def is_topic_in_autodiscovery(self, topic: str) -> bool:
        topic_parts_raw = topic[len(f"{self._ha_discovery_prefix}/") :].split("/")
        ha_type = topic_parts_raw[0]
        return ha_type in self._autodiscovery_messages and topic in self._autodiscovery_messages[ha_type]
    
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
        """Reload configuration from YAML file (fast path for hot-reload).
        
        Uses load_yaml_file() + merge_board_config() to read the config
        directly from YAML without running Cerberus validation. This is
        much faster (~0.5-1s) than the full validation path (~20s on BB).
        
        Full Cerberus validation is only needed at:
        - Application startup (via load_config_from_file)
        - Background disk cache rebuild (debounced after config changes)
        - Monaco YAML editor validation (load_config_from_string)
        
        NOTE: Migrations are not applied here — they run at startup and
        are idempotent (version-gated). Config saved via the UI always
        has current schema version.
        
        Returns:
            dict: Reloaded configuration dictionary
            
        Raises:
            ValueError: If config_file_path is not set
        """

        if self._config_file_path is None:
            raise ValueError("config_file_path not set in ConfigHelper")

        _t0 = _time.monotonic()
        _LOGGER.info("Fast-reloading config from: %s", self._config_file_path)

        from boneio.core.config.yaml_util import load_yaml_file, merge_board_config

        config_yaml = load_yaml_file(self._config_file_path)
        if config_yaml is None:
            raise ValueError(f"Failed to load config from: {self._config_file_path}")

        merged = merge_board_config(config_yaml)
        self._config_cache = merged

        elapsed = _time.monotonic() - _t0
        _LOGGER.info("Fast config reload completed in %.2fs", elapsed)

        return merged

    def update_config_section(self, section: str, data: object) -> None:
        """Update a single section in the in-memory config cache.

        Fast path: modifies the cached dict directly without reloading
        YAML from disk.  If the cache is not populated yet, this is a
        no-op — the next ``get_config()`` call will load from file.

        Args:
            section: Top-level config key (e.g. ``"event"``, ``"output"``).
            data: New value for that section (typically a ``list[dict]``).
        """
        if self._config_cache is None:
            _LOGGER.debug(
                "Config cache not populated, skipping in-place update for '%s'",
                section,
            )
            return
        self._config_cache[section] = data
        _LOGGER.debug("Updated config section '%s' in-place", section)

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
