"""Serial ports a Modbus bus can use: the built-in RS485 and USB adapters."""

from __future__ import annotations

import os
import re
from collections.abc import Iterable

from boneio.const import UARTS

#: The controller's own RS485 port; always offered.
DEFAULT_UART = "uart4"


def _usb_label(name: str) -> str:
    """A by-id link name without its ``usb-`` prefix and ``-ifNN[-portN]`` suffix."""
    name = name.removeprefix("usb-")
    return re.sub(r"-if\d+(-port\d+)?$", "", name)


def list_serial_ports(
    configured: Iterable[str], by_id_dir: str = "/dev/serial/by-id"
) -> list[dict]:
    """Ports to offer for a bus: ``uart4`` first, UARTs in ``configured``, then USB.

    Each item is ``{"port", "label", "kind": "builtin" | "usb"}``. A USB
    adapter's port is its by-id path, which survives replugging. A missing
    ``by_id_dir`` means no USB adapters.
    """
    uarts = list(dict.fromkeys([DEFAULT_UART, *(p for p in configured if p in UARTS)]))
    ports = [{"port": u, "label": f"RS485 ({u})", "kind": "builtin"} for u in uarts]
    try:
        with os.scandir(by_id_dir) as entries:
            names = sorted(e.name for e in entries)
    except OSError:
        names = []
    ports += [
        {"port": f"{by_id_dir}/{n}", "label": _usb_label(n), "kind": "usb"} for n in names
    ]
    return ports
