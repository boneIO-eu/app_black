"""The Home Assistant security entity.

The point of the entity is that a device nobody visits still says something,
so the tests care most about the paths where something is missing or broken:
those are exactly the devices this is for.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from boneio.core.manager.security_alert import SecurityAlertPublisher, build_payloads
from boneio.core.security.posture import Posture, evaluate
from boneio.webui.middleware import auth as auth_module


def _config_helper():
    """A ConfigHelper stand-in the discovery builder can walk.

    The builder reads a dozen presentation attributes that have nothing to do
    with this entity, so the ones that matter are set and the rest are left to
    the mock.
    """
    helper = MagicMock()
    helper.topic_prefix = "boneio"
    helper.name = "boneIO Black"
    helper.serial_number = "aabbccdd"
    helper.device_type = "24x16"
    helper.ha_discovery_prefix = "homeassistant"
    helper.cloud_registration = False
    helper.is_web_active = False
    helper.network_info = {}
    helper.ha_child_devices = False
    helper.areas = {}
    helper._cloud_reg = None
    return helper


class _FakeManager:
    """Only the four things the publisher touches."""

    def __init__(self, config_file: str) -> None:
        self._config_file_path = config_file
        self._config_helper = _config_helper()
        self._topic_prefix = "boneio"
        self.published: list[tuple[str, str]] = []
        self.discovery: list[dict] = []

    def send_message(self, topic, payload, retain=False):
        self.published.append((topic, payload))

    def publish_ha_discovery(self, id, ha_type, payload):
        self.discovery.append({"id": id, "ha_type": ha_type, "payload": payload})


@pytest.fixture
def device(tmp_path):
    """A device with the factory MQTT password and no accounts."""
    config = tmp_path / "config.yaml"
    config.write_text("mqtt:\n  host: localhost\n  password: boneio123\n", encoding="utf-8")
    return _FakeManager(str(config))


async def test_publishes_discovery_and_state(device):
    """Registration and the first state go out together."""
    await SecurityAlertPublisher(device).send_ha_autodiscovery()

    assert device.discovery[0]["ha_type"] == "binary_sensor"
    assert device.discovery[0]["payload"]["device_class"] == "problem"

    topics = dict(device.published)
    assert json.loads(topics["boneio/security/state"])["state"] == "ON"
    attrs = json.loads(topics["boneio/security/attributes"])
    assert attrs["critical"] >= 1
    assert any(r["id"] == "mqtt_password" for r in attrs["recommendations"])


async def test_clean_device_reports_off(tmp_path):
    """Nothing outstanding must read OFF, not 'unavailable'."""
    config = tmp_path / "config.yaml"
    config.write_text(
        "mqtt:\n  host: localhost\n  password: something-else\n"
        "web:\n  security:\n    frame_ancestors: 'self'\n",
        encoding="utf-8",
    )
    users = tmp_path / "users.json"
    users.write_text(
        json.dumps(
            {
                "version": 1,
                "users": [
                    {
                        "username": "admin",
                        "password_hash": "scrypt$dummy",
                        "role": "admin",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    manager = _FakeManager(str(config))
    publisher = SecurityAlertPublisher(manager)
    # Cloud certificate in place, so the INFO check passes too.
    manager._config_helper._cloud_reg = type("C", (), {"is_cloud_config_active": lambda self: True})()

    await publisher.publish_state()
    assert json.loads(dict(manager.published)["boneio/security/state"])["state"] == "OFF"


async def test_unreadable_config_does_not_stop_startup(tmp_path):
    """A missing config must not raise out of autodiscovery."""
    manager = _FakeManager(str(tmp_path / "gone.yaml"))
    await SecurityAlertPublisher(manager).send_ha_autodiscovery()
    assert manager.published  # it still said something


async def test_attributes_carry_a_readable_summary(device):
    """An HA notification templates against this string."""
    await SecurityAlertPublisher(device).publish_state()
    attrs = json.loads(dict(device.published)["boneio/security/attributes"])
    assert "MQTT" in attrs["summary"]
    assert attrs["worst"] == "critical"


def test_empty_posture_summary_is_not_empty_string():
    """'No recommendations' must be a sentence, not a blank."""
    state, attrs = build_payloads(Posture(checks=[]))
    assert json.loads(state)["state"] == "OFF"
    assert json.loads(attrs)["summary"]
    assert json.loads(attrs)["worst"] == "none"


@pytest.mark.parametrize(
    "config,provisioned",
    [
        ({}, False),
        ({"web": {"auth": {"allow_anonymous": True}}}, False),
        ({"web": {"auth": {"username": "a", "password": "b"}}}, False),
        ({"web": {"auth": {"allow_anonymous": True}}}, True),
        ({"mqtt": {"password": "boneio123"}}, True),
    ],
)
def test_both_entry_points_agree(monkeypatch, config, provisioned):
    """The sensor and the API must never disagree about the same device.

    ``evaluate_config`` derives from the files what ``evaluate`` is handed by
    the running web server. If those two ever drift, the panel and Home
    Assistant tell the user different things about one controller.
    """
    from boneio.core.security.posture import evaluate_config

    class _Store:
        def is_provisioned(self):
            return provisioned

    monkeypatch.setattr(auth_module, "_user_store", _Store())
    monkeypatch.setattr(
        auth_module, "_auth_config", (config.get("web", {}).get("auth", {}) or {})
    )
    monkeypatch.setattr(
        auth_module, "_allow_anonymous", bool(config.get("web", {}).get("auth", {}).get("allow_anonymous"))
    )

    from_files = evaluate_config(config, user_store=_Store())
    from_runtime = evaluate(
        config,
        is_provisioned=provisioned,
        anonymous_allowed=auth_module.is_anonymous_allowed(),
        auth_required=auth_module.is_auth_required(),
        cloud_active=False,
    )
    assert from_files.to_dict() == from_runtime.to_dict()


async def test_advice_alone_does_not_raise_the_problem_sensor(tmp_path):
    """A default device is OFF, and still carries the advice.

    Self-signed certificate and unset frame_ancestors apply to nearly every
    controller. A problem sensor that is ON everywhere gets automated around.
    """
    config = tmp_path / "config.yaml"
    config.write_text("mqtt:\n  host: localhost\n  password: changed\n", encoding="utf-8")
    (tmp_path / "users.json").write_text(
        json.dumps(
            {
                "version": 1,
                "users": [
                    {"username": "admin", "password_hash": "scrypt$x", "role": "admin"}
                ],
            }
        ),
        encoding="utf-8",
    )

    manager = _FakeManager(str(config))
    await SecurityAlertPublisher(manager).publish_state()

    topics = dict(manager.published)
    assert json.loads(topics["boneio/security/state"])["state"] == "OFF"
    attrs = json.loads(topics["boneio/security/attributes"])
    assert attrs["actionable"] == 0
    assert attrs["failed"] > 0  # the advice is still there to read


async def test_summary_describes_only_what_turned_the_sensor_on(device):
    """An automation templating on `summary` must not report the advice.

    The state counts actionable findings; a summary listing every finding
    would make a notification say something the sensor does not.
    """
    await SecurityAlertPublisher(device).publish_state()
    attrs = json.loads(dict(device.published)["boneio/security/attributes"])

    assert "MQTT" in attrs["summary"]
    assert "certificate" not in attrs["summary"].lower()
    assert "certificate" in attrs["advice"].lower()
    assert attrs["summary"].count(";") + 1 == attrs["actionable"]
