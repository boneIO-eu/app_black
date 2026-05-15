"""Alarm panel sub-manager for TemplateManager."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from boneio.components.template.alarm_panel import (
    AlarmOutput,
    AlarmPinCode,
    AlarmZone,
    BoneIOAlarmPanel,
    ZoneInput,
)
from boneio.const import ALARM_CONTROL_PANEL
from boneio.core.utils.timeperiod import parse_time_to_seconds

if TYPE_CHECKING:
    from boneio.core.manager.manager import Manager

_LOGGER = logging.getLogger(__name__)


class AlarmManager:
    """Manages alarm panel template entities.

    Args:
        manager: Reference to the main Manager.
    """

    def __init__(self, manager: Manager) -> None:
        self._manager = manager
        self._items: list[BoneIOAlarmPanel] = []
        self._input_map: dict[str, list[BoneIOAlarmPanel]] = {}

    @property
    def items(self) -> list[BoneIOAlarmPanel]:
        """All configured alarm panels."""
        return self._items

    @property
    def input_map(self) -> dict[str, list[BoneIOAlarmPanel]]:
        """Input ID → alarm panel mapping (used by TemplateManager for event routing)."""
        return self._input_map

    def get(self, entity_id: str) -> BoneIOAlarmPanel | None:
        """Get alarm panel by ID.

        Args:
            entity_id: Alarm panel entity ID.

        Returns:
            BoneIOAlarmPanel or None if not found.
        """
        for a in self._items:
            if a.id == entity_id:
                return a
        return None

    # -- Configuration -------------------------------------------------------

    def configure(self, config: dict[str, Any]) -> None:
        """Configure an alarm panel from YAML config.

        Args:
            config: Alarm panel configuration dictionary.
        """
        entity_id: str = config.get("id", "")
        name: str = config.get("name") or entity_id
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
            #   inputs: [{id: in_01, type: normally_closed}, ...]
            #   inputs: [{id: remote_sensor, source: remote, on_disconnect: ignore}, ...]
            zone_inputs: list[ZoneInput] = []
            for inp_cfg in zone_cfg.get("inputs", []):
                if isinstance(inp_cfg, str):
                    zone_inputs.append(ZoneInput(input_id=inp_cfg))
                elif isinstance(inp_cfg, dict):
                    zone_inputs.append(ZoneInput(
                        input_id=inp_cfg.get("id", ""),
                        wiring=inp_cfg.get("type", "normally_closed"),
                        source=inp_cfg.get("source", "local"),
                        on_disconnect=inp_cfg.get("on_disconnect", "ignore"),
                    ))

            zones.append(AlarmZone(
                name=zone_name,
                inputs=zone_inputs,
                arm_modes=arm_modes,
                entry_delay=entry_delay,
            ))

        if not zones:
            _LOGGER.warning("Alarm %s has no zones configured", entity_id)

        # Parse PIN codes — auto-migrate plain-text to SHA-256 hashes
        pin_codes: list[AlarmPinCode] = []
        needs_hash_migration = False
        for code_cfg in config.get("codes", []):
            pin_name = code_cfg.get("name", "")
            pin_code = str(code_cfg.get("code", ""))
            if pin_code:
                if not AlarmPinCode._is_sha256(pin_code):
                    needs_hash_migration = True
                pin_codes.append(AlarmPinCode(name=pin_name, code_or_hash=pin_code))

        if needs_hash_migration:
            self._migrate_codes_to_hashes(pin_codes)

        code_arm_required = config.get("code_arm_required", False)
        allow_frontend_control = config.get("allow_frontend_control", False)

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
            allow_frontend_control=allow_frontend_control,
            arming_time_s=arming_time_s,
            delay_time_s=delay_time_s,
            trigger_time_s=trigger_time_s,
            area=area,
            state_manager=self._manager.state_manager,
        )

        self._items.append(alarm)

        # Register input → alarm mapping
        for zone in zones:
            for input_id in zone.input_ids:
                if input_id not in self._input_map:
                    self._input_map[input_id] = []
                self._input_map[input_id].append(alarm)

        # Sync initial input states so _check_zones_clear has live data
        self._sync_initial_input_states(zones)

        # Publish HA discovery
        self._publish_discovery(alarm)

        _LOGGER.info(
            "Configured alarm panel '%s' (%d zones, %d outputs, %d PIN codes)",
            entity_id, len(zones), len(alarm_outputs), len(pin_codes),
        )

    # -- Initial state sync --------------------------------------------------

    def _sync_initial_input_states(self, zones: list) -> None:
        """Ask InputManager to re-send current state for local alarm zone inputs.

        Remote inputs are skipped — they have no GPIO and receive state
        via their protocol (ESPHome API, MQTT, etc.).

        Args:
            zones: List of AlarmZone instances with input IDs.
        """
        input_mgr = self._manager.inputs
        seen: set[str] = set()
        for zone in zones:
            for zone_input in zone.inputs:
                if zone_input.is_remote:
                    continue
                if zone_input.input_id not in seen:
                    seen.add(zone_input.input_id)
                    input_mgr.send_current_state_for_input(zone_input.input_id)

    # -- Removal -------------------------------------------------------------

    async def remove(self, entity_id: str) -> None:
        """Remove an alarm panel: stop MQTT, remove input mappings, remove HA discovery.

        Args:
            entity_id: Alarm panel entity ID to remove.
        """
        alarm = self.get(entity_id)
        if not alarm:
            return

        _LOGGER.info("Removing alarm panel '%s'", entity_id)
        await alarm.stop()

        # Remove input → alarm mappings
        for input_id in list(self._input_map.keys()):
            self._input_map[input_id] = [
                a for a in self._input_map[input_id] if a.id != entity_id
            ]
            if not self._input_map[input_id]:
                del self._input_map[input_id]

        self._remove_ha_discovery(entity_id)
        self._items = [a for a in self._items if a.id != entity_id]

    # -- HA Discovery --------------------------------------------------------

    def _publish_discovery(self, alarm: BoneIOAlarmPanel) -> None:
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

    def publish_all_discovery(self) -> None:
        """Resend HA autodiscovery for all alarm panels."""
        for alarm in self._items:
            self._publish_discovery(alarm)

    def _remove_ha_discovery(self, entity_id: str) -> None:
        """Remove HA autodiscovery entries for an alarm panel.

        Args:
            entity_id: Entity ID to remove.
        """
        matching_topics = self._manager._config_helper.get_autodiscovery_topics_for_id(entity_id)
        for ha_type, topic in matching_topics:
            _LOGGER.debug("Removing HA Discovery for %s: %s", entity_id, topic)
            self._manager.send_message(topic=topic, payload=None, retain=True)
            self._manager._config_helper.remove_autodiscovery_msg(ha_type, topic)

    def _migrate_codes_to_hashes(self, pin_codes: list[AlarmPinCode]) -> None:
        """Replace plain-text PIN codes with SHA-256 hashes in the YAML config.

        Called automatically on startup when plain-text codes are detected.
        Updates the ``template`` section so that subsequent loads already
        contain hashed values.

        Args:
            pin_codes: List of AlarmPinCode objects (already hashed in memory).
        """
        try:
            config_helper = self._manager._config_helper
            config = config_helper.get_config()
            template_list: list[dict] = config.get("template", [])
            changed = False

            for entry in template_list:
                if entry.get("platform") != "alarm_control_panel":
                    continue
                for code_cfg in entry.get("codes", []):
                    raw = str(code_cfg.get("code", ""))
                    if raw and not AlarmPinCode._is_sha256(raw):
                        code_cfg["code"] = AlarmPinCode.hash_code(raw)
                        changed = True

            if changed:
                from boneio.core.config.yaml_util import update_config_section
                config_file = config_helper._config_file_path
                if config_file is None:
                    _LOGGER.warning("Cannot migrate PIN codes: config_file_path not set")
                    return
                update_config_section(config_file, "template", template_list)
                _LOGGER.info(
                    "Migrated plain-text alarm PIN codes to SHA-256 hashes in YAML"
                )
        except Exception as err:
            _LOGGER.warning(
                "Failed to migrate alarm PIN codes to hashes: %s", err
            )
