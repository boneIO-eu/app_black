"""Reloading outputs or covers must not drop other entities from the HA discovery cache.

The MQTT client deletes from Home Assistant every discovery topic it receives
that the cache does not hold — the broker's replay on reconnect, and the echo
of our own publishes. Outputs share switch/light/valve with schedules, virtual
switches, irrigation, modbus and remote outputs; covers share COVER with gate
covers and remote covers. A reload that wiped a whole type took all of those
out of HA on the next reconnect.
"""

from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

mock_gpiod = MagicMock()
sys.modules.setdefault("gpiod", mock_gpiod)
sys.modules.setdefault("gpiod.line", mock_gpiod.line)

from boneio.core.config.config_helper import ConfigHelper  # noqa: E402
from boneio.core.manager.covers import CoverManager  # noqa: E402
from boneio.core.manager.outputs import OutputManager  # noqa: E402


def _topic(ha_type: str, entity_id: str) -> str:
    return f"homeassistant/{ha_type}/blk0001/{entity_id}/config"


SHARED = [
    ("switch", "schedule_podlewanie"),
    ("switch", "virtual_tryb_urlop"),
    ("valve", "ogrod_trawnik"),
    ("switch", "modbus_pompa"),
    ("switch", "remote_out_1"),
    ("cover", "brama_wjazdowa"),
]


@pytest.fixture
def config_helper():
    helper = ConfigHelper(name="black", serial_override="blk0001")
    for ha_type, entity_id in SHARED:
        helper.add_autodiscovery_msg(ha_type=ha_type, topic=_topic(ha_type, entity_id), payload={"name": None})
    return helper


@pytest.fixture
def manager(config_helper):
    def publish_ha_discovery(id, ha_type, payload):
        config_helper.add_autodiscovery_msg(topic=_topic(ha_type, id), ha_type=ha_type, payload=payload)

    return SimpleNamespace(
        _config_helper=config_helper,
        config_helper=config_helper,
        publish_ha_discovery=MagicMock(side_effect=publish_ha_discovery),
        send_message=MagicMock(),
        _event_bus=MagicMock(),
        loop=MagicMock(),
    )


def _cached(config_helper, ha_type, entity_id) -> bool:
    return config_helper.is_topic_in_autodiscovery(_topic(ha_type, entity_id))


def _removed(manager) -> set[str]:
    return {
        c.kwargs["topic"]
        for c in manager.send_message.call_args_list
        if c.kwargs.get("payload") is None and c.kwargs.get("retain")
    }


# ── outputs ──────────────────────────────────────────────────────────────────


def _output_manager(manager, announced: list[tuple[str, str]]) -> OutputManager:
    outputs = OutputManager.__new__(OutputManager)
    outputs._manager = manager
    outputs._outputs = {}
    outputs._configured_output_groups = {}
    outputs._interlock_manager = MagicMock()
    outputs._outputs_group = []
    outputs._ha_topics = set()
    for ha_type, entity_id in announced:
        outputs._publish_discovery(id=entity_id, ha_type=ha_type, payload={"name": entity_id})
    manager.publish_ha_discovery.reset_mock()
    return outputs


def _reload_outputs(outputs, manager, announce_now: list[tuple[str, str]]) -> None:
    """Run reload_outputs with an output init that announces ``announce_now``."""

    def fake_init(relay_pins, reload_config=False, preserved_states=None):
        for ha_type, entity_id in announce_now:
            outputs._publish_discovery(id=entity_id, ha_type=ha_type, payload={"name": entity_id})

    with (
        patch.object(manager._config_helper, "get_config", return_value={"output": [], "output_group": []}),
        patch.object(outputs, "_initialize_outputs", side_effect=fake_init),
        patch.object(outputs, "_configure_output_groups"),
        patch.object(outputs, "_broadcast_all_states"),
    ):
        asyncio.new_event_loop().run_until_complete(outputs.reload_outputs())


def test_output_init_on_reload_keeps_shared_entries(manager, config_helper):
    outputs = _output_manager(manager, [])

    outputs._initialize_outputs(relay_pins=[], reload_config=True)

    for ha_type, entity_id in SHARED:
        assert _cached(config_helper, ha_type, entity_id), entity_id


def test_output_reload_keeps_shared_entries(manager, config_helper):
    outputs = _output_manager(manager, [("switch", "out_01")])

    _reload_outputs(outputs, manager, [("switch", "out_01")])

    for ha_type, entity_id in SHARED:
        assert _cached(config_helper, ha_type, entity_id), entity_id
    assert _cached(config_helper, "switch", "out_01")
    assert _removed(manager) == set()


def test_deleted_output_and_its_duration_are_removed(manager, config_helper):
    outputs = _output_manager(manager, [("switch", "out_01"), ("number", "out_01_duration"), ("light", "out_02")])

    _reload_outputs(outputs, manager, [("light", "out_02")])

    assert _removed(manager) == {_topic("switch", "out_01"), _topic("number", "out_01_duration")}
    assert not _cached(config_helper, "switch", "out_01")
    assert not _cached(config_helper, "number", "out_01_duration")
    assert _cached(config_helper, "light", "out_02")


def test_type_change_removes_the_old_type(manager, config_helper):
    outputs = _output_manager(manager, [("switch", "out_01")])

    _reload_outputs(outputs, manager, [("light", "out_01")])

    assert _removed(manager) == {_topic("switch", "out_01")}
    assert _cached(config_helper, "light", "out_01")


