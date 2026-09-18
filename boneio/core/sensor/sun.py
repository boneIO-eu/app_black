"""Sun sensors for boneIO.

Where the Sun is, published as entities: Home Assistant gets something to
automate on and graph, and the panel gets something to show. Nothing here
computes anything — every value comes from
:class:`boneio.core.manager.sun.SunProvider`, which caches a day of anchors and
a minute of elevation, so six sensors on a 60-second loop cost six dictionary
lookups a minute.

They exist only when the ``location:`` section does. A sun sensor on a device
that does not know where it is would report nothing forever, and an entity that
is permanently unavailable is worse than an absent one.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from boneio.core.sensor import BaseSensor
from boneio.core.utils import TimePeriod

if TYPE_CHECKING:
    from boneio.core.manager import Manager
    from boneio.core.messaging import MessageBus

_LOGGER = logging.getLogger(__name__)

#: The Sun moves at most 0.25° per minute, so a minute is already finer than
#: anything a relay cares about. Faster would only add MQTT traffic.
DEFAULT_UPDATE_INTERVAL = TimePeriod(seconds=60)


def _iso(moment: datetime) -> str:
    """ISO-8601 to the second.

    The engine returns microseconds; nobody reads them, and they make every
    MQTT payload and Home Assistant history entry noisier than it needs to be.
    """
    return moment.replace(microsecond=0).isoformat()


class _SunSensor(BaseSensor):
    """Shared plumbing: read from the provider, publish, or stay quiet.

    Subclasses implement :meth:`read`. Returning None means "not now" — the
    clock has not been set, or the Sun does not reach that angle today — and
    nothing is published, so the entity keeps its last value rather than
    flapping to null.
    """

    def __init__(
        self,
        manager: Manager,
        message_bus: MessageBus,
        topic_prefix: str,
        sensor_id: str,
        name: str,
        update_interval: TimePeriod | None = None,
        unit_of_measurement: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(
            id=sensor_id,
            name=name,
            manager=manager,
            message_bus=message_bus,
            topic_prefix=topic_prefix,
            update_interval=update_interval or DEFAULT_UPDATE_INTERVAL,
            unit_of_measurement=unit_of_measurement,
            **kwargs,
        )

    @property
    def _provider(self):
        """The manager's SunProvider."""
        return self.manager.sun

    def read(self, now: datetime) -> Any:
        """Return the value to publish, or None to publish nothing."""
        raise NotImplementedError

    def extra_attributes(self, now: datetime) -> dict[str, Any]:
        """Attributes to publish alongside the state."""
        return {}

    async def async_update(self, timestamp: float) -> None:
        """Read the Sun's position and publish it.

        Args:
            timestamp: Current timestamp, supplied by AsyncUpdater.
        """
        now = datetime.now().astimezone()
        if not self._provider.ready(now):
            # The provider logs the reason once; repeating it every minute for
            # six sensors would bury everything else in the journal.
            _LOGGER.debug("Sun sensor '%s': provider not ready, skipping", self.id)
            return

        try:
            value = self.read(now)
        except Exception as err:  # noqa: BLE001 - one bad sensor must not stop the rest
            _LOGGER.error("Error reading sun sensor '%s': %s", self.id, err)
            return

        if value is None:
            return

        self._state = value
        self._attributes = self.extra_attributes(now)
        self._publish_state(timestamp=timestamp)


class SunElevationSensor(_SunSensor):
    """Geometric elevation of the Sun's centre, in degrees."""

    def __init__(self, manager, message_bus, topic_prefix, **kwargs) -> None:
        super().__init__(
            manager=manager,
            message_bus=message_bus,
            topic_prefix=topic_prefix,
            sensor_id="sun_elevation",
            name="Sun Elevation",
            unit_of_measurement="°",
            **kwargs,
        )

    @property
    def state_class(self) -> str:
        return "measurement"

    def read(self, now: datetime) -> float | None:
        elevation = self._provider.elevation(now)
        return None if elevation is None else round(elevation, 2)


class SunAzimuthSensor(_SunSensor):
    """Bearing of the Sun, degrees clockwise from true north."""

    def __init__(self, manager, message_bus, topic_prefix, **kwargs) -> None:
        super().__init__(
            manager=manager,
            message_bus=message_bus,
            topic_prefix=topic_prefix,
            sensor_id="sun_azimuth",
            name="Sun Azimuth",
            unit_of_measurement="°",
            **kwargs,
        )

    @property
    def state_class(self) -> str:
        return "measurement"

    def read(self, now: datetime) -> float | None:
        position = self._provider.position(now)
        return None if position is None else round(position[1], 2)


