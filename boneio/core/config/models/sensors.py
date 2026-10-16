"""Sensors and expanders: 1-Wire, ADC, INA219/226, LM75, MCP9808, Modbus, CAN,
the MCP23017/PCF8575/PCA9685 expanders and virtual energy sensors.

Mirrors boneio/schema/schema.yaml for these sections. One rule is enforced
here and not at start-up: ``update_interval``'s ``min: 1s`` on Modbus devices.
Cerberus compares a TimePeriod with a string, gets TypeError and lets it
pass, so a saved config may still hold less; a save cannot add it.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import AfterValidator, BeforeValidator, Field, TypeAdapter, model_validator

from boneio.core.config.models.base import Model, Str, StrPeriod, coerce, str_lower
from boneio.core.config.yaml_util import _get_schema

Number = Union[float, int]
Address = Union[str, int]
Filter = dict[
    Literal["offset", "round", "multiply", "filter_out", "filter_out_greater", "filter_out_lower"],
    Any,
]


def _interval(default: str):
    return Field(default, validate_default=True)


# ------------------------------------------------------------------ sensors


class OneWireSensor(Model):
    id: str | None = None
    name: str | None = None
    area: str | None = None
    address: str
    show_in_ha: bool = True
    filters: list[Filter] = Field(default_factory=lambda: [{"round": 2}])
    update_interval: StrPeriod = _interval("60s")
    unit_of_measurement: Literal["°C", "°F"] = "°C"


class Adc(Model):
    name: str | None = None
    id: str | None = None
    pin: Literal["P9_33", "P9_35", "P9_36", "P9_37", "P9_38", "P9_39", "P9_40"]
    area: str | None = None
    update_interval: StrPeriod = _interval("60s")
    show_in_ha: bool = True
    filters: list[Filter] = Field(default_factory=lambda: [{"multiply": 1.8}, {"round": 2}])


class InaSensor(Model):
    id: str | None = None
    device_class: Literal["current", "power", "voltage"] | None = None
    filters: list[Filter] = Field(default_factory=lambda: [{"round": 2}])


def _ina_sensors() -> list[InaSensor]:
    return [
        InaSensor(id="Board Current", device_class="current"),
        InaSensor(id="Board Power", device_class="power"),
        InaSensor(id="Board Voltage", device_class="voltage"),
    ]


class Ina(Model):
    """INA219 and INA226 share their fields."""

    id: str | None = None
    address: Address = 64
    sensors: list[InaSensor] = Field(default_factory=_ina_sensors)
    update_interval: StrPeriod = _interval("60s")


class Lm75(Model):
    id: str | None = None
    address: int = 72
    update_interval: StrPeriod = _interval("60s")
    filters: list[Filter] = Field(default_factory=lambda: [{"round": 2}])
    unit_of_measurement: Literal["°C", "°F"] = "°C"


class Mcp9808(Lm75):
    address: Address = 24


# ------------------------------------------------------------------- modbus


class Modbus(Model):
    uart: Literal["uart1", "uart2", "uart3", "uart4", "uart5"]
    baudrate: int = 9600
    stopbits: Literal[1, 2] = 1
    bytesize: int = 8
    parity: Literal["N", "E", "O"] = "N"
    timeout: StrPeriod = _interval("1500ms")
    inter_device_delay: StrPeriod = _interval("5ms")


def _known_model(value: str) -> str:
    # The schema's list is filled from the device files when it is loaded.
    allowed = _get_schema()["modbus_devices"]["schema"]["schema"]["model"]["allowed"]
    if value not in allowed:
        raise ValueError(f"unallowed value {value}")
    return value


class SensorsFilters(Model):
    temperature: list[Filter] = Field(default_factory=lambda: [{"round": 2}])
    humidity: list[Filter] = Field(default_factory=lambda: [{"round": 2}])


Length = Annotated[Number, BeforeValidator(coerce("length_to_meters"))]


class TankData(Model):
    width: Length | None = None
    length: Length | None = None


def _at_least_a_second(value):
    if value.total_in_seconds < 1:
        raise ValueError("at least 1s: a Modbus device polled faster crowds out the others on the bus")
    return value


class ModbusDevice(Model):
    name: str | None = None
    area: str | None = None
    id: Annotated[str, BeforeValidator(str), Field(pattern=r"^[a-z0-9_]+$")] | None = None
    address: Address
    model: Annotated[str, BeforeValidator(str_lower), AfterValidator(_known_model)]
    update_interval: Annotated[StrPeriod, AfterValidator(_at_least_a_second)] = _interval("30s")
    entity_labels: dict[str, str] | None = None
    sensors_filters: SensorsFilters | None = None
    data: TankData | None = None

    @model_validator(mode="after")
    def _blocks_fit_the_model(self) -> ModbusDevice:
        if self.sensors_filters is not None and self.model != "cwt":
            raise ValueError("sensors_filters: only allowed with model cwt")
        if self.data is not None and self.model != "liquid-sensor":
            raise ValueError("data: only allowed with model liquid-sensor")
        return self


# ---------------------------------------------------------------------- can


class Can(Model):
    enabled: bool = False
    channel: str = "can0"
    bitrate: Literal[10000, 20000, 50000, 100000, 125000, 250000, 500000, 1000000] = 125000
    node_id: Address = "auto"
    mode: Literal["master", "slave"] = "master"
    auto_setup: bool = True
    restart_on_error: bool = True


# ---------------------------------------------------------------- expanders


class Expander(Model):
    id: str | None = None
    address: int
    init_sleep: StrPeriod = _interval("0s")


class Mcp23017(Expander):
    inverted: bool | None = None


# ----------------------------------------------------- virtual energy sensor


class VirtualEnergySensor(Model):
    # coerce: str turns a null into "None" in Cerberus, so it passes there.
    nullable = frozenset({"id"})

    id: Str | None = None
    name: str
    output_id: str
    sensor_type: Literal["power", "water"]
    power_usage: Annotated[Number, BeforeValidator(coerce("power_value_to_watts"))] | None = None
    flow_rate: Annotated[Number, BeforeValidator(coerce("volume_flow_rate_to_lph"))] | None = None
    area: str | None = None

    @model_validator(mode="after")
    def _reading_fits_the_type(self) -> VirtualEnergySensor:
        if self.power_usage is not None and self.sensor_type != "power":
            raise ValueError("power_usage: only allowed with sensor_type power")
        if self.flow_rate is not None and self.sensor_type != "water":
            raise ValueError("flow_rate: only allowed with sensor_type water")
        return self


SECTION_ADAPTERS = {
    "sensor": TypeAdapter(list[OneWireSensor]),
    "adc": TypeAdapter(list[Adc]),
    "ina219": TypeAdapter(list[Ina]),
    "ina226": TypeAdapter(list[Ina]),
    "lm75": TypeAdapter(list[Lm75]),
    "mcp9808": TypeAdapter(list[Mcp9808]),
    "modbus": TypeAdapter(Modbus),
    "modbus_devices": TypeAdapter(list[ModbusDevice]),
    "can": TypeAdapter(Can),
    "mcp23017": TypeAdapter(list[Mcp23017]),
    "pcf8575": TypeAdapter(list[Expander]),
    "pca9685": TypeAdapter(list[Expander]),
    "virtual_energy_sensor": TypeAdapter(list[VirtualEnergySensor]),
}
