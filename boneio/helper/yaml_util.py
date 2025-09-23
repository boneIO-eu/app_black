import fnmatch
import logging
import os
import re
from collections import OrderedDict
from typing import Any, Tuple

from cerberus import TypeDefinition, Validator
from yaml import MarkedYAMLError, SafeLoader, YAMLError, dump, load

from boneio.const import ID, OUTPUT
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
            raise MarkedYAMLError(
                f"Secret '{node.value}' not defined", node.start_mark
            )
        val = secrets[node.value]
        _SECRET_VALUES[str(val)] = node.value
        return val

    def represent_stringify(self, value):
        return self.represent_scalar(
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
    with open(filename, "r") as stream:
        try:
            return load(stream, Loader=BoneIOLoader) or OrderedDict()
        except YAMLError as exception:
            msg = ""
            if hasattr(exception, "problem_mark"):
                if exception.context is not None:
                    msg+= ('  parser says\n' + str(exception.problem_mark) + '\n  ' +
                        str(exception.problem) + ' ' + str(exception.context) +
                        '\nPlease correct data and retry.')
                mark = exception.problem_mark
                msg = f" at line {mark.line + 1} column {mark.column + 1}"
            raise ConfigurationException(f"Error loading yaml{msg}") from exception


def get_board_config_path(board_name: str, version: str) -> str:
    """Get the appropriate board configuration file path based on version."""
    base_dir = os.path.join(os.path.dirname(__file__), "../boards")
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
        32x10a, 32x10A, 32 -> 32_10
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
    
    # Handle 32x10A variations
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
        board_config = load_yaml_file(board_file)
        input_config = load_yaml_file(input_file)
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
                del output["boneio_output"]
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

    types_mapping = Validator.types_mapping.copy()
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
            self._error(field, "must be a string")
            return

        allowed = self.schema[field].get('allowed')
        if allowed and value.lower() not in [a.lower() for a in allowed]:
            self._error(field, f"unallowed value {value}")

    def _validate_required_if(self, required_if, field, value):
        """Validate that a field is required if a condition is met.
        
        The rule's arguments are validated against this schema:
        {'type' : 'dict'}
        """
        if not required_if:
            return

        for key, values in required_if.items():
            if key not in self.document:
                continue

            doc_value = self.document[key]
            if isinstance(doc_value, str):
                doc_value = doc_value.lower()
            if doc_value in [v.lower() if isinstance(v, str) else v for v in values]:
                if field not in self.document:
                    self._error(field, f"required when {key} is {doc_value}")

    def _validate_forbidden_if(self, forbidden_if, field, value):
        """Validate that a field is forbidden if a condition is met.
        
        The rule's arguments are validated against this schema:
        {'type': 'dict'}
        """
        if not forbidden_if:
            return
        default_value = self.schema[field].get("default")
        for key, values in forbidden_if.items():
            if key not in self.document:
                continue

            doc_value = self.document[key]
            if isinstance(doc_value, str):
                doc_value = doc_value.lower()
            
            if doc_value in [v.lower() if isinstance(v, str) else v for v in values]:
                if field in self.document and value != default_value:
                    self._error(field, f"forbidden when {key} is {doc_value}")

    def _normalize_coerce_action_field(self, value):
        """Handle conditional defaults for action fields."""
        action = self.document.get('action', '').lower()
        field_name = self.schema_path[-1]
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

    def _normalize_coerce_length_to_meters(self, value) -> float:
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
        """Check if outputs ids are unique if they exists."""
        if self.document[OUTPUT] is not None:
            all_ids = [x[ID] for x in self.document[OUTPUT]]
            if len(all_ids) != len(set(all_ids)):
                self._error(field, "Output IDs are not unique.")

    def _normalize_coerce_to_bool(self, value):
        return True

    def _normalize_coerce_remove_space(self, value):
        return str(value).replace(" ", "")

    def _normalize_coerce_actions_output(self, value):
        return str(value).upper()

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
        num, unit = match.groups()
        num = float(num)
        multiplier = 1.0
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
        num, unit = match.groups()
        num = float(num)
        multiplier = 1.0
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



def load_config_from_string(config_str: str) -> dict:
    """Load config from string."""
    schema = load_yaml_file(schema_file)
    v = CustomValidator(schema, purge_unknown=True)

    # First normalize the document
    doc = v.normalized(config_str, always_return_document=True)
    # Then merge board config
    if "modbus_sensors" in doc:
        _LOGGER.warning("Modbus sensors are renamed to modbus_devices. Please update your config.")
    merged_doc = merge_board_config(doc)
    
    # Finally validate
    if not v.validate(merged_doc):
        error_msg = "Configuration validation failed:\n"
        for field, errors in v.errors.items():
            error_lines = []
            if "line" in v.errors[field][0]:
                error_lines = [
                    f"{v.errors[field][0]['line']+1}: {line}"
                    for line in config_str.splitlines()[v.errors[field][0]["line"]-1:v.errors[field][0]["line"]+1]
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
    return load_config_from_string(config_yaml)


def update_config_section(config_file: str, section: str, data: dict) -> dict:
    """
    Update content of a configuration section with intelligent !include handling.
    
    Args:
        config_file: Path to the main config.yaml file
        section: Name of the section to update
        data: New data for the section
        
    Returns:
        dict: Status response with success/error message
    """
    import os
    from pathlib import Path
    
    config_dir = Path(config_file).parent
    
    _LOGGER.info(f"Updating section '{section}' with data: {data}")
    
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
        with open(config_file, 'r', encoding='utf-8') as f:
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
                
                # Save data to the included file
                content = dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
                with open(include_file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                    
                _LOGGER.info(f"Successfully updated included file: {include_file_path}")
                
            else:
                # It's a regular section - replace in config.yaml
                _LOGGER.info(f"Section '{section}' is inline, updating in config.yaml")
                config_content[section] = data
                
                # Save updated config.yaml (need to handle !include when saving)
                # Read original file as text to preserve !include syntax
                with open(config_file, 'r', encoding='utf-8') as f:
                    original_lines = f.readlines()
                
                # Find and replace the section in the original text
                updated_lines = []
                in_section = False
                section_indent = 0
                
                for line in original_lines:
                    if line.strip().startswith(f"{section}:"):
                        # Found the section start
                        in_section = True
                        section_indent = len(line) - len(line.lstrip())
                        # Add the section header
                        updated_lines.append(line)
                        # Add the new data
                        section_yaml = dump({section: data}, default_flow_style=False, allow_unicode=True, sort_keys=False)
                        section_lines = section_yaml.split('\n')[1:]  # Skip the section name line
                        for data_line in section_lines:
                            if data_line.strip():
                                updated_lines.append(' ' * section_indent + data_line + '\n')
                    elif in_section:
                        # Check if we're still in the same section
                        line_indent = len(line) - len(line.lstrip())
                        if line.strip() and line_indent <= section_indent:
                            # We've moved to a new section
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
            section_yaml = dump({section: data}, default_flow_style=False, allow_unicode=True, sort_keys=False)
            with open(config_file, 'a', encoding='utf-8') as f:
                f.write('\n' + section_yaml)
                
            _LOGGER.info(f"Successfully added new section '{section}' to config.yaml")
        
        return {"status": "success", "message": f"Section '{section}' saved successfully"}
        
    except Exception as e:
        _LOGGER.error(f"Error saving section '{section}': {str(e)}")
        return {"status": "error", "message": f"Error saving section: {str(e)}"}
