"""Tests for remote output interlock integration.

Tests verify that:
1. Remote outputs check interlock before turning ON
2. Local outputs block remote outputs in the same interlock group
3. Remote outputs block local outputs in the same interlock group
4. Enforce interlock turns OFF remote output on external violation
5. Without enforce, external ON is allowed even on violation
6. set_interlock() updates groups on existing remote output
7. interlock_groups appear in OutputState events
"""

from __future__ import annotations

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mock gpiod before importing boneio modules
mock_gpiod = MagicMock()
mock_gpiod.line = MagicMock()
mock_gpiod.line.Bias = MagicMock()
mock_gpiod.line.Direction = MagicMock()
mock_gpiod.line.Edge = MagicMock()
mock_gpiod.EdgeEvent = MagicMock()
mock_gpiod.LineRequest = MagicMock()
sys.modules.setdefault("gpiod", mock_gpiod)
sys.modules.setdefault("gpiod.line", mock_gpiod.line)

from boneio.components.output.remote import RemoteOutputBase
from boneio.const import OFF, ON
from boneio.integration.interlock import SoftwareInterlockManager


# ==================== Helpers ====================


def _make_remote_output(
    id: str = "remote_pump",
    interlock_manager: SoftwareInterlockManager | None = None,
    interlock_groups: list[str] | None = None,
    enforce_interlock: bool = False,
) -> RemoteOutputBase:
    """Create a RemoteOutputBase with interlock configuration.

    Args:
        id: Output entity ID.
        interlock_manager: Shared interlock manager.
        interlock_groups: Interlock group names.
        enforce_interlock: Whether to enforce interlock on external changes.

    Returns:
        Configured RemoteOutputBase with mocked device manager.
    """
    event_bus = MagicMock()
    output = RemoteOutputBase(
        id=id,
        name=id.replace("_", " ").title(),
        device_id="esphome_1",
        output_id="relay_1",
        remote_source="esphome_api",
        event_bus=event_bus,
        output_type="switch",
        interlock_manager=interlock_manager,
        interlock_groups=interlock_groups,
        enforce_interlock=enforce_interlock,
    )
    # Provide a mocked device manager
    device_mgr = MagicMock()
    device_mgr.control_output = AsyncMock(return_value=True)
    output._device_manager = device_mgr
    return output


def _make_local_output(
    id: str = "local_pump",
    state: str = OFF,
) -> MagicMock:
    """Create a mock local output (BasicOutput) for interlock tests.

    Args:
        id: Output entity ID.
        state: Initial state (ON/OFF).

    Returns:
        Mock with .state property.
    """
    output = MagicMock()
    output.id = id
    output.state = state
    return output


# ==================== check_interlock ====================


class TestRemoteCheckInterlock:
    """Test RemoteOutputBase.check_interlock()."""

    def test_no_interlock_returns_true(self):
        """Without interlock manager, check_interlock always returns True."""
        output = _make_remote_output()
        assert output.check_interlock() is True

    def test_empty_groups_returns_true(self):
        """With empty interlock groups, check_interlock returns True."""
        mgr = SoftwareInterlockManager()
        output = _make_remote_output(interlock_manager=mgr, interlock_groups=[])
        assert output.check_interlock() is True

    def test_no_conflict_returns_true(self):
        """With no conflicting output ON, check_interlock returns True."""
        mgr = SoftwareInterlockManager()
        local = _make_local_output(state=OFF)
        mgr.register(local, ["pumps"])

        output = _make_remote_output(
            interlock_manager=mgr, interlock_groups=["pumps"]
        )
        mgr.register(output, ["pumps"])

        assert output.check_interlock() is True

    def test_conflict_returns_false(self):
        """When local output in same group is ON, check_interlock returns False."""
        mgr = SoftwareInterlockManager()
        local = _make_local_output(state=ON)
        mgr.register(local, ["pumps"])

        output = _make_remote_output(
            interlock_manager=mgr, interlock_groups=["pumps"]
        )
        mgr.register(output, ["pumps"])

        assert output.check_interlock() is False


# ==================== async_turn_on with interlock ====================


