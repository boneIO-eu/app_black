"""Tests for the sun sensors.

They compute nothing themselves — every value comes from SunProvider — so what
matters here is the wiring: that they exist only when the device knows where it
is, that they publish nothing rather than nulls when the Sun's position is
unknowable, and that each one is discovered by Home Assistant as the right kind
of entity.
"""

from __future__ import annotations

import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from boneio.core.manager.sun import SunProvider
from boneio.core.sensor.sun import build_sun_sensors

WARSAW = ZoneInfo("Europe/Warsaw")
LOCATION = {"latitude": 52.2297, "longitude": 21.0122}


@pytest.fixture
def manager(monkeypatch):
    """A manager stub with a real provider and a recording message bus."""
    monkeypatch.setattr("boneio.core.manager.sun.local_timezone", lambda: WARSAW)
    fake = MagicMock()
    fake.sun = SunProvider(LOCATION)
    fake.append_task = MagicMock(return_value=None)
    return fake


@pytest.fixture
def bus():
    published: list[tuple[str, dict]] = []
    fake = MagicMock()
    fake.send_message = lambda topic, payload: published.append((topic, payload))
    fake.published = published
    return fake


def build(manager, bus):
    return build_sun_sensors(manager=manager, message_bus=bus, topic_prefix="boneio")


# ── existence ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_full_set_is_built_when_a_location_is_configured(manager, bus):
    ids = [sensor.id for sensor in build(manager, bus)]
    assert ids == [
        "sun_elevation",
        "sun_azimuth",
        "sun_phase",
        "sun_above_horizon",
        "sun_next_sunrise",
        "sun_next_sunset",
    ]


@pytest.mark.asyncio
async def test_no_location_means_no_sensors(manager, bus):
    """An entity that is permanently unavailable is worse than an absent one."""
    manager.sun = SunProvider(None)
    assert build(manager, bus) == []


# ── publishing ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_every_sensor_publishes_a_plausible_value(manager, bus):
    for sensor in build(manager, bus):
        await sensor.async_update(1.0)

    states = {topic.rsplit("/", 1)[-1]: payload for topic, payload in bus.published}
    assert set(states) == {
        "sun_elevation", "sun_azimuth", "sun_phase",
        "sun_above_horizon", "sun_next_sunrise", "sun_next_sunset",
    }
    assert -90 <= states["sun_elevation"]["state"] <= 90
    assert 0 <= states["sun_azimuth"]["state"] <= 360
    assert states["sun_above_horizon"]["state"] in ("on", "off")
    assert states["sun_next_sunrise"]["state"].startswith("20")


@pytest.mark.asyncio
async def test_the_phase_sensor_carries_the_days_turning_points(manager, bus):
    phase = next(s for s in build(manager, bus) if s.id == "sun_phase")
    await phase.async_update(1.0)

    _, payload = bus.published[-1]
    for key in ("next_sunrise", "next_sunset", "next_dawn", "next_dusk"):
        assert key in payload, key
    assert isinstance(payload["golden_hour"], bool)
    assert payload["state"] in (
        "day", "civil_twilight", "nautical_twilight", "astronomical_twilight", "night",
    )


@pytest.mark.asyncio
async def test_nothing_is_published_while_the_clock_is_unset(manager, bus, monkeypatch):
    """The board has no RTC. Publishing a sunset computed for 1970 would look
    exactly like a working sensor."""
    monkeypatch.setattr("boneio.core.manager.sun._CLOCK_SANE_FROM", date(2999, 1, 1))
    for sensor in build(manager, bus):
        await sensor.async_update(1.0)
    assert bus.published == []


@pytest.mark.asyncio
async def test_a_reading_error_does_not_take_the_sensor_down(manager, bus):
    elevation = next(s for s in build(manager, bus) if s.id == "sun_elevation")

    def boom(now):
        raise RuntimeError("ephemeris on fire")

    elevation.read = boom
    await elevation.async_update(1.0)  # must not raise
    assert bus.published == []


@pytest.mark.asyncio
async def test_the_last_value_survives_a_missing_anchor(manager, bus, monkeypatch):
    """Polar seasons: publishing None would make the entity go unavailable for
    two months, so the sensor stays quiet and keeps what it had."""
    sensor = next(s for s in build(manager, bus) if s.id == "sun_next_sunrise")
    await sensor.async_update(1.0)
    first = sensor.state
    assert first is not None

    # SunProvider uses __slots__, so swap the whole provider: the sensor reads
    # manager.sun on every update anyway.
    manager.sun = SimpleNamespace(ready=lambda now=None: True, next_anchor=lambda *a, **k: None)
    await sensor.async_update(2.0)
    assert sensor.state == first


# ── Home Assistant discovery ─────────────────────────────────────────────


def _config_helper():
    """A config helper with just the fields discovery reads, and no more.

    MagicMock for the rest: ha_availabilty_message pulls a dozen attributes off
    it and listing them all here would make these tests fail for reasons that
    have nothing to do with the Sun.
    """
    helper = MagicMock()
    helper.topic_prefix = "boneio"
    helper.name = "Test"
    helper.device_type = "32x10a"
    helper.cloud_registration = False
    helper.serial_number = "blk000000"
    helper.real_serial = "blk000000"
    helper.is_web_active = False
    helper.network_info = {}
    helper.areas = {}
    helper.ha_child_devices = False
    helper.ha_discovery_prefix = "homeassistant"
    helper.get_area_name.return_value = None
    return helper


def test_a_measurement_sensor_is_discovered_with_its_unit():
    from boneio.integration.homeassistant import ha_sun_sensor_message

    msg = ha_sun_sensor_message(
        id="sun_elevation",
        name="Sun Elevation",
        config_helper=_config_helper(),
        unit_of_measurement="°",
        state_class="measurement",
    )
    assert msg["unit_of_measurement"] == "°"
    assert msg["state_class"] == "measurement"
    assert msg["value_template"] == "{{ value_json.state }}"
    # Not diagnostic: where the Sun is belongs on a dashboard.
    assert "entity_category" not in msg


def test_a_next_event_sensor_is_discovered_as_a_timestamp():
    from boneio.integration.homeassistant import ha_sun_sensor_message

    msg = ha_sun_sensor_message(
        id="sun_next_sunset",
        name="Sun Next Sunset",
        config_helper=_config_helper(),
        device_class="timestamp",
    )
    assert msg["device_class"] == "timestamp"


def test_above_the_horizon_is_discovered_as_a_binary_sensor():
    from boneio.integration.homeassistant import ha_sun_binary_sensor_message

    msg = ha_sun_binary_sensor_message(
        id="sun_above_horizon",
        name="Sun Above Horizon",
        config_helper=_config_helper(),
    )
    assert msg["payload_on"] == "on"
    assert msg["payload_off"] == "off"
    # It publishes on a sensor topic so the panel lists it too.
    assert msg["state_topic"].endswith("sensor/sun_above_horizon")
    assert msg["value_template"] == "{{ value_json.state }}"
