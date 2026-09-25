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



# ---------------------------------------------------------------------------
# 4. Adopting the new password here, so the device stays on its own broker
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _has_fastapi(),
    reason="fastapi not installed in test environment",
)
class TestAdoptingTheNewPassword:
    """The account the panel changes is the account boneIO connects with.

    Changing it in the broker and nowhere else took the device off its own
    broker until somebody edited config.yaml and restarted — which is what
    testers reported as the password change not working.
    """

    @staticmethod
    def _device(tmp_path, config_text: str, host: str = "localhost", username: str = "boneio"):
        """A manager whose configuration is a real file on disk."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_text, encoding="utf-8")

        manager = MagicMock()
        manager.config_helper.config_file_path = str(config_file)
        manager.config_helper.get_config.return_value = {
            "mqtt": {"host": host, "username": username, "password": "boneio123"}
        }
        manager.reload_config = AsyncMock(return_value={"status": "success"})
        return manager, config_file

    @staticmethod
    def _request(username: str = "boneio", **kwargs):
        from boneio.webui.routes.update import MqttPasswordChangeRequest

        return MqttPasswordChangeRequest(
            username=username, new_password="nowe-haslo-123", **kwargs
        )

    @pytest.mark.asyncio
    async def test_the_new_password_lands_in_the_configuration(self, tmp_path):
        from boneio.webui.routes.update import change_mqtt_password

        manager, config_file = self._device(
            tmp_path, "mqtt:\n  host: localhost\n  password: boneio123\n"
        )

        with patch("boneio.webui.routes.update.system_ops") as ops:
            ops.mqtt_password.return_value = MagicMock(ok=True, stderr="")
            ops.mqtt_reload.return_value = MagicMock(ok=True, stderr="")
            result = await change_mqtt_password(self._request(update_config=True), manager)

        assert result["status"] == "success"
        # Into secrets.yaml, not the config: a password in config.yaml goes
        # with every backup (migration v7 moved the old ones out).
        assert result["config"] == {"status": "adopted", "written_to": "secret"}
        assert "password: !secret mqtt_password" in config_file.read_text()
        assert 'mqtt_password: "nowe-haslo-123"' in (tmp_path / "secrets.yaml").read_text()

    @pytest.mark.asyncio
    async def test_the_device_reconnects_instead_of_waiting_for_a_restart(self, tmp_path):
        from boneio.webui.routes.update import change_mqtt_password

        manager, _ = self._device(
            tmp_path, "mqtt:\n  host: localhost\n  password: boneio123\n"
        )

        with patch("boneio.webui.routes.update.system_ops") as ops:
            ops.mqtt_password.return_value = MagicMock(ok=True, stderr="")
            ops.mqtt_reload.return_value = MagicMock(ok=True, stderr="")
            await change_mqtt_password(self._request(update_config=True), manager)

        manager.reload_config.assert_awaited_once_with(reload_sections=["mqtt"])

    @pytest.mark.asyncio
    async def test_a_secret_reference_is_followed_instead_of_overwritten(self, tmp_path):
        """`password: !secret mqtt_pass` usually means config.yaml is somewhere
        the password must not be — a git repository, a support bundle."""
        from boneio.webui.routes.update import change_mqtt_password

        manager, config_file = self._device(
            tmp_path, "mqtt:\n  host: localhost\n  password: !secret mqtt_pass\n"
        )
        (tmp_path / "secrets.yaml").write_text("mqtt_pass: boneio123\n", encoding="utf-8")

        with patch("boneio.webui.routes.update.system_ops") as ops:
            ops.mqtt_password.return_value = MagicMock(ok=True, stderr="")
            ops.mqtt_reload.return_value = MagicMock(ok=True, stderr="")
            result = await change_mqtt_password(self._request(update_config=True), manager)

        assert result["config"] == {"status": "adopted", "written_to": "secret"}
        assert "!secret mqtt_pass" in config_file.read_text()
        assert "nowe-haslo-123" not in config_file.read_text()
        assert "nowe-haslo-123" in (tmp_path / "secrets.yaml").read_text()

    @pytest.mark.asyncio
    async def test_a_remote_broker_leaves_the_configuration_alone(self, tmp_path):
        """Point boneIO at the broker in Home Assistant and the accounts in the
        local password file are not the ones it uses."""
        from boneio.webui.routes.update import change_mqtt_password

        manager, config_file = self._device(
            tmp_path,
            "mqtt:\n  host: 192.168.1.50\n  password: boneio123\n",
            host="192.168.1.50",
        )
        before = config_file.read_text()

        with patch("boneio.webui.routes.update.system_ops") as ops:
            ops.mqtt_password.return_value = MagicMock(ok=True, stderr="")
            ops.mqtt_reload.return_value = MagicMock(ok=True, stderr="")
            result = await change_mqtt_password(self._request(update_config=True), manager)

        assert result["config"] == {"status": "skipped", "reason": "remote_broker"}
        assert config_file.read_text() == before
        manager.reload_config.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_another_account_leaves_the_configuration_alone(self, tmp_path):
        """The broker also carries accounts for Home Assistant and whatever
        else; changing those says nothing about this device's own."""
        from boneio.webui.routes.update import change_mqtt_password

        manager, config_file = self._device(
            tmp_path, "mqtt:\n  host: localhost\n  password: boneio123\n"
        )
        before = config_file.read_text()

        with patch("boneio.webui.routes.update.system_ops") as ops:
            ops.mqtt_password.return_value = MagicMock(ok=True, stderr="")
            ops.mqtt_reload.return_value = MagicMock(ok=True, stderr="")
            result = await change_mqtt_password(
                self._request(username="homeassistant", update_config=True), manager
            )

        assert result["config"] == {"status": "skipped", "reason": "other_account"}
        assert config_file.read_text() == before

    @pytest.mark.asyncio
    async def test_without_the_option_nothing_here_is_touched(self, tmp_path):
        """The checkbox is the whole authorisation to edit somebody's file."""
        from boneio.webui.routes.update import change_mqtt_password

        manager, config_file = self._device(
            tmp_path, "mqtt:\n  host: localhost\n  password: boneio123\n"
        )
        before = config_file.read_text()

        with patch("boneio.webui.routes.update.system_ops") as ops:
            ops.mqtt_password.return_value = MagicMock(ok=True, stderr="")
            ops.mqtt_reload.return_value = MagicMock(ok=True, stderr="")
            result = await change_mqtt_password(self._request(), manager)

        assert "config" not in result
        assert config_file.read_text() == before
        manager.reload_config.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_failed_reconnect_is_reported_not_hidden(self, tmp_path):
        """The password is already changed in the broker by then. Saying the
        whole thing failed would be as wrong as saying it worked."""
        from boneio.webui.routes.update import change_mqtt_password

        manager, _ = self._device(
            tmp_path, "mqtt:\n  host: localhost\n  password: boneio123\n"
        )
        manager.reload_config.side_effect = RuntimeError("bus is gone")

        with patch("boneio.webui.routes.update.system_ops") as ops:
            ops.mqtt_password.return_value = MagicMock(ok=True, stderr="")
            ops.mqtt_reload.return_value = MagicMock(ok=True, stderr="")
            result = await change_mqtt_password(self._request(update_config=True), manager)

        assert result["status"] == "success"
        assert result["config"]["status"] == "written"

    @pytest.mark.asyncio
    async def test_the_include_every_controller_ships_with_is_followed(self, tmp_path):
        """`mqtt: !include mqtt.yaml` is the layout on every shipped device,
        and that file is the per-device one the broker password lives in.

        Writing to config.yaml instead would create a second mqtt section
        beside the include — the password stored twice, in two places, and the
        device reading neither reliably."""
        from boneio.webui.routes.update import change_mqtt_password

        manager, config_file = self._device(tmp_path, "mqtt: !include mqtt.yaml\n")
        included = tmp_path / "mqtt.yaml"
        included.write_text(
            "host: localhost\nusername: boneio\npassword: boneio123\n", encoding="utf-8"
        )

        with patch("boneio.webui.routes.update.system_ops") as ops:
            ops.mqtt_password.return_value = MagicMock(ok=True, stderr="")
            ops.mqtt_reload.return_value = MagicMock(ok=True, stderr="")
            result = await change_mqtt_password(self._request(update_config=True), manager)

        assert result["config"] == {"status": "adopted", "written_to": "secret"}
        assert "password: !secret mqtt_password" in included.read_text()
        assert 'mqtt_password: "nowe-haslo-123"' in (tmp_path / "secrets.yaml").read_text()
        assert config_file.read_text() == "mqtt: !include mqtt.yaml\n"

    @pytest.mark.asyncio
    async def test_a_secret_inside_the_included_file_is_followed_too(self, tmp_path):
        """BoneIOLoader resolves a !secret against the directory of the file
        that names it, so the write has to land in the same secrets.yaml."""
        from boneio.webui.routes.update import change_mqtt_password

        manager, _ = self._device(tmp_path, "mqtt: !include mqtt.yaml\n")
        (tmp_path / "mqtt.yaml").write_text(
            "host: localhost\npassword: !secret mqtt_pass\n", encoding="utf-8"
        )
        (tmp_path / "secrets.yaml").write_text("mqtt_pass: boneio123\n", encoding="utf-8")

        with patch("boneio.webui.routes.update.system_ops") as ops:
            ops.mqtt_password.return_value = MagicMock(ok=True, stderr="")
            ops.mqtt_reload.return_value = MagicMock(ok=True, stderr="")
            result = await change_mqtt_password(self._request(update_config=True), manager)

        assert result["config"] == {"status": "adopted", "written_to": "secret"}
        assert "!secret mqtt_pass" in (tmp_path / "mqtt.yaml").read_text()
        assert "nowe-haslo-123" in (tmp_path / "secrets.yaml").read_text()

    @pytest.mark.asyncio
    async def test_an_include_naming_a_file_that_is_not_there_is_refused(self, tmp_path):
        """Creating it would invent a section out of a typo, and leave the
        device offline just the same."""
        from boneio.webui.routes.update import change_mqtt_password

        manager, config_file = self._device(tmp_path, "mqtt: !include mqtt.yaml\n")
        before = config_file.read_text()

        with patch("boneio.webui.routes.update.system_ops") as ops:
            ops.mqtt_password.return_value = MagicMock(ok=True, stderr="")
            ops.mqtt_reload.return_value = MagicMock(ok=True, stderr="")
            result = await change_mqtt_password(self._request(update_config=True), manager)

        assert result["status"] == "success"
        assert result["config"]["status"] == "error"
        assert config_file.read_text() == before
        assert not (tmp_path / "mqtt.yaml").exists()
