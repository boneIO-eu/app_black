import logging
import asyncio
from struct import unpack
from collections import namedtuple

from boneio.const import SDM630, SENSOR, STATE, ONLINE, OFFLINE, BASE, LENGTH, REGISTERS
from boneio.helper import BasicMqtt
from boneio.helper.ha_discovery import sdm630_availabilty_message

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


RegistryEntry = namedtuple(
    "RegistryEntry", "sensor_id address unit_of_measurement state_class device_class"
)

REGISTER_BASE = [
    {
        BASE: 0x00,
        LENGTH: 60,
        REGISTERS: [
            RegistryEntry("Voltage_Phase1", 0x0000, "V", "measurement", "voltage"),
            RegistryEntry("Voltage_Phase2", 0x0002, "V", "measurement", "voltage"),
            RegistryEntry("Voltage_Phase3", 0x0004, "V", "measurement", "voltage"),
            RegistryEntry("Current_Phase1", 0x0006, "A", "measurement", "current"),
            RegistryEntry("Current_Phase2", 0x0008, "A", "measurement", "current"),
            RegistryEntry("Current_Phase3", 0x000A, "A", "measurement", "current"),
            RegistryEntry("Power_Phase1", 0x000C, "W", "measurement", "power"),
            RegistryEntry("Power_Phase2", 0x000E, "W", "measurement", "power"),
            RegistryEntry("Power_Phase3", 0x0010, "W", "measurement", "power"),
            RegistryEntry("Power_VA_Phase1", 0x0012, "VA", "measurement", None),
            RegistryEntry("Power_VA_Phase2", 0x0014, "VA", "measurement", None),
            RegistryEntry("Power_VA_Phase3", 0x0016, "VA", "measurement", None),
            RegistryEntry("Power_VAr_Phase1", 0x0018, "var", "measurement", None),
            RegistryEntry("Power_VAr_Phase2", 0x001A, "var", "measurement", None),
            RegistryEntry("Power_VAr_Phase3", 0x001C, "var", "measurement", None),
            RegistryEntry("Power_Factor_Phase1", 0x001E, "%", "measurement", None),
            RegistryEntry("Power_Factor_Phase2", 0x0020, "%", "measurement", None),
            RegistryEntry("Power_Factor_Phase3", 0x0022, "%", "measurement", None),
            RegistryEntry("Phase_Angle_Phase1", 0x0024, "°", "measurement", None),
            RegistryEntry("Phase_Angle_Phase2", 0x0026, "°", "measurement", None),
            RegistryEntry("Phase_Angle_Phase3", 0x0028, "°", "measurement", None),
            RegistryEntry(
                "Line_to_Neutral_AVG_Volts", 0x002A, "V", "measurement", None
            ),
            RegistryEntry("AVG_Current", 0x002E, "A", "measurement", "current"),
            RegistryEntry("Sum_Current", 0x0030, "A", "measurement", "current"),
            RegistryEntry("Total_Power_Watt", 0x0034, "W", "measurement", "power"),
            RegistryEntry("Total_Power_VA", 0x0038, "VA", "measurement", None),
        ],
    },
    {
        BASE: 0x003C,
        LENGTH: 48,
        REGISTERS: [
            RegistryEntry("System_VAr_Total", 0x003C, "var", "measurement", None),
            RegistryEntry(
                "System_Power_Factor_Total", 0x003E, "%", "measurement", None
            ),
            RegistryEntry("System_PhaseAngle", 0x0042, "°", "measurement", None),
            RegistryEntry("Frequency", 0x0046, "Hz", "measurement", None),
            RegistryEntry(
                "Import_Energy_kWh_Total", 0x0048, "kWh", "total_increasing", "energy"
            ),
            RegistryEntry(
                "Export_Energy_kWh_Total", 0x004A, "kWh", "total_increasing", "energy"
            ),
            RegistryEntry(
                "Import_Energy_kVArh_Total", 0x004C, "kvArh", "total_increasing", None
            ),
            RegistryEntry(
                "Export_Energy_kVArh_Total", 0x004E, "kvArh", "total_increasing", None
            ),
        ],
    },
    {
        BASE: 0x0156,
        LENGTH: 4,
        REGISTERS: [
            RegistryEntry("kWh_Total", 0x0156, "kWh", "total_increasing", "energy"),
            RegistryEntry("kvarh_Total", 0x0158, "kvArh", "total_increasing", None),
        ],
    },
]


class Sdm630(BasicMqtt):
    """Represent Sdm630 sensor in BoneIO."""

    SensorClass = None
    DefaultName = SDM630

    def __init__(
        self,
        modbus,
        address: str,
        ha_discovery_prefix: str,
        topic_prefix: str,
        ha_discovery: bool = False,
        id: str = DefaultName,
        update_interval: int = 60,
        **kwargs,
    ):
        """Initialize Sdm630 class."""
        super().__init__(
            id=id or address, topic_type=SENSOR, topic_prefix=topic_prefix, **kwargs
        )
        self._topic_prefix = topic_prefix
        self._modbus = modbus
        self._address = address
        self._ha_discovery = ha_discovery
        self._discovery_sent = False
        self._ha_discovery_prefix = ha_discovery_prefix
        self._update_interval = update_interval

    def _send_ha_autodiscovery(
        self, id: str, sdm_name: str, sensor_id: str, **kwargs
    ) -> None:
        """Send HA autodiscovery information for each SDM sensor."""
        _LOGGER.debug("Sending HA discovery for sensor %s %s.", sdm_name, sensor_id)
        self._send_message(
            topic=(
                f"{self._ha_discovery_prefix}/{SENSOR}/{self._topic_prefix}"
                f"/{id}{sensor_id.replace('_', '').lower()}/config"
            ),
            payload=sdm630_availabilty_message(
                topic=self._topic_prefix,
                id=id,
                name=sdm_name,
                sensor_id=sensor_id,
                **kwargs,
            ),
        )

    def _send_discovery_for_all_registers(self, register: int = 0) -> bool:
        """Send discovery message to HA for each register."""
        if register > 0:
            for data in REGISTER_BASE:
                for register in data["registers"]:
                    kwargs = {
                        "unit_of_measurement": getattr(register, "unit_of_measurement"),
                        "state_class": getattr(register, "state_class"),
                        "value_template": "{{ value | round(2)}}",
                        "sensor_id": getattr(register, "sensor_id"),
                    }
                    if getattr(register, "device_class"):
                        kwargs["device_class"] = getattr(register, "device_class")
                    self._send_ha_autodiscovery(
                        id=self._id, sdm_name=self._name, **kwargs
                    )
            return True
        return False

    async def send_state(self) -> None:
        """Fetch state periodically and send to MQTT."""
        register = self._modbus.read_single_register(unit=self._address, address=0)
        if not self._discovery_sent and self._ha_discovery:
            self._discovery_sent = self._send_discovery_for_all_registers(register)
        while True:
            payload_online = OFFLINE
            for data in REGISTER_BASE:
                values = self._modbus.read_multiple_registers(
                    unit=self._address, address=data[BASE], count=data[LENGTH]
                )
                if payload_online == OFFLINE:
                    payload_online = ONLINE
                    self._send_message(
                        topic=f"{self._topic_prefix}/{self._id}{STATE}",
                        payload=payload_online,
                    )
                for register in data["registers"]:
                    self._send_message(
                        topic=f'{self._send_topic}/{getattr(register, "sensor_id")}',
                        payload=float32(
                            values, data[BASE], getattr(register, "address")
                        ),
                    )
            await asyncio.sleep(self._update_interval)
