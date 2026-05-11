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

    def test_all_mqtt_users_have_batch_rule(self):
        """Each allowed MQTT user must have a NOPASSWD rule with ``-b``."""
        expected_users = {"boneio", "homeassistant", "mqtt"}
        lines = _read_sudoers_lines()

        for user in expected_users:
            pattern = re.compile(
                rf"NOPASSWD:.*mosquitto_passwd\s+-b\s+/etc/mosquitto/passwd\s+{user}\s"
            )
            matches = [line for line in lines if pattern.search(line)]
            assert matches, (
                f"Missing NOPASSWD sudoers rule for MQTT user '{user}' with -b flag"
            )

    def test_sudoers_command_matches_api_invocation(self):
        """The sudo command built by the API must match a sudoers rule.

        The API builds: ``sudo mosquitto_passwd -b /etc/mosquitto/passwd <user> <pw>``
        The sudoers must allow: ``/usr/bin/mosquitto_passwd -b /etc/mosquitto/passwd <user> *``
        """
        passwd_file = "/etc/mosquitto/passwd"
        allowed_users = ["boneio", "homeassistant", "mqtt"]
        lines = _read_sudoers_lines()

        for username in allowed_users:
            # This is the exact pattern the API will invoke
            expected_cmd_fragment = f"mosquitto_passwd -b {passwd_file} {username}"
            matching = [line for line in lines if expected_cmd_fragment in line]
            assert matching, (
                f"API invokes 'sudo mosquitto_passwd -b {passwd_file} {username} <pw>' "
                f"but no matching sudoers rule found"
            )

    def test_sudoers_allows_mosquitto_reload(self):
        """Sudoers must allow reloading mosquitto after password change."""
        lines = _read_sudoers_lines()
        assert any(
            "systemctl reload mosquitto" in line for line in lines
        ), "Missing NOPASSWD rule for 'systemctl reload mosquitto'"


# ---------------------------------------------------------------------------
# 2. Migration plan validation
# ---------------------------------------------------------------------------


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
    async def test_calls_mosquitto_passwd_without_create_flag(self):
        """The endpoint must use ``-b`` (batch) NOT ``-c -b`` (create)."""
        from boneio.webui.routes.update import change_mqtt_password, MqttPasswordChangeRequest

        request = MqttPasswordChangeRequest(username="boneio", new_password="testpass123")

        with patch("boneio.webui.routes.update.subprocess") as mock_subprocess:
            # Mock which to return success
            mock_which = MagicMock()
            mock_which.returncode = 0
            mock_subprocess.run.side_effect = [mock_which, MagicMock(returncode=0), MagicMock(returncode=0)]
            mock_subprocess.CalledProcessError = subprocess.CalledProcessError

            result = await change_mqtt_password(request)

            # Second call is the actual mosquitto_passwd command
            passwd_call = mock_subprocess.run.call_args_list[1]
            cmd = passwd_call[0][0]  # First positional arg is the command list

            assert cmd[0] == "sudo"
            assert cmd[1] == "mosquitto_passwd"
            assert "-b" in cmd
            assert "-c" not in cmd, "Must not use -c flag (creates new file, wipes other users)"
            assert cmd[3] == "/etc/mosquitto/passwd"
            assert cmd[4] == "boneio"

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
    async def test_all_allowed_users_use_same_command_pattern(self):
        """All three allowed users must use the same ``-b`` command pattern."""
        from boneio.webui.routes.update import change_mqtt_password, MqttPasswordChangeRequest

        for username in ["boneio", "homeassistant", "mqtt"]:
            request = MqttPasswordChangeRequest(username=username, new_password="testpass123")

            with patch("boneio.webui.routes.update.subprocess") as mock_subprocess:
                mock_which = MagicMock()
                mock_which.returncode = 0
                mock_subprocess.run.side_effect = [
                    mock_which,
                    MagicMock(returncode=0),
                    MagicMock(returncode=0),
                ]
                mock_subprocess.CalledProcessError = subprocess.CalledProcessError

                await change_mqtt_password(request)

                passwd_call = mock_subprocess.run.call_args_list[1]
                cmd = passwd_call[0][0]
                assert cmd == [
                    "sudo", "mosquitto_passwd", "-b",
                    "/etc/mosquitto/passwd", username, "testpass123",
                ], f"Wrong command for user '{username}': {cmd}"
