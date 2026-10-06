"""A factory reset puts back the configuration of the board it runs on.

The revision decides which board files boneIO loads (boards/1.1 has the
buzzer, boards/1.0 the inverted MCPs), so a reset that wrote the wrong
version: left a board running another board's wiring.
"""

from __future__ import annotations

import asyncio

import pytest

from boneio.core.config.yaml_util import load_config_from_file, load_yaml_file
from boneio.factory_config import FACTORY_CONFIG_DIR
from boneio.webui.routes import update

TEMPLATES = sorted(p.parent for p in FACTORY_CONFIG_DIR.glob("*/*/config.yaml"))


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "boneio").mkdir()
    return tmp_path


def _reset(board: str, version: str | None) -> dict:
    request = update.FactoryResetRequest(device_type=board, version=version)
    return asyncio.run(update.factory_reset(request))


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_every_template_validates(template, tmp_path):
    target = tmp_path / "boneio"
    target.mkdir()
    for f in template.glob("*.yaml"):
        (target / f.name).write_bytes(f.read_bytes())
    config = load_config_from_file(str(target / "config.yaml"))
    assert str(config["boneio"]["version"]) == template.parent.name


@pytest.mark.parametrize("version", ["0.8", "1.0", "1.1"])
@pytest.mark.parametrize("board", ["32x10", "24x16", "48x4", "cover", "cover_mix"])
def test_reset_writes_the_template_of_that_revision(home, board, version):
    assert _reset(board, version)["status"] == "success"
    written = (home / "boneio" / "config.yaml").read_text()
    assert written == (FACTORY_CONFIG_DIR / version / board / "config.yaml").read_text()


@pytest.mark.parametrize(("version", "temp", "power"), [
    ("0.2", "mcp9808", None),
    ("0.4", "lm75", "ina219"),
])
def test_an_older_revision_is_fitted(home, version, temp, power):
    assert _reset("32x10", version)["status"] == "success"
    config = load_yaml_file(str(home / "boneio" / "config.yaml"))
    assert str(config["boneio"]["version"]) == version
    assert temp in config
    assert ("ina226" not in config) and (power is None or power in config)


def test_without_a_version_the_reset_keeps_the_boards(home):
    (home / "boneio" / "config.yaml").write_text("boneio:\n  name: x\n  version: 1.1\n")
    assert _reset("32x10", None)["hardware_version"] == "1.1"


def test_the_devices_secrets_stay(home):
    (home / "boneio" / "secrets.yaml").write_text('mqtt_password: "mine"\n')
    _reset("32x10", "1.1")
    assert load_yaml_file(str(home / "boneio" / "secrets.yaml"))["mqtt_password"] == "mine"


def test_a_partial_reset_finds_relay_boards(home):
    request = update.PartialResetRequest(device_type="32x10A", files_to_replace=["output"])
    result = asyncio.run(update.partial_factory_reset(request))
    assert result["status"] == "success", result
    assert result["copied_files"] == ["output32x10A.yaml"]


def test_the_current_revision_is_read_from_a_real_config(home):
    for f in (FACTORY_CONFIG_DIR / "1.0" / "32x10").glob("*.yaml"):
        (home / "boneio" / f.name).write_bytes(f.read_bytes())
    assert asyncio.run(update.get_hardware_versions())["current"] == "1.0"


def test_templates_are_on_the_current_schema():
    from boneio.core.config.migrations import CURRENT_SCHEMA_VERSION, get_config_version

    for template in TEMPLATES:
        doc = load_yaml_file(str(template / "config.yaml"))
        assert get_config_version(doc) == CURRENT_SCHEMA_VERSION, template
