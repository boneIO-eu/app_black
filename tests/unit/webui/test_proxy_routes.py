"""The Caddy switch endpoints: who may ask, and what the helper is asked."""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from boneio.core import containers
from boneio.core.auth.models import Role
from boneio.core.auth.store import USERS_FILENAME, UserStore
from boneio.core.containers import Result
from boneio.webui.middleware.auth import (
    REAUTH_WINDOW,
    AuthMiddleware,
    create_token,
    issue_token,
    set_auth_config,
    set_jwt_secret,
    set_user_store,
)
from boneio.webui.routes import proxy

SECRET = "test-secret-for-proxy-tests-----------"


@pytest.fixture
def store(tmp_path):
    set_jwt_secret(SECRET)
    set_auth_config({})
    users = UserStore(tmp_path / USERS_FILENAME)
    users.load()
    users.add_user("pawel", "haslo-admina", Role.ADMIN)
    users.add_user("gosc", "poufne-haslo", Role.VIEWER)
    set_user_store(users)
    yield users
    set_user_store(None)


@pytest.fixture
def client(store, monkeypatch):
    monkeypatch.setattr(containers, "helper_supports", lambda verb: True)
    app = FastAPI()
    app.include_router(proxy.router)
    app.add_middleware(AuthMiddleware)
    return TestClient(app)


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _stale():
    old = int(time.time() - REAUTH_WINDOW.total_seconds() - 60)
    return create_token({"sub": "pawel", "role": "admin", "auth_time": old})


def test_a_viewer_may_neither_read_nor_start(client):
    token = create_token({"sub": "gosc", "role": "viewer", "auth_time": int(time.time())})
    assert client.get("/api/proxy/state", headers=_bearer(token)).status_code == 403
    assert client.post("/api/proxy/switch", headers=_bearer(token)).status_code == 403


def test_an_admin_without_a_fresh_password_is_asked_for_it(client, monkeypatch):
    started = []
    monkeypatch.setattr(containers, "proxy_switch_start", lambda timeout=60: started.append(1))
    response = client.post("/api/proxy/switch", headers=_bearer(_stale()))
    assert response.status_code == 403
    assert response.json()["code"] == "reauth_required"
    assert started == []


def test_a_fresh_admin_starts_the_switch(client, store, monkeypatch):
    monkeypatch.setattr(
        containers, "proxy_switch_start", lambda timeout=60: Result(0, '{"started": true}', "", True)
    )
    token = issue_token(store.get_user("pawel"))
    assert client.post("/api/proxy/switch", headers=_bearer(token)).json() == {"status": "started"}


def test_a_refusal_from_the_helper_is_a_conflict(client, store, monkeypatch):
    monkeypatch.setattr(
        containers, "proxy_switch_start",
        lambda timeout=60: Result(1, "", "[ERROR] REFUSED: already running", True),
    )
    token = issue_token(store.get_user("pawel"))
    assert client.post("/api/proxy/switch", headers=_bearer(token)).status_code == 409


def test_the_state_carries_mode_version_and_switch(client, store, monkeypatch):
    monkeypatch.setattr(containers, "proxy_mode", lambda: "native")
    monkeypatch.setattr(
        containers, "caddy_image_state",
        lambda timeout=30: Result(0, json.dumps({"mode": "native", "installed": "2.10.2", "candidate": "2.11.0"}), "", True),
    )
    monkeypatch.setattr(
        containers, "proxy_switch_state",
        lambda timeout=30: Result(0, json.dumps({"state": "done", "log": "ok"}), "", True),
    )
    token = issue_token(store.get_user("pawel"))
    body = client.get("/api/proxy/state", headers=_bearer(token)).json()
    assert body["mode"] == "native"
    assert body["installed"] == "2.10.2"
    assert body["switch"]["state"] == "done"
