"""Announce the panel on the local network over mDNS, as ``_boneio._tcp``.

Lets anything on the LAN - Home Assistant first of all - find a controller
without being told its address. Done through avahi-daemon, which the system
image already runs: it owns the host name, follows address changes and answers
queries in its own process, not in boneIO's event loop. ``avahi-publish`` holds
the announcement for as long as it runs, as the boneio user, no root needed.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from boneio.core.config.config_helper import ConfigHelper

_LOGGER = logging.getLogger(__name__)

SERVICE_TYPE = "_boneio._tcp"
#: How often the announcement is checked against the current panel port and
#: name, and against avahi-publish still running.
RECHECK_SECONDS = 60


def publish_command(config_helper: ConfigHelper) -> list[str] | None:
    """The avahi-publish command line, or None when there is no panel to find.

    Args:
        config_helper: Where the identity and the panel port come from.

    Returns:
        The argv to run, or None.
    """
    if not config_helper.is_web_active:
        return None
    serial = config_helper.real_serial
    return [
        "avahi-publish",
        "--service",
        # The serial, not the configured name: names repeat on a LAN full of
        # controllers left at the default, and avahi would rename one of them
        # by whichever happened to boot second. Not withheld as it is from
        # anonymous API replies: mDNS stays on the link, where the MAC the
        # serial is made from is already in every ARP reply.
        serial,
        SERVICE_TYPE,
        str(config_helper.web_configuration_port),
        f"serial={serial}",
        f"name={config_helper.name}",
        f"device_type={config_helper.device_type}",
        f"board={config_helper.version}",
        f"proto={config_helper.http_proto}",
    ]


async def _stop(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is None:
        proc.terminate()
    await proc.wait()


async def advertise(config_helper: ConfigHelper) -> None:
    """Keep the announcement in step with the controller until cancelled.

    avahi-publish is started again when what it announces changes, and when it
    has exited - an avahi-daemon restart takes it down with it. Cancelling
    stops it, and avahi sends the goodbye that takes the controller off the
    browsers.

    Args:
        config_helper: Passed to :func:`publish_command` on every check.
    """
    if shutil.which("avahi-publish") is None:
        _LOGGER.info("avahi-publish not installed, not announcing on the LAN")
        return
    proc: asyncio.subprocess.Process | None = None
    published: list[str] | None = None
    try:
        while True:
            wanted = publish_command(config_helper)
            if proc is not None and (wanted != published or proc.returncode is not None):
                if proc.returncode is not None:
                    _LOGGER.warning("avahi-publish exited with %s, starting it again", proc.returncode)
                await _stop(proc)
                proc = None
            if proc is None and wanted is not None:
                try:
                    # stderr is inherited, so avahi's own complaint lands in
                    # the journal next to ours.
                    proc = await asyncio.create_subprocess_exec(
                        *wanted, stdout=asyncio.subprocess.DEVNULL
                    )
                    published = wanted
                    _LOGGER.info("mDNS: announcing %s on port %s", wanted[2], wanted[4])
                except OSError:
                    _LOGGER.warning("Could not start avahi-publish", exc_info=True)
            await asyncio.sleep(RECHECK_SECONDS)
    finally:
        if proc is not None:
            await _stop(proc)
