"""Changing the boneio SSH password from the panel: passwd, and nothing more.

The helper does the change as root and keeps the global count of wrong
guesses; these tests are about what the route adds on top — who may call it,
that a wrong password is not a sign-out, that it counts against the session,
and that there is no way through it without the current password.
"""

from __future__ import annotations

import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from boneio.core.auth.models import Role
from boneio.core.auth.store import USERS_FILENAME, UserStore
from boneio.core.system_ops import Result
from boneio.webui.middleware.auth import (
    AuthMiddleware,
    create_token,
    issue_token,
    set_allow_anonymous,
    set_auth_config,
    set_jwt_secret,
    set_user_store,
)
from boneio.webui.routes import accounts as accounts_module
from boneio.webui.routes import security as security_module
from boneio.webui.routes.accounts import router as accounts_router
from boneio.webui.routes.auth import SESSION_MAX_WRONG_PASSWORDS

URL = "/api/accounts/ssh-password"
SSH_NOW = "stare-haslo-ssh"


class FakeHelper:
    """boneio-system's service-password-change, with the same outcomes."""

    def __init__(self):
        self.password = SSH_NOW
        self.state = "set"
        self.supported = True
        self.failures = 0
        self.limit = 5
        self.calls: list[tuple[str, str]] = []
        self.broken = False

    def supports(self, verb):
        return self.supported and verb == "service-password-change"

    def current_state(self):
        return self.state

    def change(self, current, new):
        self.calls.append((current, new))
        if self.broken:
            return Result(1, "", "2026-09-30 [ERROR] chpasswd exploded\n")
        if self.state not in ("set", "shipped"):
            out = {"result": "refused", "state": self.state}
        elif self.failures >= self.limit:
            out = {"result": "throttled", "retry_after": 600}
        elif current != self.password:
            self.failures += 1
            out = {"result": "wrong_password", "attempts_left": self.limit - self.failures}
        else:
            self.failures = 0
            self.password = new
            return Result(0, json.dumps({"result": "changed"}), "")
        return Result(1, json.dumps(out), "")


@pytest.fixture
def helper(monkeypatch):
    fake = FakeHelper()
    ops = accounts_module.system_ops
    monkeypatch.setattr(ops, "helper_supports", fake.supports)
    monkeypatch.setattr(ops, "service_password_state", fake.current_state)
    monkeypatch.setattr(ops, "service_password_change", fake.change)
    return fake


@pytest.fixture
def events(monkeypatch):
    sent: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        accounts_module.security_events, "emit", lambda kind, **kw: sent.append((kind, kw))
    )
    return sent


@pytest.fixture
def store(tmp_path):
    store = UserStore(tmp_path / USERS_FILENAME)
    store.load()
    set_jwt_secret("test-secret-for-ssh-password-tests------")
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
    app.add_middleware(AuthMiddleware)
    return TestClient(app)


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _admin(store) -> dict:
    return _bearer(issue_token(store.get_user("pawel")))


def _change(client, headers, current=SSH_NOW, new="nowe-haslo-ssh"):
    return client.put(URL, headers=headers, json={"current_password": current, "new_password": new})


# ---------------------------------------------------------------- changing


def test_the_right_current_password_changes_it(client, store, helper):
    response = _change(client, _admin(store))
    assert response.status_code == 200
    assert response.json() == {"changed": True}
    assert helper.calls == [(SSH_NOW, "nowe-haslo-ssh")]
    assert helper.password == "nowe-haslo-ssh"


def test_the_security_section_hears_about_it_at_once(client, store, helper, monkeypatch):
    # Otherwise it goes on saying "critical: shipped password" for a minute.
    monkeypatch.setattr(security_module._service_password, "_at", time.monotonic())
    monkeypatch.setattr(security_module._service_password, "_value", "shipped")
    _change(client, _admin(store))
    assert not security_module._service_password.known


def test_a_wrong_current_password_is_not_a_sign_out(client, store, helper):
    # 401 is what the panel takes as "signed out": a typo would drop the owner
    # at the login screen.
    response = _change(client, _admin(store), current="zgadywane")
    assert response.status_code == 403
    assert response.json()["code"] == "current_password_wrong"
    assert response.json()["attempts_left"] == 4
    assert helper.password == SSH_NOW


def test_the_fewer_tries_left_is_the_one_reported(client, store, helper):
    helper.failures = 1  # somebody else guessed through the helper directly
    response = _change(client, _admin(store), current="zgadywane")
    assert response.json()["attempts_left"] == 3


