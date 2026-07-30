"""Migration v5: Convert 'ina219' OLED screen name to generic 'ina'.

Before: oled.screens: [- ina219]
After:  oled.screens: [- ina]
"""

from __future__ import annotations

import logging
import re

from boneio.core.config.migrations import register_migration

_LOGGER = logging.getLogger(__name__)


def _persist_ina_screen(config_file: str) -> None:
    """Replace '- ina219' with '- ina' in YAML file.

    Args:
        config_file: Path to the YAML config file.
    """
    with open(config_file, encoding="utf-8") as f:
        lines = f.readlines()

    updated = False
    updated_lines: list[str] = []
    ina_re = re.compile(r"^(\s*-\s*)ina219(\s*)$")

    for line in lines:
        m = ina_re.match(line)
        if m:
            new_line = f"{m.group(1)}ina{m.group(2)}\n"
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
    version=5,
    name="Convert OLED screen name 'ina219' to generic 'ina'",
    migrate_file=_persist_ina_screen,
)
def migrate_v5_ina_screen(doc: dict) -> dict:
    """Replace 'ina219' with 'ina' in oled.screens list.

    Args:
        doc: Raw config dictionary.

    Returns:
        Migrated config dictionary.
    """
    oled = doc.get("oled")
    if isinstance(oled, dict):
        screens = oled.get("screens")
        if isinstance(screens, list) and "ina219" in screens:
            doc["oled"]["screens"] = [
                "ina" if s == "ina219" else s for s in screens
            ]
            _LOGGER.info("Migrated oled.screens: replaced 'ina219' with 'ina'")
    return doc
