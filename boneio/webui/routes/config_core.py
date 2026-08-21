"""Core configuration routes and state management for BoneIO Web UI."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, Body, HTTPException

if TYPE_CHECKING:
    from starlette.datastructures import State

from boneio.core.config.yaml_util import (
    clear_config_cache,
    load_config_from_file,
    load_yaml_file,
    merge_board_config,
    update_config_section,
    wait_for_pending_yaml_saves,
)
from boneio.core.manager import Manager
from boneio.webui.action_validation import validate_section_actions as _validate_section_actions

_LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["config"])

# Config cache to avoid re-parsing YAML on every request
_config_cache: dict = {"data": None, "mtime": 0}

# SHA256 checksum cache - recomputed on every config change
_checksum_cache: dict = {"sha256": None, "file_count": 0}

# App state reference - set by app initialization
_app_state: State | None = None
_websocket_manager = None


def set_app_state(app_state: State) -> None:
    """Set app state reference."""
    global _app_state
    _app_state = app_state


def set_websocket_manager(ws_manager) -> None:
    """Set websocket manager reference."""
    global _websocket_manager
    _websocket_manager = ws_manager


def _get_app_state() -> State:
    """Get app state, raising an error if not initialized."""
    if _app_state is None:
        raise HTTPException(status_code=500, detail="App state not initialized")
    return _app_state


def get_manager():
    """Get manager instance - will be overridden by app initialization."""
    raise NotImplementedError("Manager not initialized")


def _get_config_yaml_files(config_dir: Path) -> list[Path]:
    """
    Get sorted list of all YAML config files (same set as download_config).

    Args:
        config_dir: Root config directory.

    Returns:
        Sorted list of Path objects for all YAML files.
    """
    files: list[Path] = []
    for pattern in ["*.yaml", "*.yml"]:
        for yaml_file in config_dir.glob(pattern):
            if yaml_file.is_file():
                files.append(yaml_file)
    for subdir in config_dir.iterdir():
        if subdir.is_dir() and not subdir.name.startswith("."):
            for pattern in ["*.yaml", "*.yml"]:
                for yaml_file in subdir.glob(pattern):
                    if yaml_file.is_file():
                        files.append(yaml_file)
    files.sort(key=lambda p: str(p))
    return files


def _recompute_config_checksum() -> None:
    """
    Recompute SHA256 checksum over all YAML config files.

    The hash is deterministic: files are sorted by path, and both
    the relative path and content of each file are fed into the digest.
    """
    try:
        config_file = _get_app_state().yaml_config_file
        config_dir = Path(config_file).parent
        files = _get_config_yaml_files(config_dir)

        hasher = hashlib.sha256()
        for f in files:
            rel = str(f.relative_to(config_dir))
            hasher.update(rel.encode("utf-8"))
            hasher.update(f.read_bytes())

        _checksum_cache["sha256"] = hasher.hexdigest()
        _checksum_cache["file_count"] = len(files)
        _LOGGER.debug("Config checksum recomputed: %s (%d files)", _checksum_cache["sha256"][:12], len(files))
    except Exception as exc:
        _LOGGER.warning("Failed to compute config checksum: %s", exc)
        _checksum_cache["sha256"] = None
        _checksum_cache["file_count"] = 0


def invalidate_config_cache(
    section: str | None = None,
    section_data: object = None,
) -> None:
    """Invalidate route-level config cache and disk validation cache, recompute checksum.

    Clears the route-level mtime cache and the disk .pkl cache, then schedules
    a debounced background rebuild. The rebuild runs 30 seconds after the last
    config change so that rapid edits don't trigger multiple slow Cerberus
    validations (~20s each on BeagleBone).

    When *section* and *section_data* are provided, the corresponding key
    inside ``ConfigHelper._config_cache`` is patched **in-place** so that the
    next ``GET /api/config`` returns up-to-date data without reloading the
    full YAML from disk (which takes ~20-30 s on BeagleBone Black).
    """
    _config_cache["data"] = None
    _config_cache["mtime"] = 0

    # Patch ConfigHelper in-place when caller provides section data
    if section is not None and section_data is not None:
        try:
            app_state = _get_app_state()
            if (
                app_state
                and hasattr(app_state, "manager")
                and app_state.manager
                and hasattr(app_state.manager, "config_helper")
                and app_state.manager.config_helper
            ):
                app_state.manager.config_helper.update_config_section(
                    section, section_data,
                )
        except Exception as err:
            _LOGGER.debug(
                "Could not update config_helper section '%s' in-place: %s",
                section, err,
            )

    try:
        config_file = _get_app_state().yaml_config_file
        clear_config_cache(config_file)
        # Schedule debounced rebuild — not immediate
        _schedule_debounced_cache_rebuild(config_file)
    except Exception:
        clear_config_cache()
    _recompute_config_checksum()


# Debounced cache rebuild timer — cancels previous timer on each config change
_cache_rebuild_timer: threading.Timer | None = None
_cache_rebuild_lock: threading.Lock = threading.Lock()

# How long to wait after the last config edit before rebuilding disk cache
_CACHE_REBUILD_DELAY_SECONDS: float = 30.0


def _schedule_debounced_cache_rebuild(config_file: str) -> None:
    """Schedule a debounced background cache rebuild."""
    global _cache_rebuild_timer

    with _cache_rebuild_lock:
        if _cache_rebuild_timer is not None:
            _cache_rebuild_timer.cancel()
            _LOGGER.debug("Cancelled pending config cache rebuild timer")

        _cache_rebuild_timer = threading.Timer(
            _CACHE_REBUILD_DELAY_SECONDS,
            _do_cache_rebuild,
            args=(config_file,),
        )
        _cache_rebuild_timer.daemon = True
        _cache_rebuild_timer.name = "config-cache-rebuild-timer"
        _cache_rebuild_timer.start()
        _LOGGER.debug(
            "Scheduled config cache rebuild in %.0fs",
            _CACHE_REBUILD_DELAY_SECONDS,
        )


def _do_cache_rebuild(config_file: str) -> None:
    """Execute the actual disk cache rebuild."""
    global _cache_rebuild_timer

    try:
        _LOGGER.info("Background config cache rebuild started")
        load_config_from_file(config_file)
        _LOGGER.info("Background config cache rebuild completed")
    except Exception as e:
        _LOGGER.warning("Background config cache rebuild failed: %s", e)
    finally:
        with _cache_rebuild_lock:
            _cache_rebuild_timer = None


def _get_config_mtime(config_file: str) -> float:
    """Get the latest mtime of config file and all included files."""
    config_dir = Path(config_file).parent
    max_mtime = os.path.getmtime(config_file)

    for pattern in ["*.yaml", "*.yml"]:
        for f in config_dir.glob(pattern):
            try:
                mtime = os.path.getmtime(f)
                if mtime > max_mtime:
                    max_mtime = mtime
            except OSError:
                pass

    return max_mtime


@router.get("/config")
async def get_parsed_config():
    """Get parsed configuration data with !include resolved (cached with mtime check)."""
    import time

    try:
        config_file = _get_app_state().yaml_config_file
        current_mtime = _get_config_mtime(config_file)

        if _config_cache["data"] is not None and _config_cache["mtime"] >= current_mtime:
            _LOGGER.debug("Returning cached configuration (mtime unchanged)")
            return {"config": _config_cache["data"]}

        start = time.time()
        try:
            manager: Manager = _get_app_state().manager
            source_config = manager.config_helper.get_config()
        except Exception:
            source_config = load_yaml_file(config_file)
            try:
                source_config = merge_board_config(source_config)
            except Exception as merge_err:
                _LOGGER.warning("Failed to merge board config for API response: %s", merge_err)

        config_data = dict(source_config)

        if "output" in config_data and isinstance(config_data["output"], list):
            import re

            enriched: list[dict] = []
            for output in config_data["output"]:
                if not output.get("id"):
                    out = dict(output)
                    if out.get("boneio_output"):
                        out["id"] = out["boneio_output"]
                    elif out.get("name"):
                        name = out["name"].lower()
                        name = re.sub(r"[^a-z0-9]+", "_", name)
                        out["id"] = name.strip("_")
                    enriched.append(out)
                else:
                    enriched.append(output)
            config_data["output"] = enriched

        if "cover" in config_data and isinstance(config_data["cover"], list):
            enriched_covers: list[dict] = []
            for cover in config_data["cover"]:
                if not cover.get("id"):
                    cov = dict(cover)
                    open_relay = cov.get("open_relay", "")
                    close_relay = cov.get("close_relay", "")
                    if open_relay and close_relay:
                        cov["id"] = f"cover_{open_relay}_{close_relay}".lower().replace(" ", "_")
                    enriched_covers.append(cov)
                else:
                    enriched_covers.append(cover)
            config_data["cover"] = enriched_covers

        if "output_group" in config_data and isinstance(config_data["output_group"], list):
            import re

            enriched_groups: list[dict] = []
            for group in config_data["output_group"]:
                if not group.get("id") and group.get("name"):
                    grp = dict(group)
                    name = grp["name"].lower()
                    name = re.sub(r"[^a-z0-9]+", "_", name)
                    grp["id"] = name.strip("_")
                    enriched_groups.append(grp)
                else:
                    enriched_groups.append(group)
            config_data["output_group"] = enriched_groups

        _EVENT_ACTION_TYPES = (
            "single", "double", "triple", "long",
            "double_then_long", "single_then_long", "double_then_single",
        )
        for section_key in ("event", "remote_inputs"):
            if section_key in config_data and isinstance(config_data[section_key], list):
                for entry in config_data[section_key]:
                    if not isinstance(entry, dict):
                        continue
                    for act_type in _EVENT_ACTION_TYPES:
                        flat_key = f"actions_{act_type}"
                        if flat_key in entry:
                            if "actions" not in entry or not isinstance(entry.get("actions"), dict):
                                entry["actions"] = {}
                            # Merge (don't overwrite) in case actions.single already exists
                            existing = entry["actions"].get(act_type, [])
                            entry["actions"][act_type] = existing + entry.pop(flat_key)

        elapsed = time.time() - start

        _config_cache["data"] = config_data
        _config_cache["mtime"] = current_mtime

        _LOGGER.info("Loaded and cached configuration in %.2fs (mtime: %.0f)", elapsed, current_mtime)
        return {"config": config_data}

    except Exception as e:
        _LOGGER.error(f"Error loading parsed configuration: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error loading configuration: {str(e)}") from e


def _apply_entity_labels_to_coordinators(manager: Manager, devices_data: list) -> None:
    """Hot-apply entity_labels from saved config to running Modbus coordinators."""
    from boneio.const import ADDRESS, ID, MODEL

    if not hasattr(manager, "modbus") or manager.modbus is None:
        return

    coordinators = manager.modbus.get_all_coordinators()
    if not coordinators:
        return

    for device_config in devices_data:
        entity_labels = device_config.get("entity_labels")
        if entity_labels is None:
            continue

        has_custom_id = bool(device_config.get(ID))
        if has_custom_id:
            device_id = str(device_config[ID]).replace(" ", "").lower()
        else:
            addr = device_config.get(ADDRESS, "")
            model = device_config.get(MODEL, "")
            device_id = f"{addr}_{model}".lower().replace(" ", "_")

        coordinator = coordinators.get(device_id)
        if coordinator:
            coordinator.update_entity_labels(entity_labels)
            _LOGGER.info("Hot-applied entity labels for coordinator %s", device_id)


@router.put("/config/{section}")
async def update_section_content(section: str, data: dict | list = Body(...)):
    """Update content of a configuration section."""
    RESTART_REQUIRED_SECTIONS = {
        "boneio", "mqtt", "lox_udp", "web", "modbus",
        "mcp23017", "lm75", "ina219", "ina226", "mcp9808", "can",
    }

    if section in ("event", "binary_sensor") and isinstance(data, list):
        errors = _validate_section_actions(section, data)
        if errors:
            raise HTTPException(
                status_code=422,
                detail={"message": "Invalid action configuration", "errors": errors},
            )
        for entry in data:
            entry.pop("gpio_mode", None)

    if section == "lox_udp" and isinstance(data, dict) and data.get("enabled"):
        import re

        host = str(data.get("host", "")).strip()
        ipv4_re = r"^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$"
        hostname_re = r"^([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$"
        if not host or (not re.match(ipv4_re, host) and not re.match(hostname_re, host)):
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Invalid lox_udp configuration",
                    "errors": [f"Invalid host: '{host}'. Use an IPv4 address or hostname."],
                },
            )

    # Strip empty string values from data to prevent cerberus coercion failures
    # (e.g. bounce_time: '' instead of being omitted).
    def _strip_empty_strings(obj: dict | list) -> dict | list:
        """Recursively remove keys whose value is an empty string."""
        if isinstance(obj, list):
            return [
                _strip_empty_strings(item) if isinstance(item, (dict, list)) else item
                for item in obj
                if item != ""
            ]
        if isinstance(obj, dict):
            return {
                k: _strip_empty_strings(v) if isinstance(v, (dict, list)) else v
                for k, v in obj.items()
                if v != ""
            }
        return obj

    data = _strip_empty_strings(data)

    try:
        t_route_start = time.perf_counter()
        app_state = _get_app_state()

        # Wait for any pending background quick-action saves to complete
        # before doing a full section save (prevents overwriting changes).
        # Run in executor to avoid blocking the async event loop.
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, wait_for_pending_yaml_saves, 15.0
        )

        result = await loop.run_in_executor(
            None,
            update_config_section,
            app_state.yaml_config_file,
            section,
            data,
        )
        t_after_executor = time.perf_counter()
        _LOGGER.info(
            "[ROUTE] run_in_executor took %.3fs for section='%s'",
            t_after_executor - t_route_start, section,
        )

        if result["status"] == "error":
            raise HTTPException(status_code=500, detail=result["message"])

        invalidate_config_cache(section=section, section_data=data)

        if section in RESTART_REQUIRED_SECTIONS:
            manager: Manager = app_state.manager
            manager.config_helper.set_restart_required(section)
            result["restart_required"] = True
            result["restart_required_sections"] = manager.config_helper.restart_required_sections

        if section == "modbus_devices" and isinstance(data, list):
            try:
                _apply_entity_labels_to_coordinators(app_state.manager, data)
            except Exception as e:
                _LOGGER.warning("Failed to hot-apply entity labels: %s", e)

        _LOGGER.info(
            "[ROUTE] total PUT /config/%s took %.3fs",
            section, time.perf_counter() - t_route_start,
        )
        return result

    except Exception as e:
        _LOGGER.error(f"Error saving section '{section}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error saving section: {str(e)}") from e


@router.post("/config/reload")
async def reload_configuration(
    sections: list[str] | None = Body(None, description="Optional list of sections to reload"),
):
    """Reload configuration from file."""
    manager: Manager = _get_app_state().manager

    try:
        from boneio.models.events import ConfigReloadEvent

        reload_event = ConfigReloadEvent(sections=sections or ["all"])
        if _websocket_manager:
            await _websocket_manager.broadcast(reload_event.model_dump())

        result = await manager.reload_config(reload_sections=sections)

        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail=result.get("message", "Failed to reload configuration"))

        return result

    except HTTPException:
        raise
    except Exception as e:
        _LOGGER.error(f"Error reloading config: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error reloading config: {str(e)}") from e


@router.get("/config/checksum")
async def get_config_checksum():
    """Return cached SHA256 checksum of all YAML configuration files."""
    if not _checksum_cache["sha256"]:
        _recompute_config_checksum()
    return _checksum_cache
