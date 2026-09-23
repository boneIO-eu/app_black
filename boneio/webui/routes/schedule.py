"""Schedule routes for the boneIO web UI.

The ``schedule:`` section itself is edited like any other config section. What
cannot be read out of the configuration is the part that matters when something
does not work: whether a schedule is actually armed, and for when.

A schedule is also the one kind of action nobody can test by pressing a button,
which is why "run it now" is an endpoint.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from boneio.core.manager import Manager
from boneio.core.manager.scheduler import SOURCE_MANUAL

_LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["schedule"])


def get_manager():
    """Get manager instance - will be overridden by app initialization."""
    raise NotImplementedError("Manager not initialized")


@router.get("/schedule")
async def get_schedule_status(manager: Manager = Depends(get_manager)):
    """What is armed, and when each schedule fires next.

    Returns:
        Dict with a ``schedules`` list; ``next_fire`` is null for a schedule
        that is disabled, has no firing in sight, or is waiting for the clock.
    """
    scheduler = getattr(manager, "scheduler", None)
    if scheduler is None:
        return {"schedules": []}
    return {"schedules": scheduler.status()}


@router.post("/schedule/{schedule_id}/run")
async def run_schedule_now(schedule_id: str, manager: Manager = Depends(get_manager)):
    """Run one schedule immediately, as if it had fired.

    Its conditions still apply — a "run now" that ignored them would be testing
    something other than the schedule. The armed timer is untouched, so the
    next real firing still happens.

    Args:
        schedule_id: The schedule's id.
        manager: Injected manager.

    Returns:
        Status response.

    Raises:
        HTTPException: 404 when no such schedule exists.
    """
    scheduler = getattr(manager, "scheduler", None)
    entry = None
    if scheduler is not None:
        entry = next((e for e in scheduler._entries if e.id == schedule_id), None)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"No schedule with id {schedule_id!r}.")

    _LOGGER.info("Schedule '%s' run manually from the web UI.", schedule_id)
    await scheduler._run(entry, source=SOURCE_MANUAL)
    return {"status": "success", **(scheduler.status_for(entry.id) or {})}


class EnableRequest(BaseModel):
    """Body of the enable/disable call."""

    enabled: bool


@router.post("/schedule/{schedule_id}/enable")
async def set_schedule_enabled(
    schedule_id: str,
    body: EnableRequest,
    manager: Manager = Depends(get_manager),
):
    """Turn one schedule on or off without editing the config.

    The same entry point the Home Assistant switch uses. The choice is
    persisted, so it outlives a restart — until somebody edits ``enabled:`` in
    the config, which is treated as the more deliberate statement of the two
    and wins.

    Args:
        schedule_id: The schedule's id.
        body: ``{"enabled": bool}``.
        manager: Injected manager.

    Returns:
        The schedule's status after the change.

    Raises:
        HTTPException: 404 when no such schedule exists.
    """
    scheduler = getattr(manager, "scheduler", None)
    if scheduler is None or not scheduler.set_enabled(schedule_id, body.enabled):
        raise HTTPException(status_code=404, detail=f"No schedule with id {schedule_id!r}.")
    return {"status": "success", **(scheduler.status_for(schedule_id) or {})}


@router.get("/schedule/{schedule_id}/history")
async def get_schedule_history(schedule_id: str, manager: Manager = Depends(get_manager)):
    """Every run this schedule still remembers, newest last.

    Args:
        schedule_id: The schedule's id.
        manager: Injected manager.

    Returns:
        Dict with a ``history`` list.

    Raises:
        HTTPException: 404 when no such schedule exists.
    """
    scheduler = getattr(manager, "scheduler", None)
    status = scheduler.status_for(schedule_id) if scheduler is not None else None
    if status is None:
        raise HTTPException(status_code=404, detail=f"No schedule with id {schedule_id!r}.")
    return {"id": schedule_id, "history": status.get("history", [])}
