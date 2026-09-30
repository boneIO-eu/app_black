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
