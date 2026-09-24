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
import threading
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from boneio.core import containers, system_ops

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


class AutoUpdateRequest(BaseModel):
    """Switch for automatic security updates."""

    enabled: bool


@router.post("/autoupdate")
async def set_autoupdate(request: AutoUpdateRequest):
    """Switch automatic security updates on or off.

    Only the switch. Which archive they come from — Debian-Security alone — and
    that they never reboot are fixed in a file a signed migration installs.
    """
    if not await asyncio.to_thread(system_ops.helper_supports, "os-autoupdate-set"):
        raise HTTPException(
            status_code=409,
            detail="The installed system helper cannot switch automatic updates yet. "
            "Apply the pending system migrations (1.6.22) and try again.",
        )
    result = await asyncio.to_thread(system_ops.os_autoupdate_set, request.enabled)
    if not result.ok:
        detail = (result.stderr or result.stdout).strip() or "Could not switch automatic updates"
        raise HTTPException(status_code=500, detail=detail)
    _LOGGER.info("Automatic security updates %s from the panel",
                 "enabled" if request.enabled else "disabled")
    return {"status": "success", "autoupdate": result.json()}


# ---------------------------------------------------------------------- Caddy
#
# Applying the pinned Caddy image pulls it and recreates the container. The
# request that asks for it very likely arrives through that same Caddy, so the
# connection is cut when the container is recreated: the work runs in a thread
# and the panel polls GET /caddy, retrying through the gap.

_caddy_task: dict = {"status": "idle", "started": None, "finished": None, "message": None}
_caddy_lock = threading.Lock()


def _apply_caddy() -> None:
    result = containers.caddy_image_apply()
    with _caddy_lock:
        _caddy_task["finished"] = time.time()
        if result.ok:
            _caddy_task["status"] = "success"
            _caddy_task["message"] = None
        else:
            _caddy_task["status"] = "failed"
            _caddy_task["message"] = (result.stderr or result.stdout).strip()[-500:] or None
    _LOGGER.info("Caddy image apply finished: %s", _caddy_task["status"])


@router.get("/caddy")
async def get_caddy():
    """The Caddy image this release pins, the one in use, and any apply in progress."""
    if not await asyncio.to_thread(containers.helper_supports, "caddy-image-state"):
        return {"supported": False, "task": dict(_caddy_task)}
    result = await asyncio.to_thread(containers.caddy_image_state)
    state = result.json() if result.ok else None
    if state is None:
        detail = (result.stderr or result.stdout).strip() or "Could not read the Caddy image"
        raise HTTPException(status_code=500, detail=detail)
    with _caddy_lock:
        task = dict(_caddy_task)
    return {"supported": True, **state, "task": task}


@router.post("/caddy/apply")
async def apply_caddy():
    """Move Caddy to the pinned image. Returns at once; poll GET /caddy."""
    if not await asyncio.to_thread(containers.helper_supports, "caddy-image-apply"):
        raise HTTPException(
            status_code=409,
            detail="The installed container helper cannot update Caddy yet. "
            "Apply the pending system migrations (1.6.21) and try again.",
        )
    with _caddy_lock:
        if _caddy_task["status"] == "running":
            raise HTTPException(status_code=409, detail="Caddy is already being updated")
        _caddy_task.update(status="running", started=time.time(), finished=None, message=None)
    threading.Thread(target=_apply_caddy, name="caddy-image-apply", daemon=True).start()
    _LOGGER.info("Caddy image apply started from the panel")
    return {"status": "started"}
