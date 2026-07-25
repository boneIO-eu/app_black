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

    mock_openssl_out = "notAfter=Oct  9 15:02:27 2026 GMT\n"

    with patch("boneio.core.cloud.registration.CERT_FILE", cert_file):
        with patch("boneio.core.cloud.registration.KEY_FILE", cert_file):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout=mock_openssl_out)

                needs_refresh = await cloud_reg._cert_needs_refresh()
                # Should successfully parse date (Oct 9 2026 is far in future) -> False
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
