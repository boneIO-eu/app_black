"""Tests for restricting the MQTT password database (F-11)."""

from __future__ import annotations

import re
from pathlib import Path

from boneio.migrations.actions import SetFilePermissions
from boneio.migrations.versions import v1_6_1_mosquitto_passwd_perms as migration

REPO_ROOT = Path(__file__).resolve().parents[3]
IMAGE_SCRIPT = REPO_ROOT.parent / "black_debian_images/scripts/setup_boneio.sh"
HELPER = REPO_ROOT / "boneio/migrations/bootstrap/boneio-migrate"


# ----------------------------------------------------------------- migration


def test_the_password_file_stops_being_world_readable():
    """It shipped 0644 and was found at 704 — rwx---r-- — so every local
    account could take the hashes for an offline crack."""
    perms = [a for a in migration.plan() if isinstance(a, SetFilePermissions)]
    assert perms, "migration sets no permissions"
    action = perms[0]
    assert action.path == "/etc/mosquitto/passwd"
    assert action.mode == 0o640
    assert action.owner == "root"
    assert action.group == "mosquitto"


def test_the_broker_can_still_read_it():
    """mosquitto runs as its own user, so the group has to be mosquitto or the
    fix would take the broker down with the exposure."""
    action = next(a for a in migration.plan() if isinstance(a, SetFilePermissions))
    assert action.group == "mosquitto"
    assert action.mode & 0o040, "group read bit missing"


def test_no_other_account_is_left_any_access():
    action = next(a for a in migration.plan() if isinstance(a, SetFilePermissions))
    assert action.mode & 0o007 == 0, "world still has access"


def test_the_contents_are_not_replaced():
    """The passwords are the device's own; installing a file over them would
    wipe whatever the owner has set."""
    assert not any(hasattr(a, "src") for a in migration.plan())


# ------------------------------------------------------------------- action


def test_the_action_is_narrow():
    """Permissions of one named path — not a general way to run commands as
    root, which is what a migration framework must not grow."""
    payload = SetFilePermissions(path="/etc/x", mode=0o600).to_dict()
    assert set(payload) == {"action", "path", "mode", "owner", "group"}


def test_the_helper_accepts_the_action():
    """The plan is applied by the privileged helper, which refuses anything
    not on its whitelist."""
    source = HELPER.read_text(encoding="utf-8")
    assert '"set_file_permissions",' in source
    assert "def handle_set_file_permissions" in source


def test_the_helper_refuses_a_symlink():
    """Following one would let a writable path redirect the chown somewhere
    else entirely."""
    assert "is_symlink" in HELPER.read_text(encoding="utf-8")


# -------------------------------------------------------------- image script


def test_the_image_sets_the_permissions_after_writing_the_passwords():
    """mosquitto_passwd rewrites the file, so permissions set before it would
    be replaced by whatever it chooses."""
    if not IMAGE_SCRIPT.exists():
        import pytest

        pytest.skip("image repository not checked out next to this one")

    text = IMAGE_SCRIPT.read_text(encoding="utf-8")
    last_write = max(m.end() for m in re.finditer(r"mosquitto_passwd -b", text))
    chmod_at = text.index("chmod 0640 /etc/mosquitto/passwd")
    assert chmod_at > last_write


def test_the_image_no_longer_ships_it_world_readable():
    if not IMAGE_SCRIPT.exists():
        import pytest

        pytest.skip("image repository not checked out next to this one")

    text = IMAGE_SCRIPT.read_text(encoding="utf-8")
    assert "chmod 0644 /etc/mosquitto/passwd" not in text
    assert "chown root:mosquitto /etc/mosquitto/passwd" in text
