"""Tests for the role policy — which role may make which request.

Also where F-12 is held closed. /api/logs, /api/system/overlay and
/api/hostname answered anyone who asked, handing out the service journal, the
boot overlay path and the hostname without a token. The policy here is what
decides that an API path needs a role at all, so a route added without one
fails these tests rather than shipping open.
"""

from __future__ import annotations

import pytest

from boneio.core.auth.models import Role
from boneio.webui.middleware.policy import (
    is_api_path,
    is_exempt,
    required_role,
    role_allows,
)


# ------------------------------------------------------------------ exemptions


@pytest.mark.parametrize(
    "path",
    [
        "/api/login",
        "/api/init",
        "/api/version",
        "/api/auth/required",
        "/api/onboarding/status",
        "/api/onboarding/admin",
    ],
)
def test_exempt_paths(path):
    assert is_exempt(path) is True


@pytest.mark.parametrize(
    "path", ["/api/config", "/api/outputs/x/toggle", "/api/system/restart"]
)
def test_non_exempt_paths(path):
    assert is_exempt(path) is False


def test_only_api_paths_are_gated():
    assert is_api_path("/api/config") is True
    assert is_api_path("/assets/index.js") is False
    assert is_api_path("/") is False


# -------------------------------------------------------------- viewer: reads


@pytest.mark.parametrize(
    "path",
    [
        "/api/outputs",
        "/api/sensors",
        "/api/dashboard",
        "/api/config",
        "/api/covers",
    ],
)
def test_viewer_may_read(path):
    assert required_role("GET", path) is Role.VIEWER
    assert role_allows(Role.VIEWER, "GET", path) is True


@pytest.mark.parametrize(
    "path",
    [
        "/api/files",
        "/api/files/config.yaml",
        "/api/accounts",
        "/api/config/download",
        "/api/config/backups",
        "/api/nodered/backup",
    ],
)
def test_viewer_may_not_read_credential_carriers(path):
    """Config archives bundle secrets.yaml, so downloading one is a secret read."""
    assert required_role("GET", path) is Role.ADMIN
    assert role_allows(Role.VIEWER, "GET", path) is False


@pytest.mark.parametrize(
    "path",
    [
        "/api/diagnostics/bundle",
        "/api/diagnostics/capture",
        "/api/logs",
        "/api/i2c/scan",
        "/api/can/status",
        "/api/can/nodes",
    ],
)
def test_viewer_may_not_read_diagnostics(path):
    """Diagnostics is admin-only even though every route in it is a GET.

    The bus scans reach into the hardware — the Modbus helper pauses the
    polling loop to take the bus — and the device log carries the serial
    number that /api/version withholds from a non-admin.
    """
    assert required_role("GET", path) is Role.ADMIN
    assert role_allows(Role.VIEWER, "GET", path) is False


# ------------------------------------------------------------- viewer: writes


@pytest.mark.parametrize(
    "path",
    [
        "/api/outputs/relay_01/toggle",
        "/api/outputs/relay_01/turn_on",
        "/api/outputs/relay_01/turn_off",
        "/api/outputs/relay_01/set_duration",
        "/api/outputs/relay_01/set_brightness",
        "/api/groups/lights/toggle",
        "/api/covers/blind_01/action",
        "/api/covers/blind_01/set_position",
        "/api/covers/blind_01/set_tilt",
        "/api/irrigation/garden/command",
        "/api/irrigation/garden/zone/lawn/command",
        "/api/irrigation/garden/schedule/0/skip",
        "/api/templates/thermostats/living/temperature",
        "/api/templates/alarms/house/command",
        "/api/remote-devices/esp1/output/relay/action",
        "/api/remote-devices/esp1/cover/blind/action",
        "/api/modbus/get",
    ],
)
def test_viewer_may_operate_the_device(path):
    assert required_role("POST", path) is Role.VIEWER
    assert role_allows(Role.VIEWER, "POST", path) is True


