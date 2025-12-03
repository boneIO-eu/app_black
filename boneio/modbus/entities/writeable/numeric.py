from __future__ import annotations

# Typing imports that create a circular dependency
from typing import TYPE_CHECKING

from boneio.const import ID, MODEL, NAME, NUMERIC, SENSOR
from boneio.integration.homeassistant import modbus_numeric_availabilty_message

if TYPE_CHECKING:
    from boneio.modbus.coordinator import ModbusCoordinator

from boneio.modbus.entities.sensor.numeric import ModbusNumericSensor


class ModbusNumericWriteableEntityDiscrete(ModbusNumericSensor):

    _entity_type = SENSOR

    def __init__(self, coordinator: ModbusCoordinator, write_address: int | None = None, write_filters: list | None = [], step: float | str | None = None, **kwargs):
        ModbusNumericSensor.__init__(self, **kwargs)
        self._coordinator = coordinator
        self._write_address = write_address
        self._write_filters = write_filters
        self._step = step

    async def write_value(self, value: float) -> None:
        """Write value to the modbus register.
        
        Args:
            value: The numeric value to write.
        """
        await self._coordinator.write_register(value=value, entity=self)

    @property
    def write_address(self) -> int | None:
        return self._write_address

    @property
    def step(self) -> float | str | None:
        return self._step or 1.0

    def discovery_message(self):
        value_template = f"{{{{ value_json.{self.decoded_name} }}}}"
        kwargs = {
            "value_template": value_template,
            "entity_id": self.name,
        }
        msg = modbus_numeric_availabilty_message(
            config_helper=self._config_helper,
            id=self._parent[ID],
            name=self._parent[NAME],
            state_topic_base=str(self.base_address),
            model=self._parent[MODEL],
            device_type=SENSOR, #because we send everything to boneio/sensor from modbus.
            **kwargs,
        )
        return msg


class ModbusNumericWriteableEntity(ModbusNumericWriteableEntityDiscrete):

    _entity_type = NUMERIC

    def discovery_message(self):
        value_template = f"{{{{ value_json.{self.decoded_name} }}}}"
        kwargs = {
            "value_template": value_template,
            "entity_id": self.name,
            "mode": "box",
            "step": self.step,
            "command_topic": f"{self._config_helper.topic_prefix}/cmd/modbus/{self._parent[ID].lower()}/set",
            "command_template": '{"device": "' + self.decoded_name + '", "value": "{{ value }}"}',
        }
        msg = modbus_numeric_availabilty_message(
            config_helper=self._config_helper,
            id=self._parent[ID],
            name=self._parent[NAME],
            state_topic_base=str(self.base_address),
            model=self._parent[MODEL],
            device_type=SENSOR, #because we send everything to boneio/sensor from modbus.
            **kwargs,
        )
        return msg

    def encode_value(self, value: float | int | None) -> float | int | None:
        if self._write_filters:
            value = self._apply_filters(value=value, filters=self._write_filters)
        return value

        