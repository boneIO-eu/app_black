"""Pydantic model of a Modbus device definition (boneio/modbus/devices/*/*.json)."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Discriminator, Tag, model_validator

from boneio.modbus.heat_pump import REQUIRED_ROLES, ROLE_KINDS

DEVICES_DIR = Path(__file__).parent / "devices"

ValueType = Literal["FP32", "U_WORD", "S_WORD", "U_DWORD", "S_DWORD"]


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _RegisterBase(_Frozen):
    name: str
    address: int
    value_type: ValueType
    unit_of_measurement: str | None = None
    state_class: str | None = None
    device_class: str | None = None
    entity_category: str | None = None
    filters: list[dict[str, Any]] = []
    ha_filter: str | None = "round(2)"
    hidden: bool = False
    confirm: bool = False

    @property
    def decoded_name(self) -> str:
        return self.name.replace(" ", "").lower()


class _Writeable(_RegisterBase):
    write_address: int | None = None
    write_filters: list[dict[str, Any]] = []
    step: float | None = None
    min: float | None = None
    max: float | None = None


class _Binary(_RegisterBase):
    payload_on: str = "ON"
    payload_off: str = "OFF"


class SensorRegister(_RegisterBase):
    entity_type: Literal["sensor"] = "sensor"


class TextSensorRegister(_RegisterBase):
    entity_type: Literal["text_sensor"] = "text_sensor"
    x_mapping: dict[str, str] = {}


class BinarySensorRegister(_Binary):
    entity_type: Literal["binary_sensor"] = "binary_sensor"


class WriteableSensorRegister(_Writeable):
    entity_type: Literal["writeable_sensor"] = "writeable_sensor"


class WriteableDiscreteRegister(_Writeable):
    entity_type: Literal["writeable_sensor_discrete"] = "writeable_sensor_discrete"
    x_mapping: dict[str, str] = {}


class WriteableBinaryRegister(_Writeable, _Binary):
    entity_type: Literal["writeable_binary_sensor_discrete"] = (
        "writeable_binary_sensor_discrete"
    )


class ButtonRegister(_RegisterBase):
    entity_type: Literal["button"] = "button"
    write_address: int | None = None
    write_value: int = 1


def _entity_type(v: Any) -> str:
    # A missing entity_type means "sensor".
    if isinstance(v, dict):
        return v.get("entity_type", "sensor")
    return getattr(v, "entity_type", "sensor")


Register = Annotated[
    Union[
        Annotated[SensorRegister, Tag("sensor")],
        Annotated[TextSensorRegister, Tag("text_sensor")],
        Annotated[BinarySensorRegister, Tag("binary_sensor")],
        Annotated[WriteableSensorRegister, Tag("writeable_sensor")],
        Annotated[WriteableDiscreteRegister, Tag("writeable_sensor_discrete")],
        Annotated[WriteableBinaryRegister, Tag("writeable_binary_sensor_discrete")],
        Annotated[ButtonRegister, Tag("button")],
    ],
    Discriminator(_entity_type),
]


class RegisterBlock(_Frozen):
    base: int
    length: int
    register_type: Literal["input", "holding", "coil", "discrete_input"] = "input"
    update_every_n: int | None = None
    optional: bool = False
    registers: list[Register]


class _AdditionalBase(_Frozen):
    name: str
    source: str | list[str]
    unit_of_measurement: str | None = None
    state_class: str | None = None
    device_class: str | None = None
    entity_category: str | None = None


class AdditionalSensor(_AdditionalBase):
    entity_type: Literal["sensor"] = "sensor"
    operation: str | None = None
    formula: str | None = None
    config_keys: list[str] | None = None


class AdditionalTextSensor(_AdditionalBase):
    entity_type: Literal["text_sensor"] = "text_sensor"
    x_mapping: dict[str, str] = {}


class AdditionalSelect(_AdditionalBase):
    entity_type: Literal["select"] = "select"
    x_mapping: dict[str, str] = {}


class AdditionalSwitch(_AdditionalBase):
    entity_type: Literal["switch"] = "switch"
    x_mapping: dict[str, str] = {}
    payload_on: str = "ON"
    payload_off: str = "OFF"


class AdditionalNumber(_AdditionalBase):
    entity_type: Literal["number"] = "number"
    x_mapping: dict[str, str] = {}
    payload_on: str = "ON"
    payload_off: str = "OFF"


AdditionalEntity = Annotated[
    Union[
        Annotated[AdditionalSensor, Tag("sensor")],
        Annotated[AdditionalTextSensor, Tag("text_sensor")],
        Annotated[AdditionalSelect, Tag("select")],
        Annotated[AdditionalSwitch, Tag("switch")],
        Annotated[AdditionalNumber, Tag("number")],
    ],
    Discriminator(_entity_type),
]


class SetBaudrate(_Frozen):
    address: int
    possible_baudrates: dict[str, int]


class SetBase(_Frozen):
    set_address_address: int
    set_baudrate: SetBaudrate | None = None


class HeatPumpSpec(_Frozen):
    scheme: Literal["lg_therma", "phnix"]
    roles: dict[str, str | list[str]]


_NUMERIC = {"sensor", "writeable_sensor", "writeable_sensor_discrete"}
_ROLE_REGISTER_TYPES = {
    "number": _NUMERIC,
    "number_or_text": _NUMERIC | {"text_sensor"},
    "binary": {"binary_sensor"},
}


class DeviceDefinition(_Frozen):
    model: str
    manufacturer: str
    description: str
    category: str
    default_address: int
    default_update_interval: str
    registers_base: list[RegisterBlock]
    additional_entities: list[AdditionalEntity] = []
    set_base: SetBase | None = None
    heat_pump: HeatPumpSpec | None = None

    @model_validator(mode="after")
    def _heat_pump_roles_fit_entities(self) -> DeviceDefinition:
        """Every role names a known role and an entity of the kind the scheme reads."""
        hp = self.heat_pump
        if hp is None:
            return self
        missing = REQUIRED_ROLES[hp.scheme] - hp.roles.keys()
        if missing:
            raise ValueError(f"heat_pump is missing roles: {sorted(missing)}")
        registers = {
            r.decoded_name: r.entity_type for b in self.registers_base for r in b.registers
        }
        switches = {
            a.name.replace(" ", "").lower()
            for a in self.additional_entities
            if a.entity_type == "switch"
        }
        for role, ref in hp.roles.items():
            kind = ROLE_KINDS.get(role)
            if kind is None:
                raise ValueError(f"heat_pump has unknown role {role!r}")
            for name in [ref] if isinstance(ref, str) else ref:
                key = name.replace(" ", "").lower()
                if kind == "switch":
                    ok = key in switches
                else:
                    ok = registers.get(key) in _ROLE_REGISTER_TYPES[kind]
                if not ok:
                    raise ValueError(f"heat_pump role {role!r}: {name!r} is not a {kind} entity")
        return self


def _files() -> dict[str, Path]:
    return {p.stem: p for p in sorted(DEVICES_DIR.rglob("*.json"))}


def device_models() -> list[str]:
    return list(_files())


@cache
def load_definition(model: str) -> DeviceDefinition:
    path = _files().get(model)
    if path is None:
        raise FileNotFoundError(f"No device definition for model {model!r}")
    return DeviceDefinition.model_validate(json.loads(path.read_text()))
