"""Where the Sun is, for the rest of boneIO.

:mod:`boneio.core.utils.sun` is pure maths and knows nothing about this device.
This is the layer that gives it a place and a clock: it reads the configured
coordinates, resolves the system timezone, caches a day's anchors so a button
press never computes an ephemeris, and refuses to answer at all while the clock
is obviously wrong.

Everything returned is timezone-aware. Callers that need local wall-clock times
convert at the edge; nothing inside works with naive datetimes.

Usage:
    provider = SunProvider(config.get("location"))
    if provider.configured:
        anchors = provider.anchors(datetime.now().astimezone())
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, tzinfo
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from boneio.core.utils import sun

_LOGGER = logging.getLogger("boneio.sun")

#: Below this date the clock has not been set. The BeagleBone has no
#: battery-backed RTC, so between power-on and the first NTP reply it reports
#: something near the epoch. Computing sunset for 1970 and arming anything
#: against it is worse than answering "not yet".
_CLOCK_SANE_FROM = date(2025, 1, 1)

#: Days of anchors kept at once. Two would do — today and tomorrow, for the
#: "next sunrise" sensors — three leaves room for a query about yesterday
#: without evicting them.
_ANCHOR_CACHE_DAYS = 3

#: How long an elevation reading is reused. The Sun moves at most 0.25°/minute,
#: which is below the resolution of any threshold worth configuring.
_ELEVATION_TTL = timedelta(seconds=60)

_ETC_TIMEZONE = Path("/etc/timezone")
_ETC_LOCALTIME = Path("/etc/localtime")
_ZONEINFO_ROOT = Path("/usr/share/zoneinfo")


def local_timezone() -> tzinfo:
    """Resolve the system timezone as a real zone, not a fixed offset.

    ``datetime.now().astimezone().tzinfo`` looks like the answer but is not: it
    is the offset in force *right now*, frozen. Ask it about a day in the other
    half of the year and it applies today's DST offset to it, which moves every
    anchor by an hour twice a year.

    Returns:
        The system's IANA zone, or its current fixed offset if the zone cannot
        be identified.
    """
    try:
        name = _ETC_TIMEZONE.read_text(encoding="utf-8").strip()
        if name:
            return ZoneInfo(name)
    except (OSError, ZoneInfoNotFoundError, ValueError):
        pass

    try:
        resolved = _ETC_LOCALTIME.resolve()
        if resolved.is_relative_to(_ZONEINFO_ROOT):
            return ZoneInfo(str(resolved.relative_to(_ZONEINFO_ROOT)))
    except (OSError, ZoneInfoNotFoundError, ValueError):
        pass

    _LOGGER.warning(
        "Could not identify the system timezone; falling back to the current "
        "UTC offset. Sun times more than a few months away may be off by an hour."
    )
    return datetime.now().astimezone().tzinfo  # type: ignore[return-value]


class SunProvider:
    """The device's view of the Sun: configured position, cached per day.

    Attributes:
        latitude: Degrees north, or None when unconfigured.
        longitude: Degrees east, or None when unconfigured.
        elevation_m: Height above sea level in metres.
    """

    __slots__ = (
        "latitude",
        "longitude",
        "elevation_m",
        "_tz",
        "_anchor_cache",
        "_elevation_cache",
        "_warned_unconfigured",
        "_warned_clock",
    )

    def __init__(self, location: dict | None = None) -> None:
        """Build a provider from the ``location:`` config section.

        Args:
            location: The parsed section, or None when it is absent.
        """
        self.latitude: float | None = None
        self.longitude: float | None = None
        self.elevation_m: float = 0.0
        self._tz: tzinfo | None = None
        # Keyed by (local date, timezone). Small on purpose: "today" plus
        # "tomorrow" is all anyone asks for, and an unbounded dict on a device
        # that runs for months is a leak nobody would notice.
        self._anchor_cache: dict[tuple[date, str], dict[str, datetime | None]] = {}
        self._elevation_cache: tuple[datetime, float, float] | None = None
        self._warned_unconfigured = False
        self._warned_clock = False
        self.configure(location)

    # ── configuration ────────────────────────────────────────────────────

    def configure(self, location: dict | None) -> None:
        """Adopt a new ``location:`` section and drop every cached answer.

        Args:
            location: The parsed section, or None to become unconfigured.
        """
        if not location:
            self.latitude = self.longitude = None
            self.elevation_m = 0.0
            self.invalidate()
            return

        try:
            latitude = float(location["latitude"])
            longitude = float(location["longitude"])
        except (KeyError, TypeError, ValueError):
            _LOGGER.error(
                "location: needs both latitude and longitude as numbers; got %r. "
                "Sun-based features stay disabled.",
                location,
            )
            self.latitude = self.longitude = None
            self.invalidate()
            return

        if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
            _LOGGER.error(
                "location: %s, %s is outside the valid range. "
                "Sun-based features stay disabled.",
                latitude,
                longitude,
            )
            self.latitude = self.longitude = None
            self.invalidate()
            return

        if latitude == 0.0 and longitude == 0.0:
            # Null Island is in the Gulf of Guinea. Nobody installs a controller
            # there; this is what an unfilled form looks like.
            _LOGGER.warning(
                "location: is 0, 0 — almost certainly left unset. Sun times will "
                "be computed for the Gulf of Guinea."
            )

        self.latitude = latitude
        self.longitude = longitude
        try:
            self.elevation_m = float(location.get("elevation") or 0.0)
        except (TypeError, ValueError):
            self.elevation_m = 0.0
        self.invalidate()
        _LOGGER.info(
            "Sun position configured for %.4f, %.4f (%.0f m).",
            latitude,
            longitude,
            self.elevation_m,
        )

    @property
    def configured(self) -> bool:
        """Whether a usable location is set."""
        return self.latitude is not None and self.longitude is not None

    def invalidate(self) -> None:
        """Drop cached anchors, elevation and timezone.

        Call after the config changes, after the timezone changes, and after the
        clock jumps — each of those makes every cached answer wrong in a way the
        cache key alone would not catch.
        """
        self._tz = None
        self._anchor_cache.clear()
        self._elevation_cache = None

    @property
    def timezone(self) -> tzinfo:
        """The system timezone, resolved once and cached until invalidated."""
        if self._tz is None:
            self._tz = local_timezone()
        return self._tz

    # ── readiness ────────────────────────────────────────────────────────

    def clock_ready(self, now: datetime | None = None) -> bool:
        """Whether the system clock has been set to something plausible.

        Returns:
            False before the first time synchronisation after a cold boot.
        """
        current = (now or datetime.now().astimezone()).date()
        if current >= _CLOCK_SANE_FROM:
            return True
        if not self._warned_clock:
            self._warned_clock = True
            _LOGGER.warning(
                "System clock reads %s, so it has not been set yet. Sun-based "
                "features stay inactive until NTP synchronises. If this device "
                "has no route to the internet, configure a local NTP server.",
                current,
            )
        return False

    def ready(self, now: datetime | None = None) -> bool:
        """Whether sun questions can be answered at all."""
        if not self.configured:
            if not self._warned_unconfigured:
                self._warned_unconfigured = True
                _LOGGER.error(
                    "A sun-based feature is in use but no location: section is "
                    "configured. Set the coordinates in Settings → Location."
                )
            return False
        return self.clock_ready(now)

    # ── answers ──────────────────────────────────────────────────────────

    def anchors(self, now: datetime | None = None) -> dict[str, datetime | None]:
        """Every sun anchor of the local day containing *now*, as aware UTC.

        Computed once per local day and reused. The cache key carries the
        timezone as well as the date, so changing the timezone from the panel
        cannot leave yesterday's answers in place.

        Args:
            now: Aware datetime; defaults to the current local time.

        Returns:
            Anchor name → instant, with None for anchors the Sun does not reach
            that day. Empty when :meth:`ready` is False.
        """
        now = self._now(now)
        if not self.ready(now):
            return {}

        return self._anchors_for(now.astimezone(self.timezone).date())

    def _anchors_for(self, day: date) -> dict[str, datetime | None]:
        """Anchors of one local date, computed once and cached."""
        tz = self.timezone
        key = (day, str(tz))
        cached = self._anchor_cache.get(key)
        if cached is not None:
            return cached

        computed = sun.all_anchors(
            self.latitude, self.longitude, day, tz, self.elevation_m
        )
        if len(self._anchor_cache) >= _ANCHOR_CACHE_DAYS:
            self._anchor_cache.clear()
        self._anchor_cache[key] = computed
        return computed

    def anchor(self, name: str, now: datetime | None = None) -> datetime | None:
        """One anchor of the current local day.

        Args:
            name: An entry of :data:`boneio.core.utils.sun.ANCHOR_NAMES`.
            now: Aware datetime; defaults to the current local time.

        Returns:
            The instant, or None when unavailable that day or not ready.

        Raises:
            KeyError: If *name* is not an anchor.
        """
        anchors = self.anchors(now)
        if not anchors:
            return None
        if name not in anchors:
            raise KeyError(f"unknown sun anchor: {name!r}")
        return anchors[name]

    def next_anchor(self, name: str, now: datetime | None = None) -> datetime | None:
        """The next occurrence of an anchor, today's or tomorrow's.

        Looks at the current local day first and moves on when that instant has
        already passed. Days where the anchor does not exist (polar) are
        skipped, up to a week — past that the answer is honestly "not soon",
        and returning a date three months out would be worse than None.

        Args:
            name: An entry of :data:`boneio.core.utils.sun.ANCHOR_NAMES`.
            now: Aware datetime; defaults to the current local time.

        Returns:
            The instant, or None when not ready or not within a week.

        Raises:
            KeyError: If *name* is not an anchor.
        """
        now = self._now(now)
        if not self.ready(now):
            return None
        if name not in sun.ANCHOR_NAMES:
            raise KeyError(f"unknown sun anchor: {name!r}")

        day = now.astimezone(self.timezone).date()
        for offset in range(8):
            moment = self._anchors_for(day + timedelta(days=offset)).get(name)
            if moment is not None and moment > now:
                return moment
        return None

    def position(self, now: datetime | None = None) -> tuple[float, float] | None:
        """Geometric elevation and azimuth right now, cached for a minute.

        Returns:
            ``(elevation, azimuth)`` in degrees, or None when not ready.
        """
        now = self._now(now)
        if not self.ready(now):
            return None

        cached = self._elevation_cache
        if cached and abs(now - cached[0]) < _ELEVATION_TTL:
            return cached[1], cached[2]

        elevation, azimuth = sun.solar_position(self.latitude, self.longitude, now)
        self._elevation_cache = (now, elevation, azimuth)
        return elevation, azimuth

    def elevation(self, now: datetime | None = None) -> float | None:
        """Geometric elevation in degrees, or None when not ready."""
        position = self.position(now)
        return None if position is None else position[0]

    def phase(self, now: datetime | None = None) -> str | None:
        """Current basic phase (``day`` … ``night``), or None when not ready."""
        elevation = self.elevation(now)
        return None if elevation is None else sun.phase_of(elevation)

    def in_phase(self, phase: str, now: datetime | None = None) -> bool | None:
        """Whether the Sun is currently in *phase*, or None when not ready."""
        elevation = self.elevation(now)
        return None if elevation is None else sun.in_phase(elevation, phase)

    def threshold_state(self, threshold: float, now: datetime | None = None) -> str | None:
        """Whether the Sun crosses *threshold* today, and otherwise on which side.

        Returns:
            ``"crosses"``, ``"always_above"``, ``"always_below"``, or None when
            not ready.
        """
        now = self._now(now)
        if not self.ready(now):
            return None
        tz = self.timezone
        return sun.threshold_state(
            self.latitude,
            self.longitude,
            now.astimezone(tz).date(),
            tz,
            threshold,
            self.elevation_m,
        )

    # ── helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _now(now: datetime | None) -> datetime:
        """Return an aware *now*, rejecting naive input from callers."""
        if now is None:
            return datetime.now().astimezone()
        if now.tzinfo is None:
            raise ValueError("SunProvider needs an aware datetime, got a naive one")
        return now
