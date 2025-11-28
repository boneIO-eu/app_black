from __future__ import annotations

import logging

from boneio.const import BINARY_SENSOR, ID, MODEL, NAME, SENSOR
from boneio.integration.homeassistant import modbus_numeric_availabilty_message

from boneio.modbus.entities.base import ModbusBaseEntity

_LOGGER = logging.getLogger(__name__)


class ModbusBinarySensor(ModbusBaseEntity):
    _entity_type = BINARY_SENSOR

    def __init__(
        self, payload_off: str = "OFF", payload_on: str = "ON", **kwargs
    ) -> None:
        """
        Initialize single sensor.
        :param payload_off: payload off
        :param payload_on: payload on
        """
        super().__init__(
            **kwargs,
        )
        self._payload_off = payload_off
        self._payload_on = payload_on

    def discovery_message(self):
        value_template = f"{{{{ value_json.{self.decoded_name} }}}}"
        kwargs = {
            "value_template": value_template,
            "entity_id": self.name,
            "payload_off": self._payload_off,
            "payload_on": self._payload_on,
        }
        msg = modbus_numeric_availabilty_message(
            config_helper=self._config_helper,
            id=self._parent[ID],
            name=self._parent[NAME],
            state_topic_base=str(self.base_address),
            model=self._parent[MODEL],
            device_type=SENSOR,  # because we send everything to boneio/sensor from modbus.
            **kwargs,
        )
        return msg
