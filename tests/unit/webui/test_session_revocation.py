"""A password change signs every other session out.

Login tokens live for 30 days. Before session versions, changing the password
did nothing to a token already out there — a stolen one kept working until it
expired. These tests pin down that the change now cuts it off everywhere the
token is accepted: the HTTP API, the identity attached on open routes, and the
WebSocket.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from boneio.core.auth.models import Role, User
from boneio.core.auth.store import USERS_FILENAME, UserStore
from boneio.webui.middleware.auth import (
    AuthMiddleware,
    create_token,
    issue_token,
    set_allow_anonymous,
    set_auth_config,
    set_jwt_secret,
    set_user_store,
)
from boneio.webui.routes.accounts import router as accounts_router
from boneio.webui.websocket_manager import WebSocketManager

SECRET = "test-secret-for-session-revocation----"


@pytest.fixture
def store(tmp_path):
    store = UserStore(tmp_path / USERS_FILENAME)
    store.load()
    set_jwt_secret(SECRET)
    set_auth_config({})
    set_allow_anonymous(False)
    set_user_store(store)
    store.add_user("pawel", "haslo-admina", Role.ADMIN)
    store.add_user("gosc", "poufne-haslo", Role.VIEWER)
    yield store
    set_user_store(None)


@pytest.fixture
def client(store):
    app = FastAPI()
    app.include_router(accounts_router)

    # An open route, to see what identity the middleware attaches to it.
    @app.get("/api/version")
    async def version(request: Request):
        return {"user": getattr(request.state, "user", None)}

    app.add_middleware(AuthMiddleware)
    return TestClient(app)


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _token(store: UserStore, username: str) -> str:
    return issue_token(store.get_user(username))


# ------------------------------------------------------------------ the store


def test_a_password_change_bumps_the_session_version(store):
    before = store.get_user("gosc").session_version
    store.set_password("gosc", "zupelnie-nowe")
    assert store.get_user("gosc").session_version == before + 1


def test_the_session_version_survives_a_reload(store, tmp_path):
    store.set_password("gosc", "zupelnie-nowe")
    reloaded = UserStore(tmp_path / USERS_FILENAME)
    reloaded.load()
    assert reloaded.get_user("gosc").session_version == 1


def test_accounts_written_before_versions_read_as_zero():
    user = User.from_dict({"username": "stary", "password_hash": "x", "role": "admin"})
    assert user.session_version == 0


def test_a_garbled_version_reads_as_zero():
    user = User.from_dict(
        {"username": "stary", "password_hash": "x", "role": "admin", "session_version": "abc"}
    )
    assert user.session_version == 0


# ------------------------------------------------------------- the HTTP API


def test_changing_your_password_revokes_your_other_tokens(client, store):
    old = _token(store, "gosc")
    response = client.put(
        "/api/account/password",
        headers=_bearer(old),
        json={"current_password": "poufne-haslo", "new_password": "zupelnie-nowe"},
    )
    assert response.status_code == 200

    refused = client.get("/api/account/me", headers=_bearer(old))
    assert refused.status_code == 401
    assert refused.json()["code"] == "session_revoked"


def test_the_session_that_changed_the_password_carries_on(client, store):
    response = client.put(
        "/api/account/password",
        headers=_bearer(_token(store, "gosc")),
        json={"current_password": "poufne-haslo", "new_password": "zupelnie-nowe"},
    )
    fresh = response.json()["token"]
    assert client.get("/api/account/me", headers=_bearer(fresh)).status_code == 200


def test_an_admin_reset_signs_the_account_out(client, store):
    victim = _token(store, "gosc")
    admin = _token(store, "pawel")
    response = client.put(
        "/api/accounts/gosc/password", headers=_bearer(admin), json={"password": "od-admina"}
    )
    assert response.status_code == 200
    # Somebody else's password: nothing for the admin to adopt.
    assert "token" not in response.json()

    assert client.get("/api/account/me", headers=_bearer(victim)).status_code == 401
    assert client.get("/api/account/me", headers=_bearer(admin)).status_code == 200


def test_an_admin_resetting_their_own_password_gets_a_token_back(client, store):
    old = _token(store, "pawel")
    response = client.put(
        "/api/accounts/pawel/password", headers=_bearer(old), json={"password": "nowe-admina"}
    )
    assert response.status_code == 200
    fresh = response.json()["token"]

    assert client.get("/api/account/me", headers=_bearer(fresh)).status_code == 200
    assert client.get("/api/account/me", headers=_bearer(old)).status_code == 401


def test_a_token_from_before_versions_still_works(client, store):
    """Upgrading must not sign everybody out: no claim means version 0."""
    legacy = create_token({"sub": "gosc", "role": "viewer"})
    assert client.get("/api/account/me", headers=_bearer(legacy)).status_code == 200


def test_a_token_from_before_versions_dies_with_the_first_change(client, store):
    legacy = create_token({"sub": "gosc", "role": "viewer"})
    store.set_password("gosc", "zupelnie-nowe")
    assert client.get("/api/account/me", headers=_bearer(legacy)).status_code == 401


@pytest.mark.parametrize("ver", ["0", 0.0, True, None, [0]])
def test_a_version_claim_that_is_not_a_whole_number_is_refused(client, store, ver):
    token = create_token({"sub": "gosc", "role": "viewer", "ver": ver})
    assert client.get("/api/account/me", headers=_bearer(token)).status_code == 401


def test_a_revoked_token_gets_no_identity_on_open_routes(client, store):
    """/api/version and /api/init tell a known caller more (the serial)."""
    token = _token(store, "gosc")
    assert client.get("/api/version", headers=_bearer(token)).json()["user"] == "gosc"

    store.set_password("gosc", "zupelnie-nowe")
    assert client.get("/api/version", headers=_bearer(token)).json()["user"] is None


# --------------------------------------------------------------- the socket


def _socket_with(token: str):
    return SimpleNamespace(headers={"sec-websocket-protocol": f"token.{token}"})


def test_the_websocket_refuses_a_revoked_token(store):
    manager = WebSocketManager(jwt_secret=SECRET, auth_required=True)
    token = _token(store, "gosc")
    assert asyncio.run(manager._verify_token(_socket_with(token))) is True

    store.set_password("gosc", "zupelnie-nowe")
    assert asyncio.run(manager._verify_token(_socket_with(token))) is False


def test_the_websocket_refuses_a_deleted_account(store):
    manager = WebSocketManager(jwt_secret=SECRET, auth_required=True)
    token = _token(store, "gosc")
    store.delete_user("gosc")
    assert asyncio.run(manager._verify_token(_socket_with(token))) is False


def test_users_json_records_the_version(store, tmp_path):
    store.set_password("gosc", "zupelnie-nowe")
    raw = json.loads((tmp_path / USERS_FILENAME).read_text())
    by_name = {u["username"]: u for u in raw["users"]}
    assert by_name["gosc"]["session_version"] == 1
