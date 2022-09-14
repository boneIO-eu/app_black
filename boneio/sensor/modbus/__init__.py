import asyncio
import json
import logging
import os
from datetime import datetime
from struct import unpack

from boneio.const import (
    ADDRESS,
    BASE,
    LENGTH,
    MODEL,
    OFFLINE,
    ONLINE,
    REGISTERS,
    SENSOR,
    STATE,
)
from boneio.helper import BasicMqtt, AsyncUpdater
from boneio.helper.config import ConfigHelper
from boneio.helper.events import EventBus
from boneio.helper.ha_discovery import modbus_sensor_availabilty_message
from boneio.modbus import Modbus

_LOGGER = logging.getLogger(__name__)


def float32(result, base, addr):
    """Read Float value from register."""
    low = result.getRegister(addr - base)
    high = result.getRegister(addr - base + 1)
    data = bytearray(4)
    data[0] = high & 0xFF
    data[1] = high >> 8
    data[2] = low & 0xFF
    data[3] = low >> 8
    val = unpack("f", bytes(data))
    return val[0]


def floatsofar(result, base, addr):
    """Read Float value from register."""
    low = result.getRegister(addr - base)
    high = result.getRegister(addr - base + 1)
    return high + low


def multiply0_1(result, base, addr):
    low = result.getRegister(addr - base)
    return round(low * 0.1, 4)


def multiply0_01(result, base, addr):
    low = result.getRegister(addr - base)
    return round(low * 0.01, 4)


def multiply10(result, base, addr):
    low = result.getRegister(addr - base)
    return round(low * 10, 4)


def regular_result(result, base, addr):
    return result.getRegister(addr - base)


CONVERT_METHODS = {
    "float32": float32,
    "multiply0_1": multiply0_1,
    "multiply0_01": multiply0_01,
    "floatsofar": floatsofar,
    "multiply10": multiply10,
    "regular": regular_result,
}
REGISTERS_BASE = "registers_base"


def open_json(model: str) -> dict:
    """Open json file."""
    file = f"{os.path.join(os.path.dirname(__file__))}/{model}.json"
    with open(file, "r") as db_file:
        datastore = json.load(db_file)
        return datastore


class ModbusSensor(BasicMqtt, AsyncUpdater):
    """Represent Modbus sensor in BoneIO."""

    SensorClass = None
    DefaultName = "ModbusSensor"

    def __init__(
        self,
        modbus: Modbus,
        address: str,
        model: str,
        config_helper: ConfigHelper,
        event_bus: EventBus,
        id: str = DefaultName,
        **kwargs,
    ):
        """Initialize Modbus sensor class."""
        super().__init__(
            id=id or address,
            topic_type=SENSOR,
            topic_prefix=config_helper.topic_prefix,
            **kwargs,
        )
        self._config_helper = config_helper
        self._modbus = modbus
        self._db = open_json(model=model)
        self._model = self._db[MODEL]
        self._address = address
        self._discovery_sent = False
        self._payload_online = OFFLINE
        event_bus.add_haonline_listener(target=self.set_payload_offline)
        AsyncUpdater.__init__(self, **kwargs)

    def set_payload_offline(self):
        self._payload_online = OFFLINE

    def _send_ha_autodiscovery(
        self, id: str, sdm_name: str, sensor_id: str, **kwargs
    ) -> None:
        """Send HA autodiscovery information for each Modbus sensor."""
        _LOGGER.debug(
            "Sending HA discovery for modbus sensor %s %s.", sdm_name, sensor_id
        )
        topic = (
            f"{self._config_helper.ha_discovery_prefix}/{SENSOR}/{self._config_helper.topic_prefix}{id}"
            f"/{id}{sensor_id.replace('_', '').replace(' ', '').lower()}/config"
        )
        payload = modbus_sensor_availabilty_message(
            topic=self._config_helper.topic_prefix,
            id=id,
            name=sdm_name,
            model=self._model,
            sensor_id=sensor_id,
            **kwargs,
        )
        self._config_helper.add_autodiscovery_msg(topic=topic, payload=payload)
        self._send_message(topic=topic, payload=payload)

    def _send_discovery_for_all_registers(self, register: int = 0) -> bool:
        """Send discovery message to HA for each register."""
        for data in self._db[REGISTERS_BASE]:
            for register in data[REGISTERS]:
                value_template = (
                    f'{{{{ value_json.{register.get("name").replace(" ", "")} | '
                    f'{register.get("ha_filter", "round(2)")} }}}}'
                )
                kwargs = {
                    "unit_of_measurement": register.get("unit_of_measurement"),
                    "state_class": register.get("state_class"),
                    "value_template": value_template,
                    "sensor_id": register.get("name"),
                }
                device_class = register.get("device_class")
                if device_class:
                    kwargs["device_class"] = device_class
                self._send_ha_autodiscovery(
                    id=self._id,
                    sdm_name=self._name,
                    state_topic_base=data[BASE],
                    **kwargs,
                )
        return datetime.now()

    async def check_availability(self) -> None:
        """Get first register and check if it's available."""
        if (
            not self._discovery_sent
            or (datetime.now() - self._discovery_sent).seconds > 3600
        ) and self._config_helper.topic_prefix:
            self._discovery_sent = False
            first_register_base = self._db[REGISTERS_BASE][0]
            register_method = first_register_base.get("register_type", "input")
            # Let's try fetch register 2 times in case something wrong with initial packet.
            for _ in [0, 1]:
                register = await self._modbus.read_single_register(
                    unit=self._address,
                    address=first_register_base[REGISTERS][0][ADDRESS],
                    method=register_method,
                )
                if register is not None:
                    self._discovery_sent = self._send_discovery_for_all_registers(
                        register
                    )
                    await asyncio.sleep(2)
                    break
            _LOGGER.error(
                "Discovery for %s not sent. First register not available.", self._id
            )

    async def async_update(self, time: datetime) -> None:
        """Fetch state periodically and send to MQTT."""
        update_interval = self._update_interval.total_in_seconds
        await self.check_availability()
        for data in self._db[REGISTERS_BASE]:
            values = await self._modbus.read_multiple_registers(
                unit=self._address,
                address=data[BASE],
                count=data[LENGTH],
                method=data.get("register_type", "input"),
            )
            if self._payload_online == OFFLINE and values:
                _LOGGER.info("Sending online payload about device.")
                self._payload_online = ONLINE
                self._send_message(
                    topic=f"{self._config_helper.topic_prefix}/{self._id}{STATE}",
                    payload=self._payload_online,
                )
            if not values:
                if update_interval < 600:
                    # Let's wait litte more for device.
                    update_interval = update_interval * 1.5
                else:
                    # Let's assume device is offline.
                    self.set_payload_offline()
                    self._send_message(
                        topic=f"{self._config_helper.topic_prefix}/{self._id}{STATE}",
                        payload=self._payload_online,
                    )
                _LOGGER.warn(
                    "Can't fetch data from modbus device %s. Will sleep for %s seconds",
                    self.id,
                    update_interval,
                )
                self._discovery_sent = False
                return update_interval
            elif update_interval != self._update_interval.total_in_seconds:
                update_interval = self._update_interval.total_in_seconds
            output = {}
            for register in data["registers"]:
                output[register.get("name").replace(" ", "")] = CONVERT_METHODS[
                    register.get("return_type", "regular")
                ](result=values, base=data[BASE], addr=register.get("address"))
            self._send_message(
                topic=f"{self._send_topic}/{data[BASE]}",
                payload=output,
            )
        return update_interval
