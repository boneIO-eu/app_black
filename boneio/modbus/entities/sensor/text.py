from __future__ import annotations

import logging

from boneio.const import ID, MODEL, NAME, SENSOR
from boneio.core.config import ConfigHelper
from boneio.integration.homeassistant import modbus_sensor_availabilty_message
from boneio.core.messaging.basic import MessageBus

from .base import BaseSensor

_LOGGER = logging.getLogger(__name__)


class ModbusTextSensor(BaseSensor):

    _ha_type_ = SENSOR

    def __init__(
        self,
        name: str,
        parent: dict,
        register_address: int,
        base_address: int,
        unit_of_measurement: str,
        state_class: str,
        device_class: str,
        value_type: str,
        return_type: str,
        filters: list,
        message_bus: MessageBus,
        config_helper: ConfigHelper,
        value_mapping: dict = {},
        user_filters: list | None = [],
        ha_filter: str = "",
    ) -> None:
        """
        Initialize single sensor.
        :param name: name of sensor
        :param register_address: address of register
        :param base_address: address of base
        :param unit_of_measurement: unit of measurement
        :param state_class: state class
        :param device_class: device class
        :param value_type: type of value
        :param return_type: type of return
        :param user_filters: list of user filters
        :param filters: list of filters
        :param send_ha_autodiscovery: function for sending HA autodiscovery
        """
        super().__init__(
            name=name,
            parent=parent,
            unit_of_measurement=unit_of_measurement,
            state_class=state_class,
            device_class=device_class,
            value_type=value_type,
            return_type=return_type,
            filters=filters,
            message_bus=message_bus,
            config_helper=config_helper,
            user_filters=user_filters,
            ha_filter=None,
        )
        self._register_address = register_address
        self._base_address = base_address
        self._value_mapping = value_mapping

    @property
    def address(self) -> int:
        return self._register_address

    @property
    def base_address(self) -> int:
        return self._base_address

    @property
    def state(self) -> str:
        """Give rounded value of temperature."""
        return self._value or ""

    def set_value(self, value, timestamp: float) -> None:
        self._timestamp = timestamp
        self._value = self._value_mapping.get(str(value), "Unknown")

    def discovery_message(self):
        kwargs = {
            "value_template": f"{{{{ value_json.{self.decoded_name} }}}}",
            "sensor_id": self.name,
        }
        return modbus_sensor_availabilty_message(
            topic=self._config_helper.topic_prefix,
            id=self._parent[ID],
            name=self._parent[NAME],
            state_topic_base=str(self.base_address),
            model=self._parent[MODEL],
            **kwargs,
        )
