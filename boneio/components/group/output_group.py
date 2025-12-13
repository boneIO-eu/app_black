"""Group output module."""

from __future__ import annotations

import asyncio
import time
from typing import override

from boneio.components.output.basic import BasicOutput
from boneio.const import COVER, OFF, ON, SWITCH
from boneio.models import OutputState
from boneio.models.events import GroupEvent
from boneio.models.state import GroupState


class OutputGroup(BasicOutput):
    """Output group for managing multiple outputs as a single entity."""

    def __init__(
        self,
        members: list[BasicOutput],
        output_type: str = SWITCH,
        restored_state: bool = False,
        all_on_behaviour: bool = False,
        **kwargs,
    ) -> None:
        """Initialize output group.
        
        Args:
            members: List of BasicOutput instances to group
            output_type: Type of output (default: SWITCH)
            restored_state: Whether to restore state on restart
            all_on_behaviour: If True, group is ON only when all members are ON.
                            If False, group is ON when any member is ON.
            **kwargs: Additional arguments passed to BasicOutput
        """
        self._loop = asyncio.get_event_loop()
        super().__init__(
            **kwargs,
            output_type=output_type,
            restored_state=False,
            topic_type="group",
        )
        self._all_on_behaviour = all_on_behaviour
        self._group_members = [x for x in members if x.output_type != COVER]
        self._timer_handle = None
        self.check_state()

        # Subscribe to member state changes
        for member in self._group_members:
            self._event_bus.add_event_listener(
                event_type="output",
                entity_id=member.id,
                listener_id=self.id,
                target=self.event_listener,
            )

    def check_state(self) -> None:
        """Check initial state based on members."""
        for x in self._group_members:
            if x.state == ON:
                self._state = ON
                return

    async def event_listener(self, event: OutputState | None = None) -> None:
        """Listen for events called by children outputs.
        
        Args:
            event: Output state event from a member
        """
        if self._all_on_behaviour:
            # All must be ON for group to be ON
            state = (
                ON if all(x.state == ON for x in self._group_members) else OFF
            )
        else:
            # Any ON means group is ON
            state = (
                ON if any(x.state == ON for x in self._group_members) else OFF
            )
        
        if state != self._state or not event:
            self._state = state
            self._loop.create_task(self.async_send_state())

    async def async_turn_on(self, timestamp=None) -> None:
        """Turn on all members in the group.
        
        Executes turn_on sequentially to prevent I2C bus contention
        when multiple outputs are on the same GPIO expander.
        
        Args:
            timestamp: Optional timestamp for the operation
        """
        for x in self._group_members:
            await x.async_turn_on(timestamp=timestamp)

    async def async_turn_off(self, timestamp=None) -> None:
        """Turn off all members in the group.
        
        Executes turn_off sequentially to prevent I2C bus contention
        when multiple outputs are on the same GPIO expander.
        
        Args:
            timestamp: Optional timestamp for the operation
        """
        for x in self._group_members:
            await x.async_turn_off(timestamp=timestamp)

    @property
    def is_active(self) -> bool:
        """Check if group is active (ON state)."""
        return self._state == ON

    @override
    async def async_send_state(self, optimized_value: str | None = None) -> None:
        """Send state to message bus and event bus for WebSocket."""
        # Send to MQTT
        self._message_bus.send_message(
            topic=self._send_topic, payload=self.payload(), retain=True
        )
        
        # Send to WebSocket via event bus
        self._last_timestamp = time.time()
        group_state = GroupState(
            id=self.id,
            name=self.name,
            state=self._state,
            type=self._output_type,
            timestamp=self._last_timestamp,
        )
        group_event = GroupEvent(
            entity_id=self.id,
            state=group_state,
        )
        self._event_bus.trigger_event(group_event)

    def cleanup(self) -> None:
        """Cleanup resources before removing/reloading group.
        
        Removes event listeners from member outputs and clears references.
        """
        # Remove event listeners for member state changes
        for member in self._group_members:
            try:
                self._event_bus.remove_event_listener(
                    event_type="output",
                    entity_id=member.id,
                    listener_id=self.id,
                )
            except Exception:
                pass  # Ignore errors if listener already removed
        
        # Cancel any pending timer
        if self._timer_handle:
            self._timer_handle.cancel()
            self._timer_handle = None
        
        # Clear member references
        self._group_members.clear()

