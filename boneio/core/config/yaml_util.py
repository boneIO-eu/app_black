import fnmatch
import logging
import os
import re
from collections import OrderedDict
from typing import Any

from cerberus import TypeDefinition, Validator
from yaml import MarkedYAMLError, SafeLoader, YAMLError, dump, load

from boneio.const import OUTPUT
from boneio.core.utils import TimePeriod
from boneio.exceptions import ConfigurationException

schema_file = os.path.join(os.path.dirname(__file__), "../../schema/schema.yaml")
_LOGGER = logging.getLogger(__name__)

SECRET_YAML = "secrets.yaml"
_SECRET_VALUES = {}

# Cache for schema to avoid loading it multiple times (saves ~2-3s per config load)
_SCHEMA_CACHE = None
# Cache for board configs to avoid loading them multiple times
_BOARD_CONFIG_CACHE = {}


def _get_schema():
    """Get schema from cache or load it if not cached."""
    global _SCHEMA_CACHE
    if _SCHEMA_CACHE is None:
        _LOGGER.debug("Loading schema from file (first time)")
        _SCHEMA_CACHE = load_yaml_file(schema_file)
    return _SCHEMA_CACHE


def _get_board_config(board_file: str):
    """Get board config from cache or load it if not cached."""
    global _BOARD_CONFIG_CACHE
    if board_file not in _BOARD_CONFIG_CACHE:
        _LOGGER.debug(f"Loading board config from file: {board_file}")
        _BOARD_CONFIG_CACHE[board_file] = load_yaml_file(board_file)
    return _BOARD_CONFIG_CACHE[board_file]


def clear_config_cache():
    """Clear all cached YAML configs.
    
    Use this when schema or board config files have been modified
    and you want to force reload without restarting the process.
    
    Note: In production, cache is automatically cleared on process restart.
    """
    global _SCHEMA_CACHE, _BOARD_CONFIG_CACHE
    _SCHEMA_CACHE = None
    _BOARD_CONFIG_CACHE.clear()
    _LOGGER.info("Config cache cleared")