@pytest.mark.parametrize(
    "path",
    [
        "/api/config/boneio",
        "/api/config/reload",
        "/api/config/restore",
        "/api/config/create_backup",
        "/api/files/config.yaml",
        "/api/restart",
        "/api/reboot",
        "/api/shutdown",
        "/api/hostname",
        "/api/timezone",
        "/api/log-level",
        "/api/system/overlay",
        "/api/accounts",
        "/api/accounts/gosc",
        "/api/modbus/set",
        "/api/modbus/set_multiple",
        "/api/modbus/coord1/entity/set_value",
        "/api/remote-devices/discover-wled",
        "/api/remote-devices/discover-esphome",
        "/api/nodered/update/perform",
        "/api/caddy/config",
        "/api/can/send",
        "/api/migrations/apply",
        "/api/irrigation/garden/settings",
        "/api/irrigation/garden/zone/lawn/settings",
        "/api/irrigation/import",
    ],
)
def test_viewer_may_not_configure_the_device(path):
    assert required_role("POST", path) is Role.ADMIN
    assert role_allows(Role.VIEWER, "POST", path) is False


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_unknown_write_routes_default_to_admin(method):
    """A route added later is locked down until this policy is edited."""
    assert required_role(method, "/api/some/brand/new/route") is Role.ADMIN


def test_delete_is_never_a_viewer_action():
    assert required_role("DELETE", "/api/outputs/relay_01/toggle") is Role.ADMIN


# --------------------------------------------------------------------- admin


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/files/config.yaml"),
        ("POST", "/api/restart"),
        ("PUT", "/api/config/boneio"),
        ("DELETE", "/api/accounts/gosc"),
        ("POST", "/api/outputs/relay_01/toggle"),
    ],
)
def test_admin_may_do_everything(method, path):
    assert role_allows(Role.ADMIN, method, path) is True


# ------------------------------------- what the settings screen actually writes
#
# The Settings entry has always been hidden from a viewer, but the route stayed
# reachable — by a bookmark and by the "edit in settings" shortcut behind a long
# press on an output. The UI gate is now closed too, but the UI is a hint: these
# are the requests that screen makes, and they are what has to stay admin-only
# whatever the front end offers.


@pytest.mark.parametrize("method,path", [
    ("POST", "/api/config"),
    ("PUT", "/api/config"),
    ("POST", "/api/config/save"),
    ("POST", "/api/config/section"),
    ("POST", "/api/config/restore"),
    ("DELETE", "/api/config/backups/backup.tar.gz"),
    ("POST", "/api/files/save"),
    ("POST", "/api/system/restart"),
    ("POST", "/api/system/overlay"),
    ("POST", "/api/timezone"),
    ("POST", "/api/ntp"),
    ("POST", "/api/name"),
    ("POST", "/api/accounts"),
    ("DELETE", "/api/accounts/somebody"),
    ("POST", "/api/migrations/apply"),
    ("POST", "/api/update/start"),
    ("POST", "/api/can/interface-up"),
    ("POST", "/api/nodered/restore"),
])
def test_everything_the_settings_screen_writes_needs_an_admin(method, path):
    assert required_role(method, path) is Role.ADMIN


def test_a_viewer_may_still_operate_the_device(monkeypatch):
    """The role would be pointless otherwise — see the policy docstring."""
    for method, path in [
        ("POST", "/api/outputs/relay1/toggle"),
        ("POST", "/api/covers/blind1/action"),
        ("POST", "/api/irrigation/garden/command"),
        ("PUT", "/api/account/password"),
    ]:
        assert required_role(method, path) is Role.VIEWER, f"{method} {path}"


def test_reading_the_configuration_stays_open_to_a_viewer():
    """Deliberate: the dashboard needs it, and secrets are masked on the way out.

    If this ever has to change, the masking in config_core is the thing to check
    first — it is what makes the read safe, not the role.
    """
    assert required_role("GET", "/api/config") is Role.VIEWER
    # The archive routes are a different matter: the tar bundles secrets.yaml.
    assert required_role("GET", "/api/config/download") is Role.ADMIN
