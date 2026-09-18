"""Tests for MQTT password change — sudoers rules & endpoint.

Validates that:
1. The sudoers asset file does NOT use the dangerous ``-c`` flag for any user.
2. The sudoers rules match the actual ``sudo`` commands built by the API endpoint.
3. The migration plan ships the corrected sudoers file.
4. The change_mqtt_password endpoint invokes the correct subprocess command.
"""

from __future__ import annotations

import os
import re
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _has_fastapi() -> bool:
    """Check if fastapi is importable."""
    try:
        import fastapi  # noqa: F401
        return True
    except ImportError:
        return False

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

_PROJECT_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, os.pardir)
)
_ASSETS_DIR = os.path.join(_PROJECT_ROOT, "boneio", "migrations", "assets")
_SUDOERS_PATH = os.path.join(_ASSETS_DIR, "sudoers", "boneio")


# ---------------------------------------------------------------------------
# 1. Sudoers asset content validation
# ---------------------------------------------------------------------------


def _read_sudoers_lines() -> list[str]:
    """Read non-empty, non-comment lines from the sudoers asset file."""
    with open(_SUDOERS_PATH) as fh:
        return [
            line.strip()
            for line in fh
            if line.strip() and not line.strip().startswith("#")
        ]


class TestSudoersAsset:
    """Validate the sudoers asset file."""

    def test_sudoers_file_exists(self):
        """Sudoers asset must exist at the expected path."""
        assert os.path.isfile(_SUDOERS_PATH), f"Missing sudoers asset: {_SUDOERS_PATH}"

    def test_no_create_flag_in_mosquitto_rules(self):
        """The ``-c`` flag wipes the password file — must NEVER be used.

        Bug context: baseline migration used ``-c -b`` for the ``boneio`` user
        which (a) did not match the API command (``-b`` only) causing a sudo
        password prompt, and (b) would destroy all other users' entries.
        """
        for line in _read_sudoers_lines():
            if "mosquitto_passwd" not in line:
                continue
            assert " -c " not in line and " -c\n" not in line, (
                f"Sudoers rule uses dangerous -c flag (creates new file, wipes others): {line}"
            )

    def test_the_mosquitto_rules_are_gone(self):
        """They took the new password on the command line.

        `mosquitto_passwd -b <file> <user> *` meant the password stood in the
        process table for as long as the command ran, readable by every local
        account. It goes to boneio-system over stdin now, so the rule that
        allowed the old shape has no reason to exist.
        """
        for line in _read_sudoers_lines():
            assert "mosquitto_passwd" not in line, (
                f"a rule still grants mosquitto_passwd directly: {line}"
            )
            assert "reload mosquitto" not in line, (
                f"a rule still grants the broker reload directly: {line}"
            )

    def test_nothing_left_here_takes_a_name_the_caller_chooses(self):
        """Except the CAN one, which the bring-up still falls back to.

        Everything else is a fixed command: a wildcard is a rule whose effect
        the caller decides, and that is what moved behind the helpers.
        """
        wildcards = [
            line for line in _read_sudoers_lines()
            if line.strip().endswith("*")
        ]
        assert all("ip link set can" in line for line in wildcards), (
            f"unexpected wildcard rules remain: {wildcards}"
        )

    def test_the_helper_rule_is_what_replaced_them(self):
        """The capability did not go away; it changed shape."""
        from pathlib import Path

        fragment = (
            Path(_SUDOERS_PATH).resolve().parent / "boneio-helpers"
        ).read_text(encoding="utf-8")
        assert "/usr/sbin/boneio-system" in fragment
        # And that helper is what now holds the account list.
        helper = (
            Path(__file__).resolve().parents[3]
            / "boneio" / "migrations" / "assets" / "helpers" / "boneio-system"
        ).read_text(encoding="utf-8")
        for account in ("boneio", "homeassistant", "mqtt"):
            assert f'"{account}"' in helper