class BoneIOLoader(SafeLoader):
    """Loader which support for include in yaml files."""

    def __init__(self, stream):
        # Type: ignore[attr-defined] - stream may not have name attribute
        self._root = os.path.split(stream.name)[0] if hasattr(stream, 'name') else "."  # type: ignore[attr-defined]
        super().__init__(stream)

    def include(self, node):

        filename = os.path.join(self._root, self.construct_scalar(node))

        with open(filename) as f:
            return load(f, BoneIOLoader)

    def _rel_path(self, *args):
        return os.path.join(self._root, *args)

    def construct_secret(self, node):
        secrets = load_yaml_file(self._rel_path(SECRET_YAML))
        if node.value not in secrets:
            raise MarkedYAMLError(
                f"Secret '{node.value}' not defined", node.start_mark
            )
        val = secrets[node.value]
        _SECRET_VALUES[str(val)] = node.value
        return val

    def represent_stringify(self, value):
        # Type: ignore[attr-defined] - represent_scalar is inherited from SafeLoader
        return self.represent_scalar(  # type: ignore[attr-defined]
            tag="tag:yaml.org,2002:str", value=str(value)
        )

    def construct_include_dir_list(self, node):
        files = filter_yaml_files(
            _find_files(self._rel_path(node.value), "*.yaml")
        )
        return [load_yaml_file(f) for f in files]

    def construct_include_dir_merge_list(self, node):
        files = filter_yaml_files(
            _find_files(self._rel_path(node.value), "*.yaml")
        )
        merged_list = []
        for fname in files:
            loaded_yaml = load_yaml_file(fname)
            if isinstance(loaded_yaml, list):
                merged_list.extend(loaded_yaml)
        return merged_list

    def construct_include_dir_named(self, node):
        files = filter_yaml_files(
            _find_files(self._rel_path(node.value), "*.yaml")
        )
        mapping = OrderedDict()
        for fname in files:
            filename = os.path.splitext(os.path.basename(fname))[0]
            mapping[filename] = load_yaml_file(fname)
        return mapping

    def construct_include_dir_merge_named(self, node):
        files = filter_yaml_files(
            _find_files(self._rel_path(node.value), "*.yaml")
        )
        mapping = OrderedDict()
        for fname in files:
            loaded_yaml = load_yaml_file(fname)
            if isinstance(loaded_yaml, dict):
                mapping.update(loaded_yaml)
        return mapping

    def construct_include_files(self, node):
        files = os.path.join(self._root, self.construct_scalar(node)).split()
        merged_list = []
        for fname in files:
            loaded_yaml = load_yaml_file(fname.strip())
            if isinstance(loaded_yaml, list):
                merged_list.extend(loaded_yaml)
        return merged_list


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
BoneIOLoader.add_constructor(
    "!include_files", BoneIOLoader.construct_include_files
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
    with open(filename) as stream:
        try:
            return load(stream, Loader=BoneIOLoader) or OrderedDict()
        except YAMLError as exception:
            msg = ""
            # Type: ignore[attr-defined] - YAMLError attributes are dynamic
            if hasattr(exception, "problem_mark"):  # type: ignore[attr-defined]
                mark = exception.problem_mark  # type: ignore[attr-defined]
                msg = f" at line {mark.line + 1} column {mark.column + 1}"
                if hasattr(exception, "context") and exception.context is not None:  # type: ignore[attr-defined]
                    problem = getattr(exception, "problem", "Unknown error")  # type: ignore[attr-defined]
                    context = getattr(exception, "context", "")  # type: ignore[attr-defined]
                    msg = ('  parser says\n' + str(exception.problem_mark) + '\n  ' +  # type: ignore[attr-defined]
                        str(problem) + ' ' + str(context) +
                        '\nPlease correct data and retry.')
            raise ConfigurationException(f"Error loading yaml{msg}") from exception


def get_board_config_path(board_name: str, version: str) -> str:
    """Get the appropriate board configuration file path based on version."""
    base_dir = os.path.join(os.path.dirname(__file__), "../../boards")
    version_dir = os.path.join(base_dir, version)
    version_specific_file = os.path.join(version_dir, f"{board_name}.yaml")
    
    if not os.path.exists(version_dir):
        raise ConfigurationException(
            f"Board configurations for version {version} not found. "
            f"Expected directory: {version_dir}"
        )
    
    if os.path.exists(version_specific_file):
        return version_specific_file
        
    raise ConfigurationException(
        f"Board configuration '{board_name}' for version {version} not found. "
        f"Expected file: {version_specific_file}"
    )


def normalize_board_name(name: str) -> str:
    """Normalize board name to a standard format.
    
    Examples:
        32x10a, 32x10A, 32x10 -> 32_10
        32x5a, 32x5A, 32x5 -> 32_5
        cover -> cover
        cover mix, cm -> cover_mix
        24x16A, 24x16, 24 -> 24_16
    """
    if not name:
        return name

    name = name.lower().strip()
    
    # Handle cover mix variations
    if name in ('cm', 'cover mix', 'covermix', "cover_mix"):
        return 'cover_mix'
    
    # Handle simple cover case
    if name == 'cover':
        return 'cover'
    
    # Handle 32x5A variations (must check before 32x10 since both start with 32)
    if name in ('32x5a', '32x5'):
        return '32_5'
    
    # Handle 32x10A variations (default for 32 without suffix)
    if name.startswith('32'):
        return '32_10'
    
    # Handle 24x16A variations
    if name.startswith('24'):
        return '24_16'
    
    return name


def normalize_version(version: str) -> str:
    """Normalize version to major.minor format.
    
    Examples:
        0.7.1 -> 0.7
        0.8.2 -> 0.8
        0.9   -> 0.9
    """
    if not version:
        return version
    
    # Split by dot and take only the first two parts (major.minor)
    parts = version.split('.')
    if len(parts) >= 2:
        return f"{parts[0]}.{parts[1]}"
    return version


def merge_board_config(config: dict) -> dict:
    """Merge predefined board configuration with user config."""
    if not config.get("boneio", {}).get("device_type"):
        return config

    board_name = normalize_board_name(config["boneio"]["device_type"])
    version = normalize_version(config["boneio"]["version"])
    config["boneio"]["version"] = version
    
    try:
        board_file = get_board_config_path(f"output_{board_name}", version)
        input_file = get_board_config_path("input", version)
        board_config = _get_board_config(board_file)  # Use cache
        input_config = _get_board_config(input_file)  # Use cache
        if not board_config:
            raise ConfigurationException(f"Bottom board configuration file {board_file} is empty")
    except FileNotFoundError:
        raise ConfigurationException(
            f"Board configuration for {board_name} version {version} not found"
        )
    _LOGGER.debug(f"Loaded board configuration: {board_name}")

    # Copy MCP configuration if not already defined
    if "mcp23017" not in config and "mcp23017" in board_config:
        config["mcp23017"] = board_config["mcp23017"]

    # Process outputs
    if board_name == "cover" and "output" not in config:
        output_mapping = board_config.get("output_mapping", {})
        config["output"] = []
        for boneio_output, mapped_output in output_mapping.items():
            output = {"id": boneio_output, **mapped_output}
            config["output"].append(output)
    if "output" in config:
        output_mapping = board_config.get("output_mapping", {})
        for output in config["output"]:
            if "boneio_output" in output:
                boneio_output = output["boneio_output"].lower()
                mapped_output = output_mapping.get(boneio_output)
                if not mapped_output:
                    raise ConfigurationException(
                        f"Output mapping '{output['boneio_output']}' not found in board configuration"
                    )
                # Merge mapped output with user config, preserving user-specified values
                output.update({k: v for k, v in mapped_output.items() if k not in output})
    if "event" or "binary_sensor" in config:
        input_mapping = input_config.get("input_mapping", {})
        for input in config.get("event", []):
            if "boneio_input" in input:
                boneio_input = input["boneio_input"].lower()
                mapped_input = input_mapping.get(boneio_input)
                if not mapped_input:
                    raise ConfigurationException(
                        f"Input mapping '{input['boneio_input']}' not found in board configuration"
                    )
                # Merge mapped output with user config, preserving user-specified values
                input.update({k: v for k, v in mapped_input.items()})

        for input in config.get("binary_sensor", []):
            if "boneio_input" in input:
                boneio_input = input["boneio_input"].lower()
                mapped_input = input_mapping.get(boneio_input)
                if not mapped_input:
                    raise ConfigurationException(
                        f"Input mapping '{input['boneio_input']}' not found in board configuration"
                    )
                # Merge mapped output with user config, preserving user-specified values
                input.update({k: v for k, v in mapped_input.items()})
    return config


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

    # Type: ignore[attr-defined] - types_mapping is inherited from Validator
    types_mapping = Validator.types_mapping.copy()  # type: ignore[attr-defined]
    types_mapping["timeperiod"] = timeperiod_type

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.allow_unknown = True

    def _validate_case_insensitive(self, case_insensitive, field, value):
        """Validate field allowing any case but check against lowercase values.
        
        The rule's arguments are validated against this schema:
        {'type': 'boolean'}
        """
        if not isinstance(value, str):
            self._error(field, "must be a string")  # type: ignore[attr-defined]
            return

        allowed = self.schema[field].get('allowed')  # type: ignore[attr-defined]
        if allowed and value.lower() not in [a.lower() for a in allowed]:
            self._error(field, f"unallowed value {value}")  # type: ignore[attr-defined]

    def _validate_required_if(self, required_if, field, value):
        """Validate that a field is required if a condition is met.
        
        The rule's arguments are validated against this schema:
        {'type' : 'dict'}
        """
        if not required_if:
            return

        for key, values in required_if.items():
            if key not in self.document:  # type: ignore[attr-defined]
                continue

            doc_value = self.document[key]  # type: ignore[attr-defined]
            if isinstance(doc_value, str):
                doc_value = doc_value.lower()
            if doc_value in [v.lower() if isinstance(v, str) else v for v in values]:
                if field not in self.document:  # type: ignore[attr-defined]
                    self._error(field, f"required when {key} is {doc_value}")  # type: ignore[attr-defined]

    def _validate_forbidden_if(self, forbidden_if, field, value):
        """Validate that a field is forbidden if a condition is met.
        
        The rule's arguments are validated against this schema:
        {'type': 'dict'}
        """
        if not forbidden_if:
            return
        default_value = self.schema[field].get("default")  # type: ignore[attr-defined]
        for key, values in forbidden_if.items():
            if key not in self.document:  # type: ignore[attr-defined]
                continue

            doc_value = self.document[key]  # type: ignore[attr-defined]
            if isinstance(doc_value, str):
                doc_value = doc_value.lower()
            
            if doc_value in [v.lower() if isinstance(v, str) else v for v in values]:
                if field in self.document and value != default_value:  # type: ignore[attr-defined]
                    self._error(field, f"forbidden when {key} is {doc_value}")  # type: ignore[attr-defined]

    def _normalize_coerce_action_field(self, value):
        """Handle conditional defaults for action fields."""
        action = self.document.get('action', '').lower()  # type: ignore[attr-defined]
        field_name = self.schema_path[-1]  # type: ignore[attr-defined]
        if value is None:
            if (field_name == 'action_cover' and action == 'cover') or \
               (field_name == 'action_output' and action == 'output'):
                return 'TOGGLE'
            return None
        return str(value).upper()

    def _normalize_coerce_lower(self, value):
        """Convert string to lowercase."""
        if isinstance(value, str):
            return value.lower()
        return value

    def _normalize_coerce_upper(self, value):
        """Convert string to uppercase."""
        if isinstance(value, str):
            return value.upper()
        return value

    def _normalize_coerce_str(self, value):
        """Convert value to string."""
        return str(value)

    def _normalize_coerce_version_to_str(self, value):
        """Convert value to string."""
        _v = str(value)
        return _v

    def _normalize_coerce_actions_output(self, value):
        return str(value).upper()

    def _normalize_coerce_length_to_meters(self, value) -> float | None:
        """
        Convert a length value to meters.
        Accepts:
        - Numeric values (int, float) - assumed to be in meters
        - Strings with units: 'm', 'cm', 'mm'
        Examples:
        5 -> 5.0
        '5m' -> 5.0
        '500cm' -> 5.0
        '2000mm' -> 2.0
        """
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        value = str(value).strip().lower()
        match = re.match(r"^([-+]?[0-9]*\.?[0-9]*)\s*(m|cm|mm)?$", value)
        if not match:
            raise ValueError(f"Invalid length value: {value}")
        num = float(match.group(1))
        unit = match.group(2) or "m"
        if unit == "m":
            multiplier = 1.0
        elif unit == "cm":
            multiplier = 0.01
        elif unit == "mm":
            multiplier = 0.001
        else:
            raise ValueError(f"Unknown unit for length value: {unit}")
        result = num * multiplier
        _LOGGER.debug(f"Parsed length value '{value}' as {result} m")
        return result

    def _normalize_coerce_positive_time_period(self, value) -> TimePeriod:
        """Validate and transform time period with time unit and integer value."""
        if isinstance(value, int):
            raise ConfigurationException(
                f"Don't know what '{value}' means as it has no time *unit*! Did you mean '{value}s'?"
            )
        if isinstance(value, TimePeriod):
            value = str(value)
        if not isinstance(value, str):
            raise ConfigurationException(
                "Expected string for time period with unit."
            )
        
        # Handle empty string
        if not value or not value.strip():
            raise ConfigurationException(
                "Time period cannot be empty. Expected value with unit like '30s' or '1000ms'."
            )

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
            "mins": "minutes",
            "minutes": "minutes",
            "h": "hours",
            "hours": "hours",
            "d": "days",
            "days": "days",
        }

        match = re.match(r"^([-+]?[0-9]*\.?[0-9]*)\s*(\w*)$", value)
        if match is None:
            raise ConfigurationException(
                f"Expected time period with unit, got {value}"
            )
        kwarg = unit_to_kwarg[one_of(*unit_to_kwarg)(match.group(2))]
        return TimePeriod(**{kwarg: float(match.group(1))})

    def _lookup_field(self, path: str) -> tuple:
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
            context = self.root_document  # type: ignore[attr-defined]

            for key in self.document_path[:dot_count]:  # type: ignore[attr-defined]
                context = context[key]

            context = context.get(parts[-1])

            return parts[-1], context

        else:
            return super()._lookup_field(path)  # type: ignore[attr-defined]

    def _check_with_output_id_uniqueness(self, field, value):
        """Check if outputs ids are unique if they exist."""
        if self.document[OUTPUT] is not None:  # type: ignore[attr-defined]
            all_ids = [x.get('id') for x in self.document[OUTPUT] if x.get('id')]  # type: ignore[attr-defined]
            if len(all_ids) != len(set(all_ids)):
                self._error(field, "Output IDs are not unique.")  # type: ignore[attr-defined]

    def _check_with_output_id_exists(self, field, value):
        """Check if output id exists or boneio_output is provided."""
        if value:
            for i, output in enumerate(value):
                if "id" not in output and "boneio_output" not in output:
                    self._error(field, f"Output at index {i} must have either 'id' or 'boneio_output' defined.")  # type: ignore[attr-defined]

    def _check_with_input_id_exists(self, field, value):
        """Check if input id exists or boneio_input is provided."""
        if value:
            for i, input_item in enumerate(value):
                if "id" not in input_item and "boneio_input" not in input_item:
                    self._error(field, f"Input at index {i} must have either 'id' or 'boneio_input' defined.")  # type: ignore[attr-defined]

    def _normalize_coerce_to_bool(self, value):
        return True

    def _normalize_coerce_remove_space(self, value):
        return str(value).replace(" ", "")

    def _normalize_coerce_power_value_to_watts(self, value):
        """
        Parse a power or energy value and return it in watts (W).
        Accepts:
        - Numeric values (int, float)
        - Strings with units: 'W', 'kW', 'kWh', 'MW', 'mW', etc.
        - For 'kWh' (kilowatt-hour), returns equivalent average power in W (1kWh = 1000W for 1h)
        - For 'kW', 'MW', etc., converts to W
        Example:
            9 -> 9.0
            '9W' -> 9.0
            '1kW' -> 1000.0
            '1kWh' -> 1000.0
            '2.5MW' -> 2500000.0
        Returns float (watts) or raises ValueError if invalid.
        """
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if not isinstance(value, str):
            raise ValueError(f"Unsupported type for power value: {type(value)}")
        value = value.strip().replace(' ', '').lower()
        pattern = r"^([-+]?[0-9]*\.?[0-9]+)([a-z]*)$"
        match = re.match(pattern, value)
        if not match:
            _LOGGER.warning(f"Could not parse power value: {value}")
            raise ValueError(f"Could not parse power value: {value}")
        num = float(match.group(1))
        unit = match.group(2) or "w"
        if unit in ('w', ''):
            multiplier = 1.0
        elif unit == 'kw':
            multiplier = 1000.0
        elif unit == 'mw':
            multiplier = 1_000_000.0
        elif unit == 'gw':
            multiplier = 1_000_000_000.0
        elif unit == 'mw':
            multiplier = 1_000_000.0
        elif unit == 'kwh':
            # 1 kWh = 1000 W (for 1h). For config, treat as 1000W average.
            multiplier = 1000.0
        elif unit == 'mwh':
            multiplier = 1_000_000.0
        elif unit == 'gwh':
            multiplier = 1_000_000_000.0
        elif unit == 'mw':
            multiplier = 1_000_000.0
        elif unit == 'wh':
            multiplier = 1.0
        elif unit == 'mw':
            multiplier = 1_000_000.0
        elif unit == 'mw':
            multiplier = 1_000_000.0
        elif unit == 'mw':
            multiplier = 1_000_000.0
        elif unit == 'mw':
            multiplier = 1_000_000.0
        elif unit == 'mw':
            multiplier = 1_000_000.0
        elif unit == 'mw':
            multiplier = 1_000_000.0
        else:
            _LOGGER.warning(f"Unknown unit for power value: {unit}")
            raise ValueError(f"Unknown unit for power value: {unit}")
        result = num * multiplier
        _LOGGER.debug(f"Parsed power value '{value}' as {result} W")
        return result

    def _normalize_coerce_volume_flow_rate_to_lph(self, value):
        """
        Parse a volume flow rate value and return it in liters per minute (L/min).
        Accepts:
        - Numeric values (int, float)
        - Strings with units: 'L/min', 'L/h', etc.
        Example:
            9 -> 9.0
            '9L/min' -> 9.0
            '1L/h' -> 1000.0
        Returns float (L/h) or raises ValueError if invalid.
        """
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if not isinstance(value, str):
            raise ValueError(f"Unsupported type for volume flow rate value: {type(value)}")
        value = value.strip().replace(' ', '').lower()
        pattern = r"^([-+]?[0-9]*\.?[0-9]+)\s*([a-zA-Z/]*)$"
        match = re.match(pattern, value)
        if not match:
            _LOGGER.warning(f"Could not parse volume flow rate value: {value}")
            raise ValueError(f"Could not parse volume flow rate value: {value}")
        num = float(match.group(1))
        unit = match.group(2) or "lph"
        if unit in ('lph', 'l/h', ''):
            multiplier = 1.0
        elif unit in ('lpm', 'l/min'):
            multiplier = 60.0
        else:
            _LOGGER.warning(f"Unknown unit for volume flow rate value: {unit}")
            raise ValueError(f"Unknown unit for volume flow rate value: {unit}")
        result = num * multiplier
        _LOGGER.debug(f"Parsed volume flow rate value '{value}' as {result} L/h")
        return result



