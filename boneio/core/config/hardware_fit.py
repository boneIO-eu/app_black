"""Fit a restored configuration to the controller it is restored on.

A backup carries the hardware of the controller it was made on: the revision
in ``boneio.version`` (which picks the pin mapping in ``boneio/boards``), the
power and temperature sensors, the Modbus UART and which AIN pin each ADC
terminal is on. Restored on another revision, those are wrong for the
controller it now runs on; everything else in the backup is the user's.

The files are edited as text so comments, ``!include`` and ``!secret`` stay
exactly as the backup has them.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml

from boneio.core.atomic_file import write_atomically
from boneio.core.config.yaml_util import get_board_config_path, normalize_board_name, normalize_version
from boneio.factory_config import HARDWARE_SENSORS, OLDEST_REVISION, template_dir, type_folder

_LOGGER = logging.getLogger(__name__)


class _TagBlindLoader(yaml.SafeLoader):
    """Reads one file without following ``!include``/``!secret``."""


_TagBlindLoader.add_multi_constructor("!", lambda loader, suffix, node: None)


def hardware_of(config_text: str) -> dict[str, str | None]:
    """Revision and type a config.yaml names; None for what it does not."""
    try:
        doc = yaml.load(config_text, Loader=_TagBlindLoader)  # noqa: S506 — safe loader subclass
    except yaml.YAMLError:
        doc = None
    boneio = doc.get("boneio") if isinstance(doc, dict) else None
    if not isinstance(boneio, dict):
        boneio = {}
    version = boneio.get("version")
    device_type = boneio.get("device_type")
    return {
        "version": normalize_version(version) if version is not None else None,
        "device_type": str(device_type) if device_type else None,
    }


def compare_hardware(backup_text: str, current_text: str) -> dict[str, Any]:
    """What differs between the backup's controller and this one."""
    backup, current = hardware_of(backup_text), hardware_of(current_text)
    return {
        "backup_version": backup["version"],
        "current_version": current["version"],
        "backup_device_type": backup["device_type"],
        "current_device_type": current["device_type"],
        "version_mismatch": bool(backup["version"] and current["version"])
        and backup["version"] != current["version"],
        "device_type_mismatch": bool(backup["device_type"] and current["device_type"])
        and normalize_board_name(backup["device_type"]) != normalize_board_name(current["device_type"]),
    }


def current_hardware(config_file: str | Path) -> dict[str, str | None]:
    """Revision and type of the config.yaml on disk, before a restore replaces it."""
    try:
        return hardware_of(Path(config_file).read_text(encoding="utf-8"))
    except OSError:
        return {"version": None, "device_type": None}


def _is_1x(revision: str) -> bool:
    try:
        return float(revision) >= 1.0
    except ValueError:
        return False


def _adc_pins(device_type: str | None, revision: str) -> dict[str, str]:
    """ADC terminal name → AIN pin for a revision, from its factory adc.yaml."""
    folder = type_folder(normalize_board_name(device_type or "32x10"))
    templates = template_dir(folder, revision) or template_dir(folder, OLDEST_REVISION)
    if templates is None or not (templates / "adc.yaml").is_file():
        return {}
    entries = yaml.safe_load((templates / "adc.yaml").read_text(encoding="utf-8")) or []
    return {e["name"]: str(e["pin"]) for e in entries if isinstance(e, dict) and "name" in e and "pin" in e}


def _remap_pins(text: str, pin_map: dict[str, str]) -> str:
    # One pass, so swapped pins (P9_37 ↔ P9_38) are not swapped back.
    return re.sub(
        r"(\bpin:[ \t]*['\"]?)(P9_\d+)",
        lambda m: m.group(1) + pin_map.get(m.group(2), m.group(2)),
        text,
    )


def _fit_adc(config_dir: Path, text: str, pin_map: dict[str, str]) -> tuple[str, bool]:
    """Move the ADC section's pins; returns config.yaml text and whether ADC is used."""
    included = re.search(r"^adc:[ \t]*!include[ \t]+(\S+)", text, re.MULTILINE)
    if included:
        adc_file = (config_dir / included.group(1)).resolve()
        if not adc_file.is_relative_to(config_dir.resolve()) or not adc_file.is_file():
            return text, False
        adc_text = adc_file.read_text(encoding="utf-8")
        fitted = _remap_pins(adc_text, pin_map)
        if fitted != adc_text:
            write_atomically(adc_file, fitted.encode("utf-8"))
        return text, True
    inline = re.search(r"^adc:[^\n]*\n(?:(?:[ \t]+|#)[^\n]*\n|\n)*", text, re.MULTILINE)
    if not inline:
        return text, False
    block = _remap_pins(inline.group(0), pin_map)
    return text[: inline.start()] + block + text[inline.end() :], True


