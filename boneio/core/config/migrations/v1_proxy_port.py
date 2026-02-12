"""Migration v1: Rename deprecated config fields.

- web.nginx_proxy_port -> web.proxy_port
- modbus_sensors -> modbus_devices (warning only, no rename)
"""

from __future__ import annotations

import logging
import re

from boneio.core.config.migrations import register_migration

_LOGGER = logging.getLogger(__name__)


def _persist_proxy_port(config_file: str) -> None:
    """Replace nginx_proxy_port with proxy_port in the YAML file.

    Args:
        config_file: Path to the YAML config file.
    """
    with open(config_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    updated = False
    updated_lines: list[str] = []
    for line in lines:
        if "nginx_proxy_port:" in line:
            indent = len(line) - len(line.lstrip())
            value_part = line.split("nginx_proxy_port:", 1)[1]
            new_line = " " * indent + "proxy_port:" + value_part
            updated_lines.append(new_line)
            updated = True
            _LOGGER.info(
                "Replaced in config file: %s -> %s",
                line.rstrip(),
                new_line.rstrip(),
            )
        else:
            updated_lines.append(line)

    if updated:
        with open(config_file, "w", encoding="utf-8") as f:
            f.writelines(updated_lines)


@register_migration(
    version=1,
    name="nginx_proxy_port -> proxy_port, modbus_sensors deprecation",
    migrate_file=_persist_proxy_port,
)
def migrate(doc: dict) -> dict:
    """Migrate web.nginx_proxy_port to web.proxy_port and warn about modbus_sensors.

    Args:
        doc: Raw config dict.

    Returns:
        Migrated config dict.
    """
    # web.nginx_proxy_port -> web.proxy_port
    if "web" in doc and isinstance(doc["web"], dict):
        if "nginx_proxy_port" in doc["web"]:
            _LOGGER.info("Migrating 'web.nginx_proxy_port' to 'web.proxy_port'")
            doc["web"]["proxy_port"] = doc["web"].pop("nginx_proxy_port")

    # modbus_sensors -> modbus_devices (warning only)
    if "modbus_sensors" in doc:
        _LOGGER.warning(
            "Modbus sensors are renamed to modbus_devices. "
            "Please update your config."
        )

    return doc