def _migrate_config(doc: dict, config_file: str | None = None) -> tuple[dict, bool]:
    """
    Apply configuration migrations for backward compatibility.
    
    Args:
        doc: Configuration document to migrate
        config_file: Optional path to config file for persisting migrations
        
    Returns:
        Tuple of (migrated configuration document, whether migrations were applied)
    """
    migrated = False
    migrations_applied = []
    
    # Migration: nginx_proxy_port -> proxy_port in web section
    if "web" in doc and isinstance(doc["web"], dict):
        if "nginx_proxy_port" in doc["web"]:
            _LOGGER.info("Migrating 'web.nginx_proxy_port' to 'web.proxy_port'")
            doc["web"]["proxy_port"] = doc["web"].pop("nginx_proxy_port")
            migrated = True
            migrations_applied.append("web.nginx_proxy_port -> web.proxy_port")
    
    # Migration: modbus_sensors -> modbus_devices
    if "modbus_sensors" in doc:
        _LOGGER.warning("Modbus sensors are renamed to modbus_devices. Please update your config.")
        migrated = True
        migrations_applied.append("modbus_sensors -> modbus_devices")
    
    if migrated:
        _LOGGER.info("Configuration migrations applied: %s", ", ".join(migrations_applied))
        
        # Persist migrations to config file if provided
        if config_file:
            try:
                _persist_migrations(config_file, doc, migrations_applied)
            except Exception as e:
                _LOGGER.error("Failed to persist migrations to config file: %s", e)
    
    return doc, migrated


