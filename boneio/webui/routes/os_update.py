"""Operating system updates: apt, through the privileged helper.

Updating boneIO never touched the Debian system under it, so a controller
shipped a year ago still runs the kernel and libraries it left the factory with.
These endpoints let an administrator check for and install system updates.

Nothing here builds a command. The helper takes a mode from a closed set —
``check`` or ``upgrade`` — and owns the apt command lines, options and
repositories; see ``boneio-system``. The run happens in a transient systemd
unit, so these endpoints return at once and the panel polls ``/state``.

The device never reboots on its own. ``/state`` says when a restart is needed
and why; the operator uses the existing restart action when it suits them.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from boneio.core import system_ops

_LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/os-update", tags=["os-update"])

#: Where the system images and recovery instructions live, for when an update
#: leaves a controller that does not come back. Shown next to every update.
RECOVERY_IMAGES_URL = "https://github.com/boneIO-eu/black_debian_images"

_UNSUPPORTED = (
    "The installed system helper cannot update the operating system yet. "
    "Apply the pending system migrations (1.6.18) and try again."
)


def _supported() -> bool:
    return system_ops.helper_supports("os-update-state")


@router.get("/state")
async def get_state():
    """What the last run found, whether one is running, and if a reboot is due.

    Returns:
        ``supported`` false on a helper that predates these operations;
        otherwise the helper's report plus the recovery images URL.
    """
    if not await asyncio.to_thread(_supported):
        return {"supported": False, "message": _UNSUPPORTED,
                "recovery_images_url": RECOVERY_IMAGES_URL}
    result = await asyncio.to_thread(system_ops.os_update_state)
    state = result.json() if result.ok else None
    if state is None:
        detail = (result.stderr or result.stdout).strip() or "Could not read the update state"
        raise HTTPException(status_code=500, detail=detail)
    return {"supported": True, "recovery_images_url": RECOVERY_IMAGES_URL, **state}


async def _start(mode: str):
    if not await asyncio.to_thread(_supported):
        raise HTTPException(status_code=409, detail=_UNSUPPORTED)
    result = await asyncio.to_thread(system_ops.os_update_start, mode)
    if not result.ok:
        detail = (result.stderr or result.stdout).strip() or f"Could not start the {mode}"
        # A run already in progress is the caller's timing, not a fault.
        status = 409 if "already running" in detail else 500
        raise HTTPException(status_code=status, detail=detail)
    _LOGGER.info("Operating system %s started from the panel", mode)
    return {"status": "started", "mode": mode}


@router.post("/check")
async def start_check():
    """Refresh the package lists and list what an upgrade would install."""
    return await _start("check")


@router.post("/upgrade")
async def start_upgrade():
    """Install the available system updates. Does not reboot."""
    return await _start("upgrade")


@router.get("/log")
async def get_log():
    """The end of the last run's apt output."""
    if not await asyncio.to_thread(_supported):
        return {"log": ""}
    result = await asyncio.to_thread(system_ops.os_update_log)
    return {"log": result.stdout if result.ok else ""}
