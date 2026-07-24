"""Unit tests for YAML serialization lock and pending save helpers in yaml_util."""

from __future__ import annotations

import threading
import time

import pytest

from boneio.core.config.yaml_util import (
    decrement_pending_yaml_saves,
    get_pending_yaml_saves_count,
    increment_pending_yaml_saves,
    wait_for_pending_yaml_saves,
    yaml_saves_pending,
)


def test_pending_saves_counter() -> None:
    """Test incrementing and decrementing pending YAML saves."""
    assert not yaml_saves_pending()
    assert get_pending_yaml_saves_count() == 0

    increment_pending_yaml_saves()
    assert yaml_saves_pending()
    assert get_pending_yaml_saves_count() == 1

    increment_pending_yaml_saves()
    assert get_pending_yaml_saves_count() == 2

    decrement_pending_yaml_saves()
    assert get_pending_yaml_saves_count() == 1
    assert yaml_saves_pending()

    decrement_pending_yaml_saves()
    assert get_pending_yaml_saves_count() == 0
    assert not yaml_saves_pending()

    # Decrementing past zero stays at zero
    decrement_pending_yaml_saves()
    assert get_pending_yaml_saves_count() == 0
    assert not yaml_saves_pending()


def test_wait_for_pending_yaml_saves_completes() -> None:
    """Test wait_for_pending_yaml_saves blocks until counter reaches 0."""
    increment_pending_yaml_saves()

    def _delayed_decrement() -> None:
        time.sleep(0.15)
        decrement_pending_yaml_saves()

    t = threading.Thread(target=_delayed_decrement)
    t.start()

    start_time = time.monotonic()
    result = wait_for_pending_yaml_saves(timeout=2.0)
    elapsed = time.monotonic() - start_time

    t.join()

    assert result is True
    assert 0.1 <= elapsed <= 1.0
    assert not yaml_saves_pending()


def test_wait_for_pending_yaml_saves_timeout() -> None:
    """Test wait_for_pending_yaml_saves times out if pending save never finishes."""
    increment_pending_yaml_saves()
    try:
        start_time = time.monotonic()
        result = wait_for_pending_yaml_saves(timeout=0.2)
        elapsed = time.monotonic() - start_time

        assert result is False
        assert 0.15 <= elapsed <= 0.5
    finally:
        decrement_pending_yaml_saves()
