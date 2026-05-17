"""MqttTopicDispatcher — fan-out layer over boneIO's MQTT bus.

The upstream bus (``boneio.core.messaging.mqtt.MQTTClient``) maps **one
callback per topic key** in ``_mqtt_energy_listeners``. Two practical
limitations follow:

1. Re-subscribing the same topic with a second callback **silently
   overwrites** the first one — so multiple ``MQTTGenericInput`` rows
   sharing a topic (e.g. extracting four fields from
   ``n64/88/temp1 = {"val":6.5,"fail":0,"ala":0,"alb":0}``) can't all
   receive messages.
2. The scanner subscribing ``n64/#`` while production has ``n64/99/in1``
   registered can displace the production callback in the dict, and
   ``handle_messages`` breaks on the first matching listener (insertion
   order), so messages may go to the wrong callback during the scan.

This module-owned dispatcher fixes both by keeping its own
``{topic → [(subscriber_id, callback)]}`` registry and exposing a SINGLE
dispatch function to the upstream bus per unique topic. Incoming messages
are fanned out to every registered subscriber whose subscription topic
matches the message topic (wildcards supported via ``aiomqtt.Topic.matches``).

The dispatcher is a process-wide singleton — ``get_dispatcher(bus)`` is
the only entry point. boneIO's bus lifetime equals the process lifetime,
so the cached instance is always valid.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from boneio.core.messaging.basic import MessageBus

_LOGGER = logging.getLogger(__name__)

Callback = Callable[[str, str], Awaitable[None]]


class MqttTopicDispatcher:
    """Fans out a single MQTT bus subscription to multiple internal subscribers."""

    def __init__(self, bus: "MessageBus") -> None:
        self._bus = bus
        # topic_pattern -> list of (subscriber_id, callback)
        self._subscribers: dict[str, list[tuple[str, Callback]]] = {}

    async def subscribe(self, topic: str, callback: Callback, subscriber_id: str) -> None:
        """Register ``callback`` for ``topic`` under ``subscriber_id``.

        First subscriber on a topic triggers an actual bus subscription;
        subsequent ones just join the in-memory list.

        ``subscriber_id`` must be unique per (topic, consumer) so the
        matching unsubscribe can remove the right entry.
        """
        existing = self._subscribers.get(topic)
        if existing is None:
            self._subscribers[topic] = [(subscriber_id, callback)]
            await self._bus.subscribe_and_listen(topic, self._dispatch)
            _LOGGER.debug(
                "MqttTopicDispatcher: subscribed to '%s' (first subscriber=%s)",
                topic, subscriber_id,
            )
        else:
            # Replace if subscriber_id already there (idempotent), otherwise append
            existing[:] = [(sid, cb) for sid, cb in existing if sid != subscriber_id]
            existing.append((subscriber_id, callback))
            _LOGGER.debug(
                "MqttTopicDispatcher: added subscriber '%s' to existing '%s' (total=%d)",
                subscriber_id, topic, len(existing),
            )

    async def unsubscribe(self, topic: str, subscriber_id: str) -> None:
        """Remove ``subscriber_id`` from ``topic``. If empty, drop bus subscription too."""
        existing = self._subscribers.get(topic)
        if not existing:
            return
        remaining = [(sid, cb) for sid, cb in existing if sid != subscriber_id]
        if remaining:
            self._subscribers[topic] = remaining
            _LOGGER.debug(
                "MqttTopicDispatcher: removed '%s' from '%s' (remaining=%d)",
                subscriber_id, topic, len(remaining),
            )
            return
        # Last subscriber gone — fully drop
        del self._subscribers[topic]
        try:
            await self._bus.unsubscribe_and_stop_listen(topic)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning(
                "MqttTopicDispatcher: bus unsubscribe failed for '%s': %s",
                topic, exc,
            )
        _LOGGER.debug("MqttTopicDispatcher: dropped last subscription on '%s'", topic)

    async def _dispatch(self, topic_str: str, payload: str) -> None:
        """Bus callback — fan out to every subscriber whose topic matches ``topic_str``.

        The bus only calls this once per message (it breaks on the first
        matching listener); our own fan-out then ensures every consumer
        whose subscription pattern matches the incoming topic receives it.
        """
        # Local import: aiomqtt is part of the existing MQTT dependency, so
        # this is always available wherever the bus is running.
        from aiomqtt import Topic

        incoming = Topic(topic_str)
        # Snapshot to allow callbacks to safely mutate _subscribers (e.g.
        # via unsubscribe) without mutating the iterator.
        snapshot = list(self._subscribers.items())
        for sub_topic, subscribers in snapshot:
            if not incoming.matches(sub_topic):
                continue
            for subscriber_id, cb in subscribers:
                try:
                    await cb(topic_str, payload)
                except Exception as exc:  # noqa: BLE001
                    _LOGGER.error(
                        "MqttTopicDispatcher: subscriber '%s' on '%s' raised: %s",
                        subscriber_id, sub_topic, exc, exc_info=True,
                    )

    # ------------------------------------------------------------------
    # Introspection (for diagnostics / future admin UI)
    # ------------------------------------------------------------------

    def subscriber_count(self, topic: str) -> int:
        return len(self._subscribers.get(topic, []))

    def topics(self) -> list[str]:
        return sorted(self._subscribers.keys())


# Process-wide singleton — boneIO's bus is created once at startup.
_dispatcher: MqttTopicDispatcher | None = None


def get_dispatcher(bus: "MessageBus") -> MqttTopicDispatcher:
    """Return the process-wide dispatcher, creating it on first call."""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = MqttTopicDispatcher(bus)
    return _dispatcher


def reset_dispatcher_for_tests() -> None:
    """Drop the singleton — only intended for unit tests."""
    global _dispatcher
    _dispatcher = None
