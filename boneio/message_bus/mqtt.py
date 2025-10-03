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
from typing import TYPE_CHECKING, Any

import paho.mqtt.client as mqtt
from aiomqtt import Client as AsyncioClient
from aiomqtt import Message, MqttError, Will
from paho.mqtt.properties import Properties
from paho.mqtt.subscribeoptions import SubscribeOptions

from boneio.const import OFFLINE, PAHO, STATE
from boneio.helper.config import ConfigHelper
from boneio.helper.events import GracefulExit
from boneio.helper.queue import UniqueQueue

if TYPE_CHECKING:
    from boneio.manager import Manager
from boneio.message_bus import MessageBus

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
        self._manager: Manager = None
        self.host = host
        self.port = port
        self._config_helper = config_helper
        client_options["client_id"] = mqtt.base62(uuid.uuid4().int, padding=22)
        client_options["logger"] = logging.getLogger(PAHO)
        client_options["clean_session"] = True
        self.client_options = client_options
        self.asyncio_client: AsyncioClient = None
        self.create_client()
        self.reconnect_interval = 1
        self._connection_established = False
        self.publish_queue: UniqueQueue = UniqueQueue()
        self._mqtt_energy_listeners: dict[str, Callable[[str, str], Awaitable[None]]] = {}
        self._discovery_topics = (
            [
                f"{self._config_helper.ha_discovery_prefix}/{ha_type}/{self._config_helper.topic_prefix}/#"
                for ha_type in self._config_helper.ha_types
            ]
            if self._config_helper.ha_discovery
            else []
        )
        self._topics = [
            self._config_helper.subscribe_topic,
            "homeassistant/status",
        ]
        self._running = True
        self._cancel_future: asyncio.Future | None = None

    def create_client(self) -> None:
        """Create the asyncio client."""
        _LOGGER.debug("Creating client %s:%s", self.host, self.port)
        self.asyncio_client = AsyncioClient(
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
        payload: str | None = None,
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
            topic=args, **params, timeout=timeout
        )

    async def subscribe_and_listen(self, topic: str, callback: Callable[[str, str], Awaitable[None]]) -> None:
        self._mqtt_energy_listeners[topic] = callback

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
        params: dict = {"timeout": timeout}
        if properties:
            params["properties"] = properties

        await self.asyncio_client.unsubscribe(topic=topics, **params)

    def send_message(
        self,
        topic: str,
        payload: str | int | dict | None,
        retain: bool = False,
    ) -> None:
        """Send a message from the manager options."""
        to_publish = (
            topic,
            json.dumps(payload) if isinstance(payload, dict) else payload,
            retain,
        )
        self.publish_queue.put_nowait(to_publish)

    async def _handle_publish(self) -> None:
        """Publish messages as they are put on the queue."""
        while True:
            to_publish: tuple = await self.publish_queue.get()
            await self.publish(*to_publish)
            self.publish_queue.task_done()

    async def announce_offline(self) -> None:
        """Announce that the device is offline."""
        await self.publish(
            topic=f"{self._config_helper.topic_prefix}/{STATE}",
            payload=OFFLINE,
            retain=True,
        )

    async def start_client(self) -> None:
        """Keep the event loop alive and process any periodic tasks."""
        try:
            while True:
                try:
                    await self._subscribe_manager(self._manager)
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
                    await asyncio.sleep(self.reconnect_interval)
                    self.create_client()  # reset connect/reconnect futures
        except (asyncio.CancelledError, GracefulExit):
            _LOGGER.info("MQTT client shutting down...")
            await self.asyncio_client.disconnect(timeout=1.0)
            # raise

    def set_manager(self, manager: Manager) -> None:
        """Set manager."""
        self._manager = manager

    async def _subscribe_manager(self, manager: Manager) -> None:
        """Connect and subscribe to manager topics + host stats."""
        async with AsyncExitStack() as stack:
            await stack.enter_async_context(self.asyncio_client)
            self.publish_queue.set_connected(True)
            # Create a new future for this run
            self._cancel_future = asyncio.Future()
            
            async def wait_for_cancel():
                await self._cancel_future
                # When future completes, raise CancelledError to stop other tasks
                raise asyncio.CancelledError("Stop requested")
            
            tasks: set[asyncio.Task] = set()

            publish_task = asyncio.create_task(self._handle_publish())
            tasks.add(publish_task)

            # Messages that doesn't match a filter will get logged and handled here.
            messages = await stack.enter_async_context(
                self.asyncio_client.messages()
            )

            messages_task = asyncio.create_task(
                self.handle_messages(messages, manager.receive_message)
            )
            if not self._connection_established:
                self._connection_established = True
                reconnect_task = asyncio.create_task(
                    manager.reconnect_callback()
                )
                tasks.add(reconnect_task)
            tasks.add(messages_task)

            # Add cancel_future to tasks
            cancel_task = asyncio.create_task(wait_for_cancel())
            tasks.add(cancel_task)

            topics = self._topics + list(self._mqtt_energy_listeners.keys()) + self._discovery_topics
            await self.subscribe(topics=topics)

            # Wait for everything to complete (or fail due to, e.g., network errors).
            await asyncio.gather(*tasks)

    def state(self) -> bool:
        """State of MQTT Client."""
        return self._connection_established

    async def handle_messages(
        self, messages: Message, callback: Callable[[str, str], Awaitable[None]]
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
            if message.topic.matches(f"{self._config_helper.topic_prefix}/energy/#"):
                for topic, listener_callback in self._mqtt_energy_listeners.items():
                    if message.topic.matches(topic):
                        callback_start = False
                        await listener_callback(str(message.topic), payload)
                        break
            if callback_start:
                _LOGGER.debug(
                    "Received message topic: %s, payload: %s",
                    message.topic,
                    payload,
                )
                await callback(str(message.topic), payload)
