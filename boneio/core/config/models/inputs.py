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
    AfterValidator, BeforeValidator, ConfigDict, Discriminator, Field, Tag, TypeAdapter, model_validator,
)

from boneio.core.config.models.base import ANY_CASE, Model, Period, Str, StrPeriod, coerce, str_lower
from boneio.core.config.yaml_util import condition_shape_errors


def _upper(value: Any) -> Any:
    return str(value).upper()


SunOffset = Annotated[float, BeforeValidator(coerce("sun_offset")), Field(ge=-43200, le=43200)]
Elevation = Annotated[Union[float, int], Field(ge=-90, le=90)]

OutputCommand = Annotated[
    Literal["TOGGLE", "ON", "OFF", "BRIGHTNESS_UP", "BRIGHTNESS_DOWN", "BRIGHTNESS_UP_CYCLE",
            "BRIGHTNESS_DOWN_CYCLE", "SET_BRIGHTNESS", "CYCLE_COLOR", "CYCLE_PRESET"],
    BeforeValidator(_upper),
    Field(json_schema_extra=ANY_CASE),
]
CoverCommand = Annotated[
    Literal["TOGGLE", "OPEN", "CLOSE", "STOP", "TOGGLE_OPEN", "TOGGLE_CLOSE", "SMART_TOGGLE",
            "SET_POSITION", "TILT", "TILT_OPEN", "TILT_CLOSE"],
    BeforeValidator(_upper),
    Field(json_schema_extra=ANY_CASE),
]
BoneioInput = Annotated[
    Literal[tuple(f"in_{i:02d}" for i in range(1, 53))],  # type: ignore[valid-type]
    BeforeValidator(str_lower),
    Field(json_schema_extra=ANY_CASE),
]


#: The defaults Cerberus fills into every action, whatever its type; a
#: forbidden field holding one of them is tolerated, as it is there.
_FILLED_DEFAULTS = {"action_cover": "TOGGLE", "action_output": "TOGGLE"}


# ----------------------------------------------------------------- conditions


class Condition(Model):
    nullable = frozenset({"after_offset", "before_offset"})

    type: Literal["time", "date", "state", "sun"] = Field(description="Condition type")
    after: str | None = Field(None, description="After (start of range)")
    before: str | None = Field(None, description="Before (end of range)")
    after_offset: SunOffset | None = Field(None, description="Offset from the 'after' anchor (sun only)")
    before_offset: SunOffset | None = Field(None, description="Offset from the 'before' anchor (sun only)")
    phase: Literal["day", "civil_twilight", "nautical_twilight", "astronomical_twilight",
                   "night", "golden_hour", "blue_hour"] | None = Field(None, description="Sun phase (sun only)")
    above: Elevation | None = Field(None, description="Sun elevation above (degrees, sun only)")
    below: Elevation | None = Field(None, description="Sun elevation below (degrees, sun only)")
    entity: Literal["binary_sensor", "cover", "output", "light", "virtual_switch",
                    "remote_input", "remote_output", "remote_cover"] | None = Field(
        None, description="Entity type (for state condition)",
    )
    entity_id: str | None = Field(None, description="Entity ID (for state condition)")
    state: Literal["is_on", "is_off", "is_open", "is_closed"] | None = Field(
        None, description="Expected state (for state condition)",
    )


def _condition_shape(condition: Condition) -> Condition:
    errors = condition_shape_errors(condition.model_dump(exclude_none=True))
    if errors:
        raise ValueError(" ".join(errors))
    return condition


ShapedCondition = Annotated[Condition, AfterValidator(_condition_shape)]


class Conditions(Model):
    mode: Literal["and", "or"] = Field("and", description="Condition mode")
    # Annotated, not "= Field(...)": a value here would shadow list in the annotation.
    list: Annotated[list[ShapedCondition], Field(description="List of conditions")]


# -------------------------------------------------------------------- actions


class ActionData(Model):
    position: Annotated[int, Field(ge=0, le=100)] | None = Field(
        None, description="Position to set cover to for SET_POSITION. 0 means closed, 100 means opened.",
    )
    tilt_position: int | None = Field(
        None, description="Tilt position to set cover to. 0 means closed, 100 means opened.",
    )
    always_open_till: Annotated[int, Field(ge=0, le=100)] | None = Field(
        None, description="Smart toggle threshold (0-100%).",
    )


