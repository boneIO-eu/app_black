"""ESPHome API-based remote device implementation.

Supports controlling switches, lights, and covers on ESPHome devices
via the native ESPHome API (TCP/IP, port 6053).
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from boneio.core.remote.base import (
    RemoteDevice,
    RemoteDeviceProtocol,
    RemoteDeviceType,
)

if TYPE_CHECKING:
    from boneio.core.messaging import MessageBus

_LOGGER = logging.getLogger(__name__)

# Try to import aioesphomeapi - it's optional
try:
    from aioesphomeapi import (
        APIClient,
        APIConnectionError,
        InvalidAuthAPIError,
        ReconnectLogic,
        SwitchInfo,
        LightInfo,
        LightColorCapability,
        CoverInfo,
        SwitchState,
        LightState,
        CoverState,
    )
    ESPHOME_API_AVAILABLE = True
except ImportError:
    ESPHOME_API_AVAILABLE = False
    _LOGGER.warning("aioesphomeapi not installed - ESPHome API support disabled")


class ESPHomeLightCapabilities:
    """Capabilities of an ESPHome light entity."""
    
    def __init__(
        self,
        supports_brightness: bool = False,
        supports_color_temp: bool = False,
        supports_rgb: bool = False,
        supports_rgbw: bool = False,
        supports_rgbww: bool = False,
        min_mireds: int | None = None,
        max_mireds: int | None = None,
    ) -> None:
        """Initialize light capabilities.
        
        Args:
            supports_brightness: Whether light supports brightness control
            supports_color_temp: Whether light supports color temperature
            supports_rgb: Whether light supports RGB color
            supports_rgbw: Whether light supports RGBW color
            supports_rgbww: Whether light supports RGBWW color
            min_mireds: Minimum color temperature in mireds
            max_mireds: Maximum color temperature in mireds
        """
        self.supports_brightness = supports_brightness
        self.supports_color_temp = supports_color_temp
        self.supports_rgb = supports_rgb
        self.supports_rgbw = supports_rgbw
        self.supports_rgbww = supports_rgbww
        self.min_mireds = min_mireds
        self.max_mireds = max_mireds
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "supports_brightness": self.supports_brightness,
            "supports_color_temp": self.supports_color_temp,
            "supports_rgb": self.supports_rgb,
            "supports_rgbw": self.supports_rgbw,
            "supports_rgbww": self.supports_rgbww,
            "min_mireds": self.min_mireds,
            "max_mireds": self.max_mireds,
        }


class ESPHomeRemoteDevice(RemoteDevice):
    """ESPHome API-based remote device.
    
    Controls switches, lights, and covers on ESPHome devices via native API.
    Supports autodiscovery of entities and their capabilities.
    
    Args:
        id: Device identifier
        name: Human-readable name
        host: IP address or hostname of ESPHome device
        port: API port (default 6053)
        password: API password (optional)
        encryption_key: Encryption key for noise encryption (optional)
        switches: Optional list of known switches
        lights: Optional list of known lights with capabilities
        covers: Optional list of known covers
    """
    
    def __init__(
        self,
        id: str,
        name: str,
        host: str,
        port: int = 6053,
        password: str = "",
        encryption_key: str = "",
        switches: list[dict[str, Any]] | None = None,
        lights: list[dict[str, Any]] | None = None,
        covers: list[dict[str, Any]] | None = None,
    ) -> None:
        """Initialize ESPHome remote device.
        
        Args:
            id: Device identifier
            name: Human-readable name
            host: IP address or hostname
            port: API port (default 6053)
            password: API password (optional)
            encryption_key: Encryption key (optional)
            switches: Optional list of known switches
            lights: Optional list of known lights
            covers: Optional list of known covers
        """
        super().__init__(
            id=id,
            name=name,
            protocol=RemoteDeviceProtocol.ESPHOME_API,
            device_type=RemoteDeviceType.ESPHOME,
            config={
                "host": host,
                "port": port,
                "password": password,
                "encryption_key": encryption_key,
            },
        )
        
        self._host = host
        self._port = port
        self._password = password
        self._encryption_key = encryption_key
        
        # API client and connection state
        self._client: APIClient | None = None
        self._connected = False
        self._reconnect_logic: ReconnectLogic | None = None
        
        # Entity storage
        self._switches: list[dict[str, Any]] = []
        self._lights: list[dict[str, Any]] = []
        self._covers_list: list[dict[str, Any]] = []
        
        # Entity key mappings (for sending commands)
        self._switch_keys: dict[str, int] = {}
        self._light_keys: dict[str, int] = {}
        self._cover_keys: dict[str, int] = {}
        
        # Current states (updated via subscription)
        self._switch_states: dict[str, bool] = {}
        self._light_states: dict[str, dict[str, Any]] = {}
        self._cover_states: dict[str, dict[str, Any]] = {}
        
        # Load configured entities
        if switches:
            self._switches = switches
        if lights:
            self._lights = lights
        if covers:
            self._covers_list = covers
            # Also set parent class covers for compatibility
            self.set_covers(covers)
        
        _LOGGER.info(
            "Configured ESPHome remote device '%s' (host=%s:%d)",
            name, host, port
        )
    
    @property
    def host(self) -> str:
        """Get device host."""
        return self._host
    
    @property
    def port(self) -> int:
        """Get device port."""
        return self._port
    
    @property
    def connected(self) -> bool:
        """Check if connected to device."""
        return self._connected
    
    @property
    def switches(self) -> list[dict[str, Any]]:
        """Get list of known switches."""
        return self._switches
    
    @property
    def lights(self) -> list[dict[str, Any]]:
        """Get list of known lights with capabilities."""
        return self._lights
    
    @property
    def esphome_covers(self) -> list[dict[str, Any]]:
        """Get list of known covers."""
        return self._covers_list
    
    def has_light(self, entity_id: str) -> bool:
        """Check if entity_id is a light on this device.
        
        Args:
            entity_id: Entity ID to check
            
        Returns:
            True if entity_id is a light
        """
        # Check in configured lights
        for light in self._lights:
            if light.get("id") == entity_id or light.get("object_id") == entity_id:
                return True
        # Check in discovered light keys
        return entity_id in self._light_keys
    
    def has_switch(self, entity_id: str) -> bool:
        """Check if entity_id is a switch on this device.
        
        Args:
            entity_id: Entity ID to check
            
        Returns:
            True if entity_id is a switch
        """
        # Check in configured switches
        for switch in self._switches:
            if switch.get("id") == entity_id or switch.get("object_id") == entity_id:
                return True
        # Check in discovered switch keys
        return entity_id in self._switch_keys
    
    async def start_connection(self) -> None:
        """Start persistent connection with automatic reconnection.
        
        This method starts the ReconnectLogic which maintains a persistent
        connection to the ESPHome device and automatically reconnects on failure.
        """
        if not ESPHOME_API_AVAILABLE:
            _LOGGER.error("aioesphomeapi not installed - cannot connect to ESPHome")
            return
        
        if self._reconnect_logic is not None:
            _LOGGER.debug("Connection already started for '%s'", self._name)
            return
        
        # Create API client
        self._client = APIClient(
            address=self._host,
            port=self._port,
            password=self._password,
            noise_psk=self._encryption_key if self._encryption_key else None,
        )
        
        # Create ReconnectLogic for persistent connection
        self._reconnect_logic = ReconnectLogic(
            client=self._client,
            on_connect=self._on_connect,
            on_disconnect=self._on_disconnect,
            zeroconf_instance=None,
            name=self._name,
        )
        
        # Start the reconnect logic
        await self._reconnect_logic.start()
        _LOGGER.info("Started persistent connection to ESPHome device '%s' at %s:%d", 
                    self._name, self._host, self._port)
    
    async def _on_connect(self) -> None:
        """Callback when connected to ESPHome device."""
        self._connected = True
        _LOGGER.info("Connected to ESPHome device '%s'", self._name)
        
        if not self._client:
            return
        
        try:
            # Subscribe to state changes (not async in newer aioesphomeapi)
            self._client.subscribe_states(self._on_state_change)
            
            # Build entity key mappings from configured entities
            self._build_entity_keys()
            
            _LOGGER.debug("Subscribed to state changes on '%s'", self._name)
        except Exception as e:
            _LOGGER.error("Error during connect callback for '%s': %s", self._name, e)
    
    async def _on_disconnect(self, expected_disconnect: bool) -> None:
        """Callback when disconnected from ESPHome device.
        
        Args:
            expected_disconnect: True if disconnect was expected (e.g. user requested)
        """
        self._connected = False
        if expected_disconnect:
            _LOGGER.info("Disconnected from ESPHome device '%s' (expected)", self._name)
        else:
            _LOGGER.warning("Disconnected from ESPHome device '%s' (unexpected)", self._name)
    
    def _on_state_change(self, state: Any) -> None:
        """Callback when entity state changes.
        
        Args:
            state: State object from ESPHome (SwitchState, LightState, CoverState, etc.)
        """
        if not ESPHOME_API_AVAILABLE:
            return
        
        try:
            if isinstance(state, SwitchState):
                # Find switch by key
                for switch in self._switches:
                    if switch.get("key") == state.key:
                        switch_id = switch.get("id", "")
                        self._switch_states[switch_id] = state.state
                        _LOGGER.debug("Switch '%s' state: %s", switch_id, state.state)
                        break
                        
            elif isinstance(state, LightState):
                # Find light by key
                for light in self._lights:
                    if light.get("key") == state.key:
                        light_id = light.get("id", "")
                        self._light_states[light_id] = {
                            "state": state.state,
                            "brightness": state.brightness,
                            "color_temp": getattr(state, 'color_temperature', None),
                            "rgb": (state.red, state.green, state.blue) if hasattr(state, 'red') else None,
                        }
                        _LOGGER.debug("Light '%s' state: on=%s, brightness=%.2f", 
                                     light_id, state.state, state.brightness)
                        break
                        
            elif isinstance(state, CoverState):
                # Find cover by key
                for cover in self._covers_list:
                    if cover.get("key") == state.key:
                        cover_id = cover.get("id", "")
                        self._cover_states[cover_id] = {
                            "position": state.position,
                            "tilt": getattr(state, 'tilt', None),
                            "current_operation": getattr(state, 'current_operation', None),
                        }
                        _LOGGER.debug("Cover '%s' position: %.2f", cover_id, state.position)
                        break
        except Exception as e:
            _LOGGER.debug("Error processing state change: %s", e)
    
    def _build_entity_keys(self) -> None:
        """Build entity key mappings from configured entities."""
        self._switch_keys.clear()
        self._light_keys.clear()
        self._cover_keys.clear()
        
        for switch in self._switches:
            if "id" in switch and "key" in switch:
                self._switch_keys[switch["id"]] = switch["key"]
        
        for light in self._lights:
            if "id" in light and "key" in light:
                self._light_keys[light["id"]] = light["key"]
        
        for cover in self._covers_list:
            if "id" in cover and "key" in cover:
                self._cover_keys[cover["id"]] = cover["key"]
        
        _LOGGER.debug("Built entity keys: %d switches, %d lights, %d covers",
                     len(self._switch_keys), len(self._light_keys), len(self._cover_keys))
    
    async def connect(self) -> bool:
        """Ensure connection is established.
        
        If ReconnectLogic is running, just check connection state.
        Otherwise, start the persistent connection.
        
        Returns:
            True if connected
        """
        if not ESPHOME_API_AVAILABLE:
            _LOGGER.error("aioesphomeapi not installed - cannot connect to ESPHome")
            return False
        
        # If ReconnectLogic is running, just check state
        if self._reconnect_logic is not None:
            if self._connected:
                return True
            # Wait a bit for reconnection
            for _ in range(10):
                if self._connected:
                    return True
                await asyncio.sleep(0.1)
            _LOGGER.warning("ESPHome device '%s' not connected after waiting", self._name)
            return False
        
        # Start persistent connection if not running
        await self.start_connection()
        
        # Wait for connection
        for _ in range(30):
            if self._connected:
                return True
            await asyncio.sleep(0.1)
        
        _LOGGER.error("Failed to connect to ESPHome device '%s'", self._name)
        return False
    
    async def disconnect(self) -> None:
        """Disconnect from ESPHome device and stop reconnection logic."""
        if self._reconnect_logic:
            await self._reconnect_logic.stop()
            self._reconnect_logic = None
        
        if self._client:
            try:
                await self._client.disconnect()
            except Exception as e:
                _LOGGER.debug("Error disconnecting from '%s': %s", self._name, e)
            finally:
                self._client = None
                self._connected = False
    
    async def discover_entities(self) -> dict[str, Any]:
        """Discover all entities on the ESPHome device.
        
        Connects to the device, retrieves entity list, and returns
        switches, lights, and covers with their capabilities.
        
        Returns:
            Dictionary with 'switches', 'lights', 'covers' lists
        """
        if not ESPHOME_API_AVAILABLE:
            _LOGGER.error("aioesphomeapi not installed")
            return {"switches": [], "lights": [], "covers": [], "error": "aioesphomeapi not installed"}
        
        result = {
            "switches": [],
            "lights": [],
            "covers": [],
        }
        
        try:
            # Create temporary client for discovery
            client = APIClient(
                address=self._host,
                port=self._port,
                password=self._password,
                noise_psk=self._encryption_key if self._encryption_key else None,
            )
            
            await client.connect(login=True)
            
            # Get device info
            device_info = await client.device_info()
            _LOGGER.info("Discovering entities on '%s' (%s)", 
                        device_info.name, device_info.mac_address)
            
            # List all entities
            entities, _ = await client.list_entities_services()
            
            for entity in entities:
                if isinstance(entity, SwitchInfo):
                    result["switches"].append({
                        "id": entity.object_id,
                        "name": entity.name,
                        "key": entity.key,
                    })
                    _LOGGER.debug("Found switch: %s (%s)", entity.name, entity.object_id)
                    
                elif isinstance(entity, LightInfo):
                    # Determine light capabilities using LightColorCapability flags
                    # supported_color_modes is a list of bitmask values
                    supports_brightness = False
                    supports_color_temp = False
                    supports_rgb = False
                    supports_rgbw = False
                    
                    # Use getattr for safety - attribute may vary between aioesphomeapi versions
                    color_modes = getattr(entity, 'supported_color_modes', [])
                    for mode in color_modes:
                        # Check if mode has BRIGHTNESS capability
                        if mode & LightColorCapability.BRIGHTNESS:
                            supports_brightness = True
                        # Check for COLOR_TEMPERATURE or COLD_WARM_WHITE
                        if mode & (LightColorCapability.COLOR_TEMPERATURE | LightColorCapability.COLD_WARM_WHITE):
                            supports_color_temp = True
                        # Check for RGB
                        if mode & LightColorCapability.RGB:
                            supports_rgb = True
                        # Check for WHITE (RGBW)
                        if (mode & LightColorCapability.RGB) and (mode & LightColorCapability.WHITE):
                            supports_rgbw = True
                    
                    light_data = {
                        "id": entity.object_id,
                        "name": entity.name,
                        "key": entity.key,
                        "supports_brightness": supports_brightness,
                        "supports_color_temp": supports_color_temp,
                        "supports_rgb": supports_rgb,
                        "supports_rgbw": supports_rgbw,
                        "min_mireds": getattr(entity, 'min_mireds', None),
                        "max_mireds": getattr(entity, 'max_mireds', None),
                    }
                    
                    result["lights"].append(light_data)
                    _LOGGER.debug("Found light: %s (%s) - brightness=%s, color_temp=%s, rgb=%s",
                                 entity.name, entity.object_id,
                                 light_data["supports_brightness"],
                                 light_data["supports_color_temp"],
                                 light_data["supports_rgb"])
                    
                elif isinstance(entity, CoverInfo):
                    result["covers"].append({
                        "id": entity.object_id,
                        "name": entity.name,
                        "key": entity.key,
                        "supports_position": getattr(entity, 'supports_position', True),
                        "supports_tilt": getattr(entity, 'supports_tilt', False),
                    })
                    _LOGGER.debug("Found cover: %s (%s)", entity.name, entity.object_id)
            
            await client.disconnect()
            
            _LOGGER.info("Discovered %d switches, %d lights, %d covers on '%s'",
                        len(result["switches"]), len(result["lights"]), 
                        len(result["covers"]), self._name)
            
            return result
            
        except InvalidAuthAPIError as e:
            _LOGGER.error("Authentication failed during discovery: %s", e)
            return {"switches": [], "lights": [], "covers": [], "error": f"Authentication failed: {e}"}
        except APIConnectionError as e:
            _LOGGER.error("Connection failed during discovery: %s", e)
            return {"switches": [], "lights": [], "covers": [], "error": f"Connection failed: {e}"}
        except Exception as e:
            _LOGGER.error("Discovery failed: %s", e)
            return {"switches": [], "lights": [], "covers": [], "error": str(e)}
    
    async def control_output(
        self,
        output_id: str,
        action: str,
        message_bus: Any = None,
    ) -> bool:
        """Control a switch on the ESPHome device.
        
        Args:
            output_id: ID of the switch to control (object_id)
            action: Action to perform (ON, OFF, TOGGLE)
            message_bus: Not used for ESPHome API
            
        Returns:
            True if command was sent successfully
        """
        return await self.control_switch(output_id, action)
    
    async def control_switch(self, switch_id: str, action: str) -> bool:
        """Control a switch on the ESPHome device.
        
        Args:
            switch_id: ID of the switch (object_id)
            action: Action to perform (ON, OFF, TOGGLE)
            
        Returns:
            True if command was sent successfully
        """
        if not ESPHOME_API_AVAILABLE:
            _LOGGER.error("aioesphomeapi not installed")
            return False
        
        # Find switch key
        switch_key = self._get_entity_key(switch_id, self._switches, self._switch_keys)
        if switch_key is None:
            _LOGGER.error("Switch '%s' not found on device '%s'", switch_id, self._name)
            return False
        
        try:
            if not await self.connect():
                return False
            
            action_upper = action.upper()
            
            if action_upper == "TOGGLE":
                # Get current state and toggle
                current_state = self._switch_states.get(switch_id, False)
                state = not current_state
            elif action_upper == "ON":
                state = True
            elif action_upper == "OFF":
                state = False
            else:
                _LOGGER.error("Invalid switch action: %s", action)
                return False
            
            if self._client:
                self._client.switch_command(switch_key, state)
            _LOGGER.debug("Sent switch command: %s -> %s", switch_id, state)
            return True
            
        except Exception as e:
            _LOGGER.error("Failed to control switch '%s': %s", switch_id, e)
            return False
    
    async def control_light(
        self,
        light_id: str,
        action: str,
        brightness: int | None = None,
        color_temp: int | None = None,
        rgb: tuple[int, int, int] | None = None,
        transition: float = 0.0,
    ) -> bool:
        """Control a light on the ESPHome device.
        
        Args:
            light_id: ID of the light (object_id)
            action: Action to perform (ON, OFF, TOGGLE, BRIGHTNESS_UP, BRIGHTNESS_DOWN, SET_BRIGHTNESS)
            brightness: Brightness value (0-255) for SET_BRIGHTNESS action
            color_temp: Color temperature in mireds
            rgb: RGB color tuple (0-255 each)
            transition: Transition time in seconds
            
        Returns:
            True if command was sent successfully
        """
        if not ESPHOME_API_AVAILABLE:
            _LOGGER.error("aioesphomeapi not installed")
            return False
        
        # Find light key
        light_key = self._get_entity_key(light_id, self._lights, self._light_keys)
        if light_key is None:
            _LOGGER.error("Light '%s' not found on device '%s'", light_id, self._name)
            return False
        
        try:
            if not await self.connect():
                return False
            
            action_upper = action.upper()
            
            if not self._client:
                return False
            
            if action_upper == "OFF":
                self._client.light_command(light_key, state=False, transition_length=transition)
                
            elif action_upper == "ON":
                cmd_kwargs: dict[str, Any] = {"state": True, "transition_length": transition}
                if brightness is not None:
                    cmd_kwargs["brightness"] = brightness / 255.0
                if color_temp is not None:
                    cmd_kwargs["color_temperature"] = color_temp
                if rgb is not None:
                    cmd_kwargs["rgb"] = tuple(c / 255.0 for c in rgb)
                self._client.light_command(light_key, **cmd_kwargs)
                
            elif action_upper == "TOGGLE":
                # Get current state and toggle
                current_state = self._light_states.get(light_id, {}).get("state", False)
                new_state = not current_state
                
                if new_state:
                    # Turning ON - apply brightness/color_temp/rgb if provided
                    toggle_kwargs: dict[str, Any] = {"state": True, "transition_length": transition}
                    if brightness is not None:
                        toggle_kwargs["brightness"] = brightness / 255.0
                    if color_temp is not None:
                        toggle_kwargs["color_temperature"] = color_temp
                    if rgb is not None:
                        toggle_kwargs["rgb"] = tuple(c / 255.0 for c in rgb)
                    self._client.light_command(light_key, **toggle_kwargs)
                else:
                    # Turning OFF - just turn off
                    self._client.light_command(light_key, state=False, transition_length=transition)
                
            elif action_upper == "SET_BRIGHTNESS":
                if brightness is None:
                    _LOGGER.error("SET_BRIGHTNESS requires brightness parameter")
                    return False
                self._client.light_command(
                    light_key, 
                    state=True, 
                    brightness=brightness / 255.0,
                    transition_length=transition
                )
                
            elif action_upper == "BRIGHTNESS_UP":
                # Increase brightness by 10%
                current_brightness = self._light_states.get(light_id, {}).get("brightness", 0.5)
                new_brightness = min(1.0, current_brightness + 0.1)
                self._client.light_command(
                    light_key, 
                    state=True, 
                    brightness=new_brightness,
                    transition_length=transition
                )
                
            elif action_upper == "BRIGHTNESS_DOWN":
                # Decrease brightness by 10%
                current_brightness = self._light_states.get(light_id, {}).get("brightness", 0.5)
                new_brightness = max(0.01, current_brightness - 0.1)
                self._client.light_command(
                    light_key, 
                    state=True, 
                    brightness=new_brightness,
                    transition_length=transition
                )
                
            else:
                _LOGGER.error("Invalid light action: %s", action)
                return False
            
            _LOGGER.debug("Sent light command: %s -> %s", light_id, action)
            return True
            
        except Exception as e:
            _LOGGER.error("Failed to control light '%s': %s", light_id, e)
            return False
    
    async def control_cover(
        self,
        cover_id: str,
        action: str,
        message_bus: Any = None,
        **kwargs,
    ) -> bool:
        """Control a cover on the ESPHome device.
        
        Args:
            cover_id: ID of the cover (object_id)
            action: Action to perform (OPEN, CLOSE, STOP, TOGGLE)
            message_bus: Not used for ESPHome API
            **kwargs: Additional parameters (position, tilt_position)
            
        Returns:
            True if command was sent successfully
        """
        if not ESPHOME_API_AVAILABLE:
            _LOGGER.error("aioesphomeapi not installed")
            return False
        
        # Find cover key
        cover_key = self._get_entity_key(cover_id, self._covers_list, self._cover_keys)
        if cover_key is None:
            _LOGGER.error("Cover '%s' not found on device '%s'", cover_id, self._name)
            return False
        
        try:
            if not await self.connect():
                return False
            
            action_upper = action.upper()
            position = kwargs.get("position")
            tilt_position = kwargs.get("tilt_position")
            
            if not self._client:
                return False
            
            if position is not None:
                # Set position (0-100 -> 0.0-1.0)
                self._client.cover_command(cover_key, position=position / 100.0)
            elif tilt_position is not None:
                self._client.cover_command(cover_key, tilt=tilt_position / 100.0)
            elif action_upper == "OPEN":
                self._client.cover_command(cover_key, position=1.0)
            elif action_upper == "CLOSE":
                self._client.cover_command(cover_key, position=0.0)
            elif action_upper == "STOP":
                self._client.cover_command(cover_key, stop=True)
            elif action_upper == "TOGGLE":
                # Get current state and toggle
                current_pos = self._cover_states.get(cover_id, {}).get("position", 0.5)
                if current_pos > 0.5:
                    self._client.cover_command(cover_key, position=0.0)
                else:
                    self._client.cover_command(cover_key, position=1.0)
            else:
                _LOGGER.error("Invalid cover action: %s", action)
                return False
            
            _LOGGER.debug("Sent cover command: %s -> %s", cover_id, action)
            return True
            
        except Exception as e:
            _LOGGER.error("Failed to control cover '%s': %s", cover_id, e)
            return False
    
    def _get_entity_key(
        self, 
        entity_id: str, 
        entity_list: list[dict[str, Any]], 
        key_cache: dict[str, int]
    ) -> int | None:
        """Get entity key for API commands.
        
        Args:
            entity_id: Entity object_id
            entity_list: List of entity definitions
            key_cache: Cache of entity_id -> key mappings
            
        Returns:
            Entity key or None if not found
        """
        # Check cache first
        if entity_id in key_cache:
            return key_cache[entity_id]
        
        # Search in entity list
        for entity in entity_list:
            if entity.get("id") == entity_id:
                key = entity.get("key")
                if key is not None:
                    key_cache[entity_id] = key
                    return key
        
        return None
    
    def set_switches(self, switches: list[dict[str, Any]]) -> None:
        """Set list of known switches.
        
        Args:
            switches: List of switch definitions with 'id', 'name', 'key'
        """
        self._switches = switches
        self._switch_keys.clear()
        for switch in switches:
            if switch.get("id") and switch.get("key"):
                self._switch_keys[switch["id"]] = switch["key"]
    
    def set_lights(self, lights: list[dict[str, Any]]) -> None:
        """Set list of known lights.
        
        Args:
            lights: List of light definitions with capabilities
        """
        self._lights = lights
        self._light_keys.clear()
        for light in lights:
            if light.get("id") and light.get("key"):
                self._light_keys[light["id"]] = light["key"]
    
    def set_esphome_covers(self, covers: list[dict[str, Any]]) -> None:
        """Set list of known covers.
        
        Args:
            covers: List of cover definitions with 'id', 'name', 'key'
        """
        self._covers_list = covers
        self._cover_keys.clear()
        for cover in covers:
            if cover.get("id") and cover.get("key"):
                self._cover_keys[cover["id"]] = cover["key"]
        # Also update parent class covers
        self.set_covers(covers)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation.
        
        Returns:
            Dictionary with device information
        """
        data = super().to_dict()
        data["host"] = self._host
        data["port"] = self._port
        data["connected"] = self._connected
        data["switches"] = self._switches
        data["lights"] = self._lights
        data["esphome_covers"] = self._covers_list
        return data