def _persist_migrations(config_file: str, migrated_doc: dict, migrations: list[str]) -> None:
    """
    Persist migrated configuration back to YAML file.
    
    Args:
        config_file: Path to config file
        migrated_doc: Migrated configuration document
        migrations: List of applied migrations for logging
    """
    import os
    from pathlib import Path
    
    config_dir = Path(config_file).parent
    
    # Read original file to preserve structure and !include directives
    with open(config_file, 'r', encoding='utf-8') as f:
        original_lines = f.readlines()
    
    # For web.nginx_proxy_port -> web.proxy_port migration
    if any("nginx_proxy_port" in m for m in migrations):
        updated_lines = []
        for line in original_lines:
            # Replace nginx_proxy_port with proxy_port in the line
            if "nginx_proxy_port:" in line:
                indent = len(line) - len(line.lstrip())
                value_part = line.split("nginx_proxy_port:", 1)[1]
                updated_line = " " * indent + "proxy_port:" + value_part
                updated_lines.append(updated_line)
                _LOGGER.info("Replaced line in config file: %s -> %s", line.rstrip(), updated_line.rstrip())
            else:
                updated_lines.append(line)
        
        # Write back to file
        with open(config_file, 'w', encoding='utf-8') as f:
            f.writelines(updated_lines)
        
        _LOGGER.info("Persisted migrations to config file: %s", config_file)


