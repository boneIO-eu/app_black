"""INA219 Black sensor."""
from __future__ import annotations
from datetime import datetime
import logging
import asyncio
from boneio.const import SENSOR, STATE
from boneio.helper import BasicMqtt, AsyncUpdater
from boneio.helper.filter import Filter
from boneio.helper.sensor.ina_219_smbus import INA219_I2C

_LOGGER = logging.getLogger(__name__)

unit_converter = {
    "current": "A",
    "power": "W",
    "voltage": "V"
}


class INA219Sensor(BasicMqtt, Filter):
    """Represent singel value from INA219 as sensor."""

    def __init__(self, device_class: str, filters: list, state: float | None, **kwargs) -> None:
        super().__init__(topic_type=SENSOR, **kwargs)
        self._unit_of_measurement = unit_converter[device_class]
        self._device_class = device_class
        self._filters = filters
        self._raw_state = state
        self._state = (
            self._apply_filters(value=self._raw_state) if self._raw_state else None
        )

    @property
    def raw_state(self) -> float | None:
        return self._raw_state

    @raw_state.setter
    def raw_state(self, value: float) -> None:
        self._raw_state = value

    @property
    def state(self) -> float | None:
        return self._state
    
    @property
    def device_class(self) -> str:
        return self._device_class
    
    @property
    def unit_of_measurement(self) -> str:
        return self._unit_of_measurement

    def update(self, time: datetime) -> None:
        """Fetch temperature periodically and send to MQTT."""
        _state = self._apply_filters(value=self._raw_state) if self._raw_state else None
        if not _state:
            return
        self._state = _state
        self._send_message(
            topic=self._send_topic,
            payload={STATE: self.state},
        )


class INA219(AsyncUpdater, Filter):
    """Represent INA219 sensors."""

    def __init__(self, address: int, id: str, sensors: list[dict] = [], **kwargs) -> None:
        """Setup GPIO ADC Sensor"""
        self._loop = asyncio.get_event_loop()
        self._ina_219 = INA219_I2C(address=address)
        self._sensors = {}
        self._states = {}
        self._id = id
        for sensor in sensors:
            _name = sensor["id"]
            _id = f"{id}{_name.replace(' ', '')}"
            self._states[sensor["device_class"]] = None
            self._sensors[sensor["device_class"]] = INA219Sensor(
                device_class=sensor["device_class"],
                filters=sensor.get("filters", []),
                state=self._states[sensor["device_class"]],
                name=_name,
                id=_id,
                **kwargs,
            )
        AsyncUpdater.__init__(self, **kwargs)
        _LOGGER.debug("Configured INA219 on address %s", address)

    @property
    def id(self) -> str:
        return self._id

    @property
    def sensors(self) -> dict:
        return self._sensors

    async def async_update(self, time: datetime) -> None:
        """Fetch temperature periodically and send to MQTT."""
        for k in self._states.keys():
            value = getattr(self._ina_219, k)
            self._states[k] = value
            _LOGGER.debug("Read %s with value: %s", k, value)
        for k, sensor in self._sensors.items():
            if sensor.raw_state != self._states[k]:
                sensor.raw_state = self._states[k]
                self._loop.call_soon(sensor.update, time)
