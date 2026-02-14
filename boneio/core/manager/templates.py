"""Template Manager — orchestrates composite virtual entities.

Parses the ``template:`` config section and instantiates platform-specific
components (thermostat, alarm_control_panel).  Wires sensor events to
thermostats and input events to alarm panels.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from boneio.const import ALARM_CONTROL_PANEL, CLIMATE, SENSOR
from boneio.components.template.thermostat import BoneIOThermostat
from boneio.components.template.alarm_panel import (
    AlarmOutput,
    AlarmPinCode,
    AlarmZone,
    BoneIOAlarmPanel,
    ZoneInput,
)

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
        manager: "Manager",
        template_config: list[dict[str, Any]],
    ) -> None:
        self._manager = manager
        self._thermostats: list[BoneIOThermostat] = []
        self._alarm_panels: list[BoneIOAlarmPanel] = []

        # Map sensor_id → list of thermostats that use it
        self._sensor_thermostat_map: dict[str, list[BoneIOThermostat]] = {}
        # Map input_id → list of alarm panels that monitor it
        self._input_alarm_map: dict[str, list[BoneIOAlarmPanel]] = {}

        for entry in template_config:
            platform = entry.get("platform", "")
            try:
                if platform == "thermostat":
                    self._configure_thermostat(entry)
                elif platform == "alarm_control_panel":
                    self._configure_alarm_panel(entry)
                else:
                    _LOGGER.warning("Unknown template platform: %s", platform)
            except Exception as err:
                _LOGGER.error(
                    "Failed to configure template '%s' (%s): %s",
                    entry.get("id", "?"), platform, err,
                )

        _LOGGER.info(
            "TemplateManager initialized: %d thermostats, %d alarm panels",
            len(self._thermostats), len(self._alarm_panels),
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
        arming_time_s = self._parse_time_to_seconds(config.get("arming_time"), 30.0)
        delay_time_s = self._parse_time_to_seconds(config.get("delay_time"), 30.0)
        trigger_time_s = self._parse_time_to_seconds(config.get("trigger_time"), 300.0)

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
                pin_codes.append(AlarmPinCode(name=pin_name, code=pin_code))

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

        # Publish HA discovery
        self._publish_alarm_discovery(alarm)

        _LOGGER.info("Configured alarm panel '%s' (%d zones, %d outputs, %d PIN codes)",
                      entity_id, len(zones), len(alarm_outputs), len(pin_codes))

    # -- Time parsing --------------------------------------------------------

    @staticmethod
    def _parse_time_to_seconds(value: Any, default: float) -> float:
        """Parse a time value to seconds.

        Supports TimePeriod objects and raw numeric values.

        Args:
            value: TimePeriod, int, float, or None.
            default: Default value in seconds.

        Returns:
            Time in seconds as float.
        """
        if value is None:
            return default
        # TimePeriod object (from YAML coerce)
        if hasattr(value, "total_in_seconds"):
            return value.total_in_seconds
        # Raw numeric
        try:
            return float(value)
        except (ValueError, TypeError):
            _LOGGER.warning("Invalid time value: %s, using default %.0fs", value, default)
            return default

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
        """Route input event to matching alarm panels.

        Called by InputManager when an input fires.

        Args:
            input_id: The input entity ID.
            event_type: Event type (pressed, single, etc.).
        """
        alarms = self._input_alarm_map.get(input_id, [])
        for alarm in alarms:
            alarm.on_input_event(input_id, event_type)

    # -- HA autodiscovery resend ---------------------------------------------

    async def send_ha_autodiscovery(self) -> None:
        """Resend HA autodiscovery for all template entities."""
        for thermostat in self._thermostats:
            self._publish_thermostat_discovery(thermostat)
        for alarm in self._alarm_panels:
            self._publish_alarm_discovery(alarm)

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
        for entry in new_template_config:
            platform = entry.get("platform", "")
            eid = entry.get("id", "")
            if not eid:
                continue
            if platform == "thermostat":
                new_thermostats[eid] = entry
            elif platform == "alarm_control_panel":
                new_alarms[eid] = entry

        current_thermostat_ids = {t.id for t in self._thermostats}
        current_alarm_ids = {a.id for a in self._alarm_panels}

        # --- Remove deleted thermostats ---
        for tid in current_thermostat_ids - set(new_thermostats.keys()):
            await self._remove_thermostat(tid)

        # --- Remove deleted alarm panels ---
        for aid in current_alarm_ids - set(new_alarms.keys()):
            await self._remove_alarm_panel(aid)

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

        # Re-register all sensor EventBus listeners (clean slate)
        self._register_sensor_listeners()

        _LOGGER.info(
            "Template reload complete: %d thermostats, %d alarm panels",
            len(self._thermostats), len(self._alarm_panels),
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
