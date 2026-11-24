"""Modbus buses and which bus each device is on.

A device names its bus by ``id``; one that names none is on the first bus of
the list, so a config written for a single bus keeps working. A device's
identifier is made from its own fields only: moving it to another bus does
not change its entities in Home Assistant.
"""

from __future__ import annotations

import re

from boneio.const import ADDRESS, ID, MODEL, UARTS

#: A bus port: a built-in UART by its key, or a USB serial adapter by a name
#: that does not change when it is replugged (by-id, by-path) or by its kernel
#: name. A by-id/by-path name is one path component of letters, digits and
#: ``_.:+-``, with no dot first, so no other file is reachable through it.
PORT_PATTERN = (
    rf"^({'|'.join(UARTS)})$"
    r"|^/dev/(serial/by-(id|path)/[A-Za-z0-9_][A-Za-z0-9_.:+-]*|ttyUSB\d+|ttyACM\d+)$"
)


def is_valid_port(port: str) -> bool:
    """Whether ``port`` names a bus port :data:`PORT_PATTERN` allows."""
    return isinstance(port, str) and re.fullmatch(PORT_PATTERN, port) is not None


def serial_device(port: str) -> str:
    """The device file of a bus port: a UART's /dev/ttyS*, a path as it is."""
    return UARTS[port][ID] if port in UARTS else port


def device_id(device: dict) -> str:
    """A Modbus device's identifier: its ``id``, or address and model."""
    if device.get(ID):
        return str(device[ID]).replace(" ", "").lower()
    return f"{device.get(ADDRESS, '')}_{device.get(MODEL, '')}".lower().replace(" ", "_")


def device_bus(device: dict, buses: list[dict]) -> str | None:
    """The bus id a device names, else the first bus's; None with no buses."""
    if device.get("bus"):
        return device["bus"]
    return buses[0]["id"] if buses else None


def bus_reference_errors(devices: list[dict], buses: list[dict]) -> list[str]:
    """One line per device naming a bus the list does not have."""
    ids = {bus["id"] for bus in buses}
    return [
        f"Modbus device {device_id(d)!r} is on bus {d['bus']!r}, which is not configured."
        for d in devices
        if d.get("bus") and d["bus"] not in ids
    ]


def _on_bus(device: dict, buses: list[dict]) -> str | None:
    bus = device_bus(device, buses)
    return bus if bus in {b["id"] for b in buses} else None


def bus_change_errors(old_buses: list[dict], new_buses: list[dict], devices: list[dict]) -> list[str]:
    """One line per device a change of the bus list would move or strand.

    A device on a bus must stay on that bus: removing or renaming it, or
    reordering the list while devices without ``bus`` are on the first, is
    refused. A device whose bus was already missing is not this check's.
    """
    errors = []
    for d in devices:
        old, new = _on_bus(d, old_buses), _on_bus(d, new_buses)
        if old is None or new == old:
            continue
        if new is None:
            errors.append(f"Modbus device {device_id(d)!r} is on bus {old!r}, which this change removes.")
        else:
            errors.append(f"Modbus device {device_id(d)!r} is on bus {old!r} and would move to {new!r}.")
    return errors
