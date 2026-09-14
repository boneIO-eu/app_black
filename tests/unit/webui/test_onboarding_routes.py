"""Tests for the first-run wizard endpoints and store-backed login."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from boneio.core.auth.models import Role
from boneio.core.auth.store import USERS_FILENAME, UserStore
from boneio.webui.middleware.auth import (
    set_auth_config,
    set_jwt_secret,
    set_user_store,
    verify_token,
)
from boneio.webui.routes import onboarding as onboarding_module
from boneio.webui.routes.auth import router as auth_router
from boneio.webui.routes.onboarding import router as onboarding_router


@pytest.fixture
def store(tmp_path):
    """A store wired into both the routes and the auth middleware."""
    store = UserStore(tmp_path / USERS_FILENAME)
    store.load()
    set_jwt_secret("test-secret-for-onboarding-tests")
    set_auth_config({})
    set_user_store(store)
    onboarding_module.set_user_store(store)
    onboarding_module.set_legacy_migration(None)
    yield store
    set_user_store(None)
    onboarding_module.set_user_store(None)
    set_auth_config({})


@pytest.fixture
def client(store):
    app = FastAPI()
    app.include_router(onboarding_router)
    app.include_router(auth_router)
    return TestClient(app)


# --------------------------------------------------------------------- status


def test_status_reports_a_fresh_device(client):
    body = client.get("/api/onboarding/status").json()
    assert body["provisioned"] is False
    assert body["needs_onboarding"] is True
    assert body["legacy_migration"] is None


def test_status_reports_a_provisioned_device(client, store):
    store.add_user("pawel", "dobre-haslo", Role.ADMIN)
    body = client.get("/api/onboarding/status").json()
    assert body["provisioned"] is True
    assert body["needs_onboarding"] is False


def test_status_surfaces_a_legacy_migration(client):
    onboarding_module.set_legacy_migration(
        {"username": "pawel", "used_secret_file": True}
    )
    body = client.get("/api/onboarding/status").json()
    assert body["legacy_migration"]["username"] == "pawel"
    assert body["legacy_migration"]["used_secret_file"] is True


def test_status_never_leaks_accounts(client, store):
    store.add_user("pawel", "dobre-haslo", Role.ADMIN)
    text = client.get("/api/onboarding/status").text
    assert "pawel" not in text
    assert "password" not in text.lower()


# -------------------------------------------------------------- first admin


def test_creates_the_first_admin(client, store):
    response = client.post(
        "/api/onboarding/admin",
        json={"username": "pawel", "password": "dobre-haslo"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["user"]["username"] == "pawel"
    assert body["user"]["role"] == "admin"
    assert "password_hash" not in body["user"]

    assert store.is_provisioned() is True
    assert store.verify_credentials("pawel", "dobre-haslo") is not None


def test_returned_token_carries_the_admin_role(client):
    token = client.post(
        "/api/onboarding/admin",
        json={"username": "pawel", "password": "dobre-haslo"},
    ).json()["token"]

    payload = verify_token(token)
    assert payload is not None
    assert payload["sub"] == "pawel"
    assert payload["role"] == "admin"


def test_second_admin_creation_is_refused_forever(client, store):
    client.post(
        "/api/onboarding/admin",
        json={"username": "pawel", "password": "dobre-haslo"},
    )

    response = client.post(
        "/api/onboarding/admin",
        json={"username": "napastnik", "password": "przejete-haslo"},
    )

    assert response.status_code == 409
    assert store.get_user("napastnik") is None
    assert store.verify_credentials("pawel", "dobre-haslo") is not None


def test_existing_admin_cannot_be_overwritten_by_the_wizard(client, store):
    """The takeover in F-14 relied on setting credentials without a token."""
    store.add_user("pawel", "dobre-haslo", Role.ADMIN)

    response = client.post(
        "/api/onboarding/admin",
        json={"username": "pawel", "password": "haslo-napastnika"},
    )

    assert response.status_code == 409
    assert store.verify_credentials("pawel", "dobre-haslo") is not None
    assert store.verify_credentials("pawel", "haslo-napastnika") is None


def test_a_viewer_only_device_can_still_be_provisioned(client, store):
    """A viewer is not an owner, so the wizard must still be reachable."""
    store.add_user("gosc", "dobre-haslo", Role.VIEWER)

    response = client.post(
        "/api/onboarding/admin",
        json={"username": "pawel", "password": "dobre-haslo"},
    )

    assert response.status_code == 201
    assert store.is_provisioned() is True


@pytest.mark.parametrize(
    "payload",
    [
        {"username": "pawel", "password": "krotkie"},
        {"username": "", "password": "dobre-haslo"},
        {"username": "pawel"},
        {"password": "dobre-haslo"},
        {},
    ],
)
def test_invalid_payloads_are_rejected(client, store, payload):
    response = client.post("/api/onboarding/admin", json=payload)
    assert response.status_code in (400, 422)
    assert store.is_provisioned() is False


def test_unusable_username_is_rejected(client, store):
    response = client.post(
        "/api/onboarding/admin",
        json={"username": "pa/wel", "password": "dobre-haslo"},
    )
    assert response.status_code == 400
    assert store.is_provisioned() is False


# --------------------------------------------------------------------- login


def test_login_uses_the_account_store(client, store):
    store.add_user("pawel", "dobre-haslo", Role.ADMIN)

    body = client.post(
        "/api/login", json={"username": "pawel", "password": "dobre-haslo"}
    ).json()

    assert body["role"] == "admin"
    assert body["username"] == "pawel"
    assert verify_token(body["token"])["role"] == "admin"


def test_login_rejects_a_wrong_password_on_a_provisioned_device(client, store):
    """Pre-1.6 this route handed out a token for anything (F-08)."""
    store.add_user("pawel", "dobre-haslo", Role.ADMIN)

    assert (
        client.post(
            "/api/login", json={"username": "pawel", "password": "zgadywane"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/login", json={"username": "kto-inny", "password": "cokolwiek"}
        ).status_code
        == 401
    )


def test_login_reports_the_viewer_role(client, store):
    store.add_user("pawel", "dobre-haslo", Role.ADMIN)
    store.add_user("gosc", "haslo-goscia", Role.VIEWER)

    body = client.post(
        "/api/login", json={"username": "gosc", "password": "haslo-goscia"}
    ).json()

    assert body["role"] == "viewer"
    assert verify_token(body["token"])["role"] == "viewer"


def test_login_is_case_insensitive_on_the_username(client, store):
    store.add_user("Pawel", "dobre-haslo", Role.ADMIN)

    assert (
        client.post(
            "/api/login", json={"username": "PAWEL", "password": "dobre-haslo"}
        ).status_code
        == 200
    )


def test_legacy_web_auth_still_works_when_it_could_not_be_migrated(client, store):
    """A username the new store cannot hold must not lock the owner out."""
    set_auth_config({"username": "pa/wel", "password": "stare-haslo"})

    assert (
        client.post(
            "/api/login", json={"username": "pa/wel", "password": "stare-haslo"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/login", json={"username": "pa/wel", "password": "zle"}
        ).status_code
        == 401
    )


def test_auth_required_follows_provisioning(client, store):
    assert client.get("/api/auth/required").json()["required"] is False
    store.add_user("pawel", "dobre-haslo", Role.ADMIN)
    assert client.get("/api/auth/required").json()["required"] is True
