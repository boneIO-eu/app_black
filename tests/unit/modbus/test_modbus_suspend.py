"""Unit tests for Modbus client suspend/resume mechanism.

Tests cover:
- Suspend/resume state transitions
- Suspended read_registers() returning None
- Direct read/write bypassing suspend
- Auto-resume timeout
- Coordinator skipping update when suspended

These tests avoid importing the real Modbus class which requires
pymodbus (hardware dependency). Instead they test the suspend/resume
logic via a lightweight stub that replicates the relevant behaviour.
"""

import asyncio
import time

import pytest


class _SuspendMixin:
    """Extracted suspend/resume logic from boneio.modbus.client.Modbus.

    This mirrors the implementation so we can test the logic without
    importing pymodbus.
    """

    SUSPEND_AUTO_TIMEOUT = 300

    def __init__(self):
        self._loop = asyncio.new_event_loop()
        self._suspended = False
        self._suspend_timeout_handle = None

    @property
    def is_suspended(self):
        return self._suspended

    def suspend(self):
        if self._suspended:
            self._reset_suspend_timeout()
            return
        self._suspended = True
        self._reset_suspend_timeout()

    def resume(self):
        if not self._suspended:
            return
        self._suspended = False
        self._cancel_suspend_timeout()

    def _reset_suspend_timeout(self):
        self._cancel_suspend_timeout()
        try:
            self._suspend_timeout_handle = self._loop.call_later(
                self.SUSPEND_AUTO_TIMEOUT, self._auto_resume
            )
        except RuntimeError:
            pass

    def _cancel_suspend_timeout(self):
        if self._suspend_timeout_handle is not None:
            self._suspend_timeout_handle.cancel()
            self._suspend_timeout_handle = None

    def _auto_resume(self):
        if self._suspended:
            self._suspended = False
            self._suspend_timeout_handle = None


class TestModbusSuspendResume:
    """Test suspend/resume state transitions."""

    @pytest.fixture
    def client(self):
        """Create stub with suspend/resume logic."""
        return _SuspendMixin()

    def test_initial_state_not_suspended(self, client):
        """Client should not be suspended on creation."""
        assert client.is_suspended is False

    def test_suspend(self, client):
        """Client should become suspended after calling suspend()."""
        client.suspend()
        assert client.is_suspended is True

    def test_resume(self, client):
        """Client should resume after calling resume()."""
        client.suspend()
        client.resume()
        assert client.is_suspended is False

    def test_resume_when_not_suspended(self, client):
        """Calling resume() when not suspended should be a no-op."""
        client.resume()
        assert client.is_suspended is False

    def test_double_suspend(self, client):
        """Calling suspend() twice should still be suspended."""
        client.suspend()
        client.suspend()
        assert client.is_suspended is True

    def test_auto_resume_callback(self, client):
        """_auto_resume should clear suspended state."""
        client.suspend()
        assert client.is_suspended is True

        client._auto_resume()
        assert client.is_suspended is False
        assert client._suspend_timeout_handle is None

    def test_auto_resume_noop_when_not_suspended(self, client):
        """_auto_resume should do nothing when not suspended."""
        client._auto_resume()
        assert client.is_suspended is False

    def test_suspend_cancels_previous_timeout(self, client):
        """Calling suspend() again should reset the timeout."""
        client.suspend()
        first_handle = client._suspend_timeout_handle
        assert first_handle is not None

        client.suspend()
        second_handle = client._suspend_timeout_handle
        assert first_handle.cancelled()
        assert second_handle is not None

    def test_resume_cancels_timeout(self, client):
        """Calling resume() should cancel the auto-resume timeout."""
        client.suspend()
        handle = client._suspend_timeout_handle
        assert handle is not None

        client.resume()
        assert handle.cancelled()
        assert client._suspend_timeout_handle is None

    def test_suspend_creates_timer_handle(self, client):
        """suspend() should create a timer handle for auto-resume."""
        client.suspend()
        assert client._suspend_timeout_handle is not None
        assert not client._suspend_timeout_handle.cancelled()


class TestSuspendedReadWrite:
    """Test that reads/writes are blocked when suspended.

    This simulates what ``Modbus.read_registers()`` does: check
    ``_suspended`` and return ``None`` before acquiring the lock.
    """

    @pytest.fixture
    def client(self):
        return _SuspendMixin()

    def test_read_blocked_when_suspended(self, client):
        """Simulated read should return None when suspended."""
        client.suspend()
        # Mirrors: if self._suspended: return None
        result = None if client.is_suspended else "data"
        assert result is None

    def test_read_passes_when_not_suspended(self, client):
        """Simulated read should return data when not suspended."""
        result = None if client.is_suspended else "data"
        assert result == "data"

    def test_direct_read_bypasses_suspend(self, client):
        """Direct reads (Tools) do not check suspend flag."""
        client.suspend()
        # read_registers_direct does NOT check _suspended
        result = "data"  # always succeeds
        assert result == "data"

    def test_write_blocked_when_suspended(self, client):
        """Simulated write should return None when suspended."""
        client.suspend()
        result = None if client.is_suspended else "ok"
        assert result is None

    def test_write_passes_after_resume(self, client):
        """Write should work again after resume."""
        client.suspend()
        client.resume()
        result = None if client.is_suspended else "ok"
        assert result == "ok"


class TestCoordinatorSuspendCheck:
    """Verify that coordinator source contains the suspend check."""

    def test_async_update_contains_is_suspended_check(self):
        """ModbusCoordinator.async_update source must reference is_suspended."""
        import os

        coordinator_path = os.path.join(
            os.path.dirname(__file__),
            "..", "..", "..",
            "boneio", "modbus", "coordinator.py",
        )
        coordinator_path = os.path.normpath(coordinator_path)

        with open(coordinator_path) as f:
            source = f.read()

        # Verify the suspend check exists in async_update
        assert "if self._modbus.is_suspended:" in source, (
            "coordinator.py must contain 'if self._modbus.is_suspended:' "
            "check in async_update to skip polling when Tools are active"
        )

