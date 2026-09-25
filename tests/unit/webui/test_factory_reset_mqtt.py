"""A factory reset keeps the device's connection to its own broker.

Images draw the MQTT password per device at first boot, while the example
configs a reset copies say "boneio123". Copied as they were, a reset left
boneIO unable to reach its broker — the failure first seen on a PC-built dev15
card, reached a second way.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from boneio.core.config.yaml_util import load_yaml_file
from boneio.webui.routes import update


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "boneio").mkdir()
    return tmp_path


def _reset(board: str = "32x10") -> dict:
    request = update.FactoryResetRequest(device_type=board, version=update.HARDWARE_VERSIONS[-1])
    return asyncio.run(update.factory_reset(request))


def _password_after(home: Path) -> str:
    mqtt = (home / "boneio" / "mqtt.yaml").read_text()
    assert "password: !secret mqtt_password" in mqtt
    return load_yaml_file(str(home / "boneio" / "secrets.yaml"))["mqtt_password"]


def test_a_plain_password_moves_to_secrets_yaml(home):
    (home / "boneio" / "mqtt.yaml").write_text("host: localhost\npassword: per-device-1\n")
    assert _reset()["status"] == "success"
    assert _password_after(home) == "per-device-1"


def test_a_secret_password_survives_and_other_secrets_stay(home):
    (home / "boneio" / "mqtt.yaml").write_text("host: localhost\npassword: !secret mqtt_password\n")
    (home / "boneio" / "secrets.yaml").write_text(
        'mqtt_password: "per-device-2"\nwifi_psk: keep-me\n'
    )
    assert _reset()["status"] == "success"
    assert _password_after(home) == "per-device-2"
    assert load_yaml_file(str(home / "boneio" / "secrets.yaml"))["wifi_psk"] == "keep-me"


@pytest.mark.parametrize(("written", "value"), [
    ("password: 'a\"b\\\\c'\n", 'a"b\\\\c'),     # single quotes: backslashes literal
    ('password: "x\\"y\\\\z"\n', 'x"y\\z'),       # double quotes: escapes resolved
    ("password: plain-123\n", "plain-123"),
])
def test_the_password_is_read_and_written_as_yaml(home, written, value):
    (home / "boneio" / "mqtt.yaml").write_text(written)
    _reset()
    assert _password_after(home) == value


def test_without_mqtt_yaml_the_example_is_kept_as_it_was(home):
    _reset()
    assert "password: !secret" not in (home / "boneio" / "mqtt.yaml").read_text()
