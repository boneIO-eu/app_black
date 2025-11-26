"""Configuration loader - remaining utility functions."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from boneio.components.sensor import SerialNumberSensor
from boneio.const import SENSOR
from boneio.core.messaging.basic import MessageBus
from boneio.integration.homeassistant import ha_sensor_availabilty_message

if TYPE_CHECKING:
    from boneio.core.manager import Manager

_LOGGER = logging.getLogger(__name__)


def create_serial_number_sensor(
    manager: Manager,
    message_bus: MessageBus,
    topic_prefix: str,
):
    """Create Serial number sensor in manager."""
    sensor = SerialNumberSensor(
        id="serial_number",
        name="Serial number",
        manager=manager,
        message_bus=message_bus,
        topic_prefix=topic_prefix,
    )
    manager.send_ha_autodiscovery(
        id="serial_number",
        name="Serial number",
        ha_type=SENSOR,
        entity_category="diagnostic",
        availability_msg_func=ha_sensor_availabilty_message,
    )
    return sensor
