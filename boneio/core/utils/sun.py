"""Solar position and solar event times.

Pure maths: no config, no I/O, no cached state. Everything the rest of boneIO
needs about the Sun is derived here from a latitude, a longitude and an instant.

Algorithm: NOAA Solar Calculator (a simplified Meeus). Measured against
`astral` over a full year for eight cities spanning both hemispheres, every
event agrees to within 41 s up to |latitude| ~62°.

The exception is a *grazing* event — one where the Sun barely reaches the
threshold, so it happens near solar midnight and the crossing is nearly
tangential. There the time of the event is extremely sensitive to the angle and
implementations diverge by minutes (Reykjavik's civil dusk in late May differs
from astral's by ~3 min; a day later astral refuses to compute it at all).
Nothing that drives a relay cares, and no amount of iteration fixes the
underlying conditioning.

Events are anchored to **solar noon**, not to the calendar: the civil dusk of a
day is the one that follows that day's noon, even when it lands after local
midnight. Anything else would make "dusk today" mean yesterday's dusk during
the light half of the year at northern latitudes.

Two conventions matter and are easy to mix up:

* **Geometric elevation** — the true angle of the Sun's centre above the
  horizon, ignoring the atmosphere. Every threshold in this module is
  geometric, including ``SUNRISE_SUNSET = -0.833°``, which already bakes in
  mean refraction and the solar semi-diameter by definition.
* **Apparent elevation** — what an observer actually sees, i.e. geometric plus
  atmospheric refraction. Use :func:`apparent_elevation` for display only.

Mixing the two would make ``phase_of()`` disagree with the event times from
:func:`event_time` near the horizon, so the logic layer uses geometric
throughout.

Example:
    >>> from datetime import date
    >>> from zoneinfo import ZoneInfo
    >>> anchors = all_anchors(52.2297, 21.0122, date(2025, 6, 21), ZoneInfo("Europe/Warsaw"))
    >>> anchors["sunrise"].astimezone(ZoneInfo("Europe/Warsaw")).strftime("%H:%M")
    '04:14'
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, time, timedelta, tzinfo

__all__ = [
    "ANCHOR_NAMES",
    "ANCHORS",
    "ASTRONOMICAL",
    "BLUE_HOUR_HIGH",
    "CIVIL",
    "GOLDEN_HOUR_HIGH",
    "GOLDEN_HOUR_LOW",
    "NAUTICAL",
    "PHASE_NAMES",
    "SUNRISE_SUNSET",
    "all_anchors",
    "apparent_elevation",
    "event_time",
    "horizon_dip",
    "in_phase",
    "phase_of",
    "solar_noon",
    "solar_position",
    "threshold_state",
]

# ── Elevation thresholds (degrees, geometric) ────────────────────────────────

#: Upper limb touching the horizon: 16' semi-diameter + 34' mean refraction.
SUNRISE_SUNSET = -0.833
#: Civil twilight — outdoor activity still possible without artificial light.
CIVIL = -6.0
#: Nautical twilight — horizon at sea still discernible.
NAUTICAL = -12.0
#: Astronomical twilight — sky indistinguishable from full night above this.
ASTRONOMICAL = -18.0
#: Golden hour spans -4°..+6°; blue hour the -6°..-4° band below it.
GOLDEN_HOUR_LOW = -4.0
GOLDEN_HOUR_HIGH = 6.0
BLUE_HOUR_HIGH = -4.0

#: Anchor name → (threshold in degrees, sun is rising).
#:
#: Some anchors deliberately share an instant: the blue hour ends exactly where
#: the golden hour begins, and its other edge is civil twilight by definition.
#: Two names for one moment is the photographic convention, not a bug.
ANCHORS: dict[str, tuple[float, bool]] = {
    "astronomical_dawn": (ASTRONOMICAL, True),
    "nautical_dawn": (NAUTICAL, True),
    "civil_dawn": (CIVIL, True),
    "blue_hour_morning_start": (CIVIL, True),
    "blue_hour_morning_end": (BLUE_HOUR_HIGH, True),
    "golden_hour_morning_start": (GOLDEN_HOUR_LOW, True),
    "sunrise": (SUNRISE_SUNSET, True),
    "golden_hour_morning_end": (GOLDEN_HOUR_HIGH, True),
    "golden_hour_evening_start": (GOLDEN_HOUR_HIGH, False),
    "sunset": (SUNRISE_SUNSET, False),
    "golden_hour_evening_end": (GOLDEN_HOUR_LOW, False),
    "blue_hour_evening_start": (BLUE_HOUR_HIGH, False),
    "blue_hour_evening_end": (CIVIL, False),
    "civil_dusk": (CIVIL, False),
    "nautical_dusk": (NAUTICAL, False),
    "astronomical_dusk": (ASTRONOMICAL, False),
}

#: Every anchor a condition may reference, threshold-based ones plus the two
#: extrema, which exist on every day at every latitude.
ANCHOR_NAMES: tuple[str, ...] = (*ANCHORS.keys(), "solar_noon", "solar_midnight")

#: Phases usable as a membership test. ``golden_hour`` and ``blue_hour`` overlap
#: ``day`` and ``civil_twilight`` — this is a set of predicates, not a partition.
PHASE_NAMES: tuple[str, ...] = (
    "day",
    "civil_twilight",
    "nautical_twilight",
    "astronomical_twilight",
    "night",
    "golden_hour",
    "blue_hour",
)

# Latitude is clamped before any cos(lat) division: exactly ±90° would make the
# hour-angle denominator zero, and no boneIO is installed on a pole.
_MAX_LATITUDE = 89.9

_UNIX_EPOCH_JD = 2440587.5
_J2000 = 2451545.0


# ── NOAA core ────────────────────────────────────────────────────────────────


def _julian_century(when: datetime) -> float:
    """Julian centuries since J2000.0 for an aware instant."""
    julian_day = when.timestamp() / 86400.0 + _UNIX_EPOCH_JD
    return (julian_day - _J2000) / 36525.0


def _declination_and_eot(jc: float) -> tuple[float, float]:
    """Solar declination (degrees) and the equation of time (minutes)."""
    mean_long = (280.46646 + jc * (36000.76983 + jc * 0.0003032)) % 360.0
    mean_anom = 357.52911 + jc * (35999.05029 - 0.0001537 * jc)
    eccentricity = 0.016708634 - jc * (0.000042037 + 0.0000001267 * jc)

    anom_rad = math.radians(mean_anom)
    centre = (
        math.sin(anom_rad) * (1.914602 - jc * (0.004817 + 0.000014 * jc))
        + math.sin(2 * anom_rad) * (0.019993 - 0.000101 * jc)
        + math.sin(3 * anom_rad) * 0.000289
    )

    omega = 125.04 - 1934.136 * jc
    apparent_long = mean_long + centre - 0.00569 - 0.00478 * math.sin(math.radians(omega))

    mean_obliquity = 23.0 + (26.0 + (21.448 - jc * (46.815 + jc * (0.00059 - jc * 0.001813))) / 60.0) / 60.0
    obliquity = mean_obliquity + 0.00256 * math.cos(math.radians(omega))

    declination = math.degrees(math.asin(math.sin(math.radians(obliquity)) * math.sin(math.radians(apparent_long))))

    y = math.tan(math.radians(obliquity / 2.0)) ** 2
    long_rad = math.radians(mean_long)
    eot = 4.0 * math.degrees(
        y * math.sin(2 * long_rad)
        - 2 * eccentricity * math.sin(anom_rad)
        + 4 * eccentricity * y * math.sin(anom_rad) * math.cos(2 * long_rad)
        - 0.5 * y * y * math.sin(4 * long_rad)
        - 1.25 * eccentricity * eccentricity * math.sin(2 * anom_rad)
    )
    return declination, eot


def _clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _require_aware(when: datetime) -> datetime:
    if when.tzinfo is None:
        raise ValueError("solar calculations need an aware datetime, got a naive one")
    return when


def _check_coords(latitude: float, longitude: float) -> None:
    if not -90.0 <= latitude <= 90.0:
        raise ValueError(f"latitude out of range: {latitude}")
    if not -180.0 <= longitude <= 180.0:
        raise ValueError(f"longitude out of range: {longitude}")


# ── Public: instantaneous position ───────────────────────────────────────────


def solar_position(latitude: float, longitude: float, when: datetime) -> tuple[float, float]:
    """Geometric elevation and azimuth of the Sun, both in degrees.

    Args:
        latitude: Degrees north, -90..90.
        longitude: Degrees east, -180..180.
        when: An aware datetime. Naive input is rejected rather than guessed at.

    Returns:
        ``(elevation, azimuth)``. Elevation is geometric — see the module
        docstring. Azimuth is measured clockwise from true north.
    """
    _check_coords(latitude, longitude)
    when = _require_aware(when)

    jc = _julian_century(when)
    declination, eot = _declination_and_eot(jc)

    utc = when.astimezone(UTC)
    minutes = utc.hour * 60.0 + utc.minute + utc.second / 60.0 + utc.microsecond / 6.0e7
    true_solar_time = (minutes + eot + 4.0 * longitude) % 1440.0
    hour_angle = true_solar_time / 4.0 - 180.0

    lat_rad = math.radians(_clamp(latitude, -_MAX_LATITUDE, _MAX_LATITUDE))
    decl_rad = math.radians(declination)
    ha_rad = math.radians(hour_angle)

    cos_zenith = _clamp(
        math.sin(lat_rad) * math.sin(decl_rad) + math.cos(lat_rad) * math.cos(decl_rad) * math.cos(ha_rad)
    )
    zenith = math.acos(cos_zenith)
    elevation = 90.0 - math.degrees(zenith)

    denominator = math.cos(lat_rad) * math.sin(zenith)
    if abs(denominator) < 1e-12:
        # Sun directly overhead or at the zenith of a pole: azimuth undefined,
        # report the meridian rather than dividing by ~zero.
        azimuth = 180.0 if latitude >= 0 else 0.0
    else:
        cos_azimuth = _clamp((math.sin(lat_rad) * cos_zenith - math.sin(decl_rad)) / denominator)
        acos_az = math.degrees(math.acos(cos_azimuth))
        azimuth = (acos_az + 180.0) % 360.0 if hour_angle > 0 else (540.0 - acos_az) % 360.0

    return elevation, azimuth


def apparent_elevation(geometric: float) -> float:
    """Add mean atmospheric refraction to a geometric elevation.

    For display only. Every threshold in this module is geometric, so feeding
    this back into :func:`phase_of` would disagree with :func:`event_time`.
    """
    if geometric > 85.0:
        return geometric
    tan_e = math.tan(math.radians(geometric))
    if geometric > 5.0:
        refraction = 58.1 / tan_e - 0.07 / tan_e**3 + 0.000086 / tan_e**5
    elif geometric > -0.575:
        refraction = 1735.0 + geometric * (-518.2 + geometric * (103.4 + geometric * (-12.79 + geometric * 0.711)))
    else:
        refraction = -20.772 / tan_e
    return geometric + refraction / 3600.0


def horizon_dip(elevation_m: float) -> float:
    """Degrees the horizon drops for an observer `elevation_m` above sea level.

    110 m of altitude lowers the horizon by ~0.37°, which shifts sunrise in
    central Europe by roughly two minutes — small, but larger than the error of
    the algorithm itself, so it is worth applying rather than ignoring.
    """
    if elevation_m <= 0.0:
        return 0.0
    return 0.0353 * math.sqrt(elevation_m)


# ── Public: event times ──────────────────────────────────────────────────────


def solar_noon(longitude: float, day: date, tz: tzinfo) -> datetime:
    """Local solar noon of `day` as observed in `tz`, returned as aware UTC.

    Independent of latitude: solar noon is when the Sun crosses the meridian.
    """
    _check_coords(0.0, longitude)
    guess = datetime.combine(day, time(12, 0), tzinfo=tz).astimezone(UTC)
    for _ in range(2):
        _, eot = _declination_and_eot(_julian_century(guess))
        minutes = guess.hour * 60.0 + guess.minute + guess.second / 60.0
        true_solar_time = minutes + eot + 4.0 * longitude
        # Wrap the correction into (-720, 720] so we land on the solar noon
        # nearest the guess rather than one a day away.
        delta = ((720.0 - true_solar_time + 720.0) % 1440.0) - 720.0
        guess = guess + timedelta(minutes=delta)
    return guess


def _hour_angle(latitude: float, declination: float, threshold: float) -> float | None:
    """Half-length of the day above `threshold`, in degrees, or None.

    None means the Sun does not cross the threshold at all on that day —
    :func:`threshold_state` says on which side it stays.
    """
    lat_rad = math.radians(_clamp(latitude, -_MAX_LATITUDE, _MAX_LATITUDE))
    decl_rad = math.radians(declination)
    cos_ha = (math.sin(math.radians(threshold)) - math.sin(lat_rad) * math.sin(decl_rad)) / (
        math.cos(lat_rad) * math.cos(decl_rad)
    )
    if cos_ha < -1.0 or cos_ha > 1.0:
        return None
    return math.degrees(math.acos(cos_ha))


def threshold_state(
    latitude: float,
    longitude: float,
    day: date,
    tz: tzinfo,
    threshold: float,
    elevation_m: float = 0.0,
) -> str:
    """Whether the Sun crosses `threshold` on `day`, and if not, on which side.

    Returns ``"crosses"``, ``"always_above"`` or ``"always_below"``. Callers use
    this to turn a missing anchor into a sensible window: during polar day a
    ``sunrise → sunset`` window covers the whole day, during polar night it is
    empty, and getting that backwards would leave lights on for a month.
    """
    _check_coords(latitude, longitude)
    effective = threshold - horizon_dip(elevation_m)
    noon = solar_noon(longitude, day, tz)
    declination, _ = _declination_and_eot(_julian_century(noon))
    if _hour_angle(latitude, declination, effective) is not None:
        return "crosses"
    elevation, _ = solar_position(latitude, longitude, noon)
    return "always_above" if elevation > effective else "always_below"


def event_time(
    latitude: float,
    longitude: float,
    day: date,
    tz: tzinfo,
    threshold: float,
    *,
    rising: bool,
    elevation_m: float = 0.0,
) -> datetime | None:
    """When the Sun crosses `threshold` on `day`, as aware UTC.

    Args:
        latitude: Degrees north.
        longitude: Degrees east.
        day: The local date, as seen in `tz`.
        tz: Timezone that defines which day is meant.
        threshold: Geometric elevation in degrees (e.g. ``SUNRISE_SUNSET``).
        rising: True for the morning crossing, False for the evening one.
        elevation_m: Observer height above sea level, metres.

    Returns:
        The crossing instant, or None if the Sun stays on one side of the
        threshold all day (polar day or polar night). Use
        :func:`threshold_state` to find out which.
    """
    _check_coords(latitude, longitude)
    effective = threshold - horizon_dip(elevation_m)
    noon = solar_noon(longitude, day, tz)

    estimate = noon
    result: datetime | None = None
    # Two passes: the first uses the declination at noon, the second the
    # declination at the estimated event. Without the refinement the error grows
    # to a couple of minutes near the equinoxes, when declination moves fastest.
    for _ in range(2):
        declination, _ = _declination_and_eot(_julian_century(estimate))
        hour_angle = _hour_angle(latitude, declination, effective)
        if hour_angle is None:
            return None
        offset = -hour_angle if rising else hour_angle
        estimate = noon + timedelta(minutes=4.0 * offset)
        result = estimate
    return result


def all_anchors(
    latitude: float,
    longitude: float,
    day: date,
    tz: tzinfo,
    elevation_m: float = 0.0,
) -> dict[str, datetime | None]:
    """Every anchor of one local day, as aware UTC.

    This is the call a per-day cache is built on: the conditions layer resolves
    names against the returned dict instead of recomputing ephemerides on a
    button press. Values are None for anchors the Sun does not reach that day.
    """
    _check_coords(latitude, longitude)
    noon = solar_noon(longitude, day, tz)
    anchors: dict[str, datetime | None] = {
        "solar_noon": noon,
        "solar_midnight": noon - timedelta(hours=12),
    }
    for name, (threshold, rising) in ANCHORS.items():
        anchors[name] = event_time(
            latitude,
            longitude,
            day,
            tz,
            threshold,
            rising=rising,
            elevation_m=elevation_m,
        )
    return anchors


# ── Public: phases ───────────────────────────────────────────────────────────


def phase_of(elevation: float) -> str:
    """Name the basic phase for a geometric elevation.

    Only the five phases that partition the day are returned; golden and blue
    hour overlap them and are tested with :func:`in_phase`.
    """
    if elevation > SUNRISE_SUNSET:
        return "day"
    if elevation > CIVIL:
        return "civil_twilight"
    if elevation > NAUTICAL:
        return "nautical_twilight"
    if elevation > ASTRONOMICAL:
        return "astronomical_twilight"
    return "night"


def in_phase(elevation: float, phase: str) -> bool:
    """Whether a geometric elevation falls inside a named phase."""
    if phase == "golden_hour":
        return GOLDEN_HOUR_LOW <= elevation <= GOLDEN_HOUR_HIGH
    if phase == "blue_hour":
        return CIVIL <= elevation < BLUE_HOUR_HIGH
    if phase not in PHASE_NAMES:
        raise ValueError(f"unknown sun phase: {phase!r}")
    return phase_of(elevation) == phase
