"""Sun routes for the boneIO web UI.

One endpoint, deliberately. The panel needs today's anchors *and* the Sun's
current position together — showing the times without the live elevation makes
it impossible to tell a wrong latitude from a wrong clock — and polling two
endpoints to draw one card is how they drift apart.

The maths lives in ``boneio.core.utils.sun`` and is never reimplemented in
TypeScript: one source of truth, one set of tests.
"""

from __future__ import annotations

import logging
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from boneio.core.manager import Manager
from boneio.core.utils import sun as sun_utils

_LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["sun"])


def get_manager():
    """Get manager instance - will be overridden by app initialization."""
    raise NotImplementedError("Manager not initialized")


def _map_tiles_enabled(manager: Manager) -> bool:
    """Whether the Location page may show a map.

    Reported here rather than from a page of its own because the page that asks
    about the Sun is exactly the page that wants the map, and a second request
    to learn one boolean is a second thing that can be out of step.
    """
    try:
        config = manager.config_helper.get_config() or {}
        return bool(((config.get("web") or {}).get("security") or {}).get("map_tiles"))
    except Exception:  # noqa: BLE001 - never fail the whole page over a flag
        return False


def _as_local_iso(value: datetime | None, tz) -> str | None:
    """Render an aware UTC instant in the device's timezone, or None.

    None is a real answer here, not a missing one: it is what an anchor looks
    like on a day the Sun never reaches that angle.
    """
    return None if value is None else value.astimezone(tz).isoformat()


@router.get("/sun/today")
async def get_sun_today(
    day: str | None = Query(
        default=None,
        description="Local date as YYYY-MM-DD. Defaults to today on the device.",
    ),
    manager: Manager = Depends(get_manager),
):
    """Sun anchors for one local day, plus the Sun's position right now.

    Args:
        day: Optional local date; defaults to the device's today.
        manager: Injected manager, which owns the provider.

    Returns:
        Dict with the configured location, the day's anchors as local ISO
        timestamps, the current position, and the polar state of the horizon.

    Raises:
        HTTPException: 400 for an unparseable date.
    """
    provider = manager.sun

    if not provider.configured:
        return {
            "configured": False,
            "ready": False,
            "reason": "no_location",
            "anchors": {},
            "map_tiles": _map_tiles_enabled(manager),
        }

    if not provider.clock_ready():
        # Answering with sunset for 1970 would look like a working feature.
        return {
            "configured": True,
            "ready": False,
            "reason": "clock_not_set",
            "anchors": {},
            "latitude": provider.latitude,
            "longitude": provider.longitude,
            "elevation": provider.elevation_m,
            "map_tiles": _map_tiles_enabled(manager),
        }

    tz = provider.timezone

    if day:
        try:
            requested = date.fromisoformat(day)
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail=f"Invalid date: {day!r}. Use YYYY-MM-DD."
            ) from exc
        anchors = sun_utils.all_anchors(
            provider.latitude, provider.longitude, requested, tz, provider.elevation_m
        )
    else:
        requested = datetime.now(tz).date()
        anchors = provider.anchors()

    position = provider.position()
    elevation, azimuth = position if position else (None, None)

    return {
        "configured": True,
        "ready": True,
        "latitude": provider.latitude,
        "longitude": provider.longitude,
        "elevation": provider.elevation_m,
        "timezone": str(tz),
        "map_tiles": _map_tiles_enabled(manager),
        "date": requested.isoformat(),
        "anchors": {name: _as_local_iso(value, tz) for name, value in anchors.items()},
        "now": {
            "elevation": None if elevation is None else round(elevation, 2),
            "azimuth": None if azimuth is None else round(azimuth, 2),
            "phase": None if elevation is None else sun_utils.phase_of(elevation),
            "golden_hour": None
            if elevation is None
            else sun_utils.in_phase(elevation, "golden_hour"),
            "blue_hour": None
            if elevation is None
            else sun_utils.in_phase(elevation, "blue_hour"),
        },
        # Which side of the horizon the Sun stays on when it never crosses it.
        # Without this a caller cannot tell polar day from polar night: both
        # report sunrise and sunset as null.
        "horizon_state": sun_utils.threshold_state(
            provider.latitude,
            provider.longitude,
            requested,
            tz,
            sun_utils.SUNRISE_SUNSET,
            provider.elevation_m,
        ),
    }
