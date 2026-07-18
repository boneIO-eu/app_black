"""Remote device manager.

Manages all configured remote devices and provides access to them.
Supports autodiscovery of neighboring BoneIO Black devices via MQTT.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any, cast

from boneio.core.remote.base import (
    RemoteDevice,
    RemoteDeviceProtocol,
    RemoteDeviceType,
)
from boneio.core.remote.mqtt import MQTTRemoteDevice

if TYPE_CHECKING:
    from boneio.core.messaging import MessageBus
    from boneio.core.remote.esphome import ESPHomeRemoteDevice
    from boneio.core.remote.wled import WLEDRemoteDevice

_LOGGER = logging.getLogger(__name__)

# Discovery topic pattern: boneio/blk_{serial}/discovery/{type}
DISCOVERY_TOPIC_PREFIX = "boneio"
DISCOVERY_SUBTOPIC = "discovery"


class RemoteDeviceManager:
    """Manager for remote devices.

    Handles initialization and access to all configured remote devices.
    Supports autodiscovery of neighboring BoneIO Black devices via MQTT.

    Args:
        message_bus: Message bus for MQTT communication
        remote_devices_config: List of remote device configurations
        own_serial: Serial number of this device (to exclude from autodiscovery)
    """

    def __init__(
        self,
        message_bus: MessageBus | None = None,
        remote_devices_config: list[dict[str, Any]] | None = None,
        own_serial: str | None = None,
        name: str | None = None,
    ) -> None:
        """Initialize remote device manager.

        Args:
            message_bus: Message bus for MQTT communication
            remote_devices_config: List of remote device configurations
            own_serial: Serial number of this device (to exclude from autodiscovery)
        """
        self._message_bus = message_bus
        self._devices: dict[str, RemoteDevice] = {}
        self._own_serial = own_serial
        self._name = name
        # Track autodiscovered devices separately from configured ones
        self._autodiscovered_devices: dict[str, MQTTRemoteDevice] = {}
        # Track devices that manage this boneIO (received via discovery/managed_by topic)
        self._managed_by_devices: dict[str, dict[str, Any]] = {}
        # Cycle state for CYCLE_COLOR and CYCLE_PRESET actions
        # Key: "device_id:output_id:type:action_idx", Value: current index
        self._cycle_state: dict[str, int] = {}
        self._pending_config: list[dict[str, Any]] | None = remote_devices_config
        self._initialized = False

    def add_device(self, device: RemoteDevice) -> None:
        """Dynamically add a remote device (e.g., from CAN autodiscovery).

        Args:
            device: RemoteDevice instance to register.
        """
        if device.id in self._devices:
            _LOGGER.debug("Remote device '%s' already registered, skipping", device.id)
            return
        self._devices[device.id] = device
        _LOGGER.info(
            "Registered remote device '%s' (protocol=%s)",
            device.name,
            device.protocol.value,
        )

    def _configure_devices(self, config: list[dict[str, Any]]) -> None:
        """Configure remote devices from config.

        Args:
            config: List of remote device configurations
        """
        for device_config in config:
            try:
                device = self._create_device(device_config)
                if device:
                    self._devices[device.id] = device
                    _LOGGER.info("Configured remote device '%s' (protocol=%s)", device.name, device.protocol.value)
                    # Publish managed_by to the remote device
                    self._publish_managed_by(device)
            except Exception as e:
                _LOGGER.error("Failed to configure remote device '%s': %s", device_config.get("id", "unknown"), e)

    def _publish_managed_by(self, device: RemoteDevice) -> None:
        """Publish managed_by message to remote device.

        Tells the remote device that we are managing it.
        Topic: boneio/{remote_device_id}/discovery/managed_by/{our_serial}

        Args:
            device: Remote device to notify
        """
        if not self._own_serial:
            _LOGGER.debug("Cannot publish managed_by - own_serial not set")
            return

        if not self._message_bus:
            _LOGGER.debug("Cannot publish managed_by - message_bus not set")
            return

        if not isinstance(device, MQTTRemoteDevice):
            return

        # Build topic: boneio/{remote_device}/discovery/managed_by/{our_serial}
        topic = f"{device.topic_prefix}/discovery/managed_by/{self._own_serial}"

        # Build payload with our device info
        payload = json.dumps(
            {
                "name": self._name or self._own_serial,
                "serial": self._own_serial,
            }
        )

        self._message_bus.send_message(
            topic=topic,
            payload=payload,
            retain=True,
        )
        _LOGGER.info("Published managed_by to %s (topic=%s)", device.id, topic)

    def _create_device(self, config: dict[str, Any]) -> RemoteDevice | None:
        """Create remote device from config.

        Args:
            config: Device configuration

        Returns:
            RemoteDevice instance or None if creation failed
        """
        device_id = config.get("id")
        name = config.get("name") or device_id or "unknown"
        protocol_str = config.get("protocol", "mqtt")
        device_type_str = config.get("device_type", "generic")

        if not device_id:
            _LOGGER.error("Remote device config missing 'id'")
            return None

        try:
            protocol = RemoteDeviceProtocol(protocol_str)
        except ValueError:
            _LOGGER.error("Unknown protocol '%s' for device '%s'", protocol_str, device_id)
            return None

        try:
            device_type = RemoteDeviceType(device_type_str)
        except ValueError:
            _LOGGER.warning("Unknown device_type '%s' for device '%s', using 'generic'", device_type_str, device_id)
            device_type = RemoteDeviceType.GENERIC

        # Create protocol-specific device
        if protocol == RemoteDeviceProtocol.MQTT:
            return self._create_mqtt_device(device_id, name, device_type, config)
        elif protocol == RemoteDeviceProtocol.CAN:
            _LOGGER.warning("CAN protocol not yet implemented for device '%s'", device_id)
            return None
        elif protocol == RemoteDeviceProtocol.LOX:
            _LOGGER.warning("Lox protocol not yet implemented for device '%s'", device_id)
            return None
        elif protocol == RemoteDeviceProtocol.ESPHOME_UDP:
            _LOGGER.warning("ESPHome UDP protocol not yet implemented for device '%s'", device_id)
            return None
        elif protocol == RemoteDeviceProtocol.ESPHOME_API:
            return self._create_esphome_device(device_id, name, config)
        elif protocol == RemoteDeviceProtocol.WLED:
            return self._create_wled_device(device_id, name, config)
        else:
            _LOGGER.error("Unsupported protocol '%s' for device '%s'", protocol, device_id)
            return None

    def _create_mqtt_device(
        self,
        device_id: str,
        name: str,
        device_type: RemoteDeviceType,
        config: dict[str, Any],
    ) -> MQTTRemoteDevice | None:
        """Create MQTT remote device.

        Args:
            device_id: Device ID (e.g., "blk_abc123")
            name: Device name
            device_type: Device type
            config: Full device configuration

        Returns:
            MQTTRemoteDevice instance or None if creation failed
        """
        mqtt_config = config.get("mqtt", {})
        outputs = mqtt_config.get("outputs", [])
        covers = mqtt_config.get("covers", [])

        return MQTTRemoteDevice(
            id=device_id,
            name=name,
            device_type=device_type,
            outputs=outputs,
            covers=covers,
        )

    def _create_esphome_device(
        self,
        device_id: str,
        name: str,
        config: dict[str, Any],
    ) -> RemoteDevice | None:
        """Create ESPHome API remote device.

        Args:
            device_id: Device ID
            name: Device name
            config: Full device configuration

        Returns:
            ESPHomeRemoteDevice instance or None if creation failed
        """
        from boneio.core.remote.esphome import ESPHOME_API_AVAILABLE, ESPHomeRemoteDevice

        if not ESPHOME_API_AVAILABLE:
            _LOGGER.error("aioesphomeapi not installed - cannot create ESPHome device '%s'", device_id)
            return None

        esphome_config = config.get("esphome_api", {})
        host = esphome_config.get("host")

        if not host:
            _LOGGER.error("ESPHome device '%s' missing 'host' in esphome_api config", device_id)
            return None

        port = esphome_config.get("port", 6053)
        password = esphome_config.get("password", "")
        encryption_key = esphome_config.get("encryption_key", "")
        switches = esphome_config.get("switches", [])
        lights = esphome_config.get("lights", [])
        covers = esphome_config.get("covers", [])

        return ESPHomeRemoteDevice(
            id=device_id,
            name=name,
            host=host,
            port=port,
            password=password,
            encryption_key=encryption_key,
            switches=switches,
            lights=lights,
            covers=covers,
        )

    def _create_wled_device(
        self,
        device_id: str,
        name: str,
        config: dict[str, Any],
    ) -> RemoteDevice | None:
        """Create WLED remote device.

        Args:
            device_id: Device ID
            name: Device name
            config: Full device configuration

        Returns:
            WLEDRemoteDevice instance or None if creation failed
        """
        from boneio.core.remote.wled import WLEDRemoteDevice

        wled_config = config.get("wled", {})
        host = wled_config.get("host")

        if not host:
            _LOGGER.error("WLED device '%s' missing 'host' in wled config", device_id)
            return None

        port = wled_config.get("port", 80)
        segments = wled_config.get("segments", [])

        return WLEDRemoteDevice(
            id=device_id,
            name=name,
            host=host,
            port=port,
            segments=segments,
        )

    async def initialize(self, delay_seconds: float = 10.0) -> None:
        """Initialize remote devices in background.

        Configures devices from pending config (importing ESPHome/WLED modules
        only at this point) and starts persistent ESPHome and WLED connections.
        This runs as a background task so it does not block application startup.

        Args:
            delay_seconds: Seconds to wait before starting connections
        """
        # 1. Configure devices (this triggers lazy module imports)
        if self._pending_config:
            _LOGGER.debug("Configuring %d remote device(s) in background...", len(self._pending_config))
            self._configure_devices(self._pending_config)
            self._pending_config = None
        self._initialized = True

        # 2. Start WLED WebSocket listeners immediately (lightweight)
        self._start_wled_ws_listeners()

        # 3. Start ESPHome connections after delay
        esphome_devices = [
            (device_id, device)
            for device_id, device in self._devices.items()
            if device.protocol == RemoteDeviceProtocol.ESPHOME_API
        ]

        if not esphome_devices:
            return

        _LOGGER.debug(
            "Delaying ESPHome connections by %.1f seconds (found %d devices)", delay_seconds, len(esphome_devices)
        )
        await asyncio.sleep(delay_seconds)

        _LOGGER.debug("Starting ESPHome connections...")
        for device_id, device in esphome_devices:
            try:
                await cast(Any, device).start_connection()
                _LOGGER.info("Started connection for ESPHome device '%s'", device_id)
            except Exception as e:
                _LOGGER.error("Failed to start connection for ESPHome device '%s': %s", device_id, e)

    def _start_wled_ws_listeners(self) -> None:
        """Start WebSocket listeners for all WLED devices.

        Each WLED device gets a background task that maintains a persistent
        WebSocket connection for real-time state updates.
        """
        wled_devices = [
            (device_id, device)
            for device_id, device in self._devices.items()
            if device.protocol == RemoteDeviceProtocol.WLED
        ]

        for device_id, device in wled_devices:
            try:
                cast(Any, device).start_ws_listener()
            except Exception as e:
                _LOGGER.error("Failed to start WLED WS for '%s': %s", device_id, e)

    async def stop_all_connections(self) -> None:
        """Stop all persistent connections.

        This should be called during application shutdown.
        Closes ESPHome connections and WLED aiohttp sessions.
        """
        for device_id, device in self._devices.items():
            try:
                if device.protocol == RemoteDeviceProtocol.ESPHOME_API:
                    await cast(Any, device).disconnect()
                    _LOGGER.info("Stopped connection for ESPHome device '%s'", device_id)
                elif device.protocol == RemoteDeviceProtocol.WLED:
                    await cast(Any, device).close()
                    _LOGGER.info("Closed session for WLED device '%s'", device_id)
            except Exception as e:
                _LOGGER.error("Failed to stop connection for device '%s': %s", device_id, e)

    def get_device(self, device_id: str) -> RemoteDevice | None:
        """Get remote device by ID.

        Args:
            device_id: Device ID

        Returns:
            RemoteDevice instance or None if not found
        """
        return self._devices.get(device_id)

    def get_all_devices(self) -> dict[str, RemoteDevice]:
        """Get all configured remote devices.

        Returns:
            Dictionary of device_id -> RemoteDevice
        """
        return self._devices.copy()

    async def control_output(
        self,
        device_id: str,
        output_id: str,
        action: str,
        brightness: int | None = None,
        brightness_step: int | float | None = None,
        color_temp: int | None = None,
        rgb: list[int] | tuple[int, int, int] | None = None,
        transition: float | None = None,
        effect: int | str | None = None,
        palette: int | None = None,
        effect_speed: int | None = None,
        effect_intensity: int | None = None,
    ) -> bool:
        """Control output on remote device (BoneIO MQTT, ESPHome API, or WLED).

        Automatically detects device protocol and routes to appropriate method.
        For ESPHome devices, output_id can be a switch or light entity.
        For WLED devices, output_id can be "main" or segment ID.

        Args:
            device_id: ID of the remote device
            output_id: ID of the output/switch/light to control
            action: Action to perform (ON, OFF, TOGGLE, BRIGHTNESS_UP, BRIGHTNESS_DOWN, BRIGHTNESS_UP_CYCLE, BRIGHTNESS_DOWN_CYCLE, SET_BRIGHTNESS)
            brightness: Brightness level (0-255) - for ESPHome/WLED lights
            color_temp: Color temperature in mireds - only for ESPHome lights
            rgb: RGB color as [R, G, B] list or tuple (0-255 each) - for ESPHome/WLED lights
            transition: Transition time in seconds - for ESPHome/WLED lights
            effect: Effect name (str for ESPHome) or effect ID (int for WLED)
            palette: WLED color palette ID
            effect_speed: WLED effect speed (0-255)
            effect_intensity: WLED effect intensity (0-255)

        Returns:
            True if command was sent successfully
        """
        device = self.get_device(device_id)
        if not device:
            _LOGGER.error("Remote device '%s' not found", device_id)
            return False

        # For ESPHome devices, try to determine if it's a switch or light
        if device.protocol == RemoteDeviceProtocol.ESPHOME_API:
            # Check if output_id is a light
            esphome_device = cast(Any, device)
            if esphome_device.has_light(output_id):
                _LOGGER.debug("Controlling ESPHome light '%s' on device '%s'", output_id, device_id)
                # Convert rgb list to tuple[int, int, int] if needed
                rgb_tuple: tuple[int, int, int] | None = None
                if rgb and len(rgb) >= 3:
                    rgb_tuple = (rgb[0], rgb[1], rgb[2])
                # For ESPHome, effect must be a string
                esphome_effect = str(effect) if effect is not None else None
                return await esphome_device.control_light(
                    light_id=output_id,
                    action=action,
                    brightness=brightness,
                    brightness_step=brightness_step,
                    color_temp=color_temp,
                    rgb=rgb_tuple,
                    transition=transition if transition is not None else 0.0,
                    effect=esphome_effect,
                )
            # Otherwise treat as switch
            _LOGGER.debug("Controlling ESPHome switch '%s' on device '%s'", output_id, device_id)
            return await esphome_device.control_switch(
                switch_id=output_id,
                action=action,
            )

        # For WLED devices, use fire-and-forget HTTP JSON API.
        # WLED HTTP requests can stall for seconds when the device is
        # unreachable (DNS timeout on .local), which blocks the EventBus
        # worker and freezes ALL input events.  Fire-and-forget schedules
        # the request as a background task so the caller returns immediately.
        if device.protocol == RemoteDeviceProtocol.WLED:
            _LOGGER.debug("Controlling WLED '%s' segment '%s' on device '%s'", output_id, action, device_id)
            # Parse segment_id - "main" means whole device, otherwise it's segment ID
            segment_id = None if output_id == "main" else int(output_id)
            # Convert rgb list to tuple if needed
            wled_rgb: tuple[int, int, int] | None = None
            if rgb and len(rgb) >= 3:
                wled_rgb = (rgb[0], rgb[1], rgb[2])
            from boneio.core.remote.wled import WLEDRemoteDevice
            wled_device = cast(WLEDRemoteDevice, device)
            wled_device.control_light_fire_and_forget(
                segment_id=segment_id,
                action=action,
                brightness=brightness,
                brightness_step=brightness_step,
                rgb=wled_rgb,
                transition=transition if transition is not None else 0.0,
                effect=effect if isinstance(effect, int) else None,
                palette=palette,
                effect_speed=effect_speed,
                effect_intensity=effect_intensity,
            )
            return True  # Optimistic: task is scheduled

        # For MQTT devices, use standard control_output
        return await device.control_output(
            output_id=output_id,
            action=action,
            message_bus=self._message_bus,
        )

    async def cycle_color(
        self,
        device_id: str,
        output_id: str,
        colors: list[list[int]],
        action_idx: int = 0,
        transition: float | None = None,
    ) -> bool:
        """Cycle through a list of RGB colors on a remote device light.

        Each call advances to the next color in the list, wrapping around.

        Args:
            device_id: ID of the remote device
            output_id: ID of the light to control
            colors: List of RGB colors, each as [R, G, B] (0-255)
            action_idx: Action index for unique cycle state tracking
            transition: Transition time in seconds

        Returns:
            True if command was sent successfully
        """
        if not colors:
            _LOGGER.warning("CYCLE_COLOR: no colors defined for %s:%s", device_id, output_id)
            return False

        cycle_key = f"{device_id}:{output_id}:color:{action_idx}"
        cycle_idx = self._cycle_state.get(cycle_key, 0) % len(colors)
        rgb = colors[cycle_idx]
        self._cycle_state[cycle_key] = cycle_idx + 1

        _LOGGER.debug("CYCLE_COLOR: %s:%s -> color %d/%d = %s", device_id, output_id, cycle_idx + 1, len(colors), rgb)

        return await self.control_output(
            device_id=device_id,
            output_id=output_id,
            action="ON",
            rgb=rgb,
            transition=transition,
        )

    async def cycle_preset(
        self,
        device_id: str,
        output_id: str,
        presets: list[str | int],
        action_idx: int = 0,
        transition: float | None = None,
    ) -> bool:
        """Cycle through a list of effects/presets on a remote device light.

        Each call advances to the next preset in the list, wrapping around.
        For ESPHome: presets are effect name strings.
        For WLED: presets are effect IDs (integers).

        Args:
            device_id: ID of the remote device
            output_id: ID of the light to control
            presets: List of effect names (str) or effect IDs (int)
            action_idx: Action index for unique cycle state tracking
            transition: Transition time in seconds

        Returns:
            True if command was sent successfully
        """
        if not presets:
            _LOGGER.warning("CYCLE_PRESET: no presets defined for %s:%s", device_id, output_id)
            return False

        cycle_key = f"{device_id}:{output_id}:preset:{action_idx}"
        cycle_idx = self._cycle_state.get(cycle_key, 0) % len(presets)
        preset = presets[cycle_idx]
        self._cycle_state[cycle_key] = cycle_idx + 1

        _LOGGER.debug(
            "CYCLE_PRESET: %s:%s -> preset %d/%d = %s", device_id, output_id, cycle_idx + 1, len(presets), preset
        )

        return await self.control_output(
            device_id=device_id,
            output_id=output_id,
            action="ON",
            effect=preset,
            transition=transition,
        )

    async def control_cover(
        self,
        device_id: str,
        cover_id: str,
        action: str,
        **kwargs,
    ) -> bool:
        """Control cover on remote device (BoneIO MQTT or ESPHome API).

        Automatically detects device protocol and routes to appropriate method.

        Args:
            device_id: ID of the remote device
            cover_id: ID of the cover to control
            action: Action to perform (OPEN, CLOSE, STOP, TOGGLE, etc.)
            **kwargs: Additional parameters (position, tilt_position)

        Returns:
            True if command was sent successfully
        """
        device = self.get_device(device_id)
        if not device:
            _LOGGER.error("Remote device '%s' not found", device_id)
            return False

        # For ESPHome devices, use native API
        if device.protocol == RemoteDeviceProtocol.ESPHOME_API:
            _LOGGER.debug("Controlling ESPHome cover '%s' on device '%s'", cover_id, device_id)
            return await cast(Any, device).control_cover(
                cover_id=cover_id,
                action=action,
                **kwargs,
            )

        # For MQTT devices, use standard control_cover
        return await device.control_cover(
            cover_id=cover_id,
            action=action,
            message_bus=self._message_bus,
            **kwargs,
        )

    def get_cover_state(self, device_id: str, cover_id: str) -> dict[str, Any] | None:
        """Get current cover state from an ESPHome remote device.

        Returns the cached state dict containing position, tilt,
        current_operation, and last_known_operation.

        Args:
            device_id: ID of the remote device
            cover_id: ID of the cover

        Returns:
            State dictionary or None if device/cover not found or not ESPHome
        """
        device = self.get_device(device_id)
        if not device or device.protocol != RemoteDeviceProtocol.ESPHOME_API:
            return None
        return cast(Any, device)._cover_states.get(cover_id)

    async def wait_for_cover_idle(
        self,
        device_id: str,
        cover_id: str,
        timeout: float = 120.0,
        poll_interval: float = 0.5,
    ) -> bool:
        """Wait for an ESPHome cover to reach IDLE state.

        Polls the cached cover state until current_operation becomes 0 (IDLE)
        or the timeout expires.

        Args:
            device_id: ID of the remote device
            cover_id: ID of the cover to monitor
            timeout: Maximum time to wait in seconds (default: 120s)
            poll_interval: Time between polls in seconds (default: 0.5s)

        Returns:
            True if cover reached IDLE, False on timeout
        """
        device = self.get_device(device_id)
        if not device or device.protocol != RemoteDeviceProtocol.ESPHOME_API:
            return False

        esphome = cast(Any, device)
        start = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start < timeout:
            state = esphome._cover_states.get(cover_id, {})
            if state.get("current_operation", 0) == 0:
                return True
            await asyncio.sleep(poll_interval)

        _LOGGER.warning(
            "Timeout (%.0fs) waiting for cover '%s' on device '%s' to reach IDLE",
            timeout, cover_id, device_id,
        )
        return False

    async def reload(self, remote_devices_config: list[dict[str, Any]] | None = None) -> None:
        """Reload remote devices from config.

        Stops existing ESPHome connections, reconfigures devices,
        and starts new ESPHome connections.

        Args:
            remote_devices_config: New list of remote device configurations
        """
        _LOGGER.info("Reloading remote devices configuration")

        # Stop existing ESPHome connections first
        await self.stop_all_connections()

        self._devices.clear()

        if remote_devices_config:
            self._configure_devices(remote_devices_config)

        # Start WLED WS listeners immediately
        self._start_wled_ws_listeners()

        # Start ESPHome connections immediately (no delay for reload)
        await self._start_esphome_connections_immediate()

        _LOGGER.info("Reloaded %d remote devices", len(self._devices))

    async def _start_esphome_connections_immediate(self) -> None:
        """Start ESPHome connections immediately without delay.

        Used during reload when we want connections to start right away.
        """
        esphome_devices = [
            (device_id, device)
            for device_id, device in self._devices.items()
            if device.protocol == RemoteDeviceProtocol.ESPHOME_API
        ]

        if not esphome_devices:
            return

        _LOGGER.info("Starting %d ESPHome connection(s)...", len(esphome_devices))
        for device_id, device in esphome_devices:
            try:
                await cast(Any, device).start_connection()
                _LOGGER.info("Started connection for ESPHome device '%s'", device_id)
            except Exception as e:
                _LOGGER.error("Failed to start connection for ESPHome device '%s': %s", device_id, e)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation.

        Returns:
            Dictionary with all devices information
        """
        return {device_id: device.to_dict() for device_id, device in self._devices.items()}

    # ==================== Autodiscovery ====================

    def get_discovery_topic(self) -> str:
        """Get MQTT topic pattern for autodiscovery subscription.

        Returns:
            Topic pattern like "boneio/+/discovery/#"
        """
        return f"{DISCOVERY_TOPIC_PREFIX}/+/{DISCOVERY_SUBTOPIC}/#"

    def is_discovery_topic(self, topic: str) -> bool:
        """Check if topic is a discovery topic.

        Args:
            topic: MQTT topic string

        Returns:
            True if topic matches discovery pattern
        """
        parts = topic.split("/")
        # Pattern: boneio/{device_id}/discovery/{type}
        return len(parts) >= 4 and parts[0] == DISCOVERY_TOPIC_PREFIX and parts[2] == DISCOVERY_SUBTOPIC

    def handle_discovery_message(self, topic: str, payload: str) -> None:
        """Handle incoming discovery message from another BoneIO device.

        Parses the discovery payload and creates/updates the remote device.

        Args:
            topic: MQTT topic (e.g., "boneio/blk_abc123/discovery/outputs")
            payload: JSON payload with discovery data
        """
        if not self.is_discovery_topic(topic):
            return

        parts = topic.split("/")
        device_id = parts[1]  # e.g., "blk_abc123"
        discovery_type = parts[3] if len(parts) > 3 else None  # e.g., "outputs", "covers", "device"

        # Handle managed_by BEFORE skipping own device check
        # Topic: boneio/{our_device}/discovery/managed_by/{manager_serial}
        # This is for messages TO our device, so device_id will be our serial
        if discovery_type == "managed_by":
            manager_serial = parts[4] if len(parts) > 4 else None
            if manager_serial and self._own_serial != manager_serial:
                try:
                    data = json.loads(payload) if payload else None
                except json.JSONDecodeError as e:
                    _LOGGER.warning("Invalid JSON in managed_by payload: %s", e)
                    return
                if data:
                    self.handle_managed_by_discovery(manager_serial, data)
                else:
                    # Empty payload - remove managed_by entry
                    if manager_serial in self._managed_by_devices:
                        del self._managed_by_devices[manager_serial]
                        _LOGGER.info("Removed managed_by device: %s", manager_serial)
            return

        # Skip our own device (for other discovery types)
        if self._own_serial and device_id == self._own_serial:
            _LOGGER.debug("Ignoring discovery from own device: %s", device_id)
            return

        # Skip if this device is already configured manually
        if device_id in self._devices:
            _LOGGER.debug("Device %s is manually configured, updating from discovery", device_id)
            self._update_configured_device_from_discovery(device_id, discovery_type, payload)
            return

        # Parse payload
        try:
            data = json.loads(payload) if payload else None
        except json.JSONDecodeError as e:
            _LOGGER.warning("Invalid JSON in discovery payload for %s: %s", topic, e)
            return

        if data is None:
            # Empty payload means device is offline/removed
            self._remove_autodiscovered_device(device_id)
            return

        # Process discovery by type
        if discovery_type == "device":
            self._handle_device_discovery(device_id, data)
        elif discovery_type == "outputs":
            self._handle_outputs_discovery(device_id, data)
        elif discovery_type == "covers":
            self._handle_covers_discovery(device_id, data)
        else:
            _LOGGER.debug("Ignoring discovery type '%s' for device %s", discovery_type, device_id)

    def _handle_device_discovery(self, device_id: str, data: dict[str, Any]) -> None:
        """Handle device info discovery.

        Creates a new autodiscovered device if not exists.

        Args:
            device_id: Device ID (e.g., "blk_abc123")
            data: Device info payload
        """
        if device_id not in self._autodiscovered_devices:
            name = data.get("name", device_id)
            device = MQTTRemoteDevice(
                id=device_id,
                name=name,
                device_type=RemoteDeviceType.BONEIO_BLACK,
            )
            self._autodiscovered_devices[device_id] = device
            _LOGGER.info(
                "Autodiscovered BoneIO device: %s (%s), firmware=%s", name, device_id, data.get("firmware", "unknown")
            )
        else:
            # Update name if changed
            device = self._autodiscovered_devices[device_id]
            new_name = data.get("name")
            if new_name and new_name != device.name:
                device._name = new_name
                _LOGGER.debug("Updated autodiscovered device name: %s -> %s", device_id, new_name)

    def _handle_outputs_discovery(self, device_id: str, data: list[dict[str, Any]]) -> None:
        """Handle outputs discovery.

        Updates outputs list for autodiscovered device.

        Args:
            device_id: Device ID
            data: List of output definitions
        """
        device = self._autodiscovered_devices.get(device_id)
        if not device:
            # Device info not received yet, create placeholder
            device = MQTTRemoteDevice(
                id=device_id,
                name=device_id,
                device_type=RemoteDeviceType.BONEIO_BLACK,
            )
            self._autodiscovered_devices[device_id] = device
            _LOGGER.debug("Created placeholder for autodiscovered device: %s", device_id)

        # Update outputs
        device.set_outputs(data)
        _LOGGER.debug("Updated outputs for autodiscovered device %s: %d outputs", device_id, len(data))

    def _handle_covers_discovery(self, device_id: str, data: list[dict[str, Any]]) -> None:
        """Handle covers discovery.

        Updates covers list for autodiscovered device.

        Args:
            device_id: Device ID
            data: List of cover definitions
        """
        device = self._autodiscovered_devices.get(device_id)
        if not device:
            # Device info not received yet, create placeholder
            device = MQTTRemoteDevice(
                id=device_id,
                name=device_id,
                device_type=RemoteDeviceType.BONEIO_BLACK,
            )
            self._autodiscovered_devices[device_id] = device
            _LOGGER.debug("Created placeholder for autodiscovered device: %s", device_id)

        # Update covers
        device.set_covers(data)
        _LOGGER.debug("Updated covers for autodiscovered device %s: %d covers", device_id, len(data))

    def _update_configured_device_from_discovery(
        self, device_id: str, discovery_type: str | None, payload: str
    ) -> None:
        """Update manually configured device with discovery data.

        This allows manually configured devices to receive autodiscovered
        outputs/covers without overwriting the manual configuration.

        Args:
            device_id: Device ID
            discovery_type: Type of discovery (outputs, covers, etc.)
            payload: JSON payload
        """
        device = self._devices.get(device_id)
        if not device or not isinstance(device, MQTTRemoteDevice):
            return

        try:
            data = json.loads(payload) if payload else None
        except json.JSONDecodeError:
            return

        if data is None:
            return

        if discovery_type == "outputs" and not device.outputs:
            # Only update if device has no manually configured outputs
            device.set_outputs(data)
            _LOGGER.info("Updated configured device %s with autodiscovered outputs: %d", device_id, len(data))
        elif discovery_type == "covers":
            if not device.covers:
                # No manually configured covers — use discovery data as-is
                device.set_covers(data)
                _LOGGER.info("Updated configured device %s with autodiscovered covers: %d", device_id, len(data))
            else:
                # Covers exist — enrich with tilt support info from discovery
                discovery_map = {c.get("id"): c for c in data if c.get("id")}
                updated = False
                for cover in device.covers:
                    disc = discovery_map.get(cover.get("id"))
                    if disc:
                        if "supports_tilt" not in cover and "supports_tilt" in disc:
                            cover["supports_tilt"] = disc["supports_tilt"]
                            updated = True
                        if "kind" not in cover and "kind" in disc:
                            cover["kind"] = disc["kind"]
                            updated = True
                if updated:
                    _LOGGER.debug("Enriched configured covers on %s with tilt info from discovery", device_id)

    def _remove_autodiscovered_device(self, device_id: str) -> None:
        """Remove autodiscovered device from memory only.

        This is called when receiving empty discovery payload.
        Does NOT clear MQTT retained messages.

        Args:
            device_id: Device ID to remove
        """
        if device_id in self._autodiscovered_devices:
            del self._autodiscovered_devices[device_id]
            _LOGGER.info("Removed autodiscovered device: %s", device_id)

    def remove_autodiscovered_device_from_mqtt(self, device_id: str) -> None:
        """Remove autodiscovered device and clear MQTT retained messages.

        This sends empty payloads to all discovery topics for the device,
        which clears retained messages from MQTT broker.

        Args:
            device_id: Device ID to remove
        """
        if not self._message_bus:
            _LOGGER.error("Cannot remove device from MQTT - message_bus not set")
            return

        # List of all discovery subtopics
        discovery_subtopics = [
            "device",
            "outputs",
            "covers",
            "inputs",
            "sensors",
            "modbus",
        ]

        # Send empty payload to each discovery topic to clear retained messages
        for subtopic in discovery_subtopics:
            topic = f"{DISCOVERY_TOPIC_PREFIX}/{device_id}/{DISCOVERY_SUBTOPIC}/{subtopic}"
            self._message_bus.send_message(
                topic=topic,
                payload=None,  # Empty payload clears retained message
                retain=True,
            )
            _LOGGER.debug("Cleared MQTT retained message for %s", topic)

        # Remove from memory
        if device_id in self._autodiscovered_devices:
            del self._autodiscovered_devices[device_id]
            _LOGGER.info("Removed autodiscovered device from MQTT and memory: %s", device_id)
        else:
            _LOGGER.warning("Device %s not in autodiscovered list, but cleared MQTT messages", device_id)

    def get_autodiscovered_device(self, device_id: str) -> MQTTRemoteDevice | None:
        """Get autodiscovered device by ID.

        Args:
            device_id: Device ID

        Returns:
            MQTTRemoteDevice or None
        """
        return self._autodiscovered_devices.get(device_id)

    def get_all_autodiscovered_devices(self) -> dict[str, MQTTRemoteDevice]:
        """Get all autodiscovered devices.

        Returns:
            Dictionary of device_id -> MQTTRemoteDevice
        """
        return self._autodiscovered_devices.copy()

    def get_all_available_devices(self) -> dict[str, RemoteDevice]:
        """Get all available devices (configured + autodiscovered).

        Configured devices take precedence over autodiscovered ones.

        Returns:
            Dictionary of device_id -> RemoteDevice
        """
        # Start with autodiscovered, then overlay configured
        all_devices: dict[str, RemoteDevice] = {}
        for device_id, device in self._autodiscovered_devices.items():
            all_devices[device_id] = device
        for device_id, device in self._devices.items():
            all_devices[device_id] = device
        return all_devices

    def autodiscovered_to_dict(self) -> dict[str, Any]:
        """Convert autodiscovered devices to dictionary representation.

        Returns:
            Dictionary with autodiscovered devices information
        """
        _LOGGER.debug(
            "autodiscovered_to_dict called, _autodiscovered_devices has %d items: %s",
            len(self._autodiscovered_devices),
            list(self._autodiscovered_devices.keys()),
        )
        return {device_id: device.to_dict() for device_id, device in self._autodiscovered_devices.items()}

    def get_managed_by_devices(self) -> dict[str, dict[str, Any]]:
        """Get devices that manage this boneIO.

        Returns:
            Dictionary of serial -> device info
        """
        return self._managed_by_devices.copy()

    def handle_managed_by_discovery(self, manager_serial: str, data: dict[str, Any] | None) -> None:
        """Handle managed_by discovery message.

        Called when another boneIO publishes to our discovery/managed_by topic.

        Args:
            manager_serial: Serial of the managing device
            data: Device info (id, name, serial) or None to remove
        """
        if data is None:
            # Empty payload means device no longer manages us
            if manager_serial in self._managed_by_devices:
                del self._managed_by_devices[manager_serial]
                _LOGGER.info("Removed managed_by device: %s", manager_serial)
            return

        self._managed_by_devices[manager_serial] = {
            "id": data.get("id", manager_serial),
            "name": data.get("name", manager_serial),
            "serial": manager_serial,
        }
        _LOGGER.info("Added managed_by device: %s (%s)", data.get("name", manager_serial), manager_serial)