async def discover_esphome_entities(
    host: str,
    port: int = 6053,
    password: str = "",
    encryption_key: str = "",
) -> dict[str, Any]:
    """Standalone function to discover entities on an ESPHome device.
    
    This can be called without creating an ESPHomeRemoteDevice instance.
    Useful for the discovery endpoint.
    
    Args:
        host: IP address or hostname
        port: API port (default 6053)
        password: API password (optional)
        encryption_key: Encryption key (optional)
        
    Returns:
        Dictionary with 'switches', 'lights', 'covers' lists and optional 'error'
    """
    if not ESPHOME_API_AVAILABLE:
        return {
            "switches": [],
            "lights": [],
            "covers": [],
            "error": "aioesphomeapi not installed"
        }
    
    # Create temporary device for discovery
    temp_device = ESPHomeRemoteDevice(
        id="temp_discovery",
        name="Temporary Discovery",
        host=host,
        port=port,
        password=password,
        encryption_key=encryption_key,
    )
    
    return await temp_device.discover_entities()


# Try to import zeroconf for mDNS discovery
try:
    from zeroconf import ServiceBrowser, ServiceListener, Zeroconf
    import socket
    ZEROCONF_AVAILABLE = True
    
    class ESPHomeServiceListener(ServiceListener):
        """Listener for ESPHome mDNS services."""
        
        def __init__(self):
            """Initialize the listener."""
            self.devices: list[dict[str, Any]] = []
        
        def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
            """Handle service addition."""
            info = zc.get_service_info(type_, name)
            if info:
                # Extract device name from service name
                device_name = name.replace("._esphomelib._tcp.local.", "")
                
                # Get IP address
                ip_address = None
                if info.addresses:
                    ip_address = socket.inet_ntoa(info.addresses[0])
                
                self.devices.append({
                    "name": device_name,
                    "host": info.server.rstrip('.') if info.server else ip_address,
                    "ip": ip_address,
                    "port": info.port or 6053,
                })
                _LOGGER.debug("Found ESPHome device: %s at %s:%d", 
                             device_name, ip_address, info.port or 6053)
        
        def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
            """Handle service removal."""
            pass
        
        def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
            """Handle service update."""
            pass

