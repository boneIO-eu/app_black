import fnmatch
import logging
import os
import re
from collections import OrderedDict
from typing import Any, Tuple

from cerberus import TypeDefinition, Validator
from yaml import MarkedYAMLError, SafeLoader, YAMLError, load

from boneio.const import COVER, ID, OUTPUT
from boneio.helper.exceptions import ConfigurationException
from boneio.helper.timeperiod import TimePeriod

schema_file = os.path.join(os.path.dirname(__file__), "../schema/schema.yaml")
_LOGGER = logging.getLogger(__name__)

SECRET_YAML = "secrets.yaml"
_SECRET_VALUES = {}


class BoneIOLoader(SafeLoader):
    """Loader which support for include in yaml files."""

    def __init__(self, stream):

        self._root = os.path.split(stream.name)[0]

        super(BoneIOLoader, self).__init__(stream)

    def include(self, node):

        filename = os.path.join(self._root, self.construct_scalar(node))

        with open(filename, "r") as f:
            return load(f, BoneIOLoader)

    def _rel_path(self, *args):
        return os.path.join(self._root, *args)

    def construct_secret(self, node):
        secrets = load_yaml_file(self._rel_path(SECRET_YAML))
        if node.value not in secrets:
            raise MarkedYAMLError(f"Secret '{node.value}' not defined", node.start_mark)
        val = secrets[node.value]
        _SECRET_VALUES[str(val)] = node.value
        return val

    def represent_stringify(self, value):
        return self.represent_scalar(tag="tag:yaml.org,2002:str", value=str(value))

    def construct_include_dir_list(self, node):
        files = filter_yaml_files(_find_files(self._rel_path(node.value), "*.yaml"))
        return [load_yaml_file(f) for f in files]

    def construct_include_dir_merge_list(self, node):
        files = filter_yaml_files(_find_files(self._rel_path(node.value), "*.yaml"))
        merged_list = []
        for fname in files:
            loaded_yaml = load_yaml_file(fname)
            if isinstance(loaded_yaml, list):
                merged_list.extend(loaded_yaml)
        return merged_list

    def construct_include_dir_named(self, node):
        files = filter_yaml_files(_find_files(self._rel_path(node.value), "*.yaml"))
        mapping = OrderedDict()
        for fname in files:
            filename = os.path.splitext(os.path.basename(fname))[0]
            mapping[filename] = load_yaml_file(fname)
        return mapping

    def construct_include_dir_merge_named(self, node):
        files = filter_yaml_files(_find_files(self._rel_path(node.value), "*.yaml"))
        mapping = OrderedDict()
        for fname in files:
            loaded_yaml = load_yaml_file(fname)
            if isinstance(loaded_yaml, dict):
                mapping.update(loaded_yaml)
        return mapping


BoneIOLoader.add_constructor("!include", BoneIOLoader.include)
BoneIOLoader.add_constructor("!secret", BoneIOLoader.construct_secret)
BoneIOLoader.add_constructor(
    "!include_dir_list", BoneIOLoader.construct_include_dir_list
)
BoneIOLoader.add_constructor(
    "!include_dir_merge_list", BoneIOLoader.construct_include_dir_merge_list
)
BoneIOLoader.add_constructor(
    "!include_dir_named", BoneIOLoader.construct_include_dir_named
)
BoneIOLoader.add_constructor(
    "!include_dir_merge_named", BoneIOLoader.construct_include_dir_merge_named
)


def filter_yaml_files(files):
    return [
        f
        for f in files
        if (
            os.path.splitext(f)[1] in (".yaml", ".yml")
            and os.path.basename(f) not in ("secrets.yaml", "secrets.yml")
            and not os.path.basename(f).startswith(".")
        )
    ]


def _is_file_valid(name):
    """Decide if a file is valid."""
    return not name.startswith(".")


def _find_files(directory, pattern):
    """Recursively load files in a directory."""
    for root, dirs, files in os.walk(directory, topdown=True):
        dirs[:] = [d for d in dirs if _is_file_valid(d)]
        for basename in files:
            if _is_file_valid(basename) and fnmatch.fnmatch(basename, pattern):
                filename = os.path.join(root, basename)
                yield filename


def load_yaml_file(filename: str) -> Any:
    with open(filename, "r") as stream:
        try:
            return load(stream, Loader=BoneIOLoader) or OrderedDict()
        except YAMLError as exception:
            raise exception


def load_config_from_string(config_yaml: str):
    schema = load_yaml_file(schema_file)
    v = CustomValidator(schema, purge_unknown=True)
    v.validate(config_yaml)
    if v.errors:
        _LOGGER.error("There are errors in your config %s", v.errors)
    doc = v.normalized(v.document, always_return_document=True)
    # validated = v.validated(document=doc, normalize=True, always_return_document=True)
    # doc = v.normalized(validated, always_return_document=True)
    return doc


