from __future__ import annotations

from boneio.const import ID, MODEL, NAME, TEXT_SENSOR
from boneio.core.config import ConfigHelper
from boneio.integration.homeassistant import (
    modbus_sensor_availabilty_message,
)
from boneio.core.messaging.basic import MessageBus
from boneio.modbus.entities.sensor.base import BaseSensor


class ModbusDerivedTextSensor(BaseSensor):
    _ha_type_ = TEXT_SENSOR

    def __init__(
        self,
        name: str,
        parent: dict,
        message_bus: MessageBus,
        context_config: dict,
        config_helper: ConfigHelper,
        source_sensor_base_address: str,
        source_sensor_decoded_name: str,
        value_mapping: dict,
    ) -> None:
        BaseSensor.__init__(
            self,
            name=name,
            parent=parent,
            value_type=None,
            return_type=None,
            filters=[],
            message_bus=message_bus,
            config_helper=config_helper,
            user_filters=[],
            ha_filter="",
        )
        self._context_config = context_config
        self._source_sensor_base_address = source_sensor_base_address
        self._source_sensor_decoded_name = source_sensor_decoded_name
        self._value_mapping = value_mapping

    @property
    def context(self) -> dict:
        return self._context_config

    @property
    def base_address(self) -> str:
        return self._source_sensor_base_address

    @property
    def state(self) -> str:
        """Give rounded value of temperature."""
        return self._value or ""

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

    @property
    def source_sensor_decoded_name(self) -> str:
        return self._source_sensor_decoded_name

    def evaluate_state(
        self, source_sensor_value: int | float, timestamp: float
    ) -> int | float:
        self._timestamp = timestamp
        self._value = self._value_mapping.get(str(source_sensor_value), "Unknown")
