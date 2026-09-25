"""A panel save of a section keeps its !secret references.

The section is dumped from the values the panel sends back, and a secret is
dumped as the plain string it is — so saving the MQTT page wrote the broker
password into mqtt.yaml, undoing migration v7 on the first save.
"""

from __future__ import annotations

import os
import stat

import yaml

from boneio.core.config.yaml_util import load_yaml_file, update_config_section


def _device(tmp_path, mqtt_text: str, secrets_text: str | None = "mqtt_password: \"old-pass\"\n"):
    (tmp_path / "config.yaml").write_text("boneio:\n  name: t\nmqtt: !include mqtt.yaml\n")
    (tmp_path / "mqtt.yaml").write_text(mqtt_text)
    if secrets_text is not None:
        (tmp_path / "secrets.yaml").write_text(secrets_text)
    return str(tmp_path / "config.yaml")


def _save(config_file: str, **changes) -> dict:
    mqtt = dict(load_yaml_file(config_file)["mqtt"])
    mqtt.update(changes)
    result = update_config_section(config_file, "mqtt", mqtt)
    assert result["status"] == "success", result
    return mqtt


def test_an_unchanged_secret_stays_a_reference(tmp_path):
    config_file = _device(tmp_path, "host: localhost\nusername: boneio\npassword: !secret mqtt_password\n")
    _save(config_file, host="127.0.0.1")

    text = (tmp_path / "mqtt.yaml").read_text()
    assert "old-pass" not in text
    assert "password: !secret mqtt_password" in text
    assert yaml.safe_load((tmp_path / "secrets.yaml").read_text()) == {"mqtt_password": "old-pass"}
    assert load_yaml_file(config_file)["mqtt"]["host"] == "127.0.0.1"


def test_a_new_password_goes_under_the_same_name(tmp_path):
    config_file = _device(
        tmp_path, "host: localhost\npassword: !secret my_pass\n", "my_pass: old\nother: keep\n"
    )
    _save(config_file, password="brand-new")

    assert "brand-new" not in (tmp_path / "mqtt.yaml").read_text()
    assert yaml.safe_load((tmp_path / "secrets.yaml").read_text()) == {"my_pass": "brand-new", "other": "keep"}
    assert load_yaml_file(config_file)["mqtt"]["password"] == "brand-new"


def test_a_plain_broker_password_moves_to_secrets(tmp_path):
    config_file = _device(tmp_path, "host: localhost\npassword: typed-in\n", secrets_text=None)
    _save(config_file)

    assert "typed-in" not in (tmp_path / "mqtt.yaml").read_text()
    assert stat.S_IMODE(os.stat(tmp_path / "secrets.yaml").st_mode) == 0o600
    assert load_yaml_file(config_file)["mqtt"]["password"] == "typed-in"


def test_other_sections_with_plain_values_are_left_alone(tmp_path):
    config_file = _device(tmp_path, "host: localhost\n")
    result = update_config_section(config_file, "web", {"port": 8090, "password": "not-mqtt"})
    assert result["status"] == "success"
    assert "not-mqtt" in (tmp_path / "config.yaml").read_text()
