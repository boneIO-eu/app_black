"""What happens to a validated-config cache written by a different build.

The cache next to ``config.yaml`` is a pickle of boneIO objects — ``TimePeriod``,
``OrderedDict`` and friends — and it is keyed on a hash of the config and of
``schema.yaml``.  Neither hash says anything about the *code*, so a release that
only moves or renames a class leaves a stale cache looking perfectly valid.
Unpickling it then fails on the import, and that has to come out as a cache miss
rather than as a failure to start: the fallback costs 20-30 s of Cerberus
validation on a BeagleBone, not a config the board cannot load.
"""

from __future__ import annotations

import importlib
import logging
import pickle
import sys

import pytest

from boneio.core.config import yaml_util
from boneio.version import __version__

CONFIG = "mqtt: !include mqtt.yaml\nweb:\n  port: 8090\n"
VALIDATED = {"web": {"port": 8090}, "mqtt": {"host": "localhost"}}


@pytest.fixture
def config_file(tmp_path):
    """A config.yaml for the cache to be keyed on."""
    path = tmp_path / "config.yaml"
    path.write_text(CONFIG)
    return str(path)


@pytest.fixture
def pickled_by_the_previous_build(tmp_path, monkeypatch):
    """Pickle a payload using a class this build can no longer import.

    Stands in for the real case: a ``TimePeriod`` pickled by one release and read
    back by the next, which moved the class to another module.  The returned
    helper takes a function that places the doomed object wherever the test wants
    it, and gives back the pickled bytes with the class already gone.
    """
    (tmp_path / "boneio_gone_away.py").write_text(
        "class TimePeriod:\n    def __init__(self, seconds=0):\n        self.seconds = seconds\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    module = importlib.import_module("boneio_gone_away")

    def dump(wrap):
        blob = pickle.dumps(wrap(module.TimePeriod(60)), protocol=pickle.HIGHEST_PROTOCOL)
        del sys.modules["boneio_gone_away"]
        sys.path.remove(str(tmp_path))
        with pytest.raises(ModuleNotFoundError):
            pickle.loads(blob)
        return blob

    return dump


def _valid_hashes(config_file: str) -> dict:
    """The hash pair a cache needs to look current for this config and schema."""
    return {
        "config_hash": yaml_util._compute_config_dir_hash(config_file),
        "schema_hash": yaml_util._compute_file_hash(yaml_util.schema_file),
    }


def _write_cache(config_file: str, header: dict, payload: bytes) -> None:
    """Write a cache in the current format: header pickle, then payload pickle."""
    with open(yaml_util._get_config_cache_path(config_file), "wb") as f:
        pickle.dump(header, f, protocol=pickle.HIGHEST_PROTOCOL)
        f.write(payload)


def test_a_cache_whose_classes_moved_is_a_miss_not_a_crash(
    config_file, pickled_by_the_previous_build, caplog
):
    """The case that fails to start today: the ImportError must not escape.

    A build of the same version that moved a class is the worst case, because the
    version gate lets it through and the payload is unpickled after all.
    """
    payload = pickled_by_the_previous_build(lambda grace: dict(VALIDATED, grace=grace))
    _write_cache(config_file, dict(_valid_hashes(config_file), version=__version__), payload)

    with caplog.at_level(logging.WARNING):
        assert yaml_util._try_load_cached_config(config_file) is None
    assert "ModuleNotFoundError" in caplog.text


def test_the_upgrade_a_device_in_the_field_will_actually_do(
    config_file, pickled_by_the_previous_build, caplog
):
    """A cache written before the version field, by a build whose classes moved.

    This is the reported crash on the exact file every deployed controller has on
    disk right now: one dict, payload inside, unpickled before any check runs.
    """
    blob = pickled_by_the_previous_build(
        lambda grace: dict(_valid_hashes(config_file), data=dict(VALIDATED, grace=grace))
    )
    with open(yaml_util._get_config_cache_path(config_file), "wb") as f:
        f.write(blob)

    with caplog.at_level(logging.WARNING):
        assert yaml_util._try_load_cached_config(config_file) is None
    assert "ModuleNotFoundError" in caplog.text


def test_a_cache_from_another_version_is_rejected_before_it_is_unpickled(
    config_file, pickled_by_the_previous_build, caplog
):
    """The version gate reads the header only, so the payload never has to load."""
    payload = pickled_by_the_previous_build(lambda grace: dict(VALIDATED, grace=grace))
    _write_cache(config_file, dict(_valid_hashes(config_file), version="1.5.9"), payload)

    with caplog.at_level(logging.WARNING):
        assert yaml_util._try_load_cached_config(config_file) is None
    # Named the version rather than reported an unpickling failure: proof the
    # payload was never touched.
    assert "1.5.9" in caplog.text
    assert "ModuleNotFoundError" not in caplog.text


def test_a_cache_from_before_the_version_field_is_a_miss(config_file, caplog):
    """An old cache has no version and its payload is inside the single dict."""
    with open(yaml_util._get_config_cache_path(config_file), "wb") as f:
        pickle.dump(
            dict(_valid_hashes(config_file), data=VALIDATED),
            f,
            protocol=pickle.HIGHEST_PROTOCOL,
        )

    with caplog.at_level(logging.WARNING):
        assert yaml_util._try_load_cached_config(config_file) is None
    assert "format" in caplog.text


def test_a_truncated_cache_is_a_miss(config_file, caplog):
    """Half a payload — an interrupted write, or a board that lost power."""
    yaml_util._save_config_cache(config_file, VALIDATED)
    cache_path = yaml_util._get_config_cache_path(config_file)
    with open(cache_path, "rb") as f:
        whole = f.read()
    with open(cache_path, "wb") as f:
        f.write(whole[:-5])

    with caplog.at_level(logging.WARNING):
        assert yaml_util._try_load_cached_config(config_file) is None
    assert "could not be read" in caplog.text


def test_garbage_in_the_cache_file_is_a_miss(config_file, caplog):
    with open(yaml_util._get_config_cache_path(config_file), "wb") as f:
        f.write(b"not a pickle at all")

    with caplog.at_level(logging.WARNING):
        assert yaml_util._try_load_cached_config(config_file) is None


def test_no_cache_at_all_is_quiet(config_file, caplog):
    """First boot after flashing is not something to warn about."""
    with caplog.at_level(logging.WARNING):
        assert yaml_util._try_load_cached_config(config_file) is None
    assert caplog.text == ""


def test_the_cache_this_build_wrote_is_read_back(config_file):
    """The whole point: the round trip still works, version field and all."""
    yaml_util._save_config_cache(config_file, VALIDATED)
    assert yaml_util._try_load_cached_config(config_file) == VALIDATED


def test_the_saved_cache_carries_the_boneio_version(config_file):
    """Both sides need the field, so pin what _save_config_cache writes."""
    yaml_util._save_config_cache(config_file, VALIDATED)
    with open(yaml_util._get_config_cache_path(config_file), "rb") as f:
        header = pickle.load(f)
    assert header["version"] == __version__
    assert {"version", "config_hash", "schema_hash", "secret_refs", "baked_secrets"} == set(header)


def test_an_edited_config_still_invalidates_the_cache(config_file):
    """The pre-existing hash checks survive the header split."""
    yaml_util._save_config_cache(config_file, VALIDATED)
    with open(config_file, "a") as f:
        f.write("cover:\n  - id: garage\n")
    assert yaml_util._try_load_cached_config(config_file) is None


def test_boneio_objects_survive_the_round_trip(config_file):
    """TimePeriod and OrderedDict are why this is a pickle and not JSON."""
    from collections import OrderedDict

    from boneio.core.utils import TimePeriod

    payload = {"cover": OrderedDict(a=1, b=2), "grace": TimePeriod(seconds=60)}
    yaml_util._save_config_cache(config_file, payload)
    loaded = yaml_util._try_load_cached_config(config_file)
    assert isinstance(loaded["cover"], OrderedDict)
    assert loaded["grace"].total_seconds == 60


class TestSchemaPickleCache:
    """The other pickle on the same startup path, in ~/.cache/boneio.

    It is fingerprinted on the mtime and size of the schema YAMLs, which says
    nothing about the code that parsed them — so it can go stale the same way,
    and reparsing the YAML it stands in for costs several seconds on a BeagleBone.
    """

    @pytest.fixture(autouse=True)
    def cache_in_tmp(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

    def test_a_cache_whose_classes_moved_is_reparsed_not_raised(
        self, pickled_by_the_previous_build, caplog
    ):
        path = yaml_util._get_schema_pickle_path()
        import os

        os.makedirs(os.path.dirname(path), exist_ok=True)
        blob = pickled_by_the_previous_build(
            lambda grace: {"fingerprint": yaml_util._schema_fingerprint(), "data": {"g": grace}}
        )
        with open(path, "wb") as f:
            f.write(blob)

        with caplog.at_level(logging.WARNING):
            schema = yaml_util._load_schema()
        assert isinstance(schema, dict) and schema, "schema should have been reparsed from YAML"
        assert "ModuleNotFoundError" in caplog.text

    def test_the_fingerprint_changes_with_the_boneio_version(self, monkeypatch):
        """A release that moves a class need not touch a single schema YAML."""
        before = yaml_util._schema_fingerprint()
        monkeypatch.setattr(yaml_util, "__version__", "9.9.9")
        assert yaml_util._schema_fingerprint() != before
