"""Sensors and expanders: 1-Wire, ADC, INA219/226, LM75, MCP9808, Modbus, CAN,
the MCP23017/PCF8575/PCA9685 expanders and virtual energy sensors.

Mirrors boneio/schema/schema.yaml for these sections. One rule is enforced
here and not at start-up: ``update_interval``'s ``min: 1s`` on Modbus devices.
Cerberus compares a TimePeriod with a string, gets TypeError and lets it
pass, so a saved config may still hold less; a save cannot add it.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import AfterValidator, BeforeValidator, Field, model_validator

from boneio.core.config.models.base import Model, Str, StrPeriod, coerce, section, str_lower
from boneio.core.config.onewire_address import kernel_address
from boneio.core.config.yaml_util import _get_schema

Number = Union[float, int]
Address = Union[str, int]
Filter = dict[
    Literal["offset", "round", "multiply", "filter_out", "filter_out_greater", "filter_out_lower"],
    Any,
]


_UPDATE = "Update interval. How often to fetch data from sensor. Default to 60s."
_FILTERS = "List of filters to apply. Allowed filters visible in allowed section."
_I2C_ID = "Id of I2C to use in pin config"
_SHOW_IN_HA = "If you want you can disable discovering this input in HA."


def _interval(default: str, description: str | None = _UPDATE):
    return Field(default, validate_default=True, description=description)


def _round(description: str = _FILTERS):
    return Field(default_factory=lambda: [{"round": 2}], description=description)


# ------------------------------------------------------------------ sensors


class OneWireSensor(Model):
    id: str | None = Field(None, description="Id to use in HA if needed. Default to address.")
    name: str | None = Field(None, description="Display name for the sensor in Home Assistant.")
    area: str | None = Field(
        None, description="Area/room where the sensor is located. Used for HA device grouping."
    )
    # Stricter than start-up, which lets an unknown address through.
    address: Annotated[str, BeforeValidator(kernel_address)] = Field(
        description="Address of Dallas device, as the kernel names it (28-0000098c7df0) or as ESPHome "
        "writes it (0xc0000000053f3328)"
    )
    show_in_ha: bool = Field(True, description=_SHOW_IN_HA)
    filters: list[Filter] = _round()
    update_interval: StrPeriod = _interval("60s")
    unit_of_measurement: Literal["°C", "°F"] = "°C"


class Adc(Model):
    name: str | None = Field(None, description="Display name for the sensor in Home Assistant.")
    id: str | None = Field(None, description="Id to use for MQTT topic. Default to name or pin number.")
    pin: Literal["P9_33", "P9_35", "P9_36", "P9_37", "P9_38", "P9_39", "P9_40"] = Field(
        description="PIN to use."
    )
    area: str | None = Field(None, description="Area/Room")
    update_interval: StrPeriod = _interval("60s")
    show_in_ha: bool = Field(True, description=_SHOW_IN_HA)
    filters: list[Filter] = Field(
        default_factory=lambda: [{"multiply": 1.8}, {"round": 2}], description=_FILTERS
    )


class InaSensor(Model):
    id: str | None = Field(None, description=_I2C_ID)
    device_class: Literal["current", "power", "voltage"] | None = None
    filters: list[Filter] = _round()


def _ina_sensors() -> list[InaSensor]:
    return [
        InaSensor(id="Board Current", device_class="current"),
        InaSensor(id="Board Power", device_class="power"),
        InaSensor(id="Board Voltage", device_class="voltage"),
    ]


# INA219 and INA226 share their fields.
class Ina(Model):
    id: str | None = Field(None, description=_I2C_ID)
    address: Address = Field(64, description="Address of I2C")
    sensors: list[InaSensor] = Field(default_factory=_ina_sensors)
    update_interval: StrPeriod = _interval("60s")


class Lm75(Model):
    id: str | None = Field(None, description=_I2C_ID)
    address: int = Field(72, description="Address of I2C")
    update_interval: StrPeriod = _interval("60s")
    filters: list[Filter] = _round()
    unit_of_measurement: Literal["°C", "°F"] = "°C"


class Mcp9808(Lm75):
    address: Address = Field(24, description="Address of I2C device")


# ------------------------------------------------------------------- modbus


class Modbus(Model):
    uart: Literal["uart1", "uart2", "uart3", "uart4", "uart5"] = Field(description="Uart ID to use")
    baudrate: int = 9600
    stopbits: Literal[1, 2] = 1
    bytesize: int = 8
    parity: Literal["N", "E", "O"] = "N"
    timeout: StrPeriod = _interval("1500ms", "Response timeout. Increase for slow devices or long cables.")
    inter_device_delay: StrPeriod = _interval(
        "5ms",
        "Delay between Modbus transactions. Helps with star topology wiring where signal reflections need "
        "time to settle. Recommended 5-50ms for star, 0 for daisy-chain.",
    )


def _known_model(value: str) -> str:
    # The schema's list is filled from the device files when it is loaded.
    allowed = _get_schema()["modbus_devices"]["schema"]["schema"]["model"]["allowed"]
    if value not in allowed:
        raise ValueError(f"unallowed value {value}")
    return value



class SensorsFilters(Model):
    temperature: list[Filter] = Field(default_factory=lambda: [{"round": 2}], description=_FILTERS)
    humidity: list[Filter] = Field(default_factory=lambda: [{"round": 2}], description=_FILTERS)


Length = Annotated[Number, BeforeValidator(coerce("length_to_meters"))]


class TankData(Model):
    width: Length | None = Field(None, description="Width of sensor in meters, cm etc. Without unit is meters")
    length: Length | None = Field(None, description="Length of sensor in meters, cm etc. Without unit is meters")


def _at_least_a_second(value):
    if value.total_in_seconds < 1:
        raise ValueError("at least 1s: a Modbus device polled faster crowds out the others on the bus")
    return value


class ModbusDevice(Model):
    name: str | None = Field(None, description="Display Name")
    area: str | None = Field(None, description="Area")
    id: Annotated[str, BeforeValidator(str), Field(pattern=r"^[a-z0-9_]+$")] | None = Field(
        None, description="Device ID"
    )
    address: Address = Field(description="Address of Modbus sensor to use.")
    # No enum in the schema: _known_model reads the device files, so a new
    # device needs no schema rebuild.
    model: Annotated[str, BeforeValidator(str_lower), AfterValidator(_known_model)] = Field(
        description="Model to load from database."
    )
    update_interval: Annotated[StrPeriod, AfterValidator(_at_least_a_second)] = Field(
        "30s",
        validate_default=True,
        description="Update interval (minimum 1 second).",
        json_schema_extra={"minimum": 1000},
    )
    entity_labels: dict[str, str] | None = Field(None, description="Custom entity labels")
    sensors_filters: SensorsFilters | None = Field(
        None,
        description="List of sub sensors to use to filter. Available values are temperature or humidity. "
        "Only for CWT model.",
        json_schema_extra={"x-dependencies": {"model": ["cwt"]}},
    )
    data: TankData | None = Field(
        None,
        description="Data to pass to additional entities. Only for liquid-sensor model.",
        json_schema_extra={"x-dependencies": {"model": ["liquid-sensor"]}},
    )

    @model_validator(mode="after")
    def _blocks_fit_the_model(self) -> ModbusDevice:
        if self.sensors_filters is not None and self.model != "cwt":
            raise ValueError("sensors_filters: only allowed with model cwt")
        if self.data is not None and self.model != "liquid-sensor":
            raise ValueError("data: only allowed with model liquid-sensor")
        return self


# ---------------------------------------------------------------------- can


class Can(Model):
    enabled: bool = Field(False, description="Enable CAN bus communication.")
    channel: str = Field("can0", description="CAN interface name")
    bitrate: Literal[10000, 20000, 50000, 100000, 125000, 250000, 500000, 1000000] = Field(
        125000, description="CAN bus bitrate in bps"
    )
    node_id: Address = Field("auto", description="CANopen node ID (1-127 or 'auto')")
    mode: Literal["master", "slave"] = Field("master", description="CAN bus mode")
    auto_setup: bool = Field(True, description="Auto-setup CAN interface")
    restart_on_error: bool = Field(True, description="Restart CAN interface on bus-off error")


# ---------------------------------------------------------------- expanders


class Expander(Model):
    id: str | None = Field(None, description=_I2C_ID)
    # schema.yaml called it "GPIO of I2C SDA", which it is not.
    address: int = Field(description="I2C address of the expander.")


class Mcp23017(Expander):
    init_sleep: StrPeriod = _interval("0s", "How long to sleep for MCP to initialize.")
    inverted: bool | None = Field(None, description="Active-LOW relay board (inverted logic)")


class Pcf8575(Expander):
    init_sleep: StrPeriod = _interval("0s", "How long to sleep for PCF to initialize.")


class Pca9685(Expander):
    init_sleep: StrPeriod = _interval("0s", "How long to sleep for PCA to initialize.")


# ----------------------------------------------------- virtual energy sensor


class VirtualEnergySensor(Model):
    # coerce: str turns a null into "None" in Cerberus, so it passes there.
    nullable = frozenset({"id"})

    id: Str | None = Field(None, description="Sensor ID")
    name: str = Field(description="Sensor Name")
    output_id: str = Field(description="Output ID")
    sensor_type: Literal["power", "water"] = Field(description="Sensor Type")
    power_usage: Annotated[Number, BeforeValidator(coerce("power_value_to_watts"))] | None = Field(
        None, description="Power Usage", json_schema_extra={"x-dependencies": {"sensor_type": ["power"]}}
    )
    flow_rate: Annotated[Number, BeforeValidator(coerce("volume_flow_rate_to_lph"))] | None = Field(
        None, description="Flow Rate", json_schema_extra={"x-dependencies": {"sensor_type": ["water"]}}
    )
    area: str | None = Field(None, description="Area")

    @model_validator(mode="after")
    def _reading_fits_the_type(self) -> VirtualEnergySensor:
        if self.power_usage is not None and self.sensor_type != "power":
            raise ValueError("power_usage: only allowed with sensor_type power")
        if self.flow_rate is not None and self.sensor_type != "water":
            raise ValueError("flow_rate: only allowed with sensor_type water")
        return self


SECTION_ADAPTERS = {
    "sensor": section(
        list[OneWireSensor],
        "Sensor list for Dallas 1-Wire temperature sensors (DS18B20, etc.). Detected via kernel w1 subsystem.",
    ),
    "adc": section(
        list[Adc],
        "https://boneio.eu/docs/black/configuration/adc \n GPIO ADC section of boneIO Black. It enables ADC "
        "sensors in HA. Don't let them hang without use.",
    ),
    "ina219": section(
        list[Ina],
        "https://boneio.eu/docs/black/configuration/ina219 \n INA219 Sensor list. All boneIO Black has one "
        "INA219 on board, which measures current, voltage and power of boneIO board.",
    ),
    "ina226": section(
        list[Ina],
        "INA226 Power monitor (boneIO Black v1.0). Measures board current, voltage and power. Replaces INA219 "
        "on v1.0 boards.",
    ),
    "lm75": section(
        list[Lm75],
        "https://boneio.eu/docs/black/configuration/lm75 \n LM75 Sensor list. All boneIO Black has one LM75 "
        "on board.",
    ),
    "mcp9808": section(
        list[Mcp9808],
        "https://boneio.eu/docs/black/configuration/mcp9808 \n MCP9808 Sensor list. Older boneIO Black had "
        "one MCP9808 instead of LM75on board, which measures temperature.",
    ),
    "modbus": section(
        Modbus,
        "https://boneio.eu/docs/black/configuration/modbus \n Modbus section of boneIO Black. It enables "
        "modbus support. You define on which uart it modbus defined. For new boneIO it is uart4. For old "
        "boneIO it is uart1.",
    ),
    "modbus_devices": section(
        list[ModbusDevice],
        "https://boneio.eu/docs/black/configuration/modbus-sensors \n List of modbus sensors. You can use "
        "predefined modbus sensors. It would fetch data from them and publish to mqtt.",
    ),
    "can": section(Can, "CAN bus configuration for inter-device communication via CANopen protocol."),
    "mcp23017": section(
        list[Mcp23017],
        "https://boneio.eu/docs/black/configuration/mcp23017 \n MCP23017 Pin config. All boneIO Black "
        "32X10/Cover/Cover Mix/24x16 has two MCP23017 on board. If you use new boneio: section, then you "
        "don't need to define this.",
    ),
    "pcf8575": section(
        list[Pcf8575], "https://boneio.eu/docs/black/configuration/pcf8575 \n PCF8575 Pin config. UNSTABLE."
    ),
    "pca9685": section(list[Pca9685], "https://boneio.eu/docs/black/configuration/pca9685 \n PCA9685 Pin config."),
    "virtual_energy_sensor": section(
        list[VirtualEnergySensor],
        "Virtual energy/water sensors linked to outputs. Creates power/energy or flow/volume sensors in Home "
        "Assistant.",
    ),
}
