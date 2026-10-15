"""The committed JSON Schema files match schema.yaml.

The panel's forms and the config editor read boneio/webui/schema/, which
schema_converter.py generates and nothing regenerates on its own. In
September 2026 the files were three features behind schema.yaml and nobody
noticed: a form just does not know a field it was never told about.
"""

from __future__ import annotations

import json
import os

from boneio.core.config.schema_converter import OUTPUT_DIR, build_schemas

REGENERATE = "run: python boneio/core/config/schema_converter.py"


def test_every_schema_file_matches_schema_yaml():
    built = build_schemas()
    stale = []
    for name, expected in built.items():
        with open(os.path.join(OUTPUT_DIR, name), encoding="utf-8") as f:
            if json.load(f) != expected:
                stale.append(name)
    assert not stale, f"Stale schema files {stale}; {REGENERATE}"


def test_no_schema_file_is_left_over_or_missing():
    on_disk = {n for n in os.listdir(OUTPUT_DIR) if n.endswith(".schema.json")}
    assert on_disk == set(build_schemas()), REGENERATE
