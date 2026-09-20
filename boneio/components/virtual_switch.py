"""Virtual switches — a switch with nothing behind it.

Every other switch in boneIO ends at a relay. This one ends nowhere: it holds
an on/off state, publishes it, and accepts commands. Its whole purpose is to be
read by a condition, so that "IN_11 turns on OUT_11" can be qualified with
"...but only while evening mode is on", where evening mode is something a
person flips in Home Assistant, in the panel, or from another button.

boneIO owns the state, deliberately. Modelling this the other way round — an
`input_boolean` in Home Assistant that boneIO subscribes to — would mean the
controller forgets what mode it is in whenever the broker restarts or Home
Assistant is down, which is exactly when a building controller should keep
working on its own.

It looks like an output because from MQTT and Home Assistant it is one: same
state topic shape, same command topic, discovered as a `switch`. It is not one
in the code, because an output owns a pin and this owns nothing.
"""

from __future__ import annotations

import asyncio
import logging
import time

from boneio.const import OFF, ON, VIRTUAL_SWITCH
from boneio.core.events import EventBus
from boneio.core.messaging.basic_mqtt import BasicMqtt
from boneio.models.events import OutputEvent
from boneio.models.state import OutputState

_LOGGER = logging.getLogger(__name__)


class VirtualSwitch(BasicMqtt):
    """An on/off flag that lives in the controller.

    Args:
        id: Unique identifier, used in the MQTT topic.
        event_bus: EventBus, for telling the panel the state changed.
        topic_prefix: MQTT topic prefix.
        message_bus: MessageBus for MQTT.
        name: Display name; defaults to the id.
        icon: MDI icon for Home Assistant.
        area: Area for Home Assistant grouping.
        restored_state: The state to come up in, already resolved by the
            manager from the state file or the configured initial value.
        show_in_ha: Whether to announce it to Home Assistant.
        state_save: Callback invoked with the new state so it survives a
            restart. None disables persistence.
    """

    def __init__(
        self,
        id: str,
        event_bus: EventBus,
        topic_prefix: str,
        name: str | None = None,
        icon: str | None = None,
        area: str | None = None,
        restored_state: bool = False,
        show_in_ha: bool = True,
        state_save=None,
        **kwargs,
    ) -> None:
        super().__init__(
            id=id,
            name=name or id,
            topic_type=VIRTUAL_SWITCH,
            topic_prefix=topic_prefix,
            **kwargs,
        )
        self._event_bus = event_bus
        self._icon = icon
        self.area = area
        self._show_in_ha = show_in_ha
        self._state_save = state_save
        self._state = ON if restored_state else OFF
        self._last_timestamp = 0.0

    # ── state ────────────────────────────────────────────────────────────

    @property
    def state(self) -> str:
        """``"ON"`` or ``"OFF"``."""
        return self._state

    @property
    def is_active(self) -> bool:
        """Whether the switch is on.

        Named to match outputs and binary sensors: the condition evaluator
        reads this one property on all of them, so a virtual switch needs no
        special case there.
        """
        return self._state == ON

    @property
    def icon(self) -> str | None:
        """MDI icon for Home Assistant."""
        return self._icon

    @property
    def show_in_ha(self) -> bool:
        """Whether this switch is announced to Home Assistant."""
        return self._show_in_ha

    @property
    def last_timestamp(self) -> float:
        """When the state last changed."""
        return self._last_timestamp

    # ── commands ─────────────────────────────────────────────────────────

    async def async_turn_on(self, timestamp=None) -> bool:
        """Turn on.

        Returns:
            True, always. The signature matches an output's so the action
            dispatcher can treat both the same way; nothing can refuse here,
            there being no interlock and no hardware.
        """
        await self._set(ON)
        return True

    async def async_turn_off(self, timestamp=None) -> None:
        """Turn off."""
        await self._set(OFF)

    async def async_toggle(self, timestamp=None) -> None:
        """Flip the state."""
        await self._set(OFF if self.is_active else ON)

    async def _set(self, state: str) -> None:
        """Adopt a state, persist it, and tell everyone.

        Publishes even when the state has not changed: an unchanged retained
        message is what a broker that lost its retained set needs to see, and
        it costs nothing.
        """
        self._state = state
        self._last_timestamp = time.time()

        if self._state_save is not None:
            try:
                self._state_save(state)
            except Exception as err:  # noqa: BLE001 - a flag that cannot be saved still works
                _LOGGER.error("Could not save state of virtual switch '%s': %s", self.id, err)

        self._message_bus.send_message(
            topic=self._send_topic,
            payload={"state": state},
            retain=True,
        )
        self._event_bus.trigger_event(
            OutputEvent(
                entity_id=self.id,
                state=OutputState(
                    id=self.id,
                    name=self.name,
                    state=state,
                    # The discriminator the panel groups on. A virtual switch
                    # travels the same WebSocket channel as an output because
                    # it is the same shape of thing to a viewer — something
                    # with a name that is on or off.
                    type=VIRTUAL_SWITCH,
                    expander_id=None,
                    pin=None,
                    timestamp=self._last_timestamp,
                    area=self.area,
                ),
            )
        )
        _LOGGER.debug("Virtual switch '%s' is now %s", self.id, state)

    async def async_send_state(self) -> None:
        """Re-publish the current state without changing it."""
        await self._set(self._state)

    def turn_on(self, timestamp=None) -> None:
        """Synchronous turn on, for callers outside the loop."""
        asyncio.get_event_loop().create_task(self.async_turn_on(timestamp))

    def turn_off(self, timestamp=None) -> None:
        """Synchronous turn off, for callers outside the loop."""
        asyncio.get_event_loop().create_task(self.async_turn_off(timestamp))
