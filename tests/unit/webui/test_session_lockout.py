"""A session that keeps typing wrong passwords is signed out.

The password prompt and the own-password form draw on the login's attempt
buckets, but those are sliding windows: a few guesses every five minutes stay
under them forever. So the session keeps its own count, cumulative and kept in
users.json, and at SESSION_MAX_WRONG_PASSWORDS it is signed out — that session
only, since the point is to stop whoever holds it, not to lock the owner out.
"""

from __future__ import annotations

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from boneio.core.auth.models import Role, User
from boneio.core.auth.store import USERS_FILENAME, UserStore
from boneio.webui.middleware.auth import (
    REAUTH_WINDOW,
    AuthMiddleware,
    create_token,
    issue_token,
    set_allow_anonymous,
    set_auth_config,
    set_jwt_secret,
    set_user_store,
    verify_token,
)
from boneio.webui.rate_limit import LOGIN_MAX_ATTEMPTS, login_rate_limiter
from boneio.webui.routes.accounts import router as accounts_router
from boneio.webui.routes.auth import SESSION_MAX_WRONG_PASSWORDS
from boneio.webui.routes.auth import router as auth_router

from .real_app import real_app_client

SECRET = "test-secret-for-session-lockout--------"


@pytest.fixture(autouse=True)
def _clean_globals():
    login_rate_limiter._failures.clear()
    yield
    login_rate_limiter._failures.clear()
    set_user_store(None)
    set_auth_config({})
    set_allow_anonymous(False)


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


def _confirm(client, token: str, password: str = "zle"):
    return client.post("/api/auth/confirm", headers=_bearer(token), json={"password": password})


def _me(client, token: str) -> int:
    return client.get("/api/account/me", headers=_bearer(token)).status_code


# --------------------------------------------------------------- the count


def test_each_wrong_password_says_how_many_are_left(client, store):
    token = issue_token(store.get_user("pawel"))
    first = _confirm(client, token)
    assert first.status_code == 403
    assert first.json()["attempts_left"] == SESSION_MAX_WRONG_PASSWORDS - 1


def test_the_last_wrong_password_signs_the_session_out(client, store):
    token = issue_token(store.get_user("pawel"))
    for _ in range(SESSION_MAX_WRONG_PASSWORDS - 1):
        assert _confirm(client, token).status_code == 403

    last = _confirm(client, token)
    assert last.status_code == 401
    assert last.json()["code"] == "session_locked"

    refused = client.get("/api/account/me", headers=_bearer(token))
    assert refused.status_code == 401
    assert refused.json()["code"] == "session_locked"


def test_the_accounts_other_sessions_carry_on(client, store):
    """The promise: whoever was guessing is out, the owner is not."""
    guessing = issue_token(store.get_user("pawel"))
    owner = issue_token(store.get_user("pawel"))
    for _ in range(SESSION_MAX_WRONG_PASSWORDS):
        _confirm(client, guessing)

    assert _me(client, guessing) == 401
    assert _me(client, owner) == 200


def test_a_right_password_clears_the_count(client, store):
    token = issue_token(store.get_user("pawel"))
    for _ in range(SESSION_MAX_WRONG_PASSWORDS - 1):
        _confirm(client, token)
    fresh = _confirm(client, token, "haslo-admina").json()["token"]

    for _ in range(SESSION_MAX_WRONG_PASSWORDS - 1):
        assert _confirm(client, fresh).status_code == 403
    assert _me(client, fresh) == 200


def test_the_count_is_not_a_window(client, store):
    """A patient guesser does not get a fresh allowance by waiting."""
    token = issue_token(store.get_user("pawel"))
    for _ in range(SESSION_MAX_WRONG_PASSWORDS - 1):
        _confirm(client, token)
    # The login buckets have long emptied; the session's count has not.
    login_rate_limiter._failures.clear()
    assert _confirm(client, token).status_code == 401


def test_the_count_survives_a_restart(client, store, tmp_path):
    """A restart must not hand the session a fresh allowance either."""
    token = issue_token(store.get_user("pawel"))
    for _ in range(SESSION_MAX_WRONG_PASSWORDS - 1):
        _confirm(client, token)

    reloaded = UserStore(tmp_path / USERS_FILENAME)
    reloaded.load()
    set_user_store(reloaded)
    login_rate_limiter._failures.clear()

    assert _confirm(client, token).status_code == 401
    assert _me(client, token) == 401


