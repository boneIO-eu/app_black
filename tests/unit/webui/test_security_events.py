"""Password guessing, told to Home Assistant.

What these pin down: an event goes out once per guessing burst rather than
once per refused attempt, its payload is what the HA event entity declares,
and a username typed by a stranger cannot put anything odd in a notification.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from boneio.core.auth.models import Role
from boneio.core.auth.store import USERS_FILENAME, UserStore
from boneio.core.manager.security_alert import SecurityAlertPublisher
from boneio.integration.homeassistant import ha_security_event_message
from boneio.webui import security_events
from boneio.webui.middleware.auth import (
    AuthMiddleware,
    issue_token,
    set_allow_anonymous,
    set_auth_config,
    set_jwt_secret,
    set_user_store,
)
from boneio.webui.rate_limit import LOGIN_MAX_ATTEMPTS, login_rate_limiter
from boneio.webui.routes.accounts import router as accounts_router
from boneio.webui.routes.auth import SESSION_MAX_WRONG_PASSWORDS
from boneio.webui.routes.auth import router as auth_router

from .real_app import real_app_client

SECRET = "test-secret-for-security-events-------"


@pytest.fixture(autouse=True)
def sent():
    events: list[dict] = []
    login_rate_limiter._failures.clear()
    security_events.set_publisher(events.append)
    yield events
    security_events.set_publisher(None)
    login_rate_limiter._failures.clear()
    set_user_store(None)
    set_auth_config({})
    set_allow_anonymous(False)


@pytest.fixture
def client(tmp_path):
    store = UserStore(tmp_path / USERS_FILENAME)
    store.load()
    set_jwt_secret(SECRET)
    set_auth_config({})
    set_allow_anonymous(False)
    set_user_store(store)
    store.add_user("pawel", "haslo-admina", Role.ADMIN)
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(accounts_router)
    app.add_middleware(AuthMiddleware)
    client = TestClient(app)
    client.store = store
    return client


def _wrong_login(client, username="pawel"):
    return client.post("/api/login", json={"username": username, "password": "zle"})


# ---------------------------------------------------------------- bursts


def test_a_burst_of_wrong_logins_is_one_event(client, sent):
    for _ in range(LOGIN_MAX_ATTEMPTS + 5):
        _wrong_login(client)
    assert [e["event_type"] for e in sent] == ["password_guessing"]
    assert sent[0]["username"] == "pawel"
    assert sent[0]["where"] == "login"


def test_a_few_wrong_logins_are_not_an_event(client, sent):
    for _ in range(LOGIN_MAX_ATTEMPTS - 1):
        _wrong_login(client)
    assert sent == []


def test_a_session_signed_out_for_guessing_is_an_event(client, sent):
    token = issue_token(client.store.get_user("pawel"))
    for _ in range(SESSION_MAX_WRONG_PASSWORDS):
        client.post(
            "/api/auth/confirm",
            headers={"Authorization": f"Bearer {token}"},
            json={"password": "zle"},
        )
    assert [e["event_type"] for e in sent] == ["session_signed_out"]
    assert sent[0]["where"] == "confirm"


def test_the_own_password_form_says_so(client, sent):
    token = issue_token(client.store.get_user("pawel"))
    for _ in range(SESSION_MAX_WRONG_PASSWORDS):
        client.put(
            "/api/account/password",
            headers={"Authorization": f"Bearer {token}"},
            json={"current_password": "zle", "new_password": "zupelnie-nowe"},
        )
    assert sent[-1]["where"] == "password_change"


# --------------------------------------------------------------- payload


def test_the_payload_is_what_the_entity_declares(sent):
    security_events.emit("password_guessing", username="pawel", client="192.168.50.31", where="login")
    event = sent[0]
    assert event["event_type"] in ha_security_event_message(MagicMock(topic_prefix="boneio"))["event_types"]
    assert event["client"] == "192.168.50.31"
    assert "pawel" in event["message"]


def test_the_loopback_is_not_reported_as_the_client(sent):
    """Behind a misconfigured proxy it would be, and it says nothing."""
    security_events.emit("password_guessing", username="pawel", client="127.0.0.1", where="login")
    assert "client" not in sent[0]


def test_an_event_the_entity_does_not_declare_is_not_sent(sent):
    security_events.emit("something_else", username="pawel", where="login")
    assert sent == []


@pytest.mark.parametrize(
    ("typed", "shown"),
    [
        ("pawel\n\u001b[31m", "pawel[31m"),
        ("‮evil", "evil"),
        ("x" * 200, "x" * 63 + "…"),
    ],
)
def test_a_typed_username_is_made_safe(typed, shown):
    assert security_events.clean_username(typed) == shown


def test_a_broken_publisher_does_not_break_the_login(client):
    def broken(_payload):
        raise RuntimeError("broker down")

    security_events.set_publisher(broken)
    for _ in range(LOGIN_MAX_ATTEMPTS):
        response = _wrong_login(client)
    assert response.status_code == 401


# ------------------------------------------------------------- MQTT & HA


def test_events_are_published_unretained():
    """A retained event would fire again every time HA reconnects."""
    manager = MagicMock()
    manager._topic_prefix = "boneio"
    SecurityAlertPublisher(manager).publish_event({"event_type": "password_guessing"})
    kwargs = manager.send_message.call_args.kwargs
    assert kwargs["topic"] == "boneio/security/event"
    assert kwargs["retain"] is False
    assert json.loads(kwargs["payload"]) == {"event_type": "password_guessing"}


def test_the_entity_is_a_diagnostic_event():
    helper = MagicMock()
    helper.topic_prefix = "boneio"
    msg = ha_security_event_message(helper)
    assert msg["state_topic"] == "boneio/security/event"
    assert msg["event_types"] == list(security_events.EVENT_TYPES)
    assert msg["entity_category"] == "diagnostic"


def test_init_app_hands_events_to_the_manager(tmp_path):
    with real_app_client(tmp_path, SECRET, {"pawel": "haslo-admina"}) as client:
        manager = client.app.state.manager
        security_events.emit("password_guessing", username="pawel", where="login")
        manager.security_alert.publish_event.assert_called_once()