def _action_schema(schema: dict, cls: type) -> None:
    """The schema of an action type: only the fields that type may carry.

    A field the type redefines (to make it required) is described once, on
    _Action.
    """
    for key in cls.forbidden:  # type: ignore[attr-defined]
        schema["properties"].pop(key, None)
    # Another type's field is refused, so the editor flags it too; not the
    # TOGGLE start-up fills in, which an action may carry whatever its type.
    refused = sorted(cls.forbidden - _FILLED_DEFAULTS.keys())  # type: ignore[attr-defined]
    if refused:
        schema["propertyNames"] = {"not": {"enum": refused}}
    schema["properties"]["action"].update(ANY_CASE)  # lowered by _lower_action
    for key, prop in schema["properties"].items():
        base = _Action.model_fields.get(key)
        if base is not None and base.description:
            prop.setdefault("description", base.description)


class _Action(Model):
    """Every field any action may carry; Cerberus checks each on every action.

    An action type below makes the fields it needs required and lists the
    ones it may not have.
    """

    #: Fields refused when set to anything but the default Cerberus fills in.
    forbidden: ClassVar[frozenset[str]] = frozenset()

    model_config = ConfigDict(**Model.model_config, json_schema_extra=_action_schema)

    @classmethod
    def _refuse_forbidden(cls, data: dict) -> dict:
        bad = sorted(
            k for k in cls.forbidden
            if k in data and not (k in _FILLED_DEFAULTS and str(data[k]).upper() == _FILLED_DEFAULTS[k])
        )
        if bad:
            raise ValueError(f"not allowed with action '{data.get('action')}': {', '.join(bad)}")
        return data

    boneio_output: str | None = Field(None, description="Output ID")
    boneio_cover: str | None = Field(None, description="Cover ID")
    boneio_virtual_switch: str | None = Field(None, description="Virtual switch ID")
    topic: str | None = Field(None, description="If mqtt action then topic to send")
    action_cover: CoverCommand = Field("TOGGLE", description="If cover action chosen then what action to perform.")
    data: ActionData = Field(
        ActionData(), description="Extra data for cover actions (position, tilt, smart toggle threshold).",
    )
    restore_tilt: bool = Field(False, description="Restore Tilt After Movement")
    action_output: OutputCommand = Field("TOGGLE", description="If output action chosen then what action to perform.")
    action_mqtt_msg: str | None = Field(None, description="What message to send to mqtt topic")
    boneio_id: str | None = Field(
        None,
        description="boneIO id to perform action on. Use only with action type `output_over_mqtt` or "
        "`cover_over_mqtt`.",
    )
    remote_device: str | None = Field(None, description="Remote Device ID")
    output_id: str | None = Field(None, description="Remote Output ID")
    cover_id: str | None = Field(None, description="Remote Cover ID")
    brightness: Annotated[int, Field(ge=0, le=255)] | None = Field(None, description="Brightness (0-255)")
    brightness_step: Annotated[int, Field(ge=1, le=50)] | None = Field(None, description="Brightness step (1-50%)")
    color_temp: int | None = Field(None, description="Color Temperature (mireds)")
    rgb: list | None = Field(None, description="RGB Color [R, G, B]")
    transition: Period | None = Field(None, description="Transition Time")
    colors: list | None = Field(None, description="Color List for CYCLE_COLOR")
    presets: list | None = Field(None, description="Preset/Effect List for CYCLE_PRESET")
    repeat: bool = Field(False, description="Repeat on Hold")
    repeat_interval: Period = Field("800ms", validate_default=True, description="Repeat Interval")
    probability: Annotated[Union[float, int], Field(ge=0, le=1)] | None = Field(None, description="Chance of running")
    delay: Period | None = Field(None, description="Delay Before Execution")
    delay_cancel_on: list[Literal["pressed", "released", "single", "double", "long"]] | None = Field(
        None, description="Cancel Delay On Events",
    )
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
#: Union tags in error locations, which are not fields (see models._path).
UNION_TAGS = frozenset(_ACTIONS)


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


class EventActions(Model):
    single: list[Action] | None = None
    double: list[Action] | None = None
    triple: list[Action] | None = None
    long: list[Action] | None = None
    double_then_long: list[Action] | None = None
    single_then_long: list[Action] | None = None
    double_then_single: list[Action] | None = None


