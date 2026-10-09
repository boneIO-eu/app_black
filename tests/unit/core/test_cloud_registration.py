"""Unit tests for CloudRegistration module."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from boneio.core.cloud.registration import CloudRegistration, CERT_FILE


@pytest.fixture
def cloud_reg():
    """Create a CloudRegistration instance for testing."""
    return CloudRegistration(
        serial_number="blkf8dc18",
        local_ip="192.168.1.50",
        master_secret="testsecret",
        enabled=True,
    )


@pytest.mark.asyncio
async def test_cert_needs_refresh_with_extra_spaces(cloud_reg, tmp_path):
    """Test openssl date parsing when date string contains double spaces."""
    cert_file = tmp_path / "fullchain.pem"
    cert_file.write_text("fake cert content")

    mock_openssl_out = "notAfter=Oct  9 15:02:27 2099 GMT\n"

    with patch("boneio.core.cloud.registration.CERT_FILE", cert_file):
        with patch("boneio.core.cloud.registration.KEY_FILE", cert_file):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout=mock_openssl_out)

                needs_refresh = await cloud_reg._cert_needs_refresh()
                # Should successfully parse date (Oct 9 2099 is far in future) -> False
                assert needs_refresh is False


class TestCaddyCertMatchesDisk:
    """Tests for _caddy_cert_matches_disk Caddy TLS mismatch detection."""

    @pytest.mark.asyncio
    async def test_returns_true_when_no_cert_on_disk(self, cloud_reg, tmp_path):
        """If cert files don't exist, nothing to compare — return True."""
        cloud_reg._domain = "test.boneio.app"
        missing = tmp_path / "missing.pem"
        with (
            patch("boneio.core.cloud.registration.CERT_FILE", missing),
            patch("boneio.core.cloud.registration.KEY_FILE", missing),
        ):
            result = await cloud_reg._caddy_cert_matches_disk()
            assert result is True

    @pytest.mark.asyncio
    async def test_returns_true_when_domain_unknown(self, cloud_reg, tmp_path):
        """If domain is not yet known, skip the check — return True."""
        cloud_reg._domain = None
        cert = tmp_path / "fullchain.pem"
        key = tmp_path / "privkey.pem"
        cert.write_text("cert")
        key.write_text("key")

        with (
            patch("boneio.core.cloud.registration.CERT_FILE", cert),
            patch("boneio.core.cloud.registration.KEY_FILE", key),
        ):
            result = await cloud_reg._caddy_cert_matches_disk()
            assert result is True

    @pytest.mark.asyncio
    async def test_returns_true_when_disk_serial_unreadable(self, cloud_reg, tmp_path):
        """If openssl can't read the disk cert, assume OK (don't trigger restart)."""
        cloud_reg._domain = "test.boneio.app"
        cert = tmp_path / "fullchain.pem"
        key = tmp_path / "privkey.pem"
        cert.write_text("bad")
        key.write_text("bad")

        with (
            patch("boneio.core.cloud.registration.CERT_FILE", cert),
            patch("boneio.core.cloud.registration.KEY_FILE", key),
            patch.object(cloud_reg, "_get_cert_serial_from_file", return_value=None),
        ):
            result = await cloud_reg._caddy_cert_matches_disk()
            assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_caddy_unreachable(self, cloud_reg, tmp_path):
        """If Caddy TLS is unreachable, return False (trigger restart)."""
        cloud_reg._domain = "test.boneio.app"
        cert = tmp_path / "fullchain.pem"
        key = tmp_path / "privkey.pem"
        cert.write_text("cert")
        key.write_text("key")

        with (
            patch("boneio.core.cloud.registration.CERT_FILE", cert),
            patch("boneio.core.cloud.registration.KEY_FILE", key),
            patch.object(
                cloud_reg, "_get_cert_serial_from_file", return_value="AABB1122"
            ),
            patch.object(cloud_reg, "_get_caddy_live_serial", return_value=None),
        ):
            result = await cloud_reg._caddy_cert_matches_disk()
            assert result is False

    @pytest.mark.asyncio
    async def test_returns_true_when_serials_match(self, cloud_reg, tmp_path):
        """Same serial on disk and live — certs match."""
        cloud_reg._domain = "test.boneio.app"
        cert = tmp_path / "fullchain.pem"
        key = tmp_path / "privkey.pem"
        cert.write_text("cert")
        key.write_text("key")

        with (
            patch("boneio.core.cloud.registration.CERT_FILE", cert),
            patch("boneio.core.cloud.registration.KEY_FILE", key),
            patch.object(
                cloud_reg, "_get_cert_serial_from_file", return_value="AABB1122"
            ),
            patch.object(
                cloud_reg, "_get_caddy_live_serial", return_value="AABB1122"
            ),
        ):
            result = await cloud_reg._caddy_cert_matches_disk()
            assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_serials_differ(self, cloud_reg, tmp_path):
        """Different serial on disk vs live — mismatch, restart needed."""
        cloud_reg._domain = "test.boneio.app"
        cert = tmp_path / "fullchain.pem"
        key = tmp_path / "privkey.pem"
        cert.write_text("cert")
        key.write_text("key")

        with (
            patch("boneio.core.cloud.registration.CERT_FILE", cert),
            patch("boneio.core.cloud.registration.KEY_FILE", key),
            patch.object(
                cloud_reg, "_get_cert_serial_from_file", return_value="AABB1122"
            ),
            patch.object(
                cloud_reg, "_get_caddy_live_serial", return_value="CCDD3344"
            ),
        ):
            result = await cloud_reg._caddy_cert_matches_disk()
            assert result is False


