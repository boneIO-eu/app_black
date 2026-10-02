"""GET /api/cloud/status tells the panel when, and where, to go.

The first-run wizard switches the PWA on and then has to send the owner to
the registered name. The template flips first and Caddy is recreated after
it, so "the template is the cloud one" is not the moment: ``serving`` is.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from boneio.webui.routes import system


def _helper(cloud_reg=None, url="https://blkf8dc18.black.boneio.app:8443"):
    return SimpleNamespace(
        _cloud_reg=cloud_reg,
        cloud_registration=cloud_reg is not None,
        configuration_url=url,
    )


def _registration(domain, serving):
    return SimpleNamespace(
        enabled=True,
        domain=domain,
        serving=serving,
        is_cloud_config_active=lambda: True,
        is_compose_writable=False,
        last_error=None,
    )


async def _status(helper):
    with patch.object(system, "_app_state", SimpleNamespace(config_helper=helper)):
        return await system.get_cloud_status()


@pytest.mark.asyncio
async def test_reports_serving_and_where():
    status = await _status(_helper(_registration("blkf8dc18.black.boneio.app", True)))
    assert status["serving"] is True
    assert status["url"] == "https://blkf8dc18.black.boneio.app:8443"


@pytest.mark.asyncio
async def test_still_switching_is_not_serving():
    status = await _status(_helper(_registration("blkf8dc18.black.boneio.app", False)))
    assert status["serving"] is False


@pytest.mark.asyncio
async def test_no_url_before_the_name_is_registered():
    status = await _status(_helper(_registration(None, False)))
    assert status["url"] is None


@pytest.mark.asyncio
async def test_registration_not_running():
    status = await _status(_helper(None))
    assert status["serving"] is False
    assert status["url"] is None
