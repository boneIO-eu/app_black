"""Tests for password hashing and the ``users.json`` account store."""

from __future__ import annotations

import json
import stat

import pytest

from boneio.core.auth.hashing import hash_password, needs_rehash, verify_password
from boneio.core.auth.models import Role, User
from boneio.core.auth.store import (
    USERS_FILENAME,
    UserStore,
    UserStoreError,
    normalize_username,
    validate_password,
)


@pytest.fixture
def store(tmp_path):
    """An empty store in a throwaway config directory."""
    return UserStore(tmp_path / USERS_FILENAME)


# ------------------------------------------------------------------ hashing


def test_hash_roundtrip():
    encoded = hash_password("correct horse battery")
    assert verify_password("correct horse battery", encoded) is True
    assert verify_password("wrong horse battery", encoded) is False


def test_hash_is_salted():
    """Two hashes of the same password must differ, or the file leaks reuse."""
    assert hash_password("same-password") != hash_password("same-password")


def test_hash_rejects_empty_password():
    with pytest.raises(ValueError):
        hash_password("")


@pytest.mark.parametrize(
    "broken",
    [
        "",
        "not-a-hash",
        "$scrypt$",
        "$scrypt$n=16384$onlyonefield",
        "$bcrypt$n=16384,r=8,p=1$c2FsdA$aGFzaA",
        "$scrypt$n=abc,r=8,p=1$c2FsdA$aGFzaA",
        "$scrypt$r=8,p=1$c2FsdA$aGFzaA",
    ],
)
def test_verify_treats_broken_hash_as_failure(broken):
    """A corrupt entry must lock that account out, never crash the login route."""
    assert verify_password("anything", broken) is False


def test_tampered_hash_fails():
    encoded = hash_password("secret-password")
    head, _, tail = encoded.rpartition("$")
    tampered = f"{head}${'A' * len(tail)}"
    assert verify_password("secret-password", tampered) is False


def test_needs_rehash():
    encoded = hash_password("secret-password")
    assert needs_rehash(encoded) is False
    assert needs_rehash(encoded.replace("n=16384", "n=1024")) is True
    assert needs_rehash("garbage") is True


# ----------------------------------------------------------------- validation


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("Admin", "admin"), ("  Pawel  ", "pawel"), ("MiXeD", "mixed")],
)
def test_normalize_username(raw, expected):
    assert normalize_username(raw) == expected


@pytest.mark.parametrize(
    "bad",
    ["", "   ", "a" * 65, "we/ird", "back\\slash", "qu\"ote", "new\nline", "nul\x00"],
)
def test_normalize_username_rejects(bad):
    with pytest.raises(UserStoreError):
        normalize_username(bad)


@pytest.mark.parametrize("bad", ["", "short", "1234567"])
def test_validate_password_rejects_short(bad):
    with pytest.raises(UserStoreError):
        validate_password(bad)


def test_validate_password_accepts_eight_chars():
    validate_password("12345678")


@pytest.mark.parametrize(
    "username, password",
    [
        # The exact case Pawel asked about: name and secret identical.
        ("boneioAAA", "boneioAAA"),
        # Case is irrelevant — logging in does not care either.
        ("boneioAAA", "BONEIOaaa"),
        ("admin123", "ADMIN123"),
        # Padding the username out to the length minimum fools nobody.
        ("boneio", "boneio1234"),
        ("boneio", "xx-boneio-xx"),
        # The store matches usernames case-insensitively and trims them, so the
        # policy has to look at the same canonical form.
        ("  boneio  ", "boneio-panel"),
    ],
)
def test_validate_password_rejects_username_lookalikes(username, password):
    with pytest.raises(UserStoreError, match="username"):
        validate_password(password, username)


@pytest.mark.parametrize(
    "username, password",
    [
        # Shares a prefix but is not the username.
        ("boneio", "bone-shaker-42"),
        ("pawel", "correct horse battery"),
        # Too short to ban from inside a password without absurd collateral.
        ("ab", "abstract-cat"),
    ],
)
def test_validate_password_accepts_unrelated(username, password):
    validate_password(password, username)