def load_config_from_string(config_str: str) -> dict:
    """Load config from string."""
    schema = _get_schema()  # Use cached schema instead of loading every time
    v = CustomValidator(schema, purge_unknown=True)

    # First normalize the document
    doc = v.normalized(config_str, always_return_document=True)  # type: ignore[attr-defined]
    
    # Apply migrations (without persisting - that happens in load_config_from_file)
    doc, _ = _migrate_config(doc, config_file=None)
    
    # Then merge board config
    merged_doc = merge_board_config(doc)
    
    # Finally validate
    if not v.validate(merged_doc, schema):  # type: ignore[attr-defined]
        error_msg = "Configuration validation failed:\n"
        for field, errors in v.errors.items():  # type: ignore[attr-defined]
            error_lines = []
            if "line" in v.errors[field][0]:  # type: ignore[attr-defined]
                error_lines = [
                    f"{v.errors[field][0]['line']+1}: {line}"  # type: ignore[attr-defined]
                    for line in config_str.splitlines()[v.errors[field][0]["line"]-1:v.errors[field][0]["line"]+1]  # type: ignore[attr-defined]
                ]
            error_msg += f"\n- {field}: {errors}\n{', '.join(error_lines)}"
        raise ConfigurationException(error_msg)
    
    return merged_doc


