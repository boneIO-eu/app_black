"""Tests for migrating pre-1.6 ``web.auth`` credentials into ``users.json``."""

from __future__ import annotations

import pytest

from boneio.core.auth.migration import migrate_legacy_auth
from boneio.core.auth.models import Role
from boneio.core.auth.store import USERS_FILENAME, UserStore


@pytest.fixture
def store(tmp_path):
    return UserStore(tmp_path / USERS_FILENAME)


def test_migrates_legacy_pair(store):
    result = migrate_legacy_auth(store, {"username": "pawel", "password": "sekret123"})

    assert result.migrated is True
    assert bool(result) is True
    assert result.username == "pawel"

    user = store.verify_credentials("pawel", "sekret123")
    assert user is not None
    assert user.role is Role.ADMIN
    assert store.is_provisioned() is True


def test_short_legacy_password_is_still_migrated(store):
    """Refusing it would turn an upgrade into a lockout."""
    result = migrate_legacy_auth(store, {"username": "pawel", "password": "Black"})

    assert result.migrated is True
    assert store.verify_credentials("pawel", "Black") is not None


def test_legacy_password_is_hashed_not_copied(store, tmp_path):
    migrate_legacy_auth(store, {"username": "pawel", "password": "sekret123"})
    assert "sekret123" not in (tmp_path / USERS_FILENAME).read_text(encoding="utf-8")


def test_is_idempotent(store):
    migrate_legacy_auth(store, {"username": "pawel", "password": "sekret123"})
    again = migrate_legacy_auth(store, {"username": "ktos", "password": "inne1234"})

    assert again.migrated is False
    assert again.reason == "already_provisioned"
    assert [u.username for u in store.list_users()] == ["pawel"]


def test_existing_admin_is_never_overwritten(store):
    store.add_user("pawel", "nowe-haslo", Role.ADMIN)
    migrate_legacy_auth(store, {"username": "pawel", "password": "stare-haslo"})

    assert store.verify_credentials("pawel", "nowe-haslo") is not None
    assert store.verify_credentials("pawel", "stare-haslo") is None


@pytest.mark.parametrize(
    ("legacy", "reason"),
    [
        (None, "no_legacy_auth"),
        ({}, "no_legacy_auth"),
        ("not-a-dict", "no_legacy_auth"),
        ({"username": "pawel"}, "incomplete_legacy_auth"),
        ({"password": "sekret123"}, "incomplete_legacy_auth"),
        ({"username": "", "password": ""}, "incomplete_legacy_auth"),
    ],
)
def test_nothing_to_migrate(store, legacy, reason):
    result = migrate_legacy_auth(store, legacy)

    assert result.migrated is False
    assert result.reason == reason
    assert store.is_provisioned() is False


def test_unusable_username_leaves_device_for_the_wizard(store):
    """Better an explicit wizard than a silently mangled username."""
    result = migrate_legacy_auth(store, {"username": "pa/wel", "password": "sekret123"})

    assert result.migrated is False
    assert result.reason.startswith("invalid_legacy_auth")
    assert store.is_provisioned() is False


def test_notices_password_came_from_secrets_yaml(store):
    result = migrate_legacy_auth(
        store,
        {"username": "pawel", "password": "sekret123"},
        secrets_values={"sekret123", "mqtt-pass"},
    )

    assert result.migrated is True
    assert result.used_secret_file is True


def test_plain_password_is_not_flagged_as_secret(store):
    result = migrate_legacy_auth(
        store,
        {"username": "pawel", "password": "sekret123"},
        secrets_values={"cos-innego"},
    )

    assert result.used_secret_file is False


def test_config_yaml_is_left_untouched(tmp_path):
    config = tmp_path / "config.yaml"
    original = "web:\n  auth:\n    username: pawel  # moje konto\n    password: sekret123\n"
    config.write_text(original, encoding="utf-8")

    store = UserStore.for_config_file(config)
    migrate_legacy_auth(store, {"username": "pawel", "password": "sekret123"})

    assert config.read_text(encoding="utf-8") == original
