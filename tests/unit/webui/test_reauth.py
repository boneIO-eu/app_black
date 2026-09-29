"""The requests that want the password again, not just a valid token.

A login token lives for 30 days on whatever device it was left on. For the
handful of requests that cannot be walked back — accounts, replacing the
configuration, changing the software, the certificate — the middleware wants a
token issued within REAUTH_WINDOW of the password being typed, and the panel
gets a fresh one from POST /api/auth/confirm.
"""

from __future__ import annotations

import re
import time
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from boneio.core.auth.models import Role
from boneio.core.auth.store import USERS_FILENAME, UserStore
from boneio.webui.app import init_app
from boneio.webui.middleware import policy
from boneio.webui.middleware.auth import (
    REAUTH_WINDOW,
    AuthMiddleware,
    create_token,
    issue_token,
    recently_authenticated,
    set_allow_anonymous,
    set_auth_config,
    set_jwt_secret,
    set_user_store,
    verify_token,
)
from boneio.webui.rate_limit import LOGIN_MAX_ATTEMPTS, login_rate_limiter
from boneio.webui.routes.accounts import router as accounts_router
from boneio.webui.routes.auth import router as auth_router

from .route_paths import all_routes

SECRET = "test-secret-for-reauth-tests-----------"


@pytest.fixture(autouse=True)
def _clean_globals():
    login_rate_limiter._failures.clear()
    yield
    login_rate_limiter._failures.clear()
    set_user_store(None)
    set_auth_config({})
    set_allow_anonymous(False)


# ------------------------------------------------------------------ the table


@pytest.fixture
def app_routes(tmp_path) -> list[tuple[str, str]]:
    """Every (method, concrete path) the real application serves."""
    config = tmp_path / "config.yaml"
    config.write_text("web:\n  port: 8090\n", encoding="utf-8")
    app = init_app(
        manager=MagicMock(),
        yaml_config_file=str(config),
        config_helper=MagicMock(),
        auth_config={},
        jwt_secret=SECRET,
    )
    # /api/accounts/{username} → /api/accounts/x, so the policy's patterns
    # can be tried against it as against a real request.
    return [
        (method, re.sub(r"\{[^}]+\}", "x", path)) for method, path in all_routes(app)
    ]


def test_every_entry_guards_a_route_that_exists(app_routes):
    """A typo in the table would guard nothing, silently."""
    dead = [
        (method, pattern.pattern)
        for method, pattern in policy._REAUTH_WRITES
        if not any(m == method and pattern.match(p) for m, p in app_routes)
    ]
    assert dead == []


@pytest.mark.parametrize(
    ("method", "path"),
    [
        # What the panel actually calls, spelled the way it calls it.
        ("POST", "/api/accounts"),
        ("DELETE", "/api/accounts/gosc"),
        ("PUT", "/api/accounts/gosc/role"),
        ("PUT", "/api/accounts/gosc/password"),
        ("POST", "/api/config/restore"),
        ("POST", "/api/config/restore_backup"),
        ("POST", "/api/factory_reset"),
        ("POST", "/api/factory_reset/partial"),
        ("POST", "/api/factory_reset/restore_backup"),
        ("POST", "/api/nodered/backup/restore"),
        ("POST", "/api/nodered/backup/upload_restore"),
        ("POST", "/api/update"),
        ("POST", "/api/update/rollback"),
        ("POST", "/api/os-update/upgrade"),
        ("POST", "/api/os-update/autoupdate"),
        ("POST", "/api/os-update/caddy/apply"),
        ("POST", "/api/security/certificate"),
        ("DELETE", "/api/security/certificate"),
    ],
)
def test_the_panels_dangerous_calls_want_the_password(method, path):
    assert policy.requires_recent_auth(method, path)


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/accounts"),
        ("GET", "/api/security/certificate"),
        ("POST", "/api/os-update/check"),
        ("POST", "/api/check_update_now"),
        ("POST", "/api/restart"),
        ("PUT", "/api/files/config.yaml"),
        ("PUT", "/api/account/password"),
        ("POST", "/api/auth/confirm"),
        ("POST", "/api/config/create_backup"),
        # Anchored: a longer path is not the guarded one.
        ("POST", "/api/update/status"),
    ],
)
def test_everyday_requests_do_not(method, path):
    assert not policy.requires_recent_auth(method, path)


def test_any_role_may_confirm_its_password():
    assert policy.required_role("POST", "/api/auth/confirm") is Role.VIEWER


# ---------------------------------------------------------------- freshness


def _payload(auth_time):
    return {"sub": "pawel", "auth_time": auth_time}


def test_a_token_from_a_login_just_now_is_fresh():
    assert recently_authenticated(_payload(int(time.time())))


def test_a_token_older_than_the_window_is_not():
    old = time.time() - REAUTH_WINDOW.total_seconds() - 5
    assert not recently_authenticated(_payload(int(old)))


def test_a_token_without_the_claim_is_not():
    """Issued before the claim existed, at some point in the last 30 days."""
    assert not recently_authenticated({"sub": "pawel"})


def test_a_little_clock_skew_is_tolerated():
    assert recently_authenticated(_payload(int(time.time()) + 30))


