"""Lox UDP Client for BoneIO.

Implements the Loxone UDP protocol for bidirectional communication
between BoneIO and a Loxone Miniserver:

- Receiving commands from Miniserver (e.g. "OUT_04=ON")
- Sending state feedback to Miniserver (e.g. "OUT_04=ON", "cover1=50")
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any

from boneio.const import NONE as OUTPUT_NONE
from boneio.const import cover_actions, output_actions
from boneio.core.messaging.basic import MessageBus

if TYPE_CHECKING:
    from boneio.core.config import ConfigHelper
    from boneio.core.manager import Manager
    from boneio.integration.homeassistant import HomeAssistantDiscoveryMessage

_LOGGER = logging.getLogger(__name__)

# Entity types whose state changes should be forwarded to Loxone
_LOX_ENTITY_TYPES = frozenset(("output", "cover", "sensor", "event", "binary_sensor", "input"))


class LoxUDPProtocol(asyncio.DatagramProtocol):
    """Protocol for handling Lox UDP communication."""

    def __init__(self, callback: Callable[[str, str], Coroutine[Any, Any, None]]):
        self._callback = callback
        self._loop = asyncio.get_running_loop()

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        """Handle connection established."""
        self.transport = transport

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        """Handle incoming datagram.

        Expected message format: "device_id=value" or just "device_id".
        """
        try:
            message = data.decode("utf-8").strip()
            _LOGGER.info("Received Lox UDP message: %s from %s", message, addr)

            # Message format expected: "device=value" or just "device"
            if "=" in message:
                device, payload = message.split("=", 1)
            else:
                device = message
                payload = "pressed"

            self._loop.create_task(self._callback(device, payload))
        except Exception as e:
            _LOGGER.error("Error processing Lox UDP datagram: %s", e)


class LoxUDPClient(MessageBus):
    """Represent a Lox UDP client.

    This message bus translates between BoneIO's internal MQTT-style
    topic/payload model and the simple "key=value" UDP protocol
    expected by Loxone Miniserver.

    Outgoing (BoneIO → Miniserver):
        topic "boneio/{serial}/output/relay1" + payload {"state": "ON"}
        → UDP datagram "relay1=ON" sent to Miniserver

    Incoming (Miniserver → BoneIO):
        UDP datagram "relay1=ON"
        → routed to Manager as "boneio/{serial}/cmd/output/relay1/set" = "ON"
    """

    def __init__(
        self,
        config_helper: ConfigHelper,
        host: str,
        send_port: int,
        listen_port: int,
    ) -> None:
        """Set up client.

        Args:
            config_helper: BoneIO configuration helper.
            host: Loxone Miniserver IP address.
            send_port: Port on Miniserver to send state feedback to.
            listen_port: Port BoneIO listens on for commands from Miniserver.
        """
        self._manager: Manager | None = None
        self._config_helper = config_helper
        self.host = host
        self.send_port = send_port
        self.listen_port = listen_port
        self._transport: asyncio.DatagramTransport | None = None
        self._listeners: dict[str, Callable[[str, str], Coroutine[Any, Any, None]]] = {}
        self._state = False

    def send_message(
        self,
        topic: str,
        payload: str | int | bytes | dict[str, Any] | HomeAssistantDiscoveryMessage | None,
        retain: bool = False,
        qos: int = 0,
    ) -> None:
        """Send a state update to Loxone Miniserver via UDP.

        Converts BoneIO's MQTT-style topic/payload into a simple UDP
        datagram in the format "device_id=state_value".

        Topic format: boneio/{serial}/{entity_type}/{device_id}
        or:           boneio/{serial}/{entity_type}/{device_id}/state
        or:           boneio/{serial}/{entity_type}/{device_id}/pos

        Args:
            topic: MQTT-style topic string.
            payload: State payload (dict, string, bytes, int, or None).
            retain: Ignored for UDP.
            qos: Ignored for UDP.
        """
        if payload is None:
            return

        topic_str = str(topic)
        parts = topic_str.split("/")

        # Need at least: prefix/serial/entity_type/device_id
        if len(parts) < 4:
            return

        # Skip HA Discovery messages (homeassistant/*/config topics)
        if parts[0] == "homeassistant" or topic_str.endswith("/config"):
            return

        # Skip command topics — we only send state feedback, not commands
        if "cmd" in parts:
            return

        # Determine entity_type and device_id based on topic structure
        # Standard: boneio/{serial}/{entity_type}/{device_id}
        # With suffix: boneio/{serial}/{entity_type}/{device_id}/state
        # With suffix: boneio/{serial}/{entity_type}/{device_id}/pos
        entity_type = parts[2] if len(parts) >= 3 else ""
        suffix = parts[-1] if len(parts) >= 5 else ""

        # For topics with suffix (state/pos), device_id is parts[-2]
        if suffix in ("state", "pos", "set"):
            device_id = parts[-2]
        else:
            device_id = parts[-1]

        # Skip non-relevant entity types
        if entity_type not in _LOX_ENTITY_TYPES:
            return

        # Skip "set" suffix — those are incoming commands, not state feedback
        if suffix == "set":
            return

        # Extract state value from payload
        state_value = self._extract_state_value(payload)
        if not state_value:
            return

        self._send_udp(device_id, state_value)

    @staticmethod
    def _extract_state_value(
        payload: str | int | bytes | dict[str, Any] | HomeAssistantDiscoveryMessage,
    ) -> str:
        """Extract a simple state string from various payload formats.

        Args:
            payload: The message payload in any supported format.

        Returns:
            State value as string, or empty string if extraction fails.
        """
        if isinstance(payload, dict):
            # Try standard keys: {"state": "ON"}, {"value": "50"}
            state_value = payload.get("state", payload.get("value", ""))
            if state_value:
                return str(state_value)
            # Fallback: use first value from dict
            if payload:
                return str(next(iter(payload.values()), ""))
            return ""
        if isinstance(payload, bytes):
            return payload.decode("utf-8")
        return str(payload)

    def _send_udp(self, device_id: str, state_value: str) -> None:
        """Send a UDP datagram to Loxone Miniserver.

        Args:
            device_id: Entity identifier (e.g. "relay1", "cover1").
            state_value: State value string (e.g. "ON", "50").
        """
        try:
            udp_msg = f"{device_id}={state_value}".encode()
            if self._transport:
                self._transport.sendto(udp_msg, (self.host, self.send_port))
                _LOGGER.debug(
                    "Sent Lox UDP message: %s to %s:%s",
                    udp_msg.decode("utf-8"),
                    self.host,
                    self.send_port,
                )
            else:
                _LOGGER.debug(
                    "Lox UDP transport not ready, dropping: %s",
                    udp_msg.decode("utf-8"),
                )
        except Exception as e:
            _LOGGER.error("Error sending Lox UDP message: %s", e)

    @property
    def state(self) -> bool:
        """State of Lox Client."""
        return self._state

    async def start_client(self) -> None:
        """Start UDP server and client."""
        try:
            loop = asyncio.get_running_loop()
            transport, protocol = await loop.create_datagram_endpoint(
                lambda: LoxUDPProtocol(self._handle_incoming),
                local_addr=("0.0.0.0", self.listen_port),
            )
            self._transport = transport
            self._state = True
            _LOGGER.info(
                "Lox UDP client started. Listening on port %s, sending to %s:%s",
                self.listen_port,
                self.host,
                self.send_port,
            )

            # Announce online status so Lox Miniserver knows we are alive
            self._transport.sendto(b"boneio=online", (self.host, self.send_port))

            while True:
                await asyncio.sleep(3600)

        except asyncio.CancelledError:
            _LOGGER.info("Lox UDP client shutting down...")
        except Exception as e:
            _LOGGER.error("Failed to start Lox UDP client: %s", e)
            self._state = False
        finally:
            if self._transport:
                self._transport.close()

    def set_manager(self, manager: Manager) -> None:
        """Set manager reference for routing incoming commands."""
        self._manager = manager

    async def announce_offline(self) -> None:
        """Announce offline status to Miniserver."""
        if self._transport:
            self._transport.sendto(b"boneio=offline", (self.host, self.send_port))

    async def subscribe_and_listen(self, topic: str, callback: Callable[[str, str], Coroutine[Any, Any, None]]) -> None:
        """Register a listener for a topic pattern."""
        self._listeners[topic] = callback

    async def unsubscribe_and_stop_listen(self, topic: str) -> None:
        """Unregister a listener."""
        if topic in self._listeners:
            del self._listeners[topic]

    async def _handle_incoming(self, device: str, payload: str) -> None:
        """Handle incoming Lox messages and execute commands directly.

        Resolves the device name to an output, output group, or cover and
        executes the command (ON/OFF/TOGGLE) directly on the entity.

        Falls back to case-insensitive lookup if exact match fails, since
        Loxone may alter the casing of device identifiers.

        Args:
            device: Device identifier from UDP message (e.g. "OUT_10").
            payload: Command value from UDP message (e.g. "ON").
        """
        _LOGGER.info("Lox UDP incoming command: %s = %s", device, payload)

        if not self._manager:
            _LOGGER.warning("Lox UDP: manager not set, ignoring command %s=%s", device, payload)
            return

        try:
            # --- Resolve target entity ---
            target = self._manager.outputs.get_output(device)
            entity_type = "output" if target else None

            if not target:
                target = self._manager.outputs.get_output_group(device)
                entity_type = "group" if target else None

            if not target:
                cover = self._manager.covers.get_cover(device)
                if cover:
                    target = cover
                    entity_type = "cover"

            # Fallback: case-insensitive lookup for outputs
            if not target:
                device_lower = device.lower()
                for oid, out in self._manager.outputs.get_all_outputs().items():
                    if oid.lower() == device_lower:
                        target = out
                        entity_type = "output"
                        _LOGGER.info(
                            "Lox UDP: matched '%s' to output '%s' (case-insensitive)",
                            device,
                            oid,
                        )
                        break

            if not target:
                _LOGGER.warning(
                    "Lox UDP: device '%s' not found in outputs, groups, or covers",
                    device,
                )
                return

            # --- Notify explicit listeners (for compatibility) ---
            if self._listeners:
                cmd_prefix = self._config_helper.cmd_topic_prefix
                msg_type_str = entity_type if entity_type != "group" else "output"
                full_topic = f"{cmd_prefix}{msg_type_str}/{device}/set"
                for listen_topic, callback in self._listeners.items():
                    if listen_topic == full_topic or (
                        listen_topic.endswith("/#") and full_topic.startswith(listen_topic[:-2])
                    ):
                        await callback(full_topic, payload)

            # --- Execute command ---
            action_name = payload.upper()

            if entity_type in ("output", "group"):
                if getattr(target, "output_type", None) == OUTPUT_NONE:
                    _LOGGER.debug("Lox UDP: ignoring command for '%s' (output_type=none)", device)
                    return

                action_method_name = output_actions.get(action_name)
                if not action_method_name:
                    _LOGGER.warning(
                        "Lox UDP: unknown output action '%s' for device '%s'",
                        action_name,
                        device,
                    )
                    return

                action_method = getattr(target, action_method_name, None)
                if not action_method:
                    _LOGGER.error(
                        "Lox UDP: output '%s' has no method '%s'",
                        device,
                        action_method_name,
                    )
                    return

                _LOGGER.info(
                    "Lox UDP: executing %s on %s '%s'",
                    action_method_name,
                    entity_type,
                    device,
                )
                await action_method()

            elif entity_type == "cover":
                action_method_name = cover_actions.get(action_name)
                if not action_method_name:
                    # Try as position value (e.g. "50")
                    try:
                        position = int(payload)
                        _LOGGER.info(
                            "Lox UDP: setting cover '%s' position to %d",
                            device,
                            position,
                        )
                        await target.set_cover_position(position)
                        return
                    except ValueError:
                        _LOGGER.warning(
                            "Lox UDP: unknown cover action '%s' for device '%s'",
                            action_name,
                            device,
                        )
                        return

                action_method = getattr(target, action_method_name, None)
                if action_method:
                    _LOGGER.info(
                        "Lox UDP: executing %s on cover '%s'",
                        action_method_name,
                        device,
                    )
                    await action_method()
                else:
                    _LOGGER.error(
                        "Lox UDP: cover '%s' has no method '%s'",
                        device,
                        action_method_name,
                    )

        except Exception:
            _LOGGER.exception("Lox UDP: error handling command %s=%s", device, payload)
