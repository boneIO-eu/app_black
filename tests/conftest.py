"""Pytest configuration and shared fixtures for BoneIO tests."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ============================================================================
# GPIO Mocks (for running tests without hardware)
# ============================================================================

@pytest.fixture(autouse=True)
def mock_gpiod():
    """Mock gpiod module for tests running without hardware."""
    mock_chip = MagicMock()
    mock_line = MagicMock()
    mock_chip.get_line.return_value = mock_line
    
    with patch.dict("sys.modules", {
        "gpiod": MagicMock(),
    }):
        yield mock_chip


@pytest.fixture
def mock_config_helper():
    """Provide a mock ConfigHelper for HA integration tests."""
    helper = MagicMock()
    helper.topic_prefix = "boneio"
    helper.ha_discovery = True
    helper.ha_discovery_prefix = "homeassistant"
    helper.ha_child_devices = False
    return helper


# ============================================================================
# I2C Mocks
# ============================================================================

@pytest.fixture
def mock_smbus():
    """Provide a MockSMBus instance."""
    from tests.mocks.i2c import MockSMBus
    return MockSMBus(bus_number=2)


@pytest.fixture
def mock_i2c():
    """Provide a MockSMBus2I2C instance."""
    from tests.mocks.i2c import MockSMBus2I2C
    return MockSMBus2I2C(bus_number=2)


@pytest.fixture
def mock_i2c_with_mcp23017(mock_i2c):
    """Provide MockSMBus2I2C with MCP23017 at 0x20."""
    from tests.mocks.i2c import MockMCP23017Registers
    mock_i2c.add_device(0x20, MockMCP23017Registers.default())
    return mock_i2c


@pytest.fixture
def mock_i2c_with_pcf8575(mock_i2c):
    """Provide MockSMBus2I2C with PCF8575 at 0x20."""
    from tests.mocks.i2c import MockPCF8575Registers
    mock_i2c.add_device(0x20, MockPCF8575Registers.default())
    return mock_i2c


@pytest.fixture
def mock_i2c_with_pca9685(mock_i2c):
    """Provide MockSMBus2I2C with PCA9685 at 0x40."""
    from tests.mocks.i2c import MockPCA9685Registers
    mock_i2c.add_device(0x40, MockPCA9685Registers.default())
    return mock_i2c


# ============================================================================
# Configuration Fixtures
# ============================================================================

@pytest.fixture
def minimal_config() -> dict:
    """Provide minimal valid configuration."""
    return {
        "mqtt": {
            "host": "localhost",
            "username": "test",
            "password": "test",
        },
        "version": "0.8",
    }


@pytest.fixture
def config_with_outputs() -> dict:
    """Provide configuration with output definitions."""
    return {
        "mqtt": {
            "host": "localhost",
            "username": "test",
            "password": "test",
        },
        "version": "0.8",
        "output": [
            {
                "id": "relay_1",
                "pin": "P8_11",
                "kind": "gpio",
                "output_type": "relay",
            },
            {
                "id": "relay_2",
                "mcp_id": "mcp1",
                "pin": 0,
                "kind": "mcp",
                "output_type": "relay",
            },
        ],
        "mcp23017": [
            {
                "id": "mcp1",
                "address": "0x20",
            },
        ],
    }


@pytest.fixture
def config_with_inputs() -> dict:
    """Provide configuration with input definitions."""
    return {
        "mqtt": {
            "host": "localhost",
            "username": "test",
            "password": "test",
        },
        "version": "0.8",
        "binary_sensor": [
            {
                "id": "button_1",
                "pin": "P8_12",
            },
        ],
        "event": [
            {
                "id": "switch_1",
                "pin": "P8_13",
                "actions": {
                    "pressed": [
                        {"action": "output", "pin": "relay_1", "action_output": "toggle"},
                    ],
                },
            },
        ],
    }


# ============================================================================
# Async Fixtures
# ============================================================================

@pytest.fixture
def event_loop_policy():
    """Provide event loop policy for async tests."""
    import asyncio
    return asyncio.DefaultEventLoopPolicy()


# ============================================================================
# Markers
# ============================================================================

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "hardware: tests requiring real hardware"
    )
    config.addinivalue_line(
        "markers", "slow: slow running tests"
    )
    config.addinivalue_line(
        "markers", "integration: integration tests"
    )
