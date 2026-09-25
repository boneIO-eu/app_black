"""Tests for Migration v7: the broker password moves to secrets.yaml."""

from __future__ import annotations

import os
import stat

import pytest
import yaml

from boneio.core.config.migrations import _has_legacy_fields, run_migrations
from boneio.core.config.migrations.v7_mqtt_password_secret import (
    _persist_mqtt_password_secret,
)
from boneio.core.config.yaml_patch import YamlPatchError
from boneio.core.config.yaml_util import SecretStr, load_yaml_file

MAIN = "boneio:\n  name: test\n  config_version: 6\nmqtt: !include mqtt.yaml\n"


def _device(tmp_path, mqtt_text: str, secrets_text: str | None = None):
    (tmp_path / "config.yaml").write_text(MAIN)
    (tmp_path / "mqtt.yaml").write_text(mqtt_text)
    if secrets_text is not None:
        (tmp_path / "secrets.yaml").write_text(secrets_text)
    return str(tmp_path / "config.yaml")


def _mode(path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


def test_the_include_every_controller_ships_with(tmp_path):
    config_file = _device(tmp_path, "host: localhost\nusername: boneio\npassword: s3cr:et # old\nport: 1883\n")
    _persist_mqtt_password_secret(config_file)

    assert (tmp_path / "mqtt.yaml").read_text() == (
        "host: localhost\nusername: boneio\npassword: !secret mqtt_password\nport: 1883\n"
    )
    assert yaml.safe_load((tmp_path / "secrets.yaml").read_text()) == {"mqtt_password": "s3cr:et"}
    assert _mode(tmp_path / "secrets.yaml") == 0o600
    # And the loader reads back the very same password.
    assert load_yaml_file(config_file)["mqtt"]["password"] == "s3cr:et"


@pytest.mark.parametrize("password", ['"quo\\"ted"', "'it''s'", "123456789", "'  spaces  '"])
def test_quoting_survives_the_trip(tmp_path, password):
    config_file = _device(tmp_path, f"host: localhost\npassword: {password}\n")
    before = yaml.safe_load((tmp_path / "mqtt.yaml").read_text())["password"]
    _persist_mqtt_password_secret(config_file)
    assert load_yaml_file(config_file)["mqtt"]["password"] == str(before)


def test_inline_mqtt_section(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("boneio:\n  name: t\nmqtt:\n  host: localhost\n  password: boneio123\n")
    _persist_mqtt_password_secret(str(config_file))
    assert "password: !secret mqtt_password" in config_file.read_text()
    assert load_yaml_file(str(config_file))["mqtt"]["password"] == "boneio123"


def test_an_existing_reference_is_left_alone(tmp_path):
    mqtt = "host: localhost\npassword: !secret my_pass\n"
    config_file = _device(tmp_path, mqtt, "my_pass: abc\n")
    _persist_mqtt_password_secret(config_file)
    assert (tmp_path / "mqtt.yaml").read_text() == mqtt
    assert (tmp_path / "secrets.yaml").read_text() == "my_pass: abc\n"


@pytest.mark.parametrize("mqtt", ["host: localhost\n", "host: localhost\npassword:\n", 'host: x\npassword: ""\n'])
def test_nothing_to_move(tmp_path, mqtt):
    config_file = _device(tmp_path, mqtt)
    _persist_mqtt_password_secret(config_file)
    assert (tmp_path / "mqtt.yaml").read_text() == mqtt
    assert not (tmp_path / "secrets.yaml").exists()


def test_other_secrets_are_kept_and_a_taken_name_is_not_overwritten(tmp_path):
    config_file = _device(
        tmp_path,
        "host: localhost\npassword: mine\n",
        "# my secrets\nwifi: \"w\"\nmqtt_password: someone-elses\n",
    )
    os.chmod(tmp_path / "secrets.yaml", 0o644)
    _persist_mqtt_password_secret(config_file)

    secrets = yaml.safe_load((tmp_path / "secrets.yaml").read_text())
    assert secrets == {"wifi": "w", "mqtt_password": "someone-elses", "mqtt_password_2": "mine"}
    assert (tmp_path / "secrets.yaml").read_text().startswith("# my secrets\n")
    assert "!secret mqtt_password_2" in (tmp_path / "mqtt.yaml").read_text()
    assert _mode(tmp_path / "secrets.yaml") == 0o600


def test_the_same_value_already_there_is_reused(tmp_path):
    config_file = _device(tmp_path, "password: same\n", "mqtt_password: same\n")
    _persist_mqtt_password_secret(config_file)
    assert (tmp_path / "secrets.yaml").read_text() == "mqtt_password: same\n"
    assert "!secret mqtt_password\n" in (tmp_path / "mqtt.yaml").read_text()


def test_a_broken_secrets_file_stops_it_before_anything_changes(tmp_path):
    mqtt = "password: mine\n"
    config_file = _device(tmp_path, mqtt, "- not\n- a mapping\n")
    with pytest.raises(YamlPatchError):
        _persist_mqtt_password_secret(config_file)
    assert (tmp_path / "mqtt.yaml").read_text() == mqtt


def test_run_migrations_from_v6(tmp_path):
    config_file = _device(tmp_path, "host: localhost\npassword: mine\n")
    doc = load_yaml_file(config_file)
    doc, version = run_migrations(doc, 6, config_file)
    assert version == 7
    assert "config_version: 7" in (tmp_path / "config.yaml").read_text()
    assert yaml.safe_load((tmp_path / "secrets.yaml").read_text()) == {"mqtt_password": "mine"}
    assert doc["mqtt"]["password"] == "mine"


def test_legacy_detection():
    assert _has_legacy_fields({"mqtt": {"host": "localhost", "password": "plain"}})
    assert not _has_legacy_fields({"mqtt": {"host": "localhost", "password": SecretStr("x", "mqtt_password")}})
    assert not _has_legacy_fields({"mqtt": {"host": "localhost"}})


def test_no_cache_is_written_from_a_document_read_before_the_migration(tmp_path, monkeypatch):
    """Cached here, the password would sit in .cache.pkl by value."""
    from boneio.core.config import yaml_util

    saved = []
    monkeypatch.setattr(yaml_util, "_save_config_cache", lambda *a: saved.append(a))
    config_file = _device(tmp_path, "host: localhost\nusername: boneio\npassword: mine\n")
    (tmp_path / "config.yaml").write_text(
        "boneio:\n  name: test\n  device_type: 32x10\n  version: '0.8'\n  config_version: 6\nmqtt: !include mqtt.yaml\n"
    )

    yaml_util.load_config_from_file(config_file)
    assert saved == []
    assert "!secret mqtt_password" in (tmp_path / "mqtt.yaml").read_text()

    yaml_util.load_config_from_file(config_file)
    assert len(saved) == 1