class TestRemoteTurnOnInterlock:
    """Test async_turn_on() respects interlock."""

    async def test_turn_on_allowed_no_conflict(self):
        """Should turn ON when no interlock conflict."""
        mgr = SoftwareInterlockManager()
        output = _make_remote_output(
            interlock_manager=mgr, interlock_groups=["pumps"]
        )
        mgr.register(output, ["pumps"])

        result = await output.async_turn_on()
        assert result is True
        assert output.state == ON

    async def test_turn_on_blocked_by_local(self):
        """Should be blocked when local output in same group is ON."""
        mgr = SoftwareInterlockManager()
        local = _make_local_output(state=ON)
        mgr.register(local, ["pumps"])

        output = _make_remote_output(
            interlock_manager=mgr, interlock_groups=["pumps"]
        )
        mgr.register(output, ["pumps"])

        result = await output.async_turn_on()
        assert result is False
        assert output.state == OFF  # Stayed OFF

    async def test_turn_on_blocked_by_remote(self):
        """Should be blocked when another remote output in same group is ON."""
        mgr = SoftwareInterlockManager()

        remote_a = _make_remote_output(
            id="remote_a",
            interlock_manager=mgr,
            interlock_groups=["pumps"],
        )
        mgr.register(remote_a, ["pumps"])

        remote_b = _make_remote_output(
            id="remote_b",
            interlock_manager=mgr,
            interlock_groups=["pumps"],
        )
        mgr.register(remote_b, ["pumps"])

        # Turn on A
        await remote_a.async_turn_on()
        assert remote_a.state == ON

        # B should be blocked
        result = await remote_b.async_turn_on()
        assert result is False
        assert remote_b.state == OFF

    async def test_turn_on_no_interlock_always_succeeds(self):
        """Without interlock, turn ON always succeeds."""
        output = _make_remote_output()
        result = await output.async_turn_on()
        assert result is True
        assert output.state == ON


# ==================== Local blocked by remote ====================


class TestLocalBlockedByRemote:
    """Test that local outputs are blocked by remote outputs."""

    def test_local_blocked_when_remote_is_on(self):
        """SoftwareInterlockManager should block local when remote is ON."""
        mgr = SoftwareInterlockManager()

        remote = _make_remote_output(
            interlock_manager=mgr, interlock_groups=["pumps"]
        )
        mgr.register(remote, ["pumps"])
        remote._state = ON  # Simulate remote ON

        local = _make_local_output(state=OFF)
        mgr.register(local, ["pumps"])

        # Local should be blocked
        assert mgr.can_turn_on(local, ["pumps"]) is False

    def test_local_allowed_when_remote_is_off(self):
        """Local should be allowed when remote is OFF."""
        mgr = SoftwareInterlockManager()

        remote = _make_remote_output(
            interlock_manager=mgr, interlock_groups=["pumps"]
        )
        mgr.register(remote, ["pumps"])
        remote._state = OFF

        local = _make_local_output(state=OFF)
        mgr.register(local, ["pumps"])

        assert mgr.can_turn_on(local, ["pumps"]) is True


# ==================== enforce_interlock ====================


