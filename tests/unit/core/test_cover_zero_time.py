"""A cover with open_time/close_time = 0 is silently immobile.

`_move_cover` bails out before `relay.turn_on()`, so the relay is never
energised and the motor never sees voltage — but the cover still flips to IDLE
and publishes state, so the UI and the logs look like the command worked. From
position 0% even `close()` short-circuits on `position <= 0`, which means no
command can ever move the cover again and no restart helps.

These tests pin down that the zero-duration case is reported as an error and
that the ordinary "already at target" case stays quiet.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from boneio.components.cover.time_based import TimeBasedCover
from boneio.components.cover.venetian import VenetianCover
from boneio.const import CLOSE, IDLE, OPEN


def _bare_cover(cls, position: float = 0.0):
    """Build only the attributes `_move_cover` touches before it returns.

    A real cover drags in MQTT, the event bus and the config stack; the guard
    under test needs none of it.
    """
    cover = object.__new__(cls)
    cover._id = "cover_05"
    cover._position = position
    cover._initial_position = position
    cover._initial_tilt_position = 0.0
    cover._tilt_position = 0.0
    cover._open_relay = MagicMock()
    cover._close_relay = MagicMock()
    cover._current_operation = "opening"
    cover._loop = MagicMock()
    return cover


class TestTimeBasedCoverZeroDuration:
    def test_zero_open_time_logs_error_and_never_switches_relay(self, caplog):
        cover = _bare_cover(TimeBasedCover, position=0.0)

        with caplog.at_level(logging.ERROR):
            cover._move_cover(OPEN, 0)

        cover._open_relay.turn_on.assert_not_called()
        assert cover._current_operation == IDLE
        assert "open_time is 0" in caplog.text
        assert "cover_05" in caplog.text

    def test_zero_close_time_logs_error_and_never_switches_relay(self, caplog):
        cover = _bare_cover(TimeBasedCover, position=100.0)

        with caplog.at_level(logging.ERROR):
            cover._move_cover(CLOSE, 0)

        cover._close_relay.turn_on.assert_not_called()
        assert "close_time is 0" in caplog.text

    def test_already_at_target_is_not_an_error(self, caplog):
        """total_steps == 0 with a valid duration is normal, not misconfigured."""
        cover = _bare_cover(TimeBasedCover, position=100.0)

        with caplog.at_level(logging.ERROR):
            cover._move_cover(OPEN, 35000)

        cover._open_relay.turn_on.assert_not_called()
        assert cover._current_operation == IDLE
        assert caplog.text == ""


class TestVenetianCoverZeroDuration:
    def test_zero_open_time_logs_error_and_never_switches_relay(self, caplog):
        cover = _bare_cover(VenetianCover, position=0.0)

        with caplog.at_level(logging.ERROR):
            cover._move_cover(OPEN, 0, 0)

        cover._open_relay.turn_on.assert_not_called()
        assert "open_time is 0" in caplog.text

    def test_already_at_target_is_not_an_error(self, caplog):
        cover = _bare_cover(VenetianCover, position=100.0)

        with caplog.at_level(logging.ERROR):
            cover._move_cover(OPEN, 40000, 2000)

        cover._open_relay.turn_on.assert_not_called()
        assert caplog.text == ""
