"""API keys: what an agent or a script gets instead of a login.

A key acts within its scope only, stops working the moment it expires, is
revoked or its owner is no longer an administrator, and never sees what an
agent should not pass on to its model's vendor.
"""

from __future__ import annotations

import os
import re
import stat
import threading
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from boneio.core.auth import api_keys as api_keys_module
from boneio.core.auth.api_keys import KEY_PREFIX, ApiKeyError, ApiKeyStore, KeyScope
from boneio.core.auth.models import Role
from boneio.core.auth.store import USERS_FILENAME, UserStore
from boneio.webui.middleware import policy
from boneio.webui.middleware.auth import (
    AuthMiddleware,
    set_allow_anonymous,
    set_auth_config,
    set_jwt_secret,
    set_key_store,
    set_user_store,
)

from .route_paths import all_routes

SECRET = "test-secret-for-api-key-tests-32-bytes-long"


@pytest.fixture
def users(tmp_path):
    store = UserStore(tmp_path / USERS_FILENAME)
    store.load()
    store.add_user("pawel", "dobre-haslo", Role.ADMIN)
    store.add_user("gosc", "dobre-haslo", Role.VIEWER)
    return store


@pytest.fixture
def keys(users):
    return ApiKeyStore.beside(users)


# ------------------------------------------------------------------- store


class TestStore:
    def test_a_key_is_shown_once_and_only_its_digest_is_stored(self, keys):
        key, secret = keys.create("Claude", "pawel", KeyScope.READ, 30)
        assert secret.startswith(KEY_PREFIX) and len(secret) > 40
        text = keys._path.read_text(encoding="utf-8")
        assert secret not in text and key.digest in text
        assert "digest" not in key.public()
        assert stat.S_IMODE(os.stat(keys._path).st_mode) == 0o600

    def test_the_secret_authenticates_and_nothing_else_does(self, keys):
        key, secret = keys.create("Claude", "pawel", KeyScope.WRITE, 7)
        assert keys.authenticate(secret).id == key.id
        assert keys.authenticate(secret[:-1] + ("A" if secret[-1] != "A" else "B")) is None
        assert keys.authenticate("not-a-key") is None

    def test_an_expired_key_is_refused(self, keys, monkeypatch):
        _, secret = keys.create("Claude", "pawel", KeyScope.READ, 7)
        later = api_keys_module._now() + timedelta(days=8)
        monkeypatch.setattr(api_keys_module, "_now", lambda: later)
        assert keys.authenticate(secret) is None

    def test_a_revoked_key_is_refused_at_once(self, keys):
        key, secret = keys.create("Claude", "pawel", KeyScope.READ, 30)
        keys.revoke(key.id)
        assert keys.authenticate(secret) is None

    def test_a_key_stops_when_its_owner_is_no_longer_an_admin(self, keys, users):
        _, secret = keys.create("Claude", "pawel", KeyScope.READ, 30)
        users.add_user("druga", "dobre-haslo", Role.ADMIN)
        users.set_role("pawel", Role.VIEWER)
        assert keys.authenticate(secret) is None

    def test_a_key_made_elsewhere_is_seen_without_a_restart(self, keys, users):
        _, secret = ApiKeyStore.beside(users).create("CLI", "pawel", KeyScope.READ, 30)
        assert keys.authenticate(secret) is not None

    @pytest.mark.parametrize(
        ("name", "owner", "days"),
        [("", "pawel", 30), ("x" * 65, "pawel", 30), ("ok", "pawel", 10), ("ok", "gosc", 30),
         ("ok", "nobody", 30)],
    )
    def test_what_cannot_be_made(self, keys, name, owner, days):
        with pytest.raises(ApiKeyError):
            keys.create(name, owner, KeyScope.READ, days)

    def test_last_use_is_written_at_most_hourly(self, keys, monkeypatch):
        _, secret = keys.create("Claude", "pawel", KeyScope.READ, 30)
        saves = []
        monkeypatch.setattr(keys, "_save", lambda: saves.append(1))
        for _ in range(5):
            assert keys.authenticate(secret) is not None
        for thread in [t for t in threading.enumerate() if t.name == "api-key-last-used"]:
            thread.join()
        assert len(saves) == 1


# ------------------------------------------------------------------ policy