class TestRegistrationLoopCaddyMismatch:
    """Test that registration loop restarts Caddy on cert mismatch."""

    @pytest.mark.asyncio
    async def test_restarts_caddy_on_cert_mismatch(self, cloud_reg):
        """When disk cert is OK but Caddy serves stale cert, Caddy is restarted."""
        with (
            patch.object(cloud_reg, "_register_dns", return_value=True),
            patch.object(cloud_reg, "_cert_exists", return_value=True),
            patch.object(cloud_reg, "_cert_needs_refresh", return_value=False),
            patch.object(cloud_reg, "is_cloud_config_active", return_value=True),
            patch.object(
                cloud_reg, "_caddy_cert_matches_disk", return_value=False
            ) as mock_match,
            patch.object(
                cloud_reg, "_recreate_caddy", return_value=True
            ) as mock_recreate,
        ):
            cloud_reg._domain = "test.boneio.app"

            # Run one iteration of the loop
            with patch("asyncio.sleep", side_effect=asyncio.CancelledError):
                with pytest.raises(asyncio.CancelledError):
                    await cloud_reg._registration_loop()

            mock_match.assert_called_once()
            mock_recreate.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_restart_when_certs_match(self, cloud_reg):
        """When disk and Caddy certs match, no restart is triggered."""
        with (
            patch.object(cloud_reg, "_register_dns", return_value=True),
            patch.object(cloud_reg, "_cert_exists", return_value=True),
            patch.object(cloud_reg, "_cert_needs_refresh", return_value=False),
            patch.object(cloud_reg, "is_cloud_config_active", return_value=True),
            patch.object(
                cloud_reg, "_caddy_cert_matches_disk", return_value=True
            ),
            patch.object(
                cloud_reg, "_recreate_caddy", return_value=True
            ) as mock_recreate,
        ):
            cloud_reg._domain = "test.boneio.app"

            with patch("asyncio.sleep", side_effect=asyncio.CancelledError):
                with pytest.raises(asyncio.CancelledError):
                    await cloud_reg._registration_loop()

            mock_recreate.assert_not_called()


def _ok():
    return MagicMock(ok=True, stderr="", stdout="")


