"""Tests for `type: sun` action conditions.

Three shapes (a window between anchors, a phase, an elevation band) and one
awkward reality: at high latitudes an anchor may not exist on a given day, and
whether the bound then collapses to the start or the end of the day decides
whether "while it is dark" covers a polar summer or nothing at all.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from boneio.core.manager.action_conditions import (
    precompile_conditions,
    should_execute_action,
)
from boneio.core.manager.sun import SunProvider

WARSAW = ZoneInfo("Europe/Warsaw")
OSLO = ZoneInfo("Europe/Oslo")

# Warsaw, 20 March 2025: sunrise 05:38, sunset 17:49 local.
EQUINOX = "2025-03-20"


@pytest.fixture
def warsaw(monkeypatch) -> SunProvider:
    monkeypatch.setattr("boneio.core.manager.sun.local_timezone", lambda: WARSAW)
    return SunProvider({"latitude": 52.2297, "longitude": 21.0122})


@pytest.fixture
def tromso(monkeypatch) -> SunProvider:
    monkeypatch.setattr("boneio.core.manager.sun.local_timezone", lambda: OSLO)
    return SunProvider({"latitude": 69.6492, "longitude": 18.9553})


def when(iso: str, tz=WARSAW) -> datetime:
    """Local wall-clock time, e.g. "2025-03-20 12:00"."""
    return datetime.fromisoformat(iso).replace(tzinfo=tz)


def compile_condition(condition: dict, provider: SunProvider | None):
    return precompile_conditions({"condition": condition}, provider)


def holds(condition: dict, provider: SunProvider | None, moment: datetime) -> bool:
    return should_execute_action(compile_condition(condition, provider), moment)


# ── windows between anchors ──────────────────────────────────────────────


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (f"{EQUINOX} 12:00", True),   # broad daylight
        (f"{EQUINOX} 06:00", True),   # just after sunrise
        (f"{EQUINOX} 05:00", False),  # before sunrise
        (f"{EQUINOX} 18:30", False),  # after sunset
        (f"{EQUINOX} 23:00", False),
    ],
)
def test_a_daylight_window(warsaw, moment, expected):
    condition = {"type": "sun", "after": "sunrise", "before": "sunset"}
    assert holds(condition, warsaw, when(moment)) is expected


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (f"{EQUINOX} 23:00", True),   # after sunset
        (f"{EQUINOX} 02:00", True),   # before sunrise, same calendar day
        (f"{EQUINOX} 12:00", False),
        (f"{EQUINOX} 17:00", False),  # still light
    ],
)
def test_a_night_window_crosses_midnight(warsaw, moment, expected):
    """`sunset → sunrise` is the same wrap-around rule as `22:00 → 06:00`."""
    condition = {"type": "sun", "after": "sunset", "before": "sunrise"}
    assert holds(condition, warsaw, when(moment)) is expected


def test_an_offset_moves_the_boundary(warsaw):
    """Sunset is 17:49; -15 min must open the window at 17:34, not before."""
    condition = {"type": "sun", "after": "sunset", "after_offset": -900}
    assert holds(condition, warsaw, when(f"{EQUINOX} 17:30")) is False
    assert holds(condition, warsaw, when(f"{EQUINOX} 17:40")) is True


def test_a_positive_offset_delays_the_boundary(warsaw):
    condition = {"type": "sun", "after": "sunrise", "after_offset": 3600}
    assert holds(condition, warsaw, when(f"{EQUINOX} 06:00")) is False
    assert holds(condition, warsaw, when(f"{EQUINOX} 07:00")) is True


def test_only_an_upper_bound(warsaw):
    condition = {"type": "sun", "before": "civil_dusk"}
    assert holds(condition, warsaw, when(f"{EQUINOX} 12:00")) is True
    assert holds(condition, warsaw, when(f"{EQUINOX} 19:00")) is False


def test_twilight_anchors_differ_from_sunset(warsaw):
    """Civil dusk is 18:23, half an hour after sunset — the point of having
    both."""
    after_sunset = when(f"{EQUINOX} 18:00")
    assert holds({"type": "sun", "before": "sunset"}, warsaw, after_sunset) is False
    assert holds({"type": "sun", "before": "civil_dusk"}, warsaw, after_sunset) is True


# ── phases ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("phase", "moment", "expected"),
    [
        ("day", f"{EQUINOX} 12:00", True),
        ("day", f"{EQUINOX} 22:00", False),
        ("night", f"{EQUINOX} 22:00", True),
        ("night", f"{EQUINOX} 12:00", False),
        ("civil_twilight", f"{EQUINOX} 18:10", True),
        ("civil_twilight", f"{EQUINOX} 12:00", False),
        ("golden_hour", f"{EQUINOX} 17:40", True),
        ("golden_hour", f"{EQUINOX} 12:00", False),
    ],
)
def test_phases(warsaw, phase, moment, expected):
    assert holds({"type": "sun", "phase": phase}, warsaw, when(moment)) is expected


def test_golden_hour_overlaps_day(warsaw):
    """It is a photographic band, not a slot between the basic phases."""
    late = when(f"{EQUINOX} 17:40")
    assert holds({"type": "sun", "phase": "golden_hour"}, warsaw, late) is True
    assert holds({"type": "sun", "phase": "day"}, warsaw, late) is True


# ── elevation ────────────────────────────────────────────────────────────


def test_above_a_given_elevation(warsaw):
    condition = {"type": "sun", "above": 20}
    assert holds(condition, warsaw, when(f"{EQUINOX} 12:00")) is True
    assert holds(condition, warsaw, when(f"{EQUINOX} 07:00")) is False


def test_a_band_of_elevations(warsaw):
    """Above the horizon but still low — the shape a glare-blind rule takes."""
    condition = {"type": "sun", "above": 0, "below": 10}
    assert holds(condition, warsaw, when(f"{EQUINOX} 12:00")) is False  # too high
    assert holds(condition, warsaw, when(f"{EQUINOX} 04:00")) is False  # too low
    assert holds(condition, warsaw, when(f"{EQUINOX} 06:20")) is True


def test_below_the_horizon(warsaw):
    condition = {"type": "sun", "below": 0}
    assert holds(condition, warsaw, when(f"{EQUINOX} 23:00")) is True
    assert holds(condition, warsaw, when(f"{EQUINOX} 12:00")) is False


# ── polar days ───────────────────────────────────────────────────────────


def test_polar_day_makes_a_daylight_window_cover_everything(tromso):
    """Tromsø in June: the Sun never sets, so "between sunrise and sunset"
    must be true at 2 a.m. — not false because the anchors are missing."""
    condition = {"type": "sun", "after": "sunrise", "before": "sunset"}
    assert holds(condition, tromso, when("2025-06-21 02:00", OSLO)) is True
    assert holds(condition, tromso, when("2025-06-21 14:00", OSLO)) is True


def test_polar_day_makes_a_night_window_empty(tromso):
    condition = {"type": "sun", "after": "civil_dusk", "before": "civil_dawn"}
    assert holds(condition, tromso, when("2025-06-21 02:00", OSLO)) is False
    assert holds(condition, tromso, when("2025-06-21 14:00", OSLO)) is False


def test_polar_night_makes_a_daylight_window_empty(tromso):
    condition = {"type": "sun", "after": "sunrise", "before": "sunset"}
    assert holds(condition, tromso, when("2025-12-21 12:00", OSLO)) is False
    assert holds(condition, tromso, when("2025-12-21 02:00", OSLO)) is False


def test_polar_night_makes_a_night_window_cover_everything(tromso):
    condition = {"type": "sun", "after": "sunset", "before": "sunrise"}
    assert holds(condition, tromso, when("2025-12-21 12:00", OSLO)) is True


# ── failure modes ────────────────────────────────────────────────────────


def test_without_a_location_the_action_is_allowed(caplog):
    """Fail open, like every other condition on a configuration error — and
    say so, because a silent always-true is indistinguishable from working."""
    condition = {"type": "sun", "after": "sunrise", "before": "sunset"}
    with caplog.at_level("ERROR"):
        assert holds(condition, SunProvider(None), when(f"{EQUINOX} 23:00")) is True
    assert any("cannot be evaluated" in record.message for record in caplog.records)


def test_the_complaint_is_made_once(caplog):
    compiled = compile_condition(
        {"type": "sun", "phase": "day"}, SunProvider(None)
    )
    with caplog.at_level("ERROR"):
        for _ in range(5):
            should_execute_action(compiled, when(f"{EQUINOX} 12:00"))
    assert sum("cannot be evaluated" in r.message for r in caplog.records) == 1


def test_an_unset_clock_allows_the_action(warsaw, monkeypatch):
    from datetime import date

    monkeypatch.setattr("boneio.core.manager.sun._CLOCK_SANE_FROM", date(2999, 1, 1))
    condition = {"type": "sun", "after": "sunrise", "before": "sunset"}
    assert holds(condition, warsaw, when(f"{EQUINOX} 23:00")) is True


# ── composition ──────────────────────────────────────────────────────────


def test_a_sun_condition_combines_with_the_others(warsaw):
    """AND with a date window: dark, and in the heating season."""
    compiled = precompile_conditions(
        {
            "conditions": {
                "mode": "and",
                "list": [
                    {"type": "sun", "after": "sunset", "before": "sunrise"},
                    {"type": "date", "after": "10-01", "before": "04-30"},
                ],
            }
        },
        warsaw,
    )
    assert should_execute_action(compiled, when(f"{EQUINOX} 23:00")) is True   # March
    assert should_execute_action(compiled, when(f"{EQUINOX} 12:00")) is False  # daylight
    assert should_execute_action(compiled, when("2025-07-15 23:00")) is False  # summer


def test_or_mode_with_a_sun_condition(warsaw):
    compiled = precompile_conditions(
        {
            "conditions": {
                "mode": "or",
                "list": [
                    {"type": "sun", "phase": "night"},
                    {"type": "time", "after": "12:00", "before": "13:00"},
                ],
            }
        },
        warsaw,
    )
    assert should_execute_action(compiled, when(f"{EQUINOX} 23:00")) is True
    assert should_execute_action(compiled, when(f"{EQUINOX} 12:30")) is True
    assert should_execute_action(compiled, when(f"{EQUINOX} 15:00")) is False


def test_reconfiguring_the_location_reaches_compiled_conditions(warsaw):
    """The condition holds the provider by reference, so moving the device
    must not require recompiling every action."""
    compiled = compile_condition(
        {"type": "sun", "after": "sunrise", "before": "sunset"}, warsaw
    )
    # 02:00 UTC+1 in Warsaw is night; the same instant in Sydney is daytime.
    moment = when("2025-03-20 02:00")
    assert should_execute_action(compiled, moment) is False

    warsaw.configure({"latitude": -33.8688, "longitude": 151.2093})
    assert should_execute_action(compiled, moment) is True