def test_output_now_driving_a_cover_is_removed(manager, config_helper):
    """An output switched to type cover is no longer announced on its own."""
    outputs = _output_manager(manager, [("switch", "out_01")])

    _reload_outputs(outputs, manager, [])

    assert _removed(manager) == {_topic("switch", "out_01")}


def test_remote_outputs_are_not_owned(manager, config_helper):
    outputs = _output_manager(manager, [])
    outputs._publish_discovery(id="remote_out_1", ha_type="switch", payload={}, remote=True)

    _reload_outputs(outputs, manager, [])

    assert _removed(manager) == set()
    assert _cached(config_helper, "switch", "remote_out_1")


# ── covers ───────────────────────────────────────────────────────────────────


def _cover(cover_id: str, *, remote: bool = False, show_in_ha: bool = True) -> MagicMock:
    cover = MagicMock()
    cover.id = cover_id
    cover.name = cover_id
    cover._name = cover_id
    cover.kind = "time"
    cover.is_remote = remote
    cover.show_in_ha = show_in_ha
    cover.device_class = None
    cover.area = None
    return cover


def _cover_manager(manager, covers: dict) -> CoverManager:
    cm = CoverManager.__new__(CoverManager)
    cm._manager = manager
    cm._covers = covers
    cm._config_covers = []
    manager.outputs = MagicMock()
    for cover_id, cover in covers.items():
        if cover.show_in_ha:
            manager.publish_ha_discovery(id=cover_id, ha_type="cover", payload={"name": cover_id})
    manager.publish_ha_discovery.reset_mock()
    return cm


def _reload_covers(cm, manager, cover_config: list[dict]) -> None:
    with patch.object(manager._config_helper, "get_config", return_value={"cover": cover_config}):
        cm._configure_covers(reload_config=True)


def test_cover_reload_keeps_gate_and_remote_covers(manager, config_helper):
    cm = _cover_manager(manager, {"remote_cover": _cover("remote_cover", remote=True)})

    _reload_covers(cm, manager, [])

    assert "remote_cover" in cm._covers
    assert _cached(config_helper, "cover", "remote_cover")
    assert _cached(config_helper, "cover", "brama_wjazdowa")
    assert _removed(manager) == set()


def test_deleted_cover_is_removed(manager, config_helper):
    cm = _cover_manager(manager, {"salon": _cover("salon")})

    _reload_covers(cm, manager, [])

    assert "salon" not in cm._covers
    assert _removed(manager) == {_topic("cover", "salon")}
    assert _cached(config_helper, "cover", "brama_wjazdowa")


def test_hiding_a_cover_removes_it(manager, config_helper):
    cm = _cover_manager(manager, {"salon": _cover("salon")})

    _reload_covers(
        cm, manager, [{"id": "salon", "open_relay": "o1", "close_relay": "o2", "show_in_ha": False}]
    )

    assert not _cached(config_helper, "cover", "salon")
    assert _topic("cover", "salon") in _removed(manager)
    manager.publish_ha_discovery.assert_not_called()


def test_cover_removal_only_touches_the_cover_type(manager, config_helper):
    """A switch that happens to share the cover's id is not the cover's."""
    config_helper.add_autodiscovery_msg(ha_type="switch", topic=_topic("switch", "salon"), payload={})
    cm = _cover_manager(manager, {"salon": _cover("salon")})

    _reload_covers(cm, manager, [])

    assert _cached(config_helper, "switch", "salon")


def test_unchanged_cover_is_updated_in_place(manager, config_helper):
    """Removing before re-publishing makes HA delete and recreate the entity."""
    cm = _cover_manager(manager, {"salon": _cover("salon")})

    _reload_covers(cm, manager, [{"id": "salon", "open_relay": "o1", "close_relay": "o2"}])

    assert _removed(manager) == set()
    assert _cached(config_helper, "cover", "salon")
    manager.publish_ha_discovery.assert_called_once()


def test_cover_moved_to_another_area_leaves_the_old_device(manager, config_helper):
    cm = _cover_manager(manager, {"salon": _cover("salon")})

    _reload_covers(cm, manager, [{"id": "salon", "open_relay": "o1", "close_relay": "o2", "area": "kuchnia"}])

    assert _removed(manager) == {_topic("cover", "salon")}
    assert _cached(config_helper, "cover", "salon")


def test_unchanged_group_is_not_removed(manager, config_helper):
    """Removing before re-publishing makes HA delete and recreate the group."""
    outputs = _output_manager(manager, [("light", "grupa_1")])
    outputs._configured_output_groups = {"grupa_1": SimpleNamespace(id="grupa_1", area=None, cleanup=MagicMock())}

    _reload_outputs(outputs, manager, [("light", "grupa_1")])

    assert _removed(manager) == set()


def test_group_changing_type_drops_the_old_one(manager, config_helper):
    outputs = _output_manager(manager, [("switch", "grupa_1")])
    outputs._configured_output_groups = {"grupa_1": SimpleNamespace(id="grupa_1", area=None, cleanup=MagicMock())}

    _reload_outputs(outputs, manager, [("light", "grupa_1")])

    assert _removed(manager) == {_topic("switch", "grupa_1")}
    assert _cached(config_helper, "light", "grupa_1")


def test_remote_output_with_an_area_is_left_alone(manager, config_helper):
    """Absent from the output section, a remote output looked moved to no area."""
    outputs = _output_manager(manager, [])
    outputs._outputs = {"remote_out_1": SimpleNamespace(is_remote=True, area="salon", is_active=False)}

    _reload_outputs(outputs, manager, [])

    assert _removed(manager) == set()
    assert _cached(config_helper, "switch", "remote_out_1")
