"""Irrigation control routes for BoneIO Web UI."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from boneio.const import NEXT_VALVE, OFF, ON, PAUSE, RESUME
from boneio.core.manager import Manager

_LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/irrigation", tags=["irrigation"])


def get_manager():
    """Get manager instance - will be overridden by app initialization."""
    raise NotImplementedError("Manager not initialized")


# ============================================================================
# List all irrigation controllers and their zone states
# ============================================================================


@router.get("")
async def list_controllers(manager: Manager = Depends(get_manager)):
    """Return current state of all irrigation controllers.

    Returns:
        List of controllers with their zones and runtime status.
    """
    result = []
    for ctrl in manager.irrigation._controllers.values():
        active_zone = None
        if ctrl._active_zone_idx is not None and 0 <= ctrl._active_zone_idx < len(ctrl.zones):
            z = ctrl.zones[ctrl._active_zone_idx]
            end_utc = None
            remaining_s = ctrl._active_zone_remaining_s
            if ctrl._run_start_utc and ctrl._active_zone_remaining_s:
                from datetime import timedelta

                end_dt = ctrl._run_start_utc + timedelta(seconds=ctrl._active_zone_remaining_s)
                end_utc = end_dt.isoformat()
                # Calculate real remaining based on current time
                from boneio.core.events.bus import utcnow

                remaining_s = max(0, int((end_dt - utcnow()).total_seconds()))
            active_zone = {
                "id": z.id,
                "name": z.name,
                "remaining_s": remaining_s,
                "end_utc": end_utc,
            }

        zones = []
        for z in ctrl.zones:
            skip_count = ctrl._get(f"zone/{z.id}/skip_count", 0)
            zones.append(
                {
                    "id": z.id,
                    "name": z.name,
                    "run_duration": z.run_duration // 60,
                    "enabled": z.enabled,
                    "run_every_n": z.run_every_n,
                    "skip_count": int(skip_count),
                }
            )

        schedules = []
        for idx, sched in enumerate(ctrl._schedule):
            schedules.append(
                {
                    "index": idx,
                    "time": sched.get("time", ""),
                    "days": sched.get("days", "daily"),
                    "skip": sched.get("skip", False),
                }
            )

        result.append(
            {
                "id": ctrl.id,
                "name": ctrl.name,
                "state": ctrl.state.value,
                "active_zone": active_zone,
                "multiplier": ctrl._multiplier,
                "repeat": ctrl._repeat,
                "auto_advance": ctrl._auto_advance,
                "reverse": ctrl._reverse,
                "standby": ctrl._standby,
                "skip_next_run": ctrl._skip_next_run,
                "pause_timeout_s": ctrl._pause_timeout_s,
                "zones": zones,
                "schedules": schedules,
                "water_sources": [
                    {"id": ws.id, "name": ws.name, "output_ids": ws.output_ids} for ws in ctrl.water_sources
                ],
                "active_water_source": ctrl.active_water_source.id if ctrl.active_water_source else None,
            }
        )
    return result


# ============================================================================
# Controller commands: start / stop / pause / resume / next_valve
# ============================================================================


@router.post("/{ctrl_id}/command")
async def controller_command(
    ctrl_id: str,
    data: dict[str, Any] = Body(...),
    manager: Manager = Depends(get_manager),
):
    """Send a command to an irrigation controller.

    Supported commands: ON, OFF, PAUSE, RESUME, NEXT_VALVE.
    """
    ctrl = manager.irrigation._controllers.get(ctrl_id)
    if not ctrl:
        raise HTTPException(status_code=404, detail="Irrigation controller not found")

    command = str(data.get("command", "")).upper()

    if command == ON:
        await ctrl.start_full_cycle()
    elif command == OFF:
        await ctrl.shutdown()
    elif command == PAUSE:
        await ctrl.pause()
    elif command == RESUME:
        await ctrl.resume()
    elif command == NEXT_VALVE:
        await ctrl.next_valve()
    else:
        raise HTTPException(status_code=400, detail=f"Unknown command: {command}")

    return {"status": "ok", "state": ctrl.state.value}


# ============================================================================
# Zone commands: enable/disable a single zone or start it manually
# ============================================================================


@router.post("/{ctrl_id}/zone/{zone_id}/command")
async def zone_command(
    ctrl_id: str,
    zone_id: str,
    data: dict[str, Any] = Body(...),
    manager: Manager = Depends(get_manager),
):
    """Send a command to a specific irrigation zone.

    Supported commands: ON (start zone), OFF (stop), ENABLE, DISABLE, NEXT_VALVE (skip to next).
    """
    ctrl = manager.irrigation._controllers.get(ctrl_id)
    if not ctrl:
        raise HTTPException(status_code=404, detail="Irrigation controller not found")

    zone = next((z for z in ctrl.zones if z.id == zone_id), None)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")

    command = str(data.get("command", "")).upper()

    if command == ON:
        await ctrl.start_single_zone(zone_id)
    elif command == OFF:
        await ctrl.shutdown()
    elif command == NEXT_VALVE:
        await ctrl.next_valve()
    elif command == "ENABLE":
        zone.enabled = True
        ctrl._save(f"zone/{zone_id}/enabled", True)
    elif command == "DISABLE":
        zone.enabled = False
        ctrl._save(f"zone/{zone_id}/enabled", False)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown zone command: {command}")

    return {"status": "ok"}


# ============================================================================
# Zone settings: update duration
# ============================================================================


@router.post("/{ctrl_id}/zone/{zone_id}/settings")
async def update_zone_settings(
    ctrl_id: str,
    zone_id: str,
    data: dict[str, Any] = Body(...),
    manager: Manager = Depends(get_manager),
):
    """Update zone runtime settings (duration, run_every_n).

    Body fields (all optional):
        run_duration: int  — seconds
        run_every_n: int — run every Nth scheduled cycle
        enabled: bool
    """
    ctrl = manager.irrigation._controllers.get(ctrl_id)
    if not ctrl:
        raise HTTPException(status_code=404, detail="Irrigation controller not found")

    zone = next((z for z in ctrl.zones if z.id == zone_id), None)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")

    if "run_duration" in data:
        val = int(data["run_duration"])
        if val < 1:
            raise HTTPException(status_code=400, detail="run_duration must be >= 1")
        zone.run_duration = val * 60  # Convert minutes to seconds
        ctrl._save(f"zone/{zone_id}/duration", val * 60)

    if "run_every_n" in data:
        val = int(data["run_every_n"])
        if val < 1:
            raise HTTPException(status_code=400, detail="run_every_n must be >= 1")
        zone.run_every_n = val
        ctrl._save(f"zone/{zone_id}/run_every_n", val)

    if "enabled" in data:
        zone.enabled = bool(data["enabled"])
        ctrl._save(f"zone/{zone_id}/enabled", zone.enabled)

    return {"status": "ok"}


# ============================================================================
# Controller settings: multiplier, repeat, skip_next_run, auto_advance, reverse
# ============================================================================


@router.post("/{ctrl_id}/settings")
async def update_controller_settings(
    ctrl_id: str,
    data: dict[str, Any] = Body(...),
    manager: Manager = Depends(get_manager),
):
    """Update controller-level runtime settings.

    Body fields (all optional):
        multiplier: float
        repeat: int
        skip_next_run: bool
        auto_advance: bool
        reverse: bool
        standby: bool
    """
    ctrl = manager.irrigation._controllers.get(ctrl_id)
    if not ctrl:
        raise HTTPException(status_code=404, detail="Irrigation controller not found")

    if "multiplier" in data:
        val = float(data["multiplier"])
        if val < 0.1:
            raise HTTPException(status_code=400, detail="multiplier must be >= 0.1")
        ctrl._multiplier = val
        ctrl._save("multiplier", val)

    if "repeat" in data:
        val = int(data["repeat"])
        if val < 0:
            raise HTTPException(status_code=400, detail="repeat must be >= 0")
        ctrl._repeat = val
        ctrl._save("repeat", val)

    if "skip_next_run" in data:
        ctrl._skip_next_run = bool(data["skip_next_run"])
        ctrl._save("skip_next_run", ctrl._skip_next_run)

    if "auto_advance" in data:
        ctrl._auto_advance = bool(data["auto_advance"])
        ctrl._save("auto_advance", ctrl._auto_advance)

    if "reverse" in data:
        ctrl._reverse = bool(data["reverse"])
        ctrl._save("reverse", ctrl._reverse)

    if "standby" in data:
        await ctrl.set_standby(bool(data["standby"]))

    if "water_source" in data:
        await ctrl.set_water_source(str(data["water_source"]))

    return {"status": "ok"}


# ============================================================================
# Schedule skip toggle
# ============================================================================


@router.post("/{ctrl_id}/schedule/{idx}/skip")
async def toggle_schedule_skip(
    ctrl_id: str,
    idx: int,
    data: dict[str, Any] = Body(...),
    manager: Manager = Depends(get_manager),
):
    """Set skip flag for a schedule entry.

    Body fields:
        skip: bool
    """
    ctrl = manager.irrigation._controllers.get(ctrl_id)
    if not ctrl:
        raise HTTPException(status_code=404, detail="Irrigation controller not found")

    if idx < 0 or idx >= len(ctrl._schedule):
        raise HTTPException(status_code=404, detail="Schedule index out of range")

    skip = bool(data.get("skip", False))
    ctrl._schedule[idx]["skip"] = skip
    ctrl._save(f"schedule/{idx}/skip", skip)

    return {"status": "ok", "skip": skip}


# ============================================================================
# AI Context: export available outputs + existing controllers for AI prompt
# ============================================================================


@router.get("/ai-context")
async def get_ai_context(manager: Manager = Depends(get_manager)):
    """Return context data for AI-assisted irrigation configuration.

    Provides available outputs, existing controllers, and schema summary
    that can be embedded into an AI prompt for generating irrigation config.

    Returns:
        Dict with available_outputs, existing_controllers, and schema_summary.
    """
    # Available outputs (relays, valves, etc.)
    available_outputs = []
    used_output_ids: set[str] = set()

    # Collect output IDs already used by irrigation controllers
    for ctrl in manager.irrigation._controllers.values():
        for zone in ctrl.zones:
            if hasattr(zone, "valve") and hasattr(zone.valve, "id"):
                used_output_ids.add(zone.valve.id)
        for ws in ctrl.water_sources:
            for out in ws.outputs:
                if hasattr(out, "id"):
                    used_output_ids.add(out.id)

    for output_id, output in manager.outputs.get_all_outputs().items():
        out_info: dict[str, Any] = {
            "id": output_id,
            "name": getattr(output, "name", output_id),
            "type": getattr(output, "output_type", "unknown"),
        }
        if output_id in used_output_ids:
            out_info["in_use"] = True
            # Find which controller uses it
            for ctrl in manager.irrigation._controllers.values():
                for zone in ctrl.zones:
                    if hasattr(zone, "valve") and getattr(zone.valve, "id", None) == output_id:
                        out_info["used_by"] = f"irrigation:{ctrl.id}:zone:{zone.id}"
                        break
                for ws in ctrl.water_sources:
                    for out_obj in ws.outputs:
                        if getattr(out_obj, "id", None) == output_id:
                            out_info["used_by"] = f"irrigation:{ctrl.id}:source:{ws.id}"
                            break
        else:
            out_info["in_use"] = False

        available_outputs.append(out_info)

    # Existing controllers summary
    existing_controllers = []
    for ctrl in manager.irrigation._controllers.values():
        existing_controllers.append({
            "id": ctrl.id,
            "name": ctrl.name,
            "zones": [{"id": z.id, "name": z.name, "valve": getattr(z.valve, "id", None)} for z in ctrl.zones],
            "water_sources": [
                {"id": ws.id, "name": ws.name, "outputs": ws.output_ids}
                for ws in ctrl.water_sources
            ],
            "schedules": [
                {"time": s.get("time", ""), "days": s.get("days", "daily")}
                for s in ctrl._schedule
            ],
        })

    return {
        "device_name": getattr(manager, "_device_name", "boneIO Black"),
        "available_outputs": available_outputs,
        "existing_controllers": existing_controllers,
        "schema_summary": {
            "controller_fields": [
                "id (string, lowercase, no spaces)",
                "name (string, display name)",
                "schedule (list of {time: 'HH:MM', days: 'daily|weekdays|weekend|mon|tue|wed|thu|fri|sat|sun'})",
                "auto_advance (bool, default true)",
                "reverse (bool, default false)",
                "repeat (int, 0=once)",
                "valve_open_delay (string, e.g. '5s')",
            ],
            "zone_fields": [
                "id (string, lowercase)",
                "name (string, display name)",
                "valve (string, output_id from available_outputs)",
                "run_duration (int, minutes)",
                "run_every_n (int, 1=every cycle, 2=every other, etc.)",
            ],
            "water_source_fields": [
                "id (string, lowercase)",
                "name (string, display name)",
                "outputs (list of output_id strings — pumps/master valves)",
            ],
        },
    }


# ============================================================================
# AI Import: validate and save AI-generated irrigation configuration
# ============================================================================


@router.post("/import")
async def import_irrigation_config(
    data: dict[str, Any] = Body(...),
    manager: Manager = Depends(get_manager),
):
    """Import AI-generated irrigation configuration.

    Validates the provided JSON and writes it to the YAML config file.
    Does NOT restart controllers — user must reload or restart.

    Body:
        controllers: list of controller definitions
            Each controller has: id, name, zones, water_sources, schedule, etc.

    Returns:
        Dict with status, created/updated controller IDs, and any conflicts.
    """
    controllers = data.get("controllers", [])
    if not controllers:
        raise HTTPException(status_code=400, detail="No controllers provided in import data.")

    # Validate output IDs exist
    all_output_ids = set(manager.outputs.get_all_outputs().keys())
    errors: list[str] = []
    conflicts: list[str] = []

    for ctrl_def in controllers:
        ctrl_id = ctrl_def.get("id", "")
        if not ctrl_id:
            errors.append("Controller missing 'id' field.")
            continue

        # Check for existing controller
        if ctrl_id in manager.irrigation._controllers:
            conflicts.append(ctrl_id)

        # Validate zone valve IDs
        for zone in ctrl_def.get("zones", []):
            valve_id = zone.get("valve", "")
            if valve_id and valve_id not in all_output_ids:
                errors.append(f"Zone '{zone.get('id', '?')}' valve '{valve_id}' not found in available outputs.")

        # Validate water source output IDs
        for ws in ctrl_def.get("water_sources", []):
            for out_id in ws.get("outputs", []):
                if out_id not in all_output_ids:
                    errors.append(f"Water source '{ws.get('id', '?')}' output '{out_id}' not found in available outputs.")

    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors, "conflicts": conflicts})

    # Build YAML-compatible irrigation config
    import_configs: list[dict[str, Any]] = []
    for ctrl_def in controllers:
        cfg: dict[str, Any] = {
            "id": ctrl_def["id"],
            "name": ctrl_def.get("name", ctrl_def["id"]),
        }

        # Schedule
        if ctrl_def.get("schedule"):
            cfg["schedule"] = ctrl_def["schedule"]

        # Settings
        for field in ("auto_advance", "reverse", "repeat", "valve_open_delay", "valve_overlap",
                       "pause_timeout", "pump_off_during_delay"):
            if field in ctrl_def:
                cfg[field] = ctrl_def[field]

        # Zones
        zones_cfg = []
        for z in ctrl_def.get("zones", []):
            zone_cfg: dict[str, Any] = {
                "id": z["id"],
                "name": z.get("name", z["id"]),
                "valve": z["valve"],
                "run_duration": f"{z.get('run_duration', 10)}min",
            }
            if z.get("run_every_n", 1) != 1:
                zone_cfg["run_every_n"] = z["run_every_n"]
            zones_cfg.append(zone_cfg)
        cfg["zones"] = zones_cfg

        # Water sources
        if ctrl_def.get("water_sources"):
            ws_cfg = []
            for ws in ctrl_def["water_sources"]:
                ws_item: dict[str, Any] = {
                    "id": ws["id"],
                    "name": ws.get("name", ws["id"]),
                    "outputs": ws["outputs"],
                }
                for delay_field in ("pump_start_valve_delay", "pump_start_pump_delay",
                                     "pump_stop_valve_delay", "pump_stop_pump_delay",
                                     "sequential_output_start_delay", "sequential_output_stop_delay"):
                    if delay_field in ws:
                        ws_item[delay_field] = ws[delay_field]
                ws_cfg.append(ws_item)
            cfg["water_sources"] = ws_cfg

        import_configs.append(cfg)

    return {
        "status": "ok",
        "controllers": [c["id"] for c in import_configs],
        "conflicts": conflicts,
        "config": import_configs,
    }

