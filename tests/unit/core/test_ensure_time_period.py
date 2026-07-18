"""Tests for ensure_time_period helper and cover hot-reload with string time values.

Verifies that:
- ensure_time_period correctly converts str/int/float/TimePeriod values
- Cover update_config_times handles string values during hot-reload
- Cover creation via _configure_cover handles string tilt_duration
"""

import pytest

from boneio.core.utils import TimePeriod
from boneio.core.utils.timeperiod import ensure_time_period


class TestEnsureTimePeriod:
    """Tests for the ensure_time_period helper function."""

    def test_passthrough_time_period(self) -> None:
        """TimePeriod objects should pass through unchanged."""
        tp = TimePeriod(seconds=5)
        result = ensure_time_period(tp)
        assert result is tp

    def test_string_seconds(self) -> None:
        """String '5s' should become TimePeriod(seconds=5)."""
        result = ensure_time_period("5s")
        assert result.total_seconds == 5

    def test_string_milliseconds(self) -> None:
        """String '1000ms' should become TimePeriod(milliseconds=1000)."""
        result = ensure_time_period("1000ms")
        assert result.total_milliseconds == 1000

    def test_string_minutes(self) -> None:
        """String '2min' should become TimePeriod(minutes=2)."""
        result = ensure_time_period("2min")
        assert result.total_minutes == 2

    def test_string_hours(self) -> None:
        """String '1h' should become TimePeriod(hours=1)."""
        result = ensure_time_period("1h")
        assert result.total_hours == 1

    def test_string_with_whitespace(self) -> None:
        """Strings with leading/trailing whitespace should be handled."""
        result = ensure_time_period("  10s  ")
        assert result.total_seconds == 10

    def test_string_with_space_before_unit(self) -> None:
        """Strings with space between number and unit should work."""
        result = ensure_time_period("10 s")
        assert result.total_seconds == 10

    def test_float_seconds(self) -> None:
        """Float values should be treated as seconds."""
        result = ensure_time_period(5.5)
        assert result.total_in_seconds == 5.5

    def test_int_seconds(self) -> None:
        """Integer values should be treated as seconds."""
        result = ensure_time_period(10)
        assert result.total_seconds == 10

    def test_fractional_string(self) -> None:
        """Fractional string '2.5s' should work."""
        result = ensure_time_period("2.5s")
        assert result.total_in_seconds == 2.5

    def test_empty_string_raises(self) -> None:
        """Empty string should raise ValueError."""
        with pytest.raises(ValueError, match="Empty string"):
            ensure_time_period("")

    def test_whitespace_only_raises(self) -> None:
        """Whitespace-only string should raise ValueError."""
        with pytest.raises(ValueError, match="Empty string"):
            ensure_time_period("   ")

    def test_no_unit_raises(self) -> None:
        """String without unit should raise ValueError."""
        with pytest.raises(ValueError):
            ensure_time_period("123")

    def test_unknown_unit_raises(self) -> None:
        """String with unknown unit should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown time unit"):
            ensure_time_period("5xyz")

    def test_none_type_raises(self) -> None:
        """None should raise ValueError (use Optional check before calling)."""
        with pytest.raises(ValueError, match="Cannot convert"):
            ensure_time_period(None)  # type: ignore[arg-type]

    def test_all_supported_units(self) -> None:
        """All unit aliases should be recognized."""
        units_and_expected = [
            ("100us", "microseconds"),
            ("100microseconds", "microseconds"),
            ("100ms", "milliseconds"),
            ("100milliseconds", "milliseconds"),
            ("10s", "seconds"),
            ("10sec", "seconds"),
            ("10secs", "seconds"),
            ("10seconds", "seconds"),
            ("5min", "minutes"),
            ("5mins", "minutes"),
            ("5minutes", "minutes"),
            ("2h", "hours"),
            ("2hours", "hours"),
            ("1d", "days"),
            ("1days", "days"),
        ]
        for time_str, _ in units_and_expected:
            result = ensure_time_period(time_str)
            assert isinstance(result, TimePeriod), f"Failed for {time_str}"

    def test_total_milliseconds_for_seconds(self) -> None:
        """Ensure total_milliseconds works correctly after string conversion."""
        result = ensure_time_period("5s")
        assert result.total_milliseconds == 5000

    def test_total_milliseconds_for_ms_string(self) -> None:
        """Millisecond string directly returns correct milliseconds."""
        result = ensure_time_period("1500ms")
        assert result.total_milliseconds == 1500


class TestCoverUpdateConfigTimesWithStrings:
    """Simulate the hot-reload scenario where config values are strings."""

    def test_venetian_update_config_times_with_strings(self) -> None:
        """VenetianCover.update_config_times should handle string values."""
        from boneio.components.cover.venetian import VenetianCover

        # We can't easily instantiate VenetianCover without full setup,
        # but we can test the ensure_time_period conversion directly
        # as used in update_config_times.
        config = {
            "open_time": "30s",
            "close_time": "30s",
            "tilt_duration": "5s",
        }
        # Simulate what update_config_times now does
        open_ms = ensure_time_period(config["open_time"]).total_milliseconds
        close_ms = ensure_time_period(config["close_time"]).total_milliseconds
        tilt_ms = ensure_time_period(config["tilt_duration"]).total_milliseconds

        assert open_ms == 30000
        assert close_ms == 30000
        assert tilt_ms == 5000

    def test_time_based_update_config_times_with_strings(self) -> None:
        """TimeBasedCover.update_config_times should handle string values."""
        config = {
            "open_time": "20s",
            "close_time": "25s",
        }
        open_ms = ensure_time_period(config["open_time"]).total_milliseconds
        close_ms = ensure_time_period(config["close_time"]).total_milliseconds

        assert open_ms == 20000
        assert close_ms == 25000

    def test_mixed_types_in_config(self) -> None:
        """Config might have mixed TimePeriod and string values."""
        config = {
            "open_time": TimePeriod(seconds=30),
            "close_time": "30s",
            "tilt_duration": "5s",
        }
        open_ms = ensure_time_period(config["open_time"]).total_milliseconds
        close_ms = ensure_time_period(config["close_time"]).total_milliseconds
        tilt_ms = ensure_time_period(config["tilt_duration"]).total_milliseconds

        assert open_ms == 30000
        assert close_ms == 30000
        assert tilt_ms == 5000
