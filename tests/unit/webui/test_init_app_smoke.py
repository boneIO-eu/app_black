"""Smoke tests for init_app.

init_app had no coverage at all, which is how a function-local `import os`
shadowing the module import shipped to a controller and crash-looped the
service: every use of `os` earlier in the function raised UnboundLocalError,
and nothing here exercised the function to notice. These tests call it for
real, so that class of mistake fails on a laptop instead of on hardware.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from boneio.core.auth.models import Role
from boneio.core.auth.store import USERS_FILENAME, UserStore
from boneio.webui.app import init_app
from boneio.webui.middleware.auth import (
    get_user_store,
    is_anonymous_allowed,
    is_auth_required,
    set_allow_anonymous,
    set_user_store,
)


@pytest.fixture
def config_file(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("web:\n  port: 8090\n", encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _reset_auth_globals():
    yield
    set_user_store(None)
    set_allow_anonymous(False)


def _init(config_file, auth_config=None, monkeypatch=None, dev=False):
    if monkeypatch is not None:
        if dev:
            monkeypatch.setenv("BONEIO_DEV", "1")
        else:
            monkeypatch.delenv("BONEIO_DEV", raising=False)
    return init_app(
        manager=MagicMock(),
        yaml_config_file=str(config_file),
        config_helper=MagicMock(),
        auth_config=auth_config or {},
        jwt_secret="smoke-test-secret",
    )


def test_init_app_runs_on_a_fresh_device(config_file, monkeypatch):
    """The regression: this raised UnboundLocalError and crash-looped boneio."""
    app = _init(config_file, monkeypatch=monkeypatch)
    assert app is not None
    assert get_user_store() is not None


def test_init_app_leaves_a_fresh_device_closed(config_file, monkeypatch):
    _init(config_file, monkeypatch=monkeypatch)
    assert is_auth_required() is False
    assert is_anonymous_allowed() is False


def test_boneio_dev_opens_an_unprovisioned_device(config_file, monkeypatch):
    """What a developer running the Vite dev server needs."""
    _init(config_file, monkeypatch=monkeypatch, dev=True)
    assert is_anonymous_allowed() is True


def test_allow_anonymous_from_config_is_honoured(config_file, monkeypatch):
    _init(config_file, auth_config={"allow_anonymous": True}, monkeypatch=monkeypatch)
    assert is_anonymous_allowed() is True


def test_init_app_migrates_legacy_credentials(config_file, monkeypatch):
    _init(
        config_file,
        auth_config={"username": "pawel", "password": "stare-haslo"},
        monkeypatch=monkeypatch,
    )
    store = get_user_store()
    assert store.verify_credentials("pawel", "stare-haslo") is not None
    assert is_auth_required() is True


def test_init_app_on_a_provisioned_device(config_file, monkeypatch):
    seed = UserStore(config_file.parent / USERS_FILENAME)
    seed.add_user("pawel", "haslo-admina", Role.ADMIN)

    _init(config_file, monkeypatch=monkeypatch)
    assert is_auth_required() is True


def test_boneio_dev_does_not_unlock_a_provisioned_device(config_file, monkeypatch):
    """Dev mode opens setup, not a device that already has an owner."""
    seed = UserStore(config_file.parent / USERS_FILENAME)
    seed.add_user("pawel", "haslo-admina", Role.ADMIN)

    _init(config_file, monkeypatch=monkeypatch, dev=True)
    assert is_auth_required() is True