except ImportError:
    ZEROCONF_AVAILABLE = False
    _LOGGER.debug("zeroconf not installed - mDNS discovery disabled")


async def scan_esphome_devices(timeout: float = 3.0) -> dict[str, Any]:
    """
    Scan the local network for ESPHome devices using mDNS.
    
    Args:
        timeout: How long to scan in seconds (default 3.0)
        
    Returns:
        Dictionary with 'devices' list containing found devices,
        each with 'name', 'host', 'ip', 'port' fields.
        May contain 'error' if scanning failed.
    """
    if not ZEROCONF_AVAILABLE:
        return {
            "devices": [],
            "error": "zeroconf not installed - mDNS discovery disabled"
        }
    
    _LOGGER.info("Scanning for ESPHome devices (timeout: %.1fs)...", timeout)
    
    try:
        zc = Zeroconf()
        listener = ESPHomeServiceListener()
        
        # Browse for ESPHome services
        browser = ServiceBrowser(zc, "_esphomelib._tcp.local.", listener)
        
        # Wait for discovery
        await asyncio.sleep(timeout)
        
        # Cleanup
        browser.cancel()
        zc.close()
        
        _LOGGER.info("Found %d ESPHome device(s)", len(listener.devices))
        
        return {
            "devices": listener.devices,
        }
        
    except Exception as e:
        _LOGGER.error("mDNS scan failed: %s", e)
        return {
            "devices": [],
            "error": str(e)
        }
