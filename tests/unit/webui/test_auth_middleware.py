"""Tests for the request gate in AuthMiddleware."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from boneio.core.auth.models import Role
from boneio.core.auth.store import USERS_FILENAME, UserStore
from boneio.webui.middleware.auth import (
    AuthMiddleware,
    create_token,
    set_auth_config,
    set_jwt_secret,
    set_user_store,
)
from boneio.webui.routes.onboarding import router as onboarding_router
from boneio.webui.routes import onboarding as onboarding_module


@pytest.fixture
def store(tmp_path):
    store = UserStore(tmp_path / USERS_FILENAME)
    store.load()
    set_jwt_secret("test-secret-for-middleware-tests")
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

    @app.get("/api/protected")
    async def protected():
        return {"ok": True}

    # Installed unconditionally, exactly as init_app does it.
    app.add_middleware(AuthMiddleware)
    return TestClient(app)


def test_device_without_accounts_stays_open(client):
    """Pre-1.6 behaviour for a device that never had credentials (F-02)."""
    assert client.get("/api/protected").status_code == 200


def test_provisioning_closes_the_api_without_a_restart(client, store):
    """The hole this guards: the wizard writes users.json, and config.yaml
    stays empty, so a gate on web.auth would leave the API open until reboot."""
    assert client.get("/api/protected").status_code == 200

    client.post(
        "/api/onboarding/admin",
        json={"username": "pawel", "password": "dobre-haslo"},
    )

    assert client.get("/api/protected").status_code == 401


def test_a_token_from_the_wizard_opens_the_api(client):
    token = client.post(
        "/api/onboarding/admin",
        json={"username": "pawel", "password": "dobre-haslo"},
    ).json()["token"]

    response = client.get(
        "/api/protected", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200


def test_onboarding_status_stays_reachable_when_locked(client, store):
    """The frontend has to ask before it can know whether to show a login."""
    store.add_user("pawel", "dobre-haslo", Role.ADMIN)
    assert client.get("/api/onboarding/status").status_code == 200


def test_first_admin_endpoint_is_open_but_self_guarding(client, store):
    """It bypasses the middleware, so its own 409 is the only thing stopping
    an unauthenticated takeover."""
    store.add_user("pawel", "dobre-haslo", Role.ADMIN)

    response = client.post(
        "/api/onboarding/admin",
        json={"username": "napastnik", "password": "haslo-napastnika"},
    )

    assert response.status_code == 409
    assert store.get_user("napastnik") is None


@pytest.mark.parametrize(
    "header",
    ["", "Bearer", "Basic abc", "Bearer not-a-jwt", "Token abc def"],
)
def test_malformed_authorization_headers_are_rejected(client, store, header):
    store.add_user("pawel", "dobre-haslo", Role.ADMIN)
    response = client.get("/api/protected", headers={"Authorization": header})
    assert response.status_code == 401


def test_expired_or_foreign_token_is_rejected(client, store):
    store.add_user("pawel", "dobre-haslo", Role.ADMIN)
    token = create_token({"sub": "pawel", "role": "admin"})

    set_jwt_secret("a-completely-different-secret")
    try:
        response = client.get(
            "/api/protected", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 401
    finally:
        set_jwt_secret("test-secret-for-middleware-tests")


def test_legacy_web_auth_alone_still_closes_the_api(client):
    """A 1.5.x device whose credentials could not be migrated stays protected."""
    set_auth_config({"username": "pa/wel", "password": "stare-haslo"})
    assert client.get("/api/protected").status_code == 401
