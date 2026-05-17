"""Tests for WaterSource sequential output activation/deactivation."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from boneio.components.irrigation.water_source import WaterSource


def _mock_output(output_id: str, turn_on_result: bool = True) -> MagicMock:
    """Create a mock output with async_turn_on/off.

    Args:
        output_id: The ID for this mock output.
        turn_on_result: Return value for async_turn_on (True=ok, False=blocked).
    """
    out = MagicMock()
    out.id = output_id
    out.async_turn_on = AsyncMock(return_value=turn_on_result)
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
        result = await source.activate(timestamp=ts)
        assert result is True
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
            out.async_turn_on = AsyncMock(
                side_effect=lambda n=name, **kw: (call_order.append(("ON", n)), True)[-1]
            )
            outputs.append(out)

        source = WaterSource(
            id="rain", name="Rain", outputs=outputs,
            output_start_delay_s=1,
        )

        result = await source.activate(timestamp=time.time())
        assert result is True
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
        result = await source.activate(timestamp=time.time())
        elapsed = asyncio.get_event_loop().time() - start
        assert result is True
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
        result = await source.activate(timestamp=time.time())
        elapsed = asyncio.get_event_loop().time() - start
        assert result is True
        assert elapsed < 0.1
        for out in outputs:
            out.async_turn_on.assert_called_once()

    @pytest.mark.asyncio
    async def test_output_ids_property(self):
        """output_ids should return list of output IDs."""
        outputs = [_mock_output("OUT_01"), _mock_output("OUT_02")]
        source = WaterSource(id="test", name="Test", outputs=outputs)
        assert source.output_ids == ["OUT_01", "OUT_02"]


class TestWaterSourceInterlockRollback:
    """Test interlock blocking and rollback behavior."""

    @pytest.mark.asyncio
    async def test_activate_blocked_second_output_rollback(self):
        """When second output is blocked, first should be rolled back."""
        out1 = _mock_output("OUT_01", turn_on_result=True)
        out2 = _mock_output("OUT_02", turn_on_result=False)
        out3 = _mock_output("OUT_03", turn_on_result=True)

        source = WaterSource(id="rain", name="Rain", outputs=[out1, out2, out3])

        result = await source.activate(timestamp=time.time())
        assert result is False
        # OUT_01 was activated then rolled back
        out1.async_turn_on.assert_called_once()
        out1.async_turn_off.assert_called_once()
        # OUT_02 was attempted but blocked
        out2.async_turn_on.assert_called_once()
        # OUT_03 was never attempted
        out3.async_turn_on.assert_not_called()

    @pytest.mark.asyncio
    async def test_activate_blocked_first_output_no_rollback(self):
        """When first output is blocked, nothing to roll back."""
        out1 = _mock_output("OUT_01", turn_on_result=False)
        out2 = _mock_output("OUT_02", turn_on_result=True)

        source = WaterSource(id="rain", name="Rain", outputs=[out1, out2])

        result = await source.activate(timestamp=time.time())
        assert result is False
        out1.async_turn_on.assert_called_once()
        out1.async_turn_off.assert_not_called()
        out2.async_turn_on.assert_not_called()

    @pytest.mark.asyncio
    async def test_activate_all_ok_returns_true(self):
        """All outputs OK returns True."""
        outputs = [_mock_output("OUT_01"), _mock_output("OUT_02")]
        source = WaterSource(id="city", name="City", outputs=outputs)
        result = await source.activate(timestamp=time.time())
        assert result is True
