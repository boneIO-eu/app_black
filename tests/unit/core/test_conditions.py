"""Tests for conditional action execution.

Tests evaluate_conditions, check_single_condition, and all three condition types:
  - time: hourly ranges with midnight crossover
  - date: monthly ranges with new year crossover
  - state: entity state checks (binary_sensor, cover, output/light)
"""

import pytest
from datetime import datetime, time as dt_time
from unittest.mock import MagicMock

from boneio.core.utils.conditions import (
    evaluate_conditions,
    check_single_condition,
    _check_time_condition,
    _check_date_condition,
    _check_state_condition,
    _parse_time,
    _parse_date,
)


# ---------------------------------------------------------------------------
# _parse_time
# ---------------------------------------------------------------------------

class TestParseTime:
    """Tests for time string parsing."""

    def test_parse_hh_mm(self):
        assert _parse_time("05:00") == dt_time(5, 0)

    def test_parse_hh_mm_ss(self):
        assert _parse_time("22:30:45") == dt_time(22, 30, 45)

    def test_parse_midnight(self):
        assert _parse_time("00:00") == dt_time(0, 0)

    def test_parse_end_of_day(self):
        assert _parse_time("23:59") == dt_time(23, 59)

    def test_parse_with_whitespace(self):
        assert _parse_time("  05:00  ") == dt_time(5, 0)

    def test_parse_invalid_format_raises(self):
        with pytest.raises(ValueError):
            _parse_time("5")

    def test_parse_invalid_hour_raises(self):
        with pytest.raises(ValueError):
            _parse_time("25:00")


# ---------------------------------------------------------------------------
# _parse_date
# ---------------------------------------------------------------------------

class TestParseDate:
    """Tests for date string parsing."""

    def test_parse_valid_date(self):
        assert _parse_date("11-01") == (11, 1)

    def test_parse_december(self):
        assert _parse_date("12-31") == (12, 31)

    def test_parse_january(self):
        assert _parse_date("01-01") == (1, 1)

    def test_parse_with_whitespace(self):
        assert _parse_date("  03-15  ") == (3, 15)

    def test_parse_invalid_month_raises(self):
        with pytest.raises(ValueError):
            _parse_date("13-01")

    def test_parse_invalid_day_raises(self):
        with pytest.raises(ValueError):
            _parse_date("01-32")

    def test_parse_invalid_format_raises(self):
        with pytest.raises(ValueError):
            _parse_date("2026-01-15")


# ---------------------------------------------------------------------------
# _check_time_condition
# ---------------------------------------------------------------------------

