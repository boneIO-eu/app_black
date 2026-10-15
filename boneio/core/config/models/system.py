"""The ``web``, ``mqtt`` and ``boneio`` sections: the controller itself.

Mirrors boneio/schema/schema.yaml for these sections. They are single
dictionaries, not lists. What a save of them does to the running system -
the reverse proxy guard, the MQTT credentials - stays in the save route.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BeforeValidator, Field, TypeAdapter, model_validator

from boneio.core.config.models.base import Model, str_lower


class Cloud(Model):
    nullable = frozenset({"pwa_name"})

    enabled: bool = False
    declined: bool = False
    pwa_name: str | None = None


class Security(Model):
    nullable = frozenset({"frame_ancestors"})

    map_tiles: bool = False
    frame_ancestors: Union[list[str], str] | None = None


class LegacyAuth(Model):
    username: str | None = None
    password: str | None = None
    allow_anonymous: bool = False


class Web(Model):
    nullable = frozenset({"proxy_port", "cloud", "security", "auth"})

    port: int = 8090
    proxy_port: int | None = None
    expose: Literal["all", "proxy"] = "all"
    cloud: Cloud | None = Field(default_factory=Cloud)
    security: Security | None = Field(default_factory=Security)
    auth: LegacyAuth | None = Field(default_factory=LegacyAuth)


class HaDiscovery(Model):
    enabled: bool = True
    topic_prefix: str = "homeassistant"


class Tls(Model):
    enabled: bool = False
    ca_certs: str | None = None
    certfile: str | None = None
    keyfile: str | None = None
    insecure: bool = False

    @model_validator(mode="after")
    def _certificate_and_key_together(self) -> Tls:
        if (self.certfile is None) != (self.keyfile is None):
            raise ValueError("certfile and keyfile go together: set both or neither")
        return self


class Mqtt(Model):
    enabled: bool = True
    host: str
    username: str | None = None
    password: str | None = None
    port: int = 1883
    ha_discovery: HaDiscovery = Field(default_factory=HaDiscovery)
    send_boneio_autodiscovery: bool = True
    receive_boneio_autodiscovery: bool = True
    update_channel: Literal["stable", "dev"] = "stable"
    tls: Tls | None = None


BoardVersion = Annotated[
    Literal["0.2", "0.3", "0.4", "0.5", "0.6", "0.7", "0.8", "1.0", "1.1"],
    BeforeValidator(str),  # coerce: version_to_str
]
DeviceType = Annotated[
    Literal["32x10a", "32x10", "32", "32x5a", "32x5", "24x16a", "24x16", "24", "48x4a", "48x4",
            "48", "cover", "cover mix", "cm"],
    BeforeValidator(str_lower),
]


class Boneio(Model):
    nullable = frozenset({"serial_override"})

    config_version: int = 0
    name: str
    version: BoardVersion | None = None
    device_type: DeviceType | None = None
    ha_child_devices: bool = False
    ha_child_devices_naming: Literal["default", "device_name", "device_name_area"] = "default"
    serial_override: Annotated[str, Field(pattern=r"^blk[a-f0-9]{6}$")] | None = None


SECTION_ADAPTERS = {
    "web": TypeAdapter(Web | None),
    "mqtt": TypeAdapter(Mqtt),
    "boneio": TypeAdapter(Boneio),
}
