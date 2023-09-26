"""
Provide an MQTT client for providing BoneIO MQTT broker.
Code based on cgarwood/python-openzwave-mqtt.
"""
from __future__ import annotations
import asyncio
import json
import logging
import uuid
from contextlib import AsyncExitStack
from typing import Any, Callable, Optional, Set, Union, Awaitable

import paho.mqtt.client as mqtt
from aiomqtt import Client as AsyncioClient, MqttError, Will
from paho.mqtt.properties import Properties
from paho.mqtt.subscribeoptions import SubscribeOptions

from boneio.const import OFFLINE, PAHO, STATE
from boneio.helper import UniqueQueue
from boneio.helper.config import ConfigHelper
from boneio.helper.events import GracefulExit
from boneio.manager import Manager
from boneio.helper.exceptions import RestartRequestException

_LOGGER = logging.getLogger(__name__)


class MQTTClient:
    """Represent an MQTT client."""

    def __init__(
        self,
        host: str,
        config_helper: ConfigHelper,
        port: int = 1883,
        **client_options: Any,
    ) -> None:
        """Set up client."""
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
        self._discovery_topics = [f"{self._config_helper.ha_discovery_prefix}/{ha_type}/{self._config_helper.topic_prefix}/#" for ha_type in self._config_helper.ha_types] if self._config_helper.ha_discovery else []
        self._topics = [self._config_helper.subscribe_topic, "homeassistant/status"]

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
        payload: Optional[str] = None,
        retain: bool = False,
        qos: int = 0,
        properties: Optional[Properties] = None,
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
        options: Optional[SubscribeOptions] = None,
        properties: Optional[Properties] = None,
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
        await self.asyncio_client.subscribe(topic=args, **params, timeout=timeout)

    async def unsubscribe(
        self,
        topics: list[str],
        properties: Optional[Properties] = None,
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
        self, topic: str, payload: Union[str, int, dict, None], retain: bool = False
    ) -> None:
        """Send a message from the manager options."""
        to_publish = (
            topic,
            json.dumps(payload) if type(payload) == dict else payload,
            retain,
        )
        self.publish_queue.put_nowait(to_publish)

    async def _handle_publish(self) -> None:
        """Publish messages as they are put on the queue."""
        while True:
            to_publish: tuple = await self.publish_queue.get()
            await self.publish(*to_publish)
            self.publish_queue.task_done()

    async def start_client(self, manager: Manager) -> None:
        """Start the client with the manager."""
        # Reconnect automatically until the client is stopped.
        try:
            while True:
                try:
                    await self._subscribe_manager(manager)
                except MqttError as err:
                    self.reconnect_interval = min(self.reconnect_interval * 2, 900)
                    _LOGGER.error(
                        "MQTT error: %s. Reconnecting in %s seconds",
                        err,
                        self.reconnect_interval,
                    )
                    self._connection_established = False
                    await asyncio.sleep(self.reconnect_interval)
                    self.create_client()  # reset connect/reconnect futures
        except (asyncio.CancelledError, GracefulExit):
            _LOGGER.info("MQTT client task canceled.")
            pass

    async def stop_client(self) -> None:
        await self.unsubscribe(
            topics=self._topics
        )
        raise RestartRequestException("Restart requested.")
    
    def state(self) -> bool:
        """State of MQTT Client."""
        return self._connection_established
    
    async def _subscribe_manager(self, manager: Manager) -> None:
        """Connect and subscribe to manager topics + host stats."""
        async with AsyncExitStack() as stack:
            tasks: Set[asyncio.Task] = set()

            # Connect to the MQTT broker.
            await stack.enter_async_context(self.asyncio_client)
            # Reset the reconnect interval after successful connection.
            self.reconnect_interval = 1

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
                reconnect_task = asyncio.create_task(manager.reconnect_callback())
                tasks.add(reconnect_task)
            tasks.add(messages_task)

            await self.subscribe(
                topics=self._topics
            )
            await self.subscribe(
                topics=self._discovery_topics
            )

            # Wait for everything to complete (or fail due to, e.g., network errors).
            await asyncio.gather(*tasks)

    async def handle_messages(self, messages: Any, callback: Callable[[str, str], Awaitable[None]]):
        """Handle messages with callback or remove obsolete HA discovery messages."""
        async for message in messages:
            payload = message.payload.decode()
            callback_start = True
            for discovery_topic in self._discovery_topics:
                if message.topic.matches(discovery_topic):
                    callback_start = False
                    topic = str(message.topic)
                    if message.payload and not self._config_helper.is_topic_in_autodiscovery(topic):
                        _LOGGER.info("Removing unused discovery entity %s", topic)
                        self.send_message(topic=topic, payload=None, retain=True)
                    break
            if callback_start:
                _LOGGER.debug("Received message topic: %s, payload: %s", message.topic, payload)
                await callback(str(message.topic), payload)
