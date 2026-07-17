"""Irrigation manager - handles irrigation controllers and MQTT integration."""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING, Any

from boneio.components.irrigation import IrrigationController, IrrigationZone, WaterSource
from boneio.const import NEXT_VALVE, ON, PAUSE, RESUME
from boneio.core.utils.timeperiod import parse_time_to_seconds
from boneio.integration.homeassistant import (
    _ha_irrigation_device,
    ha_irrigation_button_message,
    ha_irrigation_event_message,
    ha_irrigation_main_switch_message,
    ha_irrigation_number_message,
    ha_irrigation_select_message,
    ha_irrigation_switch_message,
    ha_irrigation_timestamp_sensor_message,
    ha_irrigation_valve_message,
)

if TYPE_CHECKING:
    from boneio.components.output.basic import BasicOutput
    from boneio.core.manager import Manager

_LOGGER = logging.getLogger(__name__)


class IrrigationManager:
    """Manages irrigation controllers and their HA integration."""

    def __init__(self, manager: Manager, irrigation_config: list[dict[str, Any]]) -> None:
        self._manager = manager
        self._controllers: dict[str, IrrigationController] = {}
        self._subscribed_topics: set[str] = set()

        self._initialize(irrigation_config)

        _LOGGER.info("IrrigationManager initialized with %d controllers", len(self._controllers))

    def _initialize(self, irrigation_config: list[dict[str, Any]]) -> None:
        for cfg in irrigation_config:
            ctrl = self._build_controller(cfg)
            if ctrl is None:
                continue
            self._controllers[ctrl.id] = ctrl

    def _build_controller(self, cfg: dict[str, Any]) -> IrrigationController | None:
        ctrl_id = str(cfg.get("id", "")).strip()
        if not ctrl_id:
            _LOGGER.error("Irrigation controller missing required field 'id': %s", cfg)
            return None

        name = str(cfg.get("name", ctrl_id)).strip() or ctrl_id

        zones: list[IrrigationZone] = []
        for zone_cfg in cfg.get("zones", []):
            zone = self._build_zone(zone_cfg)
            if zone is not None:
                zones.append(zone)

        if not zones:
            _LOGGER.warning("Irrigation controller '%s' has no valid zones", ctrl_id)
            return None

        # Build water sources
        water_sources: list[WaterSource] = []
        for ws_cfg in cfg.get("water_sources", []):
            ws = self._build_water_source(ws_cfg)
            if ws is not None:
                water_sources.append(ws)

        schedule = cfg.get("schedule", [])
        if not isinstance(schedule, list):
            schedule = []

        return IrrigationController(
            id=ctrl_id,
            name=name,
            topic_prefix=self._manager.config_helper.topic_prefix,
            message_bus=self._manager.message_bus,
            event_bus=self._manager.event_bus,
            state_manager=self._manager.state_manager,
            zones=zones,
            schedule=schedule,
            water_sources=water_sources,
            valve_open_delay_s=int(parse_time_to_seconds(cfg.get("valve_open_delay"), 0)),
            valve_overlap_s=int(parse_time_to_seconds(cfg.get("valve_overlap"), 0)),
            standby=bool(cfg.get("standby", False)),
            multiplier=float(cfg.get("multiplier", 1.0)),
            repeat=int(cfg.get("repeat", 0)),
            auto_advance=bool(cfg.get("auto_advance", True)),
            reverse=bool(cfg.get("reverse", False)),
            pause_timeout_s=int(parse_time_to_seconds(cfg.get("pause_timeout"), 1800)),
            area_id=cfg.get("area"),
        )

    def _build_zone(self, zone_cfg: dict[str, Any]) -> IrrigationZone | None:
        zone_id = str(zone_cfg.get("id", "")).strip()
        valve_id = str(zone_cfg.get("valve_id", "")).strip()

        if not zone_id or not valve_id:
            _LOGGER.error("Irrigation zone missing required fields 'id' or 'valve_id': %s", zone_cfg)
            return None

        valve: BasicOutput | None = self._manager.outputs.get_output(valve_id)
        if valve is None:
            _LOGGER.error("Irrigation zone '%s': valve '%s' not found", zone_id, valve_id)
            return None

        run_duration = int(parse_time_to_seconds(zone_cfg.get("run_duration"), 60))
        run_duration = max(60, run_duration)

        run_every_n = int(zone_cfg.get("run_every_n", 1))
        run_every_n = max(1, run_every_n)

        return IrrigationZone(
            id=zone_id,
            name=str(zone_cfg.get("name", zone_id)),
            valve=valve,
            run_duration=run_duration,
            enabled=bool(zone_cfg.get("enabled", True)),
            run_every_n=run_every_n,
        )

    def _build_water_source(self, ws_cfg: dict[str, Any]) -> WaterSource | None:
        """Build a WaterSource from config.

        Args:
            ws_cfg: Water source configuration dict.

        Returns:
            WaterSource instance or None if config is invalid.
        """
        ws_id = str(ws_cfg.get("id", "")).strip()
        if not ws_id:
            _LOGGER.error("Water source missing required field 'id': %s", ws_cfg)
            return None

        name = str(ws_cfg.get("name", ws_id)).strip() or ws_id

        output_ids = ws_cfg.get("outputs", [])
        if not isinstance(output_ids, list) or not output_ids:
            _LOGGER.error("Water source '%s' must have at least one output", ws_id)
            return None

        outputs = []
        for oid in output_ids:
            output = self._manager.outputs.get_output(str(oid))
            if output is None:
                _LOGGER.error("Water source '%s': output '%s' not found", ws_id, oid)
                return None
            outputs.append(output)

        return WaterSource(
            id=ws_id,
            name=name,
            outputs=outputs,
            output_start_delay_s=int(parse_time_to_seconds(ws_cfg.get("output_start_delay"), 0)),
            output_stop_delay_s=int(parse_time_to_seconds(ws_cfg.get("output_stop_delay"), 0)),
            pump_start_pump_delay_s=int(parse_time_to_seconds(ws_cfg.get("pump_start_pump_delay"), 0)),
            pump_start_valve_delay_s=int(parse_time_to_seconds(ws_cfg.get("pump_start_valve_delay"), 0)),
            pump_stop_pump_delay_s=int(parse_time_to_seconds(ws_cfg.get("pump_stop_pump_delay"), 0)),
            pump_stop_valve_delay_s=int(parse_time_to_seconds(ws_cfg.get("pump_stop_valve_delay"), 0)),
            pump_switch_off_during_valve_open_delay=bool(ws_cfg.get("pump_switch_off_during_valve_open_delay", False)),
        )

    @property
    def controllers(self) -> dict[str, IrrigationController]:
        return self._controllers

    async def send_ha_autodiscovery(self) -> None:
        for ctrl in self._controllers.values():
            self._publish_discovery(ctrl)

    async def start(self) -> None:
        """Start irrigation controllers — called once on first MQTT connection.

        Subscribes MQTT command topics, starts schedule tasks, and publishes
        initial states.
        """
        for ctrl in self._controllers.values():
            await self._subscribe_controller(ctrl)
            ctrl.start_schedules()
            await ctrl.publish_all_states()
            _LOGGER.info(
                "Irrigation controller '%s' started with %d schedule(s), %d zone(s)",
                ctrl.id,
                len(ctrl._schedule),
                len(ctrl.zones),
            )

    async def reconnect(self) -> None:
        """Handle MQTT (re-)connect — re-subscribe topics and re-publish states.

        On **first connection** (no schedule tasks running yet), schedule tasks
        are started for each controller.  On subsequent MQTT reconnects the
        existing schedule tasks are left untouched — they are long-lived
        ``asyncio.Task``s that sleep until the next fire time.  Restarting
        them would cancel the pending sleep and recalculate the next fire time
        from "now", potentially skipping a schedule that was about to fire.
        """
        # Detect first connection: if any controller has no schedule tasks yet,
        # we treat this as the initial start.
        first_connect = any(
            ctrl._schedule and not ctrl._schedule_tasks
            for ctrl in self._controllers.values()
        )
        if first_connect:
            _LOGGER.info("Irrigation: first MQTT connection — starting schedule tasks")
        else:
            _LOGGER.info("Irrigation MQTT reconnect: re-subscribing topics and re-publishing states")

        for ctrl in self._controllers.values():
            await self._subscribe_controller(ctrl)
            if first_connect and ctrl._schedule and not ctrl._schedule_tasks:
                ctrl.start_schedules()
            await ctrl.publish_all_states()

    async def stop(self) -> None:
        for topic in list(self._subscribed_topics):
            with contextlib.suppress(Exception):
                await self._manager.message_bus.unsubscribe_and_stop_listen(topic)
        self._subscribed_topics.clear()

        for ctrl in self._controllers.values():
            await ctrl.full_stop()

    async def reload_irrigation(self) -> None:
        """Reload irrigation configuration from file.

        Handles adding, removing, and updating irrigation controllers
        without requiring a full application restart.
        """
        _LOGGER.info("Reloading irrigation configuration")

        config = self._manager._config_helper.get_config()
        # Read from dedicated irrigation section
        new_irrigation_config: list[dict[str, Any]] = list(config.get("irrigation", []))
        # Also include irrigation entries from template section
        for entry in config.get("template", []):
            if entry.get("platform") == "irrigation":
                new_irrigation_config.append(entry)

        new_ids = set()
        for cfg in new_irrigation_config:
            ctrl_id = str(cfg.get("id", "")).strip()
            if ctrl_id:
                new_ids.add(ctrl_id)

        # Stop & remove deleted controllers
        removed_ids = set(self._controllers.keys()) - new_ids
        for ctrl_id in removed_ids:
            ctrl = self._controllers[ctrl_id]
            _LOGGER.info("Removing irrigation controller '%s'", ctrl_id)
            ctrl.stop_schedules()
            await ctrl.full_stop()
            # Remove HA discovery for this controller
            self._remove_discovery(ctrl)
            del self._controllers[ctrl_id]

        # Add new / update existing controllers
        for cfg in new_irrigation_config:
            ctrl_id = str(cfg.get("id", "")).strip()
            if not ctrl_id:
                continue

            # Remove existing controller (will be re-created)
            if ctrl_id in self._controllers:
                old_ctrl = self._controllers[ctrl_id]
                old_ctrl.stop_schedules()
                await old_ctrl.full_stop()
                del self._controllers[ctrl_id]

            # Build new controller
            ctrl = self._build_controller(cfg)
            if ctrl is None:
                _LOGGER.error("Failed to rebuild irrigation controller '%s'", ctrl_id)
                continue
            self._controllers[ctrl_id] = ctrl

            # Subscribe, publish discovery, start schedules
            await self._subscribe_controller(ctrl)
            self._publish_discovery(ctrl)
            ctrl.start_schedules()
            await ctrl.publish_all_states()
            _LOGGER.info("Reloaded irrigation controller '%s'", ctrl_id)

        # Unsubscribe topics for controllers that no longer exist
        valid_prefixes = set()
        for ctrl in self._controllers.values():
            valid_prefixes.add(f"{ctrl._topic_prefix}/cmd/irrigation/{ctrl.id}")
        stale_topics = {t for t in self._subscribed_topics if not any(t.startswith(p) for p in valid_prefixes)}
        for topic in stale_topics:
            with contextlib.suppress(Exception):
                await self._manager.message_bus.unsubscribe_and_stop_listen(topic)
            self._subscribed_topics.discard(topic)

        _LOGGER.info(
            "Irrigation reload complete: %d controllers active",
            len(self._controllers),
        )

    def _remove_discovery(self, ctrl: IrrigationController) -> None:
        """Remove HA discovery messages for an irrigation controller.

        Sends empty payload to discovery topics to remove entities from HA.
        """
        cfg = self._manager.config_helper
        serial = cfg.serial_number

        # Build list of discovery IDs to remove
        discovery_ids: list[tuple[str, str]] = [
            (f"{ctrl.id}", "switch"),
            (f"{ctrl.id}_skip_next_run", "switch"),
            (f"{ctrl.id}_standby", "switch"),
            (f"{ctrl.id}_multiplier", "number"),
            (f"{ctrl.id}_repeat", "number"),
            (f"{ctrl.id}_pause", "button"),
            (f"{ctrl.id}_resume", "button"),
            (f"{ctrl.id}_event", "event"),
        ]
        # Multi-zone-only entities
        if len(ctrl.zones) > 1:
            discovery_ids.extend([
                (f"{ctrl.id}_auto_advance", "switch"),
                (f"{ctrl.id}_reverse", "switch"),
                (f"{ctrl.id}_next_valve", "button"),
            ])
        for zone in ctrl.zones:
            discovery_ids.append((f"{ctrl.id}_zone_{zone.id}", "valve"))
            discovery_ids.append((f"{ctrl.id}_zone_{zone.id}_enabled", "switch"))
            discovery_ids.append((f"{ctrl.id}_zone_{zone.id}_duration", "number"))
        for idx in range(len(ctrl._schedule)):
            discovery_ids.append((f"{ctrl.id}_schedule_{idx}_skip", "switch"))

        for disc_id, ha_type in discovery_ids:
            topic = f"{cfg.ha_discovery_prefix}/{ha_type}/{serial}/{disc_id}/config"
            self._manager.send_message(topic=topic, payload="", retain=True)

    async def _subscribe_topic(self, topic: str, handler) -> None:
        if topic in self._subscribed_topics:
            _LOGGER.debug("Irrigation: topic already subscribed: %s", topic)
            return
        _LOGGER.debug("Irrigation: subscribing to MQTT topic: %s → handler=%s", topic, handler.__name__)
        await self._manager.message_bus.subscribe_and_listen(topic, handler)
        self._subscribed_topics.add(topic)

    async def _subscribe_controller(self, ctrl: IrrigationController) -> None:
        async def handle_main(_topic: str, payload: str, _ctrl: IrrigationController = ctrl) -> None:
            await _ctrl.handle_main_command(payload)

        await self._subscribe_topic(ctrl._cmd_topic(), handle_main)

        async def handle_auto_advance(_topic: str, payload: str, _ctrl: IrrigationController = ctrl) -> None:
            await _ctrl.set_auto_advance(payload.strip().upper() == ON)

        async def handle_reverse(_topic: str, payload: str, _ctrl: IrrigationController = ctrl) -> None:
            await _ctrl.set_reverse(payload.strip().upper() == ON)

        async def handle_multiplier(_topic: str, payload: str, _ctrl: IrrigationController = ctrl) -> None:
            try:
                val = float(payload)
            except (TypeError, ValueError):
                return
            await _ctrl.set_multiplier(val)

        async def handle_repeat(_topic: str, payload: str, _ctrl: IrrigationController = ctrl) -> None:
            try:
                val = int(float(payload))
            except (TypeError, ValueError):
                return
            await _ctrl.set_repeat(val)

        async def handle_skip_next(_topic: str, payload: str, _ctrl: IrrigationController = ctrl) -> None:
            await _ctrl.set_skip_next_run(payload.strip().upper() == ON)

        async def handle_standby(_topic: str, payload: str, _ctrl: IrrigationController = ctrl) -> None:
            await _ctrl.set_standby(payload.strip().upper() == ON)

        # Subscribe multi-zone-only MQTT handlers
        if len(ctrl.zones) > 1:
            await self._subscribe_topic(ctrl._setting_cmd_topic("auto_advance"), handle_auto_advance)
            await self._subscribe_topic(ctrl._setting_cmd_topic("reverse"), handle_reverse)
        await self._subscribe_topic(ctrl._setting_cmd_topic("multiplier"), handle_multiplier)
        await self._subscribe_topic(ctrl._setting_cmd_topic("repeat"), handle_repeat)
        await self._subscribe_topic(ctrl._setting_cmd_topic("skip_next_run"), handle_skip_next)
        await self._subscribe_topic(ctrl._setting_cmd_topic("standby"), handle_standby)

        # Water source select handler
        if ctrl.water_sources:

            async def handle_water_source(_topic: str, payload: str, _ctrl: IrrigationController = ctrl) -> None:
                await _ctrl.set_water_source(payload.strip())

            await self._subscribe_topic(ctrl._setting_cmd_topic("water_source"), handle_water_source)

        for zone in ctrl.zones:

            async def handle_zone(
                _topic: str, payload: str, _ctrl: IrrigationController = ctrl, _zone_id: str = zone.id
            ) -> None:
                await _ctrl.handle_zone_command(_zone_id, payload)

            async def handle_zone_enable(
                _topic: str, payload: str, _ctrl: IrrigationController = ctrl, _zone_id: str = zone.id
            ) -> None:
                await _ctrl.set_zone_enabled(_zone_id, payload.strip().upper() == ON)

            async def handle_zone_duration(
                _topic: str, payload: str, _ctrl: IrrigationController = ctrl, _zone_id: str = zone.id
            ) -> None:
                await _ctrl.handle_zone_duration_command(_zone_id, payload)

            await self._subscribe_topic(ctrl._zone_cmd_topic(zone.id), handle_zone)
            await self._subscribe_topic(ctrl._setting_cmd_topic(f"zone/{zone.id}/enabled"), handle_zone_enable)
            await self._subscribe_topic(ctrl._zone_duration_cmd_topic(zone.id), handle_zone_duration)

        for idx, _schedule in enumerate(ctrl._schedule):

            async def handle_sched_skip(
                _topic: str, payload: str, _ctrl: IrrigationController = ctrl, _idx: int = idx
            ) -> None:
                await _ctrl.set_schedule_skip(_idx, payload.strip().upper() == ON)

            await self._subscribe_topic(ctrl._schedule_skip_cmd_topic(idx), handle_sched_skip)

    def _publish_discovery(self, ctrl: IrrigationController) -> None:
        cfg = self._manager.config_helper
        # Resolve area name for HA suggested_area
        area_name = cfg.get_area_name(ctrl.area_id) if ctrl.area_id else None
        device = _ha_irrigation_device(ctrl.id, ctrl.name, cfg, area=ctrl.area_id, area_name=area_name)

        def _pub(id: str, ha_type: str, payload: dict | str) -> None:
            """Publish discovery with area-enriched device info."""
            if isinstance(payload, dict) and "device" in payload:
                payload["device"] = device
            self._manager.publish_ha_discovery(id=id, ha_type=ha_type, payload=payload)

        _pub(
            id=f"{ctrl.id}",
            ha_type="switch",
            payload=ha_irrigation_main_switch_message(ctrl.id, ctrl.name, cfg),
        )

        # Multi-zone-only switches: auto_advance, reverse
        if len(ctrl.zones) > 1:
            _pub(
                id=f"{ctrl.id}_auto_advance",
                ha_type="switch",
                payload=ha_irrigation_switch_message(
                    ctrl.id,
                    ctrl.name,
                    suffix="auto_advance",
                    name=f"{ctrl.name} Auto Advance",
                    config_helper=cfg,
                ),
            )

            _pub(
                id=f"{ctrl.id}_reverse",
                ha_type="switch",
                payload=ha_irrigation_switch_message(
                    ctrl.id,
                    ctrl.name,
                    suffix="reverse",
                    name=f"{ctrl.name} Reverse",
                    config_helper=cfg,
                ),
            )

        _pub(
            id=f"{ctrl.id}_skip_next_run",
            ha_type="switch",
            payload=ha_irrigation_switch_message(
                ctrl.id,
                ctrl.name,
                suffix="skip_next_run",
                name=f"{ctrl.name} Skip Next Run",
                config_helper=cfg,
            ),
        )

        _pub(
            id=f"{ctrl.id}_standby",
            ha_type="switch",
            payload=ha_irrigation_switch_message(
                ctrl.id,
                ctrl.name,
                suffix="standby",
                name=f"{ctrl.name} Standby",
                config_helper=cfg,
            ),
        )

        _pub(
            id=f"{ctrl.id}_multiplier",
            ha_type="number",
            payload=ha_irrigation_number_message(
                ctrl.id,
                ctrl.name,
                suffix="multiplier",
                name=f"{ctrl.name} Multiplier",
                min_val=0.1,
                max_val=5.0,
                step=0.1,
                unit="x",
                config_helper=cfg,
            ),
        )

        _pub(
            id=f"{ctrl.id}_repeat",
            ha_type="number",
            payload=ha_irrigation_number_message(
                ctrl.id,
                ctrl.name,
                suffix="repeat",
                name=f"{ctrl.name} Repeat",
                min_val=0,
                max_val=10,
                step=1,
                unit="",
                config_helper=cfg,
            ),
        )

        # Multi-zone-only button: next_valve
        if len(ctrl.zones) > 1:
            _pub(
                id=f"{ctrl.id}_next_valve",
                ha_type="button",
                payload=ha_irrigation_button_message(
                    ctrl.id,
                    ctrl.name,
                    suffix="next_valve",
                    name=f"{ctrl.name} Next Valve",
                    payload_press=NEXT_VALVE,
                    config_helper=cfg,
                ),
            )

        _pub(
            id=f"{ctrl.id}_pause",
            ha_type="button",
            payload=ha_irrigation_button_message(
                ctrl.id,
                ctrl.name,
                suffix="pause",
                name=f"{ctrl.name} Pause",
                payload_press=PAUSE,
                config_helper=cfg,
            ),
        )

        _pub(
            id=f"{ctrl.id}_resume",
            ha_type="button",
            payload=ha_irrigation_button_message(
                ctrl.id,
                ctrl.name,
                suffix="resume",
                name=f"{ctrl.name} Resume",
                payload_press=RESUME,
                config_helper=cfg,
            ),
        )

        for zone in ctrl.zones:
            # Remove stale switch discovery (migration from switch → valve)
            self._manager.publish_ha_discovery(
                id=f"{ctrl.id}_zone_{zone.id}",
                ha_type="switch",
                payload="",
            )
            _pub(
                id=f"{ctrl.id}_zone_{zone.id}",
                ha_type="valve",
                payload=ha_irrigation_valve_message(
                    ctrl.id,
                    ctrl.name,
                    suffix=f"zone/{zone.id}",
                    name=f"{ctrl.name} {zone.name}",
                    config_helper=cfg,
                ),
            )

            _pub(
                id=f"{ctrl.id}_zone_{zone.id}_enabled",
                ha_type="switch",
                payload=ha_irrigation_switch_message(
                    ctrl.id,
                    ctrl.name,
                    suffix=f"zone/{zone.id}/enabled",
                    name=f"{ctrl.name} {zone.name} Enabled",
                    config_helper=cfg,
                ),
            )

            # Duration max: configured time + 20min, clamped to [30, 120]
            zone_duration_min = max(1, round(zone.run_duration / 60))
            duration_max = min(120, max(30, zone_duration_min + 20))

            _pub(
                id=f"{ctrl.id}_zone_{zone.id}_duration",
                ha_type="number",
                payload=ha_irrigation_number_message(
                    ctrl.id,
                    ctrl.name,
                    suffix=f"zone/{zone.id}/duration",
                    name=f"{ctrl.name} {zone.name} Duration",
                    min_val=1,
                    max_val=duration_max,
                    step=1,
                    unit="min",
                    config_helper=cfg,
                ),
            )

            # Remove stale per-zone next_run sensor (migrated to valve attributes)
            if zone.run_every_n > 1:
                self._manager.publish_ha_discovery(
                    id=f"{ctrl.id}_zone_{zone.id}_next_run",
                    ha_type="sensor",
                    payload="",
                )

        for idx, _schedule in enumerate(ctrl._schedule):
            _pub(
                id=f"{ctrl.id}_schedule_{idx}_skip",
                ha_type="switch",
                payload=ha_irrigation_switch_message(
                    ctrl.id,
                    ctrl.name,
                    suffix=f"schedule/{idx}/skip",
                    name=f"{ctrl.name} Schedule {idx + 1} Skip",
                    config_helper=cfg,
                ),
            )

        # Zone end time sensor — HA shows countdown automatically
        _pub(
            id=f"{ctrl.id}_zone_end_time",
            ha_type="sensor",
            payload=ha_irrigation_timestamp_sensor_message(
                ctrl.id,
                ctrl.name,
                suffix="zone_end_time",
                name=f"{ctrl.name} Zone End Time",
                config_helper=cfg,
            ),
        )

        # Next scheduled run time sensor
        _pub(
            id=f"{ctrl.id}_next_run_time",
            ha_type="sensor",
            payload=ha_irrigation_timestamp_sensor_message(
                ctrl.id,
                ctrl.name,
                suffix="next_run_time",
                name=f"{ctrl.name} Next Run",
                config_helper=cfg,
                icon="mdi:calendar-clock",
            ),
        )

        # Water source select — only when multiple sources exist
        if len(ctrl.water_sources) > 1:
            _pub(
                id=f"{ctrl.id}_water_source",
                ha_type="select",
                payload=ha_irrigation_select_message(
                    ctrl.id,
                    ctrl.name,
                    options=[ws.id for ws in ctrl.water_sources],
                    config_helper=cfg,
                ),
            )

        # Event entity — fires on interlock faults, cycle completions, etc.
        _pub(
            id=f"{ctrl.id}_event",
            ha_type="event",
            payload=ha_irrigation_event_message(
                ctrl.id,
                ctrl.name,
                config_helper=cfg,
            ),
        )
