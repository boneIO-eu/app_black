"""Lox UDP Client for BoneIO."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from boneio.core.messaging.basic import MessageBus

if TYPE_CHECKING:
    from boneio.core.config import ConfigHelper
    from boneio.core.manager import Manager
    from boneio.integration.homeassistant import HomeAssistantDiscoveryMessage

_LOGGER = logging.getLogger(__name__)


class LoxUDPProtocol(asyncio.DatagramProtocol):
    """Protocol for handling Lox UDP communication."""

    def __init__(self, callback: Callable[[str, str], Awaitable[None]]):
        self._callback = callback
        self._loop = asyncio.get_running_loop()

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        self.transport = transport

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        try:
            message = data.decode("utf-8").strip()
            _LOGGER.debug("Received Lox UDP message: %s from %s", message, addr)

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
    """Represent a Lox UDP client."""

    def __init__(
        self,
        config_helper: ConfigHelper,
        host: str,
        send_port: int,
        listen_port: int,
    ) -> None:
        """Set up client."""
        self._manager: Manager | None = None
        self._config_helper = config_helper
        self.host = host
        self.send_port = send_port
        self.listen_port = listen_port
        self._transport: asyncio.DatagramTransport | None = None
        self._listeners: dict[str, Callable[[str, str], Awaitable[None]]] = {}
        self._state = False

    def send_message(
        self,
        topic: str,
        payload: str | int | bytes | dict[str, Any] | HomeAssistantDiscoveryMessage | None,
        retain: bool = False,
        qos: int = 0,
    ) -> None:
        """Send a message via UDP.

        Converts MQTT-style messages to simple UDP datagrams.
        Topic format: boneio/{serial}/{type}/{device_id}
        Payload: dict {"state": "ON"} or string "ON"

        Sent UDP message format: {device_id}={state_value}
        """
        if payload is None:
            return

        # Skip HA Discovery messages (they have complex payloads not relevant for Lox)
        if isinstance(payload, dict) and "config" in str(topic):
            return

        # Extract device_id from topic: boneio/{serial}/{type}/{device_id}
        parts = str(topic).split("/")
        if len(parts) < 4:
            return

        device_id = parts[-1]
        entity_type = parts[-2] if len(parts) >= 3 else ""

        # Skip command topics (cmd/), availability, and discovery
        if "cmd" in parts or device_id in ("state", "config", "set"):
            return

        # Only send state for outputs, covers, and sensors
        if entity_type not in ("output", "cover", "sensor"):
            return

        # Extract state value from payload
        if isinstance(payload, dict):
            # {"state": "ON"} → "ON"
            state_value = payload.get("state", payload.get("value", ""))
            if not state_value and payload:
                # Fallback: use first value
                state_value = str(next(iter(payload.values()), ""))
        elif isinstance(payload, bytes):
            state_value = payload.decode("utf-8")
        else:
            state_value = str(payload)

        if not state_value:
            return

        try:
            udp_msg = f"{device_id}={state_value}".encode()

            if self._transport:
                self._transport.sendto(udp_msg, (self.host, self.send_port))
                _LOGGER.debug(
                    "Sent Lox UDP message: %s to %s:%s", udp_msg.decode("utf-8"), self.host, self.send_port
                )
            else:
                _LOGGER.debug("Lox UDP transport not ready yet, dropping: %s", udp_msg.decode("utf-8"))
        except Exception as e:
            _LOGGER.error("Error sending Lox UDP message for topic %s: %s", topic, e)

    @property
    def state(self) -> bool:
        """State of Lox Client."""
        return self._state

    async def start_client(self) -> None:
        """Start UDP server and client."""
        try:
            loop = asyncio.get_running_loop()
            transport, protocol = await loop.create_datagram_endpoint(
                lambda: LoxUDPProtocol(self._handle_incoming), local_addr=("0.0.0.0", self.listen_port)
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
        """Set manager."""
        self._manager = manager

    async def announce_offline(self) -> None:
        """Announce offline status."""
        if self._transport:
            self._transport.sendto(b"boneio=offline", (self.host, self.send_port))

    async def subscribe_and_listen(self, topic: str, callback: Callable[[str, str], Awaitable[None]]) -> None:
        """Register a listener."""
        self._listeners[topic] = callback

    async def unsubscribe_and_stop_listen(self, topic: str) -> None:
        """Unregister a listener."""
        if topic in self._listeners:
            del self._listeners[topic]

    async def _handle_incoming(self, device: str, payload: str) -> None:
        """Handle incoming Lox messages and route them to Manager or listeners."""
        _LOGGER.debug("Lox handle incoming: %s = %s", device, payload)

        if not self._manager:
            return

        try:
            cmd_prefix = self._config_helper.cmd_topic_prefix
            msg_type = None

            output = self._manager.outputs.get_output(device) or self._manager.outputs.get_output_group(device)
            if output:
                msg_type = "output"
            else:
                cover = self._manager.covers.get_cover(device)
                if cover:
                    msg_type = "cover"

            if not msg_type:
                _LOGGER.warning("Lox UDP device %s not found in outputs/covers", device)
                return

            full_topic = f"{cmd_prefix}{msg_type}/{device}/set"

            # Check explicit listeners
            for listen_topic, callback in self._listeners.items():
                if listen_topic == full_topic or (
                    listen_topic.endswith("/#") and full_topic.startswith(listen_topic[:-2])
                ):
                    await callback(full_topic, payload)

            await self._manager.receive_message(full_topic, payload)
        except Exception as e:
            _LOGGER.error("Error passing Lox message to manager: %s", e)
