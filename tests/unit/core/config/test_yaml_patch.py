"""Creating a config section without disturbing the rest of the file.

config.yaml is a file people edit by hand. These tests care about what a
line-based edit can get wrong: comments, !secret references, indentation, and
the quoting that decides whether a CSP keyword survives the round trip.
"""

from __future__ import annotations

import logging

import pytest
import yaml

from boneio.core.config.yaml_patch import (
    YamlPatchError,
    ensure_section,
    quote_scalar,
    resolve_field,
    secret_reference,
    set_block_list,
    set_scalar,
    set_secret,
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


# --------------------------------------------------------------- block lists


def test_writes_a_block_list(tmp_path):
    path = write(tmp_path, "web:\n  port: 8090\n")
    set_block_list(path, ("web", "security"), "frame_ancestors", ["self"])

    assert yaml.safe_load(path.read_text())["web"]["security"] == {
        "frame_ancestors": ["self"]
    }
    assert "      - self\n" in path.read_text()


def test_the_keyword_needs_no_quoting_gymnastics(tmp_path):
    """A list entry reads back as typed, which is the point of the list form."""
    path = write(tmp_path, "web:\n  port: 8090\n")
    set_block_list(
        path,
        ("web", "security"),
        "frame_ancestors",
        ["self", "https://homeassistant.local:8123"],
    )
    assert yaml.safe_load(path.read_text())["web"]["security"]["frame_ancestors"] == [
        "self",
        "https://homeassistant.local:8123",
    ]


def test_replacing_a_longer_list_with_a_shorter_one(tmp_path):
    """Leftover entries would silently widen the policy."""
    path = write(
        tmp_path,
        "web:\n  security:\n    frame_ancestors:\n      - self\n      - https://a.local\n"
        "      - https://b.local\n  port: 8090\n",
    )
    set_block_list(path, ("web", "security"), "frame_ancestors", ["self"])

    loaded = yaml.safe_load(path.read_text())
    assert loaded["web"]["security"]["frame_ancestors"] == ["self"]
    assert loaded["web"]["port"] == 8090  # what followed is still there


def test_replacing_the_old_scalar_form(tmp_path):
    """Configs written by 1.6 before the list existed."""
    path = write(
        tmp_path,
        "web:\n  security:\n    frame_ancestors: \"'self'\"\n  port: 8090\n",
    )
    set_block_list(path, ("web", "security"), "frame_ancestors", ["self", "https://ha.local"])

    loaded = yaml.safe_load(path.read_text())
    assert loaded["web"]["security"]["frame_ancestors"] == ["self", "https://ha.local"]
    assert loaded["web"]["port"] == 8090


def test_surrounding_comments_and_secrets_survive(tmp_path):
    path = write(
        tmp_path,
        "# top\nmqtt:\n  password: !secret p\nweb:\n  # how it is reached\n  port: 8090\n",
    )
    set_block_list(path, ("web", "security"), "frame_ancestors", ["self"])
    text = path.read_text()

    assert "# top" in text
    assert "!secret p" in text
    assert "# how it is reached" in text


def test_an_empty_list_is_written_as_an_empty_list(tmp_path):
    """Not as a dangling key that reads back as null and means the default."""
    path = write(tmp_path, "web:\n  port: 8090\n")
    set_block_list(path, ("web", "security"), "frame_ancestors", [])
    assert yaml.safe_load(path.read_text())["web"]["security"]["frame_ancestors"] is None


def test_refuses_an_included_section(tmp_path):
    path = write(tmp_path, "web: !include web.yaml\n")
    with pytest.raises(YamlPatchError):
        set_block_list(path, ("web", "security"), "frame_ancestors", ["self"])


# ----------------------------------------------------------- entry quoting


@pytest.mark.parametrize(
    "token",
    [
        "self",
        "none",
        "https://homeassistant.local:8123",
        "http://ha.local",
        "*",
        "yes",
        "null",
        "a b",
        "#comment-ish",
        "- dash",
        "",
        "'self'",
        "x: y",
    ],
)
def test_every_entry_reads_back_exactly_as_written(tmp_path, token):
    """Quoting is an optimisation for readability, never for correctness."""
    path = write(tmp_path, "web:\n  port: 8090\n")
    set_block_list(path, ("web", "security"), "frame_ancestors", [token])
    assert yaml.safe_load(path.read_text())["web"]["security"]["frame_ancestors"] == [token]


def test_ordinary_entries_are_left_unquoted(tmp_path):
    """The list form exists so the file reads as someone would type it."""
    path = write(tmp_path, "web:\n  port: 8090\n")
    set_block_list(
        path, ("web", "security"), "frame_ancestors", ["self", "https://ha.local:8123"]
    )
    text = path.read_text()
    assert "      - self\n" in text
    assert "      - https://ha.local:8123\n" in text
    assert '"' not in text


def test_the_wildcard_is_quoted_because_yaml_would_choke(tmp_path):
    """`- *` is an alias reference and a syntax error, not a string."""
    path = write(tmp_path, "web:\n  port: 8090\n")
    set_block_list(path, ("web", "security"), "frame_ancestors", ["*"])
    assert '- "*"' in path.read_text()
    assert yaml.safe_load(path.read_text())["web"]["security"]["frame_ancestors"] == ["*"]


# ---------------------------------------------------------------------------
# Writing a value, and following a !secret reference to where it really lives
# ---------------------------------------------------------------------------


def test_a_plain_field_has_no_secret_reference(tmp_path):
    path = write(tmp_path, "mqtt:\n  password: boneio123\n")
    assert secret_reference(path, ("mqtt", "password")) is None


def test_a_reference_names_the_secret(tmp_path):
    path = write(tmp_path, "mqtt:\n  password: !secret mqtt_pass  # do not commit\n")
    assert secret_reference(path, ("mqtt", "password")) == "mqtt_pass"


def test_a_field_that_is_not_there_has_no_reference(tmp_path):
    path = write(tmp_path, "mqtt:\n  host: localhost\n")
    assert secret_reference(path, ("mqtt", "password")) is None


def test_a_value_is_replaced_in_place(tmp_path):
    path = write(tmp_path, "mqtt:\n  host: localhost\n  password: boneio123\n")
    set_scalar(path, ("mqtt", "password"), "nowe-haslo")
    loaded = yaml.safe_load(path.read_text())
    assert loaded["mqtt"] == {"host": "localhost", "password": "nowe-haslo"}


def test_a_missing_field_is_created(tmp_path):
    path = write(tmp_path, "mqtt:\n  host: localhost\n")
    set_scalar(path, ("mqtt", "password"), "nowe-haslo")
    assert yaml.safe_load(path.read_text())["mqtt"]["password"] == "nowe-haslo"


def test_the_rest_of_the_file_is_left_alone(tmp_path):
    path = write(
        tmp_path,
        "# boneIO\nmqtt:\n  host: localhost  # broker\n  password: stare\nweb:\n  port: 8090\n",
    )
    set_scalar(path, ("mqtt", "password"), "nowe-haslo")
    text = path.read_text()
    assert "# boneIO" in text
    assert "host: localhost  # broker" in text
    assert "port: 8090" in text


def test_a_password_yaml_would_misread_survives(tmp_path):
    """`no`, `1234`, a leading `*`: all of them stop being that password."""
    path = write(tmp_path, "mqtt:\n  password: stare\n")
    for password in ("no", "1234", "*tajne*", 'ma "cudzyslow"'):
        set_scalar(path, ("mqtt", "password"), password)
        assert yaml.safe_load(path.read_text())["mqtt"]["password"] == password


def test_the_value_does_not_reach_the_log(tmp_path, caplog):
    """update_yaml_field logs what it wrote, which a password must not be."""
    path = write(tmp_path, "mqtt:\n  password: stare\n")
    with caplog.at_level(logging.INFO):
        set_scalar(path, ("mqtt", "password"), "bardzo-tajne")
    assert "bardzo-tajne" not in caplog.text


def test_a_secret_is_replaced_without_disturbing_the_others(tmp_path):
    secrets = tmp_path / "secrets.yaml"
    secrets.write_text(
        "# not in git\nmqtt_pass: stare\nweb_pass: inne\n", encoding="utf-8"
    )
    set_secret(secrets, "mqtt_pass", "nowe-haslo")
    loaded = yaml.safe_load(secrets.read_text())
    assert loaded == {"mqtt_pass": "nowe-haslo", "web_pass": "inne"}
    assert "# not in git" in secrets.read_text()


def test_a_secret_that_is_not_there_yet_is_appended(tmp_path):
    secrets = tmp_path / "secrets.yaml"
    secrets.write_text("web_pass: inne", encoding="utf-8")
    set_secret(secrets, "mqtt_pass", "nowe-haslo")
    assert yaml.safe_load(secrets.read_text())["mqtt_pass"] == "nowe-haslo"


def test_a_missing_secrets_file_is_refused(tmp_path):
    """A reference pointing at a file that is not there is a problem to
    report, not one to paper over by creating the file."""
    with pytest.raises(YamlPatchError):
        set_secret(tmp_path / "secrets.yaml", "mqtt_pass", "nowe-haslo")


# ---------------------------------------------------------------------------
# A section kept in a file of its own — the layout every controller ships with
# ---------------------------------------------------------------------------


def test_a_plain_section_resolves_to_the_same_file(tmp_path):
    path = write(tmp_path, "mqtt:\n  password: boneio123\n")
    target, field = resolve_field(path, ("mqtt", "password"))
    assert (target, field) == (path, ("mqtt", "password"))


def test_an_include_resolves_to_the_file_beside_it(tmp_path):
    path = write(tmp_path, "mqtt: !include mqtt.yaml\n")
    target, field = resolve_field(path, ("mqtt", "password"))
    assert (target.name, field) == ("mqtt.yaml", ("password",))
    assert target.parent == path.parent


def test_the_password_is_written_into_the_included_file(tmp_path):
    path = write(tmp_path, "mqtt: !include mqtt.yaml\nweb:\n  port: 8090\n")
    included = tmp_path / "mqtt.yaml"
    included.write_text("host: localhost\npassword: boneio123\n", encoding="utf-8")

    set_scalar(path, ("mqtt", "password"), "nowe-haslo")

    assert yaml.safe_load(included.read_text()) == {
        "host": "localhost",
        "password": "nowe-haslo",
    }
    assert path.read_text() == "mqtt: !include mqtt.yaml\nweb:\n  port: 8090\n"


def test_a_field_missing_from_the_included_file_is_appended(tmp_path):
    path = write(tmp_path, "mqtt: !include mqtt.yaml\n")
    included = tmp_path / "mqtt.yaml"
    included.write_text("host: localhost\n", encoding="utf-8")

    set_scalar(path, ("mqtt", "password"), "nowe-haslo")

    assert yaml.safe_load(included.read_text())["password"] == "nowe-haslo"


def test_a_secret_inside_the_included_file_is_found(tmp_path):
    path = write(tmp_path, "mqtt: !include mqtt.yaml\n")
    (tmp_path / "mqtt.yaml").write_text(
        "password: !secret mqtt_pass\n", encoding="utf-8"
    )
    assert secret_reference(path, ("mqtt", "password")) == "mqtt_pass"


def test_an_include_naming_nothing_is_refused_not_created(tmp_path):
    """Creating the file would invent a section out of a typo."""
    path = write(tmp_path, "mqtt: !include mqtt.yaml\n")
    with pytest.raises(YamlPatchError):
        set_scalar(path, ("mqtt", "password"), "nowe-haslo")
    assert not (tmp_path / "mqtt.yaml").exists()
