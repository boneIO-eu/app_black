"""Irrigation manager - handles irrigation controllers and MQTT integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from boneio.components.irrigation import IrrigationController, IrrigationZone
from boneio.const import IRRIGATION, NEXT_VALVE, OFF, ON, PAUSE, RESUME
from boneio.core.utils.timeperiod import parse_time_to_seconds
from boneio.integration.homeassistant import (
    ha_irrigation_button_message,
    ha_irrigation_main_switch_message,
    ha_irrigation_number_message,
    ha_irrigation_switch_message,
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

        master_valve = None
        master_valve_id = cfg.get("master_valve")
        if master_valve_id:
            master_valve = self._manager.outputs.get_output(str(master_valve_id))
            if master_valve is None:
                _LOGGER.warning(
                    "Irrigation %s: master valve '%s' not found, continuing without master valve",
                    ctrl_id,
                    master_valve_id,
                )

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
            master_valve=master_valve,
            valve_open_delay_s=int(parse_time_to_seconds(cfg.get("valve_open_delay"), 0)),
            valve_overlap_s=int(parse_time_to_seconds(cfg.get("valve_overlap"), 0)),
            standby=bool(cfg.get("standby", False)),
            pump_switch_off_during_valve_open_delay=bool(cfg.get("pump_switch_off_during_valve_open_delay", False)),
            pump_start_pump_delay_s=int(parse_time_to_seconds(cfg.get("pump_start_pump_delay"), 0)),
            pump_start_valve_delay_s=int(parse_time_to_seconds(cfg.get("pump_start_valve_delay"), 0)),
            pump_stop_pump_delay_s=int(parse_time_to_seconds(cfg.get("pump_stop_pump_delay"), 0)),
            pump_stop_valve_delay_s=int(parse_time_to_seconds(cfg.get("pump_stop_valve_delay"), 0)),
            multiplier=float(cfg.get("multiplier", 1.0)),
            repeat=int(cfg.get("repeat", 0)),
            auto_advance=bool(cfg.get("auto_advance", True)),
            reverse=bool(cfg.get("reverse", False)),
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
        run_duration = max(1, run_duration)

        run_every_days = int(parse_time_to_seconds(zone_cfg.get("run_every"), 24 * 60 * 60) / (24 * 60 * 60))
        run_every_days = max(1, run_every_days)

        return IrrigationZone(
            id=zone_id,
            name=str(zone_cfg.get("name", zone_id)),
            valve=valve,
            run_duration=run_duration,
            enabled=bool(zone_cfg.get("enabled", True)),
            run_every_days=run_every_days,
        )

    @property
    def controllers(self) -> dict[str, IrrigationController]:
        return self._controllers

    async def send_ha_autodiscovery(self) -> None:
        for ctrl in self._controllers.values():
            self._publish_discovery(ctrl)

    async def start(self) -> None:
        for ctrl in self._controllers.values():
            await self._subscribe_controller(ctrl)
            ctrl.start_schedules()
            await ctrl.publish_all_states()

    async def stop(self) -> None:
        for topic in list(self._subscribed_topics):
            try:
                await self._manager.message_bus.unsubscribe_and_stop_listen(topic)
            except Exception:
                pass
        self._subscribed_topics.clear()

        for ctrl in self._controllers.values():
            await ctrl.shutdown()

    async def _subscribe_topic(self, topic: str, handler) -> None:
        if topic in self._subscribed_topics:
            return
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

        await self._subscribe_topic(ctrl._setting_cmd_topic("auto_advance"), handle_auto_advance)
        await self._subscribe_topic(ctrl._setting_cmd_topic("reverse"), handle_reverse)
        await self._subscribe_topic(ctrl._setting_cmd_topic("multiplier"), handle_multiplier)
        await self._subscribe_topic(ctrl._setting_cmd_topic("repeat"), handle_repeat)
        await self._subscribe_topic(ctrl._setting_cmd_topic("skip_next_run"), handle_skip_next)
        await self._subscribe_topic(ctrl._setting_cmd_topic("standby"), handle_standby)

        for zone in ctrl.zones:
            async def handle_zone(_topic: str, payload: str, _ctrl: IrrigationController = ctrl, _zone_id: str = zone.id) -> None:
                await _ctrl.handle_zone_command(_zone_id, payload)

            async def handle_zone_enable(_topic: str, payload: str, _ctrl: IrrigationController = ctrl, _zone_id: str = zone.id) -> None:
                await _ctrl.set_zone_enabled(_zone_id, payload.strip().upper() == ON)

            async def handle_zone_duration(_topic: str, payload: str, _ctrl: IrrigationController = ctrl, _zone_id: str = zone.id) -> None:
                await _ctrl.handle_zone_duration_command(_zone_id, payload)

            await self._subscribe_topic(ctrl._zone_cmd_topic(zone.id), handle_zone)
            await self._subscribe_topic(ctrl._setting_cmd_topic(f"zone/{zone.id}/enabled"), handle_zone_enable)
            await self._subscribe_topic(ctrl._zone_duration_cmd_topic(zone.id), handle_zone_duration)

        for idx, _schedule in enumerate(ctrl._schedule):
            async def handle_sched_skip(_topic: str, payload: str, _ctrl: IrrigationController = ctrl, _idx: int = idx) -> None:
                await _ctrl.set_schedule_skip(_idx, payload.strip().upper() == ON)

            await self._subscribe_topic(ctrl._schedule_skip_cmd_topic(idx), handle_sched_skip)

    def _publish_discovery(self, ctrl: IrrigationController) -> None:
        cfg = self._manager.config_helper

        self._manager.publish_ha_discovery(
            id=f"{ctrl.id}",
            ha_type="switch",
            payload=ha_irrigation_main_switch_message(ctrl.id, ctrl.name, cfg),
        )

        self._manager.publish_ha_discovery(
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

        self._manager.publish_ha_discovery(
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

        self._manager.publish_ha_discovery(
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

        self._manager.publish_ha_discovery(
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

        self._manager.publish_ha_discovery(
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

        self._manager.publish_ha_discovery(
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

        self._manager.publish_ha_discovery(
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

        self._manager.publish_ha_discovery(
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

        self._manager.publish_ha_discovery(
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
            self._manager.publish_ha_discovery(
                id=f"{ctrl.id}_zone_{zone.id}",
                ha_type="switch",
                payload=ha_irrigation_switch_message(
                    ctrl.id,
                    ctrl.name,
                    suffix=f"zone/{zone.id}",
                    name=f"{ctrl.name} {zone.name}",
                    config_helper=cfg,
                ),
            )

            self._manager.publish_ha_discovery(
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

            self._manager.publish_ha_discovery(
                id=f"{ctrl.id}_zone_{zone.id}_duration",
                ha_type="number",
                payload=ha_irrigation_number_message(
                    ctrl.id,
                    ctrl.name,
                    suffix=f"zone/{zone.id}/duration",
                    name=f"{ctrl.name} {zone.name} Duration",
                    min_val=1,
                    max_val=86400,
                    step=1,
                    unit="s",
                    config_helper=cfg,
                ),
            )

        for idx, _schedule in enumerate(ctrl._schedule):
            self._manager.publish_ha_discovery(
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
