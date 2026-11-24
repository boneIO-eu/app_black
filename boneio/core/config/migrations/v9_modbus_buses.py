"""Migration v9: The single modbus section becomes a list of buses.

From 1.7 ``modbus`` is a list of buses, each with an ``id`` that a device
names in its ``bus``. The old section becomes the only bus, ``rs485``: its
``uart`` is now ``port`` and every other key stays as it was. A device
without ``bus`` is on the first bus, so ``modbus_devices`` is not touched and
no device identifier changes.

Before:
    modbus:
      uart: uart4
      baudrate: 9600
After:
    modbus:
      - id: rs485
        port: uart4
        baudrate: 9600

The file is edited on lines, so comments, ``!secret`` and a section kept in
an ``!include``d file survive; the changed file is copied to
``backups/<name>.pre-v9`` first, and an edit that does not read back as
intended is undone. A section written in flow style is left for the recovery
panel.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

import yaml

from boneio.core.atomic_file import write_atomically
from boneio.core.config.migrations import register_migration
from boneio.core.config.migrations.v8_dead_entries import _block, _end_line, _section_roots

_LOGGER = logging.getLogger(__name__)

BUS_ID = "rs485"


def _bus(section: dict) -> dict:
    """The old section as the bus ``rs485``: ``uart`` renamed ``port``, the rest as it is."""
    return {"id": BUS_ID, **{"port" if key == "uart" else key: value for key, value in section.items()}}


@register_migration(
    version=9,
    name="Modbus section becomes a list of buses",
    migrate_file=lambda config_file: _persist(config_file),
)
def migrate_v9_modbus_buses(doc: dict) -> dict:
    """Make the in-memory config what the files will hold after _persist."""
    modbus = doc.get("modbus")
    if isinstance(modbus, dict):
        doc["modbus"] = [_bus(modbus)]
        _LOGGER.warning("Config migration v9: modbus is now a list with the one bus %r", BUS_ID)
    return doc


def _as_list(lines: list[str], node: yaml.Node) -> list[str] | None:
    """The lines with the block mapping at ``node`` turned into a one-bus list.

    None when ``node`` is not a block mapping that starts a line of its own.
    """
    if not isinstance(node, yaml.MappingNode) or node.flow_style or not node.value:
        return None
    start, column = node.start_mark.line, node.start_mark.column
    if lines[start][:column].strip():
        return None
    _, end = _block(lines, start, _end_line(lines, node.end_mark))
    lines = list(lines)
    for key, _ in node.value:
        if key.value == "uart" and key.start_mark.line == key.end_mark.line:
            row = lines[key.start_mark.line]
            lines[key.start_mark.line] = row[: key.start_mark.column] + "port" + row[key.end_mark.column :]
    bus = [f"{' ' * column}- id: {BUS_ID}\n"] + ["  " + line if line.strip() else line for line in lines[start:end]]
    return lines[:start] + bus + lines[end:]


def _persist(config_file: str) -> None:
    from boneio.core.config.yaml_util import load_yaml_file

    main = Path(config_file)
    doc = load_yaml_file(str(main))
    if not isinstance(doc.get("modbus"), dict):
        return

    file, node = _section_roots(main).get("modbus", (None, None))
    text = file.read_text(encoding="utf-8") if file is not None else ""
    edited = _as_list(text.splitlines(keepends=True), node) if node is not None else None
    if edited is None:
        _LOGGER.warning("Config migration v9: the modbus section needs turning into a list of buses by hand")
        return

    backup = main.parent / "backups" / f"{file.name}.pre-v9"
    backup.parent.mkdir(exist_ok=True)
    shutil.copy2(file, backup)
    write_atomically(file, "".join(edited))
    if load_yaml_file(str(main)) != {**doc, "modbus": [_bus(doc["modbus"])]}:
        # The file does not read back as intended: put it back and let
        # start-up report the section instead.
        write_atomically(file, text)
        _LOGGER.error("Config migration v9 did not apply cleanly; %s is as it was", file.name)
    else:
        _LOGGER.warning("Config migration v9 changed %s (copy in backups/)", file.name)
