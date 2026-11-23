"""A section reaches the running objects in the shape Cerberus gave it.

The shapes in config_shape/<section>.json were written from Cerberus'
normalization of every factory config and of every valid entry
test_section_models.py builds. They outlive
Cerberus: whatever start-up validates with, the components get these.

Two differences are deliberate, and the shapes hold the model's side:
- ``remote_inputs`` actions get an input action's defaults and coercions
  (Cerberus took any dictionary there); the action runner reads both.
- ``mqtt.topic_prefix``, a key no code reads, is dropped.

Regenerate after a deliberate change of shape, while Cerberus is installed:
``python -m tests.unit.core.config.test_config_shape``.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from boneio.core.config import models

SHAPES = Path(__file__).parent / "config_shape"


def _canon(value: Any) -> Any:
    """JSON-comparable: a TimePeriod (or any other object) by its repr."""
    if isinstance(value, dict):
        return {str(k): _canon(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canon(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return f"<{type(value).__name__} {value!r}>"


def _cases(section: str) -> list[dict]:
    return json.loads((SHAPES / f"{section}.json").read_text())


def test_every_section_has_shapes():
    assert {path.stem for path in SHAPES.glob("*.json")} == models.SECTIONS


@pytest.mark.parametrize("section", sorted(models.SECTIONS))
def test_the_model_gives_the_shape(section):
    for case in _cases(section):
        assert _canon(models.load(section, copy.deepcopy(case["input"]))) == case["shape"], case["input"]


def _cerberus_shape(section: str, data: Any) -> Any:
    from boneio.core.config.yaml_util import normalize_section

    shape = _canon(normalize_section(section, copy.deepcopy(data)))
    if section == "mqtt":
        shape.pop("topic_prefix", None)
    return shape


def _without_remote_actions(section: str, shape: Any) -> Any:
    if section != "remote_inputs":
        return shape
    return [{k: v for k, v in entry.items() if k != "actions"} for entry in shape]


@pytest.mark.parametrize("section", sorted(models.SECTIONS))
def test_the_shape_is_what_cerberus_gives(section):
    """Goes with Cerberus."""
    for case in _cases(section):
        expected = _without_remote_actions(section, case["shape"])
        assert _without_remote_actions(section, _cerberus_shape(section, case["input"])) == expected, case["input"]


def _write() -> None:
    """Every factory config's sections and every valid differential case."""
    import glob

    from boneio.core.config.yaml_util import _run_config_migrations, load_yaml_file, validate_section
    from tests.unit.core.config import test_section_models as diff

    found: list[tuple[str, Any, dict]] = []
    for path in sorted(glob.glob("boneio/factory_config/*/*/config.yaml")):
        raw, _ = _run_config_migrations(load_yaml_file(path), config_file=None)
        found += [(s, raw[s], raw["boneio"]) for s in sorted(models.SECTIONS & raw.keys())]
    for base in diff._BASES:
        found += [(base[0], diff._data(base[0], base[1]), diff.BONEIO)]
        found += [(base[0], data, diff.BONEIO) for _, _, data in diff._cases(*base)]
    # The differential test has no base for it.
    found += [("usage_history", d, diff.BONEIO) for d in ({}, {"enabled": True}, {"enabled": False, "days": 90})]

    shapes: dict[str, dict[str, dict]] = {}
    for section, data, boneio in found:
        try:
            key = json.dumps(data, sort_keys=True)
        except TypeError:
            continue
        if key in shapes.get(section, {}) or validate_section(section, copy.deepcopy(data), boneio):
            continue
        shape = _canon(models.load(section, copy.deepcopy(data)))
        assert _without_remote_actions(section, _cerberus_shape(section, data)) == _without_remote_actions(
            section, shape
        ), (section, data)
        shapes.setdefault(section, {})[key] = {"input": data, "shape": shape}

    SHAPES.mkdir(exist_ok=True)
    for section, cases in shapes.items():
        lines = (json.dumps(case, sort_keys=True, ensure_ascii=False) for case in cases.values())
        (SHAPES / f"{section}.json").write_text("[\n" + ",\n".join(lines) + "\n]\n")
        print(section, len(cases))


if __name__ == "__main__":
    _write()
