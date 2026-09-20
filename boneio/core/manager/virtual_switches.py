"""Virtual switches: build them, restore them, announce them.

Small by design. A virtual switch has no hardware to probe, no bus to share
and nothing that can fail at runtime, so this manager only has to get three
things right: the state it comes up in, the Home Assistant announcement, and
finding one by id when a condition or an action asks for it.

Commands arrive through ``Manager.receive_message`` — the controller already
subscribes to the whole ``cmd/+/+/#`` tree, so there is nothing to subscribe
to here.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from boneio.components.virtual_switch import VirtualSwitch
from boneio.const import VIRTUAL_SWITCH

if TYPE_CHECKING:
    from boneio.core.manager import Manager

_LOGGER = logging.getLogger(__name__)


class VirtualSwitchManager:
    """Owns every configured virtual switch.

    Args:
        manager: The manager, for the message bus, the event bus and state.
        config: The parsed ``virtual_switch:`` section.
    """

    def __init__(self, manager: Manager, config: list[dict] | None = None) -> None:
        self._manager = manager
        self._switches: dict[str, VirtualSwitch] = {}
        self._configure(config or [])

    def _configure(self, config: list[dict]) -> None:
        """Build the switches, restoring the state of the ones that ask for it."""
        for entry in config:
            switch_id = entry.get("id")
            if not switch_id:
                _LOGGER.error("Virtual switch without an id, skipping: %s", entry)
                continue
            if switch_id in self._switches:
                _LOGGER.error("Duplicate virtual switch id '%s', skipping.", switch_id)
                continue

            restore = entry.get("restore_state", True)
            initial = bool(entry.get("initial", False))
            restored = (
                bool(
                    self._manager._state_manager.get(
                        attr_type=VIRTUAL_SWITCH, attr=switch_id, default_value=initial
                    )
                )
                if restore
                else initial
            )

            switch = VirtualSwitch(
                id=switch_id,
                name=entry.get("name") or switch_id,
                icon=entry.get("icon"),
                area=entry.get("area"),
                show_in_ha=entry.get("show_in_ha", True),
                restored_state=restored,
                event_bus=self._manager._event_bus,
                message_bus=self._manager._message_bus,
                topic_prefix=self._manager._topic_prefix,
                state_save=self._make_saver(switch_id) if restore else None,
                action_runner=self._manager.execute_actions,
            )
            self._switches[switch_id] = switch

        # Second pass: an action may target another virtual switch, and
        # resolving that needs every switch to exist first.
        for entry in config:
            switch = self._switches.get(entry.get("id"))
            if switch is None:
                continue
            raw = entry.get("actions") or {}
            if not raw:
                continue
            switch.set_actions(
                self._manager.parse_actions(pin=switch.id, actions=raw)
            )

        if self._switches:
            _LOGGER.info(
                "Configured %d virtual switch(es): %s",
                len(self._switches),
                list(self._switches),
            )

    def _make_saver(self, switch_id: str):
        """Return a callback that persists one switch's state.

        Stores the boolean rather than the "ON"/"OFF" string: the state file is
        read back by :meth:`_configure` as a boolean, and a type that survives
        a round trip through JSON without a parse step is one less thing to get
        wrong on a device that loses power mid-write.
        """

        def save(state: str) -> None:
            self._manager._state_manager.save_attribute(
                attr_type=VIRTUAL_SWITCH, attribute=switch_id, value=state == "ON"
            )

        return save

    # ── lookups ──────────────────────────────────────────────────────────

    def get(self, switch_id: str) -> VirtualSwitch | None:
        """Find a switch by id, or None."""
        return self._switches.get(switch_id)

    def all(self) -> list[VirtualSwitch]:
        """Every configured switch."""
        return list(self._switches.values())

    # ── announcements ────────────────────────────────────────────────────

    def publish_discovery(self) -> None:
        """Announce every switch to Home Assistant."""
        from boneio.integration.homeassistant import ha_switch_availabilty_message

        for switch in self._switches.values():
            if not switch.show_in_ha:
                continue
            payload = ha_switch_availabilty_message(
                id=switch.id,
                name=switch.name,
                config_helper=self._manager._config_helper,
                device_type=VIRTUAL_SWITCH,
                area=switch.area,
            )
            if switch.icon:
                payload["icon"] = switch.icon
            self._manager.publish_ha_discovery(
                id=switch.id, ha_type="switch", payload=payload
            )

    async def republish_states(self) -> None:
        """Re-publish every state.

        Retained messages usually make this unnecessary. Usually: a broker that
        was reinstalled, or one configured without persistence, comes back with
        an empty retained set, and a mode nobody can see is a mode nobody
        trusts.
        """
        for switch in self._switches.values():
            await switch.async_send_state()

    # ── reload ───────────────────────────────────────────────────────────

    async def reload(self, config: list[dict] | None) -> None:
        """Adopt a new section.

        Switches that survive keep their state — reloading the configuration
        should not silently turn off a mode the house is running on. Only ones
        that were removed lose it, which is what removing them means.

        The state is handed over with ``async_adopt_state`` rather than a turn
        on: a reload is not somebody flipping the switch, and running the
        actions here would fire every configured scene each time anyone saved
        an unrelated edit on this page.
        """
        previous = self._switches
        self._switches = {}
        self._configure(config or [])

        for switch_id, switch in self._switches.items():
            kept = previous.get(switch_id)
            if kept is not None and kept.is_active != switch.is_active:
                await switch.async_adopt_state(kept.is_active)

        self.publish_discovery()
        await self.republish_states()
