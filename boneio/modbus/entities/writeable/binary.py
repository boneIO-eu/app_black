from __future__ import annotations

# Typing imports that create a circular dependency
from typing import TYPE_CHECKING

from boneio.const import BINARY_SENSOR, ID, MODEL, NAME, SENSOR
from boneio.integration.homeassistant import modbus_numeric_availabilty_message
from boneio.modbus.entities.base import ModbusBaseEntity

if TYPE_CHECKING:
    from boneio.modbus.coordinator import ModbusCoordinator


class ModbusBinaryWriteableEntityDiscrete(ModbusBaseEntity):

    _entity_type = BINARY_SENSOR

    def __init__(self, coordinator: ModbusCoordinator, write_address: int | None = None, payload_off: str = "OFF", payload_on: str = "ON", write_filters: list | None = [], **kwargs):
        ModbusBaseEntity.__init__(self, **kwargs)
        self._coordinator = coordinator
        self._write_address = write_address
        self._write_filters = write_filters
        self._payload_off = payload_off
        self._payload_on = payload_on

    async def write_value(self, value: float) -> None:
        await self._coordinator.write_register(
            entity=self,
            value=value,
        )

    @property
    def write_address(self) -> int | None:
        return self._write_address

    def discovery_message(self):
        value_template = f"{{{{ value_json.{self.decoded_name} }}}}"
        kwargs = {
            "value_template": value_template,
            "payload_off": self._payload_off,
            "payload_on": self._payload_on,
        }
        msg = modbus_numeric_availabilty_message(
            entity_id=self._id,
            entity_name=self._name,
            device_id=self._parent[ID],
            device_name=self._parent[NAME],
            manufacturer=self._parent.get("manufacturer", "boneIO"),
            state_topic_base=str(self.base_address),
            model=self._parent[MODEL],
            area=self._parent.get("area"),
            config_helper=self._config_helper,
            has_custom_id=self._parent.get("has_custom_id", False),
            device_type=SENSOR,  # because we send everything to boneio/sensor from modbus.
            **kwargs,
        )
        return msg
        