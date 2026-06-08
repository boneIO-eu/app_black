"""Template Manager — orchestrates composite virtual entities.

Parses the ``template:`` config section and delegates to platform-specific
sub-managers (ThermostatManager, AlarmManager, GateCoverManager).
Routes sensor / input events and manages lifecycle (start, stop, reload).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from boneio.core.manager.templates.alarm import AlarmManager
from boneio.core.manager.templates.gate_cover import GateCoverManager
from boneio.core.manager.templates.thermostat import ThermostatManager

if TYPE_CHECKING:
    from boneio.core.manager.manager import Manager

_LOGGER = logging.getLogger(__name__)


class TemplateManager:
    """Orchestrates template sub-managers and routes events between them.

    Args:
        manager: Reference to the main Manager.
        template_config: List of template definitions from YAML config.
    """

    def __init__(
        self,
        manager: Manager,
        template_config: list[dict[str, Any]],
    ) -> None:
        self._manager = manager

        self._thermostats = ThermostatManager(manager)
        self._alarms = AlarmManager(manager)
        self._gates = GateCoverManager(manager)

        for entry in template_config:
            platform = entry.get("platform", "")
            try:
                if platform == "thermostat":
                    self._thermostats.configure(entry)
                elif platform == "alarm_control_panel":
                    self._alarms.configure(entry)
                elif platform == "gate_cover":
                    self._gates.configure(entry)
                else:
                    _LOGGER.warning("Unknown template platform: %s", platform)
            except Exception as err:
                _LOGGER.error(
                    "Failed to configure template '%s' (%s): %s",
                    entry.get("id", "?"), platform, err,
                )

        _LOGGER.info(
            "TemplateManager initialized: %d thermostats, %d alarm panels, %d gate covers",
            len(self._thermostats.items),
            len(self._alarms.items),
            len(self._gates.items),
        )

    # -- Sub-manager accessors -----------------------------------------------

    @property
    def thermostat_manager(self) -> ThermostatManager:
        """Thermostat sub-manager."""
        return self._thermostats

    @property
    def alarm_manager(self) -> AlarmManager:
        """Alarm panel sub-manager."""
        return self._alarms

    @property
    def gate_manager(self) -> GateCoverManager:
        """Gate cover sub-manager."""
        return self._gates

    # -- Event routing -------------------------------------------------------

    def _on_sensor_event(self, event: Any) -> None:
        """Handle SensorEvent from EventBus and route to matching thermostats.

        Args:
            event: SensorEvent with entity_id and state.
        """
        sensor_id = event.entity_id
        try:
            temperature = float(event.state.state)
        except (ValueError, TypeError, AttributeError):
            return

        matched = self._thermostats.sensor_map.get(sensor_id, [])
        if not matched:
            _LOGGER.debug(
                "SensorEvent '%s' (%.1f°C) has no matching thermostat. "
                "Registered sensor_ids: %s",
                sensor_id, temperature,
                list(self._thermostats.sensor_map.keys()),
            )
        for thermostat in matched:
            thermostat.update_sensor_temperature(sensor_id, temperature)

    def on_input_event(self, input_id: str, event_type: str) -> None:
        """Route input event to matching alarm panels and gate covers.

        Called by InputManager when an input fires.

        Args:
            input_id: The input entity ID.
            event_type: Event type (pressed, single, etc.).
        """
        for alarm in self._alarms.input_map.get(input_id, []):
            alarm.on_input_event(input_id, event_type)

        gates = self._gates.input_map.get(input_id, [])
        if gates:
            is_closed = event_type in ("pressed", "single", "double", "long")
            for gate in gates:
                gate.on_sensor_event(input_id, is_closed)

    # -- HA autodiscovery resend ---------------------------------------------

    async def send_ha_autodiscovery(self) -> None:
        """Resend HA autodiscovery for all template entities."""
        self._thermostats.publish_all_discovery()
        self._alarms.publish_all_discovery()
        self._gates.publish_all_discovery()

    # -- Lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        """Start all template entities (subscribe to MQTT, register EventBus)."""
        self._register_sensor_listeners()
        _LOGGER.info(
            "TemplateManager registered %d sensor listeners",
            len(self._thermostats.sensor_map),
        )

        for thermostat in self._thermostats.items:
            await thermostat.start()
        for alarm in self._alarms.items:
            await alarm.start()
        for gate in self._gates.items:
            await gate.start()
        _LOGGER.info("TemplateManager started all entities")

    async def stop(self) -> None:
        """Stop all template entities and remove EventBus listeners."""
        event_bus = self._manager.event_bus
        for sensor_id in self._thermostats.sensor_map:
            event_bus.remove_event_listener(
                event_type="sensor",
                entity_id=sensor_id,
                listener_id=f"template_mgr_{sensor_id}",
            )
        for thermostat in self._thermostats.items:
            await thermostat.stop()
        for alarm in self._alarms.items:
            await alarm.stop()
        for gate in self._gates.items:
            await gate.stop()

    # -- Hot reload ----------------------------------------------------------

    async def reload_templates(self) -> None:
        """Reload template configuration from file.

        Handles adding, removing, and updating all template entities
        without requiring a full application restart.
        """
        _LOGGER.info("Reloading template configuration")

        config = self._manager._config_helper.get_config()
        new_template_config: list[dict[str, Any]] = config.get("template", [])

        # Build maps of new entities by ID
        new_thermostats: dict[str, dict[str, Any]] = {}
        new_alarms: dict[str, dict[str, Any]] = {}
        new_gates: dict[str, dict[str, Any]] = {}
        for entry in new_template_config:
            platform = entry.get("platform", "")
            eid = entry.get("id", "")
            if not eid:
                continue
            if platform == "thermostat":
                new_thermostats[eid] = entry
            elif platform == "alarm_control_panel":
                new_alarms[eid] = entry
            elif platform == "gate_cover":
                new_gates[eid] = entry

        current_thermostat_ids = {t.id for t in self._thermostats.items}
        current_alarm_ids = {a.id for a in self._alarms.items}
        current_gate_ids = {g.id for g in self._gates.items}

        # --- Remove deleted ---
        for tid in current_thermostat_ids - set(new_thermostats.keys()):
            await self._thermostats.remove(tid)
        for aid in current_alarm_ids - set(new_alarms.keys()):
            await self._alarms.remove(aid)
        for gid in current_gate_ids - set(new_gates.keys()):
            await self._gates.remove(gid)

        # --- Add new / update existing thermostats ---
        for eid, entry in new_thermostats.items():
            if eid in current_thermostat_ids:
                await self._thermostats.remove(eid)
            try:
                self._thermostats.configure(entry)
            except Exception as err:
                _LOGGER.error("Failed to configure thermostat '%s': %s", eid, err)
                continue
            thermostat = self._thermostats.get(eid)
            if thermostat:
                await thermostat.start()

        # --- Add new / update existing alarm panels ---
        for eid, entry in new_alarms.items():
            if eid in current_alarm_ids:
                await self._alarms.remove(eid)
            try:
                self._alarms.configure(entry)
            except Exception as err:
                _LOGGER.error("Failed to configure alarm panel '%s': %s", eid, err)
                continue
            alarm = self._alarms.get(eid)
            if alarm:
                await alarm.start()

        # --- Add new / update existing gate covers ---
        for eid, entry in new_gates.items():
            if eid in current_gate_ids:
                await self._gates.remove(eid)
            try:
                self._gates.configure(entry)
            except Exception as err:
                _LOGGER.error("Failed to configure gate cover '%s': %s", eid, err)
                continue
            gate = self._gates.get(eid)
            if gate:
                await gate.start()

        # Re-register all sensor EventBus listeners (clean slate)
        self._register_sensor_listeners()

        _LOGGER.info(
            "Template reload complete: %d thermostats, %d alarm panels, %d gate covers",
            len(self._thermostats.items),
            len(self._alarms.items),
            len(self._gates.items),
        )

    # -- Internal helpers ----------------------------------------------------

    def _register_sensor_listeners(self) -> None:
        """Register (or re-register) EventBus listeners for all sensor → thermostat mappings."""
        event_bus = self._manager.event_bus

        # Remove all existing template sensor listeners
        for sensor_id in list(self._thermostats.sensor_map.keys()):
            event_bus.remove_event_listener(
                event_type="sensor",
                entity_id=sensor_id,
                listener_id=f"template_mgr_{sensor_id}",
            )

        # Re-register for current mappings (native SensorEvent sources)
        for sensor_id in self._thermostats.sensor_map:
            event_bus.add_event_listener(
                event_type="sensor",
                entity_id=sensor_id,
                listener_id=f"template_mgr_{sensor_id}",
                target=self._on_sensor_event,
            )

        _LOGGER.info(
            "Registered sensor listeners for thermostat sensor_ids: %s",
            list(self._thermostats.sensor_map.keys()),
        )
