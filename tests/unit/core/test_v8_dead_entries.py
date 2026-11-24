"""Tests for Migration v8: what never ran and the section models refuse."""

from __future__ import annotations

import glob

from boneio.core.config.migrations import CURRENT_SCHEMA_VERSION, _has_legacy_fields, run_migrations
from boneio.core.config.migrations.v8_dead_entries import _fixes, _persist, migrate_v8_dead_entries
from boneio.core.config.yaml_util import load_yaml_file, validate_section

BONEIO = "boneio:\n  name: test\n  config_version: 7\n  version: 1.1\n  device_type: 24x16A\n"

EVENT = """\
event:
  # Kitchen
  - boneio_input: in_01
    pin: P8_37  # the board's own wins
    actions:
      single:
        - action: output
          boneio_output: out_01
        # no type: never ran
        - boneio_output: out_02
        - action: output
      double:
        - action: mqtt
          topic: a
          action_mqtt_msg: m
  - pin: P8_38
    boneio_input: in_02
    actions:
      single:
      - action: cover
"""


def test_the_dict_loses_only_what_never_ran():
    doc = {
        "event": [{
            "boneio_input": "in_01", "pin": "P8_37",
            "actions": {"single": [{"action": "output", "boneio_output": "out_01"}, {"boneio_output": "x"}],
                        "double": [{"action": "output"}]},
        }],
        "event_without_board": None,
        "binary_sensor": [{"pin": "P8_38", "name": "kept: no boneio_input"}],
        "schedule": [{"name": "s", "actions": [{"action": "mqtt", "topic": "t", "action_mqtt_msg": "m"}, {}]}],
        "virtual_switch": [{"name": "v", "actions": {"on_turn_on": [{"action": "virtual_switch"}]}}],
        "modbus_devices": [{"update_interval": 500}, {"update_interval": "0.5s"}, {"update_interval": "2s"}],
    }
    migrate_v8_dead_entries(doc)
    assert doc["event"] == [{
        "boneio_input": "in_01",
        "actions": {"single": [{"action": "output", "boneio_output": "out_01"}], "double": []},
    }]
    assert doc["binary_sensor"] == [{"pin": "P8_38", "name": "kept: no boneio_input"}]
    assert doc["schedule"][0]["actions"] == [{"action": "mqtt", "topic": "t", "action_mqtt_msg": "m"}]
    assert doc["virtual_switch"][0]["actions"] == {"on_turn_on": []}
    assert [d["update_interval"] for d in doc["modbus_devices"]] == ["1s", "1s", "2s"]


def test_an_action_missing_something_in_its_condition_is_kept():
    # The action ran; only its condition is incomplete, and that is a guess.
    action = {"action": "output", "boneio_output": "out_01", "condition": {"entity": "output"}}
    assert _fixes({"event": [{"boneio_input": "in_01", "actions": {"single": [action]}}]}) == []


def test_a_wrong_value_is_left_for_the_recovery_panel():
    # Refused for what it holds, not for what it lacks: no guessing.
    doc = {"event": [{"boneio_input": "in_01", "actions": {"single": [{"action": "output", "boneio_output": 5}]}}]}
    assert _fixes(doc) == []


def test_an_unversioned_config_with_dead_entries_is_migrated():
    assert _has_legacy_fields({"event": [{"boneio_input": "in_01", "pin": "P8_37"}]})
    assert not _has_legacy_fields({"event": [{"boneio_input": "in_01"}]})


def test_the_files_lose_the_same_and_keep_their_comments(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(BONEIO + "event: !include event.yaml\nmodbus_devices:\n- address: 1\n  model: sdm120\n"
                      "  update_interval: 500  # ms\n")
    (tmp_path / "event.yaml").write_text(EVENT.removeprefix("event:\n").replace("\n  ", "\n").lstrip())

    _persist(str(config))

    doc = load_yaml_file(str(config))
    assert doc["event"] == [
        {"boneio_input": "in_01",
         "actions": {"single": [{"action": "output", "boneio_output": "out_01"}],
                     "double": [{"action": "mqtt", "topic": "a", "action_mqtt_msg": "m"}]}},
        {"boneio_input": "in_02", "actions": {"single": []}},
    ]
    assert doc["modbus_devices"][0]["update_interval"] == "1s"
    event_text = (tmp_path / "event.yaml").read_text()
    assert "# Kitchen" in event_text and "# the board's own wins" not in event_text
    assert "- boneio_input: in_02" in event_text  # the dropped pin handed its dash on
    assert "update_interval: 1s  # ms" in config.read_text()
    assert (tmp_path / "backups" / "event.yaml.pre-v8").read_text().startswith("# Kitchen")
    assert (tmp_path / "backups" / "config.yaml.pre-v8").exists()
    assert _fixes(doc) == []


def test_an_inline_section_is_edited_in_config_yaml(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(BONEIO + EVENT)
    _persist(str(config))
    doc = load_yaml_file(str(config))
    assert _fixes(doc) == []
    assert doc["event"][1] == {"boneio_input": "in_02", "actions": {"single": []}}
    assert validate_section("event", doc["event"], doc["boneio"]) == []


def test_what_it_cannot_reach_it_leaves_alone(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(BONEIO + "event:\n  - !include in1.yaml\n")
    (tmp_path / "in1.yaml").write_text("boneio_input: in_01\npin: P8_37\n")
    _persist(str(config))
    assert (tmp_path / "in1.yaml").read_text() == "boneio_input: in_01\npin: P8_37\n"
    assert not (tmp_path / "backups").exists()


def test_a_version_7_config_is_migrated_on_load(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(BONEIO + EVENT)
    doc, version = run_migrations(load_yaml_file(str(config)), config_file=str(config))
    assert version == CURRENT_SCHEMA_VERSION
    assert f"config_version: {CURRENT_SCHEMA_VERSION}" in config.read_text()
    assert load_yaml_file(str(config))["event"] == doc["event"]


def test_no_factory_config_has_anything_to_remove():
    paths = sorted(glob.glob("boneio/factory_config/*/*/config.yaml"))
    assert paths
    for path in paths:
        assert _fixes(load_yaml_file(path)) == [], path