def test_a_timestamp_far_in_the_future_is_not_fresh():
    """What a clock stepping back after NTP leaves behind: fresh for hours."""
    assert not recently_authenticated(_payload(int(time.time()) + 3600))


@pytest.mark.parametrize("raw", ["123", True, None, 10**20])
def test_a_claim_that_is_not_a_timestamp_is_not_fresh(raw):
    assert not recently_authenticated(_payload(raw))


def test_issued_tokens_carry_a_fresh_auth_time(store):
    payload = verify_token(issue_token(store.get_user("pawel")))
    assert recently_authenticated(payload)


# --------------------------------------------------------------- the gate


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
    return store


@pytest.fixture
def client(store):
    app = FastAPI()
    app.include_router(accounts_router)
    app.include_router(auth_router)
    app.add_middleware(AuthMiddleware)
    return TestClient(app)


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _stale(user: str, role: str = "admin") -> str:
    old = int(time.time() - REAUTH_WINDOW.total_seconds() - 60)
    return create_token({"sub": user, "role": role, "auth_time": old})


NEW_VIEWER = {"username": "nowy", "password": "dobre-haslo", "role": "viewer"}


def test_a_stale_token_is_asked_for_the_password(client, store):
    response = client.post("/api/accounts", headers=_bearer(_stale("pawel")), json=NEW_VIEWER)
    assert response.status_code == 403
    assert response.json()["code"] == "reauth_required"
    assert store.get_user("nowy") is None


def test_a_fresh_token_goes_through(client, store):
    token = issue_token(store.get_user("pawel"))
    response = client.post("/api/accounts", headers=_bearer(token), json=NEW_VIEWER)
    assert response.status_code == 201


def test_a_stale_token_still_reads(client):
    """Only the named requests ask; looking around never does."""
    assert client.get("/api/accounts", headers=_bearer(_stale("pawel"))).status_code == 200


def test_a_viewer_is_told_it_is_forbidden_not_asked_for_a_password(client):
    """The role check comes first: a password would not help a viewer."""
    response = client.post(
        "/api/accounts", headers=_bearer(_stale("gosc", "viewer")), json=NEW_VIEWER
    )
    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"


def test_confirming_the_password_makes_the_request_go_through(client, store):
    stale = _stale("pawel")
    confirmed = client.post(
        "/api/auth/confirm", headers=_bearer(stale), json={"password": "haslo-admina"}
    )
    assert confirmed.status_code == 200
    fresh = confirmed.json()["token"]

    payload = verify_token(fresh)
    assert payload["sub"] == "pawel"
    assert payload["ver"] == store.get_user("pawel").session_version

    response = client.post("/api/accounts", headers=_bearer(fresh), json=NEW_VIEWER)
    assert response.status_code == 201


def test_a_wrong_password_is_not_a_sign_out(client):
    """401 would make the panel drop the session; the session is fine."""
    response = client.post(
        "/api/auth/confirm", headers=_bearer(_stale("pawel")), json={"password": "zle"}
    )
    assert response.status_code == 403
    assert response.json()["code"] == "reauth_failed"


def test_confirming_needs_a_token(client):
    assert client.post("/api/auth/confirm", json={"password": "haslo-admina"}).status_code == 401


def test_confirming_only_checks_the_callers_own_password(client):
    """A viewer's token cannot be upgraded by knowing the admin's password."""
    response = client.post(
        "/api/auth/confirm",
        headers=_bearer(_stale("gosc", "viewer")),
        json={"password": "haslo-admina"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "reauth_failed"


def test_confirming_shares_the_login_attempt_budget(client):
    token = _stale("pawel")
    for _ in range(LOGIN_MAX_ATTEMPTS):
        client.post("/api/auth/confirm", headers=_bearer(token), json={"password": "zle"})

    throttled = client.post(
        "/api/auth/confirm", headers=_bearer(token), json={"password": "haslo-admina"}
    )
    assert throttled.status_code == 429


def test_the_own_password_route_is_throttled_too(client, store):
    """With a borrowed token it would otherwise be an unlimited password oracle."""
    token = issue_token(store.get_user("gosc"))
    for _ in range(LOGIN_MAX_ATTEMPTS):
        client.put(
            "/api/account/password",
            headers=_bearer(token),
            json={"current_password": "zle", "new_password": "zupelnie-nowe"},
        )
    throttled = client.put(
        "/api/account/password",
        headers=_bearer(token),
        json={"current_password": "poufne-haslo", "new_password": "zupelnie-nowe"},
    )
    assert throttled.status_code == 429


def test_a_device_on_a_legacy_login_is_not_asked(tmp_path):
    """A web.auth pair has no account for /api/auth/confirm to check."""
    set_jwt_secret(SECRET)
    set_user_store(None)
    set_auth_config({"username": "stary", "password": "haslo"})
    app = FastAPI()
    app.include_router(accounts_router)
    app.add_middleware(AuthMiddleware)
    client = TestClient(app, raise_server_exceptions=False)
    token = create_token({"sub": "stary", "role": "admin"})
    response = client.post("/api/accounts", headers=_bearer(token), json=NEW_VIEWER)
    assert response.json().get("code") != "reauth_required"
