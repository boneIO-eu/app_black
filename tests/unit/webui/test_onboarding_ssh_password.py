"""The first administrator's password becomes the SSH password too.

A 1.6 image ships the boneio login locked, so nobody can reach a fresh device
over SSH with a password — not with the "Black" every unit used to share. The
owner's first password, typed into the wizard, is what opens it. The wizard
says so, and the reply says whether it happened.

What the wizard must never do is fail because of it, or replace a password the
owner already chose over SSH.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from boneio.core.auth.store import USERS_FILENAME, UserStore
from boneio.core.system_ops import Result
from boneio.webui.middleware.auth import set_auth_config, set_jwt_secret, set_user_store
from boneio.webui.routes import onboarding as onboarding_module
from boneio.webui.routes.onboarding import router as onboarding_router

ADMIN = {"username": "wlasciciel", "password": "ZupelnieInneHaslo-42"}


@pytest.fixture
def client(tmp_path):
    store = UserStore(tmp_path / USERS_FILENAME)
    store.load()
    set_jwt_secret("test-secret-for-ssh-password-tests")
    set_auth_config({})
    set_user_store(store)
    onboarding_module.set_user_store(store)
    onboarding_module.set_legacy_migration(None)
    app = FastAPI()
    app.include_router(onboarding_router)
    yield TestClient(app)
    set_user_store(None)
    onboarding_module.set_user_store(None)
    set_auth_config({})


@pytest.fixture
def helper(monkeypatch):
    """Stand in for boneio-system, recording what the wizard asked of it."""

    class Helper:
        state: str | None = "locked"
        init_ok = True
        given: list[str] = []

    def state():
        return Helper.state

    def init(password):
        Helper.given.append(password)
        return Result(0 if Helper.init_ok else 1, "", "" if Helper.init_ok else "refused")

    Helper.given = []
    monkeypatch.setattr(onboarding_module.system_ops, "service_password_state", state)
    monkeypatch.setattr(onboarding_module.system_ops, "service_password_init", init)
    return Helper


def test_a_fresh_device_takes_the_owners_password(client, helper):
    reply = client.post("/api/onboarding/admin", json=ADMIN)

    assert reply.status_code == 201
    assert reply.json()["ssh"] == "set"
    assert helper.given == [ADMIN["password"]]


@pytest.mark.parametrize("state", ["shipped", "empty"])
def test_the_shipped_password_is_replaced(client, helper, state):
    # An upgraded device still on "Black", or one with no password at all:
    # whoever holds the account already has root, so replacing it grants
    # nothing and removes the one everybody knows.
    helper.state = state
    assert client.post("/api/onboarding/admin", json=ADMIN).json()["ssh"] == "set"


def test_a_password_the_owner_chose_is_left_alone(client, helper):
    helper.state = "set"
    reply = client.post("/api/onboarding/admin", json=ADMIN)

    assert reply.json()["ssh"] == "kept"
    assert helper.given == []


def test_no_helper_does_not_stop_the_wizard(client, helper):
    helper.state = None
    reply = client.post("/api/onboarding/admin", json=ADMIN)

    assert reply.status_code == 201
    assert reply.json()["ssh"] == "unavailable"
    assert reply.json()["token"]


def test_a_refusal_does_not_stop_the_wizard(client, helper):
    helper.init_ok = False
    reply = client.post("/api/onboarding/admin", json=ADMIN)

    assert reply.status_code == 201
    assert reply.json()["ssh"] == "failed"
