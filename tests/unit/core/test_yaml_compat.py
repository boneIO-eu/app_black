"""Tests for the YAML backend selection and the pickled schema cache."""


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
