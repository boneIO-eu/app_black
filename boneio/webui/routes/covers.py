"""Cover control routes for BoneIO Web UI."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException

from boneio.components.cover.venetian import VenetianCover
from boneio.core.manager import Manager
from boneio.models.actions import CoverAction, CoverPosition, CoverTilt

if TYPE_CHECKING:
    from boneio.components.cover.previous import PreviousCover
    from boneio.components.cover.time_based import TimeBasedCover

_LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/covers", tags=["covers"])


def get_manager():
    """Get manager instance - will be overridden by app initialization."""
    raise NotImplementedError("Manager not initialized")


@router.post("/{cover_id}/action")
async def cover_action(cover_id: str, action_data: CoverAction, manager: Manager = Depends(get_manager)):
    """
    Control cover with specific action (open, close, stop).
    
    Args:
        cover_id: ID of the cover to control.
        action_data: Action to perform (open, close, stop, toggle).
        manager: Manager instance.
        
    Returns:
        Status response.
        
    Raises:
        HTTPException: 404 if cover not found, 400 if invalid action.
    """
    cover = manager.covers.get_cover(cover_id)
    if not cover:
        raise HTTPException(status_code=404, detail="Cover not found")
    
    action = action_data.action
    if action not in ["open", "close", "stop", "toggle"]:
        raise HTTPException(status_code=400, detail="Invalid action")
    
    if action == "open":
        await cover.open()
    elif action == "close":
        await cover.close()
    elif action == "stop":
        await cover.stop()
    
    return {"status": "success"}


@router.post("/{cover_id}/set_position")
async def set_cover_position(cover_id: str, position_data: CoverPosition, manager: Manager = Depends(get_manager)):
    """
    Set cover position.
    
    Args:
        cover_id: ID of the cover to control.
        position_data: Target position (0-100).
        manager: Manager instance.
        
    Returns:
        Status response.
        
    Raises:
        HTTPException: 404 if cover not found, 400 if invalid position.
    """
    cover = manager.covers.get_cover(cover_id)
    if not cover:
        raise HTTPException(status_code=404, detail="Cover not found")
    
    position = position_data.position
    if position < 0 or position > 100:
        raise HTTPException(status_code=400, detail="Invalid position")
    
    await cover.set_cover_position(position)
    
    return {"status": "success"}


@router.post("/{cover_id}/set_tilt")
async def set_cover_tilt(cover_id: str, tilt_data: CoverTilt, manager: Manager = Depends(get_manager)):
    """
    Set cover tilt position (for venetian blinds).
    
    Args:
        cover_id: ID of the cover to control.
        tilt_data: Target tilt position (0-100).
        manager: Manager instance.
        
    Returns:
        Status response.
        
    Raises:
        HTTPException: 404 if cover not found, 400 if invalid tilt or cover type.
    """
    cover: PreviousCover | TimeBasedCover | VenetianCover | None = manager.covers.get_cover(cover_id)
    if not cover:
        raise HTTPException(status_code=404, detail="Cover not found")
    if cover.kind != "venetian":
        raise HTTPException(status_code=400, detail="Invalid cover type")
    
    tilt = tilt_data.tilt
    if tilt < 0 or tilt > 100:
        raise HTTPException(status_code=400, detail="Invalid tilt")
    
    if isinstance(cover, VenetianCover):
        await cover.set_tilt(tilt)
    else:
        raise HTTPException(status_code=400, detail="Cover does not support tilt control")
    
    return {"status": "success"}
