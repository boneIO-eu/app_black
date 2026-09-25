"""The config cache keeps secrets as references, not values.

It used to pickle the validated config with every ``!secret`` already
substituted: the passwords sat in ``.cache.pkl``, and secrets.yaml was not part
of the cache key, so a password changed there went unnoticed until some other
edit happened to invalidate the cache. The first boot of an image now writes a
per-device MQTT password into secrets.yaml, which is only safe — and only fast
— if the cache neither holds the old one nor has to be thrown away for it.
"""

from __future__ import annotations

import pickle
import re
import shutil
from pathlib import Path

import pytest

from boneio.core.config import yaml_util
from boneio.core.config.migrations import CURRENT_SCHEMA_VERSION

EXAMPLE = Path(yaml_util.__file__).resolve().parents[2] / "example_config" / "32x10"


@pytest.fixture(autouse=True)
def _fresh_secret_names():
    """The loader's record of secret names is process-wide; keep tests apart."""
    yaml_util._SECRET_NAMES_LOADED.clear()
    yield
    yaml_util._SECRET_NAMES_LOADED.clear()


@pytest.fixture
def config_dir(tmp_path):
    """The shipped 32x10 example, with the MQTT password moved to secrets.yaml."""
    target = tmp_path / "boneio"
    shutil.copytree(EXAMPLE, target, ignore=shutil.ignore_patterns("__pycache__", "*.pkl"))
    mqtt = target / "mqtt.yaml"
    mqtt.write_text(
        mqtt.read_text().replace("password: boneio123", "password: !secret mqtt_password")
    )
    (target / "secrets.yaml").write_text("mqtt_password: first-password\n")
    # Already migrated: a load that migrates writes no cache, and these tests
    # are about the cache.
    main = target / "config.yaml"
    main.write_text(
        re.sub(r"config_version: \d+", f"config_version: {CURRENT_SCHEMA_VERSION}", main.read_text())
    )
    return target


def _load(config_dir: Path) -> dict:
    return yaml_util.load_config_from_file(str(config_dir / "config.yaml"))


def _cache_bytes(config_dir: Path) -> bytes:
    return Path(yaml_util._get_config_cache_path(str(config_dir / "config.yaml"))).read_bytes()


def test_a_changed_secret_is_used_and_the_cache_survives(config_dir, monkeypatch):
    assert _load(config_dir)["mqtt"]["password"] == "first-password"

    (config_dir / "secrets.yaml").write_text("mqtt_password: second-password\n")
    # A second full validation would mean the cache was thrown away for a
    # secret change — the 20-30 s on a BeagleBone this is meant to avoid.
    monkeypatch.setattr(
        yaml_util, "_full_config_validation",
        lambda *a, **k: pytest.fail("cache was not used"),
    )
    assert _load(config_dir)["mqtt"]["password"] == "second-password"


def test_the_cache_file_does_not_hold_the_secret(config_dir):
    _load(config_dir)
    blob = _cache_bytes(config_dir)
    assert b"first-password" not in blob
    assert b"mqtt_password" in blob


def test_a_secret_removed_from_secrets_yaml_forces_validation(config_dir):
    _load(config_dir)
    (config_dir / "secrets.yaml").write_text("other: x\n")
    with pytest.raises(Exception):
        # Full validation runs and reports the missing secret, instead of the
        # cache quietly supplying the old value.
        _load(config_dir)


def test_a_secret_validation_coerced_is_kept_by_value_and_checked(tmp_path):
    """Not every secret stays a string; those must not go stale either."""
    config = tmp_path / "config.yaml"
    config.write_text("web:\n  port: 8090\n")
    (tmp_path / "secrets.yaml").write_text("port: 8090\n")
    yaml_util._SECRET_NAMES_LOADED.clear()
    yaml_util._SECRET_NAMES_LOADED.add("port")
    yaml_util._save_config_cache(str(config), {"web": {"port": 8090}})
    assert yaml_util._try_load_cached_config(str(config)) == {"web": {"port": 8090}}
    (tmp_path / "secrets.yaml").write_text("port: 9000\n")
    assert yaml_util._try_load_cached_config(str(config)) is None


def test_a_secret_is_written_to_yaml_as_a_plain_string():
    value = yaml_util.SecretStr("p4ss", "mqtt_password")
    for dumper in (yaml_util.TimePeriodDumper, yaml_util.yaml.SafeDumper, yaml_util.yaml.Dumper):
        assert yaml_util.yaml.dump({"password": value}, Dumper=dumper) == "password: p4ss\n"
    # And anything else that pickles a config gets the value, not a boneIO type.
    assert type(pickle.loads(pickle.dumps(value))) is str


def test_a_stray_secret_name_does_not_poison_every_cache(tmp_path):
    """Some other YAML load may record a name this config never used."""
    config = tmp_path / "config.yaml"
    config.write_text("web:\n  port: 8090\n")
    yaml_util._SECRET_NAMES_LOADED.add("not_in_this_config")
    yaml_util._save_config_cache(str(config), {"web": {"port": 8090}})
    assert yaml_util._try_load_cached_config(str(config)) == {"web": {"port": 8090}}
