"""The panel's routes for MQTT certificates."""

from __future__ import annotations

import stat
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from boneio.core.auth.models import Role  # noqa: E402
from boneio.webui.middleware import policy  # noqa: E402
from boneio.webui.routes import mqtt_tls as route  # noqa: E402
from tests.tls_material import encrypted_key, make_ca, make_leaf  # noqa: E402


@pytest.fixture
def state(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("mqtt:\n  host: localhost\n")
    bus = MagicMock(spec=["reload_credentials", "tls_error", "state"])
    bus.tls_error = None
    bus.state = True
    manager = SimpleNamespace(
        _message_bus=SimpleNamespace(buses=[bus]),
        reload_config=AsyncMock(return_value={"status": "success"}),
    )
    app_state = SimpleNamespace(yaml_config_file=str(config), manager=manager)
    route.set_app_state(app_state)
    yield app_state
    route.set_app_state(None)


@pytest.fixture
def client(state):
    app = FastAPI()
    app.include_router(route.router)
    return TestClient(app)


@pytest.fixture(scope="module")
def ca():
    return make_ca()


def test_nothing_is_stored_on_a_fresh_device(client):
    body = client.get("/api/mqtt-tls/client").json()
    assert body["files"] == {"ca": None, "client": None}
    assert body["tls_error"] is None
    assert body["connected"] is True


def test_a_ca_upload_is_stored_and_the_client_asked_to_reconnect(client, state, tmp_path, ca):
    response = client.post(
        "/api/mqtt-tls/client/ca", files={"certificate": ("ca.pem", ca.cert)}
    )
    assert response.status_code == 200
    assert response.json()["stored"]["path"] == "certs/mqtt-ca.pem"
    assert (tmp_path / "certs" / "mqtt-ca.pem").read_bytes() == ca.cert
    state.manager.reload_config.assert_awaited_once_with(reload_sections=["mqtt"])
    assert client.get("/api/mqtt-tls/client").json()["files"]["ca"]["subject"] == "CN=Test CA"


def test_a_file_that_is_not_a_ca_is_refused(client, state):
    response = client.post(
        "/api/mqtt-tls/client/ca", files={"certificate": ("ca.pem", b"not a certificate")}
    )
    assert response.status_code == 422
    state.manager.reload_config.assert_not_awaited()


def test_a_client_pair_is_stored_privately(client, tmp_path, ca):
    pair = make_leaf(ca, ("boneio",), client=True)
    response = client.post(
        "/api/mqtt-tls/client/certificate",
        files={"certificate": ("c.pem", pair.cert), "key": ("c.key", pair.key)},
    )
    assert response.status_code == 200
    stored = response.json()["stored"]
    assert stored["path"] == "certs/mqtt-client.pem"
    assert stored["key_path"] == "certs/mqtt-client.key"
    assert stat.S_IMODE((tmp_path / "certs" / "mqtt-client.key").stat().st_mode) == 0o600
    # The key never comes back out.
    assert "PRIVATE KEY" not in response.text
    assert "PRIVATE KEY" not in client.get("/api/mqtt-tls/client").text


def test_a_protected_key_is_refused_with_a_reason(client, ca):
    pair = make_leaf(ca, ("boneio",), client=True)
    response = client.post(
        "/api/mqtt-tls/client/certificate",
        files={"certificate": ("c.pem", pair.cert), "key": ("c.key", encrypted_key(pair))},
    )
    assert response.status_code == 422
    assert "passphrase" in response.json()["detail"]


def test_files_can_be_removed(client, ca):
    client.post("/api/mqtt-tls/client/ca", files={"certificate": ("ca.pem", ca.cert)})
    assert client.delete("/api/mqtt-tls/client/ca").json() == {"removed": True}
    assert client.delete("/api/mqtt-tls/client/nonsense").status_code == 404


def test_a_tls_problem_of_the_running_client_is_reported(client, state):
    state.manager._message_bus.buses[0].tls_error = "The CA certificate x does not exist."
    assert "does not exist" in client.get("/api/mqtt-tls/client").json()["tls_error"]


# ------------------------------------------------------------------ policy


def test_viewers_cannot_read_what_the_device_trusts():
    assert not policy.role_allows(Role.VIEWER, "GET", "/api/mqtt-tls/client")
    assert policy.role_allows(Role.ADMIN, "GET", "/api/mqtt-tls/client")


@pytest.mark.parametrize("method,path", [
    ("POST", "/api/mqtt-tls/client/ca"),
    ("POST", "/api/mqtt-tls/client/certificate"),
    ("DELETE", "/api/mqtt-tls/client/ca"),
])
def test_changing_trust_wants_a_fresh_password(method, path):
    assert policy.requires_recent_auth(method, path)


# ------------------------------------------------------------- the broker


from boneio.core import system_ops  # noqa: E402
from boneio.core.messaging import broker_tls  # noqa: E402


class FakeHelper:
    """system_ops as the routes see it, without sudo."""

    def __init__(self, monkeypatch, supported=True):
        self.calls: list[tuple] = []
        self.mode = "off"
        self.fail_with: str | None = None
        monkeypatch.setattr(system_ops, "helper_supports", lambda verb: supported)
        monkeypatch.setattr(system_ops, "mqtt_tls_state", self.state)
        monkeypatch.setattr(system_ops, "mqtt_tls_cert", self.cert)
        monkeypatch.setattr(system_ops, "mqtt_tls_mode", self.set_mode)
        monkeypatch.setattr(system_ops, "mqtt_tls_cert_remove", self.remove)
        monkeypatch.setattr(route, "_reached_by", lambda: ["boneio-test", "boneio-test.local", "192.168.1.50"])

    def _result(self, stdout=""):
        if self.fail_with:
            return system_ops.Result(1, "", f"[ERROR] REFUSED: {self.fail_with}\n")
        return system_ops.Result(0, stdout, "")

    def state(self):
        import json

        return self._result(json.dumps({"mode": self.mode, "certificate": True, "active": True, "tls_port": 8883}))

    def cert(self, bundle):
        self.calls.append(("cert", bundle))
        return self._result()

    def set_mode(self, mode):
        self.calls.append(("mode", mode))
        return self._result()

    def remove(self):
        self.calls.append(("remove",))
        return self._result()


def _app_mqtt(state, **mqtt):
    helper = MagicMock()
    helper.get_config.return_value = {"mqtt": mqtt}
    state.config_helper = helper


def test_the_broker_state_describes_mode_and_app(client, state, monkeypatch):
    FakeHelper(monkeypatch)
    _app_mqtt(state, host="localhost", port=1883)
    monkeypatch.setattr(broker_tls, "installed", lambda reached_by=None: None)
    body = client.get("/api/mqtt-tls/broker").json()
    assert body["supported"] is True
    assert body["mode"] == "off"
    assert body["app"]["uses_local_broker"] is True
    assert body["app"]["blocks_required"] is False


def test_an_old_helper_is_reported_not_called(client, state, monkeypatch):
    fake = FakeHelper(monkeypatch, supported=False)
    _app_mqtt(state, host="localhost")
    body = client.get("/api/mqtt-tls/broker").json()
    assert body["supported"] is False
    response = client.post("/api/mqtt-tls/broker/generate")
    assert response.status_code == 409
    assert "migrations" in response.json()["detail"]
    assert fake.calls == []


def test_generating_hands_the_helper_a_chain_and_a_key(client, state, monkeypatch):
    fake = FakeHelper(monkeypatch)
    _app_mqtt(state, host="localhost")
    response = client.post("/api/mqtt-tls/broker/generate")
    assert response.status_code == 200
    (verb, bundle), = fake.calls
    assert verb == "cert"
    assert bundle.count("BEGIN CERTIFICATE") == 2
    assert bundle.count("BEGIN PRIVATE KEY") == 1
    assert "PRIVATE KEY" not in response.text


def test_an_uploaded_certificate_goes_to_the_helper_with_its_ca(client, state, monkeypatch, ca):
    fake = FakeHelper(monkeypatch)
    leaf = make_leaf(ca, ("boneio-test.local",))
    response = client.post(
        "/api/mqtt-tls/broker/certificate",
        files={"certificate": ("b.crt", leaf.cert), "key": ("b.key", leaf.key), "ca": ("ca.crt", ca.cert)},
    )
    assert response.status_code == 200, response.text
    assert response.json()["certificate"]["ca_available"] is True
    assert fake.calls[0][1].count("BEGIN CERTIFICATE") == 2


def test_an_unusable_upload_never_reaches_the_helper(client, state, monkeypatch, ca):
    fake = FakeHelper(monkeypatch)
    leaf = make_leaf(ca, ("x",))
    other = make_leaf(ca, ("y",))
    response = client.post(
        "/api/mqtt-tls/broker/certificate",
        files={"certificate": ("b.crt", leaf.cert), "key": ("b.key", other.key)},
    )
    assert response.status_code == 422
    assert fake.calls == []


def test_the_helpers_refusal_comes_back_as_its_sentence(client, state, monkeypatch):
    fake = FakeHelper(monkeypatch)
    fake.fail_with = "the broker did not start with the new TLS settings, so the previous ones were put back"
    _app_mqtt(state, host="localhost")
    response = client.put("/api/mqtt-tls/broker/mode", json={"mode": "optional"})
    assert response.status_code == 409
    assert response.json()["detail"].startswith("the broker did not start")


def test_tls_only_is_refused_while_boneio_uses_plain_mqtt_by_its_address(client, state, monkeypatch):
    fake = FakeHelper(monkeypatch)
    import boneio.webui.routes.update as update_route

    monkeypatch.setattr(update_route, "is_local_broker_host", lambda host: True)
    _app_mqtt(state, host="192.168.1.50", port=1883)
    response = client.put("/api/mqtt-tls/broker/mode", json={"mode": "required"})
    assert response.status_code == 409
    assert "localhost" in response.json()["detail"]
    assert fake.calls == []

    # Over loopback it keeps working, and with TLS of its own too.
    _app_mqtt(state, host="localhost", port=1883)
    assert client.put("/api/mqtt-tls/broker/mode", json={"mode": "required"}).status_code == 200
    _app_mqtt(state, host="192.168.1.50", port=8883, tls={"enabled": True})
    assert client.put("/api/mqtt-tls/broker/mode", json={"mode": "required"}).status_code == 200


def test_an_unknown_mode_is_refused_before_the_helper(client, state, monkeypatch):
    fake = FakeHelper(monkeypatch)
    assert client.put("/api/mqtt-tls/broker/mode", json={"mode": "on"}).status_code == 422
    assert fake.calls == []


def test_the_ca_is_offered_only_when_the_chain_has_one(client, monkeypatch):
    monkeypatch.setattr(broker_tls, "installed_ca", lambda: None)
    assert client.get("/api/mqtt-tls/broker/ca").status_code == 404
    monkeypatch.setattr(broker_tls, "installed_ca", lambda: b"-----BEGIN CERTIFICATE-----\n")
    response = client.get("/api/mqtt-tls/broker/ca")
    assert response.status_code == 200
    assert "boneio-mqtt-ca.crt" in response.headers["content-disposition"]


@pytest.mark.parametrize("method,path", [
    ("POST", "/api/mqtt-tls/broker/certificate"),
    ("POST", "/api/mqtt-tls/broker/generate"),
    ("PUT", "/api/mqtt-tls/broker/mode"),
    ("DELETE", "/api/mqtt-tls/broker/certificate"),
])
def test_changing_the_broker_wants_a_fresh_password(method, path):
    assert policy.requires_recent_auth(method, path)


def test_reading_the_ca_does_not(client):
    assert not policy.requires_recent_auth("GET", "/api/mqtt-tls/broker/ca")
