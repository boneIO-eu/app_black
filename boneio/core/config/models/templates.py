"""The ``template`` section: thermostats, alarm panels, gates and irrigation.

Mirrors boneio/schema/schema.yaml for the section, where one flat list of
fields serves every platform and nothing ties a field to the platform it
belongs to. Kept that way here, so the model refuses what Cerberus refuses
and no more.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import Field, TypeAdapter

from boneio.core.config.models.base import Model, StrPeriod

Number = Union[float, int]
"""Cerberus' ``float`` takes an int too."""

Days = Literal["daily", "weekdays", "weekend", "mon", "tue", "wed", "thu", "fri", "sat", "sun"]


class Code(Model):
    name: str
    code: Annotated[str, Field(pattern=r"^([0-9]+|[0-9a-fA-F]{64})$")]


class AlarmOutput(Model):
    id: str
    type: Literal["siren", "notification", "light", "custom"] = "siren"


class Zone(Model):
    name: str | None = None
    inputs: list | None = None
    arm_modes: list | None = None
    entry_delay: bool = False
    id: str | None = None
    valve_id: str | None = None
    run_duration: StrPeriod | None = None
    enabled: bool = True
    run_every_n: Annotated[int, Field(ge=1)] = 1


class WaterSource(Model):
    id: str | None = Field(None, description="Id of I2C to use in pin config")
    name: str | None = Field(None, description="Display name for the water source.")
    outputs: list = Field(description="Output IDs to activate when this water source is used.")
    output_start_delay: StrPeriod | None = Field(
        None, description="Delay between activating each output (sequential ON, in order)."
    )
    output_stop_delay: StrPeriod | None = Field(
        None, description="Delay between deactivating each output (sequential OFF, reverse order)."
    )
    pump_switch_off_during_valve_open_delay: bool = Field(
        False, description="Turn off source outputs during valve_open_delay interval."
    )
    pump_start_pump_delay: StrPeriod | None = Field(None, description="Delay from valve open to source activation.")
    pump_start_valve_delay: StrPeriod | None = Field(None, description="Delay from source activation to valve open.")
    pump_stop_pump_delay: StrPeriod | None = Field(None, description="Delay from valve close to source deactivation.")
    pump_stop_valve_delay: StrPeriod | None = Field(None, description="Delay from source deactivation to valve close.")


class Run(Model):
    time: str = Field(description="Start time in HH:MM format. Example: 06:00.")
    days: Days = Field("daily", description="Days when this schedule is active.")


class Template(Model):
    id: str | None = None
    name: str | None = None
    platform: Literal["thermostat", "alarm_control_panel", "gate_cover", "irrigation"]
    area: str | None = None
    # thermostat
    sensor_id: str | None = None
    sensor_ids: list | None = None
    output_id: str | None = None
    mode: Literal["heat", "off"] = "heat"
    target_temperature: Number = 21.0
    hysteresis: Number = 0.5
    min_temperature: Number = 5.0
    max_temperature: Number = 35.0
    # alarm_control_panel
    codes: list[Code] | None = None
    code_arm_required: bool = False
    arming_time: StrPeriod | None = None
    delay_time: StrPeriod | None = None
    trigger_time: StrPeriod | None = None
    outputs: list[AlarmOutput] | None = None
    zones: list[Zone] | None = None
    # gate_cover
    control_mode: Literal["cycle", "separate", "open_only"] = "cycle"
    device_class: Literal["gate", "garage_door", "barrier", "door"] = "gate"
    pulse_output: str | None = None
    open_output: str | None = None
    close_output: str | None = None
    stop_output: str | None = None
    pulse_duration: StrPeriod | None = None
    closed_sensor: str | None = None
    open_sensor: str | None = None
    # irrigation
    water_sources: list[WaterSource] | None = None
    standby: bool = False
    valve_open_delay: StrPeriod | None = None
    valve_overlap: StrPeriod | None = None
    multiplier: Number = 1.0
    repeat: int = 0
    auto_advance: bool = True
    reverse: bool = False
    pause_timeout: StrPeriod | None = None
    schedule: list[Run] | None = None


SECTION_ADAPTERS = {"template": TypeAdapter(list[Template])}