class MqttSequences(Model):
    double_then_long: bool = Field(False, description="Send double_then_long to MQTT")
    single_then_long: bool = Field(False, description="Send single_then_long to MQTT")
    double_then_single: bool = Field(False, description="Send double_then_single to MQTT")


class Event(Model):
    name: str | None = Field(None, description="Name to use in HA.")
    id: str | None = Field(None, description="Id to use for MQTT topic. Default to boneio_input or pin number.")
    pin: str | None = Field(None, description="PIN to use.")
    bounce_time: StrPeriod = Field(
        "30ms", validate_default=True, description="Bounce time for GPIO in miliseconds. Only for advanced usage.",
    )
    boneio_input: BoneioInput | None = Field(None, description="Reference to predefined input configuration")
    area: str | None = Field(None, description="Area/Room")
    show_in_ha: bool = Field(True, description="If you want you can disable discovering this input in HA.")
    inverted: bool = Field(False, description="Check if sensor type is inverted. Only aplicable for sensor kind.")
    device_class: Literal["button", "doorbell", "motion"] = Field("button", description="Device class to use in HA")
    double_click_duration: StrPeriod = Field("220ms", validate_default=True, description="Double Click Duration")
    long_press_duration: StrPeriod = Field("400ms", validate_default=True, description="Long Press Duration")
    sequence_window_duration: StrPeriod = Field("500ms", validate_default=True, description="Sequence Window Duration")
    actions: EventActions | None = None
    sequence_mode: Literal["immediate", "exclusive"] = Field("exclusive", description="Sequence Mode")
    enable_triple_click: bool = Field(False, description="Enable Triple Click")
    long_press_mqtt_mode: Literal["single", "periodic"] = Field("single", description="Long Press MQTT Mode")
    max_long_press_duration: StrPeriod = Field("30s", validate_default=True, description="Max Long Press Duration")
    mqtt_sequences: MqttSequences | None = Field(None, description="MQTT Sequences")

    @model_validator(mode="before")
    @classmethod
    def _has_id_or_input(cls, data: Any) -> Any:
        if isinstance(data, dict) and "id" not in data and "boneio_input" not in data:
            raise ValueError("must have either 'id' or 'boneio_input' defined")
        return data


class BinarySensorActions(Model):
    pressed: list[Action] | None = None
    released: list[Action] | None = None


class BinarySensor(Model):
    # Not in the Cerberus schema, yet kept by it and read at start-up as the
    # entity's name in HA; the factory configs name every input.
    name: Str | None = Field(None, description="Name to use in HA.")
    id: str | None = Field(None, description="Id to use in HA if needed. Default to pin number.")
    pin: str | None = Field(None, description="PIN to use.")
    bounce_time: StrPeriod = Field(
        "120ms", validate_default=True, description="Bounce time for GPIO in miliseconds. Only for advanced usage.",
    )
    boneio_input: BoneioInput | None = Field(None, description="Reference to predefined input configuration")
    area: str | None = Field(None, description="Area/Room")
    show_in_ha: bool = Field(True, description="If you want you can disable discovering this input in HA.")
    inverted: bool = Field(False, description="Check if sensor type is inverted. Only aplicable for sensor kind.")
    initial_send: bool = Field(
        False,
        description="If set to true, then on startup of application initial status of the binary sensor will be "
        "send to MQTT.",
    )
    device_class: Literal["battery", "battery_charging", "carbon_monoxide", "cold",
                          "connectivity", "door", "garage_door", "gas", "heat", "light", "lock",
                          "moisture", "motion", "moving", "occupancy", "opening", "plug", "power",
                          "presence", "problem", "running", "safety", "smoke", "sound", "tamper",
                          "vibration", "window"] | None = Field(None, description="Device class to use in HA")
    actions: BinarySensorActions | None = None


SECTION_ADAPTERS = {
    "event": TypeAdapter(Annotated[list[Event], Field(description=(
        "https://boneio.eu/docs/black/configuration/event \n GPIO event entity section of boneIO Black. "
        "It enables event entities in HA. It detects single, double and long click. It can run action based "
        "on states. It always send message to MQTT broker of invoked state."
    ))]),
    "binary_sensor": TypeAdapter(Annotated[list[BinarySensor], Field(description=(
        "https://boneio.eu/docs/black/configuration/binary \n GPIO binary section of boneIO Black. It enables "
        "binary sensors in HA. It detects press and release states. It can run action based on states. It "
        "always send message to MQTT broker of invoked state."
    ))]),
}
