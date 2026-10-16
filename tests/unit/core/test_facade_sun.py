"""Whether the Sun shines on a cover's window.

The angle is plain geometry; what matters is that the cover with a facade
gets an entity in Home Assistant, loses it when the facade goes, and that a
window the Sun is behind, or below the neighbour's roof, reads "off".
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from boneio.core.manager.facade_sun import FacadeSun
from boneio.core.utils.sun import facade_incidence, sun_on_facade


@pytest.mark.parametrize(
    ("elevation", "azimuth", "facade", "min_elevation", "on"),
    [
        (30, 180, 180, 0, True),    # noon sun on a south window
        (30, 180, 0, 0, False),     # ...and the north one, behind the wall
        (5, 95, 90, 0, True),       # early sun on an east window
        (5, 95, 90, 10, False),     # ...hidden by the house opposite
        (-2, 90, 90, 0, False),     # before sunrise
        (20, 271, 180, 0, False),   # sun just past grazing a south window
    ],
)
def test_sun_on_facade(elevation, azimuth, facade, min_elevation, on):
    assert sun_on_facade(elevation, azimuth, facade, min_elevation) is on


def test_incidence_is_zero_straight_on_and_ninety_grazing():
    assert facade_incidence(0, 180, 180) == pytest.approx(0)
    assert facade_incidence(0, 270, 180) == pytest.approx(90)
    assert facade_incidence(60, 180, 180) == pytest.approx(60)


def _cover(cid, facade, **kw):
    return SimpleNamespace(id=cid, name=cid.title(), facade_azimuth=facade, facade_min_elevation=0,
                           show_in_ha=True, area=None, **kw)


@pytest.fixture
def facades():
    manager = MagicMock()
    manager._topic_prefix = "boneio/blk"
    manager.sun.ready.return_value = True
    manager.sun.configured = True
    manager.sun.position.return_value = (30.0, 180.0)
    covers = {"south": _cover("south", 180), "north": _cover("north", 0), "plain": _cover("plain", None)}
    manager.covers.get_all_covers.return_value = covers
    helper = manager._config_helper
    helper.topic_prefix = "boneio/blk"
    helper.get_autodiscovery_topics_for_id.side_effect = lambda i: [("binary_sensor", f"ha/{i}")]
    facade = FacadeSun(manager)
    facade.covers = covers
    return facade


def test_each_cover_with_a_facade_reports_and_others_do_not(facades):
    facades.update(0)
    sent = {c.kwargs["topic"]: c.kwargs["payload"] for c in facades.manager.send_message.call_args_list}
    assert sent["boneio/blk/sensor/sun_on_south"]["state"] == "on"
    assert sent["boneio/blk/sensor/sun_on_north"]["state"] == "off"
    assert "boneio/blk/sensor/sun_on_plain" not in sent


def test_discovery_follows_the_covers(facades):
    facades.publish_discovery()
    published = {c.kwargs["id"] for c in facades.manager.publish_ha_discovery.call_args_list}
    assert published == {"sun_on_south", "sun_on_north"}
    payload = facades.manager.publish_ha_discovery.call_args_list[0].kwargs["payload"]
    assert payload["json_attributes_topic"] == payload["state_topic"]

    facades.covers["north"].facade_azimuth = None  # the facade was cleared
    facades.manager.publish_ha_discovery.reset_mock()
    facades.publish_discovery()
    facades.manager.send_message.assert_any_call(topic="ha/sun_on_north", payload=None, retain=True)
    facades.manager._config_helper.remove_autodiscovery_msg.assert_any_call("binary_sensor", "ha/sun_on_north")


def test_no_location_no_entities(facades):
    facades.manager.sun.configured = False
    facades.publish_discovery()
    facades.manager.publish_ha_discovery.assert_not_called()


# ── when the Sun reaches and leaves a window ─────────────────────────────

from datetime import date, datetime, timedelta  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

from boneio.core.config.yaml_util import schedule_shape_errors  # noqa: E402
from boneio.core.manager.scheduler import Scheduler  # noqa: E402
from boneio.core.manager.sun import SunProvider  # noqa: E402
from boneio.core.utils import sun as sun_utils  # noqa: E402

WARSAW = ZoneInfo("Europe/Warsaw")
POZNAN = (52.4, 16.9)
MIDSUMMER, MIDWINTER = date(2026, 6, 21), date(2026, 12, 21)


def _window(day, facade, min_elevation=0):
    return sun_utils.facade_window(*POZNAN, day, WARSAW, facade, min_elevation)


def test_an_east_window_gets_the_sun_from_sunrise_to_solar_noon():
    enter, leave = _window(MIDSUMMER, 90)
    anchors = sun_utils.all_anchors(*POZNAN, MIDSUMMER, WARSAW, 0.0)
    # Entering is the Sun clearing the geometric horizon, a few minutes after
    # the almanac's sunrise (which counts refraction); leaving, it passing south.
    assert timedelta(0) < enter - anchors["sunrise"] < timedelta(minutes=10)
    assert abs(leave - anchors["solar_noon"]) < timedelta(minutes=2)


def test_a_north_window_gets_morning_and_evening_sun_in_summer_and_none_in_winter():
    enter, leave = _window(MIDSUMMER, 0)
    assert enter.hour < 7 and leave.hour >= 20
    assert _window(MIDWINTER, 0) == (None, None)


def test_a_higher_horizon_shortens_the_window():
    low, high = _window(MIDSUMMER, 270), _window(MIDSUMMER, 270, 10)
    assert high[1] < low[1] - timedelta(minutes=30)  # the house opposite hides the evening sun


def test_the_same_day_gives_the_same_answer():
    first = _window(MIDSUMMER, 135)
    sun_utils.facade_window.cache_clear()
    assert _window(MIDSUMMER, 135) == first


@pytest.mark.parametrize(
    ("trigger", "error"),
    [
        ({"event": "facade_sun_enter"}, "needs 'cover'"),
        ({"event": "sunset", "cover": "salon"}, "belongs to a facade event"),
        ({"event": "facade_sun_leave", "cover": "salon"}, None),
    ],
)
def test_a_facade_trigger_names_its_cover_and_only_it_does(trigger, error):
    errors = schedule_shape_errors({"trigger": {"type": "sun", **trigger}, "actions": [{"action": "output"}]})
    assert (error in errors[0]) if error else errors == []


def _scheduler(monkeypatch, facade):
    monkeypatch.setattr("boneio.core.manager.sun.local_timezone", lambda: WARSAW)
    manager = MagicMock()
    manager.sun = SunProvider({"latitude": POZNAN[0], "longitude": POZNAN[1]})
    manager.parse_actions = lambda _id, actions: {k: list(v) for k, v in actions.items()}
    manager.covers.get_cover.return_value = SimpleNamespace(facade_azimuth=facade, facade_min_elevation=0)
    entry = {"id": "east_open", "name": "East open", "enabled": True, "on_missed": "skip", "catch_up": 900,
             "trigger": {"type": "sun", "event": "facade_sun_enter", "cover": "salon", "days": "daily"},
             "actions": [{"action": "mqtt", "topic": "t", "action_mqtt_msg": "go"}]}
    return Scheduler(manager, [entry])


def test_a_schedule_fires_when_the_sun_reaches_its_window(monkeypatch):
    scheduler = _scheduler(monkeypatch, 90)
    now = datetime(2026, 6, 21, 1, 0, tzinfo=WARSAW)
    when = scheduler._fire_time_on(scheduler._entries[0], MIDSUMMER, now)
    assert when == _window(MIDSUMMER, 90)[0]
    # A week ahead is as far as it looks.
    assert scheduler._fire_time_on(scheduler._entries[0], MIDSUMMER + timedelta(days=8), now) is None


def test_a_cover_without_a_facade_never_fires_and_says_so_once(monkeypatch, caplog):
    scheduler = _scheduler(monkeypatch, None)
    now = datetime(2026, 6, 21, 1, 0, tzinfo=WARSAW)
    for _ in range(3):
        assert scheduler._fire_time_on(scheduler._entries[0], MIDSUMMER, now) is None
    assert sum("has no facade_azimuth" in r.message for r in caplog.records) == 1


def test_a_schedule_naming_a_cover_without_a_facade_is_refused_on_save():
    from boneio.webui.routes import config_core

    state = MagicMock()
    covers = {"salon": SimpleNamespace(facade_azimuth=180), "garage": SimpleNamespace(facade_azimuth=None)}
    state.manager.covers.get_cover.side_effect = covers.get
    config_core.set_app_state(state)

    def entry(cover):
        return {"trigger": {"type": "sun", "event": "facade_sun_enter", "cover": cover}}

    errors = config_core._facade_trigger_errors([entry("salon"), entry("garage"), entry("attic")])
    assert len(errors) == 2
    assert "schedule[1]" in errors[0] and "no facade_azimuth" in errors[0]
    assert "schedule[2]" in errors[1] and "no cover 'attic'" in errors[1]
