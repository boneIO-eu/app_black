"""Tests for the YAML backend selection and the pickled schema cache."""

import os

import pytest
from yaml import dump, load

from boneio.core.config import yaml_util as yu
from boneio.core.config.yaml_compat import HAS_LIBYAML, FastSafeDumper, FastSafeLoader
from boneio.core.utils import TimePeriod


class TestYamlBackend:
    """The fast backend must stay a drop-in replacement for SafeLoader."""

    def test_backend_flag_is_bool(self):
        assert isinstance(HAS_LIBYAML, bool)

    def test_loader_supports_custom_constructors(self, tmp_path):
        """Custom tags (used for !include/!secret) must work on the C loader."""

        class Loader(FastSafeLoader):
            pass

        Loader.add_constructor("!marker", lambda loader, node: f"got:{node.value}")

        assert load("a: !marker abc", Loader=Loader) == {"a": "got:abc"}

    def test_dumper_supports_custom_representers(self):
        """TimePeriod must still be serialized as a plain string."""
        assert dump({"t": TimePeriod(seconds=30)}, Dumper=yu.TimePeriodDumper, sort_keys=False) == "t: 30s\n"

    def test_boneio_loader_resolves_include(self, tmp_path):
        (tmp_path / "part.yaml").write_text("- id: one\n", encoding="utf-8")
        main = tmp_path / "config.yaml"
        main.write_text("output: !include part.yaml\n", encoding="utf-8")

        assert yu.load_yaml_file(str(main)) == {"output": [{"id": "one"}]}

    def test_dumper_is_a_yaml_dumper(self):
        assert issubclass(yu.TimePeriodDumper, FastSafeDumper)


class TestSchemaPickleCache:
    """The parsed schema is cached on disk to avoid reparsing the YAML."""

    @pytest.fixture(autouse=True)
    def isolated_cache(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
        yu.clear_config_cache(clear_static=True)
        yield
        yu.clear_config_cache(clear_static=True)

    def test_cache_file_is_created_and_reused(self, tmp_path):
        first = yu._load_schema()
        cache_path = yu._get_schema_pickle_path()

        assert os.path.exists(cache_path)
        assert first == yu._load_schema()

    def test_stale_cache_is_ignored(self, tmp_path):
        import pickle

        yu._load_schema()
        cache_path = yu._get_schema_pickle_path()
        with open(cache_path, "wb") as f:
            pickle.dump({"fingerprint": ("stale",), "data": {"bogus": True}}, f)

        schema = yu._load_schema()
        assert "bogus" not in schema
        assert "mqtt" in schema

    def test_corrupt_cache_falls_back_to_yaml(self):
        yu._load_schema()
        with open(yu._get_schema_pickle_path(), "wb") as f:
            f.write(b"not a pickle")

        assert "mqtt" in yu._load_schema()


class TestClearConfigCache:
    """Static package caches must survive ordinary config saves."""

    def test_static_caches_kept_by_default(self):
        schema = yu._get_schema()
        yu.clear_config_cache()
        assert yu._get_schema() is schema

    def test_static_caches_cleared_on_request(self):
        schema = yu._get_schema()
        yu.clear_config_cache(clear_static=True)
        assert yu._get_schema() is not schema
