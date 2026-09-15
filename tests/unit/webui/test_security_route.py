"""The security posture endpoint.

Two things matter here and nothing else does: that the answer describes the
device rather than a default, and that a viewer cannot ask the question. The
contents of each check are the posture module's business and are tested there.
"""

from __future__ import annotations

import pytest

from boneio.core.auth.models import Role
from boneio.webui.middleware import policy
from boneio.webui.routes import security as security_route


class _FakeStore:
    def __init__(self, provisioned: bool) -> None:
        self._provisioned = provisioned

    def is_provisioned(self) -> bool:
        return self._provisioned


class _FakeCloud:
    def __init__(self, active: bool) -> None:
        self._active = active

    def is_cloud_config_active(self) -> bool:
        return self._active


class _FakeHelper:
    def __init__(self, cloud_active: bool | None) -> None:
        self._cloud_reg = _FakeCloud(cloud_active) if cloud_active is not None else None


class _FakeState:
    def __init__(self, config_file: str, cloud_active: bool | None = None) -> None:
        self.yaml_config_file = config_file
        self.config_helper = _FakeHelper(cloud_active)


@pytest.fixture
def config_file(tmp_path):
    """A minimal config on disk, since the route reads the real file."""
    path = tmp_path / "config.yaml"
    path.write_text("mqtt:\n  host: localhost\n  password: boneio123\n", encoding="utf-8")
    return str(path)


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    """Keep module-level state from leaking between tests."""
    monkeypatch.setattr(security_route, "_app_state", None)
    yield
    security_route.set_app_state(None)


def _install(monkeypatch, config_file, *, provisioned=True, anonymous=False, auth=True, cloud=None):
    security_route.set_app_state(_FakeState(config_file, cloud))
    monkeypatch.setattr(security_route, "get_user_store", lambda: _FakeStore(provisioned))
    monkeypatch.setattr(security_route, "is_anonymous_allowed", lambda: anonymous)
    monkeypatch.setattr(security_route, "is_auth_required", lambda: auth)


def test_reports_the_real_configuration(monkeypatch, config_file):
    """The factory MQTT password in the file must reach the answer."""
    _install(monkeypatch, config_file)
    posture = security_route.current_posture()
    assert "mqtt_password" in {c.id for c in posture.failed}


def test_resolves_secret_references(monkeypatch, tmp_path):
    """A default password hidden behind !secret is still the default."""
    (tmp_path / "secrets.yaml").write_text("mqtt_pass: boneio123\n", encoding="utf-8")
    path = tmp_path / "config.yaml"
    path.write_text("mqtt:\n  host: localhost\n  password: !secret mqtt_pass\n", encoding="utf-8")
    _install(monkeypatch, str(path))
    assert "mqtt_password" in {c.id for c in security_route.current_posture().failed}


def test_unreadable_config_still_answers(monkeypatch, tmp_path):
    """A device that cannot read its config must not fail the request."""
    _install(monkeypatch, str(tmp_path / "missing.yaml"))
    posture = security_route.current_posture()
    assert posture.checks  # it answered
    assert "mqtt_password" not in {c.id for c in posture.failed}


def test_broken_store_does_not_claim_the_device_is_unclaimed(monkeypatch, config_file):
    """A store that raises must not be reported as 'no admin account'."""
    _install(monkeypatch, config_file)

    class _Broken:
        def is_provisioned(self):
            raise RuntimeError("users.json unreadable")

    monkeypatch.setattr(security_route, "get_user_store", lambda: _Broken())
    assert "admin_account" not in {c.id for c in security_route.current_posture().failed}


def test_cloud_certificate_is_reflected(monkeypatch, config_file):
    """Cloud registration clears the self-signed-certificate note."""
    _install(monkeypatch, config_file, cloud=True)
    assert "certificate" not in {c.id for c in security_route.current_posture().failed}

    _install(monkeypatch, config_file, cloud=False)
    assert "certificate" in {c.id for c in security_route.current_posture().failed}


@pytest.mark.asyncio
async def test_endpoint_shape(monkeypatch, config_file):
    """The response carries the checks and a summary."""
    _install(monkeypatch, config_file)
    body = await security_route.get_posture()
    assert body["summary"]["worst"] == "critical"
    assert any(c["id"] == "mqtt_password" for c in body["checks"])
    assert all("remedy" in c for c in body["checks"])


def test_viewers_may_not_read_the_posture():
    """The list of open doors is admin-only, GET notwithstanding."""
    assert policy.required_role("GET", "/api/security/posture") is Role.ADMIN
    assert not policy.role_allows(Role.VIEWER, "GET", "/api/security/posture")
    assert policy.role_allows(Role.ADMIN, "GET", "/api/security/posture")


def test_posture_is_not_reachable_without_a_token():
    """It is not on the pre-login exempt list."""
    assert not policy.is_exempt("/api/security/posture")
