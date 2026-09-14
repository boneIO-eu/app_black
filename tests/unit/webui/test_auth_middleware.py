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
    set_allow_anonymous,
    set_auth_config,
    set_jwt_secret,
    set_user_store,
)
from boneio.webui.routes import onboarding as onboarding_module
from boneio.webui.routes.onboarding import router as onboarding_router


@pytest.fixture
def store(tmp_path):
    store = UserStore(tmp_path / USERS_FILENAME)
    store.load()
    set_jwt_secret("test-secret-for-middleware-tests")
    set_auth_config({})
    set_allow_anonymous(False)
    set_user_store(store)
    onboarding_module.set_user_store(store)
    onboarding_module.set_legacy_migration(None)
    yield store
    set_user_store(None)
    onboarding_module.set_user_store(None)
    set_auth_config({})
    set_allow_anonymous(False)


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


def test_device_without_accounts_refuses_until_setup(client):
    """F-02: before 1.6 this served the whole API to anyone on the network."""
    response = client.get("/api/protected")
    assert response.status_code == 403
    assert response.json()["code"] == "setup_required"


def test_allow_anonymous_reopens_the_device(client):
    """The config-file opt-out, for headless installs and upstream auth."""
    set_allow_anonymous(True)
    assert client.get("/api/protected").status_code == 200


def test_allow_anonymous_is_not_reachable_from_the_wizard(client):
    """The opt-out must never be one click away in the setup flow."""
    import boneio.webui.routes.onboarding as onboarding

    body = client.get("/api/onboarding/status").json()
    assert "allow_anonymous" not in body
    assert not hasattr(onboarding.router, "allow_anonymous")


def test_provisioning_closes_the_api_without_a_restart(client, store):
    """The wizard writes users.json and leaves config.yaml empty, so a gate on
    web.auth would leave the API open until the next reboot."""
    assert client.get("/api/protected").status_code == 403

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


def test_token_ttl_matches_the_configured_lifetime():
    """The login token lifetime is a deliberate security/UX choice; guard it."""
    from datetime import UTC, datetime

    from boneio.webui.middleware.auth import TOKEN_TTL_DAYS, create_token, verify_token

    set_jwt_secret("test-secret-for-ttl")
    payload = verify_token(create_token({"sub": "pawel", "role": "admin"}))
    assert payload is not None

    remaining_days = (datetime.fromtimestamp(payload["exp"], tz=UTC) - datetime.now(UTC)).days
    # Allow a day of slack for the clock between issue and assertion.
    assert TOKEN_TTL_DAYS - 1 <= remaining_days <= TOKEN_TTL_DAYS


# ------------------------------------------------------------ role enforcement


@pytest.fixture
def rbac_client(store):
    """An app with one operating route and one admin route."""
    app = FastAPI()

    @app.post("/api/outputs/{output_id}/toggle")
    async def toggle(output_id: str):
        return {"toggled": output_id}

    @app.post("/api/restart")
    async def restart():
        return {"restarting": True}

    @app.get("/api/files/config.yaml")
    async def raw_file():
        return {"content": "secret"}

    @app.get("/api/outputs")
    async def list_outputs():
        return {"outputs": []}

    app.add_middleware(AuthMiddleware)
    store.add_user("pawel", "dobre-haslo", Role.ADMIN)
    store.add_user("gosc", "haslo-goscia", Role.VIEWER)
    return TestClient(app)


def _auth(role: str, user: str) -> dict:
    return {"Authorization": f"Bearer {create_token({'sub': user, 'role': role})}"}


def test_viewer_may_operate_outputs(rbac_client):
    response = rbac_client.post(
        "/api/outputs/relay_01/toggle", headers=_auth("viewer", "gosc")
    )
    assert response.status_code == 200


def test_viewer_may_read_state(rbac_client):
    assert rbac_client.get("/api/outputs", headers=_auth("viewer", "gosc")).status_code == 200


def test_viewer_may_not_restart_the_device(rbac_client):
    response = rbac_client.post("/api/restart", headers=_auth("viewer", "gosc"))
    assert response.status_code == 403
    body = response.json()
    assert body["code"] == "forbidden"
    assert body["required_role"] == "admin"


def test_viewer_may_not_read_raw_files(rbac_client):
    assert rbac_client.get(
        "/api/files/config.yaml", headers=_auth("viewer", "gosc")
    ).status_code == 403


def test_admin_may_do_both(rbac_client):
    assert rbac_client.post(
        "/api/outputs/relay_01/toggle", headers=_auth("admin", "pawel")
    ).status_code == 200
    assert rbac_client.post("/api/restart", headers=_auth("admin", "pawel")).status_code == 200
    assert rbac_client.get(
        "/api/files/config.yaml", headers=_auth("admin", "pawel")
    ).status_code == 200


def test_a_token_without_a_role_gets_the_stored_one(rbac_client):
    """Tokens predate roles, and the claim is not what decides: the store is
    asked, and it says pawel is an admin."""
    headers = {"Authorization": f"Bearer {create_token({'sub': 'pawel'})}"}
    assert rbac_client.post("/api/restart", headers=headers).status_code == 200


def test_an_invented_role_gains_nothing(rbac_client):
    """A signed token naming 'superadmin' for a real viewer stays a viewer."""
    assert rbac_client.post("/api/restart", headers=_auth("superadmin", "gosc")).status_code == 403
    assert rbac_client.get("/api/outputs", headers=_auth("superadmin", "gosc")).status_code == 200


# ------------------------------------- account changes reach an open session


def test_deleting_an_account_kills_its_session(rbac_client, store):
    """Tokens are valid for weeks and cannot be revoked one by one, so the
    store — not the claim — has to decide whether the caller still exists."""
    headers = _auth("viewer", "gosc")
    assert rbac_client.get("/api/outputs", headers=headers).status_code == 200

    store.delete_user("gosc")

    response = rbac_client.get("/api/outputs", headers=headers)
    assert response.status_code == 401
    assert response.json()["code"] == "account_gone"


def test_demoting_an_admin_takes_effect_on_the_next_request(rbac_client, store):
    store.add_user("druga", "haslo-admina", Role.ADMIN)
    headers = _auth("admin", "pawel")
    assert rbac_client.post("/api/restart", headers=headers).status_code == 200

    store.set_role("pawel", Role.VIEWER)

    # The token still claims admin; the store says otherwise and wins.
    assert rbac_client.post("/api/restart", headers=headers).status_code == 403
    assert rbac_client.get("/api/outputs", headers=headers).status_code == 200


def test_promoting_a_viewer_takes_effect_without_a_new_token(rbac_client, store):
    headers = _auth("viewer", "gosc")
    assert rbac_client.post("/api/restart", headers=headers).status_code == 403

    store.set_role("gosc", Role.ADMIN)

    assert rbac_client.post("/api/restart", headers=headers).status_code == 200


def test_a_forged_admin_claim_gains_nothing(rbac_client, store):
    """Signed tokens are trusted for identity only — 'gosc' is a viewer in the
    store whatever the claim says."""
    assert rbac_client.post("/api/restart", headers=_auth("admin", "gosc")).status_code == 403


def test_unknown_subject_is_rejected(rbac_client):
    assert rbac_client.get(
        "/api/outputs", headers=_auth("admin", "nigdy-nie-istnial")
    ).status_code == 401
