"""Whether the Sun shines on each cover's window, for Home Assistant.

A cover with ``facade_azimuth`` set gets a binary sensor, ``sun_on_<id>``,
with the angle of incidence as an attribute: what an automation against
heat needs, or one that opens the east side first.

One loop serves every cover. It reads the cover list on each tick, so a
cover reload needs no loop started or stopped - only the discovery
entities follow, through :meth:`FacadeSun.publish_discovery`.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from boneio.const import SENSOR
from boneio.core.utils.async_updater import AsyncUpdater
from boneio.core.utils.sun import facade_incidence, sun_on_facade
from boneio.core.utils.timeperiod import TimePeriod

if TYPE_CHECKING:
    from boneio.core.manager import Manager

_LOGGER = logging.getLogger(__name__)

BINARY_SENSOR = "binary_sensor"


def facade_sensor_id(cover_id: str) -> str:
    return f"sun_on_{cover_id}"


class FacadeSun(AsyncUpdater):
    """Publishes "sun on the window" for every cover that knows its facade."""

    def __init__(self, manager: Manager) -> None:
        self.id = "sun_on_facades"
        self._discovered: set[str] = set()
        super().__init__(manager=manager, update_interval=TimePeriod(seconds=60))

    def _facades(self) -> list:
        return [c for c in self.manager.covers.get_all_covers().values()
                if getattr(c, "facade_azimuth", None) is not None]

    def update(self, timestamp: float) -> None:
        provider = self.manager.sun
        now = datetime.now().astimezone()
        position = provider.position(now) if provider.ready(now) else None
        if position is None:
            return None
        elevation, azimuth = position
        for cover in self._facades():
            facade = cover.facade_azimuth
            on = sun_on_facade(elevation, azimuth, facade, getattr(cover, "facade_min_elevation", 0) or 0)
            self.manager.send_message(
                topic=f"{self.manager._topic_prefix}/{SENSOR}/{facade_sensor_id(cover.id)}",
                payload={
                    "state": "on" if on else "off",
                    "incidence": round(facade_incidence(elevation, azimuth, facade), 1),
                    "facade_azimuth": facade,
                },
            )
        return None

    def publish_discovery(self) -> None:
        """Bring Home Assistant's entities in line with the covers: add, keep, remove."""
        from boneio.integration.homeassistant import ha_sun_binary_sensor_message

        helper = self.manager._config_helper
        wanted = {}
        if self.manager.sun.configured:
            wanted = {facade_sensor_id(c.id): c for c in self._facades() if getattr(c, "show_in_ha", True)}
        for sensor_id, cover in wanted.items():
            payload = ha_sun_binary_sensor_message(
                id=sensor_id,
                name=f"{cover.name} sun",
                config_helper=helper,
                icon="mdi:sun-angle-outline",
                area=getattr(cover, "area", None),
            )
            payload["json_attributes_topic"] = payload["state_topic"]
            self.manager.publish_ha_discovery(id=sensor_id, ha_type=BINARY_SENSOR, payload=payload)
        for gone in self._discovered - set(wanted):
            for ha_type, topic in helper.get_autodiscovery_topics_for_id(gone):
                if ha_type == BINARY_SENSOR:
                    self.manager.send_message(topic=topic, payload=None, retain=True)
                    helper.remove_autodiscovery_msg(ha_type, topic)
        self._discovered = set(wanted)
        if wanted:
            self.request_update()
