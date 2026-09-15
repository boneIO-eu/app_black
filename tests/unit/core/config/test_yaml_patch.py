"""Creating a config section without disturbing the rest of the file.

config.yaml is a file people edit by hand. These tests care about what a
line-based edit can get wrong: comments, !secret references, indentation, and
the quoting that decides whether a CSP keyword survives the round trip.
"""

from __future__ import annotations

import pytest
import yaml

from boneio.core.config.yaml_patch import (
    YamlPatchError,
    ensure_section,
    quote_scalar,
)
from boneio.core.config.yaml_util import update_yaml_field


def write(tmp_path, text):
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_creates_a_missing_subsection(tmp_path):
    path = write(tmp_path, "web:\n  port: 8090\n")
    assert ensure_section(path, ("web", "security")) is True
    assert yaml.safe_load(path.read_text()) == {
        "web": {"port": 8090, "security": None}
    }


def test_existing_section_is_left_alone(tmp_path):
    path = write(tmp_path, "web:\n  security:\n    frame_ancestors: \"'self'\"\n")
    before = path.read_text()
    assert ensure_section(path, ("web", "security")) is False
    assert path.read_text() == before


def test_creates_both_levels_when_neither_exists(tmp_path):
    path = write(tmp_path, "mqtt:\n  host: localhost\n")
    ensure_section(path, ("web", "security"))
    assert yaml.safe_load(path.read_text())["web"] == {"security": None}


def test_comments_and_secrets_survive(tmp_path):
    original = (
        "# boneIO configuration\n"
        "mqtt:\n"
        "  host: localhost\n"
        "  password: !secret mqtt_pass  # do not commit\n"
        "\n"
        "web:\n"
        "  # served behind Caddy\n"
        "  port: 8090\n"
    )
    path = write(tmp_path, original)
    ensure_section(path, ("web", "security"))
    text = path.read_text()

    assert "# boneIO configuration" in text
    assert "!secret mqtt_pass  # do not commit" in text
    assert "# served behind Caddy" in text


def test_refuses_an_include(tmp_path):
    """Writing under `web: !include web.yaml` would go where nothing reads it."""
    path = write(tmp_path, "web: !include web.yaml\n")
    with pytest.raises(YamlPatchError, match="not a plain section"):
        ensure_section(path, ("web", "security"))


def test_section_is_created_inside_the_right_parent(tmp_path):
    """A later top-level key must not swallow the new section."""
    path = write(tmp_path, "web:\n  port: 8090\nmqtt:\n  host: localhost\n")
    ensure_section(path, ("web", "security"))
    loaded = yaml.safe_load(path.read_text())
    assert "security" in loaded["web"]
    assert loaded["mqtt"] == {"host": "localhost"}


@pytest.mark.parametrize(
    "value",
    [
        "'self'",  # the CSP keyword, not the bare word
        "'self' https://ha.local:8123",
        "*",
        'he said "hi"',
        "back\\slash",
    ],
)
def test_quoting_survives_the_round_trip(tmp_path, value):
    """`frame_ancestors: 'self'` would parse as the bare word `self`.

    CSP keywords carry their own single quotes. Without double quoting, the
    directive silently becomes a host name and means something else.
    """
    path = write(tmp_path, "web:\n  port: 8090\n")
    ensure_section(path, ("web", "security"))
    update_yaml_field(str(path), "web.security", "frame_ancestors", quote_scalar(value))

    loaded = yaml.safe_load(path.read_text())
    assert loaded["web"]["security"]["frame_ancestors"] == value


def test_naive_quoting_would_lose_the_csp_keyword():
    """Pins the trap this module exists to avoid."""
    assert yaml.safe_load("frame_ancestors: 'self'")["frame_ancestors"] == "self"
    assert yaml.safe_load("frame_ancestors: \"'self'\"")["frame_ancestors"] == "'self'"


def test_the_new_block_joins_its_section_not_the_gap_after_it(tmp_path):
    """Blank lines separating two top-level sections must stay separating them.

    Inserting after them is valid YAML and reads as though the setting fell
    out of the section it belongs to — in a file people open by hand.
    """
    path = write(
        tmp_path,
        "web:\n  port: 8090\n\n\nmqtt:\n  host: localhost\n",
    )
    ensure_section(path, ("web", "security"))
    lines = path.read_text().splitlines()

    assert lines.index("  security:") < lines.index("")
    assert yaml.safe_load(path.read_text())["web"] == {"port": 8090, "security": None}
