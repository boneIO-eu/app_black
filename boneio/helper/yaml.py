import logging
from typing import Any
import os
from cerberus import Validator
from boneio.const import COVER, ID, OUTPUT
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
    aa = v.normalized(config_yaml)
    bb = v.validate(aa)
    return aa


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

    def _normalize_coerce_check_actions(self, value):
        _path = self.document_path
        parent = self.root_document[_path[0]][_path[1]]
        keys = value.keys()
        _schema = self.schema["actions"]
        out = {}
        for key in keys:
            _deps = _schema["schema"][key]["dependencies"].items()
            d = next(iter(_deps))
            _parent_key_value = parent[d[0]]
            for _v in d[1]:
                if _v == _parent_key_value:
                    out[key] = value[key]
        return out

    def _normalize_coerce_check_action_def(self, value):
        parent = self.root_document[self.document_path[0]][self.document_path[1]]
        _schema = self.schema["actions"]
        keys = value.keys()
        out = {}
        for key in keys:
            _deps = _schema["schema"][key]["dependencies"].items()
            d = next(iter(_deps))
            _parent_key_value = parent[d[0]]
            for _v in d[1]:
                if _v == _parent_key_value:
                    out[key] = value[key]
        return out

    def _normalize_default_setter_toggle_cover(self, document):
        def get_parent():
            out = self.root_document
            for _p in self.document_path:
                out = out[_p]
            return out

        parent = get_parent()
        if parent["action"] == COVER:
            return "toggle"
