"""The ``remote_devices`` section: other controllers, ESPHome and WLED devices.

Mirrors boneio/schema/schema.yaml for the section. A protocol's block
(``mqtt``, ``esphome_api``, ``wled``) is only allowed on a device of that
protocol, as the Cerberus ``dependencies`` rule has it.
"""

from __future__ import annotations

from typing import Literal, Union

from pydantic import TypeAdapter, model_validator

from boneio.core.config.models.base import Model, Str

Number = Union[float, int]


class Entity(Model):
    id: str
    name: str | None = None


class MqttBlock(Model):
    outputs: list[Entity] | None = None
    covers: list[Entity] | None = None


class EspSwitch(Entity):
    key: int | None = None


class EspLight(EspSwitch):
    supports_brightness: bool = False
    supports_color_temp: bool = False
    supports_rgb: bool = False
    supports_rgbw: bool = False
    min_mireds: Number | None = None
    max_mireds: Number | None = None


class EspCover(EspSwitch):
    supports_position: bool = False
    supports_tilt: bool | None = None


class EsphomeApiBlock(Model):
    host: str
    port: int = 6053
    password: str | None = None
    encryption_key: str | None = None
    switches: list[EspSwitch] | None = None
    lights: list[EspLight] | None = None
    covers: list[EspCover] | None = None


class WledBlock(Model):
    host: str
    port: int = 80


class RemoteDevice(Model):
    # coerce: str turns a null into "None" in Cerberus, so it passes there.
    nullable = frozenset({"id"})

    id: Str
    name: str
    protocol: Literal["mqtt", "esphome_api", "wled"]
    device_type: Literal["boneio_black", "esphome", "wled", "generic"] = "boneio_black"
    mqtt: MqttBlock | None = None
    esphome_api: EsphomeApiBlock | None = None
    wled: WledBlock | None = None

    @model_validator(mode="after")
    def _block_fits_protocol(self) -> RemoteDevice:
        wrong = [k for k in ("mqtt", "esphome_api", "wled") if getattr(self, k) is not None and self.protocol != k]
        if wrong:
            raise ValueError(f"{', '.join(wrong)}: only allowed with protocol {' / '.join(wrong)}")
        return self


SECTION_ADAPTERS = {"remote_devices": TypeAdapter(list[RemoteDevice])}
