"""Unit tests for BuzzerOutput."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from boneio.components.output.buzzer import BuzzerOutput
from boneio.const import OFF, ON


class TestBuzzerOutput:
    """Test BuzzerOutput component."""

    @pytest.fixture
    def sysfs_path(self, tmp_path):
        """Provide a temporary file path simulating sysfs led brightness."""
        return str(tmp_path / "brightness")

    @pytest.fixture
    def mock_event_bus(self):
        return MagicMock()

    @pytest.fixture
    def mock_message_bus(self):
        return MagicMock()

    @pytest.mark.asyncio
    async def test_initialization_off(self, sysfs_path, mock_event_bus, mock_message_bus):
        """Buzzer should initialize to 0 in sysfs when restored_state is False."""
        buzzer = BuzzerOutput(
            sysfs_path=sysfs_path,
            id="test_buzzer",
            name="Test Buzzer",
            event_bus=mock_event_bus,
            topic_prefix="boneio",
            restored_state=False,
            message_bus=mock_message_bus,
        )

        assert os.path.exists(sysfs_path)
        with open(sysfs_path, "r") as f:
            assert f.read().strip() == "0"
        assert buzzer.state == OFF
        assert buzzer.is_active is False

    @pytest.mark.asyncio
    async def test_initialization_on(self, sysfs_path, mock_event_bus, mock_message_bus):
        """Buzzer should initialize to 1 in sysfs when restored_state is True."""
        buzzer = BuzzerOutput(
            sysfs_path=sysfs_path,
            id="test_buzzer",
            name="Test Buzzer",
            event_bus=mock_event_bus,
            topic_prefix="boneio",
            restored_state=True,
            message_bus=mock_message_bus,
        )

        assert os.path.exists(sysfs_path)
        with open(sysfs_path, "r") as f:
            assert f.read().strip() == "1"
        assert buzzer.state == ON
        assert buzzer.is_active is True

    @pytest.mark.asyncio
    async def test_turn_on(self, sysfs_path, mock_event_bus, mock_message_bus):
        """Buzzer should write 1 to sysfs on turn_on."""
        buzzer = BuzzerOutput(
            sysfs_path=sysfs_path,
            id="test_buzzer",
            name="Test Buzzer",
            event_bus=mock_event_bus,
            topic_prefix="boneio",
            restored_state=False,
            message_bus=mock_message_bus,
        )

        buzzer.turn_on()
        with open(sysfs_path, "r") as f:
            assert f.read().strip() == "1"
        assert buzzer.state == ON
        assert buzzer.is_active is True

    @pytest.mark.asyncio
    async def test_turn_off(self, sysfs_path, mock_event_bus, mock_message_bus):
        """Buzzer should write 0 to sysfs on turn_off."""
        buzzer = BuzzerOutput(
            sysfs_path=sysfs_path,
            id="test_buzzer",
            name="Test Buzzer",
            event_bus=mock_event_bus,
            topic_prefix="boneio",
            restored_state=True,
            message_bus=mock_message_bus,
        )

        buzzer.turn_off()
        with open(sysfs_path, "r") as f:
            assert f.read().strip() == "0"
        assert buzzer.state == OFF
        assert buzzer.is_active is False

    @pytest.mark.asyncio
    async def test_is_active_reads_sysfs(self, sysfs_path, mock_event_bus, mock_message_bus):
        """is_active property should read current state from sysfs."""
        buzzer = BuzzerOutput(
            sysfs_path=sysfs_path,
            id="test_buzzer",
            name="Test Buzzer",
            event_bus=mock_event_bus,
            topic_prefix="boneio",
            restored_state=False,
            message_bus=mock_message_bus,
        )

        # Manually alter sysfs value from outside
        with open(sysfs_path, "w") as f:
            f.write("1")

        assert buzzer.is_active is True

        with open(sysfs_path, "w") as f:
            f.write("0")

        assert buzzer.is_active is False

    @pytest.mark.asyncio
    async def test_fallback_when_file_not_found(self, mock_event_bus, mock_message_bus):
        """is_active and functions should fall back gracefully if sysfs path does not exist."""
        non_existent_path = "/non/existent/path/brightness"
        buzzer = BuzzerOutput(
            sysfs_path=non_existent_path,
            id="test_buzzer",
            name="Test Buzzer",
            event_bus=mock_event_bus,
            topic_prefix="boneio",
            restored_state=False,
            message_bus=mock_message_bus,
        )

        # Should not crash and should return standard state
        assert buzzer.is_active is False
        buzzer.turn_on()
        assert buzzer.state == ON
        assert buzzer.is_active is True