class TestOneCaddyStartPerTemplateSwap:
    """With ``web.expose: proxy`` Caddy is the only way into the panel.

    Switching the template used to run ``up`` and then ``restart``: ``up``
    already recreated the container from the new definition, so the restart
    took the panel down a second time — it came back, then died again.
    """

    @pytest.mark.asyncio
    async def test_switching_to_cloud_starts_caddy_once(self, cloud_reg):
        with (
            patch("boneio.core.cloud.registration.containers") as containers,
            patch.object(cloud_reg, "_ensure_cloud_script"),
            patch.object(cloud_reg, "_check_compose_ownership", return_value=True),
            patch.object(cloud_reg, "is_cloud_config_active", return_value=False),
        ):
            containers.apply_cloud_template.return_value = _ok()
            containers.start_caddy.return_value = _ok()

            assert await cloud_reg._switch_to_cloud_config() is True

            containers.start_caddy.assert_called_once()
            containers.restart_caddy.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("to_cloud", [True, False])
    async def test_the_packaged_caddy_is_not_started_again(self, cloud_reg, to_cloud):
        """The helper's template verb has reloaded it; a start costs seconds of
        a request the panel waits on (16 s turning cloud off on a BeagleBone)."""
        with (
            patch("boneio.core.cloud.registration.containers") as containers,
            patch.object(cloud_reg, "_ensure_cloud_script"),
            patch.object(cloud_reg, "_check_compose_ownership", return_value=True),
            patch.object(cloud_reg, "is_cloud_config_active", return_value=not to_cloud),
        ):
            containers.proxy_mode.return_value = "native"
            containers.apply_cloud_template.return_value = _ok()
            containers.remove_cloud_template.return_value = _ok()

            if to_cloud:
                assert await cloud_reg._switch_to_cloud_config() is True
            else:
                assert await cloud_reg._restore_local_config() is True

            containers.start_caddy.assert_not_called()
            containers.restart_caddy.assert_not_called()

    @pytest.mark.asyncio
    async def test_an_already_local_packaged_caddy_is_left_alone(self, cloud_reg):
        """Turning cloud off in settings: /cloud/disable restored it first."""
        with (
            patch("boneio.core.cloud.registration.containers") as containers,
            patch.object(cloud_reg, "_check_compose_ownership", return_value=True),
            patch.object(cloud_reg, "is_cloud_config_active", return_value=False),
        ):
            containers.proxy_mode.return_value = "native"
            assert await cloud_reg._restore_local_config() is True
            containers.start_caddy.assert_not_called()
            containers.restart_caddy.assert_not_called()

    @pytest.mark.asyncio
    async def test_restoring_the_local_template_starts_caddy_once(self, cloud_reg):
        with (
            patch("boneio.core.cloud.registration.containers") as containers,
            patch.object(cloud_reg, "_check_compose_ownership", return_value=True),
            patch.object(cloud_reg, "is_cloud_config_active", return_value=True),
        ):
            containers.remove_cloud_template.return_value = _ok()
            containers.start_caddy.return_value = _ok()

            assert await cloud_reg._restore_local_config() is True

            containers.start_caddy.assert_called_once()
            containers.restart_caddy.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_refreshed_certificate_still_restarts(self, cloud_reg):
        # Same compose file: ``up`` leaves the container running with the
        # certificate it read at start, so only the restart picks up the new one.
        with patch("boneio.core.cloud.registration.containers") as containers:
            containers.start_caddy.return_value = _ok()
            containers.restart_caddy.return_value = _ok()

            assert await cloud_reg._recreate_caddy() is True

            containers.restart_caddy.assert_called_once()


class TestServing:
    """``serving`` is what the panel waits for before sending anybody away."""

    @pytest.mark.asyncio
    async def test_not_serving_while_caddy_is_being_recreated(self, cloud_reg):
        cloud_reg._domain = "blkf8dc18.black.boneio.app"
        seen: list[bool] = []

        def start_caddy():
            seen.append(cloud_reg.serving)
            return _ok()

        with (
            patch("boneio.core.cloud.registration.containers") as containers,
            patch.object(cloud_reg, "_ensure_cloud_script"),
            patch.object(cloud_reg, "_check_compose_ownership", return_value=True),
            # The template is already the cloud one by the time Caddy restarts.
            patch.object(cloud_reg, "is_cloud_config_active", side_effect=[False, True, True]),
        ):
            containers.apply_cloud_template.return_value = _ok()
            containers.start_caddy.side_effect = start_caddy

            await cloud_reg._switch_to_cloud_config()

            assert seen == [False]
            assert cloud_reg.serving is True

    def test_not_serving_before_the_name_is_registered(self, cloud_reg):
        with patch.object(cloud_reg, "is_cloud_config_active", return_value=True):
            assert cloud_reg.serving is False

    @pytest.mark.asyncio
    async def test_a_failed_switch_does_not_stay_switching(self, cloud_reg):
        cloud_reg._domain = "blkf8dc18.black.boneio.app"
        with (
            patch("boneio.core.cloud.registration.containers") as containers,
            patch.object(cloud_reg, "_ensure_cloud_script"),
            patch.object(cloud_reg, "_check_compose_ownership", return_value=True),
            patch.object(cloud_reg, "is_cloud_config_active", return_value=False),
        ):
            containers.apply_cloud_template.side_effect = RuntimeError("helper gone")

            with pytest.raises(RuntimeError):
                await cloud_reg._switch_to_cloud_config()

            assert cloud_reg._switching is False


