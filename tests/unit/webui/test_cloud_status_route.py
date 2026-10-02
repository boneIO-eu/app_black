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


def _init_helper():
    reg = _registration("blkf8dc18.black.boneio.app", True)
    reg.last_error = "Error response from daemon: stderr nobody outside should read"
    reg.is_compose_writable = True
    return SimpleNamespace(
        _cloud_reg=reg,
        cloud_registration=True,
        serial_number="blkf8dc18",
        real_serial="blkf8dc18",
        serial_override=None,
        name="boneIO Black",
        pwa_name="bIO f8dc18",
        get_config=lambda: {},
    )


async def _init(signed_in: bool):
    helper = _init_helper()
    request = SimpleNamespace(state=SimpleNamespace(user="pawel" if signed_in else ""))
    with (
        patch.object(system, "_app_state", SimpleNamespace(config_helper=helper)),
        patch.object(system, "is_auth_required", return_value=True),
        patch.object(system, "is_anonymous_allowed", return_value=False),
        patch.object(system, "get_user_store", return_value=None),
    ):
        return await system.get_init(request=request, config_helper=helper)


@pytest.mark.asyncio
async def test_a_stranger_learns_only_whether_cloud_is_on():
    # /api/init answers before the login form. compose's stderr and a domain
    # that spells out the withheld serial are not for that audience.
    body = await _init(signed_in=False)
    assert body["cloud"] == {"enabled": True}
    assert body["pwa_default"] is None
    assert "serial_no" not in body


@pytest.mark.asyncio
async def test_a_signed_in_caller_gets_the_cloud_details():
    body = await _init(signed_in=True)
    assert body["cloud"]["domain"] == "blkf8dc18.black.boneio.app"
    assert body["cloud"]["last_error"].startswith("Error response")
    assert body["pwa_default"] == "bIO f8dc18"
