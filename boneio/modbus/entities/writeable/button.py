from __future__ import annotations

import json
from typing import TYPE_CHECKING

from boneio.const import BUTTON, ID, MODEL, NAME
from boneio.integration.homeassistant import modbus_button_availabilty_message
from boneio.modbus.entities.base import ModbusBaseEntity

if TYPE_CHECKING:
    from boneio.modbus.coordinator import ModbusCoordinator


class ModbusButton(ModbusBaseEntity):
    """One-shot trigger register: a press writes ``write_value``, whatever was asked.

    The device resets the register itself, so there is no state to read or
    publish and the register is never decoded.
    """

    _entity_type = BUTTON

    def __init__(self, coordinator: ModbusCoordinator, write_address: int | None, write_value: int = 1, **kwargs):
        ModbusBaseEntity.__init__(self, **kwargs)
        self._coordinator = coordinator
        self._write_address = write_address
        self._write_value = write_value

    @property
    def write_address(self) -> int | None:
        return self._write_address

    @property
    def state(self) -> None:
        return None

    def encode_value(self, value: str | float | int) -> int:
        return self._write_value

    async def press(self) -> None:
        await self._coordinator.write_register(value=self._write_value, entity=self)

    async def write_value(self, value: float) -> None:
        await self.press()

    def discovery_message(self):
        return modbus_button_availabilty_message(
            entity_id=self._id,
            entity_name=self.display_name,
            device_id=self._parent[ID],
            device_name=self._parent[NAME],
            manufacturer=self._parent.get("manufacturer", "boneIO"),
            model=self._parent[MODEL],
            area=self._parent.get("area"),
            config_helper=self._config_helper,
            has_custom_id=self._parent.get("has_custom_id", False),
            payload_press=json.dumps({"device": self.decoded_name, "value": "1"}),
        )
