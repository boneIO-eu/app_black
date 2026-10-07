"""Moves a controller from the Caddy container to the packaged Caddy by itself.

The move is the root helper's (``proxy-switch-start``), run in a unit of its
own; this only decides when to ask for it and watches it finish. It waits for
the controller to have settled, needs the package repository to be reachable,
and gives up after a few failed runs so a controller that cannot make the move
does not retry for ever. Everything that touches the helper or the network runs
off the event loop, and nothing here waits on or blocks the inputs.
"""

from __future__ import annotations

import asyncio
import logging
import socket

from boneio.core import containers

_LOGGER = logging.getLogger(__name__)

#: Let the controller finish starting (discovery, Modbus, the first sensor
#: reads) before a package install competes with it for a single core.
START_DELAY = 300
#: Between looks when a condition was not met (offline, helper not updated).
RECHECK = 1800
POLL = 10
MAX_ATTEMPTS = 3
#: Where the package comes from; no point starting the move without it.
REPO_HOST = "dl.cloudsmith.io"


def has_default_route() -> bool:
    """Whether the kernel has a default IPv4 route (destination and mask zero)."""
    try:
        with open("/proc/net/route", encoding="ascii") as handle:
            rows = [line.split() for line in handle.read().splitlines()[1:]]
    except OSError:
        return False
    return any(len(r) > 7 and r[1] == "00000000" and r[7] == "00000000" for r in rows)


def repo_resolves() -> bool:
    """Whether the package repository's name resolves. Blocks; call off the loop."""
    try:
        socket.getaddrinfo(REPO_HOST, 443)
    except OSError:
        return False
    return True


def read_state() -> dict | None:
    """The helper's switch record, or None when it cannot be read."""
    result = containers.proxy_switch_state()
    state = result.json() if result.ok else None
    return state if isinstance(state, dict) else None


def _recover_if_cut_short(state: dict) -> dict | None:
    """Undo a run the helper reports as interrupted, and read the record again.

    The helper shows a ``running`` record with no unit as ``failed`` with the
    error ``interrupted``; the record itself still says ``running`` until the
    undo has run, which is what puts a stopped unit's container back. Covers
    ``systemctl stop`` of the unit without a reboot (a boot unit covers that).
    Idempotent, so a record it cannot change costs one cheap call.
    """
    _LOGGER.warning("Proxy switch was interrupted; undoing it")
    containers.proxy_switch_recover()
    return read_state()


async def attempt_switch(recovered: bool = False) -> bool:
    """One look: start the switch if every condition holds, and wait for it.

    Args:
        recovered: Whether the interrupted-run undo was already tried.

    Returns:
        Whether a switch was started.
    """
    if not await asyncio.to_thread(containers.helper_supports, "proxy-switch-start"):
        return False
    if await asyncio.to_thread(containers.proxy_mode) == "native":
        return False
    state = await asyncio.to_thread(read_state)
    if state is None:
        return False
    if not recovered and not state.get("running") and state.get("error") == "interrupted":
        state = await asyncio.to_thread(_recover_if_cut_short, state)
        if state is None:
            return False
    if state.get("running") or state.get("state") == "done":
        return False
    attempts = state.get("attempts")
    if isinstance(attempts, int) and attempts >= MAX_ATTEMPTS:
        return False
    if not await asyncio.to_thread(has_default_route):
        return False
    if not await asyncio.to_thread(repo_resolves):
        return False

    started = await asyncio.to_thread(containers.proxy_switch_start)
    if not started.ok:
        _LOGGER.warning("Proxy switch did not start: %s", (started.stderr or started.stdout).strip())
        return False
    _LOGGER.info("Proxy switch started")
    while True:
        await asyncio.sleep(POLL)
        state = await asyncio.to_thread(read_state)
        if state is not None and not state.get("running"):
            break
    _LOGGER.info("Proxy switch finished: %s", state.get("state"))
    return True


async def run() -> None:
    """Background task: look 5 minutes after start, then every half hour.

    Ends once Caddy is the package. A failed run is looked at again later, up
    to MAX_ATTEMPTS runs in all.
    """
    await asyncio.sleep(START_DELAY)
    recovered = False
    while await asyncio.to_thread(containers.proxy_mode) != "native":
        try:
            await attempt_switch(recovered)
        except Exception:  # noqa: BLE001 - a failed look must not end the task
            _LOGGER.exception("Proxy switch check failed")
        recovered = True
        await asyncio.sleep(RECHECK)
