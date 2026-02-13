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
    AlarmZone,
    BoneIOAlarmPanel,
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
        sensor_id = config.get("sensor_id", "")
        output_id = config.get("output_id", "")
        mode = config.get("mode", "heat")
        target_temp = config.get("target_temperature", 21.0)
        area = config.get("area")

        # Parse hysteresis — could be float or already parsed
        hysteresis = config.get("hysteresis", 0.5)
        if not isinstance(hysteresis, (int, float)):
            hysteresis = 0.5

        min_temp = config.get("min_temperature", 5.0)
        max_temp = config.get("max_temperature", 35.0)

        if not entity_id or not sensor_id or not output_id:
            _LOGGER.error(
                "Thermostat config missing required fields (id, sensor_id, output_id): %s",
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
            sensor_id=sensor_id,
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

        # Register sensor → thermostat mapping
        if sensor_id not in self._sensor_thermostat_map:
            self._sensor_thermostat_map[sensor_id] = []
        self._sensor_thermostat_map[sensor_id].append(thermostat)

        # Publish HA discovery
        self._publish_thermostat_discovery(thermostat)

        _LOGGER.info("Configured thermostat '%s' (sensor=%s, output=%s)",
                      entity_id, sensor_id, output_id)

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
            input_ids = zone_cfg.get("inputs", [])
            arm_modes = zone_cfg.get("arm_modes", ["armed_away"])
            entry_delay = zone_cfg.get("entry_delay", False)
            zones.append(AlarmZone(
                name=zone_name,
                input_ids=input_ids,
                arm_modes=arm_modes,
                entry_delay=entry_delay,
            ))

        if not zones:
            _LOGGER.warning("Alarm %s has no zones configured", entity_id)

        alarm = BoneIOAlarmPanel(
            id=entity_id,
            name=name,
            message_bus=self._manager.message_bus,
            event_bus=self._manager.event_bus,
            topic_prefix=self._manager.config_helper.topic_prefix,
            zones=zones,
            outputs=alarm_outputs,
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

        _LOGGER.info("Configured alarm panel '%s' (%d zones, %d outputs)",
                      entity_id, len(zones), len(alarm_outputs))

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

        payload = ha_alarm_panel_availability_message(
            id=alarm.id,
            name=alarm.name,
            config_helper=self._manager._config_helper,
            code="REMOTE_CODE",
            code_arm_required=False,
            area=alarm.area,
        )
        self._manager.publish_ha_discovery(
            id=alarm.id, ha_type=ALARM_CONTROL_PANEL, payload=payload
        )

    # -- Event routing -------------------------------------------------------

    def on_sensor_update(self, sensor_id: str, temperature: float) -> None:
        """Route sensor temperature update to matching thermostats.

        Called by SensorManager or ModbusManager when a sensor value changes.

        Args:
            sensor_id: The sensor entity ID.
            temperature: Current temperature reading.
        """
        thermostats = self._sensor_thermostat_map.get(sensor_id, [])
        for thermostat in thermostats:
            thermostat.update_temperature(temperature)

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
        """Start all template entities (subscribe to MQTT commands)."""
        for thermostat in self._thermostats:
            await thermostat.start()
        for alarm in self._alarm_panels:
            await alarm.start()
        _LOGGER.info("TemplateManager started all entities")

    async def stop(self) -> None:
        """Stop all template entities."""
        for thermostat in self._thermostats:
            await thermostat.stop()
        for alarm in self._alarm_panels:
            await alarm.stop()

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