def load_config_from_file(config_file: str):
    try:
        config_yaml = load_yaml_file(config_file)
    except FileNotFoundError as err:
        raise ConfigurationException(err)
    if not config_yaml:
        _LOGGER.warn("Missing yaml file. %s", config_file)
        return None
    return load_config_from_string(config_yaml)


def one_of(*values, **kwargs):
    """Validate that the config option is one of the given values.
    :param values: The valid values for this type
    """
    options = ", ".join(f"'{x}'" for x in values)

    def validator(value):
        if value not in values:
            import difflib

            options_ = [str(x) for x in values]
            option = str(value)
            matches = difflib.get_close_matches(option, options_)
            if matches:
                matches_str = ", ".join(f"'{x}'" for x in matches)
                raise ConfigurationException(
                    f"Unknown value '{value}', did you mean {matches_str}?"
                )
            raise ConfigurationException(
                f"Unknown value '{value}', valid options are {options}."
            )
        return value

    return validator


timeperiod_type = TypeDefinition("timeperiod", (TimePeriod,), ())


class CustomValidator(Validator):
    """Custom validator of cerberus"""

    types_mapping = Validator.types_mapping.copy()
    types_mapping["timeperiod"] = timeperiod_type

    def _lookup_field(self, path: str) -> Tuple:
        """
        Implement relative paths with dot (.) notation, following Python
        guidelines: https://www.python.org/dev/peps/pep-0328/#guido-s-decision
        - A single leading dot indicates a relative import
        starting with the current package.
        - Two or more leading dots give a relative import to the parent(s)
        of the current package, one level per dot after the first
        Return: Tuple(dependency_name: str, dependency_value: Any)
        """
        # Python relative imports use a single leading dot
        # for the current level, however no dot in Cerberus
        # does the same thing, thus we need to check 2 or more dots
        if path.startswith(".."):
            parts = path.split(".")
            dot_count = path.count(".")
            context = self.root_document

            for key in self.document_path[:dot_count]:
                context = context[key]

            context = context.get(parts[-1])

            return parts[-1], context

        else:
            return super()._lookup_field(path)

    def _check_with_output_id_uniqueness(self, field, value):
        """Check if outputs ids are unique."""
        all_ids = [x[ID] for x in self.document[OUTPUT]]
        if len(all_ids) != len(set(all_ids)):
            self._error(field, "Output IDs are not unique.")

    def _normalize_coerce_to_bool(self, value):
        return True

    def _normalize_coerce_lower(self, value):
        return str(value).lower()

    def _normalize_coerce_upper(self, value):
        return str(value).upper()

    def _normalize_coerce_actions_output(self, value):
        return str(value).lower()

    def _normalize_coerce_str(self, value):
        return str(value)

    def _normalize_coerce_check_actions(self, value):
        _path = self.document_path
        parent = self.root_document[_path[0]][_path[1]]
        keys = value.keys()
        _schema = self.schema["actions"]
        out = {}
        for key in keys:
            _deps = _schema["schema"][key]["dependencies"].items()
            d = next(iter(_deps))
            _parent_key_value = parent.get(d[0], "switch")
            for _v in d[1]:
                if _v == _parent_key_value:
                    out[key] = value[key]
        return out

    def _normalize_coerce_positive_time_period(self, value) -> TimePeriod:
        """Validate and transform time period with time unit and integer value."""
        if isinstance(value, int):
            raise ConfigurationException(
                f"Don't know what '{value}' means as it has no time *unit*! Did you mean '{value}s'?"
            )
        if isinstance(value, TimePeriod):
            value = str(value)
        if not isinstance(value, str):
            raise ConfigurationException("Expected string for time period with unit.")

        unit_to_kwarg = {
            "us": "microseconds",
            "microseconds": "microseconds",
            "ms": "milliseconds",
            "milliseconds": "milliseconds",
            "s": "seconds",
            "sec": "seconds",
            "secs": "seconds",
            "seconds": "seconds",
            "min": "minutes",
            "minutes": "minutes",
            "h": "hours",
            "hours": "hours",
            "d": "days",
            "days": "days",
        }

        match = re.match(r"^([-+]?[0-9]*\.?[0-9]*)\s*(\w*)$", value)
        if match is None:
            raise ConfigurationException(f"Expected time period with unit, got {value}")
        kwarg = unit_to_kwarg[one_of(*unit_to_kwarg)(match.group(2))]

        return TimePeriod(**{kwarg: float(match.group(1))})

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
