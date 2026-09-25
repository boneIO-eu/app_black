"""Migration v6: Drop dead keys from inputs.

Both keys were ignored at runtime but stayed in schema.yaml, so people who fed
the schema to an LLM got configs full of them:

- ``gpio_mode`` — pull-up/pull-down comes from the kernel overlay.
- ``clear_message`` — sent an empty MQTT message 200 ms after a click, the way
  Zigbee2MQTT clears its ``action`` sensor. It only made sense while clicks
  reached Home Assistant as a sensor; the event entity needs no reset. It
  stopped working in the 2025 input refactor and nobody noticed.

Before:
    event:
      - name: IN_01
        pin: P8_37
        gpio_mode: gpio_pu
        clear_message: true
After:
    event:
      - name: IN_01
        pin: P8_37
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from boneio.core.atomic_file import write_atomically
from boneio.core.config.migrations import register_migration

_LOGGER = logging.getLogger(__name__)

# Sections whose list items may still carry the keys.
_SECTIONS = ("event", "binary_sensor")
_KEYS = ("gpio_mode", "clear_message")

_TOP_LEVEL_RE = re.compile(r"^([A-Za-z_][\w-]*)\s*:(.*)$")
_INCLUDE_RE = re.compile(r"^!include\s+(\S+)$")


def _strip_key_lines(lines: list[str], keys: tuple[str, ...]) -> tuple[list[str], int]:
    """Remove every ``key: value`` line from a YAML block list.

    A key written as the first entry of a list item (``- key: value``) hands
    its dash to the next line of that item, so the item survives.

    Args:
        lines: Lines of the block, with line endings.
        keys: Mapping keys to remove.

    Returns:
        The new lines and how many were removed.
    """
    names = "|".join(re.escape(k) for k in keys)
    key_re = re.compile(rf"^(\s*)(-\s+)?(?:{names})\s*:.*$")
    out: list[str] = []
    removed = 0
    pending_dash: int | None = None  # indent of a dash that needs a new owner

    for line in lines:
        m = key_re.match(line.rstrip("\n"))
        if m:
            removed += 1
            if m.group(2):
                pending_dash = len(m.group(1))
            continue
        if pending_dash is not None and line.strip() and not line.lstrip().startswith("#"):
            indent = len(line) - len(line.lstrip())
            if indent > pending_dash:
                line = " " * pending_dash + "- " + line.lstrip()
            pending_dash = None
        out.append(line)
    return out, removed


def strip_item_keys(config_file: str, sections: tuple[str, ...], keys: tuple[str, ...]) -> None:
    """Remove ``keys`` from list items of top-level ``sections`` on disk.

    Follows a top-level ``section: !include file.yaml`` into that file, since
    that is where the shipped configs keep ``event`` and ``binary_sensor``.

    Args:
        config_file: Path to config.yaml.
        sections: Top-level section names to clean.
        keys: Mapping keys to remove from their items.
    """
    main = Path(config_file)
    lines = main.read_text(encoding="utf-8").splitlines(keepends=True)

    out: list[str] = []
    block: list[str] = []
    in_section = False
    main_removed = 0

    def flush() -> None:
        nonlocal main_removed
        if in_section:
            cleaned, n = _strip_key_lines(block, keys)
            main_removed += n
            out.extend(cleaned)
        else:
            out.extend(block)
        block.clear()

    for line in lines:
        m = _TOP_LEVEL_RE.match(line.rstrip("\n"))
        if m:
            flush()
            name, rest = m.group(1), m.group(2).split("#", 1)[0].strip()
            in_section = name in sections
            include = _INCLUDE_RE.match(rest) if in_section else None
            if include:
                _strip_file(main.parent / include.group(1), keys)
        block.append(line)
    flush()

    if main_removed:
        write_atomically(main, "".join(out))
        _LOGGER.info("Removed %d deprecated line(s) from %s", main_removed, main)


def _strip_file(path: Path, keys: tuple[str, ...]) -> None:
    """Remove ``keys`` from an included file that holds a whole section."""
    if not path.is_file():
        _LOGGER.warning("Included file %s not found, skipping", path)
        return
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    cleaned, removed = _strip_key_lines(lines, keys)
    if removed:
        write_atomically(path, "".join(cleaned))
        _LOGGER.info("Removed %d deprecated line(s) from %s", removed, path)


def _persist_input_keys(config_file: str) -> None:
    strip_item_keys(config_file, _SECTIONS, _KEYS)


@register_migration(
    version=6,
    name="Remove gpio_mode and clear_message from event/binary_sensor",
    migrate_file=_persist_input_keys,
)
def migrate_v6_input_keys(doc: dict) -> dict:
    """Drop the dead keys from every event and binary_sensor item.

    Args:
        doc: Raw config dictionary.

    Returns:
        Migrated config dictionary.
    """
    for section in _SECTIONS:
        items = doc.get(section)
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    for key in _KEYS:
                        item.pop(key, None)
    return doc
