"""Water source configuration for irrigation controllers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from boneio.components.template import BasicOutput


@dataclass
class WaterSource:
    """Represents a water source with its associated outputs and timing.

    A water source defines which physical outputs (valves, pumps) need to be
    activated to supply water from this particular source.

    When multiple outputs are defined and output_start_delay_s > 0,
    outputs are activated sequentially (in order) with the specified delay
    between each. On deactivation, outputs are turned off in reverse order.

    Example sources:
    - City water: single valve (OUT_06)
    - Rainwater: valve (OUT_07) + pump (OUT_08) with 2s sequential delay

    Attributes:
        id: Unique identifier for this water source.
        name: Human-readable name.
        outputs: List of outputs to activate when this source is selected.
        output_start_delay_s: Seconds to wait between activating each output (sequential ON).
        output_stop_delay_s: Seconds to wait between deactivating each output (sequential OFF, reverse order).
        pump_start_pump_delay_s: Seconds to wait after opening valve before starting pump.
        pump_start_valve_delay_s: Seconds to wait after starting pump before opening zone valve.
        pump_stop_pump_delay_s: Seconds to wait after closing zone valve before stopping pump.
        pump_stop_valve_delay_s: Seconds to wait after stopping pump before closing source valve.
        pump_switch_off_during_valve_open_delay: Turn off pump during valve open delay.
    """

    id: str
    name: str
    outputs: list[BasicOutput] = field(default_factory=list)
    output_start_delay_s: int = 0
    output_stop_delay_s: int = 0
    pump_start_pump_delay_s: int = 0
    pump_start_valve_delay_s: int = 0
    pump_stop_pump_delay_s: int = 0
    pump_stop_valve_delay_s: int = 0
    pump_switch_off_during_valve_open_delay: bool = False

    async def activate(self, timestamp: float) -> None:
        """Turn ON all outputs for this water source.

        When output_start_delay_s > 0, outputs are activated sequentially
        (first to last) with the configured delay between each one.

        Args:
            timestamp: Current timestamp for relay control.
        """
        for i, output in enumerate(self.outputs):
            await output.async_turn_on(timestamp=timestamp)
            if self.output_start_delay_s > 0 and i < len(self.outputs) - 1:
                await asyncio.sleep(self.output_start_delay_s)

    async def deactivate(self, timestamp: float) -> None:
        """Turn OFF all outputs for this water source.

        When output_stop_delay_s > 0, outputs are deactivated in reverse
        order (last to first) with the configured delay between each one.

        Args:
            timestamp: Current timestamp for relay control.
        """
        reversed_outputs = list(reversed(self.outputs))
        for i, output in enumerate(reversed_outputs):
            await output.async_turn_off(timestamp=timestamp)
            if self.output_stop_delay_s > 0 and i < len(reversed_outputs) - 1:
                await asyncio.sleep(self.output_stop_delay_s)

    @property
    def output_ids(self) -> list[str]:
        """Return list of output IDs for display/logging."""
        return [o.id for o in self.outputs]

