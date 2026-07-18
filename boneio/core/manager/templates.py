"""Template Manager — orchestrates composite virtual entities.

Parses the ``template:`` config section and instantiates platform-specific
components (thermostat, alarm_control_panel).  Wires sensor events to
thermostats and input events to alarm panels.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from boneio.components.template.alarm_panel import (
    AlarmOutput,
    AlarmPinCode,
    AlarmZone,
    BoneIOAlarmPanel,
    ZoneInput,
)
from boneio.components.template.gate_cover import BoneIOGateCover, CYCLE_CLOSE, CYCLE_OPEN
from boneio.components.template.thermostat import BoneIOThermostat
from boneio.const import ALARM_CONTROL_PANEL, CLIMATE, CLOSED, COVER, IDLE, OPEN
from boneio.core.utils.timeperiod import parse_time_to_ms, parse_time_to_seconds

if TYPE_CHECKING:
    from boneio.core.manager.manager import Manager

_LOGGER = logging.getLogger(__name__)


class TemplateManager:
    """Manages template entities (thermostats, alarm panels, etc.).

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
        self._thermostats: list[BoneIOThermostat] = []
        self._alarm_panels: list[BoneIOAlarmPanel] = []
        self._gate_covers: list[BoneIOGateCover] = []

        # Map sensor_id → list of thermostats that use it
        self._sensor_thermostat_map: dict[str, list[BoneIOThermostat]] = {}
        # Map input_id → list of alarm panels that monitor it
        self._input_alarm_map: dict[str, list[BoneIOAlarmPanel]] = {}
        # Map input_id → list of gate covers that monitor it (contact sensors)
        self._input_gate_map: dict[str, list[BoneIOGateCover]] = {}

        for entry in template_config:
            platform = entry.get("platform", "")
            try:
                if platform == "thermostat":
                    self._configure_thermostat(entry)
                elif platform == "alarm_control_panel":
                    self._configure_alarm_panel(entry)
                elif platform == "gate_cover":
                    self._configure_gate_cover(entry)
                else:
                    _LOGGER.warning("Unknown template platform: %s", platform)
            except Exception as err:
                _LOGGER.error(
                    "Failed to configure template '%s' (%s): %s",
                    entry.get("id", "?"), platform, err,
                )

        _LOGGER.info(
            "TemplateManager initialized: %d thermostats, %d alarm panels, %d gate covers",
            len(self._thermostats), len(self._alarm_panels), len(self._gate_covers),
        )

    # -- Configuration -------------------------------------------------------

    def _configure_thermostat(self, config: dict[str, Any]) -> None:
        """Configure a thermostat from YAML config.

        Args:
            config: Thermostat configuration dictionary.
        """
        entity_id = config.get("id", "")
        name = config.get("name", entity_id)
        output_id = config.get("output_id", "")
        mode = config.get("mode", "heat")
        target_temp = config.get("target_temperature", 21.0)
        area = config.get("area")

        # Parse sensor_ids (list) with fallback to single sensor_id
        sensor_ids: list[str] = config.get("sensor_ids", [])
        if not sensor_ids:
            single = config.get("sensor_id", "")
            if single:
                sensor_ids = [single]

        # Parse hysteresis — could be float or already parsed
        hysteresis = config.get("hysteresis", 0.5)
        if not isinstance(hysteresis, (int, float)):
            hysteresis = 0.5

        min_temp = config.get("min_temperature", 5.0)
        max_temp = config.get("max_temperature", 35.0)

        if not entity_id or not sensor_ids or not output_id:
            _LOGGER.error(
                "Thermostat config missing required fields (id, sensor_id(s), output_id): %s",
                config,
            )
            return

        # Resolve output
        output = self._manager.outputs.get_output(output_id)
        if output is None:
            output = self._manager.outputs.get_output_group(output_id)
        if output is None:
            _LOGGER.error("Thermostat %s: output '%s' not found", entity_id, output_id)
            return

        thermostat = BoneIOThermostat(
            id=entity_id,
            name=name,
            sensor_ids=sensor_ids,
            output=output,
            message_bus=self._manager.message_bus,
            event_bus=self._manager.event_bus,
            topic_prefix=self._manager.config_helper.topic_prefix,
            mode=mode,
            target_temperature=target_temp,
            hysteresis=hysteresis,
            min_temperature=min_temp,
            max_temperature=max_temp,
            area=area,
        )

        self._thermostats.append(thermostat)

        # Register sensor → thermostat mapping for each sensor ID
        for sid in sensor_ids:
            if sid not in self._sensor_thermostat_map:
                self._sensor_thermostat_map[sid] = []
            self._sensor_thermostat_map[sid].append(thermostat)

        # Publish HA discovery
        self._publish_thermostat_discovery(thermostat)

        _LOGGER.info("Configured thermostat '%s' (sensors=%s, output=%s)",
                      entity_id, sensor_ids, output_id)

    def _configure_alarm_panel(self, config: dict[str, Any]) -> None:
        """Configure an alarm panel from YAML config.

        Args:
            config: Alarm panel configuration dictionary.
        """
        entity_id = config.get("id", "")
        name = config.get("name", entity_id)
        area = config.get("area")

        if not entity_id:
            _LOGGER.error("Alarm panel config missing 'id': %s", config)
            return

        # Parse time periods
        arming_time_s = parse_time_to_seconds(config.get("arming_time"), 30.0)
        delay_time_s = parse_time_to_seconds(config.get("delay_time"), 30.0)
        trigger_time_s = parse_time_to_seconds(config.get("trigger_time"), 300.0)

        # Parse outputs
        alarm_outputs: list[AlarmOutput] = []
        for out_cfg in config.get("outputs", []):
            out_id = out_cfg.get("id", "")
            out_type = out_cfg.get("type", "siren")
            output = self._manager.outputs.get_output(out_id)
            if output is None:
                _LOGGER.error("Alarm %s: output '%s' not found", entity_id, out_id)
                continue
            alarm_outputs.append(AlarmOutput(output=output, output_type=out_type))

        # Parse zones
        zones: list[AlarmZone] = []
        for zone_cfg in config.get("zones", []):
            zone_name = zone_cfg.get("name", "unnamed")
            arm_modes = zone_cfg.get("arm_modes", ["armed_away"])
            entry_delay = zone_cfg.get("entry_delay", False)

            # Parse inputs — support both formats:
            #   inputs: ["in_01", "in_02"]              (plain string, default NC)
            #   inputs: [{id: in_01, type: normally_closed}, {id: in_05, type: normally_open}]
            zone_inputs: list[ZoneInput] = []
            for inp_cfg in zone_cfg.get("inputs", []):
                if isinstance(inp_cfg, str):
                    zone_inputs.append(ZoneInput(input_id=inp_cfg))
                elif isinstance(inp_cfg, dict):
                    zone_inputs.append(ZoneInput(
                        input_id=inp_cfg.get("id", ""),
                        wiring=inp_cfg.get("type", "normally_closed"),
                    ))

            zones.append(AlarmZone(
                name=zone_name,
                inputs=zone_inputs,
                arm_modes=arm_modes,
                entry_delay=entry_delay,
            ))

        if not zones:
            _LOGGER.warning("Alarm %s has no zones configured", entity_id)

        # Parse PIN codes
        pin_codes: list[AlarmPinCode] = []
        for code_cfg in config.get("codes", []):
            pin_name = code_cfg.get("name", "")
            pin_code = str(code_cfg.get("code", ""))
            if pin_code:
                pin_codes.append(AlarmPinCode(name=pin_name, code_or_hash=pin_code))

        code_arm_required = config.get("code_arm_required", False)

        alarm = BoneIOAlarmPanel(
            id=entity_id,
            name=name,
            message_bus=self._manager.message_bus,
            event_bus=self._manager.event_bus,
            topic_prefix=self._manager.config_helper.topic_prefix,
            zones=zones,
            outputs=alarm_outputs,
            input_manager=self._manager.inputs,
            codes=pin_codes,
            code_arm_required=code_arm_required,
            arming_time_s=arming_time_s,
            delay_time_s=delay_time_s,
            trigger_time_s=trigger_time_s,
            area=area,
        )

        self._alarm_panels.append(alarm)

        # Register input → alarm mapping
        for zone in zones:
            for input_id in zone.input_ids:
                if input_id not in self._input_alarm_map:
                    self._input_alarm_map[input_id] = []
                self._input_alarm_map[input_id].append(alarm)

        # Sync initial input states so _check_zones_clear has live data
        self._sync_alarm_initial_input_states(zones)

        # Publish HA discovery
        self._publish_alarm_discovery(alarm)

        _LOGGER.info("Configured alarm panel '%s' (%d zones, %d outputs, %d PIN codes)",
                      entity_id, len(zones), len(alarm_outputs), len(pin_codes))

    def _sync_alarm_initial_input_states(self, zones: list) -> None:
        """Ask InputManager to re-send current state for all alarm zone inputs.

        This ensures cached _state on each input reflects live GPIO,
        so _check_zones_clear works correctly from the first arming attempt.

        Args:
            zones: List of AlarmZone instances with input IDs.
        """
        input_mgr = self._manager.inputs
        seen: set[str] = set()
        for zone in zones:
            for input_id in zone.input_ids:
                if input_id not in seen:
                    seen.add(input_id)
                    input_mgr.send_current_state_for_input(input_id)

    def _configure_gate_cover(self, config: dict[str, Any]) -> None:
        """Configure a gate cover from YAML config.

        Args:
            config: Gate cover configuration dictionary.
        """
        entity_id = config.get("id", "")
        name = config.get("name", entity_id)
        area = config.get("area")
        device_class = config.get("device_class", "gate")
        control_mode = config.get("control_mode", "cycle")

        if not entity_id:
            _LOGGER.error("Gate cover config missing 'id': %s", config)
            return

        # Parse pulse_duration (optional for open_only)
        pulse_duration_ms = parse_time_to_ms(
            config.get("pulse_duration"),
            default=500 if control_mode != "open_only" else None,
        )

        # Resolve outputs
        pulse_output = None
        open_output = None
        close_output = None
        stop_output = None

        if control_mode in ("cycle", "open_only"):
            pulse_id = config.get("pulse_output", "")
            if pulse_id:
                pulse_output = self._manager.outputs.get_output(pulse_id)
                if pulse_output is None:
                    _LOGGER.error("Gate %s: pulse_output '%s' not found", entity_id, pulse_id)
                    return
            else:
                _LOGGER.error("Gate %s: pulse_output required for mode '%s'", entity_id, control_mode)
                return
        elif control_mode == "separate":
            open_id = config.get("open_output", "")
            close_id = config.get("close_output", "")
            stop_id = config.get("stop_output", "")
            if open_id:
                open_output = self._manager.outputs.get_output(open_id)
                if open_output is None:
                    _LOGGER.error("Gate %s: open_output '%s' not found", entity_id, open_id)
                    return
            if close_id:
                close_output = self._manager.outputs.get_output(close_id)
                if close_output is None:
                    _LOGGER.error("Gate %s: close_output '%s' not found", entity_id, close_id)
                    return
            if stop_id:
                stop_output = self._manager.outputs.get_output(stop_id)
                if stop_output is None:
                    _LOGGER.warning("Gate %s: stop_output '%s' not found", entity_id, stop_id)
            if not open_id and not close_id:
                _LOGGER.error("Gate %s: open_output or close_output required for 'separate' mode", entity_id)
                return

        # Contact sensors
        closed_sensor_id = config.get("closed_sensor")
        open_sensor_id = config.get("open_sensor")

        gate = BoneIOGateCover(
            id=entity_id,
            name=name,
            message_bus=self._manager.message_bus,
            event_bus=self._manager.event_bus,
            topic_prefix=self._manager.config_helper.topic_prefix,
            control_mode=control_mode,
            device_class=device_class,
            pulse_output=pulse_output,
            open_output=open_output,
            close_output=close_output,
            stop_output=stop_output,
            pulse_duration_ms=pulse_duration_ms,
            closed_sensor_id=closed_sensor_id,
            open_sensor_id=open_sensor_id,
            area=area,
        )

        self._gate_covers.append(gate)

        # Register contact sensor → gate mapping
        for sensor_id in (closed_sensor_id, open_sensor_id):
            if sensor_id:
                if sensor_id not in self._input_gate_map:
                    self._input_gate_map[sensor_id] = []
                self._input_gate_map[sensor_id].append(gate)

        # Read current sensor states to set correct initial gate state.
        # Without this, gate defaults to CLOSED which may be wrong.
        self._sync_gate_initial_state(gate, closed_sensor_id, open_sensor_id)

        # Publish HA discovery
        self._publish_gate_cover_discovery(gate)

        _LOGGER.info(
            "Configured gate cover '%s' (mode=%s, device_class=%s)",
            entity_id, control_mode, device_class,
        )

    # -- Gate cover initial state sync ----------------------------------------

    def _sync_gate_initial_state(
        self,
        gate: BoneIOGateCover,
        closed_sensor_id: str | None,
        open_sensor_id: str | None,
    ) -> None:
        """Read current sensor GPIO state and set gate cover's initial state.

        Reads the binary sensor's ``is_active`` property directly —
        no EventBus events are fired, no MQTT messages are published.
        Gate cover's ``start()`` will publish the correct state later.

        Args:
            gate: The gate cover instance to initialize.
            closed_sensor_id: ID of the closed contact sensor (or None).
            open_sensor_id: ID of the open contact sensor (or None).
        """
        from boneio.components.input.binary_sensor import GpioInputBinarySensor

        input_mgr = self._manager.inputs

        if closed_sensor_id:
            sensor = input_mgr._inputs.get(closed_sensor_id)
            if sensor and isinstance(sensor, GpioInputBinarySensor):
                is_closed = sensor.is_active
                _LOGGER.debug(
                    "Gate %s: initial closed_sensor %s is_active=%s",
                    gate.id, closed_sensor_id, is_closed,
                )
                if is_closed:
                    gate._state = CLOSED
                    gate._current_operation = IDLE
                    gate._cycle_next = CYCLE_OPEN
                elif not gate._has_open_sensor:
                    gate._state = OPEN
                    gate._current_operation = IDLE

        if open_sensor_id:
            sensor = input_mgr._inputs.get(open_sensor_id)
            if sensor and isinstance(sensor, GpioInputBinarySensor):
                is_open = sensor.is_active
                _LOGGER.debug(
                    "Gate %s: initial open_sensor %s is_active=%s",
                    gate.id, open_sensor_id, is_open,
                )
                if is_open:
                    gate._state = OPEN
                    gate._current_operation = IDLE
                    gate._cycle_next = CYCLE_CLOSE

    # -- HA Discovery --------------------------------------------------------

    def _publish_thermostat_discovery(self, thermostat: BoneIOThermostat) -> None:
        """Publish HA autodiscovery for a thermostat.

        Args:
            thermostat: The thermostat instance.
        """
        from boneio.integration.homeassistant import ha_climate_availability_message

        payload = ha_climate_availability_message(
            id=thermostat.id,
            name=thermostat.name,
            config_helper=self._manager._config_helper,
            modes=["off", "heat"],
            min_temp=thermostat._min_temperature,
            max_temp=thermostat._max_temperature,
            area=thermostat.area,
        )
        self._manager.publish_ha_discovery(
            id=thermostat.id, ha_type=CLIMATE, payload=payload
        )

    def _publish_alarm_discovery(self, alarm: BoneIOAlarmPanel) -> None:
        """Publish HA autodiscovery for an alarm panel.

        Args:
            alarm: The alarm panel instance.
        """
        from boneio.integration.homeassistant import ha_alarm_panel_availability_message

        has_codes = bool(alarm.codes)
        payload = ha_alarm_panel_availability_message(
            id=alarm.id,
            name=alarm.name,
            config_helper=self._manager._config_helper,
            code="REMOTE_CODE" if has_codes else "",
            code_arm_required=alarm.code_arm_required if has_codes else False,
            area=alarm.area,
        )
        self._manager.publish_ha_discovery(
            id=alarm.id, ha_type=ALARM_CONTROL_PANEL, payload=payload
        )

    def _publish_gate_cover_discovery(self, gate: BoneIOGateCover) -> None:
        """Publish HA autodiscovery for a gate cover.

        Args:
            gate: The gate cover instance.
        """
        from boneio.integration.homeassistant import ha_gate_cover_availability_message

        payload = ha_gate_cover_availability_message(
            id=gate.id,
            name=gate.name,
            device_class=gate.device_class,
            config_helper=self._manager._config_helper,
            area=gate.area,
        )
        self._manager.publish_ha_discovery(
            id=gate.id, ha_type=COVER, payload=payload
        )

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

        thermostats = self._sensor_thermostat_map.get(sensor_id, [])
        for thermostat in thermostats:
            thermostat.update_sensor_temperature(sensor_id, temperature)

    def on_input_event(self, input_id: str, event_type: str) -> None:
        """Route input event to matching alarm panels and gate covers.

        Called by InputManager when an input fires.

        Args:
            input_id: The input entity ID.
            event_type: Event type (pressed, single, etc.).
        """
        alarms = self._input_alarm_map.get(input_id, [])
        for alarm in alarms:
            alarm.on_input_event(input_id, event_type)

        # Route to gate covers (contact sensors)
        gates = self._input_gate_map.get(input_id, [])
        if gates:
            # Determine sensor state: "pressed" = closed circuit (True)
            is_closed = event_type in ("pressed", "single", "double", "long")
            for gate in gates:
                gate.on_sensor_event(input_id, is_closed)

    # -- HA autodiscovery resend ---------------------------------------------

    async def send_ha_autodiscovery(self) -> None:
        """Resend HA autodiscovery for all template entities."""
        for thermostat in self._thermostats:
            self._publish_thermostat_discovery(thermostat)
        for alarm in self._alarm_panels:
            self._publish_alarm_discovery(alarm)
        for gate in self._gate_covers:
            self._publish_gate_cover_discovery(gate)

    # -- MQTT subscriptions --------------------------------------------------

    async def start(self) -> None:
        """Start all template entities (subscribe to MQTT commands, register EventBus listeners)."""
        self._register_sensor_listeners()
        _LOGGER.info(
            "TemplateManager registered %d sensor listeners",
            len(self._sensor_thermostat_map),
        )

        for thermostat in self._thermostats:
            await thermostat.start()
        for alarm in self._alarm_panels:
            await alarm.start()
        for gate in self._gate_covers:
            await gate.start()
        _LOGGER.info("TemplateManager started all entities")

    async def stop(self) -> None:
        """Stop all template entities and remove EventBus listeners."""
        event_bus = self._manager.event_bus
        for sensor_id in self._sensor_thermostat_map:
            event_bus.remove_event_listener(
                event_type="sensor",
                entity_id=sensor_id,
                listener_id=f"template_mgr_{sensor_id}",
            )
        for thermostat in self._thermostats:
            await thermostat.stop()
        for alarm in self._alarm_panels:
            await alarm.stop()
        for gate in self._gate_covers:
            await gate.stop()

    # -- Hot reload ----------------------------------------------------------

    async def reload_templates(self) -> None:
        """Reload template configuration from file.

        Handles adding, removing, and updating thermostats and alarm panels
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

        current_thermostat_ids = {t.id for t in self._thermostats}
        current_alarm_ids = {a.id for a in self._alarm_panels}
        current_gate_ids = {g.id for g in self._gate_covers}

        # --- Remove deleted thermostats ---
        for tid in current_thermostat_ids - set(new_thermostats.keys()):
            await self._remove_thermostat(tid)

        # --- Remove deleted alarm panels ---
        for aid in current_alarm_ids - set(new_alarms.keys()):
            await self._remove_alarm_panel(aid)

        # --- Remove deleted gate covers ---
        for gid in current_gate_ids - set(new_gates.keys()):
            await self._remove_gate_cover(gid)

        # --- Add new / update existing thermostats ---
        for eid, entry in new_thermostats.items():
            if eid in current_thermostat_ids:
                # Update existing — remove and re-add (simplest correct approach)
                await self._remove_thermostat(eid)
            try:
                self._configure_thermostat(entry)
            except Exception as err:
                _LOGGER.error("Failed to configure thermostat '%s': %s", eid, err)
                continue
            # Start the newly added thermostat
            thermostat = self.get_thermostat(eid)
            if thermostat:
                await thermostat.start()

        # --- Add new / update existing alarm panels ---
        for eid, entry in new_alarms.items():
            if eid in current_alarm_ids:
                await self._remove_alarm_panel(eid)
            try:
                self._configure_alarm_panel(entry)
            except Exception as err:
                _LOGGER.error("Failed to configure alarm panel '%s': %s", eid, err)
                continue
            alarm = self.get_alarm_panel(eid)
            if alarm:
                await alarm.start()

        # --- Add new / update existing gate covers ---
        for eid, entry in new_gates.items():
            if eid in current_gate_ids:
                await self._remove_gate_cover(eid)
            try:
                self._configure_gate_cover(entry)
            except Exception as err:
                _LOGGER.error("Failed to configure gate cover '%s': %s", eid, err)
                continue
            gate = self.get_gate_cover(eid)
            if gate:
                await gate.start()

        # Re-register all sensor EventBus listeners (clean slate)
        self._register_sensor_listeners()

        _LOGGER.info(
            "Template reload complete: %d thermostats, %d alarm panels, %d gate covers",
            len(self._thermostats), len(self._alarm_panels), len(self._gate_covers),
        )

    async def _remove_thermostat(self, entity_id: str) -> None:
        """Remove a thermostat: stop MQTT, remove EventBus listeners, remove HA discovery.

        Args:
            entity_id: Thermostat entity ID to remove.
        """
        thermostat = self.get_thermostat(entity_id)
        if not thermostat:
            return

        _LOGGER.info("Removing thermostat '%s'", entity_id)
        await thermostat.stop()

        # Remove sensor → thermostat mappings
        for sid in thermostat.sensor_ids:
            if sid in self._sensor_thermostat_map:
                self._sensor_thermostat_map[sid] = [
                    t for t in self._sensor_thermostat_map[sid] if t.id != entity_id
                ]
                if not self._sensor_thermostat_map[sid]:
                    del self._sensor_thermostat_map[sid]

        # Remove HA discovery
        self._remove_ha_discovery(entity_id)

        self._thermostats = [t for t in self._thermostats if t.id != entity_id]

    async def _remove_alarm_panel(self, entity_id: str) -> None:
        """Remove an alarm panel: stop MQTT, remove input mappings, remove HA discovery.

        Args:
            entity_id: Alarm panel entity ID to remove.
        """
        alarm = self.get_alarm_panel(entity_id)
        if not alarm:
            return

        _LOGGER.info("Removing alarm panel '%s'", entity_id)
        await alarm.stop()

        # Remove input → alarm mappings
        for input_id in list(self._input_alarm_map.keys()):
            self._input_alarm_map[input_id] = [
                a for a in self._input_alarm_map[input_id] if a.id != entity_id
            ]
            if not self._input_alarm_map[input_id]:
                del self._input_alarm_map[input_id]

        # Remove HA discovery
        self._remove_ha_discovery(entity_id)

        self._alarm_panels = [a for a in self._alarm_panels if a.id != entity_id]

    async def _remove_gate_cover(self, entity_id: str) -> None:
        """Remove a gate cover: stop MQTT, remove sensor mappings, remove HA discovery.

        Args:
            entity_id: Gate cover entity ID to remove.
        """
        gate = self.get_gate_cover(entity_id)
        if not gate:
            return

        _LOGGER.info("Removing gate cover '%s'", entity_id)
        await gate.stop()

        # Remove sensor → gate mappings
        for input_id in list(self._input_gate_map.keys()):
            self._input_gate_map[input_id] = [
                g for g in self._input_gate_map[input_id] if g.id != entity_id
            ]
            if not self._input_gate_map[input_id]:
                del self._input_gate_map[input_id]

        # Remove HA discovery
        self._remove_ha_discovery(entity_id)

        self._gate_covers = [g for g in self._gate_covers if g.id != entity_id]

    def _remove_ha_discovery(self, entity_id: str) -> None:
        """Remove HA autodiscovery entries for an entity.

        Sends empty retained payload to remove the entity from Home Assistant.

        Args:
            entity_id: Entity ID to remove.
        """
        matching_topics = self._manager._config_helper.get_autodiscovery_topics_for_id(entity_id)
        for ha_type, topic in matching_topics:
            _LOGGER.debug("Removing HA Discovery for %s: %s", entity_id, topic)
            self._manager.send_message(topic=topic, payload=None, retain=True)
            self._manager._config_helper.remove_autodiscovery_msg(ha_type, topic)

    def _register_sensor_listeners(self) -> None:
        """Register (or re-register) EventBus listeners for all sensor → thermostat mappings."""
        event_bus = self._manager.event_bus

        # Remove all existing template sensor listeners
        for sensor_id in list(self._sensor_thermostat_map.keys()):
            event_bus.remove_event_listener(
                event_type="sensor",
                entity_id=sensor_id,
                listener_id=f"template_mgr_{sensor_id}",
            )

        # Re-register for current mappings
        for sensor_id in self._sensor_thermostat_map:
            event_bus.add_event_listener(
                event_type="sensor",
                entity_id=sensor_id,
                listener_id=f"template_mgr_{sensor_id}",
                target=self._on_sensor_event,
            )

    # -- Accessors -----------------------------------------------------------

    @property
    def thermostats(self) -> list[BoneIOThermostat]:
        """Get all configured thermostats."""
        return self._thermostats

    @property
    def alarm_panels(self) -> list[BoneIOAlarmPanel]:
        """Get all configured alarm panels."""
        return self._alarm_panels

    def get_thermostat(self, entity_id: str) -> BoneIOThermostat | None:
        """Get thermostat by ID.

        Args:
            entity_id: Thermostat entity ID.

        Returns:
            BoneIOThermostat or None if not found.
        """
        for t in self._thermostats:
            if t.id == entity_id:
                return t
        return None

    def get_alarm_panel(self, entity_id: str) -> BoneIOAlarmPanel | None:
        """Get alarm panel by ID.

        Args:
            entity_id: Alarm panel entity ID.

        Returns:
            BoneIOAlarmPanel or None if not found.
        """
        for a in self._alarm_panels:
            if a.id == entity_id:
                return a
        return None

    @property
    def gate_covers(self) -> list[BoneIOGateCover]:
        """Get all configured gate covers."""
        return self._gate_covers

    def get_gate_cover(self, entity_id: str) -> BoneIOGateCover | None:
        """Get gate cover by ID.

        Args:
            entity_id: Gate cover entity ID.

        Returns:
            BoneIOGateCover or None if not found.
        """
        for g in self._gate_covers:
            if g.id == entity_id:
                return g
        return None