class TestCheckTimeCondition:
    """Tests for time-based condition checking."""

    def test_normal_range_inside(self):
        """10:00 is inside 05:00-22:00."""
        now = datetime(2026, 3, 29, 10, 0, 0)
        assert _check_time_condition({"after": "05:00", "before": "22:00"}, now=now) is True

    def test_normal_range_outside_after(self):
        """23:00 is outside 05:00-22:00."""
        now = datetime(2026, 3, 29, 23, 0, 0)
        assert _check_time_condition({"after": "05:00", "before": "22:00"}, now=now) is False

    def test_normal_range_outside_before(self):
        """04:00 is outside 05:00-22:00."""
        now = datetime(2026, 3, 29, 4, 0, 0)
        assert _check_time_condition({"after": "05:00", "before": "22:00"}, now=now) is False

    def test_normal_range_at_boundary_after(self):
        """05:00 is exactly at the 'after' boundary (inclusive)."""
        now = datetime(2026, 3, 29, 5, 0, 0)
        assert _check_time_condition({"after": "05:00", "before": "22:00"}, now=now) is True

    def test_normal_range_at_boundary_before(self):
        """22:00 is exactly at the 'before' boundary (exclusive)."""
        now = datetime(2026, 3, 29, 22, 0, 0)
        assert _check_time_condition({"after": "05:00", "before": "22:00"}, now=now) is False

    def test_midnight_crossover_evening(self):
        """23:00 is inside 22:00-06:00 (midnight crossover)."""
        now = datetime(2026, 3, 29, 23, 0, 0)
        assert _check_time_condition({"after": "22:00", "before": "06:00"}, now=now) is True

    def test_midnight_crossover_early_morning(self):
        """03:00 is inside 22:00-06:00 (midnight crossover)."""
        now = datetime(2026, 3, 29, 3, 0, 0)
        assert _check_time_condition({"after": "22:00", "before": "06:00"}, now=now) is True

    def test_midnight_crossover_daytime(self):
        """12:00 is outside 22:00-06:00 (midnight crossover)."""
        now = datetime(2026, 3, 29, 12, 0, 0)
        assert _check_time_condition({"after": "22:00", "before": "06:00"}, now=now) is False

    def test_midnight_crossover_at_midnight(self):
        """00:00 is inside 22:00-06:00."""
        now = datetime(2026, 3, 29, 0, 0, 0)
        assert _check_time_condition({"after": "22:00", "before": "06:00"}, now=now) is True

    def test_only_after(self):
        """With only 'after', checks >= after."""
        now = datetime(2026, 3, 29, 23, 0, 0)
        assert _check_time_condition({"after": "18:00"}, now=now) is True

    def test_only_after_fails(self):
        now = datetime(2026, 3, 29, 10, 0, 0)
        assert _check_time_condition({"after": "18:00"}, now=now) is False

    def test_only_before(self):
        """With only 'before', checks < before."""
        now = datetime(2026, 3, 29, 10, 0, 0)
        assert _check_time_condition({"before": "18:00"}, now=now) is True

    def test_only_before_fails(self):
        now = datetime(2026, 3, 29, 20, 0, 0)
        assert _check_time_condition({"before": "18:00"}, now=now) is False

    def test_neither_after_nor_before_always_true(self):
        """No time constraints = always true."""
        now = datetime(2026, 3, 29, 12, 0, 0)
        assert _check_time_condition({}, now=now) is True

    def test_invalid_time_format_returns_true(self):
        """Invalid time format should not block action (fail-open)."""
        now = datetime(2026, 3, 29, 12, 0, 0)
        assert _check_time_condition({"after": "bad"}, now=now) is True


# ---------------------------------------------------------------------------
# _check_date_condition
# ---------------------------------------------------------------------------

class TestCheckDateCondition:
    """Tests for date-based condition checking."""

    def test_normal_range_inside(self):
        """July 15 is inside Mar 1 - Oct 31."""
        now = datetime(2026, 7, 15, 10, 0, 0)
        assert _check_date_condition({"after": "03-01", "before": "10-31"}, now=now) is True

    def test_normal_range_outside(self):
        """January 15 is outside Mar 1 - Oct 31."""
        now = datetime(2026, 1, 15, 10, 0, 0)
        assert _check_date_condition({"after": "03-01", "before": "10-31"}, now=now) is False

    def test_normal_range_at_boundary_start(self):
        """Mar 1 is at the start boundary (inclusive)."""
        now = datetime(2026, 3, 1, 10, 0, 0)
        assert _check_date_condition({"after": "03-01", "before": "10-31"}, now=now) is True

    def test_normal_range_at_boundary_end(self):
        """Oct 31 is at the end boundary (inclusive)."""
        now = datetime(2026, 10, 31, 10, 0, 0)
        assert _check_date_condition({"after": "03-01", "before": "10-31"}, now=now) is True

    def test_year_crossover_winter(self):
        """January 15 is inside Nov 1 - Mar 31 (new year crossover)."""
        now = datetime(2026, 1, 15, 10, 0, 0)
        assert _check_date_condition({"after": "11-01", "before": "03-31"}, now=now) is True

    def test_year_crossover_november(self):
        """November 15 is inside Nov 1 - Mar 31 (new year crossover)."""
        now = datetime(2026, 11, 15, 10, 0, 0)
        assert _check_date_condition({"after": "11-01", "before": "03-31"}, now=now) is True

    def test_year_crossover_summer_outside(self):
        """July 15 is outside Nov 1 - Mar 31 (new year crossover)."""
        now = datetime(2026, 7, 15, 10, 0, 0)
        assert _check_date_condition({"after": "11-01", "before": "03-31"}, now=now) is False

    def test_year_crossover_march_boundary(self):
        """March 31 is at the end boundary (inclusive)."""
        now = datetime(2026, 3, 31, 10, 0, 0)
        assert _check_date_condition({"after": "11-01", "before": "03-31"}, now=now) is True

    def test_only_after(self):
        now = datetime(2026, 12, 1, 10, 0, 0)
        assert _check_date_condition({"after": "11-01"}, now=now) is True

    def test_only_before(self):
        now = datetime(2026, 2, 15, 10, 0, 0)
        assert _check_date_condition({"before": "03-31"}, now=now) is True


