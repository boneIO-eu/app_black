"""The wizard asks which controller this is when the card did not say."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from boneio.core.auth.models import Role
from boneio.webui.routes import onboarding


@pytest.fixture
def device(tmp_path, monkeypatch):
    """A controller on the outputless base config, waiting for its type."""
    templates = tmp_path / "boneio_configs"
    for variant in ("base", "cover"):
        t = templates / "0.8" / variant
        t.mkdir(parents=True)
        (t / "config.yaml").write_text(f"# {variant}\n")
        (t / "secrets.yaml").write_text("mqtt_password: boneio123\n")
        (t / "config.yaml.cache.pkl").write_bytes(b"warm")
    (templates / "0.8" / "cover" / "cover.yaml").write_text("cover: []\n")
    config = tmp_path / "boneio"
    config.mkdir()
    (config / "config.yaml").write_text("# base\n")
    (config / "output32x10A.yaml").write_text("leftover\n")
    (config / "secrets.yaml").write_text('mqtt_password: "drawn-at-first-boot"\n')
    (config / "users.json").write_text("{}")
    (config / onboarding.BOARD_TYPE_PENDING).write_text("0.8\n")
    monkeypatch.setattr(onboarding, "FACTORY_TEMPLATE_DIR", templates)
    monkeypatch.setattr(onboarding, "is_running_as_service", lambda: False)
    onboarding.set_config_dir(config)
    yield config
    onboarding._config_dir = None


def _admin():
    return SimpleNamespace(state=SimpleNamespace(role=Role.ADMIN))


class _Tasks:
    def add_task(self, *args):
        raise AssertionError("no restart outside systemd")


async def test_the_picked_type_replaces_the_base_config(device):
    assert onboarding.pending_board_revision() == "0.8"
    result = await onboarding.set_board_type(
        onboarding.BoardTypeRequest(type="cover"), _admin(), _Tasks()
    )
    assert result == {"type": "cover", "revision": "0.8", "restarting": False}
    assert (device / "config.yaml").read_text() == "# cover\n"
    assert (device / "cover.yaml").exists()
    assert (device / "config.yaml.cache.pkl").read_bytes() == b"warm"
    assert not (device / "output32x10A.yaml").exists()
    assert "drawn-at-first-boot" in (device / "secrets.yaml").read_text()
    assert (device / "users.json").exists()
    assert onboarding.pending_board_revision() is None


async def test_only_an_administrator_may_pick(device):
    viewer = SimpleNamespace(state=SimpleNamespace(role=Role.VIEWER))
    anonymous = SimpleNamespace(state=SimpleNamespace())
    for request in (viewer, anonymous):
        with pytest.raises(HTTPException) as err:
            await onboarding.set_board_type(onboarding.BoardTypeRequest(type="cover"), request, _Tasks())
        assert err.value.status_code == 403
    assert (device / "config.yaml").read_text() == "# base\n"


async def test_once_set_it_cannot_be_set_again(device):
    (device / onboarding.BOARD_TYPE_PENDING).unlink()
    with pytest.raises(HTTPException) as err:
        await onboarding.set_board_type(onboarding.BoardTypeRequest(type="cover"), _admin(), _Tasks())
    assert err.value.status_code == 409


async def test_a_type_the_image_has_no_config_for_is_refused(device):
    with pytest.raises(HTTPException) as err:
        await onboarding.set_board_type(onboarding.BoardTypeRequest(type="24x16"), _admin(), _Tasks())
    assert err.value.status_code == 409
    assert (device / "config.yaml").read_text() == "# base\n"


def test_a_marker_that_is_not_a_revision_is_ignored(device):
    (device / onboarding.BOARD_TYPE_PENDING).write_text("../../etc\n")
    assert onboarding.pending_board_revision() is None
