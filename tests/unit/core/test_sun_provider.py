"""Tests for SunProvider — the layer that gives the solar maths a place and a clock.

The maths itself is covered by `test_sun.py`. What matters here is everything
around it: refusing to answer when the clock has not been set, caching a day
rather than recomputing per button press, dropping that cache when the
configuration or the timezone changes, and turning a missing anchor into
something a caller can act on.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from boneio.core.manager.sun import SunProvider

WARSAW = ZoneInfo("Europe/Warsaw")
OSLO = ZoneInfo("Europe/Oslo")

LOCATION = {"latitude": 52.2297, "longitude": 21.0122, "elevation": 110}


@pytest.fixture
def provider(monkeypatch) -> SunProvider:
    """A configured provider pinned to Europe/Warsaw, whatever the host uses."""
    monkeypatch.setattr("boneio.core.manager.sun.local_timezone", lambda: WARSAW)
    return SunProvider(LOCATION)


def at(year, month, day, hour=12, minute=0, tz=WARSAW) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=tz)


# ── configuration ────────────────────────────────────────────────────────


def test_a_configured_provider_answers(provider):
    assert provider.configured
    assert provider.latitude == pytest.approx(52.2297)
    assert provider.elevation_m == pytest.approx(110.0)


@pytest.mark.parametrize(
    "location",
    [
        None,
        {},
        {"latitude": 52.0},  # longitude missing
        {"latitude": "north", "longitude": 21.0},
        {"latitude": 95.0, "longitude": 21.0},
        {"latitude": 52.0, "longitude": 200.0},
    ],
)
def test_an_unusable_location_leaves_the_provider_unconfigured(location):
    assert SunProvider(location).configured is False


def test_an_unconfigured_provider_answers_nothing_rather_than_guessing():
    provider = SunProvider(None)
    assert provider.anchors(at(2025, 6, 21)) == {}
    assert provider.position(at(2025, 6, 21)) is None
    assert provider.phase(at(2025, 6, 21)) is None
    assert provider.threshold_state(-6.0, at(2025, 6, 21)) is None


def test_null_island_is_accepted_but_warned_about(caplog):
    """0, 0 is a real coordinate in the Gulf of Guinea and an unfilled form
    everywhere else. Refusing it would be wrong; saying nothing would be worse."""
    with caplog.at_level("WARNING"):
        provider = SunProvider({"latitude": 0, "longitude": 0})
    assert provider.configured
    assert any("0, 0" in record.message for record in caplog.records)


def test_a_missing_elevation_is_sea_level():
    assert SunProvider({"latitude": 52.0, "longitude": 21.0}).elevation_m == 0.0


# ── the clock ────────────────────────────────────────────────────────────


def test_an_unset_clock_stops_every_answer(provider):
    """The board has no RTC: before the first NTP reply it reports 1970, and
    sunset for 1970 would look exactly like a working feature."""
    epoch = at(1970, 1, 1)
    assert provider.clock_ready(epoch) is False
    assert provider.anchors(epoch) == {}
    assert provider.position(epoch) is None
    assert provider.threshold_state(-6.0, epoch) is None


def test_the_clock_complaint_is_made_once(provider, caplog):
    with caplog.at_level("WARNING"):
        for _ in range(5):
            provider.anchors(at(1970, 1, 1))
    assert sum("has not been set" in r.message for r in caplog.records) == 1


def test_a_set_clock_answers(provider):
    assert provider.clock_ready(at(2025, 6, 21)) is True
    assert provider.anchors(at(2025, 6, 21))


# ── caching ──────────────────────────────────────────────────────────────


def test_a_day_is_computed_once(provider, monkeypatch):
    from boneio.core.utils import sun as sun_utils

    original = sun_utils.all_anchors
    calls = 0

    def counting(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr("boneio.core.manager.sun.sun.all_anchors", counting)

    for hour in range(0, 24, 3):
        provider.anchors(at(2025, 6, 21, hour))
    assert calls == 1, "a button press must not recompute ephemerides"


def test_a_new_day_is_recomputed(provider):
    first = provider.anchors(at(2025, 6, 21))["sunrise"]
    second = provider.anchors(at(2025, 6, 22))["sunrise"]
    assert first != second


def test_reconfiguring_drops_the_cache(provider):
    warsaw_sunrise = provider.anchors(at(2025, 6, 21))["sunrise"]
    provider.configure({"latitude": -33.8688, "longitude": 151.2093})
    sydney_sunrise = provider.anchors(at(2025, 6, 21))["sunrise"]
    assert warsaw_sunrise != sydney_sunrise


def test_invalidate_drops_the_timezone_too(provider, monkeypatch):
    """Changing the timezone from the panel must not leave yesterday's answers
    in place — the cache key carries the zone, and invalidate() re-reads it."""
    assert str(provider.timezone) == "Europe/Warsaw"
    monkeypatch.setattr("boneio.core.manager.sun.local_timezone", lambda: OSLO)
    provider.invalidate()
    assert str(provider.timezone) == "Europe/Oslo"


def test_elevation_is_reused_within_a_minute_and_not_beyond(provider):
    base = at(2025, 6, 21, 12, 0)
    first = provider.elevation(base)
    assert provider.elevation(base + timedelta(seconds=30)) == first
    assert provider.elevation(base + timedelta(minutes=5)) != first


# ── answers ──────────────────────────────────────────────────────────────


def test_phase_follows_the_sun(provider):
    assert provider.phase(at(2025, 6, 21, 12)) == "day"
    assert provider.phase(at(2025, 12, 21, 23)) == "night"


def test_in_phase_covers_the_photographic_bands(provider):
    """Golden hour is an overlapping band, not one of the five basic phases."""
    anchors = provider.anchors(at(2025, 3, 20))
    just_after_sunrise = anchors["sunrise"] + timedelta(minutes=10)
    assert provider.in_phase("golden_hour", just_after_sunrise) is True


def test_an_unknown_anchor_is_an_error_not_a_silent_none(provider):
    with pytest.raises(KeyError):
        provider.anchor("moonrise", at(2025, 6, 21))


def test_a_missing_anchor_is_none_with_a_side(monkeypatch):
    """Tromsø in June: no sunrise, and the caller must be able to tell that
    from "no sunset in December"."""
    monkeypatch.setattr("boneio.core.manager.sun.local_timezone", lambda: OSLO)
    provider = SunProvider({"latitude": 69.6492, "longitude": 18.9553})

    june = datetime(2025, 6, 21, 12, tzinfo=OSLO)
    assert provider.anchor("sunrise", june) is None
    assert provider.threshold_state(-0.833, june) == "always_above"

    provider.invalidate()
    december = datetime(2025, 12, 21, 12, tzinfo=OSLO)
    assert provider.anchor("sunrise", december) is None
    assert provider.threshold_state(-0.833, december) == "always_below"


def test_a_naive_datetime_is_rejected(provider):
    with pytest.raises(ValueError):
        provider.anchors(datetime(2025, 6, 21, 12))


def test_elevation_shifts_sunrise(monkeypatch):
    monkeypatch.setattr("boneio.core.manager.sun.local_timezone", lambda: WARSAW)
    sea = SunProvider({"latitude": 52.2297, "longitude": 21.0122})
    hill = SunProvider({"latitude": 52.2297, "longitude": 21.0122, "elevation": 1000})
    when = at(2025, 3, 20)
    assert hill.anchors(when)["sunrise"] < sea.anchors(when)["sunrise"]


# ── manager wiring ───────────────────────────────────────────────────────


def test_the_manager_reload_handler_adopts_new_coordinates(monkeypatch):
    """`location` is in the hot-reload map, so saving it from the panel must
    take effect without a restart — the handler re-reads and reconfigures."""
    from types import SimpleNamespace

    from boneio.core.manager.manager import Manager

    monkeypatch.setattr("boneio.core.manager.sun.local_timezone", lambda: WARSAW)

    provider = SunProvider(LOCATION)
    config = {"location": {"latitude": -33.8688, "longitude": 151.2093}}
    built = []
    fake_manager = SimpleNamespace(
        sun=provider,
        _config_helper=SimpleNamespace(get_config=lambda: config),
        # The handler also asks for the sun sensors, because coordinates may
        # have just appeared on a device that started without any.
        sensors=SimpleNamespace(configure_sun_sensors=lambda: built.append(True)),
    )

    before = provider.anchors(at(2025, 6, 21))["sunrise"]
    Manager._reload_location(fake_manager)
    after = provider.anchors(at(2025, 6, 21))["sunrise"]

    assert provider.latitude == pytest.approx(-33.8688)
    assert before != after
    assert built == [True]


def test_removing_the_location_section_disables_sun_features(monkeypatch):
    from types import SimpleNamespace

    from boneio.core.manager.manager import Manager

    monkeypatch.setattr("boneio.core.manager.sun.local_timezone", lambda: WARSAW)
    provider = SunProvider(LOCATION)
    fake_manager = SimpleNamespace(
        sun=provider,
        _config_helper=SimpleNamespace(get_config=lambda: {}),
        sensors=SimpleNamespace(configure_sun_sensors=lambda: None),
    )

    Manager._reload_location(fake_manager)
    assert provider.configured is False
