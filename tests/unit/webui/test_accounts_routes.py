"""Tests for account management and self-service password change."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from boneio.core.auth.models import Role
from boneio.core.auth.store import USERS_FILENAME, UserStore
from boneio.webui.middleware.auth import (
    AuthMiddleware,
    create_token,
    set_allow_anonymous,
    set_auth_config,
    set_jwt_secret,
    set_user_store,
)
from boneio.webui.routes.accounts import router as accounts_router


@pytest.fixture
def store(tmp_path):
    store = UserStore(tmp_path / USERS_FILENAME)
    store.load()
    set_jwt_secret("test-secret-for-account-tests")
    set_auth_config({})
    set_allow_anonymous(False)
    set_user_store(store)
    store.add_user("pawel", "haslo-admina", Role.ADMIN)
    store.add_user("gosc", "haslo-goscia", Role.VIEWER)
    yield store
    set_user_store(None)


@pytest.fixture
def client(store):
    app = FastAPI()
    app.include_router(accounts_router)
    app.add_middleware(AuthMiddleware)
    return TestClient(app)


def _as(user: str, role: str) -> dict:
    return {"Authorization": f"Bearer {create_token({'sub': user, 'role': role})}"}


ADMIN = ("pawel", "admin")
VIEWER = ("gosc", "viewer")


# ------------------------------------------------------------------ listing


def test_admin_lists_accounts_without_hashes(client):
    body = client.get("/api/accounts", headers=_as(*ADMIN)).json()
    names = {a["username"] for a in body["accounts"]}
    assert names == {"pawel", "gosc"}
    assert all("password_hash" not in a for a in body["accounts"])


def test_viewer_may_not_list_accounts(client):
    assert client.get("/api/accounts", headers=_as(*VIEWER)).status_code == 403


# ----------------------------------------------------------------- creating


def test_admin_creates_a_viewer(client, store):
    response = client.post(
        "/api/accounts",
        headers=_as(*ADMIN),
        json={"username": "nowy", "password": "dobre-haslo", "role": "viewer"},
    )
    assert response.status_code == 201
    assert response.json()["account"]["role"] == "viewer"
    assert store.verify_credentials("nowy", "dobre-haslo") is not None


def test_role_defaults_to_viewer(client):
    """The safer role is the default, so a slip grants less, not more."""
    body = client.post(
        "/api/accounts",
        headers=_as(*ADMIN),
        json={"username": "nowy", "password": "dobre-haslo"},
    ).json()
    assert body["account"]["role"] == "viewer"


def test_viewer_may_not_create_accounts(client, store):
    response = client.post(
        "/api/accounts",
        headers=_as(*VIEWER),
        json={"username": "wlasny_admin", "password": "dobre-haslo", "role": "admin"},
    )
    assert response.status_code == 403
    assert store.get_user("wlasny_admin") is None


@pytest.mark.parametrize(
    "payload",
    [
        {"username": "x", "password": "krotkie"},
        {"username": "", "password": "dobre-haslo"},
        {"username": "zly/znak", "password": "dobre-haslo"},
        {"username": "nowy", "password": "dobre-haslo", "role": "superadmin"},
    ],
)
def test_invalid_account_payloads_are_rejected(client, payload):
    assert client.post(
        "/api/accounts", headers=_as(*ADMIN), json=payload
    ).status_code in (400, 422)


def test_duplicate_account_is_rejected(client):
    assert client.post(
        "/api/accounts",
        headers=_as(*ADMIN),
        json={"username": "gosc", "password": "dobre-haslo"},
    ).status_code == 400


# ----------------------------------------------------------------- deleting


def test_admin_deletes_a_viewer(client, store):
    assert client.delete("/api/accounts/gosc", headers=_as(*ADMIN)).status_code == 200
    assert store.get_user("gosc") is None


def test_cannot_delete_your_own_account(client, store):
    """Not dangerous, but it kills your own session mid-request."""
    store.add_user("druga", "haslo-admina", Role.ADMIN)
    response = client.delete("/api/accounts/pawel", headers=_as(*ADMIN))
    assert response.status_code == 409
    assert store.get_user("pawel") is not None


def test_the_last_admin_cannot_be_removed_through_the_api(client, store):
    store.add_user("inny", "haslo-admina", Role.ADMIN)

    # 'inny' removes 'pawel', leaving itself the only admin...
    assert client.delete(
        "/api/accounts/pawel", headers=_as("inny", "admin")
    ).status_code == 200

    # ...and now nothing can remove it: it is both the caller and the last
    # admin, so the self-deletion guard answers first and the store's
    # last-admin guard stands behind it (see test_auth_store.py).
    assert client.delete(
        "/api/accounts/inny", headers=_as("inny", "admin")
    ).status_code == 409
    assert store.is_provisioned() is True


def test_a_deleted_accounts_token_stops_working(client, store):
    """Tokens outlive accounts by weeks, so deletion has to reach open
    sessions — this used to keep working until the token expired."""
    store.add_user("inny", "haslo-admina", Role.ADMIN)
    gone = _as("pawel", "admin")

    assert client.delete("/api/accounts/pawel", headers=_as("inny", "admin")).status_code == 200

    response = client.get("/api/accounts", headers=gone)
    assert response.status_code == 401
    assert response.json()["code"] == "account_gone"


def test_viewer_may_not_delete_accounts(client, store):
    assert client.delete("/api/accounts/pawel", headers=_as(*VIEWER)).status_code == 403
    assert store.get_user("pawel") is not None


# --------------------------------------------------------------------- roles


def test_admin_promotes_a_viewer(client, store):
    response = client.put(
        "/api/accounts/gosc/role", headers=_as(*ADMIN), json={"role": "admin"}
    )
    assert response.status_code == 200
    assert store.get_user("gosc").role is Role.ADMIN


def test_cannot_demote_yourself(client, store):
    store.add_user("druga", "haslo-admina", Role.ADMIN)
    response = client.put(
        "/api/accounts/pawel/role", headers=_as(*ADMIN), json={"role": "viewer"}
    )
    assert response.status_code == 409
    assert store.get_user("pawel").role is Role.ADMIN


def test_viewer_may_not_promote_itself(client, store):
    assert client.put(
        "/api/accounts/gosc/role", headers=_as(*VIEWER), json={"role": "admin"}
    ).status_code == 403
    assert store.get_user("gosc").role is Role.VIEWER


# ----------------------------------------------------------------- passwords


def test_admin_resets_another_password(client, store):
    response = client.put(
        "/api/accounts/gosc/password",
        headers=_as(*ADMIN),
        json={"password": "zupelnie-nowe"},
    )
    assert response.status_code == 200
    assert store.verify_credentials("gosc", "zupelnie-nowe") is not None


def test_viewer_may_not_reset_another_password(client, store):
    assert client.put(
        "/api/accounts/pawel/password",
        headers=_as(*VIEWER),
        json={"password": "przejete-haslo"},
    ).status_code == 403
    assert store.verify_credentials("pawel", "haslo-admina") is not None


def test_viewer_may_change_their_own_password(client, store):
    """A read-only account whose password cannot be rotated never gets rotated."""
    response = client.put(
        "/api/account/password",
        headers=_as(*VIEWER),
        json={"current_password": "haslo-goscia", "new_password": "nowe-haslo-123"},
    )
    assert response.status_code == 200
    assert store.verify_credentials("gosc", "nowe-haslo-123") is not None


def test_own_password_change_needs_the_current_one(client, store):
    """A borrowed session must not be able to take the account over."""
    response = client.put(
        "/api/account/password",
        headers=_as(*VIEWER),
        json={"current_password": "zgadywane", "new_password": "nowe-haslo-123"},
    )
    assert response.status_code == 401
    assert store.verify_credentials("gosc", "haslo-goscia") is not None


def test_own_password_change_enforces_the_policy(client):
    assert client.put(
        "/api/account/password",
        headers=_as(*VIEWER),
        json={"current_password": "haslo-goscia", "new_password": "krotkie"},
    ).status_code == 422


def test_self_service_route_cannot_touch_other_accounts(client, store):
    """The singular route only ever acts on the caller, whoever they name."""
    client.put(
        "/api/account/password",
        headers=_as(*VIEWER),
        json={"current_password": "haslo-goscia", "new_password": "nowe-haslo-123"},
    )
    assert store.verify_credentials("pawel", "haslo-admina") is not None


# ----------------------------------------------------------------- whoami


def test_whoami_reports_the_caller(client):
    body = client.get("/api/account/me", headers=_as(*ADMIN)).json()
    assert body == {"username": "pawel", "role": "admin", "anonymous": False}


def test_whoami_is_available_to_a_viewer(client):
    """The UI needs it to decide what to render, so every role must reach it."""
    body = client.get("/api/account/me", headers=_as(*VIEWER)).json()
    assert body["role"] == "viewer"
    assert body["username"] == "gosc"


def test_whoami_needs_a_token(client):
    assert client.get("/api/account/me").status_code == 401


def test_allow_anonymous_does_nothing_once_accounts_exist(client):
    """A stray allow_anonymous copied into the config of a device that has real
    users must not silently unlock it. The opt-out only covers a device that was
    never set up."""
    set_allow_anonymous(True)
    try:
        assert client.get("/api/account/me").status_code == 401
        assert client.get("/api/accounts").status_code == 401
    finally:
        set_allow_anonymous(False)


def test_whoami_reports_anonymous_on_an_unprovisioned_device(tmp_path):
    """With no accounts and the opt-out on, there is no identity behind a call."""
    empty = UserStore(tmp_path / "empty" / USERS_FILENAME)
    empty.path.parent.mkdir(parents=True, exist_ok=True)
    empty.load()
    set_jwt_secret("test-secret-for-account-tests")
    set_auth_config({})
    set_user_store(empty)
    set_allow_anonymous(True)
    try:
        app = FastAPI()
        app.include_router(accounts_router)
        app.add_middleware(AuthMiddleware)
        body = TestClient(app).get("/api/account/me").json()
        assert body["anonymous"] is True
        assert body["role"] is None
    finally:
        set_allow_anonymous(False)
        set_user_store(None)
