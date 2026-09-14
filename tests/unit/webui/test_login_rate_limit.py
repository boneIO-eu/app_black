"""Tests for login throttling (F-06)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from boneio.core.auth.models import Role
from boneio.core.auth.store import USERS_FILENAME, UserStore
from boneio.webui.middleware.auth import (
    set_allow_anonymous,
    set_auth_config,
    set_jwt_secret,
    set_user_store,
)
from boneio.webui.rate_limit import (
    LOGIN_MAX_ATTEMPTS,
    RateLimiter,
    ip_key,
    login_rate_limiter,
    user_key,
)
from boneio.webui.routes.auth import router as auth_router


@pytest.fixture
def store(tmp_path):
    store = UserStore(tmp_path / USERS_FILENAME)
    store.load()
    set_jwt_secret("test-secret-for-rate-limit")
    set_auth_config({})
    set_allow_anonymous(False)
    set_user_store(store)
    store.add_user("pawel", "dobre-haslo", Role.ADMIN)
    yield store
    set_user_store(None)


@pytest.fixture(autouse=True)
def _clear_limiter():
    """The limiter is a module-level singleton shared across tests."""
    login_rate_limiter._failures.clear()
    yield
    login_rate_limiter._failures.clear()


@pytest.fixture
def client(store):
    app = FastAPI()
    app.include_router(auth_router)
    return TestClient(app)


def _attempt(client, username="pawel", password="zle"):
    return client.post("/api/login", json={"username": username, "password": password})


# ------------------------------------------------------------------ throttling


def test_wrong_passwords_are_eventually_throttled(client):
    """Pre-1.6 this endpoint accepted unlimited guesses."""
    for _ in range(LOGIN_MAX_ATTEMPTS):
        assert _attempt(client).status_code == 401

    response = _attempt(client)
    assert response.status_code == 429


def test_throttled_response_says_how_long_to_wait(client):
    for _ in range(LOGIN_MAX_ATTEMPTS):
        _attempt(client)

    response = _attempt(client)
    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 0


def test_the_correct_password_is_refused_while_throttled(client):
    """Otherwise the limiter would only slow down a wrong guess, not a run."""
    for _ in range(LOGIN_MAX_ATTEMPTS):
        _attempt(client)

    assert _attempt(client, password="dobre-haslo").status_code == 429


def test_a_success_clears_the_counter(client):
    for _ in range(LOGIN_MAX_ATTEMPTS - 1):
        assert _attempt(client).status_code == 401

    assert _attempt(client, password="dobre-haslo").status_code == 200

    # The earlier fumbles are forgiven, so the budget is whole again.
    for _ in range(LOGIN_MAX_ATTEMPTS):
        assert _attempt(client).status_code == 401


def test_unknown_accounts_are_throttled_too(client):
    """Spraying names must not be cheaper than guessing one password."""
    for _ in range(LOGIN_MAX_ATTEMPTS):
        assert _attempt(client, username="nieistniejacy").status_code == 401

    assert _attempt(client, username="nieistniejacy").status_code == 429


def test_throttling_one_account_does_not_reveal_whether_it_exists(client):
    """The 429 must look the same for a real and an invented account."""
    for _ in range(LOGIN_MAX_ATTEMPTS):
        _attempt(client, username="pawel")
    real = _attempt(client, username="pawel")

    login_rate_limiter._failures.clear()

    for _ in range(LOGIN_MAX_ATTEMPTS):
        _attempt(client, username="zmyslony")
    invented = _attempt(client, username="zmyslony")

    assert real.status_code == invented.status_code == 429
    assert real.json() == invented.json()


def test_one_account_being_throttled_leaves_another_usable(client, store):
    """An attacker grinding one name must not lock the rest of the household
    out — that would be a denial of service on the owner."""
    store.add_user("gosc", "haslo-goscia", Role.VIEWER)

    for _ in range(LOGIN_MAX_ATTEMPTS):
        _attempt(client, username="pawel")
    assert _attempt(client, username="pawel").status_code == 429

    # Same client IP, different account: the per-IP bucket is shared, so this
    # documents the deliberate trade — see test_ip_bucket_is_shared below.
    assert _attempt(client, username="gosc", password="haslo-goscia").status_code == 429


def test_ip_bucket_is_shared_on_purpose(client):
    """Counting per IP as well as per account is what catches one guess
    sprayed across many usernames; the cost is that a single busy client
    spends one budget. The window drains, so nobody is locked out."""
    for i in range(LOGIN_MAX_ATTEMPTS):
        assert _attempt(client, username=f"nazwa{i}").status_code == 401

    assert _attempt(client, username="jeszcze-inna").status_code == 429


# -------------------------------------------------------------- the limiter


def test_limiter_drains_as_the_window_slides():
    limiter = RateLimiter(max_attempts=2, window_seconds=300, name="test")
    limiter.record_failure("k")
    limiter.record_failure("k")
    assert limiter.check("k") is False

    # Age the recorded failures past the window instead of sleeping.
    limiter._failures["k"] = [t - 301 for t in limiter._failures["k"]]
    assert limiter.check("k") is True


def test_limiter_keys_never_collide():
    """An account called '10.0.0.5' must not share a bucket with that address."""
    assert ip_key("10.0.0.5") != user_key("10.0.0.5")


def test_usernames_share_a_bucket_across_casings():
    """Otherwise 'Admin' and 'admin' would double an attacker's budget."""
    assert user_key("Admin") == user_key("admin") == user_key("  ADMIN  ")


def test_reset_clears_only_the_named_keys():
    limiter = RateLimiter(max_attempts=1, window_seconds=300, name="test")
    limiter.record_failure("a")
    limiter.record_failure("b")
    limiter.reset("a")
    assert limiter.check("a") is True
    assert limiter.check("b") is False