def load_config_from_file(config_file: str):
    try:
        config_yaml = load_yaml_file(config_file)
    except FileNotFoundError as err:
        raise ConfigurationException(err)
    if not config_yaml:
        _LOGGER.warning("Missing yaml file. %s", config_file)
        return None
    
    # Load and validate config
    schema = _get_schema()
    v = CustomValidator(schema, purge_unknown=True)
    
    # First normalize the document
    doc = v.normalized(config_yaml, always_return_document=True)  # type: ignore[attr-defined]
    
    # Apply migrations and persist to file if needed
    doc, migrations_applied = _migrate_config(doc, config_file=config_file)
    
    # Then merge board config
    merged_doc = merge_board_config(doc)
    
    # Finally validate
    if not v.validate(merged_doc, schema):  # type: ignore[attr-defined]
        error_msg = "Configuration validation failed:\n"
        for field, errors in v.errors.items():  # type: ignore[attr-defined]
            error_lines = []
            if "line" in v.errors[field][0]:  # type: ignore[attr-defined]
                error_lines = [
                    f"{v.errors[field][0]['line']+1}: {line}"  # type: ignore[attr-defined]
                    for line in config_yaml.splitlines()[v.errors[field][0]["line"]-1:v.errors[field][0]["line"]+1]  # type: ignore[attr-defined]
                ]
            error_msg += f"\n- {field}: {errors}\n{', '.join(error_lines)}"
        raise ConfigurationException(error_msg)
    
    return merged_doc