class TestEnforceInterlock:
    """Test enforce_interlock on external state changes."""

    async def test_enforce_turns_off_on_violation(self):
        """With enforce_interlock, external ON violating interlock should trigger OFF."""
        mgr = SoftwareInterlockManager()

        local = _make_local_output(state=ON)
        mgr.register(local, ["pumps"])

        output = _make_remote_output(
            interlock_manager=mgr,
            interlock_groups=["pumps"],
            enforce_interlock=True,
        )
        mgr.register(output, ["pumps"])

        # Simulate external state change from ESPHome (bypassing async_turn_on)
        output.on_remote_state_change(True)

        # Give asyncio.ensure_future a chance to run
        await asyncio.sleep(0.2)

        # Should have called control_output OFF
        output._device_manager.control_output.assert_called_with(
            output_id="relay_1", action="OFF"
        )

    async def test_no_enforce_allows_violation(self):
        """Without enforce_interlock, external ON is allowed even on violation."""
        mgr = SoftwareInterlockManager()

        local = _make_local_output(state=ON)
        mgr.register(local, ["pumps"])

        output = _make_remote_output(
            interlock_manager=mgr,
            interlock_groups=["pumps"],
            enforce_interlock=False,
        )
        mgr.register(output, ["pumps"])

        # Simulate external ON
        output.on_remote_state_change(True)

        await asyncio.sleep(0.2)

        # Should NOT have sent OFF command
        output._device_manager.control_output.assert_not_called()
        # State should be ON (external change accepted)
        assert output.state == ON

    async def test_enforce_no_violation_stays_on(self):
        """With enforce but no violation, output stays ON."""
        mgr = SoftwareInterlockManager()

        output = _make_remote_output(
            interlock_manager=mgr,
            interlock_groups=["pumps"],
            enforce_interlock=True,
        )
        mgr.register(output, ["pumps"])

        # No other output in group is ON
        output.on_remote_state_change(True)

        await asyncio.sleep(0.2)

        # Should NOT have sent OFF
        output._device_manager.control_output.assert_not_called()
        assert output.state == ON

    async def test_enforce_off_state_not_triggered(self):
        """Enforce should not trigger on OFF state changes."""
        mgr = SoftwareInterlockManager()

        local = _make_local_output(state=ON)
        mgr.register(local, ["pumps"])

        output = _make_remote_output(
            interlock_manager=mgr,
            interlock_groups=["pumps"],
            enforce_interlock=True,
        )
        mgr.register(output, ["pumps"])
        output._state = ON  # Was ON

        # Simulate external OFF
        output.on_remote_state_change(False)

        await asyncio.sleep(0.2)

        output._device_manager.control_output.assert_not_called()
        assert output.state == OFF


# ==================== set_interlock ====================


class TestSetInterlock:
    """Test set_interlock() method."""

    def test_set_interlock_updates_groups(self):
        """set_interlock should update manager and groups on the output."""
        output = _make_remote_output()
        assert output._interlock_manager is None
        assert output._interlock_groups == []

        mgr = SoftwareInterlockManager()
        output.set_interlock(mgr, ["pumps", "heating"])

        assert output._interlock_manager is mgr
        assert output._interlock_groups == ["pumps", "heating"]


# ==================== State event includes interlock_groups ====================


class TestStateEventInterlock:
    """Test that interlock_groups appear in emitted OutputState."""

    def test_state_event_includes_interlock_groups(self):
        """OutputState emitted by remote output should include interlock_groups."""
        mgr = SoftwareInterlockManager()
        output = _make_remote_output(
            interlock_manager=mgr, interlock_groups=["pumps", "safety"]
        )

        # Trigger state event
        output.on_remote_state_change(True)

        # Check the event bus call
        output._event_bus.trigger_event.assert_called_once()
        event = output._event_bus.trigger_event.call_args[0][0]
        assert event.state.interlock_groups == ["pumps", "safety"]

    def test_state_event_empty_interlock_groups(self):
        """OutputState with no interlock groups should have empty list."""
        output = _make_remote_output()

        output.on_remote_state_change(True)

        event = output._event_bus.trigger_event.call_args[0][0]
        assert event.state.interlock_groups == []


# ==================== Multi-group scenarios ====================


class TestMultiGroupInterlock:
    """Test outputs in multiple interlock groups."""

    def test_blocked_by_any_shared_group(self):
        """If any shared group has a conflict, output is blocked."""
        mgr = SoftwareInterlockManager()

        local = _make_local_output(state=ON)
        mgr.register(local, ["group_b"])

        output = _make_remote_output(
            interlock_manager=mgr,
            interlock_groups=["group_a", "group_b"],
        )
        mgr.register(output, ["group_a", "group_b"])

        # Blocked because of group_b conflict
        assert output.check_interlock() is False

    def test_allowed_when_no_shared_conflict(self):
        """Allowed when conflicting output is in a different group."""
        mgr = SoftwareInterlockManager()

        local = _make_local_output(state=ON)
        mgr.register(local, ["group_c"])  # Different group

        output = _make_remote_output(
            interlock_manager=mgr,
            interlock_groups=["group_a", "group_b"],
        )
        mgr.register(output, ["group_a", "group_b"])

        assert output.check_interlock() is True
