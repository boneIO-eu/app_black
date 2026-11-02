"""The ``remote_devices`` section: other controllers, ESPHome and WLED devices.

Mirrors boneio/schema/schema.yaml for the section. A protocol's block
(``mqtt``, ``esphome_api``, ``wled``) is only allowed on a device of that
protocol, as the Cerberus ``dependencies`` rule has it.
"""

from __future__ import annotations

from typing import Literal, Union

from pydantic import Field, model_validator

from boneio.core.config.models.base import Model, Str, section

Number = Union[float, int]


# Each kind of entity repeats id and name only to describe them as its own.
class Entity(Model):
    id: str = Field(description="Output ID")
    name: str | None = Field(None, description="Output Name (for UI)")


class MqttCover(Entity):
    id: str = Field(description="Cover ID")
    name: str | None = Field(None, description="Cover Name (for UI)")


class MqttBlock(Model):
    outputs: list[Entity] | None = Field(None, description="Available Outputs")
    covers: list[MqttCover] | None = Field(None, description="Available Covers")


class EspSwitch(Entity):
    id: str = Field(description="Switch ID (object_id)")
    name: str | None = Field(None, description="Switch Name")
    key: int | None = Field(None, description="Entity Key (from discovery)")


class EspLight(EspSwitch):
    id: str = Field(description="Light ID (object_id)")
    name: str | None = Field(None, description="Light Name")
    supports_brightness: bool = Field(False, description="Supports Brightness")
    supports_color_temp: bool = Field(False, description="Supports Color Temperature")
    supports_rgb: bool = Field(False, description="Supports RGB Color")
    supports_rgbw: bool = Field(False, description="Supports RGBW Color")
    min_mireds: Number | None = Field(None, description="Min Color Temp (mireds)")
    max_mireds: Number | None = Field(None, description="Max Color Temp (mireds)")


class EspCover(EspSwitch):
    id: str = Field(description="Cover ID (object_id)")
    name: str | None = Field(None, description="Cover Name")
    supports_position: bool = Field(False, description="Supports Position")
    supports_tilt: bool | None = Field(None, description="Supports Tilt")


class EsphomeApiBlock(Model):
    host: str = Field(description="Host")
    port: int = Field(6053, description="Port")
    password: str | None = Field(None, description="API Password")
    encryption_key: str | None = Field(None, description="Encryption Key")
    switches: list[EspSwitch] | None = Field(None, description="Available Switches")
    lights: list[EspLight] | None = Field(None, description="Available Lights")
    covers: list[EspCover] | None = Field(None, description="Available Covers")


class WledBlock(Model):
    host: str = Field(description="Host")
    port: int = Field(80, description="Port")


class RemoteDevice(Model):
    # coerce: str turns a null into "None" in Cerberus, so it passes there.
    nullable = frozenset({"id"})

    id: Str = Field(description="Device ID")
    name: str = Field(description="Device Name")
    protocol: Literal["mqtt", "esphome_api", "wled"] = Field(description="Protocol")
    device_type: Literal["boneio_black", "esphome", "wled", "generic"] = Field(
        "boneio_black", description="Device Type"
    )
    mqtt: MqttBlock | None = Field(
        None, description="MQTT Protocol Settings", json_schema_extra={"x-dependencies": {"protocol": ["mqtt"]}}
    )
    esphome_api: EsphomeApiBlock | None = Field(
        None,
        description="ESPHome API Settings",
        json_schema_extra={"x-dependencies": {"protocol": ["esphome_api"]}},
    )
    wled: WledBlock | None = Field(
        None, description="WLED Settings", json_schema_extra={"x-dependencies": {"protocol": ["wled"]}}
    )

    @model_validator(mode="after")
    def _block_fits_protocol(self) -> RemoteDevice:
        wrong = [k for k in ("mqtt", "esphome_api", "wled") if getattr(self, k) is not None and self.protocol != k]
        if wrong:
            raise ValueError(f"{', '.join(wrong)}: only allowed with protocol {' / '.join(wrong)}")
        return self


SECTION_ADAPTERS = {
    "remote_devices": section(list[RemoteDevice], "Remote devices that can be controlled from this boneIO.")
}
