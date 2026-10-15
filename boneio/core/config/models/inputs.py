"""The ``event`` and ``binary_sensor`` sections: inputs and the actions they run.

Mirrors boneio/schema/schema.yaml for these sections, with one difference
made on purpose: each action type is its own model, so a field an action
type needs is required (``output`` without ``boneio_output`` is an error).
In the Cerberus schema those are ``required_if`` rules, which only run for a
field that is present and so never catch a missing one.
"""

from __future__ import annotations

from typing import Annotated, Any, ClassVar, Literal, Union

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Discriminator,
    Field,
    Tag,
    TypeAdapter,
    model_validator,
)
from pydantic_core import PydanticUndefined

from boneio.core.config.yaml_util import CustomValidator, condition_shape_errors
from boneio.core.utils import TimePeriod
from boneio.exceptions import ConfigurationException

# ponytail: the coercions still live on the Cerberus validator; move them to
# plain functions when the last section leaves Cerberus.
_cerberus = CustomValidator({})


def _coerce(name: str):
    method = getattr(_cerberus, f"_normalize_coerce_{name}")

    def coerce(value: Any) -> Any:
        try:
            return method(value)
        except ConfigurationException as err:
            raise ValueError(str(err)) from None

    return coerce


_time_period = _coerce("positive_time_period")


def _str_time_period(value: Any) -> Any:
    """``coerce: [str, positive_time_period]``."""
    return value if isinstance(value, TimePeriod) else _time_period(str(value))


def _upper(value: Any) -> Any:
    return str(value).upper()


def _str_lower(value: Any) -> Any:
    return str(value).lower()


Period = Annotated[TimePeriod, BeforeValidator(_time_period)]
StrPeriod = Annotated[TimePeriod, BeforeValidator(_str_time_period)]
SunOffset = Annotated[float, BeforeValidator(_coerce("sun_offset")), Field(ge=-43200, le=43200)]
Elevation = Annotated[Union[float, int], Field(ge=-90, le=90)]

OutputCommand = Annotated[
    Literal["TOGGLE", "ON", "OFF", "BRIGHTNESS_UP", "BRIGHTNESS_DOWN", "BRIGHTNESS_UP_CYCLE",
            "BRIGHTNESS_DOWN_CYCLE", "SET_BRIGHTNESS", "CYCLE_COLOR", "CYCLE_PRESET"],
    BeforeValidator(_upper),
]
CoverCommand = Annotated[
    Literal["TOGGLE", "OPEN", "CLOSE", "STOP", "TOGGLE_OPEN", "TOGGLE_CLOSE", "SMART_TOGGLE",
            "SET_POSITION", "TILT", "TILT_OPEN", "TILT_CLOSE"],
    BeforeValidator(_upper),
]
BoneioInput = Annotated[
    Literal[tuple(f"in_{i:02d}" for i in range(1, 53))],  # type: ignore[valid-type]
    BeforeValidator(_str_lower),
]


