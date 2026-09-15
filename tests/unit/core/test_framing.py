"""Reading and rendering the frame-ancestors list.

The whole module exists because the CSP keyword is `'self'` with quotes while
YAML strips them, so most of these tests are about the two spellings meeting
in the same place.
"""

from __future__ import annotations

import pytest

from boneio.core.security.framing import (
    DEFAULT_FRAME_ANCESTORS,
    effective,
    is_unrestricted,
    normalize,
    to_csp,
)


def test_a_list_of_plain_tokens():
    assert normalize(["self", "https://ha.local:8123"]) == (
        "self",
        "https://ha.local:8123",
    )


def test_the_keyword_is_quoted_on_the_way_out():
    """Bare `self` in a directive is a host name, not the keyword."""
    assert to_csp(("self",)) == "'self'"
    assert to_csp(("self", "https://ha.local:8123")) == "'self' https://ha.local:8123"
    assert to_csp(("none",)) == "'none'"


def test_an_old_string_value_still_reads():
    """1.6 wrote a single quoted string, and documentation still shows it."""
    assert normalize("'self' https://ha.local:8123") == (
        "self",
        "https://ha.local:8123",
    )


def test_quotes_are_stripped_wherever_they_come_from():
    """Copied out of the header, out of an old config, or typed plainly."""
    assert normalize(["'self'"]) == ("self",)
    assert normalize(['"self"']) == ("self",)
    assert normalize("self") == ("self",)


def test_keywords_are_case_insensitive():
    assert normalize(["SELF"]) == ("self",)


def test_addresses_keep_their_case():
    """A host is lowercase by convention, a path is not — do not rewrite it."""
    assert normalize(["https://HA.local:8123"]) == ("https://HA.local:8123",)


def test_duplicates_collapse():
    assert normalize(["self", "'self'", "self"]) == ("self",)


@pytest.mark.parametrize("raw", [None, [], "", "   ", 42, {"a": 1}])
def test_nothing_useful_reads_as_nothing(raw):
    assert normalize(raw) == ()


def test_an_absent_setting_falls_back_to_the_default():
    assert effective(None) == DEFAULT_FRAME_ANCESTORS
    assert effective([]) == DEFAULT_FRAME_ANCESTORS
    assert to_csp(effective(None)) == "'self'"


def test_a_configured_value_wins_over_the_default():
    assert effective(["*"]) == ("*",)


def test_the_wildcard_is_found_wherever_it_sits():
    """`self *` permits everything, whatever it looks like."""
    assert is_unrestricted(("*",))
    assert is_unrestricted(("self", "*"))
    assert not is_unrestricted(("self", "https://ha.local:8123"))
