from __future__ import annotations

import logging

from boneio.const import ID, MODEL, NAME, SENSOR
from boneio.core.config import ConfigHelper
from boneio.integration.homeassistant import modbus_sensor_availabilty_message
from boneio.core.messaging.basic import MessageBus

from boneio.modbus.entities.base import ModbusBaseEntity

_LOGGER = logging.getLogger(__name__)


class ModbusTextSensor(ModbusBaseEntity):

    _entity_type = SENSOR

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
        filters: list,
        message_bus: MessageBus,
        config_helper: ConfigHelper,
        value_mapping: dict = {},
        user_filters: list | None = [],
        ha_filter: str = "",
    ) -> None:
        """Initialize single sensor.

        Args:
            name: name of sensor
            parent: parent device info
            register_address: address of register
            base_address: address of base
            unit_of_measurement: unit of measurement
            state_class: state class
            device_class: device class
            value_type: type of value for decoding
            filters: list of filters
            message_bus: message bus instance
            config_helper: config helper instance
            value_mapping: mapping of raw values to text
            user_filters: list of user filters
            ha_filter: HA filter string
        """
        super().__init__(
            name=name,
            parent=parent,
            register_address=register_address,
            base_address=base_address,
            unit_of_measurement=unit_of_measurement,
            state_class=state_class,
            device_class=device_class,
            value_type=value_type,
            filters=filters,
            message_bus=message_bus,
            config_helper=config_helper,
            user_filters=user_filters,
            ha_filter="",
        )
        self._value_mapping = value_mapping

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
            config_helper=self._config_helper,
            id=self._parent[ID],
            name=self._parent[NAME],
            state_topic_base=str(self.base_address),
            model=self._parent[MODEL],
            area=self._parent.get("area"),
            **kwargs,
        )
