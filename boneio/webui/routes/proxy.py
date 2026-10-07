"""Caddy's move from the container to the packaged service, as the panel shows it.

The controller starts the move itself (``boneio.core.proxy_switch``); these
endpoints only report how it went and let an administrator ask again once the
automatic attempts have run out. Nothing here builds a command: the root helper
owns the switch.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from boneio.core import containers

_LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/proxy", tags=["proxy"])

_UNSUPPORTED = (
    "The installed container helper cannot switch Caddy yet. "
    "Apply the pending system migrations (1.6.42) and try again."
)


@router.get("/state")
async def get_state():
    """The mode Caddy runs in, the installed version, and the last switch."""
    if not await asyncio.to_thread(containers.helper_supports, "proxy-switch-state"):
        return {"supported": False, "message": _UNSUPPORTED}
    mode = await asyncio.to_thread(containers.proxy_mode)
    switch = (await asyncio.to_thread(containers.proxy_switch_state)).json()
    installed = candidate = None
    if mode == "native":
        image = (await asyncio.to_thread(containers.caddy_image_state)).json()
        if isinstance(image, dict):
            installed, candidate = image.get("installed"), image.get("candidate")
    return {
        "supported": True,
        "mode": mode,
        "installed": installed,
        "candidate": candidate,
        "switch": switch if isinstance(switch, dict) else None,
    }


@router.post("/switch")
async def start_switch():
    """Start the switch now, also after the automatic attempts ran out.

    The helper refuses while one runs and once Caddy is the package.
    """
    if not await asyncio.to_thread(containers.helper_supports, "proxy-switch-start"):
        raise HTTPException(status_code=409, detail=_UNSUPPORTED)
    result = await asyncio.to_thread(containers.proxy_switch_start)
    if not result.ok:
        detail = (result.stderr or result.stdout).strip() or "Could not start the switch"
        raise HTTPException(status_code=409 if "REFUSED" in detail else 500, detail=detail)
    _LOGGER.info("Proxy switch started from the panel")
    return {"status": "started"}