def strip_default_values(data: Any, schema: dict | None = None, section: str | None = None) -> Any:
    """
    Remove fields with default values from data to keep YAML clean.
    Uses Cerberus schema.yaml for default values.
    
    Args:
        data: The data to clean (dict, list, or primitive)
        schema: Optional Cerberus schema dict (if not provided, will load from schema.yaml)
        section: Optional section name to find schema
        
    Returns:
        Cleaned data with default values removed
    """
    
    def get_defaults_from_cerberus_schema(schema_obj: dict) -> dict:
        """Extract default values from Cerberus schema."""
        defaults = {}
        if isinstance(schema_obj, dict):
            # For list schemas, get the item schema
            if schema_obj.get('type') == 'list' and 'schema' in schema_obj:
                item_schema = schema_obj['schema']
                if isinstance(item_schema, dict) and item_schema.get('type') == 'dict':
                    # Get defaults from dict schema
                    dict_schema = item_schema.get('schema', {})
                    for key, prop in dict_schema.items():
                        if isinstance(prop, dict) and 'default' in prop:
                            defaults[key] = prop['default']
            # For dict schemas
            elif 'schema' in schema_obj:
                for key, prop in schema_obj['schema'].items():
                    if isinstance(prop, dict) and 'default' in prop:
                        defaults[key] = prop['default']
        return defaults
    
    def clean_dict(obj: dict, defaults: dict) -> dict:
        """Remove keys with default values from dict."""
        cleaned = {}
        for key, value in obj.items():
            # Special handling for nested structures
            if key == 'actions' and isinstance(value, dict):
                # Clean actions recursively
                cleaned_actions = {}
                for action_type, action_list in value.items():
                    if isinstance(action_list, list):
                        cleaned_list = []
                        for action_item in action_list:
                            if isinstance(action_item, dict):
                                # Get defaults for action items
                                action_defaults = {
                                    'action_cover': 'TOGGLE',
                                    'action_output': 'TOGGLE',
                                    'data': {}
                                }
                                cleaned_action = clean_dict(action_item, action_defaults)
                                # Only add if action field exists (required)
                                if 'action' in cleaned_action or cleaned_action:
                                    cleaned_list.append(cleaned_action)
                        if cleaned_list:
                            cleaned_actions[action_type] = cleaned_list
                if cleaned_actions:
                    cleaned[key] = cleaned_actions
            elif key == 'data' and value == {}:
                # Skip empty data objects
                continue
            elif key in defaults and value == defaults[key]:
                # Skip if value equals default
                continue
            elif isinstance(value, dict):
                # Recursively clean nested dicts
                cleaned_value = clean_dict(value, {})
                if cleaned_value:  # Only add if not empty
                    cleaned[key] = cleaned_value
            elif isinstance(value, list):
                # Clean list items
                cleaned_list = []
                for item in value:
                    if isinstance(item, dict):
                        cleaned_item = clean_dict(item, defaults)
                        if cleaned_item:
                            cleaned_list.append(cleaned_item)
                    else:
                        cleaned_list.append(item)
                if cleaned_list:
                    cleaned[key] = cleaned_list
            else:
                # Keep non-default values
                cleaned[key] = value
        return cleaned
    
    # Get schema for section
    defaults: dict = {}
    if section:
        # Load Cerberus schema if not provided
        loaded_schema = schema if schema is not None else _get_schema()
        
        # Get section schema from Cerberus
        if loaded_schema:
            section_schema = loaded_schema.get(section, {})
            defaults = get_defaults_from_cerberus_schema(section_schema)
    
    # Process data
    if isinstance(data, list):
        return [clean_dict(item, defaults) if isinstance(item, dict) else item for item in data]
    elif isinstance(data, dict):
        return clean_dict(data, defaults)
    else:
        return data


