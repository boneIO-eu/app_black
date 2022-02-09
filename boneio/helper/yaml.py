import logging
from typing import Any
import os
from cerberus import Validator
from boneio.const import ID, OUTPUT
from yaml import load, YAMLError, SafeLoader

schema_file = os.path.join(os.path.dirname(__file__), "../schema/schema.yaml")
_LOGGER = logging.getLogger(__name__)


class Loader(SafeLoader):
    """Loader which support for include in yaml files."""

    def __init__(self, stream):

        self._root = os.path.split(stream.name)[0]

        super(Loader, self).__init__(stream)

    def include(self, node):

        filename = os.path.join(self._root, self.construct_scalar(node))

        with open(filename, "r") as f:
            return load(f, Loader)


Loader.add_constructor("!include", Loader.include)


def load_yaml_file(filename: str) -> Any:
    with open(filename, "r") as stream:
        try:
            return load(stream, Loader=Loader)
        except YAMLError as exception:
            raise exception


def load_config_from_string(config_yaml: str):
    schema = load_yaml_file(schema_file)
    v = CustomValidator(schema, purge_unknown=True)
    return v.normalized(config_yaml)


def load_config_from_file(config_file: str):
    config_yaml = load_yaml_file(config_file)
    if not config_yaml:
        _LOGGER.info("Missing file.")
        return None
    return load_config_from_string(config_yaml)


class CustomValidator(Validator):
    """Custom validator of cerberus"""

    def _check_with_output_id_uniqueness(self, field, value):
        """Check if outputs ids are unique."""
        all_ids = [x[ID] for x in self.document[OUTPUT]]
        if len(all_ids) != len(set(all_ids)):
            self._error(field, "Output IDs are not unique.")

    def _normalize_coerce_to_bool(self, value):
        return True