def test_validate_password_still_rejects_a_short_password_with_username():
    # Length is checked first: the caller should hear the simpler complaint.
    with pytest.raises(UserStoreError, match="at least"):
        validate_password("bone", "boneio")


def test_validate_password_without_username_keeps_length_only():
    # Callers that do not know the account yet must not start failing.
    validate_password("boneioAAA")


def test_add_user_rejects_password_equal_to_username(store):
    with pytest.raises(UserStoreError, match="username"):
        store.add_user("boneioAAA", "boneioAAA", Role.ADMIN)
    assert store.is_provisioned() is False


def test_set_password_rejects_password_equal_to_username(store):
    store.add_user("boneio", "correct horse battery", Role.ADMIN)
    with pytest.raises(UserStoreError, match="username"):
        store.set_password("boneio", "boneio-boneio")
    # The old password must survive a rejected change.
    assert store.verify_credentials("boneio", "correct horse battery") is not None


def test_legacy_migration_keeps_a_weak_password(store):
    # enforce_policy=False exists for credentials that already exist in
    # config.yaml: rejecting them here would lock the owner out of their own
    # device at upgrade time, which is worse than the weak password.
    user = store.add_user("boneio", "boneio", Role.ADMIN, enforce_policy=False)
    assert user.username == "boneio"


# --------------------------------------------------------------- provisioning


def test_missing_file_means_not_provisioned(store):
    store.load()
    assert store.is_provisioned() is False
    assert store.list_users() == []


def test_add_admin_provisions_device(store):
    store.add_user("pawel", "dobre-haslo", Role.ADMIN)
    assert store.is_provisioned() is True
    assert [u.username for u in store.list_users()] == ["pawel"]


def test_viewer_alone_does_not_provision(store):
    """Only an admin counts — a viewer-only device is still unmanageable."""
    store.add_user("gosc", "dobre-haslo", Role.VIEWER)
    assert store.is_provisioned() is False


def test_file_is_written_0600(store):
    store.add_user("pawel", "dobre-haslo")
    mode = stat.S_IMODE(store.path.stat().st_mode)
    assert mode == 0o600, f"expected 0600, got {mode:o}"


def test_no_temp_files_left_behind(store):
    store.add_user("pawel", "dobre-haslo")
    store.set_password("pawel", "inne-haslo")
    leftovers = [p.name for p in store.path.parent.iterdir() if p.name != USERS_FILENAME]
    assert leftovers == []


def test_password_is_not_stored_in_plaintext(store):
    store.add_user("pawel", "bardzo-tajne-haslo")
    assert "bardzo-tajne-haslo" not in store.path.read_text(encoding="utf-8")


# -------------------------------------------------------------------- queries


def test_lookup_is_case_insensitive(store):
    store.add_user("Pawel", "dobre-haslo")
    assert store.get_user("pawel") is not None
    assert store.get_user("PAWEL") is not None


def test_duplicate_username_rejected_across_casing(store):
    store.add_user("pawel", "dobre-haslo")
    with pytest.raises(UserStoreError, match="already exists"):
        store.add_user("PAWEL", "inne-haslo")


def test_verify_credentials(store):
    store.add_user("pawel", "dobre-haslo", Role.ADMIN)
    user = store.verify_credentials("PAWEL", "dobre-haslo")
    assert user is not None
    assert user.role is Role.ADMIN
    assert store.verify_credentials("pawel", "zle-haslo") is None
    assert store.verify_credentials("nieznany", "dobre-haslo") is None


def test_get_user_on_invalid_name_returns_none(store):
    """An unusable name is a miss, not an exception, on the login path."""
    assert store.get_user("we/ird") is None


# -------------------------------------------------------------------- updates


def test_set_password(store):
    store.add_user("pawel", "stare-haslo")
    store.set_password("pawel", "nowe-haslo")
    assert store.verify_credentials("pawel", "nowe-haslo") is not None
    assert store.verify_credentials("pawel", "stare-haslo") is None