class TestMqttSudoersMigration:
    """Validate the v1.3.3 migration plan."""

    def test_migration_plan_returns_install_file(self):
        """Migration must return an InstallFile action for sudoers."""
        from boneio.migrations.versions.v1_4_0_fix_mqtt_sudoers import plan

        actions = plan()
        assert len(actions) == 1
        action = actions[0]
        assert action.src == "sudoers/boneio"
        assert action.dst == "/etc/sudoers.d/boneio"
        assert action.mode == 0o440

    def test_migration_has_correct_version(self):
        """Migration version must be 1.3.3."""
        from boneio.migrations.versions.v1_4_0_fix_mqtt_sudoers import VERSION

        assert VERSION == "1.4.0"

    def test_migration_requires_root(self):
        """Sudoers changes require root."""
        from boneio.migrations.versions.v1_4_0_fix_mqtt_sudoers import REQUIRES_ROOT

        assert REQUIRES_ROOT is True


# ---------------------------------------------------------------------------
# 3. API endpoint subprocess command validation
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _has_fastapi(),
    reason="fastapi not installed in test environment",
)
class TestChangePasswordEndpoint:
    """Validate the change_mqtt_password endpoint builds correct commands."""

    @pytest.mark.asyncio
    async def test_the_password_never_reaches_the_command_line(self):
        """It used to: `sudo mosquitto_passwd -b <file> <user> <password>`.

        The process table is readable by every local account, so the new
        password was exposed for as long as the command ran. It goes to the
        helper over stdin now.
        """
        from boneio.webui.routes.update import (
            MqttPasswordChangeRequest,
            change_mqtt_password,
        )

        request = MqttPasswordChangeRequest(username="boneio", new_password="testpass123")

        with patch("boneio.webui.routes.update.system_ops") as ops:
            ops.mqtt_password.return_value = MagicMock(ok=True, stderr="")
            ops.mqtt_reload.return_value = MagicMock(ok=True, stderr="")

            result = await change_mqtt_password(request)

        assert result["status"] == "success"
        ops.mqtt_password.assert_called_once_with("boneio", "testpass123")


    @pytest.mark.asyncio
    async def test_rejects_short_password(self):
        """Passwords shorter than 8 characters must be rejected."""
        from boneio.webui.routes.update import change_mqtt_password, MqttPasswordChangeRequest

        request = MqttPasswordChangeRequest(username="boneio", new_password="short")
        result = await change_mqtt_password(request)

        assert result["status"] == "error"
        assert "8 characters" in result["message"]

    @pytest.mark.asyncio
    async def test_rejects_invalid_username(self):
        """Only allowed usernames (boneio, homeassistant, mqtt) are accepted."""
        from boneio.webui.routes.update import change_mqtt_password, MqttPasswordChangeRequest

        request = MqttPasswordChangeRequest(username="hacker", new_password="validpass123")
        result = await change_mqtt_password(request)

        assert result["status"] == "error"
        assert "Invalid username" in result["message"]

    @pytest.mark.asyncio
    async def test_every_allowed_user_takes_the_same_path(self):
        """No account gets a different, less careful route to the broker file."""
        from boneio.webui.routes.update import (
            MqttPasswordChangeRequest,
            change_mqtt_password,
        )

        for username in ["boneio", "homeassistant", "mqtt"]:
            request = MqttPasswordChangeRequest(
                username=username, new_password="testpass123"
            )
            with patch("boneio.webui.routes.update.system_ops") as ops:
                ops.mqtt_password.return_value = MagicMock(ok=True, stderr="")
                ops.mqtt_reload.return_value = MagicMock(ok=True, stderr="")

                await change_mqtt_password(request)

            ops.mqtt_password.assert_called_once_with(username, "testpass123")

    @pytest.mark.asyncio
    async def test_the_create_flag_is_nowhere_near_this(self):
        """`-c` creates a new file, wiping every other account out of it.

        The route no longer runs mosquitto_passwd at all; the helper does, and
        it uses the interactive form. This holds the property where it lives now.
        """
        from pathlib import Path

        helper = (
            Path(__file__).resolve().parents[3]
            / "boneio" / "migrations" / "assets" / "helpers" / "boneio-system"
        )
        source = helper.read_text(encoding="utf-8")
        assert '"-c"' not in source
        assert '"-b"' not in source, "the batch form puts the password in argv"

