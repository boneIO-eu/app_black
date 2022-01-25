import logging
import asyncio
from struct import unpack
import json
import os

from boneio.const import MODEL, SENSOR, STATE, ONLINE, OFFLINE, BASE, LENGTH, REGISTERS
from boneio.helper import BasicMqtt
from boneio.helper.ha_discovery import modbus_sensor_availabilty_message

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


CONVERT_METHODS = {"float32": float32}
REGISTERS_BASE = "registers_base"


def open_json(model: str) -> dict:
    """Open json file."""
    file = f"{os.path.join(os.path.dirname(__file__))}/{model}.json"
    with open(file, "r") as db_file:
        datastore = json.load(db_file)
        return datastore


class ModbusSensor(BasicMqtt):
    """Represent Modbus sensor in BoneIO."""

    SensorClass = None
    DefaultName = "ModbusSensor"

    def __init__(
        self,
        modbus,
        address: str,
        model: str,
        ha_discovery_prefix: str,
        topic_prefix: str,
        ha_discovery: bool = False,
        id: str = DefaultName,
        update_interval: int = 60,
        **kwargs,
    ):
        """Initialize Modbus sensor class."""
        super().__init__(
            id=id or address, topic_type=SENSOR, topic_prefix=topic_prefix, **kwargs
        )
        self._topic_prefix = topic_prefix
        self._modbus = modbus
        self._db = open_json(model=model)
        self._model = self._db[MODEL]
        self._address = address
        self._ha_discovery = ha_discovery
        self._discovery_sent = False
        self._ha_discovery_prefix = ha_discovery_prefix
        self._update_interval = update_interval

    def _send_ha_autodiscovery(
        self, id: str, sdm_name: str, sensor_id: str, **kwargs
    ) -> None:
        """Send HA autodiscovery information for each Modbus sensor."""
        _LOGGER.debug("Sending HA discovery for sensor %s %s.", sdm_name, sensor_id)
        self._send_message(
            topic=(
                f"{self._ha_discovery_prefix}/{SENSOR}/{self._topic_prefix}{id}"
                f"/{id}{sensor_id.replace('_', '').lower()}/config"
            ),
            payload=modbus_sensor_availabilty_message(
                topic=self._topic_prefix,
                id=id,
                name=sdm_name,
                model=self._model,
                sensor_id=sensor_id,
                **kwargs,
            ),
        )

    def _send_discovery_for_all_registers(self, register: int = 0) -> bool:
        """Send discovery message to HA for each register."""
        if register > 0:
            print(self._db)
            for data in self._db[REGISTERS_BASE]:
                for register in data[REGISTERS]:
                    kwargs = {
                        "unit_of_measurement": register.get("unit_of_measurement"),
                        "state_class": register.get("state_class"),
                        "value_template": f'{{{{ value_json.{register.get("name")} | round(2) }}}}',
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
            return True
        return False

    async def send_state(self) -> None:
        """Fetch state periodically and send to MQTT."""
        if not self._discovery_sent and self._ha_discovery:
            register = self._modbus.read_single_register(unit=self._address, address=0)
            self._discovery_sent = self._send_discovery_for_all_registers(register)
        while True:
            payload_online = OFFLINE
            for data in self._db[REGISTERS_BASE]:
                values = self._modbus.read_multiple_registers(
                    unit=self._address, address=data[BASE], count=data[LENGTH]
                )
                if payload_online == OFFLINE:
                    payload_online = ONLINE
                    self._send_message(
                        topic=f"{self._topic_prefix}/{self._id}{STATE}",
                        payload=payload_online,
                    )
                output = {}
                for register in data["registers"]:
                    output[register.get("name")] = CONVERT_METHODS[
                        register.get("return_type", float32)
                    ](values, data[BASE], register.get("address"))
                self._send_message(
                    topic=f"{self._send_topic}/{data[BASE]}",
                    payload=output,
                )
            await asyncio.sleep(self._update_interval)
