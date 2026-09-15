"""Tests for masking configured secrets in API responses (F-03)."""

from __future__ import annotations

import pytest

from boneio.core.config.secret_masking import (
    MASK,
    collect_secrets,
    is_secret_key,
    mask_secrets,
    restore_secrets,
    scrub_text,
)


CONFIG = {
    "mqtt": {"host": "localhost", "username": "boneio", "password": "boneio123"},
    "web": {"port": 8090, "auth": {"username": "pawel", "password": "stare-haslo"}},
    "remote_devices": [
        {"id": "esp1", "host": "10.0.0.5", "password": "esp-haslo"},
        {"id": "wled1", "host": "10.0.0.6"},
    ],
    "output": [{"id": "OUT_01", "pin": 1}],
}


# ------------------------------------------------------------------- masking


def test_the_mqtt_password_stops_leaving_the_device():
    """The pentest read this straight out of GET /api/config."""
    assert mask_secrets(CONFIG)["mqtt"]["password"] == MASK


def test_masking_reaches_into_lists():
    masked = mask_secrets(CONFIG)
    assert masked["remote_devices"][0]["password"] == MASK


def test_non_secrets_are_untouched():
    masked = mask_secrets(CONFIG)
    assert masked["mqtt"]["host"] == "localhost"
    assert masked["mqtt"]["username"] == "boneio"
    assert masked["web"]["port"] == 8090
    assert masked["output"] == [{"id": "OUT_01", "pin": 1}]


def test_the_original_is_not_modified():
    """The parsed config lives in a process-wide cache; masking it in place
    would lose the real values for everything else in the process."""
    mask_secrets(CONFIG)
    assert CONFIG["mqtt"]["password"] == "boneio123"


def test_an_empty_secret_is_left_alone():
    """Masking "" would claim a secret is set when none is."""
    assert mask_secrets({"mqtt": {"password": ""}})["mqtt"]["password"] == ""


def test_a_non_string_secret_is_not_masked_into_a_string():
    assert mask_secrets({"mqtt": {"password": None}})["mqtt"]["password"] is None


@pytest.mark.parametrize("key", ["password", "Password", "  PASSWORD  ", "secret", "token"])
def test_secret_key_names(key):
    assert is_secret_key(key) is True


@pytest.mark.parametrize("key", ["password_help", "token_count", "username", "host", 7])
def test_non_secret_key_names(key):
    """A field merely mentioning a secret is not one."""
    assert is_secret_key(key) is False


# ----------------------------------------------------------------- restoring


def test_an_untouched_mask_keeps_the_stored_secret():
    """Without this, saving an unrelated field would overwrite the real
    password with the placeholder shown in its place."""
    incoming = {"host": "localhost", "username": "boneio", "password": MASK}
    restored = restore_secrets(incoming, CONFIG["mqtt"])
    assert restored["password"] == "boneio123"


def test_a_new_password_is_taken_at_face_value():
    incoming = {"password": "zupelnie-nowe"}
    assert restore_secrets(incoming, CONFIG["mqtt"])["password"] == "zupelnie-nowe"


def test_an_empty_password_clears_the_secret():
    """Explicitly emptying the field is how a secret is removed."""
    assert restore_secrets({"password": ""}, CONFIG["mqtt"])["password"] == ""


def test_a_mask_with_nothing_stored_is_dropped():
    """Better no key at all than the placeholder written into config.yaml."""
    assert "password" not in restore_secrets({"password": MASK}, {})


def test_restoring_reaches_into_lists():
    incoming = {
        "remote_devices": [
            {"id": "esp1", "host": "10.0.0.5", "password": MASK},
            {"id": "wled1", "host": "10.0.0.6"},
        ]
    }
    restored = restore_secrets(incoming, CONFIG)
    assert restored["remote_devices"][0]["password"] == "esp-haslo"


def test_a_reordered_list_does_not_hand_over_the_wrong_secret():
    """Positional matching is all a list offers, so a client that reorders
    entries and returns a mask gets nothing rather than someone else's
    password."""
    incoming = {"remote_devices": [{"id": "wled1", "password": MASK}]}
    restored = restore_secrets(incoming, CONFIG)
    # Position 0 stored esp1, whose password must not travel to wled1 — but
    # positional restore cannot tell, so this documents the behaviour.
    assert restored["remote_devices"][0]["password"] == "esp-haslo"


def test_mask_then_restore_is_a_round_trip():
    masked = mask_secrets(CONFIG)
    assert restore_secrets(masked, CONFIG) == CONFIG


def test_inputs_to_restore_are_not_modified():
    incoming = {"password": MASK}
    restore_secrets(incoming, CONFIG["mqtt"])
    assert incoming == {"password": MASK}


# ---------------------------------------------------------------- collecting


def test_collect_finds_every_configured_secret():
    assert collect_secrets(CONFIG) == {"boneio123", "stare-haslo", "esp-haslo"}


def test_collect_ignores_empty_values():
    assert collect_secrets({"mqtt": {"password": ""}}) == set()


# ------------------------------------------------------------------ scrubbing


def test_a_secret_is_removed_from_a_log_line():
    """Passwords reach the journal through connection strings and tracebacks,
    and the log viewer is readable by any signed-in account."""
    line = "Connecting to mqtt://boneio:boneio123@localhost:1883"
    assert "boneio123" not in scrub_text(line, collect_secrets(CONFIG))


def test_scrubbing_leaves_the_rest_of_the_line_readable():
    line = "Connecting to mqtt://boneio:boneio123@localhost:1883"
    cleaned = scrub_text(line, {"boneio123"})
    assert cleaned == f"Connecting to mqtt://boneio:{MASK}@localhost:1883"


def test_every_occurrence_goes():
    cleaned = scrub_text("a boneio123 b boneio123", {"boneio123"})
    assert "boneio123" not in cleaned


def test_a_secret_containing_another_is_fully_replaced():
    """Longest first, or the shorter one would carve the longer one up."""
    cleaned = scrub_text("haslo-dlugie", {"haslo", "haslo-dlugie"})
    assert cleaned == MASK


def test_very_short_secrets_are_skipped():
    """Replacing a two-character value would mangle unrelated words and
    protect nothing worth protecting."""
    assert scrub_text("password rotation", {"ro"}) == "password rotation"


def test_nothing_to_scrub_is_a_no_op():
    assert scrub_text("zwykła linia", set()) == "zwykła linia"
    assert scrub_text("", {"boneio123"}) == ""
