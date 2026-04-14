"""Water source configuration for irrigation controllers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from boneio.components.template import BasicOutput


@dataclass
class WaterSource:
    """Represents a water source with its associated outputs and timing.

    A water source defines which physical outputs (valves, pumps) need to be
    activated to supply water from this particular source.

    Example sources:
    - City water: single valve (OUT_06)
    - Rainwater: valve (OUT_07) + pump (OUT_08) with pump delays

    Attributes:
        id: Unique identifier for this water source.
        name: Human-readable name.
        outputs: List of outputs to activate when this source is selected.
        pump_start_pump_delay_s: Seconds to wait after opening valve before starting pump.
        pump_start_valve_delay_s: Seconds to wait after starting pump before opening zone valve.
        pump_stop_pump_delay_s: Seconds to wait after closing zone valve before stopping pump.
        pump_stop_valve_delay_s: Seconds to wait after stopping pump before closing source valve.
        pump_switch_off_during_valve_open_delay: Turn off pump during valve open delay.
    """

    id: str
    name: str
    outputs: list[BasicOutput] = field(default_factory=list)
    pump_start_pump_delay_s: int = 0
    pump_start_valve_delay_s: int = 0
    pump_stop_pump_delay_s: int = 0
    pump_stop_valve_delay_s: int = 0
    pump_switch_off_during_valve_open_delay: bool = False

    async def activate(self, timestamp: float) -> None:
        """Turn ON all outputs for this water source.

        Args:
            timestamp: Current timestamp for relay control.
        """
        for output in self.outputs:
            await output.async_turn_on(timestamp=timestamp)

    async def deactivate(self, timestamp: float) -> None:
        """Turn OFF all outputs for this water source.

        Args:
            timestamp: Current timestamp for relay control.
        """
        for output in self.outputs:
            await output.async_turn_off(timestamp=timestamp)

    @property
    def output_ids(self) -> list[str]:
        """Return list of output IDs for display/logging."""
        return [o.id for o in self.outputs]
