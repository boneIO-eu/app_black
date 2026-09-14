"""Tests for the role policy — which role may make which request."""

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
        "/api/logs",
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
        "/api/caddy/status",
        "/api/nodered/backup",
    ],
)
def test_viewer_may_not_read_credential_carriers(path):
    """Config archives bundle secrets.yaml, so downloading one is a secret read."""
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
