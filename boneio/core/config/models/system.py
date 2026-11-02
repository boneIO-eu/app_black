"""The ``web``, ``mqtt`` and ``boneio`` sections: the controller itself.

Mirrors boneio/schema/schema.yaml for these sections. They are single
dictionaries, not lists. What a save of them does to the running system -
the reverse proxy guard, the MQTT credentials - stays in the save route.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BeforeValidator, Field, model_validator

from boneio.core.config.models.base import ANY_CASE, NULL, Model, section, str_lower


class Cloud(Model):
    nullable = frozenset({"pwa_name"})

    enabled: bool = Field(False, description="Enable cloud registration")
    declined: bool = Field(False, description="Not interested in cloud registration")
    pwa_name: str | None = Field(None, description="PWA short name", json_schema_extra=NULL)


class Security(Model):
    nullable = frozenset({"frame_ancestors"})

    map_tiles: bool = Field(False, description="Allow the location picker to load a map")
    frame_ancestors: Union[list[str], str] | None = Field(
        None, description="Which sites may embed this panel in a frame", json_schema_extra=NULL
    )


class LegacyAuth(Model):
    username: str | None = Field(None, description="Username to connect to web interface")
    password: str | None = Field(None, description="Password to web interface")
    allow_anonymous: bool = Field(False, description="Allow unauthenticated access to the web UI and API")


class Web(Model):
    nullable = frozenset({"proxy_port", "cloud", "security", "auth"})

    port: int = Field(8090, description="Port to run web server")
    proxy_port: int | None = Field(
        None,
        description="Reverse proxy port for the Home Assistant link. Advanced; set it only when your own proxy fronts "
        "this panel on another port.",
        json_schema_extra=NULL,
    )
    expose: Literal["all", "proxy"] = Field(
        "all",
        description="Which addresses the panel answers on. 'all' serves it on every interface, including in the clear "
        "on the LAN. 'proxy' limits it to the loopback and the Docker bridge, so it is reachable over TLS "
        "on the proxy port or through an SSH tunnel, and not otherwise. The proxy reaches the panel over "
        "the loopback when Caddy runs as a system service, or over the Docker bridge when it runs in a "
        "container; Node-RED always uses the bridge.",
    )
    cloud: Cloud | None = Field(
        default_factory=Cloud, description="boneIO Cloud registration for PWA support", json_schema_extra=NULL
    )
    security: Security | None = Field(
        default_factory=Security, description="Web security headers", json_schema_extra=NULL
    )
    auth: LegacyAuth | None = Field(default_factory=LegacyAuth, description="Auth if defined", json_schema_extra=NULL)


class HaDiscovery(Model):
    enabled: bool = Field(True, description="Enable HA discovery.")
    topic_prefix: str = Field("homeassistant", description="Prefix topic of HA discovery.")


class Tls(Model):
    enabled: bool = Field(False, description="Use TLS")
    ca_certs: str | None = Field(None, description="CA certificate (PEM) that signed the broker's certificate")
    certfile: str | None = Field(
        None,
        description="Client certificate (PEM), for brokers that require one",
        json_schema_extra={"x-dependencies": "keyfile"},
    )
    keyfile: str | None = Field(
        None,
        description="Private key of the client certificate (PEM, unencrypted)",
        json_schema_extra={"x-dependencies": "certfile"},
    )
    insecure: bool = Field(False, description="Skip checking the broker's certificate")

    @model_validator(mode="after")
    def _certificate_and_key_together(self) -> Tls:
        if (self.certfile is None) != (self.keyfile is None):
            raise ValueError("certfile and keyfile go together: set both or neither")
        return self


class Mqtt(Model):
    enabled: bool = Field(True, description="Enable MQTT protocol")
    host: str = Field(description="Mqtt broker hostname or IP address")
    username: str | None = Field(None, description="Username to connect ot mqtt broker")
    password: str | None = Field(None, description="Password to mqtt")
    port: int = Field(1883, description="Port to connect to mqtt broker")
    ha_discovery: HaDiscovery = Field(default_factory=HaDiscovery, description="Ha discovery sub section")
    send_boneio_autodiscovery: bool = Field(True, description="Enable sending BoneIO autodiscovery messages")
    receive_boneio_autodiscovery: bool = Field(True, description="Enable receiving BoneIO autodiscovery messages")
    update_channel: Literal["stable", "dev"] = Field("stable", description="Update channel")
    tls: Tls | None = Field(None, description="Encrypt the connection to the broker (TLS)")


_VERSIONS = ("0.2", "0.3", "0.4", "0.5", "0.6", "0.7", "0.8", "1.0", "1.1")
BoardVersion = Annotated[
    Literal[_VERSIONS],
    BeforeValidator(str),  # coerce: version_to_str
    # An unquoted 0.8 is a number in YAML.
    Field(json_schema_extra={"type": ["number", "string"], "enum": [*_VERSIONS, *map(float, _VERSIONS)]}),
]
DeviceType = Annotated[
    Literal["32x10a", "32x10", "32", "32x5a", "32x5", "24x16a", "24x16", "24", "48x4a", "48x4",
            "48", "cover", "cover mix", "cm"],
    BeforeValidator(str_lower),
    # Spelt as the product is named, 32x10A, in the configs the controller ships with.
    Field(json_schema_extra={**ANY_CASE, "enum": ["32x10A", "32x10", "32", "32x5A", "32x5", "24x16A", "24x16",
                                                  "24", "48x4A", "48x4", "48", "cover", "cover mix", "cm"]}),
]


class Boneio(Model):
    nullable = frozenset({"serial_override"})

    config_version: int = Field(0, description="Schema version for config migrations. Managed automatically.")
    name: str = Field(description="Name of boneio. Default is Black.")
    version: BoardVersion | None = Field(None, description="BoneIO Black Hardware version")
    device_type: DeviceType | None = Field(None, description="Predefined device type configuration")
    ha_child_devices: bool = Field(False, description="[EXPERIMENTAL] HA child devices mode")
    ha_child_devices_naming: Literal["default", "device_name", "device_name_area"] = Field(
        "default", description="Child device naming style"
    )
    serial_override: Annotated[str, Field(pattern=r"^blk[a-f0-9]{6}$")] | None = Field(
        None, description="Serial number override", json_schema_extra=NULL
    )


SECTION_ADAPTERS = {
    "web": section(
        Web | None,
        "https://boneio.eu/docs/black/0.9.x-dev/configuration/web \n Web section of boneIO Black. It enables web "
        "interface. Default on port 8090.",
        **NULL,
    ),
    "mqtt": section(
        Mqtt,
        "https://boneio.eu/docs/black/configuration/mqtt \n Mqtt section of boneIO Black configuration file. It "
        "handled connecting to mqtt broker, which then is connected to Home Assistant or other smart home system.",
    ),
    "boneio": section(
        Boneio,
        "https://boneio.eu/docs/black/0.9.x-dev/configuration/boneio \n BoneIO configuration section. It's new "
        "section for boneIO Black. It enables you to use predefined device types. For now only 0.7 and 0.8 devices "
        "are supported.",
    ),
}
