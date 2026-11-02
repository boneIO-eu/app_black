"""The ``template`` section: thermostats, alarm panels, gates and irrigation.

Mirrors boneio/schema/schema.yaml for the section, where one flat list of
fields serves every platform and nothing ties a field to the platform it
belongs to. Kept that way here, so the model refuses what Cerberus refuses
and no more.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import Field

from boneio.core.config.models.base import Model, StrPeriod, section

Number = Union[float, int]
"""Cerberus' ``float`` takes an int too."""

Days = Literal["daily", "weekdays", "weekend", "mon", "tue", "wed", "thu", "fri", "sat", "sun"]


class Code(Model):
    name: str = Field(description="User name (used in logs to identify who disarmed).")
    code: Annotated[str, Field(pattern=r"^([0-9]+|[0-9a-fA-F]{64})$")] = Field(
        description="Numeric PIN code (digits only), or its SHA-256 hash."
    )


class AlarmOutput(Model):
    id: str = Field(description="Output relay ID.")
    type: Literal["siren", "notification", "light", "custom"] = Field(
        "siren", description="Output type (siren, notification, light, custom)."
    )


class Zone(Model):
    name: str | None = Field(None, description="Zone name.")
    inputs: list | None = Field(
        None, description="List of input IDs monitored in this zone (alarm_control_panel only)."
    )
    arm_modes: list | None = Field(None, description="Arm modes where this zone is active (alarm_control_panel only).")
    entry_delay: bool = Field(
        False, description="Whether this zone uses entry delay before triggering (alarm_control_panel only)."
    )
    id: str | None = Field(None, description="Id of I2C to use in pin config")
    valve_id: str | None = Field(None, description="Output ID of the valve relay to control (irrigation only).")
    run_duration: StrPeriod | None = Field(
        None, description="How long to run this zone (irrigation only). Example 5min."
    )
    enabled: bool = Field(True, description="Whether this zone is active (irrigation only).")
    run_every_n: Annotated[int, Field(ge=1)] = Field(
        1, description="Run zone every Nth scheduled cycle. 1 = every time (irrigation only)."
    )


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
    id: str | None = Field(None, description="Id of I2C to use in pin config")
    name: str | None = Field(None, description="Display name for the entity in Home Assistant.")
    platform: Literal["thermostat", "alarm_control_panel", "gate_cover", "irrigation"] = Field(
        description="Template platform type."
    )
    area: str | None = Field(None, description="Area/room for HA device grouping.")
    # thermostat
    sensor_id: str | None = Field(None, description="ID of the primary temperature sensor (thermostat only).")
    sensor_ids: list | None = Field(
        None, description="List of temperature sensor IDs. Average of available readings is used (thermostat only)."
    )
    output_id: str | None = Field(None, description="ID of the output (relay) to control (thermostat only).")
    mode: Literal["heat", "off"] = Field("heat", description="Initial climate mode (thermostat only).")
    target_temperature: Number = Field(21.0, description="Initial target temperature in °C (thermostat only).")
    hysteresis: Number = Field(0.5, description="Temperature hysteresis in °C (thermostat only).")
    min_temperature: Number = Field(5.0, description="Minimum settable temperature (thermostat only).")
    max_temperature: Number = Field(35.0, description="Maximum settable temperature (thermostat only).")
    # alarm_control_panel
    codes: list[Code] | None = Field(
        None, description="List of PIN codes with user names for arming/disarming the alarm."
    )
    code_arm_required: bool = Field(False, description="Whether code is required to arm the alarm.")
    arming_time: StrPeriod | None = Field(
        None, description="Time before alarm is armed after arming command. Example 30s."
    )
    delay_time: StrPeriod | None = Field(None, description="Entry delay time before alarm triggers. Example 30s.")
    trigger_time: StrPeriod | None = Field(None, description="Duration the alarm stays triggered. Example 5min.")
    outputs: list[AlarmOutput] | None = Field(None, description="List of outputs activated when alarm triggers.")
    zones: list[Zone] | None = Field(None, description="Zones — alarm zones or irrigation zones depending on platform.")
    # gate_cover
    control_mode: Literal["cycle", "separate", "open_only"] = Field(
        "cycle", description="Gate control mode (gate_cover only)."
    )
    device_class: Literal["gate", "garage_door", "barrier", "door"] = Field(
        "gate", description="HA device class for the cover entity (gate_cover only)."
    )
    pulse_output: str | None = Field(None, description="Relay output ID for pulse control (cycle/open_only modes).")
    open_output: str | None = Field(None, description="Relay output ID for opening (separate mode).")
    close_output: str | None = Field(None, description="Relay output ID for closing (separate mode).")
    stop_output: str | None = Field(None, description="Relay output ID for stop (separate mode, optional).")
    pulse_duration: StrPeriod | None = Field(None, description="How long the relay pulse lasts. Example 500ms.")
    closed_sensor: str | None = Field(None, description="Input ID of the closed contact sensor.")
    open_sensor: str | None = Field(None, description="Input ID of the open contact sensor.")
    # irrigation
    water_sources: list[WaterSource] | None = Field(
        None,
        description="Water sources — each defines outputs to activate and per-source pump timing (irrigation only).",
    )
    standby: bool = Field(
        False, description="When enabled, the controller will not start any valves (irrigation only)."
    )
    valve_open_delay: StrPeriod | None = Field(
        None, description="Delay between valve switching (irrigation only). Example 2s."
    )
    valve_overlap: StrPeriod | None = Field(
        None, description="Time that current and next valve run simultaneously (irrigation only)."
    )
    multiplier: Number = Field(1.0, description="Duration multiplier for all zone run times (irrigation only).")
    repeat: int = Field(0, description="Number of times to repeat the full cycle (irrigation only).")
    auto_advance: bool = Field(True, description="Auto-advance to next zone (irrigation only).")
    reverse: bool = Field(False, description="Run zones in reverse order (irrigation only).")
    pause_timeout: StrPeriod | None = Field(
        None,
        description="Auto-shutdown after being paused for this duration (irrigation only). Default 30min. Set 0 to "
        "disable.",
    )
    schedule: list[Run] | None = Field(None, description="Scheduled start times (irrigation only).")


SECTION_ADAPTERS = {
    "template": section(
        list[Template], "Template entities — composite virtual entities like thermostats and alarm panels."
    )
}
