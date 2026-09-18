"""Tests for GET /api/sun/today.

The endpoint is thin, but three of its answers are load-bearing for the panel:
"no location", "the clock is not set" and "the Sun never crosses the horizon
today". Each of them looks like an empty result, and the panel has to tell them
apart to say anything useful.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException

from boneio.core.manager.sun import SunProvider
from boneio.webui.routes import sun as sun_routes

WARSAW = ZoneInfo("Europe/Warsaw")
OSLO = ZoneInfo("Europe/Oslo")


class FakeManager:
    """Just enough manager: the route reads `manager.sun` and nothing else."""

    def __init__(self, location, tz=WARSAW, monkeypatch=None):
        if monkeypatch is not None:
            monkeypatch.setattr("boneio.core.manager.sun.local_timezone", lambda: tz)
        self.sun = SunProvider(location)


def call(manager, day=None):
    return asyncio.run(sun_routes.get_sun_today(day=day, manager=manager))


@pytest.fixture
def warsaw(monkeypatch):
    return FakeManager(
        {"latitude": 52.2297, "longitude": 21.0122, "elevation": 110},
        monkeypatch=monkeypatch,
    )


def test_a_configured_device_reports_a_full_day(warsaw):
    payload = call(warsaw, day="2025-06-21")

    assert payload["configured"] is True
    assert payload["ready"] is True
    assert payload["timezone"] == "Europe/Warsaw"
    assert payload["date"] == "2025-06-21"
    assert payload["horizon_state"] == "crosses"
    assert payload["anchors"]["sunrise"].startswith("2025-06-21T04:1")
    assert payload["anchors"]["sunset"].startswith("2025-06-21T21:0")


def test_times_come_back_in_the_device_timezone(warsaw):
    """The panel renders these verbatim; handing it UTC would show a clock the
    operator has to correct in their head."""
    assert call(warsaw, day="2025-06-21")["anchors"]["sunrise"].endswith("+02:00")


def test_an_anchor_the_sun_never_reaches_is_null_not_missing(warsaw):
    """White nights in Warsaw: no astronomical twilight, ordinary sunset."""
    anchors = call(warsaw, day="2025-06-21")["anchors"]
    assert "astronomical_dusk" in anchors
    assert anchors["astronomical_dusk"] is None
    assert anchors["sunset"] is not None


def test_no_location_says_so_instead_of_returning_empty_times():
    payload = call(FakeManager(None))
    assert payload["configured"] is False
    assert payload["ready"] is False
    assert payload["reason"] == "no_location"
    assert payload["anchors"] == {}


def test_the_map_flag_travels_with_every_answer():
    """The Location page reads it to decide whether to offer a map picker, and
    it has to be there even when there is nothing else to report."""
    for manager in (FakeManager(None), FakeManager({"latitude": 52.0, "longitude": 21.0})):
        assert "map_tiles" in call(manager)


def test_an_unset_clock_is_reported_separately(monkeypatch):
    """Both look like "no times" to the panel, and they need different advice:
    one is a form to fill in, the other is NTP."""
    manager = FakeManager({"latitude": 52.2297, "longitude": 21.0122}, monkeypatch=monkeypatch)
    # Move the sanity floor into the future instead of stubbing the method:
    # this is the same code path a device takes before its first NTP reply.
    monkeypatch.setattr("boneio.core.manager.sun._CLOCK_SANE_FROM", date(2999, 1, 1))

    payload = call(manager)
    assert payload["configured"] is True
    assert payload["ready"] is False
    assert payload["reason"] == "clock_not_set"
    assert payload["anchors"] == {}
    # The coordinates still come back: the panel keeps showing what is set.
    assert payload["latitude"] == pytest.approx(52.2297)


def test_polar_day_is_distinguishable_from_polar_night(monkeypatch):
    manager = FakeManager({"latitude": 69.6492, "longitude": 18.9553}, tz=OSLO, monkeypatch=monkeypatch)

    june = call(manager, day="2025-06-21")
    assert june["anchors"]["sunrise"] is None
    assert june["horizon_state"] == "always_above"

    december = call(manager, day="2025-12-21")
    assert december["anchors"]["sunrise"] is None
    assert december["horizon_state"] == "always_below"


def test_the_current_position_comes_with_the_day(warsaw):
    """One endpoint, because times without a live elevation make a wrong
    latitude indistinguishable from a wrong clock."""
    now = call(warsaw)["now"]
    assert -90.0 <= now["elevation"] <= 90.0
    assert 0.0 <= now["azimuth"] <= 360.0
    assert now["phase"] in (
        "day", "civil_twilight", "nautical_twilight", "astronomical_twilight", "night",
    )
    assert isinstance(now["golden_hour"], bool)


def test_an_unparseable_date_is_a_bad_request(warsaw):
    with pytest.raises(HTTPException) as excinfo:
        call(warsaw, day="21-06-2025")
    assert excinfo.value.status_code == 400


def test_omitting_the_date_means_today_on_the_device(warsaw):
    expected = datetime.now(WARSAW).date().isoformat()
    assert call(warsaw)["date"] == expected