def test_wrong_ssh_passwords_sign_the_session_out(client, store, helper, events):
    helper.limit = 100  # the session's count, not the helper's, is under test
    headers = _admin(store)
    for _ in range(SESSION_MAX_WRONG_PASSWORDS - 1):
        assert _change(client, headers, current="zgadywane").status_code == 403

    last = _change(client, headers, current="zgadywane")
    assert last.status_code == 401
    assert last.json()["code"] == "session_locked"
    assert ("session_signed_out", {"username": "pawel", "client": "testclient",
                                   "where": "ssh_password"}) in events


def test_the_guess_that_shuts_the_helper_tells_home_assistant(client, store, helper, events):
    helper.failures = helper.limit - 1
    _change(client, _admin(store), current="zgadywane")
    assert [kind for kind, _ in events] == ["password_guessing"]
    assert events[0][1]["username"] == "boneio"


def test_throttled_says_when_to_come_back(client, store, helper):
    helper.failures = helper.limit
    response = _change(client, _admin(store))
    assert response.status_code == 429
    assert response.json()["code"] == "ssh_password_throttled"
    assert response.headers["Retry-After"] == "600"
    assert helper.password == SSH_NOW


@pytest.mark.parametrize("state", ["locked", "empty", "unknown"])
def test_no_password_to_know_is_refused(client, store, helper, state):
    helper.state = state
    response = _change(client, _admin(store))
    assert response.status_code == 409
    assert response.json() == {
        "detail": "The SSH login has no password to change.",
        "code": "ssh_password_not_set",
        "state": state,
    }


def test_an_older_helper_is_named_not_tried(client, store, helper):
    helper.supported = False
    response = _change(client, _admin(store))
    assert response.status_code == 409
    assert response.json()["code"] == "helper_outdated"
    assert helper.calls == []


def test_a_helper_failure_is_a_500_with_its_reason(client, store, helper):
    helper.broken = True
    response = _change(client, _admin(store))
    assert response.status_code == 500
    assert response.json()["code"] == "ssh_password_failed"
    assert "chpasswd" in response.json()["detail"]


# ------------------------------------------------------------ what it refuses


def test_there_is_no_way_through_without_the_current_password(client, store, helper):
    headers = _admin(store)
    for body in ({"new_password": "nowe-haslo-ssh"},
                 {"current_password": "", "new_password": "nowe-haslo-ssh"}):
        assert client.put(URL, headers=headers, json=body).status_code == 422
    assert helper.calls == []


@pytest.mark.parametrize(
    ("current", "new", "status"),
    [
        (SSH_NOW, "krotkie", 422),
        (SSH_NOW, "moje-boneio-haslo", 400),
        (SSH_NOW, "dwie\nlinie-hasla", 400),
        ("stare\nnowe-haslo-ssh", "nowe-haslo-ssh", 400),
    ],
    ids=["too-short", "contains-account-name", "line-break-in-new", "line-break-in-current"],
)
def test_unusable_passwords_never_reach_the_helper(client, store, helper, current, new, status):
    # A line break in the current one would move the new one onto a third
    # line of the helper's stdin.
    assert _change(client, _admin(store), current=current, new=new).status_code == status
    assert helper.calls == []


def test_a_viewer_may_not(client, store, helper):
    headers = _bearer(issue_token(store.get_user("gosc")))
    assert _change(client, headers).status_code == 403
    assert client.get(URL, headers=headers).status_code == 403
    assert helper.calls == []


def test_a_stale_login_is_asked_for_the_panel_password_first(client, store, helper):
    token = create_token({"sub": "pawel", "role": "admin", "auth_time": int(time.time()) - 3600})
    response = _change(client, _bearer(token))
    assert response.status_code == 403
    assert response.json()["code"] == "reauth_required"
    assert helper.calls == []


# ----------------------------------------------------------------- reading


def test_the_card_learns_the_state_and_whether_it_can_change_it(client, store, helper):
    assert client.get(URL, headers=_admin(store)).json() == {"state": "set", "supported": True}
    # The state is cached (a sudo call and a yescrypt check each time); what
    # the card shows follows once the cache lets go of the old answer.
    helper.supported, helper.state = False, "shipped"
    security_module.forget_service_password_state()
    assert client.get(URL, headers=_admin(store)).json() == {"state": "shipped", "supported": False}


def test_the_card_does_not_ask_the_helper_again_on_every_open(client, store, helper, monkeypatch):
    calls = []
    real = helper.current_state
    monkeypatch.setattr(
        security_module.system_ops, "service_password_state", lambda: calls.append(1) or real()
    )
    for _ in range(3):
        client.get(URL, headers=_admin(store))
    assert len(calls) == 1
