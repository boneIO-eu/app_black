"""The packaged compose file and the trusted template must not drift apart.

``boneio/core/cloud/data/docker-compose.yaml`` is what image builds used to
copy onto a fresh controller. When 1.6.15 added ``WEB_PORT`` to the migration
template and not to this copy, every image built afterwards shipped a Caddy
that proxies to 8090 whatever ``web.port`` says.
"""

from __future__ import annotations

from importlib.resources import files

_PACKAGED = files("boneio.core.cloud.data").joinpath("docker-compose.yaml")
_TEMPLATE = files("boneio.migrations.assets").joinpath(
    "docker/nodered/docker-compose.yaml"
)


def test_packaged_compose_is_the_trusted_template() -> None:
    assert _PACKAGED.read_bytes() == _TEMPLATE.read_bytes(), (
        "boneio/core/cloud/data/docker-compose.yaml differs from "
        "boneio/migrations/assets/docker/nodered/docker-compose.yaml — "
        "copy the template over it"
    )


def test_template_passes_the_panel_port_to_caddy() -> None:
    assert "- WEB_PORT=${WEB_PORT:-8090}" in _TEMPLATE.read_text()
