"""Tests for the solar engine (`boneio/core/utils/sun.py`).

Two kinds of check live here:

* **Physics invariants** — noon elevation, the equation-of-time extremes, polar
  day and night, hemisphere symmetry. These stand on their own and do not need
  any external reference.
* **Published almanac values** for a handful of cities and dates, with a 90 s
  tolerance. The algorithm claims ~1 min, so a failure here means a real
  regression rather than rounding noise.

`astral` is a test-only dependency used for a wider cross-check. It is
deliberately *not* a runtime dependency: shipping a package to the device for
~250 lines of trigonometry is a worse trade than owning the maths and pinning
it down with these tests.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from boneio.core.utils import sun

WARSAW = ZoneInfo("Europe/Warsaw")
OSLO = ZoneInfo("Europe/Oslo")
SYDNEY = ZoneInfo("Australia/Sydney")

TOLERANCE = timedelta(seconds=90)

#: Anchors in the order they must occur during one day. Entries that share an
#: instant by definition (civil dawn is the start of the blue hour) are listed
#: next to each other and only checked as non-decreasing.
CHRONOLOGICAL = (
    "astronomical_dawn",
    "nautical_dawn",
    "civil_dawn",
    "blue_hour_morning_start",
    "blue_hour_morning_end",
    "golden_hour_morning_start",
    "sunrise",
    "golden_hour_morning_end",
    "solar_noon",
    "golden_hour_evening_start",
    "sunset",
    "golden_hour_evening_end",
    "blue_hour_evening_start",
    "blue_hour_evening_end",
    "civil_dusk",
    "nautical_dusk",
    "astronomical_dusk",
)


def _local(anchors: dict[str, datetime | None], name: str, tz) -> datetime:
    value = anchors[name]
    assert value is not None, f"{name} unexpectedly missing"
    return value.astimezone(tz)


def _hhmm(anchors: dict[str, datetime | None], name: str, tz) -> str:
    return _local(anchors, name, tz).strftime("%H:%M")


# ── Published almanac values ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("day", "sunrise", "sunset"),
    [
        (date(2025, 6, 21), "04:14", "21:01"),  # summer solstice
        (date(2025, 12, 21), "07:43", "15:25"),  # winter solstice
        (date(2025, 3, 20), "05:38", "17:49"),  # spring equinox
    ],
)
def test_warsaw_sunrise_sunset(day: date, sunrise: str, sunset: str) -> None:
    anchors = sun.all_anchors(52.2297, 21.0122, day, WARSAW)
    assert _hhmm(anchors, "sunrise", WARSAW) == sunrise
    assert _hhmm(anchors, "sunset", WARSAW) == sunset


def test_sydney_winter_solstice_is_the_short_day() -> None:
    """Southern hemisphere: June is winter, so the day must be the shortest."""
    anchors = sun.all_anchors(-33.8688, 151.2093, date(2025, 6, 21), SYDNEY)
    assert _hhmm(anchors, "sunrise", SYDNEY) == "07:00"
    assert _hhmm(anchors, "sunset", SYDNEY) == "16:53"

    december = sun.all_anchors(-33.8688, 151.2093, date(2025, 12, 21), SYDNEY)
    june_length = anchors["sunset"] - anchors["sunrise"]
    december_length = december["sunset"] - december["sunrise"]
    assert december_length > june_length


# ── Physics invariants ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        # The equation of time has well-known extremes: about +16.4 min in early
        # November (solar noon early) and -14.2 min in mid-February (late).
        (date(2025, 4, 15), "11:59"),
        (date(2025, 11, 3), "11:43"),
        (date(2025, 2, 11), "12:14"),
    ],
)
def test_equation_of_time_extremes_at_greenwich(day: date, expected: str) -> None:
    noon = sun.solar_noon(0.0, day, UTC)
    assert noon.strftime("%H:%M") == expected


def test_noon_elevation_matches_latitude_and_declination() -> None:
    """At solar noon, elevation = 90 - |latitude - declination|."""
    latitude = 52.2297
    noon = sun.solar_noon(21.0122, date(2025, 6, 21), WARSAW)
    elevation, azimuth = sun.solar_position(latitude, 21.0122, noon)
    # Declination at the June solstice is the obliquity of the ecliptic.
    assert elevation == pytest.approx(90.0 - latitude + 23.44, abs=0.05)
    # Northern hemisphere, sun south of zenith at noon.
    assert azimuth == pytest.approx(180.0, abs=0.1)


def test_equinox_day_at_the_equator_is_just_over_twelve_hours() -> None:
    """Refraction and the solar semi-diameter stretch it past 12h by ~7 min."""
    anchors = sun.all_anchors(0.0, 0.0, date(2025, 3, 20), UTC)
    length = anchors["sunset"] - anchors["sunrise"]
    assert timedelta(hours=12, minutes=5) < length < timedelta(hours=12, minutes=10)


def test_anchors_are_chronological() -> None:
    anchors = sun.all_anchors(52.2297, 21.0122, date(2025, 3, 20), WARSAW)
    present = [(name, anchors[name]) for name in CHRONOLOGICAL if anchors[name] is not None]
    times = [value for _, value in present]
    assert times == sorted(times), [(n, v.isoformat()) for n, v in present]


def test_twilight_bands_nest() -> None:
    """Deeper twilight starts earlier and ends later, without exception."""
    anchors = sun.all_anchors(52.2297, 21.0122, date(2025, 3, 20), WARSAW)
    assert anchors["astronomical_dawn"] < anchors["nautical_dawn"] < anchors["civil_dawn"]
    assert anchors["civil_dusk"] < anchors["nautical_dusk"] < anchors["astronomical_dusk"]


def test_solar_midnight_is_half_a_day_before_noon() -> None:
    anchors = sun.all_anchors(52.2297, 21.0122, date(2025, 8, 1), WARSAW)
    assert anchors["solar_noon"] - anchors["solar_midnight"] == timedelta(hours=12)


# ── Polar behaviour ──────────────────────────────────────────────────────────


def test_polar_day_has_no_sunrise_but_reports_which_side() -> None:
    """Tromsø in June: the Sun never sets, so a sunrise/sunset window must be
    read as 'all day', not as 'never'."""
    day = date(2025, 6, 21)
    anchors = sun.all_anchors(69.6492, 18.9553, day, OSLO)
    assert anchors["sunrise"] is None
    assert anchors["sunset"] is None
    assert anchors["solar_noon"] is not None
    assert (
        sun.threshold_state(69.6492, 18.9553, day, OSLO, sun.SUNRISE_SUNSET) == "always_above"
    )


def test_polar_night_reports_the_other_side() -> None:
    day = date(2025, 12, 21)
    anchors = sun.all_anchors(69.6492, 18.9553, day, OSLO)
    assert anchors["sunrise"] is None
    assert (
        sun.threshold_state(69.6492, 18.9553, day, OSLO, sun.SUNRISE_SUNSET) == "always_below"
    )


def test_white_nights_lose_only_astronomical_twilight() -> None:
    """Warsaw in late June: the Sun stays above -18°, so astronomical twilight
    never arrives while sunrise and sunset are perfectly ordinary."""
    anchors = sun.all_anchors(52.2297, 21.0122, date(2025, 6, 21), WARSAW)
    assert anchors["astronomical_dusk"] is None
    assert anchors["astronomical_dawn"] is None
    assert anchors["nautical_dusk"] is not None
    assert anchors["sunset"] is not None


# ── Timezones and DST ────────────────────────────────────────────────────────


@pytest.mark.parametrize("day", [date(2025, 3, 30), date(2025, 10, 26)])
def test_anchors_land_on_the_requested_local_date_across_dst(day: date) -> None:
    anchors = sun.all_anchors(52.2297, 21.0122, day, WARSAW)
    for name in ("sunrise", "sunset", "solar_noon", "civil_dusk"):
        assert _local(anchors, name, WARSAW).date() == day, name


def test_spring_forward_shifts_local_sunrise_by_an_hour() -> None:
    """The clock jumps, the Sun does not: local sunrise must move ~1 h later
    on the wall clock while the actual instant advances by the usual day."""
    before = sun.all_anchors(52.2297, 21.0122, date(2025, 3, 29), WARSAW)["sunrise"]
    after = sun.all_anchors(52.2297, 21.0122, date(2025, 3, 30), WARSAW)["sunrise"]

    def wall_clock(value: datetime) -> timedelta:
        local = value.astimezone(WARSAW)
        return timedelta(hours=local.hour, minutes=local.minute, seconds=local.second)

    assert timedelta(minutes=55) < wall_clock(after) - wall_clock(before) < timedelta(minutes=62)
    # In absolute terms nothing dramatic happened: one ordinary day, minus the
    # couple of minutes sunrise creeps earlier at this time of year.
    assert timedelta(hours=23, minutes=50) < after - before < timedelta(hours=24)


# ── Altitude, phases, input validation ───────────────────────────────────────


def test_altitude_brings_sunrise_forward() -> None:
    day = date(2025, 3, 20)
    sea_level = sun.event_time(52.2297, 21.0122, day, WARSAW, sun.SUNRISE_SUNSET, rising=True)
    on_a_hill = sun.event_time(
        52.2297, 21.0122, day, WARSAW, sun.SUNRISE_SUNSET, rising=True, elevation_m=1000.0
    )
    assert on_a_hill < sea_level
    # ~1.1° of horizon dip at 1000 m; near the equinox in Warsaw that is minutes,
    # not hours.
    assert timedelta(minutes=3) < (sea_level - on_a_hill) < timedelta(minutes=15)


def test_horizon_dip_is_zero_at_or_below_sea_level() -> None:
    assert sun.horizon_dip(0.0) == 0.0
    assert sun.horizon_dip(-10.0) == 0.0


@pytest.mark.parametrize(
    ("elevation", "phase"),
    [
        (10.0, "day"),
        (0.0, "day"),
        (-0.833, "civil_twilight"),
        (-3.0, "civil_twilight"),
        (-6.0, "nautical_twilight"),
        (-12.0, "astronomical_twilight"),
        (-18.0, "night"),
        (-40.0, "night"),
    ],
)
def test_phase_boundaries(elevation: float, phase: str) -> None:
    assert sun.phase_of(elevation) == phase


def test_golden_and_blue_hour_overlap_the_basic_phases() -> None:
    # Golden hour spans the horizon: partly day, partly civil twilight.
    assert sun.in_phase(5.0, "golden_hour") and sun.phase_of(5.0) == "day"
    assert sun.in_phase(-2.0, "golden_hour") and sun.phase_of(-2.0) == "civil_twilight"
    # Blue hour sits entirely inside civil twilight and stops where golden starts.
    assert sun.in_phase(-5.0, "blue_hour")
    assert not sun.in_phase(-4.0, "blue_hour")
    assert sun.in_phase(-4.0, "golden_hour")
    assert not sun.in_phase(-7.0, "blue_hour")


def test_unknown_phase_is_an_error_not_a_silent_false() -> None:
    with pytest.raises(ValueError):
        sun.in_phase(0.0, "magic_hour")


def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(ValueError):
        sun.solar_position(52.0, 21.0, datetime(2025, 6, 21, 12, 0))


@pytest.mark.parametrize(("lat", "lon"), [(91.0, 0.0), (-91.0, 0.0), (0.0, 181.0), (0.0, -181.0)])
def test_coordinates_out_of_range_are_rejected(lat: float, lon: float) -> None:
    with pytest.raises(ValueError):
        sun.all_anchors(lat, lon, date(2025, 6, 21), UTC)


def test_apparent_elevation_lifts_the_sun_near_the_horizon() -> None:
    """Refraction is worth about half a degree at the horizon and nothing
    overhead — the reason -0.833° and not 0° marks sunrise."""
    assert sun.apparent_elevation(0.0) - 0.0 == pytest.approx(0.48, abs=0.05)
    assert sun.apparent_elevation(80.0) == pytest.approx(80.0, abs=0.01)
    assert sun.apparent_elevation(89.0) == 89.0


# ── Cross-check against an independent implementation ────────────────────────

try:  # astral is a test-only extra; the rest of this file must still run without it.
    import astral  # noqa: F401

    HAVE_ASTRAL = True
except ImportError:  # pragma: no cover - depends on the dev environment
    HAVE_ASTRAL = False

requires_astral = pytest.mark.skipif(not HAVE_ASTRAL, reason="astral not installed")


@requires_astral
@pytest.mark.parametrize(
    ("name", "lat", "lon", "tz"),
    [
        ("Warsaw", 52.2297, 21.0122, WARSAW),
        ("Sydney", -33.8688, 151.2093, SYDNEY),
        ("Quito", -0.1807, -78.4678, ZoneInfo("America/Guayaquil")),
        ("Reykjavik", 64.1466, -21.9426, ZoneInfo("Atlantic/Reykjavik")),
    ],
)
@pytest.mark.parametrize(
    "day",
    [date(2025, 1, 15), date(2025, 3, 20), date(2025, 6, 21), date(2025, 9, 23), date(2025, 12, 21)],
)
def test_matches_astral(name: str, lat: float, lon: float, tz, day: date) -> None:
    from astral import LocationInfo
    from astral.sun import sun as astral_sun

    location = LocationInfo(name, "", str(tz), lat, lon)
    try:
        # `tzinfo` here tells astral which day `date` refers to, not what to
        # return. It must be the location's zone, or east of Greenwich the two
        # implementations end up comparing different days.
        reference = astral_sun(location.observer, date=day, tzinfo=tz)
    except ValueError:
        pytest.skip("event does not occur at this latitude/date")

    anchors = sun.all_anchors(lat, lon, day, tz)
    for ours, theirs in (("sunrise", "sunrise"), ("sunset", "sunset"), ("civil_dawn", "dawn"), ("civil_dusk", "dusk")):
        if anchors[ours] is None:
            continue
        assert abs(anchors[ours] - reference[theirs]) < TOLERANCE, f"{name} {day} {ours}"


@requires_astral
@pytest.mark.parametrize(
    ("name", "lat", "lon", "tz"),
    [
        ("Warsaw", 52.2297, 21.0122, WARSAW),
        ("Sydney", -33.8688, 151.2093, SYDNEY),
    ],
)
def test_matches_astral_for_a_whole_year(name: str, lat: float, lon: float, tz) -> None:
    """Spot dates can hide a seasonal drift; 365 of them cannot."""
    from astral import LocationInfo
    from astral.sun import sun as astral_sun

    observer = LocationInfo(name, "", str(tz), lat, lon).observer
    worst = timedelta(0)
    day = date(2025, 1, 1)
    while day < date(2026, 1, 1):
        reference = astral_sun(observer, date=day, tzinfo=tz)
        anchors = sun.all_anchors(lat, lon, day, tz)
        for ours, theirs in (("sunrise", "sunrise"), ("sunset", "sunset"), ("solar_noon", "noon")):
            worst = max(worst, abs(anchors[ours] - reference[theirs]))
        day += timedelta(days=1)
    assert worst < timedelta(seconds=60), f"{name}: worst deviation {worst}"


def test_dusk_after_local_midnight_still_belongs_to_the_requested_day() -> None:
    """Reykjavik in late May: civil dusk falls just past 00:30 the next morning.

    It is still *that evening's* dusk and must be returned for the day asked
    for. Anchoring to the calendar instead would hand back the previous
    evening's dusk for half the summer.
    """
    day = date(2025, 5, 17)
    tz = ZoneInfo("Atlantic/Reykjavik")
    anchors = sun.all_anchors(64.1466, -21.9426, day, tz)
    dusk = anchors["civil_dusk"]
    assert dusk is not None
    assert dusk > anchors["solar_noon"]
    assert dusk.astimezone(tz).date() == day + timedelta(days=1)
    assert dusk.astimezone(tz).hour == 0
