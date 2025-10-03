from __future__ import annotations

# Typing imports that create a circular dependency
from typing import TYPE_CHECKING

from boneio.const import BINARY_SENSOR, ID, MODEL, NAME, SENSOR
from boneio.helper.ha_discovery import modbus_numeric_availabilty_message
from boneio.modbus.sensor.base import ModbusBaseSensor

if TYPE_CHECKING:
    from ..coordinator import ModbusCoordinator


class ModbusBinaryWriteableEntityDiscrete(ModbusBaseSensor):

    _ha_type_ = BINARY_SENSOR

    def __init__(self, coordinator: ModbusCoordinator, write_address: int | None = None, payload_off: str = "OFF", payload_on: str = "ON", write_filters: list | None = [], **kwargs):
        ModbusBaseSensor.__init__(self, **kwargs)
        self._coordinator = coordinator
        self._write_address = write_address
        self._write_filters = write_filters
        self._payload_off = payload_off
        self._payload_on = payload_on

    async def write_value(self, value: float) -> None:
        await self._coordinator.write_register(
            unit=self._address,
            address=self.address,
            value=value,
            method=self._register_method,
        )

    @property
    def write_address(self) -> int | None:
        return self._write_address

    def discovery_message(self):
        value_template = f"{{{{ value_json.{self.decoded_name} }}}}"
        kwargs = {
            "value_template": value_template,
            "entity_id": self.name,
            "payload_off": self._payload_off,
            "payload_on": self._payload_on,
        }
        msg = modbus_numeric_availabilty_message(
            topic=self._config_helper.topic_prefix,
            id=self._parent[ID],
            name=self._parent[NAME],
            state_topic_base=str(self.base_address),
            model=self._parent[MODEL],
            device_type=SENSOR, #because we send everything to boneio/sensor from modbus.
            **kwargs,
        )
        return msg
        