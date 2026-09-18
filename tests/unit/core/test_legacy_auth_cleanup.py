"""Tests for getting the pre-1.6 login out of a controller's configuration.

Upgrading copies the ``web.auth`` account into the hashed store and leaves the
block where it is, so the password stays on disk in plain text — in the file,
and in every backup and diagnostic bundle taken since. Two things have to
work: saying so somewhere that does not scroll away, and taking it out on
request without damaging a file the owner maintains by hand.
"""

from __future__ import annotations

import pytest

from boneio.core.config.yaml_patch import YamlPatchError, remove_section
from boneio.core.security.posture import Severity, State, evaluate

CONFIG = """mqtt: !include mqtt.yaml

web:
  port: 8090
  # The login from before 1.6
  auth:
    username: admin
    password: hunter2

  security:
    frame_ancestors: self

logger:
  default: info
"""


def _posture(config):
    posture = evaluate(
        config,
        is_provisioned=True,
        anonymous_allowed=False,
        auth_required=True,
        cloud_active=False,
    )
    return next(c for c in posture.checks if c.id == "legacy_web_auth")


# ------------------------------------------------------------ the notice


def test_a_leftover_block_is_reported():
    check = _posture({"web": {"auth": {"username": "a", "password": "p"}}})
    assert check.state is State.FAILED


def test_a_username_alone_still_counts():
    """The username is not the secret, but its presence means the block is
    there and so, usually, is the password."""
    assert _posture({"web": {"auth": {"username": "a"}}}).state is State.FAILED


def test_a_clean_configuration_passes():
    assert _posture({"web": {"port": 8090}}).state is State.OK


def test_no_web_section_at_all_passes():
    assert _posture({}).state is State.OK


def test_it_is_a_warning_not_a_critical():
    """Nothing reads the block, so this is not a way in — it is a credential
    on disk. Rating it critical would put a permanent red badge on every
    upgraded controller, and a badge that is always red is not read."""
    assert _posture({"web": {"auth": {"password": "p"}}}).severity is Severity.WARNING


def test_the_notice_survives_a_provisioned_device():
    """The bug this exists for.

    The old notice lived in the first-run wizard, which only renders on an
    unprovisioned device — and a successful migration is what provisions it.
    The one case it was written for was the one case it could not appear in.
    """
    check = _posture({"web": {"auth": {"password": "p"}}})
    assert check.state is State.FAILED, "invisible on exactly the devices that have it"
    assert check.settings_section == "security"


# ------------------------------------------------------------ the removal


@pytest.fixture
def config(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(CONFIG)
    return path


def test_the_block_goes(config):
    assert remove_section(config, ("web", "auth")) is True
    text = config.read_text()
    assert "hunter2" not in text
    assert "username: admin" not in text


def test_everything_else_stays(config):
    remove_section(config, ("web", "auth"))
    text = config.read_text()
    assert "port: 8090" in text
    assert "frame_ancestors: self" in text
    assert "mqtt: !include mqtt.yaml" in text
    assert "logger:" in text


def test_the_comment_describing_it_goes_too(config):
    """Left behind it would sit over frame_ancestors, describing nothing."""
    remove_section(config, ("web", "auth"))
    assert "login from before 1.6" not in config.read_text()


def test_the_file_still_parses(config):
    import yaml

    class Loader(yaml.SafeLoader):
        pass

    Loader.add_multi_constructor("!", lambda loader, suffix, node: None)

    remove_section(config, ("web", "auth"))
    doc = yaml.load(config.read_text(), Loader=Loader)
    assert "auth" not in doc["web"]
    assert doc["web"]["port"] == 8090
    assert doc["logger"]["default"] == "info"


def test_removing_what_is_not_there_changes_nothing(config):
    remove_section(config, ("web", "auth"))
    before = config.read_text()
    assert remove_section(config, ("web", "auth")) is False
    assert config.read_text() == before


def test_a_similarly_named_key_elsewhere_is_left_alone(tmp_path):
    """`auth` under something else is not the block being removed."""
    path = tmp_path / "config.yaml"
    path.write_text("mqtt:\n  auth:\n    password: keepme\n\nweb:\n  port: 8090\n")
    assert remove_section(path, ("web", "auth")) is False
    assert "keepme" in path.read_text()


def test_an_empty_path_is_refused(config):
    with pytest.raises(YamlPatchError):
        remove_section(config, ())


def test_the_last_section_in_a_file_can_be_removed(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("web:\n  port: 8090\n  auth:\n    password: p\n")
    assert remove_section(path, ("web", "auth")) is True
    assert path.read_text() == "web:\n  port: 8090\n"


def test_removal_needs_an_administrator():
    """The endpoint reads and rewrites config.yaml."""
    from boneio.webui.middleware.policy import required_role

    assert str(required_role("DELETE", "/api/security/legacy-auth")) == "admin"


# ---------------------------------------------------------- the endpoint


class _State:
    def __init__(self, config_file):
        self.yaml_config_file = str(config_file)
        self.config_helper = None


@pytest.fixture
def endpoint(config, monkeypatch):
    """The route, pointed at a throwaway config."""
    from boneio.webui.routes import security as route

    monkeypatch.setattr(route, "_app_state", _State(config))
    monkeypatch.setattr(route, "_config_cache", None, raising=False)
    return route


async def _call(route):
    return await route.remove_legacy_auth()


def test_the_endpoint_removes_and_keeps_a_copy(endpoint, config):
    import asyncio

    result = asyncio.run(_call(endpoint))
    assert result["removed"] is True
    assert "hunter2" not in config.read_text()

    backup = config.with_name(f"{config.name}.pre-1.6-auth.bak")
    assert backup.exists(), "edited an owner's file with no way back"
    assert "hunter2" in backup.read_text()


def test_a_second_call_is_a_no_op_and_leaves_no_stray_copy(endpoint, config):
    import asyncio

    asyncio.run(_call(endpoint))
    backup = config.with_name(f"{config.name}.pre-1.6-auth.bak")
    first = backup.read_text()

    result = asyncio.run(_call(endpoint))
    assert result["removed"] is False
    assert result["backup"] is None
    assert backup.read_text() == first, "overwrote the copy that had the block"


def test_without_a_loaded_config_it_refuses(monkeypatch):
    import asyncio

    from fastapi import HTTPException

    from boneio.webui.routes import security as route

    monkeypatch.setattr(route, "_app_state", _State(""))
    with pytest.raises(HTTPException) as err:
        asyncio.run(_call(route))
    assert err.value.status_code == 503


def test_the_copy_is_written_before_the_edit(endpoint, config, monkeypatch):
    """If the copy cannot be made, the edit must not happen: this is an
    irreversible change to a file we do not own."""
    import asyncio

    from fastapi import HTTPException

    def refuse(*args, **kwargs):
        raise OSError("read-only filesystem")

    monkeypatch.setattr(endpoint.shutil, "copy2", refuse)
    with pytest.raises(HTTPException) as err:
        asyncio.run(_call(endpoint))
    assert err.value.status_code == 500
    assert "hunter2" in config.read_text(), "removed the block with no copy saved"
