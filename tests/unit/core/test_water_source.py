"""Tests for WaterSource sequential output activation/deactivation."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from boneio.components.irrigation.water_source import WaterSource


def _mock_output(output_id: str) -> MagicMock:
    """Create a mock output with async_turn_on/off."""
    out = MagicMock()
    out.id = output_id
    out.async_turn_on = AsyncMock()
    out.async_turn_off = AsyncMock()
    return out


class TestWaterSourceActivateDeactivate:
    """Test basic activate/deactivate without delays."""

    @pytest.fixture()
    def source(self):
        outputs = [_mock_output("OUT_01"), _mock_output("OUT_02"), _mock_output("OUT_03")]
        return WaterSource(id="test", name="Test", outputs=outputs)

    @pytest.mark.asyncio
    async def test_activate_all_outputs(self, source):
        """All outputs should be turned on."""
        ts = time.time()
        await source.activate(timestamp=ts)
        for out in source.outputs:
            out.async_turn_on.assert_called_once_with(timestamp=ts)

    @pytest.mark.asyncio
    async def test_deactivate_all_outputs(self, source):
        """All outputs should be turned off."""
        ts = time.time()
        await source.deactivate(timestamp=ts)
        for out in source.outputs:
            out.async_turn_off.assert_called_once_with(timestamp=ts)


class TestWaterSourceSequentialDelay:
    """Test sequential activation with delays."""

    @pytest.mark.asyncio
    async def test_activate_sequential_order(self):
        """Outputs should activate in order (first to last)."""
        call_order = []
        outputs = []
        for name in ["OUT_01", "OUT_02", "OUT_03"]:
            out = _mock_output(name)
            out.async_turn_on = AsyncMock(side_effect=lambda n=name, **kw: call_order.append(("ON", n)))
            outputs.append(out)

        source = WaterSource(
            id="rain", name="Rain", outputs=outputs,
            output_start_delay_s=1,
        )

        await source.activate(timestamp=time.time())
        assert call_order == [("ON", "OUT_01"), ("ON", "OUT_02"), ("ON", "OUT_03")]

    @pytest.mark.asyncio
    async def test_deactivate_reverse_order(self):
        """Outputs should deactivate in reverse order (last to first)."""
        call_order = []
        outputs = []
        for name in ["OUT_01", "OUT_02", "OUT_03"]:
            out = _mock_output(name)
            out.async_turn_off = AsyncMock(side_effect=lambda n=name, **kw: call_order.append(("OFF", n)))
            outputs.append(out)

        source = WaterSource(
            id="rain", name="Rain", outputs=outputs,
            output_stop_delay_s=1,
        )

        await source.deactivate(timestamp=time.time())
        assert call_order == [("OFF", "OUT_03"), ("OFF", "OUT_02"), ("OFF", "OUT_01")]

    @pytest.mark.asyncio
    async def test_activate_no_delay_single_output(self):
        """Single output should not trigger any sleep."""
        out = _mock_output("OUT_01")
        source = WaterSource(
            id="city", name="City", outputs=[out],
            output_start_delay_s=5,
        )
        start = asyncio.get_event_loop().time()
        await source.activate(timestamp=time.time())
        elapsed = asyncio.get_event_loop().time() - start
        out.async_turn_on.assert_called_once()
        # No sleep should occur for a single output
        assert elapsed < 0.1

    @pytest.mark.asyncio
    async def test_activate_zero_delay_no_sleep(self):
        """Zero delay should not trigger sleeps between outputs."""
        outputs = [_mock_output("OUT_01"), _mock_output("OUT_02")]
        source = WaterSource(
            id="city", name="City", outputs=outputs,
            output_start_delay_s=0,
        )
        start = asyncio.get_event_loop().time()
        await source.activate(timestamp=time.time())
        elapsed = asyncio.get_event_loop().time() - start
        assert elapsed < 0.1
        for out in outputs:
            out.async_turn_on.assert_called_once()

    @pytest.mark.asyncio
    async def test_output_ids_property(self):
        """output_ids should return list of output IDs."""
        outputs = [_mock_output("OUT_01"), _mock_output("OUT_02")]
        source = WaterSource(id="test", name="Test", outputs=outputs)
        assert source.output_ids == ["OUT_01", "OUT_02"]
