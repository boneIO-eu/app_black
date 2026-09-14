"""Tests for `boneio accounts` and for picking up out-of-process edits."""

from __future__ import annotations

import argparse
import time
from unittest.mock import patch

import pytest

from boneio.core.auth.cli import run_accounts_command
from boneio.core.auth.models import Role
from boneio.core.auth.store import USERS_FILENAME, UserStore


@pytest.fixture
def config(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("web:\n  port: 8090\n", encoding="utf-8")
    return path


def _args(config, action, **kw):
    return argparse.Namespace(config=str(config), accounts_action=action, **kw)


def _run(config, action, password=None, **kw):
    """Run a subcommand, answering the password prompts with `password`."""
    with patch("boneio.core.auth.cli.getpass.getpass", return_value=password):
        return run_accounts_command(_args(config, action, **kw))


# ----------------------------------------------------------------------- list


def test_list_on_a_fresh_device(config, capsys):
    assert _run(config, "list") == 0
    assert "No accounts yet" in capsys.readouterr().out


def test_list_shows_roles(config, capsys):
    store = UserStore.for_config_file(config)
    store.add_user("pawel", "haslo-admina", Role.ADMIN)
    store.add_user("gosc", "haslo-goscia", Role.VIEWER)

    assert _run(config, "list") == 0
    out = capsys.readouterr().out
    assert "pawel" in out and "admin" in out
    assert "gosc" in out and "viewer" in out


def test_missing_config_is_an_error(tmp_path, capsys):
    assert _run(tmp_path / "nope.yaml", "list") == 1
    assert "No config file" in capsys.readouterr().err


# ------------------------------------------------------------------------ add


def test_add_creates_an_admin(config):
    assert _run(config, "add", password="dobre-haslo", username="pawel", role="admin") == 0

    store = UserStore.for_config_file(config)
    store.load()
    user = store.verify_credentials("pawel", "dobre-haslo")
    assert user is not None
    assert user.role is Role.ADMIN


def test_add_defaults_to_viewer_via_the_parser(config):
    assert _run(config, "add", password="dobre-haslo", username="gosc", role="viewer") == 0
    store = UserStore.for_config_file(config)
    store.load()
    assert store.get_user("gosc").role is Role.VIEWER


def test_add_rejects_a_short_password(config, capsys):
    assert _run(config, "add", password="krotkie", username="x", role="admin") == 1
    assert "Rejected" in capsys.readouterr().err
    assert not (config.parent / USERS_FILENAME).exists()


def test_add_aborts_when_the_repeat_differs(config, capsys):
    with patch(
        "boneio.core.auth.cli.getpass.getpass",
        side_effect=["dobre-haslo", "cos-innego"],
    ):
        rc = run_accounts_command(_args(config, "add", username="x", role="admin"))
    assert rc == 1
    assert "do not match" in capsys.readouterr().err


def test_add_aborts_on_an_empty_password(config):
    assert _run(config, "add", password="", username="x", role="admin") == 1


def test_password_is_never_taken_from_arguments(config):
    """A password in argv is visible in ps and lands in shell history."""
    import boneio.core.auth.cli as cli_module

    parser = argparse.ArgumentParser()
    cli_module.add_accounts_parser(parser.add_subparsers(dest="action"))
    with pytest.raises(SystemExit):
        parser.parse_args(["accounts", "add", "pawel", "--password", "sekret"])


# ---------------------------------------------------------------------- reset


def test_reset_changes_the_password(config):
    store = UserStore.for_config_file(config)
    store.add_user("pawel", "stare-haslo", Role.ADMIN)

    assert _run(config, "reset", password="nowe-haslo-123", username="pawel") == 0

    fresh = UserStore.for_config_file(config)
    fresh.load()
    assert fresh.verify_credentials("pawel", "nowe-haslo-123") is not None
    assert fresh.verify_credentials("pawel", "stare-haslo") is None


def test_reset_keeps_the_role(config):
    store = UserStore.for_config_file(config)
    store.add_user("gosc", "stare-haslo", Role.VIEWER)
    _run(config, "reset", password="nowe-haslo-123", username="gosc")
    fresh = UserStore.for_config_file(config)
    fresh.load()
    assert fresh.get_user("gosc").role is Role.VIEWER


def test_reset_on_an_unknown_account(config, capsys):
    assert _run(config, "reset", password="nowe-haslo-123", username="nikt") == 1
    assert "No such account" in capsys.readouterr().err


# --------------------------------------------------------------------- delete


def test_delete_removes_an_account(config):
    store = UserStore.for_config_file(config)
    store.add_user("pawel", "haslo-admina", Role.ADMIN)
    store.add_user("gosc", "haslo-goscia", Role.VIEWER)

    assert _run(config, "delete", username="gosc") == 0
    fresh = UserStore.for_config_file(config)
    fresh.load()
    assert fresh.get_user("gosc") is None


def test_delete_refuses_the_last_admin(config, capsys):
    store = UserStore.for_config_file(config)
    store.add_user("pawel", "haslo-admina", Role.ADMIN)

    assert _run(config, "delete", username="pawel") == 1
    assert "last admin" in capsys.readouterr().err


# ------------------------------------------- the running service sees changes


def test_running_store_picks_up_an_external_reset(config):
    """The web server holds the store in memory, so a CLI reset would not take
    effect until a restart — and restarting a controller to recover a password
    would interrupt whatever it is automating."""
    running = UserStore.for_config_file(config)
    running.add_user("pawel", "stare-haslo", Role.ADMIN)
    assert running.verify_credentials("pawel", "stare-haslo") is not None

    time.sleep(0.01)  # ensure a distinct mtime
    _run(config, "reset", password="nowe-haslo-123", username="pawel")

    assert running.verify_credentials("pawel", "nowe-haslo-123") is not None
    assert running.verify_credentials("pawel", "stare-haslo") is None


def test_running_store_picks_up_a_first_admin(config):
    """An unprovisioned device that gets its admin from the CLI must close its
    API without waiting for a restart."""
    running = UserStore.for_config_file(config)
    running.load()
    assert running.is_provisioned() is False

    time.sleep(0.01)
    _run(config, "add", password="dobre-haslo", username="pawel", role="admin")

    assert running.is_provisioned() is True


def test_reload_does_not_undo_our_own_writes(config):
    """The store must not treat its own save as an external change."""
    store = UserStore.for_config_file(config)
    store.add_user("pawel", "haslo-admina", Role.ADMIN)
    store.add_user("gosc", "haslo-goscia", Role.VIEWER)
    assert {u.username for u in store.list_users()} == {"pawel", "gosc"}
