from __future__ import annotations

import logging

from boneio.const import ID, MODEL, NAME, SENSOR, SWITCH
from boneio.core.config import ConfigHelper
from boneio.helper.ha_discovery import (
    modbus_availabilty_message,
)
from boneio.core.utils.util import find_key_by_value
from boneio.message_bus.basic import MessageBus
from boneio.modbus.sensor.base import BaseSensor

_LOGGER = logging.getLogger(__name__)


class ModbusDerivedSwitch(BaseSensor):
    _ha_type_ = SWITCH

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
        payload_off: str = "OFF",
        payload_on: str = "ON",
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
        self._payload_off = payload_off
        self._payload_on = payload_on

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
            "entity_id": self.name,
            "command_topic": f"{self._config_helper.topic_prefix}/cmd/modbus/{self._parent[ID].lower()}/set",
            "command_template": '{"device": "'
            + self.decoded_name
            + '", "value": "{{ value }}"}',
            "payload_off": self._payload_off,
            "payload_on": self._payload_on,
        }
        msg = modbus_availabilty_message(
            topic=self._config_helper.topic_prefix,
            id=self._parent[ID],
            name=self._parent[NAME],
            state_topic_base=str(self.base_address),
            model=self._parent[MODEL],
            device_type=SENSOR,  # because we send everything to boneio/sensor from modbus.
            **kwargs,
        )
        return msg

    @property
    def source_sensor_decoded_name(self) -> str:
        return self._source_sensor_decoded_name

    def evaluate_state(
        self, source_sensor_value: int | float, timestamp: float
    ) -> int | float:
        self._timestamp = timestamp
        self._value = self._value_mapping.get(str(source_sensor_value), "None")

    def encode_value(self, value: str | float | int) -> int:
        if self._value_mapping:
            value = find_key_by_value(self._value_mapping, value)
            if value is not None:
                return int(value)
        return 0
