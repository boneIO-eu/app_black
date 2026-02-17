"""Thermostat sub-manager for TemplateManager."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from boneio.const import CLIMATE
from boneio.core.utils.timeperiod import parse_time_to_seconds
from boneio.components.template.thermostat import BoneIOThermostat

if TYPE_CHECKING:
    from boneio.core.manager.manager import Manager

_LOGGER = logging.getLogger(__name__)


class ThermostatManager:
    """Manages thermostat template entities.

    Args:
        manager: Reference to the main Manager.
    """

    def __init__(self, manager: "Manager") -> None:
        self._manager = manager
        self._items: list[BoneIOThermostat] = []
        self._sensor_map: dict[str, list[BoneIOThermostat]] = {}

    @property
    def items(self) -> list[BoneIOThermostat]:
        """All configured thermostats."""
        return self._items

    @property
    def sensor_map(self) -> dict[str, list[BoneIOThermostat]]:
        """Sensor ID → thermostat mapping (used by TemplateManager for EventBus)."""
        return self._sensor_map

    def get(self, entity_id: str) -> BoneIOThermostat | None:
        """Get thermostat by ID.

        Args:
            entity_id: Thermostat entity ID.

        Returns:
            BoneIOThermostat or None if not found.
        """
        for t in self._items:
            if t.id == entity_id:
                return t
        return None

    # -- Configuration -------------------------------------------------------

    def configure(self, config: dict[str, Any]) -> None:
        """Configure a thermostat from YAML config.

        Args:
            config: Thermostat configuration dictionary.
        """
        entity_id = config.get("id", "")
        name = config.get("name", entity_id)
        output_id = config.get("output_id", "")
        mode = config.get("mode", "heat")
        target_temp = config.get("target_temperature", 21.0)
        area = config.get("area")

        # Parse sensor_ids (list) with fallback to single sensor_id
        sensor_ids: list[str] = config.get("sensor_ids", [])
        if not sensor_ids:
            single = config.get("sensor_id", "")
            if single:
                sensor_ids = [single]

        # Parse hysteresis — could be float or already parsed
        hysteresis = config.get("hysteresis", 0.5)
        if not isinstance(hysteresis, (int, float)):
            hysteresis = 0.5

        min_temp = config.get("min_temperature", 5.0)
        max_temp = config.get("max_temperature", 35.0)

        if not entity_id or not sensor_ids or not output_id:
            _LOGGER.error(
                "Thermostat config missing required fields (id, sensor_id(s), output_id): %s",
                config,
            )
            return

        # Resolve output
        output = self._manager.outputs.get_output(output_id)
        if output is None:
            output = self._manager.outputs.get_output_group(output_id)
        if output is None:
            _LOGGER.error("Thermostat %s: output '%s' not found", entity_id, output_id)
            return

        thermostat = BoneIOThermostat(
            id=entity_id,
            name=name,
            sensor_ids=sensor_ids,
            output=output,
            message_bus=self._manager.message_bus,
            event_bus=self._manager.event_bus,
            topic_prefix=self._manager.config_helper.topic_prefix,
            mode=mode,
            target_temperature=target_temp,
            hysteresis=hysteresis,
            min_temperature=min_temp,
            max_temperature=max_temp,
            area=area,
        )

        self._items.append(thermostat)

        # Register sensor → thermostat mapping for each sensor ID
        for sid in sensor_ids:
            if sid not in self._sensor_map:
                self._sensor_map[sid] = []
            self._sensor_map[sid].append(thermostat)

        # Publish HA discovery
        self._publish_discovery(thermostat)

        _LOGGER.info(
            "Configured thermostat '%s' (sensors=%s, output=%s)",
            entity_id, sensor_ids, output_id,
        )

    # -- Removal -------------------------------------------------------------

    async def remove(self, entity_id: str) -> None:
        """Remove a thermostat: stop MQTT, remove mappings, remove HA discovery.

        Args:
            entity_id: Thermostat entity ID to remove.
        """
        thermostat = self.get(entity_id)
        if not thermostat:
            return

        _LOGGER.info("Removing thermostat '%s'", entity_id)
        await thermostat.stop()

        # Remove sensor → thermostat mappings
        for sid in thermostat.sensor_ids:
            if sid in self._sensor_map:
                self._sensor_map[sid] = [
                    t for t in self._sensor_map[sid] if t.id != entity_id
                ]
                if not self._sensor_map[sid]:
                    del self._sensor_map[sid]

        self._remove_ha_discovery(entity_id)
        self._items = [t for t in self._items if t.id != entity_id]

    # -- HA Discovery --------------------------------------------------------

    def _publish_discovery(self, thermostat: BoneIOThermostat) -> None:
        """Publish HA autodiscovery for a thermostat.

        Args:
            thermostat: The thermostat instance.
        """
        from boneio.integration.homeassistant import ha_climate_availability_message

        payload = ha_climate_availability_message(
            id=thermostat.id,
            name=thermostat.name,
            config_helper=self._manager._config_helper,
            modes=["off", "heat"],
            min_temp=thermostat._min_temperature,
            max_temp=thermostat._max_temperature,
            area=thermostat.area,
        )
        self._manager.publish_ha_discovery(
            id=thermostat.id, ha_type=CLIMATE, payload=payload
        )

    def publish_all_discovery(self) -> None:
        """Resend HA autodiscovery for all thermostats."""
        for thermostat in self._items:
            self._publish_discovery(thermostat)

    def _remove_ha_discovery(self, entity_id: str) -> None:
        """Remove HA autodiscovery entries for a thermostat.

        Args:
            entity_id: Entity ID to remove.
        """
        matching_topics = self._manager._config_helper.get_autodiscovery_topics_for_id(entity_id)
        for ha_type, topic in matching_topics:
            _LOGGER.debug("Removing HA Discovery for %s: %s", entity_id, topic)
            self._manager.send_message(topic=topic, payload=None, retain=True)
            self._manager._config_helper.remove_autodiscovery_msg(ha_type, topic)