# ---------------------------------------------------------------------------
# _check_state_condition
# ---------------------------------------------------------------------------

class TestCheckStateCondition:
    """Tests for entity state condition checking."""

    def test_is_on_with_active_entity(self):
        entity = MagicMock(is_active=True)
        resolver = MagicMock(return_value=entity)
        cond = {"entity": "output", "entity_id": "relay_1", "state": "is_on"}
        assert _check_state_condition(cond, state_resolver=resolver) is True
        resolver.assert_called_once_with("output", "relay_1")

    def test_is_off_with_inactive_entity(self):
        entity = MagicMock(is_active=False)
        resolver = MagicMock(return_value=entity)
        cond = {"entity": "output", "entity_id": "relay_1", "state": "is_off"}
        assert _check_state_condition(cond, state_resolver=resolver) is True

    def test_is_on_with_inactive_entity_fails(self):
        entity = MagicMock(is_active=False)
        resolver = MagicMock(return_value=entity)
        cond = {"entity": "light", "entity_id": "led_1", "state": "is_on"}
        assert _check_state_condition(cond, state_resolver=resolver) is False

    def test_is_open_with_open_cover(self):
        entity = MagicMock(is_open=True)
        resolver = MagicMock(return_value=entity)
        cond = {"entity": "cover", "entity_id": "blind_1", "state": "is_open"}
        assert _check_state_condition(cond, state_resolver=resolver) is True

    def test_is_closed_with_open_cover(self):
        entity = MagicMock(is_open=True)
        resolver = MagicMock(return_value=entity)
        cond = {"entity": "cover", "entity_id": "blind_1", "state": "is_closed"}
        assert _check_state_condition(cond, state_resolver=resolver) is False

    def test_is_closed_with_closed_cover(self):
        entity = MagicMock(is_open=False)
        resolver = MagicMock(return_value=entity)
        cond = {"entity": "cover", "entity_id": "blind_1", "state": "is_closed"}
        assert _check_state_condition(cond, state_resolver=resolver) is True

    def test_entity_not_found_returns_true(self):
        """Missing entity should not block action (fail-open)."""
        resolver = MagicMock(return_value=None)
        cond = {"entity": "output", "entity_id": "unknown", "state": "is_on"}
        assert _check_state_condition(cond, state_resolver=resolver) is True

    def test_no_resolver_returns_true(self):
        """No resolver = can't check state, fail-open."""
        cond = {"entity": "output", "entity_id": "relay_1", "state": "is_on"}
        assert _check_state_condition(cond, state_resolver=None) is True

    def test_missing_fields_returns_true(self):
        """Incomplete condition = fail-open."""
        resolver = MagicMock()
        assert _check_state_condition({"entity": "output"}, state_resolver=resolver) is True

    def test_unknown_state_returns_true(self):
        """Unknown state keyword = fail-open."""
        entity = MagicMock()
        resolver = MagicMock(return_value=entity)
        cond = {"entity": "output", "entity_id": "relay_1", "state": "is_magic"}
        assert _check_state_condition(cond, state_resolver=resolver) is True


# ---------------------------------------------------------------------------
# check_single_condition
# ---------------------------------------------------------------------------

class TestCheckSingleCondition:
    """Tests for the condition type dispatcher."""

    def test_time_condition(self):
        now = datetime(2026, 3, 29, 10, 0, 0)
        cond = {"type": "time", "after": "05:00", "before": "22:00"}
        assert check_single_condition(cond, now=now) is True

    def test_date_condition(self):
        now = datetime(2026, 1, 15, 10, 0, 0)
        cond = {"type": "date", "after": "11-01", "before": "03-31"}
        assert check_single_condition(cond, now=now) is True

    def test_state_condition(self):
        entity = MagicMock(is_active=True)
        resolver = MagicMock(return_value=entity)
        cond = {"type": "state", "entity": "output", "entity_id": "relay_1", "state": "is_on"}
        assert check_single_condition(cond, state_resolver=resolver) is True

    def test_unknown_type_returns_true(self):
        """Unknown condition type = fail-open."""
        cond = {"type": "unknown"}
        assert check_single_condition(cond) is True


