"""Tests for turning a typed name into an identifier.

The identifier reaches an MQTT topic, Home Assistant's unique_id, the state
file and every reference written by a condition or an action, so the cases
that matter are the ones where a name is not ASCII and not tidy.
"""

from __future__ import annotations

import pytest

from boneio.core.utils.naming import resolve_id, slugify_id


class TestSlugifyId:
    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("Nie ma nas w domu", "nie_ma_nas_w_domu"),
            ("Evening mode", "evening_mode"),
            ("  Salon  ", "salon"),
            ("Salon / Piętro 1", "salon_pietro_1"),
            ("OUT-11", "out_11"),
            ("a---b", "a_b"),
            ("!!!", ""),
            ("", ""),
        ],
    )
    def test_shapes(self, name, expected):
        assert slugify_id(name) == expected

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("Wyjście główne", "wyjscie_glowne"),
            ("Łazienka", "lazienka"),
            ("Zażółć gęślą jaźń", "zazolc_gesla_jazn"),
            ("Küche", "kuche"),
            ("Straße", "strasse"),
            ("Sønder", "sonder"),
        ],
    )
    def test_accents_are_folded(self, name, expected):
        """An MQTT topic with ł in it is a topic half the tooling cannot type."""
        assert slugify_id(name) == expected

    def test_the_result_is_always_topic_safe(self):
        for name in ("a/b", "a+b", "a#b", "a b", "Ą/Ż"):
            assert not set(slugify_id(name)) & set("/+# ")


class TestResolveId:
    def test_an_explicit_id_wins(self):
        """It exists so a reference survives a rename — conditions, actions,
        the topic and the saved state all point at the id."""
        assert resolve_id({"id": "away", "name": "Nie ma nas w domu"}) == "away"

    def test_the_name_is_used_when_there_is_no_id(self):
        assert resolve_id({"name": "Nie ma nas w domu"}) == "nie_ma_nas_w_domu"

    def test_an_empty_id_falls_through_to_the_name(self):
        assert resolve_id({"id": "   ", "name": "Evening"}) == "evening"

    def test_nothing_usable_gives_nothing(self):
        assert resolve_id({}) == ""
        assert resolve_id({"name": "!!!"}) == ""