@pytest.mark.parametrize(
    ("scope", "method", "path", "allowed"),
    [
        (KeyScope.READ, "GET", "/api/config", True),
        (KeyScope.READ, "POST", "/api/config/event/validate", False),
        (KeyScope.READ, "PUT", "/api/config/event", False),
        (KeyScope.PROPOSE, "POST", "/api/config/event/validate", True),
        (KeyScope.PROPOSE, "PUT", "/api/config/event", False),
        (KeyScope.WRITE, "PUT", "/api/config/event", True),
        (KeyScope.WRITE, "POST", "/api/config/reload", True),
        # Restart-only and secret-holding sections are the owner's to change.
        (KeyScope.WRITE, "PUT", "/api/config/web", False),
        (KeyScope.WRITE, "PUT", "/api/config/mqtt", False),
        (KeyScope.WRITE, "PUT", "/api/config/remote_devices", False),
        (KeyScope.WRITE, "PUT", "/api/config/template", False),
        (KeyScope.WRITE, "PUT", "/api/config/boneio", False),
        (KeyScope.WRITE, "POST", "/api/config/web/validate", True),
        # Nothing outside the scopes, whatever the owner may do.
        (KeyScope.WRITE, "GET", "/api/accounts", False),
        (KeyScope.WRITE, "GET", "/api/config/download", False),
        (KeyScope.WRITE, "POST", "/api/api-keys", False),
        (KeyScope.WRITE, "PUT", "/api/config/quick-action", False),
        (KeyScope.WRITE, "POST", "/api/outputs/out_01/toggle", False),
    ],
)
def test_a_scope_reaches_its_routes_and_no_others(scope, method, path, allowed):
    assert policy.key_allows(scope, method, path) is allowed


@pytest.fixture
def app_routes(tmp_path):
    from boneio.webui.app import init_app

    config = tmp_path / "config.yaml"
    config.write_text("web:\n  port: 8090\n", encoding="utf-8")
    app = init_app(manager=MagicMock(), yaml_config_file=str(config), config_helper=MagicMock(),
                   auth_config={}, jwt_secret=SECRET)
    yield [(m, re.sub(r"\{[^}]+\}", "x", p)) for m, p in all_routes(app)]
    set_user_store(None)
    set_key_store(None)
    set_auth_config({})
    set_allow_anonymous(False)


def test_every_key_route_exists_and_none_asks_for_a_password(app_routes):
    """A typo would guard nothing; a key has no password to confirm."""
    for scope, routes in policy._KEY_ROUTES.items():
        for method, pattern in routes:
            served = [p for m, p in app_routes if m == method and pattern.match(p)]
            assert served, f"{scope}: {method} {pattern.pattern} matches no route"
            for path in served:
                assert not policy.requires_recent_auth(method, path), (method, path)


# -------------------------------------------------------------- middleware


@pytest.fixture
def client(users, keys):
    set_jwt_secret(SECRET)
    set_auth_config({})
    set_allow_anonymous(False)
    set_user_store(users)
    set_key_store(keys)
    app = FastAPI()

    @app.get("/api/config")
    async def read(request: Request):
        return {"user": request.state.user, "role": str(request.state.role)}

    @app.put("/api/config/{section}")
    async def write(section: str):
        return {"saved": section}

    @app.get("/api/accounts")
    async def accounts():
        return {"accounts": []}

    app.add_middleware(AuthMiddleware)
    yield TestClient(app)
    set_user_store(None)
    set_key_store(None)


def _bearer(secret):
    return {"Authorization": f"Bearer {secret}"}


def test_a_key_reads_as_itself_and_never_as_an_admin(client, keys):
    _, secret = keys.create("Claude", "pawel", KeyScope.READ, 30)
    response = client.get("/api/config", headers=_bearer(secret))
    assert response.status_code == 200
    assert response.json() == {"user": "key:Claude (pawel)", "role": "viewer"}


def test_a_key_does_not_wait_for_the_thread_pool(client, keys, monkeypatch):
    """On one core the default executor can be busy with sudo helpers for tens of seconds."""
    import asyncio

    def busy(*args, **kwargs):
        raise AssertionError("authenticating a key must not need the default executor")

    monkeypatch.setattr(asyncio, "to_thread", busy)
    _, secret = keys.create("Claude", "pawel", KeyScope.READ, 30)
    assert client.get("/api/config", headers=_bearer(secret)).status_code == 200


def test_a_key_is_refused_outside_its_scope(client, keys):
    _, secret = keys.create("Claude", "pawel", KeyScope.READ, 30)
    assert client.put("/api/config/event", headers=_bearer(secret), json=[]).status_code == 403
    assert client.get("/api/accounts", headers=_bearer(secret)).status_code == 403


def test_a_write_key_saves_but_not_a_section_holding_a_secret(client, keys):
    _, secret = keys.create("Agent", "pawel", KeyScope.WRITE, 30)
    assert client.put("/api/config/event", headers=_bearer(secret), json=[]).status_code == 200
    assert client.put("/api/config/remote_devices", headers=_bearer(secret), json=[]).status_code == 403


