from __future__ import annotations

from boneio.const import ID, MODEL, NAME, TEXT_SENSOR
from boneio.core.config import ConfigHelper
from boneio.integration.homeassistant import (
    modbus_sensor_availabilty_message,
)
from boneio.core.messaging.basic import MessageBus
from boneio.modbus.entities.base import ModbusDerivedEntity


class ModbusDerivedTextSensor(ModbusDerivedEntity):
    _entity_type = TEXT_SENSOR

    def __init__(
        self,
        name: str,
        parent: dict,
        message_bus: MessageBus,
        context_config: dict,
        config_helper: ConfigHelper,
        source_sensor_base_address: int,
        source_sensor_decoded_name: str,
        value_mapping: dict,
    ) -> None:
        ModbusDerivedEntity.__init__(
            self,
            name=name,
            parent=parent,
            value_type=None,
            filters=[],
            message_bus=message_bus,
            config_helper=config_helper,
            user_filters=[],
            ha_filter="",
            source_sensor_base_address=source_sensor_base_address,
            source_sensor_decoded_name=source_sensor_decoded_name,
        )
        self._context_config = context_config
        self._value_mapping = value_mapping

    @property
    def context(self) -> dict:
        return self._context_config

    @property
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

    def evaluate_state(
        self, source_sensor_value: int | float, timestamp: float
    ) -> None:
        self._timestamp = timestamp
        self._value = self._value_mapping.get(str(source_sensor_value), "Unknown")