# ---------------------------------------------------------------------------
# evaluate_conditions
# ---------------------------------------------------------------------------

class TestEvaluateConditions:
    """Tests for the main condition evaluator."""

    def test_no_conditions_returns_true(self):
        assert evaluate_conditions() is True

    def test_single_condition_passing(self):
        now = datetime(2026, 3, 29, 10, 0, 0)
        cond = {"type": "time", "after": "05:00", "before": "22:00"}
        assert evaluate_conditions(condition=cond, now=now) is True

    def test_single_condition_failing(self):
        now = datetime(2026, 3, 29, 23, 0, 0)
        cond = {"type": "time", "after": "05:00", "before": "22:00"}
        assert evaluate_conditions(condition=cond, now=now) is False

    def test_multiple_conditions_and_all_pass(self):
        now = datetime(2026, 1, 15, 14, 0, 0)  # Winter daytime
        conds = {
            "mode": "and",
            "list": [
                {"type": "time", "after": "05:00", "before": "22:00"},
                {"type": "date", "after": "11-01", "before": "03-31"},
            ],
        }
        assert evaluate_conditions(conditions=conds, now=now) is True

    def test_multiple_conditions_and_one_fails(self):
        now = datetime(2026, 7, 15, 14, 0, 0)  # Summer daytime
        conds = {
            "mode": "and",
            "list": [
                {"type": "time", "after": "05:00", "before": "22:00"},  # passes
                {"type": "date", "after": "11-01", "before": "03-31"},  # fails (summer)
            ],
        }
        assert evaluate_conditions(conditions=conds, now=now) is False

    def test_multiple_conditions_or_one_passes(self):
        now = datetime(2026, 7, 15, 14, 0, 0)  # Summer daytime
        conds = {
            "mode": "or",
            "list": [
                {"type": "time", "after": "05:00", "before": "22:00"},  # passes
                {"type": "date", "after": "11-01", "before": "03-31"},  # fails
            ],
        }
        assert evaluate_conditions(conditions=conds, now=now) is True

    def test_multiple_conditions_or_all_fail(self):
        now = datetime(2026, 7, 15, 23, 0, 0)  # Summer nighttime
        conds = {
            "mode": "or",
            "list": [
                {"type": "time", "after": "05:00", "before": "22:00"},  # fails (23:00)
                {"type": "date", "after": "11-01", "before": "03-31"},  # fails (summer)
            ],
        }
        assert evaluate_conditions(conditions=conds, now=now) is False

    def test_default_mode_is_and(self):
        now = datetime(2026, 7, 15, 14, 0, 0)
        conds = {
            "list": [
                {"type": "time", "after": "05:00", "before": "22:00"},
                {"type": "date", "after": "11-01", "before": "03-31"},
            ],
        }
        # No mode specified → defaults to "and" → False (date fails in summer)
        assert evaluate_conditions(conditions=conds, now=now) is False

    def test_empty_conditions_list_returns_true(self):
        assert evaluate_conditions(conditions={"mode": "and", "list": []}) is True

    def test_mixed_time_date_state_and(self):
        """All three condition types combined with AND."""
        now = datetime(2026, 1, 15, 14, 0, 0)
        entity = MagicMock(is_active=True)
        resolver = MagicMock(return_value=entity)
        conds = {
            "mode": "and",
            "list": [
                {"type": "time", "after": "05:00", "before": "22:00"},
                {"type": "date", "after": "11-01", "before": "03-31"},
                {"type": "state", "entity": "binary_sensor", "entity_id": "motion", "state": "is_on"},
            ],
        }
        assert evaluate_conditions(conditions=conds, state_resolver=resolver, now=now) is True

    def test_mixed_with_state_failing(self):
        """State condition fails → AND returns False."""
        now = datetime(2026, 1, 15, 14, 0, 0)
        entity = MagicMock(is_active=False)  # OFF
        resolver = MagicMock(return_value=entity)
        conds = {
            "mode": "and",
            "list": [
                {"type": "time", "after": "05:00", "before": "22:00"},
                {"type": "state", "entity": "binary_sensor", "entity_id": "motion", "state": "is_on"},
            ],
        }
        assert evaluate_conditions(conditions=conds, state_resolver=resolver, now=now) is False