def test_a_revoked_or_unknown_key_is_401(client, keys):
    key, secret = keys.create("Claude", "pawel", KeyScope.READ, 30)
    keys.revoke(key.id)
    assert client.get("/api/config", headers=_bearer(secret)).status_code == 401
    assert client.get("/api/config", headers=_bearer(KEY_PREFIX + "x" * 43)).status_code == 401


def test_a_key_in_the_query_string_is_refused(client, keys):
    _, secret = keys.create("Claude", "pawel", KeyScope.READ, 30)
    assert client.get(f"/api/config?token={secret}").status_code == 401


# ----------------------------------------------------------------- masking


@pytest.mark.asyncio
async def test_a_key_does_not_see_encryption_keys_or_alarm_codes(tmp_path):
    from boneio.core.config.secret_masking import MASK
    from boneio.webui.routes import config_core

    config_core._config_cache["data"] = {
        "remote_devices": [{"id": "esp", "name": "E", "protocol": "esphome_api",
                            "esphome_api": {"host": "h", "password": "p", "encryption_key": "psk="}}],
        "template": [{"platform": "alarm_control_panel", "codes": [{"name": "Me", "code": "1234"}]}],
    }
    config_core._config_cache["mtime"] = float("inf")
    (tmp_path / "config.yaml").write_text("{}\n", encoding="utf-8")
    state = MagicMock()
    state.yaml_config_file = str(tmp_path / "config.yaml")
    config_core.set_app_state(state)
    try:
        person = (await config_core.get_parsed_config(SimpleNamespace(state=SimpleNamespace())))["config"]
        agent = (await config_core.get_parsed_config(
            SimpleNamespace(state=SimpleNamespace(api_key=object()))))["config"]
    finally:
        config_core._config_cache["data"] = None
        config_core._config_cache["mtime"] = 0
    assert agent["remote_devices"][0]["esphome_api"] == {"host": "h", "password": MASK, "encryption_key": MASK}
    assert agent["template"][0]["codes"] == [{"name": "Me", "code": MASK}]
    # What the panel shows people is unchanged here.
    assert person["remote_devices"][0]["esphome_api"]["encryption_key"] == "psk="


# ------------------------------------------------------------------ routes


@pytest.fixture
def panel(users, keys, monkeypatch):
    from boneio.webui import security_events
    from boneio.webui.middleware.auth import issue_token
    from boneio.webui.routes.api_keys import router

    set_jwt_secret(SECRET)
    set_auth_config({})
    set_allow_anonymous(False)
    set_user_store(users)
    set_key_store(keys)
    events = []
    monkeypatch.setattr(security_events, "emit", lambda kind, **kw: events.append((kind, kw)))
    app = FastAPI()
    app.include_router(router)
    app.add_middleware(AuthMiddleware)
    client = TestClient(app)
    client.events = events
    client.admin = {"Authorization": f"Bearer {issue_token(users.get_user('pawel'))}"}
    client.viewer = {"Authorization": f"Bearer {issue_token(users.get_user('gosc'))}"}
    yield client
    set_user_store(None)
    set_key_store(None)


def test_an_admin_makes_lists_and_revokes_a_key(panel, keys):
    made = panel.post("/api/api-keys", headers=panel.admin,
                      json={"name": "Claude", "scope": "write", "days": 90})
    assert made.status_code == 200
    secret, key = made.json()["secret"], made.json()["key"]
    assert key["owner"] == "pawel" and key["scope"] == "write" and "digest" not in key
    assert keys.authenticate(secret) is not None
    assert panel.events and panel.events[0][0] == "api_key_created"

    listed = panel.get("/api/api-keys", headers=panel.admin).json()["keys"]
    assert [k["id"] for k in listed] == [key["id"]]
    assert secret not in str(listed)

    assert panel.delete(f"/api/api-keys/{key['id']}", headers=panel.admin).status_code == 200
    assert keys.authenticate(secret) is None


def test_a_viewer_cannot_see_or_make_keys(panel):
    assert panel.get("/api/api-keys", headers=panel.viewer).status_code == 403
    assert panel.post("/api/api-keys", headers=panel.viewer,
                      json={"name": "x", "scope": "read"}).status_code == 403


def test_a_key_cannot_make_another_key(panel, keys):
    _, secret = keys.create("Agent", "pawel", KeyScope.WRITE, 30)
    response = panel.post("/api/api-keys", headers=_bearer(secret), json={"name": "x", "scope": "write"})
    assert response.status_code == 403


def test_a_lifetime_not_offered_is_refused(panel):
    response = panel.post("/api/api-keys", headers=panel.admin,
                          json={"name": "x", "scope": "read", "days": 10000})
    assert response.status_code == 422
