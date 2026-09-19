"""Tests for withholding the serial number from unauthenticated callers.

/api/version and /api/init answer without a token on purpose — the UI needs
them to decide whether to show a login form — but the serial identifies the
unit and feeds its cloud subdomain and MQTT topics, so it must not be part of
an anonymous reply (F-03).
"""

from __future__ import annotations

import os

import pytest
from fastapi import FastAPI, Request
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

SERIAL = "blk265f49"


@pytest.fixture
def store(tmp_path):
    """A store wired into the auth middleware."""
    store = UserStore(tmp_path / USERS_FILENAME)
    store.load()
    set_jwt_secret("test-secret-for-serial-tests------------")
    set_auth_config({})
    set_user_store(store)
    yield store
    set_user_store(None)
    set_auth_config({})
    set_allow_anonymous(False)


@pytest.fixture
def client(store):
    """Two exempt routes behind the real middleware.

    The routes mirror what system.py returns, so the test exercises the
    middleware's best-effort identity pass and the gate together.
    """
    from boneio.webui.routes.system import _may_see_serial

    app = FastAPI()

    @app.get("/api/version")
    async def version(request: Request):
        payload = {"version": "1.6.0"}
        if _may_see_serial(request):
            payload["serial_no"] = SERIAL
            payload["serial_override"] = None
        return payload

    @app.get("/api/init")
    async def init(request: Request):
        payload = {"version": "1.6.0", "name": "boneIO"}
        if _may_see_serial(request):
            payload["serial_no"] = SERIAL
        return payload

    @app.get("/api/outputs")
    async def outputs():
        return {"outputs": []}

    app.add_middleware(AuthMiddleware)
    return TestClient(app)


def _admin_token(store):
    store.add_user("pawel", "correct horse battery", Role.ADMIN)
    return create_token({"sub": "pawel", "role": str(Role.ADMIN)})


class TestProvisionedDevice:
    """A device with an account: the serial is for signed-in callers only."""

    def test_version_hides_the_serial_from_a_stranger(self, client, store):
        _admin_token(store)
        body = client.get("/api/version").json()
        assert body["version"] == "1.6.0"
        assert "serial_no" not in body
        assert "serial_override" not in body

    def test_init_hides_the_serial_from_a_stranger(self, client, store):
        _admin_token(store)
        body = client.get("/api/init").json()
        # The fields the login screen needs still come through.
        assert body["name"] == "boneIO"
        assert "serial_no" not in body

    def test_a_signed_in_caller_still_gets_the_serial(self, client, store):
        token = _admin_token(store)
        body = client.get(
            "/api/version", headers={"Authorization": f"Bearer {token}"}
        ).json()
        assert body["serial_no"] == SERIAL

    def test_init_gives_a_signed_in_caller_the_serial(self, client, store):
        token = _admin_token(store)
        body = client.get(
            "/api/init", headers={"Authorization": f"Bearer {token}"}
        ).json()
        assert body["serial_no"] == SERIAL


class TestExemptRoutesStayReachable:
    """The identity pass must not turn an exempt route into a gated one."""

    def test_a_garbage_token_leaves_the_route_answering(self, client, store):
        _admin_token(store)
        response = client.get(
            "/api/version", headers={"Authorization": "Bearer not-a-jwt"}
        )
        assert response.status_code == 200
        assert "serial_no" not in response.json()

    def test_a_wrong_scheme_leaves_the_route_answering(self, client, store):
        _admin_token(store)
        response = client.get("/api/version", headers={"Authorization": "Basic abc"})
        assert response.status_code == 200
        assert "serial_no" not in response.json()

    def test_an_empty_bearer_leaves_the_route_answering(self, client, store):
        _admin_token(store)
        response = client.get("/api/version", headers={"Authorization": "Bearer "})
        assert response.status_code == 200

    def test_a_token_for_a_deleted_account_does_not_reveal_the_serial(
        self, client, store
    ):
        # Tokens outlive accounts; the role lookup is what catches this.
        token = _admin_token(store)
        # A second admin first: the store refuses to remove the last one.
        store.add_user("inny", "correct horse battery", Role.ADMIN)
        store.delete_user("pawel")
        body = client.get(
            "/api/version", headers={"Authorization": f"Bearer {token}"}
        ).json()
        assert "serial_no" not in body

    def test_gating_the_serial_did_not_open_a_real_route(self, client, store):
        _admin_token(store)
        assert client.get("/api/outputs").status_code == 401


class TestAnonymousDevice:
    """With anonymous access on, withholding one field protects nothing."""

    def test_the_serial_is_returned(self, client, store):
        # No accounts and the anonymous opt-in: the whole API is open anyway.
        set_allow_anonymous(True)
        body = client.get("/api/version").json()
        assert body["serial_no"] == SERIAL


@pytest.mark.skipif(
    bool(os.environ.get("BONEIO_DEV")),
    reason="BONEIO_DEV deliberately restores the docs for development",
)
class TestApiDocsAreClosed:
    """The interactive docs sit outside AuthMiddleware, which only gates /api.

    So they cannot be protected — they have to be absent (F-03).
    """

    def test_the_app_ships_without_docs_routes(self):
        from boneio.webui.app import app

        paths = {route.path for route in app.routes}
        assert "/docs" not in paths
        assert "/redoc" not in paths
        assert "/openapi.json" not in paths

    def test_the_schema_urls_are_unset(self):
        from boneio.webui.app import app

        assert app.docs_url is None
        assert app.redoc_url is None
        assert app.openapi_url is None