def test_set_password_rejects_short(store):
    store.add_user("pawel", "dobre-haslo")
    with pytest.raises(UserStoreError):
        store.set_password("pawel", "krotkie")


def test_cannot_delete_last_admin(store):
    store.add_user("pawel", "dobre-haslo", Role.ADMIN)
    store.add_user("gosc", "dobre-haslo", Role.VIEWER)
    with pytest.raises(UserStoreError, match="last admin"):
        store.delete_user("pawel")
    assert store.is_provisioned() is True


def test_cannot_demote_last_admin(store):
    store.add_user("pawel", "dobre-haslo", Role.ADMIN)
    with pytest.raises(UserStoreError, match="last admin"):
        store.set_role("pawel", Role.VIEWER)


def test_can_delete_admin_when_another_remains(store):
    store.add_user("pawel", "dobre-haslo", Role.ADMIN)
    store.add_user("druga", "dobre-haslo", Role.ADMIN)
    store.delete_user("pawel")
    assert [u.username for u in store.list_users()] == ["druga"]


def test_delete_unknown_user(store):
    with pytest.raises(UserStoreError, match="No such account"):
        store.delete_user("nikt")


# ---------------------------------------------------------------- persistence


def test_changes_survive_a_reload(store, tmp_path):
    store.add_user("pawel", "dobre-haslo", Role.ADMIN)
    store.add_user("gosc", "dobre-haslo", Role.VIEWER)

    reopened = UserStore(tmp_path / USERS_FILENAME)
    reopened.load()
    assert reopened.is_provisioned() is True
    assert {u.username: u.role for u in reopened.list_users()} == {
        "pawel": Role.ADMIN,
        "gosc": Role.VIEWER,
    }
    assert reopened.verify_credentials("pawel", "dobre-haslo") is not None


def test_for_config_file_places_store_next_to_config(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("web:\n  port: 8090\n", encoding="utf-8")
    assert UserStore.for_config_file(config).path == tmp_path / USERS_FILENAME


@pytest.mark.parametrize(
    "content",
    ["{ not json", '["a", "list"]', '{"users": "not-a-list"}'],
)
def test_unreadable_file_raises_rather_than_opening_the_device(tmp_path, content):
    """Falling back to 'no accounts' here would silently disable auth."""
    path = tmp_path / USERS_FILENAME
    path.write_text(content, encoding="utf-8")
    with pytest.raises(UserStoreError):
        UserStore(path).load()


def test_malformed_entries_are_skipped(tmp_path):
    path = tmp_path / USERS_FILENAME
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "users": [
                    {"username": "pawel", "password_hash": hash_password("x" * 10),
                     "role": "admin"},
                    {"username": "brak-hasha"},
                    "not-an-object",
                    {"password_hash": "orphan"},
                ],
            }
        ),
        encoding="utf-8",
    )
    loaded = UserStore(path)
    loaded.load()
    assert [u.username for u in loaded.list_users()] == ["pawel"]


def test_unknown_role_falls_back_to_viewer(tmp_path):
    """A hand-edited file must not be able to invent a more privileged role."""
    path = tmp_path / USERS_FILENAME
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "users": [
                    {"username": "x", "password_hash": hash_password("x" * 10),
                     "role": "superuser"}
                ],
            }
        ),
        encoding="utf-8",
    )
    loaded = UserStore(path)
    loaded.load()
    assert loaded.list_users()[0].role is Role.VIEWER
    assert loaded.is_provisioned() is False


def test_public_dict_hides_the_hash(store):
    store.add_user("pawel", "dobre-haslo")
    public = store.list_users()[0].to_public_dict()
    assert "password_hash" not in public
    assert public["username"] == "pawel"
    assert public["role"] == "admin"


def test_user_from_dict_requires_credentials():
    with pytest.raises(ValueError):
        User.from_dict({"username": "x"})
    with pytest.raises(ValueError):
        User.from_dict({"password_hash": "y"})