def _board_expanders(device_type: str | None, revision: str) -> dict[int, bool]:
    """MCP23017 address → ``inverted`` the board file of a revision gives."""
    try:
        board_file = get_board_config_path(f"output_{normalize_board_name(device_type or '')}", revision)
        board = yaml.safe_load(Path(board_file).read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001 — no board file, nothing to compare with
        return {}
    return {
        int(e["address"]): bool(e["inverted"])
        for e in board.get("mcp23017") or []
        if isinstance(e, dict) and "address" in e and "inverted" in e
    }


def _fit_expanders(text: str, old: dict[int, bool], new: dict[int, bool], changes: list[str]) -> str:
    """Give the board's own expanders in a ``mcp23017:`` section the new revision's polarity.

    The section shadows the board file (merge_board_config copies the board's
    only when there is none), so a 0.8 one on 1.x would drive the active-low
    relays inverted. Expanders the board does not have are the user's.
    """
    block = re.search(r"^mcp23017:[^\n]*\n(?:(?:[ \t]+|#)[^\n]*\n|\n)*", text, re.MULTILINE)
    if not block:
        return text
    entries = re.split(r"(?m)^(?=[ \t]*-[ \t])", block.group(0))
    for i, entry in enumerate(entries):
        address = re.search(r"\baddress:[ \t]*['\"]?(0[xX][0-9a-fA-F]+|\d+)", entry)
        if not address:
            continue
        addr = int(address.group(1), 0)
        if addr not in new or old.get(addr) == new[addr]:
            continue
        want = "true" if new[addr] else "false"
        fitted = re.sub(r"(\binverted:[ \t]*)\w+", rf"\g<1>{want}", entry, count=1)
        if fitted != entry:
            entries[i] = fitted
            changes.append(f"mcp23017 0x{addr:02x}: inverted {str(old.get(addr)).lower()} → {want}")
    return text[: block.start()] + "".join(entries) + text[block.end() :]


def fit_restored_config(config_dir: Path, revision: str | None) -> tuple[list[str], bool]:
    """Give a just-restored config.yaml this controller's hardware.

    Args:
        config_dir: The config directory the backup was written into.
        revision: This controller's revision, read before the restore.

    Returns:
        What was changed, one line each (empty when the backup already matched
        or the revision is not known), and whether the ADC section crosses the
        1.0 input stage, whose range and filters only the user can fit.
    """
    config_file = Path(config_dir) / "config.yaml"
    if not revision or not config_file.is_file():
        return [], False
    text = config_file.read_text(encoding="utf-8")
    backup = hardware_of(text)
    if not backup["version"] or backup["version"] == revision:
        return [], False

    old_rev, new_rev = backup["version"], revision
    changes = [f"boneio.version: {old_rev} → {new_rev}"]
    text = re.sub(
        r"(^boneio:[ \t]*\n(?:[ \t]+[^\n]*\n|\n)*?[ \t]+version:[ \t]*)[^\n#]*?([ \t]*(?:#[^\n]*)?)$",
        lambda m: f"{m.group(1)}{new_rev}{m.group(2)}",
        text,
        count=1,
        flags=re.MULTILINE,
    )

    old_hw, new_hw = HARDWARE_SENSORS.get(old_rev), HARDWARE_SENSORS.get(new_rev)
    if old_hw and new_hw:
        for key in ("power_sensor", "temp_sensor"):
            old, new = old_hw[key], new_hw[key]
            if old and new and old != new and re.search(rf"^{old}:", text, re.MULTILINE):
                # Backups often carry the other revision's key empty
                # ("ina226: []"); renaming next to it would duplicate the key,
                # and the last one would silently win.
                text = re.sub(rf"^{new}:[ \t]*(?:\[\]|null|~)?[ \t]*\n(?!(?:[ \t]*\n)*[ \t]+\S)", "", text, flags=re.MULTILINE)
                if re.search(rf"^{new}:", text, re.MULTILINE):
                    continue  # this controller's key is already filled in
                text = re.sub(rf"^{old}:", f"{new}:", text, flags=re.MULTILINE)
                changes.append(f"{old} → {new}")
        if old_hw["modbus_uart"] != new_hw["modbus_uart"]:
            fitted = re.sub(
                rf"(^modbus:[ \t]*\n(?:[ \t]+[^\n]*\n)*?[ \t]+uart:[ \t]*['\"]?){old_hw['modbus_uart']}\b",
                rf"\g<1>{new_hw['modbus_uart']}",
                text,
                flags=re.MULTILINE,
            )
            if fitted != text:
                text = fitted
                changes.append(f"modbus.uart: {old_hw['modbus_uart']} → {new_hw['modbus_uart']}")

    text = _fit_expanders(
        text,
        _board_expanders(backup["device_type"], old_rev),
        _board_expanders(backup["device_type"], new_rev),
        changes,
    )

    old_pins, new_pins = _adc_pins(backup["device_type"], old_rev), _adc_pins(backup["device_type"], new_rev)
    pin_map = {old_pins[n]: new_pins[n] for n in old_pins if n in new_pins and old_pins[n] != new_pins[n]}
    text, adc_used = _fit_adc(Path(config_dir), text, pin_map)
    if adc_used and pin_map:
        changes.append("adc: " + ", ".join(f"{a} → {b}" for a, b in sorted(pin_map.items())))
    adc_range_changed = adc_used and _is_1x(old_rev) != _is_1x(new_rev)

    write_atomically(config_file, text.encode("utf-8"))
    _LOGGER.info("Restored config fitted to revision %s: %s", new_rev, "; ".join(changes))
    return changes, adc_range_changed
