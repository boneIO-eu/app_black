"""Gate cover sub-manager for TemplateManager."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from boneio.const import COVER
from boneio.core.utils.timeperiod import parse_time_to_ms
from boneio.components.template.gate_cover import BoneIOGateCover

if TYPE_CHECKING:
    from boneio.core.manager.manager import Manager

_LOGGER = logging.getLogger(__name__)


class GateCoverManager:
    """Manages gate cover template entities.

    Args:
        manager: Reference to the main Manager.
    """

    def __init__(self, manager: "Manager") -> None:
        self._manager = manager
        self._items: list[BoneIOGateCover] = []
        self._input_map: dict[str, list[BoneIOGateCover]] = {}

    @property
    def items(self) -> list[BoneIOGateCover]:
        """All configured gate covers."""
        return self._items

    @property
    def input_map(self) -> dict[str, list[BoneIOGateCover]]:
        """Input ID → gate cover mapping (used by TemplateManager for event routing)."""
        return self._input_map

    def get(self, entity_id: str) -> BoneIOGateCover | None:
        """Get gate cover by ID.

        Args:
            entity_id: Gate cover entity ID.

        Returns:
            BoneIOGateCover or None if not found.
        """
        for g in self._items:
            if g.id == entity_id:
                return g
        return None

    # -- Configuration -------------------------------------------------------

    def configure(self, config: dict[str, Any]) -> None:
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

        self._items.append(gate)

        # Register contact sensor → gate mapping
        for sensor_id in (closed_sensor_id, open_sensor_id):
            if sensor_id:
                if sensor_id not in self._input_map:
                    self._input_map[sensor_id] = []
                self._input_map[sensor_id].append(gate)

        # Read current sensor states to set correct initial gate state.
        # Without this, gate defaults to CLOSED which may be wrong.
        self._sync_initial_state(closed_sensor_id, open_sensor_id)

        # Publish HA discovery
        self._publish_discovery(gate)

        _LOGGER.info(
            "Configured gate cover '%s' (mode=%s, device_class=%s)",
            entity_id, control_mode, device_class,
        )

    # -- Initial state sync --------------------------------------------------

    def _sync_initial_state(
        self,
        closed_sensor_id: str | None,
        open_sensor_id: str | None,
    ) -> None:
        """Sync initial gate state by asking InputManager to re-send sensor states.

        Delegates to InputManager.send_current_state_for_input() which reads
        live GPIO and fires an EventBus event. The gate cover's event listener
        picks it up automatically — no direct GPIO access needed here.

        Args:
            closed_sensor_id: ID of the closed contact sensor (or None).
            open_sensor_id: ID of the open contact sensor (or None).
        """
        input_mgr = self._manager.inputs
        for sensor_id in (closed_sensor_id, open_sensor_id):
            if sensor_id:
                input_mgr.send_current_state_for_input(sensor_id)

    # -- Removal -------------------------------------------------------------

    async def remove(self, entity_id: str) -> None:
        """Remove a gate cover: stop MQTT, remove sensor mappings, remove HA discovery.

        Args:
            entity_id: Gate cover entity ID to remove.
        """
        gate = self.get(entity_id)
        if not gate:
            return

        _LOGGER.info("Removing gate cover '%s'", entity_id)
        await gate.stop()

        # Remove sensor → gate mappings
        for input_id in list(self._input_map.keys()):
            self._input_map[input_id] = [
                g for g in self._input_map[input_id] if g.id != entity_id
            ]
            if not self._input_map[input_id]:
                del self._input_map[input_id]

        self._remove_ha_discovery(entity_id)
        self._items = [g for g in self._items if g.id != entity_id]

    # -- HA Discovery --------------------------------------------------------

    def _publish_discovery(self, gate: BoneIOGateCover) -> None:
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

    def publish_all_discovery(self) -> None:
        """Resend HA autodiscovery for all gate covers."""
        for gate in self._items:
            self._publish_discovery(gate)

    def _remove_ha_discovery(self, entity_id: str) -> None:
        """Remove HA autodiscovery entries for a gate cover.

        Args:
            entity_id: Entity ID to remove.
        """
        matching_topics = self._manager._config_helper.get_autodiscovery_topics_for_id(entity_id)
        for ha_type, topic in matching_topics:
            _LOGGER.debug("Removing HA Discovery for %s: %s", entity_id, topic)
            self._manager.send_message(topic=topic, payload=None, retain=True)
            self._manager._config_helper.remove_autodiscovery_msg(ha_type, topic)