class TestNativeMode:
    """The packaged Caddy has no compose file or init script: a marker says it all."""

    @pytest.fixture
    def native(self, tmp_path, monkeypatch):
        from boneio.core import containers as real

        marker = tmp_path / "proxy-cloud"
        monkeypatch.setattr(real, "proxy_mode", lambda: "native")
        monkeypatch.setattr(real, "CLOUD_MARKER", marker)
        return marker

    def test_the_marker_is_the_template(self, cloud_reg, native):
        assert cloud_reg.is_cloud_config_active() is False
        native.write_text("")
        assert cloud_reg.is_cloud_config_active() is True

    def test_no_init_script_is_deployed(self, cloud_reg, native, tmp_path):
        with patch("boneio.core.cloud.registration.CADDY_CONFIG_DIR", tmp_path):
            cloud_reg._ensure_cloud_script()
        assert not (tmp_path / "init-certs-cloud.sh").exists()

    def test_container_mode_still_deploys_the_script(self, cloud_reg, tmp_path):
        with (
            patch("boneio.core.cloud.registration.containers.proxy_mode", return_value="container"),
            patch("boneio.core.cloud.registration.CADDY_CONFIG_DIR", tmp_path),
        ):
            cloud_reg._ensure_cloud_script()
        assert (tmp_path / "init-certs-cloud.sh").exists()

    @pytest.mark.asyncio
    async def test_switching_asks_the_helper(self, cloud_reg, native):
        with patch.object(cloud_reg, "_check_compose_ownership", return_value=True):
            with patch("boneio.core.containers.apply_cloud_template") as apply, patch(
                "boneio.core.containers.start_caddy"
            ) as start:
                apply.return_value = _ok()
                start.return_value = _ok()
                assert await cloud_reg._switch_to_cloud_config() is True
                apply.assert_called_once()

    def test_a_missing_compose_file_is_not_a_warning(self, cloud_reg, native):
        assert cloud_reg.is_compose_writable is True

    @pytest.mark.asyncio
    async def test_restoring_asks_the_helper(self, cloud_reg, native):
        native.write_text("")
        with patch.object(cloud_reg, "_check_compose_ownership", return_value=True):
            with patch("boneio.core.containers.remove_cloud_template") as remove, patch(
                "boneio.core.containers.start_caddy"
            ) as start:
                remove.return_value = _ok()
                start.return_value = _ok()
                assert await cloud_reg._restore_local_config() is True
                remove.assert_called_once()


class TestRetryAfterAFailedRegistration:
    """An hour was the wait after any failure, a 429 asking for five minutes too."""

    async def _first_wait(self, cloud_reg, registered: bool, retry_after: int | None) -> float:
        async def register():
            cloud_reg._retry_after = retry_after
            return registered

        waits: list[float] = []

        async def sleep(seconds):
            waits.append(seconds)
            raise asyncio.CancelledError

        with (
            patch.object(cloud_reg, "_register_dns", side_effect=register),
            patch.object(cloud_reg, "_cert_exists", return_value=True),
            patch.object(cloud_reg, "_cert_needs_refresh", AsyncMock(return_value=False)),
            patch.object(cloud_reg, "is_cloud_config_active", return_value=True),
            patch.object(cloud_reg, "_caddy_cert_matches_disk", AsyncMock(return_value=True)),
            patch("boneio.core.cloud.registration.get_network_info", return_value={"ip": "10.0.0.2"}),
            patch("boneio.core.cloud.registration.asyncio.sleep", side_effect=sleep),
        ):
            with pytest.raises(asyncio.CancelledError):
                await cloud_reg._registration_loop()
        return waits[0]

    @pytest.mark.asyncio
    async def test_the_api_s_own_wait_is_honoured(self, cloud_reg):
        assert await self._first_wait(cloud_reg, False, 327) == 327

    @pytest.mark.asyncio
    async def test_any_other_failure_is_retried_in_minutes(self, cloud_reg):
        from boneio.core.cloud.registration import REGISTRATION_RETRY

        assert await self._first_wait(cloud_reg, False, None) == REGISTRATION_RETRY

    @pytest.mark.asyncio
    async def test_a_registered_device_waits_the_full_interval(self, cloud_reg):
        from boneio.core.cloud.registration import REGISTRATION_INTERVAL

        assert await self._first_wait(cloud_reg, True, None) == REGISTRATION_INTERVAL
