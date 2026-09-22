"""The check that moved off the device.

Cerberus re-checks that schema.yaml is a legal cerberus schema every time a
Validator is built, and on a BeagleBone that is most of what a config cache
miss costs. boneIO skips it at runtime and trusts the schema that ships in its
wheel, so the check has to happen here instead: these tests are the only thing
between a typo in schema.yaml and a release.
"""

from __future__ import annotations

import pytest
from cerberus import SchemaError, Validator
from cerberus.schema import DefinitionSchema

from boneio.core.config import yaml_util
from boneio.exceptions import ConfigurationException

GOOD_CONFIG = """
boneio:
  name: controller
mqtt:
  host: localhost
  topic_prefix: boneio
web:
  port: 8090
"""

BAD_CONFIG = """
boneio:
  name: controller
mqtt:
  host: localhost
  topic_prefix: boneio
output:
  - id: relay
    kind: not_a_kind
    pin: 12
"""


@pytest.fixture(autouse=True)
def unpatched_cerberus():
    """Start every test from stock cerberus, and leave the suite as we found it.

    _trust_schema patches the class once per process and never restores it, so
    by the time these run some earlier test has almost certainly tripped it.
    """
    found = DefinitionSchema.validate
    dropped = yaml_util._schema_self_check_dropped
    DefinitionSchema.validate = yaml_util._SCHEMA_SELF_CHECK
    yaml_util._schema_self_check_dropped = False
    Validator._valid_schemas.clear()
    yield
    DefinitionSchema.validate = found
    yaml_util._schema_self_check_dropped = dropped
    Validator._valid_schemas.clear()


def test_the_shipped_schema_is_a_legal_cerberus_schema():
    """If this fails, boneIO on a device will misvalidate configs, not crash."""
    with yaml_util.schema_self_check():
        yaml_util.CustomValidator(yaml_util._get_schema(), purge_unknown=True)


def test_the_check_is_a_real_one():
    """Guards the guard: a broken schema has to fail inside that block."""
    with yaml_util.schema_self_check(), pytest.raises(SchemaError):
        yaml_util.CustomValidator({"relay": {"type": "no_such_type"}})


def test_the_runtime_path_does_not_check_the_schema(monkeypatch):
    monkeypatch.delenv("BONEIO_VALIDATE_SCHEMA", raising=False)
    yaml_util._trust_schema()
    assert DefinitionSchema.validate is yaml_util._no_schema_self_check


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", "TRUE"])
def test_the_flag_puts_the_check_back(monkeypatch, value):
    """For editing schema.yaml on a device, where a typo should say so."""
    monkeypatch.setenv("BONEIO_VALIDATE_SCHEMA", value)
    yaml_util._trust_schema()
    assert DefinitionSchema.validate is not yaml_util._no_schema_self_check


@pytest.mark.parametrize("value", ["", "0", "no", "off", "maybe"])
def test_anything_else_leaves_the_check_off(monkeypatch, value):
    monkeypatch.setenv("BONEIO_VALIDATE_SCHEMA", value)
    yaml_util._trust_schema()
    assert DefinitionSchema.validate is yaml_util._no_schema_self_check


def _load(config: str, *, checked: bool):
    if checked:
        with yaml_util.schema_self_check():
            return yaml_util.load_config_from_string(config)
    DefinitionSchema.validate = yaml_util._no_schema_self_check
    yaml_util._schema_self_check_dropped = True
    return yaml_util.load_config_from_string(config)


def test_trusting_the_schema_does_not_change_the_config_it_produces():
    """The property that matters: only the schema check goes, nothing else."""
    assert _load(GOOD_CONFIG, checked=False) == _load(GOOD_CONFIG, checked=True)


def test_a_bad_config_is_rejected_the_same_way_either_side():
    """Skipping the schema check must not skip checking the user's config."""
    with pytest.raises(ConfigurationException) as trusted:
        _load(BAD_CONFIG, checked=False)
    with pytest.raises(ConfigurationException) as checked:
        _load(BAD_CONFIG, checked=True)
    assert str(trusted.value) == str(checked.value)
    assert "not_a_kind" in str(trusted.value)