def update_config_section(config_file: str, section: str, data: dict | list) -> dict:
    """
    Update content of a configuration section with intelligent !include handling.
    
    Args:
        config_file: Path to the main config.yaml file
        section: Name of the section to update
        data: New data for the section (dict for single-value sections, list for array sections)
        
    Returns:
        dict: Status response with success/error message
    """
    import os
    from pathlib import Path
    
    config_dir = Path(config_file).parent
    
    _LOGGER.info(f"Updating section '{section}' with data: {data}")
    
    # Special handling for mcp23017 - convert hex strings to integers
    # This ensures YAML writes them as integers which are then read back as hex
    if section == 'mcp23017' and isinstance(data, list):
        for entry in data:
            if isinstance(entry, dict) and 'address' in entry:
                addr = entry['address']
                if isinstance(addr, str):
                    if addr.startswith('0x') or addr.startswith('0X'):
                        entry['address'] = int(addr, 16)
                    else:
                        try:
                            entry['address'] = int(addr, 10)
                        except ValueError:
                            pass  # Keep as string if conversion fails
    
    # Strip default values to keep YAML clean
    cleaned_data = strip_default_values(data, {}, section)
    _LOGGER.info(f"Cleaned data (defaults removed): {cleaned_data}")
    
    # Custom YAML loader that preserves !include tags
    class IncludeLoader(SafeLoader):
        pass
    
    def include_constructor(loader, node):
        """Constructor for !include tag that preserves the tag info."""
        filename = loader.construct_scalar(node)
        # Return a special object that preserves the include info
        include_obj = type('Include', (), {'filename': filename, 'tag': '!include'})()
        return include_obj
    
    IncludeLoader.add_constructor('!include', include_constructor)
    
    try:
        # Read current config.yaml with custom loader
        with open(config_file, encoding='utf-8') as f:
            config_content = load(f, Loader=IncludeLoader)
        
        if config_content is None:
            config_content = {}
        
        # Check if section exists in config
        if section in config_content:
            section_value = config_content[section]
            
            # Check if it's an !include directive
            if hasattr(section_value, 'tag') and section_value.tag == '!include':
                # It's an !include - update the included file
                include_filename = section_value.filename
                include_file_path = os.path.join(config_dir, include_filename)
                
                _LOGGER.info(f"Section '{section}' uses !include '{include_filename}', updating {include_file_path}")
                
                # Save cleaned data to the included file
                content = dump(cleaned_data, default_flow_style=False, allow_unicode=True, sort_keys=False)
                with open(include_file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                    
                _LOGGER.info(f"Successfully updated included file: {include_file_path}")
                
            else:
                # It's a regular section - replace in config.yaml
                _LOGGER.info(f"Section '{section}' is inline, updating in config.yaml")
                config_content[section] = cleaned_data
                
                # Save updated config.yaml (need to handle !include when saving)
                # Read original file as text to preserve !include syntax
                with open(config_file, encoding='utf-8') as f:
                    original_lines = f.readlines()
                
                # Find and replace the section in the original text
                updated_lines = []
                in_section = False
                section_indent = 0
                
                for line in original_lines:
                    stripped = line.strip()
                    # Check if this line starts the target section
                    if stripped == f"{section}:" or stripped.startswith(f"{section}: "):
                        # Found the section start
                        in_section = True
                        section_indent = len(line) - len(line.lstrip())
                        # Add the complete new section (header + data)
                        section_yaml = dump({section: cleaned_data}, default_flow_style=False, allow_unicode=True, sort_keys=False)
                        # Add proper indentation if section was indented
                        if section_indent > 0:
                            indented_lines = []
                            for yaml_line in section_yaml.split('\n'):
                                if yaml_line.strip():
                                    indented_lines.append(' ' * section_indent + yaml_line)
                            section_yaml = '\n'.join(indented_lines)
                        updated_lines.append(section_yaml + '\n')
                    elif in_section:
                        # Check if we're still in the same section
                        line_indent = len(line) - len(line.lstrip())
                        if stripped and line_indent <= section_indent and not stripped.startswith('-'):
                            # We've moved to a new section (non-empty line at same or lower indent, not a list item)
                            in_section = False
                            updated_lines.append(line)
                        # Skip lines that are part of the old section
                    else:
                        updated_lines.append(line)
                
                # Write updated config
                with open(config_file, 'w', encoding='utf-8') as f:
                    f.writelines(updated_lines)
                    
                _LOGGER.info(f"Successfully updated section '{section}' in config.yaml")
        else:
            # Section doesn't exist - add it to config.yaml
            _LOGGER.info(f"Section '{section}' doesn't exist, adding to config.yaml")
            
            # Append new section to the end of the file
            section_yaml = dump({section: cleaned_data}, default_flow_style=False, allow_unicode=True, sort_keys=False)
            with open(config_file, 'a', encoding='utf-8') as f:
                f.write('\n' + section_yaml)
                
            _LOGGER.info(f"Successfully added new section '{section}' to config.yaml")
        
        return {"status": "success", "message": f"Section '{section}' saved successfully"}
        
    except Exception as e:
        _LOGGER.error(f"Error saving section '{section}': {str(e)}")
        return {"status": "error", "message": f"Error saving section: {str(e)}"}