class SunPhaseSensor(_SunSensor):
    """Which part of the day it is, with the day's turning points attached.

    The attributes are here rather than on their own entities because they are
    what someone inspecting "why did this not fire?" wants to see next to the
    phase, and because four more timestamp entities for values that change once
    a day is a poor trade.
    """

    def __init__(self, manager, message_bus, topic_prefix, **kwargs) -> None:
        super().__init__(
            manager=manager,
            message_bus=message_bus,
            topic_prefix=topic_prefix,
            sensor_id="sun_phase",
            name="Sun Phase",
            **kwargs,
        )

    def read(self, now: datetime) -> str | None:
        return self._provider.phase(now)

    def extra_attributes(self, now: datetime) -> dict[str, Any]:
        provider = self._provider
        elevation = provider.elevation(now)
        attributes: dict[str, Any] = {
            "golden_hour": provider.in_phase("golden_hour", now),
            "blue_hour": provider.in_phase("blue_hour", now),
            "elevation": None if elevation is None else round(elevation, 2),
        }
        for key, anchor in (
            ("next_sunrise", "sunrise"),
            ("next_sunset", "sunset"),
            ("next_dawn", "civil_dawn"),
            ("next_dusk", "civil_dusk"),
        ):
            moment = provider.next_anchor(anchor, now)
            attributes[key] = None if moment is None else _iso(moment)
        return attributes


class SunNextEventSensor(_SunSensor):
    """When a named anchor next happens, as an ISO-8601 timestamp.

    Home Assistant renders a ``timestamp`` sensor as relative time ("in 3
    hours"), which is what makes this readable on a dashboard.
    """

    def __init__(
        self,
        manager,
        message_bus,
        topic_prefix,
        anchor: str,
        sensor_id: str,
        name: str,
        **kwargs,
    ) -> None:
        self._anchor = anchor
        super().__init__(
            manager=manager,
            message_bus=message_bus,
            topic_prefix=topic_prefix,
            sensor_id=sensor_id,
            name=name,
            **kwargs,
        )

    @property
    def anchor(self) -> str:
        """The sun anchor this sensor tracks."""
        return self._anchor

    def read(self, now: datetime) -> str | None:
        moment = self._provider.next_anchor(self._anchor, now)
        # None during a polar season: publishing nothing keeps the last known
        # timestamp, which is more useful than an entity that goes unavailable
        # for two months.
        return None if moment is None else _iso(moment)


class SunAboveHorizonSensor(_SunSensor):
    """Whether the Sun is up, as ``on`` / ``off``.

    Published on a sensor topic and discovered as a binary_sensor, so the
    value is both readable in the panel's sensor list and automatable in HA.
    """

    def __init__(self, manager, message_bus, topic_prefix, **kwargs) -> None:
        super().__init__(
            manager=manager,
            message_bus=message_bus,
            topic_prefix=topic_prefix,
            sensor_id="sun_above_horizon",
            name="Sun Above Horizon",
            **kwargs,
        )

    def read(self, now: datetime) -> str | None:
        phase = self._provider.phase(now)
        return None if phase is None else ("on" if phase == "day" else "off")


def build_sun_sensors(
    manager: Manager,
    message_bus: MessageBus,
    topic_prefix: str,
    update_interval: TimePeriod | None = None,
) -> list[_SunSensor]:
    """Create every sun sensor, in the order they should be registered.

    Args:
        manager: The manager, which owns the provider.
        message_bus: MessageBus for MQTT.
        topic_prefix: MQTT topic prefix.
        update_interval: Override the 60-second default.

    Returns:
        The sensors, or an empty list when no location is configured.
    """
    if not manager.sun.configured:
        return []

    common = {
        "manager": manager,
        "message_bus": message_bus,
        "topic_prefix": topic_prefix,
        "update_interval": update_interval or DEFAULT_UPDATE_INTERVAL,
    }
    return [
        SunElevationSensor(**common),
        SunAzimuthSensor(**common),
        SunPhaseSensor(**common),
        SunAboveHorizonSensor(**common),
        SunNextEventSensor(
            anchor="sunrise", sensor_id="sun_next_sunrise", name="Sun Next Sunrise", **common
        ),
        SunNextEventSensor(
            anchor="sunset", sensor_id="sun_next_sunset", name="Sun Next Sunset", **common
        ),
    ]
