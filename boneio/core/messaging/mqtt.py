"""
Provide an MQTT client for providing BoneIO MQTT broker.
Code based on cgarwood/python-openzwave-mqtt.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack
from typing import TYPE_CHECKING, Any, override

if TYPE_CHECKING:
    from boneio.integration.homeassistant import HomeAssistantDiscoveryMessage

from aiomqtt import Client as AsyncioClient
from aiomqtt import MqttError, Will
from paho.mqtt.properties import Properties
from paho.mqtt.subscribeoptions import SubscribeOptions

from boneio.const import OFFLINE, PAHO, STATE
from boneio.core.config import ConfigHelper
from boneio.core.events.bus import GracefulExit
from boneio.core.messaging.queue import UniqueQueue
from boneio.models.mqtt import MQTTMessageSend

if TYPE_CHECKING:
    from boneio.core.manager import Manager
from boneio.core.messaging.basic import MessageBus

_LOGGER = logging.getLogger(__name__)

class MQTTClient(MessageBus):
    """Represent an MQTT client."""

    def __init__(
        self,
        host: str,
        config_helper: ConfigHelper,
        port: int = 1883,
        **client_options: Any,
    ) -> None:
        """Set up client."""
        self._manager: Manager | None = None
        self.host = host
        self.port = port
        self._config_helper = config_helper
        client_options["identifier"] = str(uuid.uuid4())
        client_options["logger"] = logging.getLogger(PAHO)
        client_options["clean_session"] = True
        self.client_options = client_options
        self.asyncio_client = self.create_client()
        self.reconnect_interval = 1
        self._connection_established = False
        self.publish_queue: UniqueQueue = UniqueQueue()
        self._mqtt_energy_listeners: dict[str, Callable[[str, str], Awaitable[None]]] = {}
        self._discovery_topics = (
            [
                f"{self._config_helper.ha_discovery_prefix}/{ha_type}/{self._config_helper.serial_number}/#"
                for ha_type in self._config_helper.ha_types
            ]
            if self._config_helper.ha_discovery
            else []
        )
        self._topics = [
            self._config_helper.subscribe_topic,
            "homeassistant/status",
            # Subscribe to managed_by messages for this device
            f"{self._config_helper.topic_prefix}/discovery/managed_by/#",
        ]
        # Add BoneIO autodiscovery subscription if enabled
        if self._config_helper.receive_boneio_autodiscovery:
            self._topics.append("boneio/+/discovery/#")
        self._running = True
        # The running session, so new credentials can end it on purpose.
        self._session_task: asyncio.Task | None = None
        self._reloading = False

    def create_client(self) -> AsyncioClient:
        """Create the asyncio client."""
        _LOGGER.debug("Creating client %s:%s", self.host, self.port)
        return AsyncioClient(
            self.host,
            self.port,
            will=Will(
                topic=f"{self._config_helper.topic_prefix}/{STATE}",
                payload=OFFLINE,
                qos=0,
                retain=False,
            ),
            **self.client_options,
        )

    async def publish(  # pylint:disable=too-many-arguments
        self,
        topic: str,
        payload: str | bytes | None = None,
        retain: bool = False,
        qos: int = 0,
        properties: Properties | None = None,
        timeout: float = 10,
    ) -> None:
        """Publish to topic.

        Can raise asyncio_mqtt.MqttError.
        """
        params: dict = {"qos": qos, "retain": retain, "timeout": timeout}
        if payload:
            params["payload"] = payload
        if properties:
            params["properties"] = properties

        _LOGGER.debug("Sending message topic: %s, payload: %s", topic, payload)
        await self.asyncio_client.publish(topic, **params)

    async def subscribe(  # pylint:disable=too-many-arguments
        self,
        topics: list[str],
        qos: int = 0,
        options: SubscribeOptions | None = None,
        properties: Properties | None = None,
        timeout: float = 10.0,
    ) -> None:
        """Subscribe to topic.

        Can raise asyncio_mqtt.MqttError.
        """
        args = []
        for topic in topics:
            args.append((topic, qos))
        params: dict = {"qos": qos}
        if options:
            params["options"] = options
        if properties:
            params["properties"] = properties

        # e.g. subscribe([("my/topic", SubscribeOptions(qos=0), ("another/topic", SubscribeOptions(qos=2)])
        _LOGGER.debug("Subscribing to %s", args)
        await self.asyncio_client.subscribe(
            args, timeout=timeout, **params
        )

    @override
    async def subscribe_and_listen(self, topic: str, callback: Callable[[str, str], Awaitable[None]]) -> None:
        self._mqtt_energy_listeners[topic] = callback
        # Subscribe immediately if already connected
        if self._connection_established:
            await self.subscribe(topics=[topic])

    @override
    async def unsubscribe_and_stop_listen(self, topic: str) -> None:
        await self.unsubscribe([topic])
        del self._mqtt_energy_listeners[topic]

    async def unsubscribe(
        self,
        topics: list[str],
        properties: Properties | None = None,
        timeout: float = 10.0,
    ) -> None:
        """Unsubscribe from topic.

        Can raise asyncio_mqtt.MqttError.
        """

        await self.asyncio_client.unsubscribe(topics, timeout=timeout, properties=properties)

    @override
    def send_message(
        self,
        topic: str,
        payload: str | int | bytes | dict[str, Any] | None,
        retain: bool = False,
        qos: int = 0,
    ) -> None:
        """Send a message from the manager options.
        
        Args:
            topic: MQTT topic
            payload: Message payload (will be JSON-encoded if dict, None becomes empty bytes)
            retain: Whether to retain the message
            qos: Quality of Service level (0, 1, or 2)
        """
        # Handle payload encoding:
        # - dict -> JSON string
        # - None -> empty bytes (for HA Discovery removal)
        # - int -> string
        # - str/bytes -> pass through
        encoded_payload: str | bytes
        if isinstance(payload, dict):
            encoded_payload = json.dumps(payload)
        elif payload is None:
            encoded_payload = b""  # Empty payload for HA Discovery removal
        elif isinstance(payload, int):
            encoded_payload = str(payload)
        else:
            encoded_payload = payload
        
        message = MQTTMessageSend(
            topic=topic,
            payload=encoded_payload,
            retain=retain,
            qos=qos,
        )
        self.publish_queue.put_nowait(message)

    async def _handle_publish(self) -> None:
        """Publish messages as they are put on the queue."""
        while True:
            message: MQTTMessageSend = await self.publish_queue.get()
            try:
                await self.publish(
                    topic=message.topic,
                    payload=message.payload,
                    retain=message.retain,
                    qos=message.qos,
                )
            except Exception as exc:
                _LOGGER.error(
                    "Failed to publish MQTT message to %s: %s",
                    message.topic, exc,
                )
            self.publish_queue.task_done()

    @override
    async def announce_offline(self) -> None:
        """Announce that the device is offline."""
        await self.publish(
            topic=f"{self._config_helper.topic_prefix}/{STATE}",
            payload=OFFLINE,
            retain=True,
        )

    async def reload_credentials(
        self,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
    ) -> bool:
        """Connect again with new broker credentials, without a restart.

        They are only read in :meth:`create_client`, and the loop in
        :meth:`start_client` only builds a new client after an ``MqttError``.
        So changing them took a restart of the service — which is what made
        changing the broker password look broken: the password in the broker
        was the new one, the password this client kept presenting was not.

        Args:
            host: Broker host.
            port: Broker port.
            username: The account to connect with, or None for an open broker.
            password: Its password.

        Returns:
            True when something changed and a reconnect was started.
        """
        if (
            host == self.host
            and port == self.port
            and username == self.client_options.get("username")
            and password == self.client_options.get("password")
        ):
            _LOGGER.debug("MQTT credentials unchanged; keeping the connection")
            return False

        self.host = host
        self.port = port
        self.client_options["username"] = username
        self.client_options["password"] = password
        # A fresh identifier: a broker drops the older of two connections
        # sharing one, and the session being replaced may still be on its
        # way down when the next one arrives.
        self.client_options["identifier"] = str(uuid.uuid4())
        self.reconnect_interval = 1

        session = self._session_task
        if session is None or session.done():
            # Between attempts: the loop builds its next client from the
            # options above without being told anything.
            _LOGGER.info("New MQTT credentials stored; no session to interrupt")
            return True

        self._reloading = True
        session.cancel()
        _LOGGER.info(
            "Reconnecting to MQTT at %s:%s as %s", host, port, username
        )
        return True

    @override
    async def start_client(self) -> None:
        """Keep the event loop alive and process any periodic tasks."""
        try:
            while True:
                try:
                    if self._manager is not None:
                        self._session_task = asyncio.create_task(
                            self._subscribe_manager(self._manager)
                        )
                        await self._session_task
                except asyncio.CancelledError:
                    # Ours, from reload_credentials: the session was ended so
                    # the next one can use the new credentials. A cancel from
                    # anywhere else leaves the flag down and means shutdown.
                    if not self._reloading:
                        raise
                    self._reloading = False
                    self._connection_established = False
                    self.publish_queue.set_connected(False)
                    if self._manager is not None:
                        self._manager.display.notify_mqtt_state_changed()
                    self.asyncio_client = self.create_client()
                except MqttError as err:
                    self.reconnect_interval = min(
                        self.reconnect_interval * 2, 60
                    )
                    _LOGGER.error(
                        "MQTT error: %s. Reconnecting in %s seconds",
                        err,
                        self.reconnect_interval,
                    )
                    self._connection_established = False
                    self.publish_queue.set_connected(False)
                    # Notify manager about MQTT disconnect for OLED update
                    if self._manager is not None:
                        self._manager.display.notify_mqtt_state_changed()
                    await asyncio.sleep(self.reconnect_interval)
                    self.asyncio_client = self.create_client()  # reset connect/reconnect futures
                finally:
                    # Nothing to interrupt until the next one is running, so a
                    # reload arriving now only stores the new options.
                    self._session_task = None
        except (asyncio.CancelledError, GracefulExit):
            _LOGGER.info("MQTT client shutting down...")
            # Don't call __aexit__ here - AsyncExitStack handles cleanup
            # The client context is managed by async with in _subscribe_manager
            pass

    @override
    def set_manager(self, manager: Manager) -> None:
        """Set manager."""
        self._manager = manager

    async def _subscribe_manager(self, manager: Manager) -> None:
        """Connect and subscribe to manager topics + host stats."""
        tasks: set[asyncio.Task] = set()
        try:
            async with AsyncExitStack() as stack:
                _ = await stack.enter_async_context(self.asyncio_client)
                self.publish_queue.set_connected(True)

                publish_task = asyncio.create_task(self._handle_publish())
                tasks.add(publish_task)

                # Messages that doesn't match a filter will get logged and handled here.
                messages_task = asyncio.create_task(
                    self.handle_messages(self.asyncio_client.messages, manager.receive_message)
                )
                if not self._connection_established:
                    self._connection_established = True
                    reconnect_task = asyncio.create_task(
                        manager.reconnect_callback()
                    )
                    tasks.add(reconnect_task)
                tasks.add(messages_task)

                topics = self._topics + list(self._mqtt_energy_listeners.keys()) + self._discovery_topics
                await self.subscribe(topics=topics)

                # Wait for everything to complete (or fail due to, e.g., network errors).
                await asyncio.gather(*tasks)
        finally:
            # asyncio.gather() does NOT cancel sibling tasks when one of them raises
            # (e.g. messages_task raising MqttError on disconnect), so without this,
            # publish_task/reconnect_task kept running as orphans after every
            # reconnect. An orphaned publish_task would then race the next
            # cycle's publish_task for the same publish_queue, calling publish()
            # against a client that isn't connected yet ("client is not currently
            # connected") even once the real connection was healthy again.
            self.publish_queue.set_connected(False)
            for task in tasks:
                if not task.done():
                    task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

    @property
    @override
    def state(self) -> bool:
        """State of MQTT Client."""
        return self._connection_established

    async def handle_messages(
        self, messages, callback: Callable[[str, str], Awaitable[None]]
    ):
        """Handle messages with callback or remove obsolete HA discovery messages."""
        async for message in messages:
            payload = message.payload.decode()
            callback_start = True
            for discovery_topic in self._discovery_topics:
                if message.topic.matches(discovery_topic):
                    callback_start = False
                    topic = str(message.topic)
                    if (
                        message.payload
                        and not self._config_helper.is_topic_in_autodiscovery(
                            topic
                        )
                    ):
                        _LOGGER.info(
                            "Removing unused discovery entity %s", topic
                        )
                        self.send_message(
                            topic=topic, payload=None, retain=True
                        )
                    break
            for topic, listener_callback in self._mqtt_energy_listeners.items():
                if message.topic.matches(topic):
                    callback_start = False
                    try:
                        await listener_callback(str(message.topic), payload)
                    except Exception as exc:
                        _LOGGER.error(
                            "Error in MQTT listener callback for topic %s: %s",
                            message.topic, exc, exc_info=True,
                        )
                    break
            if callback_start:
                _LOGGER.debug(
                    "Received message topic: %s, payload: %s",
                    message.topic,
                    payload,
                )
                await callback(str(message.topic), payload)