def test_the_sign_out_survives_a_restart(client, store, tmp_path):
    token = issue_token(store.get_user("pawel"))
    for _ in range(SESSION_MAX_WRONG_PASSWORDS):
        _confirm(client, token)

    reloaded = UserStore(tmp_path / USERS_FILENAME)
    reloaded.load()
    set_user_store(reloaded)
    assert _me(client, token) == 401


def test_confirming_keeps_the_session(client, store):
    token = issue_token(store.get_user("pawel"))
    fresh = _confirm(client, token, "haslo-admina").json()["token"]
    assert verify_token(fresh)["sid"] == verify_token(token)["sid"]


def test_the_count_left_is_the_smaller_of_the_two(client, store):
    """Saying "4 left" and answering the next one with a 429 would be a lie."""
    for _ in range(LOGIN_MAX_ATTEMPTS - 2):
        client.post("/api/login", json={"username": "pawel", "password": "zle"})
    token = issue_token(store.get_user("pawel"))
    assert _confirm(client, token).json()["attempts_left"] == 1


def test_the_own_password_form_counts_too(client, store):
    token = issue_token(store.get_user("gosc"))
    for _ in range(SESSION_MAX_WRONG_PASSWORDS):
        last = client.put(
            "/api/account/password",
            headers=_bearer(token),
            json={"current_password": "zle", "new_password": "zupelnie-nowe"},
        )
    assert last.status_code == 401
    assert last.json()["code"] == "session_locked"


# ---------------------------------------------- tokens from before the sid


def test_a_token_without_a_session_id_is_signed_out_on_its_own(client, store):
    """Every token alive when this shipped has no sid — a stolen one included."""
    stale = int(time.time() - REAUTH_WINDOW.total_seconds() - 60)
    guessing = create_token({"sub": "pawel", "role": "admin", "auth_time": stale})
    other = create_token({"sub": "pawel", "role": "admin", "auth_time": stale + 1})
    for _ in range(SESSION_MAX_WRONG_PASSWORDS):
        _confirm(client, guessing)

    assert _me(client, guessing) == 401
    assert _me(client, other) == 200
    assert store.get_user("pawel").session_version == 0


# ------------------------------------------------------------- users.json


def test_the_bookkeeping_stays_out_of_api_responses(store):
    token = issue_token(store.get_user("pawel"))
    sid = verify_token(token)["sid"]
    store.record_session_failure("pawel", sid, int(time.time()) + 3600)
    public = store.get_user("pawel").to_public_dict()
    assert "session_failures" not in public
    assert "revoked_sessions" not in public


def test_expired_entries_are_pruned(store):
    past = int(time.time()) - 10
    store.revoke_session("pawel", "old", past)
    store.revoke_session("pawel", "new", int(time.time()) + 3600)
    assert set(store.get_user("pawel").revoked_sessions) == {"new"}


@pytest.mark.parametrize(
    "garbage",
    [None, "x", [1, 2], {"a": "b"}, {"a": {"count": "1", "until": 2}}, {"a": True}],
)
def test_a_garbled_users_json_reads_as_nothing_recorded(garbage):
    user = User.from_dict(
        {
            "username": "stary",
            "password_hash": "x",
            "role": "admin",
            "revoked_sessions": garbage,
            "session_failures": garbage,
        }
    )
    assert user.revoked_sessions == {}
    assert user.session_failures == {}


# ------------------------------------------------------- the whole app


def test_the_lockout_through_the_real_app(tmp_path):
    """Signed out through init_app's whole stack, and signing in again works."""
    with real_app_client(tmp_path, SECRET, {"pawel": "haslo-admina"}) as client:
        origin = {"Origin": "http://testserver"}

        token = client.post(
            "/api/login", headers=origin, json={"username": "pawel", "password": "haslo-admina"}
        ).json()["token"]
        for _ in range(SESSION_MAX_WRONG_PASSWORDS):
            last = client.post(
                "/api/auth/confirm", headers={**_bearer(token), **origin}, json={"password": "zle"}
            )
        assert last.status_code == 401
        assert last.json()["code"] == "session_locked"

        again = client.post(
            "/api/login", headers=origin, json={"username": "pawel", "password": "haslo-admina"}
        )
        assert again.status_code == 200
        assert client.get("/api/account/me", headers=_bearer(again.json()["token"])).status_code == 200
