from typing import Any
import os
from cerberus import Validator
from boneio.const import ID, OUTPUT
from yaml import load, YAMLError, SafeLoader


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


class CustomValidator(Validator):
    """Custom validator of cerberus"""

    def _check_with_output_id_uniqueness(self, field, value):
        """Check if outputs ids are unique."""
        all_ids = [x[ID] for x in self.document[OUTPUT]]
        if len(all_ids) != len(set(all_ids)):
            self._error(field, "Output IDs are not unique.")

    def _normalize_coerce_to_bool(self, value):
        return True
