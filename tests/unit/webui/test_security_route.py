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
        self.restart_flagged: list[str] = []

    def set_restart_required(self, section: str) -> None:
        self.restart_flagged.append(section)


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


def test_endpoint_shape(monkeypatch, config_file):
    """The response carries the checks and a summary."""
    _install(monkeypatch, config_file)
    body = security_route.get_posture()
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


# ------------------------------------------------------------ framing policy


@pytest.fixture
def framing_device(tmp_path, monkeypatch):
    """A device whose config.yaml has a web section but no security block."""
    path = tmp_path / "config.yaml"
    path.write_text(
        "# boneIO\nmqtt:\n  host: localhost\n  password: !secret p\nweb:\n  port: 8090\n",
        encoding="utf-8",
    )
    (tmp_path / "secrets.yaml").write_text("p: changed\n", encoding="utf-8")
    _install(monkeypatch, str(path))
    return path


def _stored(path):
    """The frame_ancestors value as the app actually reads it back.

    Through the project's own loader, because the fixture carries a !secret
    reference — the kind of file this edits in real life.
    """
    from boneio.core.config.yaml_util import load_yaml_file

    return load_yaml_file(str(path))["web"]["security"]["frame_ancestors"]


def test_unconfigured_device_reports_the_default(framing_device):
    body = security_route.get_frame_ancestors()
    assert body["restrict"] is True
    assert body["configured"] is False
    assert body["tokens"] == ["self"]
    # Reported as the browser will receive it, keywords quoted.
    assert body["value"] == "'self'"


@pytest.mark.asyncio
async def test_writes_a_plain_list(framing_device):
    """The list form is what removes the quoting trap from the config."""
    await security_route.set_frame_ancestors(
        security_route.FrameAncestorsRequest(restrict=True)
    )
    assert _stored(framing_device) == ["self"]


@pytest.mark.asyncio
async def test_an_extra_origin_is_added_alongside_self(framing_device):
    await security_route.set_frame_ancestors(
        security_route.FrameAncestorsRequest(
            restrict=True, extra_origins=["https://homeassistant.local:8123/"]
        )
    )
    # The trailing slash is dropped: an origin with a path is not an origin.
    assert _stored(framing_device) == ["self", "https://homeassistant.local:8123"]


@pytest.mark.asyncio
async def test_lifting_the_restriction_drops_the_origins(framing_device):
    """Listing sites next to `*` would suggest they mean something."""
    await security_route.set_frame_ancestors(
        security_route.FrameAncestorsRequest(
            restrict=False, extra_origins=["https://ha.local:8123"]
        )
    )
    assert _stored(framing_device) == ["*"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad",
    [
        "homeassistant.local",  # no scheme
        "https://ha.local/lovelace",  # a path, not an origin
        "https://*.local",  # wildcard host
        "*",  # the way out is `restrict: false`, not an origin
        "javascript:alert(1)",
        "https://ha.local:8123 https://evil.example",  # two, smuggled as one
    ],
)
async def test_malformed_origins_are_refused(framing_device, bad):
    with pytest.raises(Exception) as err:
        await security_route.set_frame_ancestors(
            security_route.FrameAncestorsRequest(restrict=True, extra_origins=[bad])
        )
    assert getattr(err.value, "status_code", None) == 400
    # Nothing was written.
    assert "security" not in framing_device.read_text()


@pytest.mark.asyncio
async def test_an_included_web_section_is_refused_not_mangled(tmp_path, monkeypatch):
    """Writing under `web: !include web.yaml` would land where nothing reads."""
    path = tmp_path / "config.yaml"
    path.write_text("web: !include web.yaml\n", encoding="utf-8")
    (tmp_path / "web.yaml").write_text("port: 8090\n", encoding="utf-8")
    _install(monkeypatch, str(path))

    with pytest.raises(Exception) as err:
        await security_route.set_frame_ancestors(
            security_route.FrameAncestorsRequest(restrict=True)
        )
    assert getattr(err.value, "status_code", None) == 409


@pytest.mark.asyncio
async def test_saving_asks_for_a_restart(framing_device):
    """The header is assembled once, when the app starts."""
    body = await security_route.set_frame_ancestors(
        security_route.FrameAncestorsRequest(restrict=True)
    )
    assert body["restart_required"] is True
    assert security_route._app_state.config_helper.restart_flagged == ["web"]


def test_framing_routes_are_admin_only():
    assert policy.required_role("PUT", "/api/security/frame-ancestors") is Role.ADMIN
    assert not policy.role_allows(Role.VIEWER, "PUT", "/api/security/frame-ancestors")
    assert not policy.role_allows(Role.VIEWER, "GET", "/api/security/frame-ancestors")


@pytest.mark.asyncio
async def test_several_origins_are_all_kept(framing_device):
    """The config is a list, so the panel must not quietly keep only one."""
    await security_route.set_frame_ancestors(
        security_route.FrameAncestorsRequest(
            restrict=True,
            extra_origins=["https://ha.local:8123", "https://spare.local:8123"],
        )
    )
    assert _stored(framing_device) == [
        "self",
        "https://ha.local:8123",
        "https://spare.local:8123",
    ]


@pytest.mark.asyncio
async def test_a_hand_written_string_is_read_and_replaced(tmp_path, monkeypatch):
    """Configs written by 1.6 before the list existed still open and save."""
    path = tmp_path / "config.yaml"
    path.write_text(
        "web:\n  security:\n    frame_ancestors: \"'self' https://old.local\"\n",
        encoding="utf-8",
    )
    _install(monkeypatch, str(path))

    body = security_route.get_frame_ancestors()
    assert body["extra_origins"] == ["https://old.local"]

    await security_route.set_frame_ancestors(
        security_route.FrameAncestorsRequest(restrict=True, extra_origins=["https://new.local"])
    )
    assert _stored(path) == ["self", "https://new.local"]
