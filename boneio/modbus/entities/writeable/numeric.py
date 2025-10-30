from __future__ import annotations

# Typing imports that create a circular dependency
from typing import TYPE_CHECKING

from boneio.const import ID, MODEL, NAME, NUMERIC, SENSOR
from boneio.integration.homeassistant import modbus_numeric_availabilty_message

if TYPE_CHECKING:
    from boneio.modbus.coordinator import ModbusCoordinator

from boneio.modbus.entities.sensor.numeric import ModbusNumericSensor


class ModbusNumericWriteableEntityDiscrete(ModbusNumericSensor):

    _ha_type_ = SENSOR

    def __init__(self, coordinator: ModbusCoordinator, write_address: int | None = None, write_filters: list | None = [], **kwargs):
        ModbusNumericSensor.__init__(self, **kwargs)
        self._coordinator = coordinator
        self._write_address = write_address
        self._write_filters = write_filters

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


class ModbusNumericWriteableEntity(ModbusNumericWriteableEntityDiscrete):

    _ha_type_ = NUMERIC

    def discovery_message(self):
        value_template = f"{{{{ value_json.{self.decoded_name} }}}}"
        kwargs = {
            "value_template": value_template,
            "entity_id": self.name,
            "mode": "box",
            "command_topic": f"{self._config_helper.topic_prefix}/cmd/modbus/{self._parent[ID].lower()}/set",
            "command_template": '{"device": "' + self.decoded_name + '", "value": "{{ value }}"}',
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

    def encode_value(self, value: float | int) -> int:
        if self._write_filters:
            value = self._apply_filters(value=int(value), filters=self._write_filters)
        return int(value)

        