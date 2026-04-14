"""Timed output sub-manager for TemplateManager.

Handles configuration, MQTT subscriptions, HA discovery,
and lifecycle for TimedOutput template entities.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from boneio.components.template.timed_output import TimedOutput
from boneio.const import ON

if TYPE_CHECKING:
    from boneio.core.manager.manager import Manager

_LOGGER = logging.getLogger(__name__)

# device_type used in MQTT topics and HA discovery
_DEVICE_TYPE = "timed_output"


class TimedOutputManager:
    """Manages timed output template entities.

    Args:
        manager: Reference to the main Manager.
    """

    def __init__(self, manager: Manager) -> None:
        self._manager = manager
        self._items: list[TimedOutput] = []
        self._subscribed_topics: set[str] = set()

    @property
    def items(self) -> list[TimedOutput]:
        """All configured timed outputs."""
        return self._items

    def get(self, entity_id: str) -> TimedOutput | None:
        """Get timed output by ID.

        Args:
            entity_id: TimedOutput entity ID.

        Returns:
            TimedOutput or None if not found.
        """
        for item in self._items:
            if item.id == entity_id:
                return item
        return None

    # -- Configuration -------------------------------------------------------

    def configure(self, config: dict[str, Any]) -> None:
        """Configure a timed output from YAML config.

        Args:
            config: Timed output configuration dictionary.
        """
        entity_id = config.get("id", "")
        name = config.get("name", entity_id)
        output_id = config.get("output_id", "")
        area = config.get("area")

        if not entity_id:
            _LOGGER.error("Timed output config missing 'id': %s", config)
            return

        if not output_id:
            _LOGGER.error("Timed output '%s' missing 'output_id'", entity_id)
            return

        # Resolve the underlying output
        output = self._manager.outputs.get_output(output_id)
        if output is None:
            _LOGGER.error(
                "Timed output '%s': output_id '%s' not found", entity_id, output_id
            )
            return

        timed = TimedOutput(
            id=entity_id,
            name=name,
            output=output,
            message_bus=self._manager.message_bus,
            event_bus=self._manager.event_bus,
            state_manager=self._manager.state_manager,
            topic_prefix=self._manager.config_helper.topic_prefix,
            default_duration=int(config.get("default_duration", 60)),
            min_duration=int(config.get("min_duration", 1)),
            max_duration=int(config.get("max_duration", 3600)),
            step=int(config.get("step", 1)),
            unit=str(config.get("unit", "s")),
            icon=config.get("icon"),
            area=area,
        )

        self._items.append(timed)

        # Publish HA discovery
        self._publish_discovery(timed)

        _LOGGER.info(
            "Configured timed output '%s' (output=%s, duration=%ds, range=[%d-%d])",
            entity_id, output_id, timed.duration,
            timed.min_duration, timed.max_duration,
        )

    # -- MQTT subscription ---------------------------------------------------

    async def _subscribe_topic(self, topic: str, handler) -> None:
        """Subscribe to an MQTT topic, tracking it for cleanup.

        Args:
            topic: MQTT topic to subscribe to.
            handler: Async callback(topic, payload).
        """
        if topic in self._subscribed_topics:
            return
        await self._manager.message_bus.subscribe_and_listen(topic, handler)
        self._subscribed_topics.add(topic)

    async def _subscribe_timed_output(self, timed: TimedOutput) -> None:
        """Subscribe to MQTT command topics for a timed output.

        Args:
            timed: TimedOutput instance.
        """
        async def handle_command(
            _topic: str, payload: str, _t: TimedOutput = timed
        ) -> None:
            await _t.handle_command(payload)

        async def handle_duration(
            _topic: str, payload: str, _t: TimedOutput = timed
        ) -> None:
            await _t.handle_duration_command(payload)

        await self._subscribe_topic(timed._cmd_topic(), handle_command)
        await self._subscribe_topic(timed._duration_cmd_topic(), handle_duration)

    # -- Lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        """Start all timed outputs: subscribe to MQTT and publish state."""
        for timed in self._items:
            await self._subscribe_timed_output(timed)
            await timed.start()

    async def stop(self) -> None:
        """Stop all timed outputs and unsubscribe from MQTT."""
        for topic in list(self._subscribed_topics):
            try:
                await self._manager.message_bus.unsubscribe_and_stop_listen(topic)
            except Exception:
                pass
        self._subscribed_topics.clear()

        for timed in self._items:
            await timed.stop()

    # -- Removal (for hot-reload) --------------------------------------------

    async def remove(self, entity_id: str) -> None:
        """Remove a timed output: stop, unsubscribe MQTT, remove HA discovery.

        Args:
            entity_id: Entity ID to remove.
        """
        timed = self.get(entity_id)
        if not timed:
            return

        _LOGGER.info("Removing timed output '%s'", entity_id)
        await timed.stop()

        # Unsubscribe topics for this entity
        for topic in (timed._cmd_topic(), timed._duration_cmd_topic()):
            if topic in self._subscribed_topics:
                try:
                    await self._manager.message_bus.unsubscribe_and_stop_listen(topic)
                except Exception:
                    pass
                self._subscribed_topics.discard(topic)

        self._remove_ha_discovery(entity_id)
        self._items = [t for t in self._items if t.id != entity_id]

    # -- HA Discovery --------------------------------------------------------

    def _publish_discovery(self, timed: TimedOutput) -> None:
        """Publish HA autodiscovery for a timed output (switch + number).

        Args:
            timed: The TimedOutput instance.
        """
        from boneio.integration.homeassistant import (
            ha_timed_output_number_message,
            ha_timed_output_switch_message,
        )

        cfg = self._manager._config_helper

        # 1. Switch/Valve entity (main ON/OFF control)
        switch_payload = ha_timed_output_switch_message(
            id=timed.id,
            name=timed.name,
            output_type=timed.output_type,
            config_helper=cfg,
            icon=timed.icon,
            area=timed.area,
        )

        # Determine HA entity type based on output type
        ha_type = "switch"
        if timed.output_type == "valve":
            ha_type = "valve"
        elif timed.output_type == "light":
            ha_type = "light"

        self._manager.publish_ha_discovery(
            id=f"timed_{timed.id}",
            ha_type=ha_type,
            payload=switch_payload,
        )

        # 2. Number entity (duration slider)
        number_payload = ha_timed_output_number_message(
            id=timed.id,
            name=f"{timed.name} Duration",
            min_val=timed.min_duration,
            max_val=timed.max_duration,
            step=timed.step,
            unit=timed.unit,
            config_helper=cfg,
            area=timed.area,
        )
        self._manager.publish_ha_discovery(
            id=f"timed_{timed.id}_duration",
            ha_type="number",
            payload=number_payload,
        )

    def publish_all_discovery(self) -> None:
        """Resend HA autodiscovery for all timed outputs."""
        for timed in self._items:
            self._publish_discovery(timed)

    def _remove_ha_discovery(self, entity_id: str) -> None:
        """Remove HA autodiscovery entries for a timed output.

        Args:
            entity_id: Entity ID to remove.
        """
        for suffix in (f"timed_{entity_id}", f"timed_{entity_id}_duration"):
            matching = self._manager._config_helper.get_autodiscovery_topics_for_id(
                suffix
            )
            for ha_type, topic in matching:
                _LOGGER.debug("Removing HA Discovery for %s: %s", suffix, topic)
                self._manager.send_message(topic=topic, payload=None, retain=True)
                self._manager._config_helper.remove_autodiscovery_msg(ha_type, topic)
