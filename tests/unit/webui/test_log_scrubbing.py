"""Secrets must not reach the log viewer.

This file exists because the scrubbing silently did nothing for a release. The
function called a helper by a name that is not defined in its module, every
call raised NameError, a broad `except` swallowed it, and `/api/logs` returned
the journal untouched — including any line that carried a password.

Nothing caught it: the function has a try/except whose whole purpose is to
return the entries unchanged when something goes wrong, so "returns entries"
was indistinguishable from "works". The tests below assert the replacement
actually happened.
"""

from __future__ import annotations

import logging

import pytest

from boneio.core.config.secret_masking import MASK
from boneio.webui.routes import system as system_route


class _Entry:
    """Stands in for the LogEntry model, which only needs .message here."""

    def __init__(self, message: str) -> None:
        self.message = message


class _Helper:
    def __init__(self, config: dict) -> None:
        self._config = config

    def get_config(self, force_reload: bool = False) -> dict:
        return self._config


@pytest.fixture
def configured(monkeypatch):
    """A device whose broker password is known."""
    config = {"mqtt": {"host": "localhost", "username": "boneio", "password": "sekret123"}}
    monkeypatch.setattr(
        system_route, "_config_helper_getter", lambda: _Helper(config), raising=False
    )
    return config


def test_a_password_in_a_log_line_is_replaced(configured):
    entries = [_Entry("connecting with password=sekret123 to localhost")]
    scrubbed = system_route._scrub_log_entries(entries)

    assert "sekret123" not in scrubbed[0].message
    assert MASK in scrubbed[0].message


def test_dict_entries_are_scrubbed_too(configured):
    """The standalone log path yields dicts rather than models."""
    entries = [{"message": "auth failed for sekret123", "level": "ERROR"}]
    scrubbed = system_route._scrub_log_entries(entries)

    assert "sekret123" not in scrubbed[0]["message"]


def test_lines_without_secrets_are_untouched(configured):
    entries = [_Entry("Modbus read completed in 4.5 seconds")]
    assert system_route._scrub_log_entries(entries)[0].message == (
        "Modbus read completed in 4.5 seconds"
    )


def test_a_broken_helper_does_not_cost_the_operator_their_logs(monkeypatch, caplog):
    """Returning the entries is the right fallback — but it must be loud.

    Silence is what let the defect above survive: a no-op and a success look
    identical from outside.
    """

    def boom():
        raise RuntimeError("no config helper")

    monkeypatch.setattr(system_route, "_config_helper_getter", boom, raising=False)
    entries = [_Entry("something happened")]

    with caplog.at_level(logging.WARNING):
        result = system_route._scrub_log_entries(entries)

    assert result[0].message == "something happened"
    assert any("scrubbing" in record.message for record in caplog.records)


def test_the_helper_is_called_by_a_name_that_exists(configured):
    """The actual defect, pinned.

    The call used to name a function that does not exist in this module. That
    is a NameError at call time, not at import, so nothing noticed.
    """
    entries = [_Entry("password=sekret123")]
    # If the lookup breaks again, this comes back unchanged.
    assert MASK in system_route._scrub_log_entries(entries)[0].message
