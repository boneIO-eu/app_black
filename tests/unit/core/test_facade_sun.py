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