class _Model(BaseModel):
    """Strict like the Cerberus schema: no "yes" for a boolean, no 5 for a string."""

    model_config = ConfigDict(extra="ignore", strict=True, arbitrary_types_allowed=True)

    #: Fields whose null a coercion turns into a value, so it is accepted.
    nullable: ClassVar[frozenset[str]] = frozenset()
    #: Fields refused when set to anything but the default Cerberus fills in.
    forbidden: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="before")
    @classmethod
    def _as_cerberus_reads_it(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        fields = cls.model_fields
        refused = []
        for key in [k for k, v in data.items() if v is None and k in fields]:
            # Cerberus fills a null with the field's default, as if it were
            # missing; with no default it is an error.
            if fields[key].default not in (None, PydanticUndefined) or key in cls.nullable:
                data = {k: v for k, v in data.items() if k != key}
            else:
                refused.append(key)
        if refused:
            raise ValueError(f"null value not allowed: {', '.join(sorted(refused))}")
        bad = sorted(
            k for k in cls.forbidden
            if k in data and not (k in _FILLED_DEFAULTS and str(data[k]).upper() == _FILLED_DEFAULTS[k])
        )
        if bad:
            raise ValueError(f"not allowed with action '{data.get('action')}': {', '.join(bad)}")
        return data


#: The defaults Cerberus fills into every action, whatever its type; a
#: forbidden field holding one of them is tolerated, as it is there.
_FILLED_DEFAULTS = {"action_cover": "TOGGLE", "action_output": "TOGGLE"}


# ----------------------------------------------------------------- conditions


class Condition(_Model):
    nullable = frozenset({"after_offset", "before_offset"})

    type: Literal["time", "date", "state", "sun"]
    after: str | None = None
    before: str | None = None
    after_offset: SunOffset | None = None
    before_offset: SunOffset | None = None
    phase: Literal["day", "civil_twilight", "nautical_twilight", "astronomical_twilight",
                   "night", "golden_hour", "blue_hour"] | None = None
    above: Elevation | None = None
    below: Elevation | None = None
    entity: Literal["binary_sensor", "cover", "output", "light", "virtual_switch",
                    "remote_input", "remote_output", "remote_cover"] | None = None
    entity_id: str | None = None
    state: Literal["is_on", "is_off", "is_open", "is_closed"] | None = None


def _condition_shape(condition: Condition) -> Condition:
    errors = condition_shape_errors(condition.model_dump(exclude_none=True))
    if errors:
        raise ValueError(" ".join(errors))
    return condition


ShapedCondition = Annotated[Condition, AfterValidator(_condition_shape)]


class Conditions(_Model):
    mode: Literal["and", "or"] = "and"
    list: list[ShapedCondition]


# -------------------------------------------------------------------- actions


class ActionData(_Model):
    position: Annotated[int, Field(ge=0, le=100)] | None = None
    tilt_position: int | None = None
    always_open_till: Annotated[int, Field(ge=0, le=100)] | None = None


class _Action(_Model):
    """Every field any action may carry; Cerberus checks each on every action.

    An action type below makes the fields it needs required and lists the
    ones it may not have.
    """

    boneio_output: str | None = None
    boneio_cover: str | None = None
    boneio_virtual_switch: str | None = None
    topic: str | None = None
    action_cover: CoverCommand = "TOGGLE"
    data: ActionData = ActionData()
    restore_tilt: bool = False
    action_output: OutputCommand = "TOGGLE"
    action_mqtt_msg: str | None = None
    boneio_id: str | None = None
    remote_device: str | None = None
    output_id: str | None = None
    cover_id: str | None = None
    brightness: Annotated[int, Field(ge=0, le=255)] | None = None
    brightness_step: Annotated[int, Field(ge=1, le=50)] | None = None
    color_temp: int | None = None
    rgb: list | None = None
    transition: Period | None = None
    colors: list | None = None
    presets: list | None = None
    repeat: bool = False
    repeat_interval: Period = Field("800ms", validate_default=True)
    probability: Annotated[Union[float, int], Field(ge=0, le=1)] | None = None
    delay: Period | None = None
    delay_cancel_on: list[Literal["pressed", "released", "single", "double", "long"]] | None = None
    condition: ShapedCondition | None = None
    conditions: Conditions | None = None


class OutputAction(_Action):
    forbidden = frozenset({"topic", "action_cover", "action_mqtt_msg", "boneio_id",
                           "remote_device", "output_id", "cover_id", "transition"})
    action: Literal["output"]
    boneio_output: str


class CoverAction(_Action):
    forbidden = frozenset({"topic", "action_output", "action_mqtt_msg", "boneio_id",
                           "remote_device", "output_id", "cover_id", "transition"})
    action: Literal["cover"]
    boneio_cover: str


class MqttAction(_Action):
    forbidden = frozenset({"action_cover", "action_output", "boneio_id", "remote_device",
                           "output_id", "cover_id", "transition"})
    action: Literal["mqtt"]
    topic: str
    action_mqtt_msg: str


class VirtualSwitchAction(_Action):
    action: Literal["virtual_switch"]
    boneio_virtual_switch: str


class OutputOverMqttAction(_Action):
    forbidden = frozenset({"action_cover", "remote_device", "output_id", "cover_id", "transition"})
    action: Literal["output_over_mqtt"]
    boneio_output: str
    action_mqtt_msg: str
    boneio_id: str


class CoverOverMqttAction(_Action):
    forbidden = frozenset({"topic", "action_output", "remote_device", "output_id",
                           "cover_id", "transition"})
    action: Literal["cover_over_mqtt"]
    boneio_cover: str
    action_mqtt_msg: str
    boneio_id: str


class RemoteOutputAction(_Action):
    forbidden = frozenset({"topic", "action_cover", "action_mqtt_msg", "boneio_id", "cover_id"})
    action: Literal["remote_output"]
    remote_device: str
    output_id: str


class RemoteCoverAction(_Action):
    forbidden = frozenset({"topic", "action_output", "action_mqtt_msg", "boneio_id",
                           "output_id", "transition"})
    action: Literal["remote_cover"]
    remote_device: str
    cover_id: str


_ACTIONS = {
    "output": OutputAction,
    "cover": CoverAction,
    "mqtt": MqttAction,
    "virtual_switch": VirtualSwitchAction,
    "output_over_mqtt": OutputOverMqttAction,
    "cover_over_mqtt": CoverOverMqttAction,
    "remote_output": RemoteOutputAction,
    "remote_cover": RemoteCoverAction,
}
ACTION_TAGS = frozenset(_ACTIONS)


def _action_kind(value: Any) -> Any:
    return value.get("action") if isinstance(value, dict) else getattr(value, "action", None)


def _lower_action(value: Any) -> Any:
    if isinstance(value, dict) and isinstance(value.get("action"), str):
        return {**value, "action": value["action"].lower()}
    return value


Action = Annotated[
    Union[tuple(Annotated[model, Tag(tag)] for tag, model in _ACTIONS.items())],  # type: ignore[valid-type]
    Discriminator(_action_kind),
    BeforeValidator(_lower_action),
]


# --------------------------------------------------------------------- inputs


class EventActions(_Model):
    single: list[Action] | None = None
    double: list[Action] | None = None
    triple: list[Action] | None = None
    long: list[Action] | None = None
    double_then_long: list[Action] | None = None
    single_then_long: list[Action] | None = None
    double_then_single: list[Action] | None = None


class MqttSequences(_Model):
    double_then_long: bool = False
    single_then_long: bool = False
    double_then_single: bool = False


class Event(_Model):
    name: str | None = None
    id: str | None = None
    pin: str | None = None
    bounce_time: StrPeriod = Field("30ms", validate_default=True)
    boneio_input: BoneioInput | None = None
    area: str | None = None
    show_in_ha: bool = True
    inverted: bool = False
    device_class: Literal["button", "doorbell", "motion"] = "button"
    double_click_duration: StrPeriod = Field("220ms", validate_default=True)
    long_press_duration: StrPeriod = Field("400ms", validate_default=True)
    sequence_window_duration: StrPeriod = Field("500ms", validate_default=True)
    actions: EventActions | None = None
    sequence_mode: Literal["immediate", "exclusive"] = "exclusive"
    enable_triple_click: bool = False
    long_press_mqtt_mode: Literal["single", "periodic"] = "single"
    max_long_press_duration: StrPeriod = Field("30s", validate_default=True)
    mqtt_sequences: MqttSequences | None = None

    @model_validator(mode="before")
    @classmethod
    def _has_id_or_input(cls, data: Any) -> Any:
        if isinstance(data, dict) and "id" not in data and "boneio_input" not in data:
            raise ValueError("must have either 'id' or 'boneio_input' defined")
        return data


class BinarySensorActions(_Model):
    pressed: list[Action] | None = None
    released: list[Action] | None = None


class BinarySensor(_Model):
    id: str | None = None
    pin: str | None = None
    bounce_time: StrPeriod = Field("120ms", validate_default=True)
    boneio_input: BoneioInput | None = None
    area: str | None = None
    show_in_ha: bool = True
    inverted: bool = False
    initial_send: bool = False
    device_class: Literal["battery", "battery_charging", "carbon_monoxide", "cold",
                          "connectivity", "door", "garage_door", "gas", "heat", "light", "lock",
                          "moisture", "motion", "moving", "occupancy", "opening", "plug", "power",
                          "presence", "problem", "running", "safety", "smoke", "sound", "tamper",
                          "vibration", "window"] | None = None
    actions: BinarySensorActions | None = None


SECTION_ADAPTERS = {
    "event": TypeAdapter(list[Event]),
    "binary_sensor": TypeAdapter(list[BinarySensor]),
}
