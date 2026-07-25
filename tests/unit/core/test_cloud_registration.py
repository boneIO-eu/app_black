"""Unit tests for CloudRegistration module."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from boneio.core.cloud.registration import CloudRegistration, CERT_FILE


@pytest.fixture
def cloud_reg():
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
