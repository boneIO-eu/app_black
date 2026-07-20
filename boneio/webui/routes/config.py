"""Configuration routes for BoneIO Web UI."""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import os
import tarfile
import threading
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile

if TYPE_CHECKING:
    from starlette.datastructures import State
from fastapi.responses import StreamingResponse

from boneio.core.config.yaml_util import (
    clear_config_cache,
    get_board_config_path,
    load_config_from_file,
    load_yaml_file,
    merge_board_config,
    normalize_board_name,
    normalize_version,
    update_config_section,
)
from boneio.core.manager import Manager
from boneio.version import __version__
from boneio.webui.action_validation import validate_section_actions as _validate_section_actions

_LOGGER = logging.getLogger(__name__)

def _add_backup_metadata_to_tar(tar: tarfile.TarFile, config_helper):
    import json
    import socket
    
    meta = {
        "effective_serial": config_helper.serial_number,
        "real_serial": config_helper.real_serial,
        "hostname": socket.gethostname(),
        "created_at": datetime.now().isoformat(),
        "version": __version__,
    }
    meta_bytes = json.dumps(meta, indent=2).encode("utf-8")
    
    tarinfo = tarfile.TarInfo(name="_boneio_meta.json")
    tarinfo.size = len(meta_bytes)
    tarinfo.mtime = int(datetime.now().timestamp())
    
    tar.addfile(tarinfo, io.BytesIO(meta_bytes))

def _apply_serial_override_from_tar(fileobj, config_file):
    import json
    try:
        fileobj.seek(0)
    except Exception:
        pass
    effective_serial = None
    try:
        with tarfile.open(fileobj=fileobj, mode="r:gz") as tar:
            try:
                meta_member = tar.getmember("_boneio_meta.json")
                meta_file = tar.extractfile(meta_member)
                if meta_file:
                    meta = json.loads(meta_file.read().decode("utf-8"))
                    effective_serial = meta.get("effective_serial")
            except KeyError:
                pass
    except Exception as e:
        _LOGGER.warning("Could not read backup metadata for override: %s", e)

    if not effective_serial:
        _LOGGER.info("No effective_serial found in backup metadata, skipping override")
        return

    try:
        from boneio.core.config.yaml_util import load_yaml_file, update_config_section
        config_content = load_yaml_file(config_file)
        boneio_data = config_content.get("boneio", {})
        if not isinstance(boneio_data, dict):
            boneio_data = {}
        
        boneio_data["serial_override"] = effective_serial
        update_config_section(config_file, "boneio", boneio_data)
        _LOGGER.info("Successfully applied serial_override: %s", effective_serial)
    except Exception as e:
        _LOGGER.error("Failed to write serial_override to config: %s", e)

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


def invalidate_config_cache():
    """Invalidate route-level config cache and disk validation cache, recompute checksum.

    Clears the route-level mtime cache and the disk .pkl cache, then schedules
    a debounced background rebuild. The rebuild runs 30 seconds after the last
    config change so that rapid edits don't trigger multiple slow Cerberus
    validations (~20s each on BeagleBone).

    IMPORTANT: We intentionally do NOT clear ConfigHelper._config_cache here.
    Setting it to None would cause any concurrent get_config() call (from
    sensor polling, GET /api/config, etc.) to fall through to
    load_config_from_file() → full Cerberus validation (19s on BB), blocking
    MainThread and delaying the actual section reload.  The fast reload path
    (ConfigHelper.reload_config) updates _config_cache atomically in ~5s.
    Stale data for a few seconds is acceptable — it will be overwritten by
    reload_config() before the section reload callbacks run.

    Hot reload uses a fast path (load_yaml_file + merge_board_config) that
    does NOT depend on the disk cache. The disk cache is only an optimization
    for faster application startup.
    """
    _config_cache["data"] = None
    _config_cache["mtime"] = 0
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
    """Schedule a debounced background cache rebuild.

    Each call cancels any previously scheduled rebuild and starts a new
    timer. The actual rebuild runs only after ``_CACHE_REBUILD_DELAY_SECONDS``
    of inactivity (no more config edits).

    Args:
        config_file: Path to the main config YAML file.
    """
    global _cache_rebuild_timer

    with _cache_rebuild_lock:
        # Cancel any pending timer
        if _cache_rebuild_timer is not None:
            _cache_rebuild_timer.cancel()
            _LOGGER.debug("Cancelled pending config cache rebuild timer")

        # Schedule new rebuild
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
    """Execute the actual disk cache rebuild.

    Runs full Cerberus validation and saves the result to ``.cache.pkl``.
    Called by the debounced timer after edits settle.

    Args:
        config_file: Path to the main config YAML file.
    """
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
    """
    Get the latest mtime of config file and all included files.

    Args:
        config_file: Path to main config file.

    Returns:
        Maximum modification time of all config files.
    """
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
    """
    Get parsed configuration data with !include resolved (cached with mtime check).

    Returns:
        Dictionary with parsed config data.
    """
    import time

    try:
        config_file = _get_app_state().yaml_config_file
        current_mtime = _get_config_mtime(config_file)

        if _config_cache["data"] is not None and _config_cache["mtime"] >= current_mtime:
            _LOGGER.debug("Returning cached configuration (mtime unchanged)")
            return {"config": _config_cache["data"]}

        start = time.time()
        # Use ConfigHelper.get_config() to get the fully validated config.
        # This includes board defaults (output_type, kind, mcp_id, pin) from
        # merge_board_config AND Cerberus schema defaults (restore_state: true).
        # Previously used load_yaml_file() which returns raw YAML without
        # board/schema defaults — causing output_type and restore_state to
        # disappear after config cache invalidation (e.g., after saving covers).
        # The frontend already handles TimePeriod objects from the initial cache.
        try:
            manager: Manager = _get_app_state().manager
            source_config = manager.config_helper.get_config()
        except Exception:
            # Fallback to raw YAML + board merge if manager not ready
            source_config = load_yaml_file(config_file)
            try:
                source_config = merge_board_config(source_config)
            except Exception as merge_err:
                _LOGGER.warning("Failed to merge board config for API response: %s", merge_err)

        # Shallow copy top-level dict so we can replace list values without
        # mutating ConfigHelper's internal cache.  Only sections that receive
        # ID enrichment below need their items shallow-copied; everything
        # else is shared by reference (zero-cost).
        config_data = dict(source_config)

        # Enrich output entities with generated IDs if not explicitly defined
        # Strategy: explicit 'id' > 'boneio_output' > 'name' (slugified)
        if "output" in config_data and isinstance(config_data["output"], list):
            import re

            enriched: list[dict] = []
            for output in config_data["output"]:
                if not output.get("id"):
                    out = dict(output)  # shallow copy — only this item
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

        # Enrich cover entities with generated IDs if not explicitly defined
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

        # Enrich output_group entities with generated IDs if not explicitly defined
        # Strategy: explicit 'id' > 'name' (slugified)
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

        # Normalize legacy flat action keys (actions_single, actions_double, etc.)
        # into nested 'actions' dict for event section entries.
        # Old quick-action code wrote flat keys; schema expects actions.single, etc.
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
    """Hot-apply entity_labels from saved config to running Modbus coordinators.

    Matches each device config entry to its running coordinator by ID
    and calls update_entity_labels so changes take effect immediately.

    Args:
        manager: Application manager instance.
        devices_data: List of device config dicts (as saved to YAML).
    """
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
    """
    Update content of a configuration section.

    Args:
        section: Name of the config section (e.g., 'mqtt', 'output_group').
        data: Section data - dict or list depending on section type.

    Returns:
        Status response with optional restart_required flag.
    """
    RESTART_REQUIRED_SECTIONS = {
        "boneio",
        "mqtt",
        "lox_udp",
        "web",
        "modbus",
        "mcp23017",
        "lm75",
        "ina219",
        "mcp9808",
        "can",
    }

    if section in ("event", "binary_sensor") and isinstance(data, list):
        errors = _validate_section_actions(section, data)
        if errors:
            raise HTTPException(
                status_code=422,
                detail={"message": "Invalid action configuration", "errors": errors},
            )
        # Strip deprecated gpio_mode — now handled by kernel overlay
        for entry in data:
            entry.pop("gpio_mode", None)

    # Validate lox_udp host as valid IPv4 or hostname when enabled
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

    try:
        import time as _time

        t_route_start = _time.perf_counter()

        app_state = _get_app_state()
        # Offload synchronous YAML read/write/dump to a thread pool.
        # On BeagleBone ARM, large configs (e.g. 7 WLED devices with 200+
        # effects each = 64KB YAML) can take 3-5 seconds to serialize,
        # blocking the entire async event loop and causing frontend timeouts.
        import asyncio
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            update_config_section,
            app_state.yaml_config_file,
            section,
            data,
        )
        t_after_executor = _time.perf_counter()
        _LOGGER.info(
            "[ROUTE] run_in_executor took %.3fs for section='%s'",
            t_after_executor - t_route_start, section,
        )

        if result["status"] == "error":
            raise HTTPException(status_code=500, detail=result["message"])

        invalidate_config_cache()

        if section in RESTART_REQUIRED_SECTIONS:
            manager: Manager = app_state.manager
            manager.config_helper.set_restart_required(section)
            result["restart_required"] = True
            result["restart_required_sections"] = manager.config_helper.restart_required_sections

        # Hot-apply entity_labels to running Modbus coordinators
        if section == "modbus_devices" and isinstance(data, list):
            try:
                _apply_entity_labels_to_coordinators(app_state.manager, data)
            except Exception as e:
                _LOGGER.warning("Failed to hot-apply entity labels: %s", e)

        _LOGGER.info(
            "[ROUTE] total PUT /config/%s took %.3fs",
            section, _time.perf_counter() - t_route_start,
        )
        return result

    except Exception as e:
        _LOGGER.error(f"Error saving section '{section}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error saving section: {str(e)}") from e


@router.post("/config/reload")
async def reload_configuration(
    sections: list[str] | None = Body(None, description="Optional list of sections to reload"),
):
    """
    Reload configuration from file.

    Supports hot-reloading of: output, cover, input, event, binary_sensor, modbus_devices, sensor, oled.

    Args:
        sections: Optional list of section names to reload.

    Returns:
        Status of reload operation.
    """
    manager: Manager = _get_app_state().manager

    try:
        # Send ConfigReloadEvent BEFORE reload starts
        # Frontend will clear old states and wait for fresh ones
        from boneio.models.events import ConfigReloadEvent

        reload_event = ConfigReloadEvent(sections=sections or ["all"])
        if _websocket_manager:
            await _websocket_manager.broadcast(reload_event.model_dump())

        # Execute reload - each manager's reload_* method broadcasts states
        result = await manager.reload_config(reload_sections=sections)

        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail=result.get("message", "Failed to reload configuration"))

        return result

    except HTTPException:
        raise
    except Exception as e:
        _LOGGER.error(f"Error reloading config: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error reloading config: {str(e)}") from e


@router.post("/config/remove_ha_discovery")
async def remove_ha_discovery():
    """Remove all Home Assistant discovery entries for this device.

    Publishes empty retained payloads on every cached discovery topic
    so that Home Assistant removes all entities and devices registered
    by this boneIO instance.  The internal autodiscovery cache is
    cleared afterwards.

    Returns:
        Status with count of removed topics.
    """
    manager: Manager = _get_app_state().manager
    config_helper = manager.config_helper

    if not config_helper.ha_discovery:
        raise HTTPException(
            status_code=400,
            detail="HA Discovery is not enabled",
        )

    removed = 0
    for ha_type in config_helper.ha_types:
        topics = dict(config_helper._autodiscovery_messages.get(ha_type, {}))
        for topic in topics:
            _LOGGER.info("Removing HA discovery topic: %s", topic)
            manager.send_message(topic=topic, payload=None, retain=True)
            removed += 1
        config_helper.clear_autodiscovery_type(ha_type)

    # Also publish offline status so HA marks entities as unavailable immediately
    manager.send_message(
        topic=f"{config_helper.topic_prefix}/state",
        payload="offline",
        retain=False,
    )

    _LOGGER.info("Removed %d HA discovery topics", removed)
    return {
        "status": "success",
        "removed_topics": removed,
        "message": f"Removed {removed} discovery entries from Home Assistant.",
    }


@router.post("/config/resend_ha_discovery")
async def resend_ha_discovery():
    """Remove and re-send all Home Assistant discovery entries.

    First publishes empty retained payloads to clear all existing
    discovery topics in HA, then re-publishes the current cached
    payloads so HA re-creates all devices and entities from scratch.

    Useful after changing ha_child_devices, areas, or other settings
    that affect device grouping in Home Assistant.

    Returns:
        Status with counts of removed and re-sent topics.
    """
    manager: Manager = _get_app_state().manager
    config_helper = manager.config_helper

    if not config_helper.ha_discovery:
        raise HTTPException(
            status_code=400,
            detail="HA Discovery is not enabled",
        )

    # 1. Collect all current discovery messages before clearing
    all_messages: list[tuple[str, dict]] = []
    for ha_type in config_helper.ha_types:
        for topic, entry in config_helper._autodiscovery_messages.get(ha_type, {}).items():
            all_messages.append((topic, entry.get("payload")))

    # 2. Send empty retained payloads to remove all entries from HA
    removed = 0
    for topic, _ in all_messages:
        manager.send_message(topic=topic, payload=None, retain=True)
        removed += 1

    # 3. Re-send all cached discovery payloads
    resent = 0
    for topic, payload in all_messages:
        if payload:
            manager.send_message(topic=topic, payload=payload, retain=True)
            resent += 1

    # 4. Re-publish all entity states after a short delay.
    #    HA needs time to process discovery before receiving states.
    async def _delayed_republish():
        await asyncio.sleep(2)
        await manager.republish_all_entity_states()

    asyncio.ensure_future(_delayed_republish())

    _LOGGER.info("HA Discovery resend: removed %d, re-sent %d topics", removed, resent)
    return {
        "status": "success",
        "removed_topics": removed,
        "resent_topics": resent,
        "message": f"Removed {removed} and re-sent {resent} discovery entries.",
    }


@router.get("/config/download")
async def download_config():
    """
    Download current configuration as a tar.gz archive.

    Returns:
        StreamingResponse with compressed config archive.
    """
    config_file = _get_app_state().yaml_config_file
    config_dir = Path(config_file).parent

    buffer = io.BytesIO()

    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for pattern in ["*.yaml", "*.yml"]:
            for yaml_file in config_dir.glob(pattern):
                if yaml_file.is_file():
                    arcname = yaml_file.name
                    tar.add(str(yaml_file), arcname=arcname)
                    _LOGGER.debug(f"Added {arcname} to config archive")

        for subdir in config_dir.iterdir():
            if subdir.is_dir() and not subdir.name.startswith("."):
                for pattern in ["*.yaml", "*.yml"]:
                    for yaml_file in subdir.glob(pattern):
                        if yaml_file.is_file():
                            arcname = f"{subdir.name}/{yaml_file.name}"
                            tar.add(str(yaml_file), arcname=arcname)
                            _LOGGER.debug(f"Added {arcname} to config archive")

        manager: Manager = _get_app_state().manager
        _add_backup_metadata_to_tar(tar, manager.config_helper)

    buffer.seek(0)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    manager: Manager = _get_app_state().manager
    device_name = manager.config_helper.serial_number
    filename = f"{device_name}_config_{timestamp}.tar.gz"

    _LOGGER.info(f"Downloading config archive: {filename}")

    return StreamingResponse(
        buffer, media_type="application/gzip", headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/config/checksum")
async def get_config_checksum():
    """
    Return cached SHA256 checksum of all YAML configuration files.

    The checksum is recomputed automatically after every config change.
    On first request it is computed lazily if not yet available.

    Returns:
        Dictionary with sha256 hex string and file_count.
    """
    if not _checksum_cache["sha256"]:
        _recompute_config_checksum()
    return _checksum_cache


@router.post("/config/restore")
async def restore_config(file: UploadFile = File(...), override_serial: bool = Form(False)):
    """
    Restore configuration from a tar.gz archive.

    Creates a backup of current config before restoring.

    Args:
        file: Uploaded tar.gz archive.

    Returns:
        Status response with list of restored files.
    """
    config_file = _get_app_state().yaml_config_file
    config_dir = Path(config_file).parent

    try:
        if not file.filename or not file.filename.endswith((".tar.gz", ".tgz")):
            return {"status": "error", "message": "Invalid file type. Please upload a .tar.gz or .tgz file."}

        contents = await file.read()
        buffer = io.BytesIO(contents)

        # Create backup with version in filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = config_dir / "backups"
        backup_dir.mkdir(exist_ok=True)
        backup_path = backup_dir / f"config_backup_v{__version__}_{timestamp}.tar.gz"

        with tarfile.open(backup_path, mode="w:gz") as tar:
            for pattern in ["*.yaml", "*.yml"]:
                for yaml_file in config_dir.glob(pattern):
                    if yaml_file.is_file():
                        tar.add(str(yaml_file), arcname=yaml_file.name)

            for subdir in config_dir.iterdir():
                if subdir.is_dir() and not subdir.name.startswith(".") and subdir.name != "backups":
                    for pattern in ["*.yaml", "*.yml"]:
                        for yaml_file in subdir.glob(pattern):
                            if yaml_file.is_file():
                                tar.add(str(yaml_file), arcname=f"{subdir.name}/{yaml_file.name}")
            
            _add_backup_metadata_to_tar(tar, _get_app_state().manager.config_helper)

        _LOGGER.info(f"Created backup before restore: {backup_path}")

        # Extract and restore
        restored_files = []
        with tarfile.open(fileobj=buffer, mode="r:gz") as tar:
            members = tar.getmembers()
            for member in members:
                if ".." in member.name or member.name.startswith("/"):
                    return {"status": "error", "message": f"Invalid file path in archive: {member.name}"}

                if not (member.name.endswith(".yaml") or member.name.endswith(".yml")):
                    _LOGGER.warning(f"Skipping non-YAML file: {member.name}")
                    continue

            for member in members:
                if member.name.endswith(".yaml") or member.name.endswith(".yml"):
                    target_path = config_dir / member.name
                    target_path.parent.mkdir(parents=True, exist_ok=True)

                    source = tar.extractfile(member)
                    if source is None:
                        _LOGGER.warning(f"Could not extract {member.name}")
                        continue

                    with source, open(target_path, "wb") as target:
                        target.write(source.read())

                    restored_files.append(member.name)
                    _LOGGER.info(f"Restored: {member.name}")

        if override_serial:
            _apply_serial_override_from_tar(io.BytesIO(contents), config_file)

        invalidate_config_cache()

        # Validate
        try:
            load_config_from_file(config_file=_get_app_state().yaml_config_file)
            validation_status = "success"
            validation_message = "Configuration is valid"
        except Exception as e:
            validation_status = "warning"
            validation_message = f"Configuration restored but validation failed: {str(e)}"
            _LOGGER.warning(f"Restored config validation failed: {e}")

        return {
            "status": "success",
            "message": f"Restored {len(restored_files)} files from backup",
            "restored_files": restored_files,
            "backup_path": str(backup_path),
            "validation_status": validation_status,
            "validation_message": validation_message,
            "restart_required": True,
        }

    except tarfile.TarError as e:
        _LOGGER.error(f"Failed to extract archive: {e}")
        return {"status": "error", "message": f"Failed to extract archive: {str(e)}"}
    except Exception as e:
        _LOGGER.error(f"Failed to restore config: {e}")
        return {"status": "error", "message": f"Failed to restore configuration: {str(e)}"}


@router.get("/interlock-groups")
async def get_interlock_groups():
    """
    Get list of all registered interlock group names.

    Also scans the YAML configuration for groups that may not yet be
    registered at runtime (e.g. after config save before reload).

    Returns:
        List of unique interlock group names.
    """
    groups: set[str] = set()

    # 1. Runtime groups from the interlock manager
    manager = _get_app_state().manager
    if manager and hasattr(manager, "outputs"):
        output_manager = manager.outputs
        if output_manager and hasattr(output_manager, "_interlock_manager"):
            for g in output_manager._interlock_manager.get_all_groups():
                groups.add(g)

    # 2. Config-based groups (covers saved-but-not-yet-reloaded state)
    try:
        config = load_config_from_file(config_file=_get_app_state().yaml_config_file)
        for section_key in ("output", "remote_outputs"):
            for item in (config or {}).get(section_key, []):
                ig = item.get("interlock_group")
                if isinstance(ig, list):
                    for g in ig:
                        if g:
                            groups.add(g)
                elif isinstance(ig, str) and ig:
                    groups.add(ig)
    except Exception:
        pass  # Config may be invalid — runtime groups are enough

    return {"groups": sorted(groups)}


@router.get("/files")
async def list_files(path: str | None = None):
    """
    List files in the config directory.

    Args:
        path: Optional subdirectory path.

    Returns:
        Tree structure of YAML files.
    """
    config_dir = Path(_get_app_state().yaml_config_file).parent
    base_dir = config_dir / path if path else config_dir

    if not os.path.exists(base_dir):
        raise HTTPException(status_code=404, detail="Path not found")

    if not os.path.isdir(base_dir):
        raise HTTPException(status_code=400, detail="Path is not a directory")

    def scan_directory(directory: Path):
        items = []
        for entry in os.scandir(directory):
            if entry.name == ".git" or entry.name.startswith("venv"):
                continue
            relative_path = os.path.relpath(entry.path, config_dir)
            if entry.is_dir():
                children = scan_directory(Path(entry.path))
                if children:
                    items.append({"name": entry.name, "path": relative_path, "type": "directory", "children": children})
            elif entry.is_file():
                if entry.name.endswith((".yaml", ".yml")):
                    items.append({"name": entry.name, "path": relative_path, "type": "file"})
        return items

    try:
        items = [{"name": "config", "path": "", "type": "directory", "children": scan_directory(base_dir)}]
        return {"items": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/files/{file_path:path}")
async def get_file_content(file_path: str):
    """
    Get content of a file.

    Args:
        file_path: Relative path to file.

    Returns:
        File content as string.
    """
    config_dir = Path(_get_app_state().yaml_config_file).parent
    full_path = os.path.join(config_dir, file_path)

    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="File not found")

    if not os.path.isfile(full_path):
        raise HTTPException(status_code=400, detail="Path is not a file")

    if not full_path.endswith((".yaml", ".yml", ".json")):
        raise HTTPException(status_code=400, detail="Invalid file type")

    try:
        with open(full_path) as f:
            content = f.read()
        return {"content": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.put("/files/{file_path:path}")
async def update_file_content(file_path: str, content: dict = Body(...)):
    """
    Update content of a file.

    Args:
        file_path: Relative path to file.
        content: Dictionary with 'content' key containing file content.

    Returns:
        Status response.
    """
    config_dir = Path(_get_app_state().yaml_config_file).parent
    full_path = os.path.join(config_dir, file_path)

    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="File not found")

    if not os.path.isfile(full_path):
        raise HTTPException(status_code=400, detail="Path is not a file")

    if not full_path.endswith((".yaml", ".yml", ".json")):
        raise HTTPException(status_code=400, detail="Invalid file type")

    try:
        with open(full_path, "w") as f:
            f.write(content["content"])
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/config/validate_device_type_change")
async def validate_device_type_change(request: dict = Body(...)):
    """
    Validate if changing device_type will cause compatibility issues.

    Checks if current boneio_output/boneio_input references are compatible
    with the new device type's output_mapping/input_mapping.

    Args:
        request: Dictionary with:
            - new_device_type: Target device type
            - version: Hardware version (default: 0.8)

    Returns:
        Dictionary with:
            - compatible: True if all references are compatible
            - incompatible_outputs: List of incompatible output references
            - incompatible_inputs: List of incompatible input references
            - available_example_files: List of example config files for new type
    """
    new_device_type = request.get("new_device_type")
    version = request.get("version", "0.8")

    if not new_device_type:
        raise HTTPException(status_code=400, detail="new_device_type is required")

    # Normalize names
    normalized_type = normalize_board_name(new_device_type)
    normalized_version = normalize_version(version)

    # Load current config
    try:
        config_file = _get_app_state().yaml_config_file
        current_config = load_config_from_file(config_file)
    except Exception as e:
        _LOGGER.error("Failed to load current config: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to load config: {e}") from e

    # Load new board config
    try:
        board_file = get_board_config_path(f"output_{normalized_type}", normalized_version)
        input_file = get_board_config_path("input", normalized_version)
        board_config = load_yaml_file(board_file)
        input_config = load_yaml_file(input_file)
    except Exception as e:
        _LOGGER.error("Failed to load board config for %s: %s", normalized_type, e)
        raise HTTPException(
            status_code=400, detail=f"Board config not found for {new_device_type} version {version}"
        ) from e

    output_mapping = board_config.get("output_mapping", {})
    input_mapping = input_config.get("input_mapping", {})

    # Check incompatible outputs
    incompatible_outputs = []
    for output in (current_config or {}).get("output", []):
        boneio_output = output.get("boneio_output")
        if boneio_output and boneio_output.lower() not in output_mapping:
            incompatible_outputs.append(
                {
                    "boneio_output": boneio_output,
                    "id": output.get("id", boneio_output),
                    "name": output.get("name", output.get("id", boneio_output)),
                }
            )

    # Check incompatible inputs (events and binary_sensors)
    incompatible_inputs = []
    config_data = current_config or {}
    for section in ["event", "binary_sensor"]:
        for input_item in config_data.get(section, []):
            boneio_input = input_item.get("boneio_input")
            if boneio_input and boneio_input.lower() not in input_mapping:
                incompatible_inputs.append(
                    {
                        "boneio_input": boneio_input,
                        "id": input_item.get("id", boneio_input),
                        "section": section,
                    }
                )

    # Get available example files for this device type (relative to this file: boneio/webui/routes/config.py)
    boneio_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    # Convert normalized_type back to example_config folder name format (24_16 -> 24x16)
    example_folder_name = normalized_type.replace("_", "x")
    example_dir = os.path.join(boneio_path, "example_config", example_folder_name)

    available_example_files = []
    if os.path.isdir(example_dir):
        for filename in os.listdir(example_dir):
            if filename.endswith(".yaml"):
                # Categorize files
                base_name = filename.replace(".yaml", "")
                if "output" in base_name.lower():
                    category = "output"
                elif "cover" in base_name.lower() and "output" not in base_name.lower():
                    category = "cover"
                elif "event" in base_name.lower():
                    category = "event"
                elif "binary_sensor" in base_name.lower():
                    category = "binary_sensor"
                elif "mqtt" in base_name.lower():
                    category = "mqtt"
                elif "config" in base_name.lower():
                    category = "config"
                elif "adc" in base_name.lower():
                    category = "adc"
                else:
                    category = "other"

                available_example_files.append(
                    {
                        "filename": filename,
                        "category": category,
                        "path": os.path.join(example_dir, filename),
                    }
                )

    compatible = len(incompatible_outputs) == 0 and len(incompatible_inputs) == 0

    return {
        "compatible": compatible,
        "incompatible_outputs": incompatible_outputs,
        "incompatible_inputs": incompatible_inputs,
        "available_example_files": available_example_files,
        "new_device_type": new_device_type,
        "normalized_type": normalized_type,
    }


@router.get("/config/backups")
async def list_config_backups():
    """
    List available configuration backups from disk.

    Returns:
        List of backup information with timestamps and file counts.
    """
    config_file = _get_app_state().yaml_config_file
    config_dir = Path(config_file).parent
    backup_dir = config_dir / "backups"

    if not backup_dir.exists():
        return {"backups": []}

    backups = []
    for backup_file in sorted(backup_dir.glob("config_backup_*.tar.gz"), reverse=True):
        try:
            # Parse filename: config_backup_v1.0.0dev26_20260106_112345.tar.gz
            filename_parts = backup_file.stem.replace("config_backup_", "")

            # Extract version if present
            version = None
            timestamp_str = filename_parts
            if filename_parts.startswith("v"):
                # Format: vX.X.X_YYYYMMDD_HHMMSS
                parts = filename_parts.split("_", 1)
                if len(parts) == 2:
                    version = parts[0][1:]  # Remove 'v' prefix
                    timestamp_str = parts[1]

            # Parse timestamp: YYYYMMDD_HHMMSS
            formatted_timestamp = timestamp_str
            if len(timestamp_str) == 15 and timestamp_str[8] == "_":
                date_part = timestamp_str[:8]
                time_part = timestamp_str[9:]
                formatted_timestamp = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]} {time_part[:2]}:{time_part[2:4]}:{time_part[4:6]}"

            # Count files in backup
            file_count = 0
            try:
                with tarfile.open(backup_file, "r:gz") as tar:
                    file_count = len(tar.getmembers())
            except Exception:
                pass

            backups.append(
                {
                    "path": str(backup_file),
                    "filename": backup_file.name,
                    "version": version or "unknown",
                    "timestamp": formatted_timestamp,
                    "timestamp_raw": timestamp_str,
                    "size": backup_file.stat().st_size,
                    "file_count": file_count,
                }
            )
        except Exception as e:
            _LOGGER.warning(f"Error processing backup {backup_file}: {e}")
            continue

    return {"backups": backups}


@router.post("/config/restore_backup")
async def restore_config_backup(
    backup_path: str = Body(..., embed=True),
    override_serial: bool = Body(False, embed=True),
):
    """
    Restore configuration from a backup file on disk.

    Args:
        backup_path: Path to the backup file to restore.

    Returns:
        Status response with list of restored files.
    """
    config_file = _get_app_state().yaml_config_file
    config_dir = Path(config_file).parent
    backup_file = Path(backup_path)

    # Security: ensure backup is in the backups directory
    backup_dir = config_dir / "backups"
    try:
        backup_file = backup_file.resolve()
        backup_dir = backup_dir.resolve()
        if not str(backup_file).startswith(str(backup_dir)):
            return {"status": "error", "message": "Invalid backup path"}
    except Exception:
        return {"status": "error", "message": "Invalid backup path"}

    if not backup_file.exists():
        return {"status": "error", "message": "Backup file not found"}

    try:
        # Create a new backup before restoring
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_backup_path = backup_dir / f"config_backup_v{__version__}_{timestamp}.tar.gz"

        with tarfile.open(new_backup_path, mode="w:gz") as tar:
            for pattern in ["*.yaml", "*.yml"]:
                for yaml_file in config_dir.glob(pattern):
                    if yaml_file.is_file():
                        tar.add(str(yaml_file), arcname=yaml_file.name)

            for subdir in config_dir.iterdir():
                if subdir.is_dir() and not subdir.name.startswith(".") and subdir.name != "backups":
                    for pattern in ["*.yaml", "*.yml"]:
                        for yaml_file in subdir.glob(pattern):
                            if yaml_file.is_file():
                                tar.add(str(yaml_file), arcname=f"{subdir.name}/{yaml_file.name}")
            
            _add_backup_metadata_to_tar(tar, _get_app_state().manager.config_helper)

        _LOGGER.info(f"Created backup before restore: {new_backup_path}")

        # Restore from selected backup
        restored_files = []
        with tarfile.open(backup_file, mode="r:gz") as tar:
            members = tar.getmembers()
            for member in members:
                if ".." in member.name or member.name.startswith("/"):
                    continue

                if member.name.endswith((".yaml", ".yml")):
                    target_path = config_dir / member.name
                    target_path.parent.mkdir(parents=True, exist_ok=True)

                    source = tar.extractfile(member)
                    if source is None:
                        continue

                    with source, open(target_path, "wb") as target:
                        target.write(source.read())

                    restored_files.append(member.name)
                    _LOGGER.info(f"Restored: {member.name}")

        if override_serial:
            with open(backup_file, "rb") as f:
                _apply_serial_override_from_tar(f, config_file)

        invalidate_config_cache()

        # Validate
        try:
            load_config_from_file(config_file=_get_app_state().yaml_config_file)
            validation_status = "success"
            validation_message = "Configuration is valid"
        except Exception as e:
            validation_status = "warning"
            validation_message = f"Configuration restored but validation failed: {str(e)}"
            _LOGGER.warning(f"Restored config validation failed: {e}")

        return {
            "status": "success",
            "message": f"Restored {len(restored_files)} files from backup",
            "restored_files": restored_files,
            "backup_created": str(new_backup_path),
            "validation_status": validation_status,
            "validation_message": validation_message,
            "restart_required": True,
        }

    except tarfile.TarError as e:
        _LOGGER.error(f"Failed to extract backup: {e}")
        return {"status": "error", "message": f"Failed to extract backup: {str(e)}"}
    except Exception as e:
        _LOGGER.error(f"Failed to restore backup: {e}")
        return {"status": "error", "message": f"Failed to restore backup: {str(e)}"}


MAX_BACKUPS = 10


@router.post("/config/create_backup")
async def create_config_backup():
    """
    Create a configuration backup on disk with version in filename.
    Automatically removes oldest backups if more than MAX_BACKUPS exist.

    Returns:
        Status response with backup path.
    """
    config_file = _get_app_state().yaml_config_file
    config_dir = Path(config_file).parent

    try:
        backup_dir = config_dir / "backups"
        backup_dir.mkdir(exist_ok=True)

        # Clean up old backups BEFORE creating new one - keep only MAX_BACKUPS - 1
        all_backups = sorted(backup_dir.glob("config_backup_*.tar.gz"), reverse=True)
        _LOGGER.debug(f"Found {len(all_backups)} existing backups, max allowed: {MAX_BACKUPS}")

        if len(all_backups) >= MAX_BACKUPS:
            # Remove oldest backups to make room for new one
            # Sorting by filename (reverse=True) puts newest first (timestamp in filename)
            backups_to_remove = all_backups[MAX_BACKUPS - 1 :]
            _LOGGER.info(f"Removing {len(backups_to_remove)} old backups to maintain limit of {MAX_BACKUPS}")
            for old_backup in backups_to_remove:
                try:
                    old_backup.unlink()
                    _LOGGER.info(f"Removed old backup: {old_backup.name}")
                except Exception as e:
                    _LOGGER.warning(f"Failed to remove old backup {old_backup.name}: {e}")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"config_backup_v{__version__}_{timestamp}.tar.gz"

        with tarfile.open(backup_path, mode="w:gz") as tar:
            for pattern in ["*.yaml", "*.yml"]:
                for yaml_file in config_dir.glob(pattern):
                    if yaml_file.is_file():
                        tar.add(str(yaml_file), arcname=yaml_file.name)

            for subdir in config_dir.iterdir():
                if subdir.is_dir() and not subdir.name.startswith(".") and subdir.name != "backups":
                    for pattern in ["*.yaml", "*.yml"]:
                        for yaml_file in subdir.glob(pattern):
                            if yaml_file.is_file():
                                tar.add(str(yaml_file), arcname=f"{subdir.name}/{yaml_file.name}")

            _add_backup_metadata_to_tar(tar, _get_app_state().manager.config_helper)

        _LOGGER.info(f"Created config backup: {backup_path}")

        # Final count for response
        final_count = len(list(backup_dir.glob("config_backup_*.tar.gz")))
        _LOGGER.debug(f"Total backups after creation: {final_count}")

        # Count files
        file_count = 0
        with tarfile.open(backup_path, "r:gz") as tar:
            file_count = len(tar.getmembers())

        return {
            "status": "success",
            "message": f"Backup created with {file_count} files",
            "backup_path": str(backup_path),
            "filename": backup_path.name,
            "version": __version__,
            "file_count": file_count,
        }

    except Exception as e:
        _LOGGER.error(f"Failed to create backup: {e}")
        return {"status": "error", "message": f"Failed to create backup: {str(e)}"}


@router.get("/config/download_backup")
async def download_config_backup(backup_path: str):
    """
    Download a specific configuration backup from disk.

    Args:
        backup_path: Path to the backup file.

    Returns:
        StreamingResponse with backup file.
    """
    config_file = _get_app_state().yaml_config_file
    config_dir = Path(config_file).parent
    backup_file = Path(backup_path)

    # Security: ensure backup is in the backups directory
    backup_dir = config_dir / "backups"
    try:
        backup_file = backup_file.resolve()
        backup_dir = backup_dir.resolve()
        if not str(backup_file).startswith(str(backup_dir)):
            raise HTTPException(status_code=403, detail="Invalid backup path")
    except Exception as e:
        raise HTTPException(status_code=403, detail="Invalid backup path") from e

    if not backup_file.exists():
        raise HTTPException(status_code=404, detail="Backup file not found")

    _LOGGER.info(f"Downloading backup: {backup_file.name}")

    return StreamingResponse(
        open(backup_file, "rb"),
        media_type="application/gzip",
        headers={"Content-Disposition": f"attachment; filename={backup_file.name}"},
    )


@router.delete("/config/delete_backup")
async def delete_config_backup(backup_path: str = Body(..., embed=True)):
    """
    Delete a specific configuration backup from disk.

    Args:
        backup_path: Path to the backup file to delete.

    Returns:
        Status response.
    """
    config_file = _get_app_state().yaml_config_file
    config_dir = Path(config_file).parent
    backup_file = Path(backup_path)

    # Security: ensure backup is in the backups directory
    backup_dir = config_dir / "backups"
    try:
        backup_file = backup_file.resolve()
        backup_dir = backup_dir.resolve()
        if not str(backup_file).startswith(str(backup_dir)):
            return {"status": "error", "message": "Invalid backup path"}
    except Exception:
        return {"status": "error", "message": "Invalid backup path"}

    if not backup_file.exists():
        return {"status": "error", "message": "Backup file not found"}

    try:
        backup_file.unlink()
        _LOGGER.info(f"Deleted backup: {backup_file.name}")

        return {"status": "success", "message": f"Backup {backup_file.name} deleted successfully"}
    except Exception as e:
        _LOGGER.error(f"Failed to delete backup: {e}")
        return {"status": "error", "message": f"Failed to delete backup: {str(e)}"}


@router.get("/config/lox-template")
async def get_lox_template():
    """Generate and download Lox Config XML template.

    The template contains Virtual UDP Output commands (Miniserver → BoneIO)
    and Virtual UDP Input commands (BoneIO → Miniserver) for all configured
    outputs, covers, and output groups.

    Returns:
        XML file download as attachment.
    """
    from boneio.integration.lox_template import generate_lox_template

    manager: Manager = _get_app_state().manager

    try:
        xml_content = generate_lox_template(manager)
        serial = manager.config_helper.serial_number or "boneio"
        filename = f"boneio_{serial}_lox_template.xml"

        return StreamingResponse(
            io.BytesIO(xml_content.encode("utf-8")),
            media_type="application/xml",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except Exception as e:
        _LOGGER.error("Failed to generate Lox template: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate Lox template: {e}") from e


@router.get("/config/lox-commands")
async def get_lox_commands():
    """Get JSON summary of all available Lox UDP commands.

    Returns a structured list of all commands BoneIO accepts (for controlling
    outputs and covers) and all status messages BoneIO sends.

    Returns:
        JSON with commands and status_messages arrays.
    """
    from boneio.integration.lox_template import generate_lox_summary

    manager: Manager = _get_app_state().manager

    try:
        return generate_lox_summary(manager)
    except Exception as e:
        _LOGGER.error("Failed to generate Lox commands: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate Lox commands: {e}") from e


@router.post("/config/quick-action")
async def add_quick_action(payload: dict = Body(...)):
    """Add a single action to an input's click type without full section save.

    This is a simplified endpoint for the Quick Action Sheet UI.
    It reads the current config, finds the input by entity_id, adds or appends
    the action to the specified click type, and saves the section.

    Expected payload::

        {
            "entity_id": "in_01",
            "click_type": "single",        # single/double/long/pressed/released
            "action_type": "output",        # output/cover
            "output_id": "OUT_01",          # for output type
            "cover_id": "cover_01",         # for cover type
            "action": "TOGGLE"              # TOGGLE/ON/OFF/OPEN/CLOSE/STOP
        }

    Returns:
        Status response indicating success or failure.
    """
    entity_id = payload.get("entity_id", "").strip()
    click_type = payload.get("click_type", "").strip()
    action_type = payload.get("action_type", "output").strip()
    output_id = payload.get("output_id", "").strip()
    cover_id = payload.get("cover_id", "").strip()
    action = payload.get("action", "TOGGLE").strip()
    remote_device = payload.get("remote_device", "").strip()
    boneio_id = payload.get("boneio_id", "").strip()
    topic = payload.get("topic", "").strip()
    mqtt_msg = payload.get("action_mqtt_msg", "").strip()

    if not entity_id:
        raise HTTPException(status_code=422, detail="entity_id is required")
    if not click_type:
        raise HTTPException(status_code=422, detail="click_type is required")

    valid_click_types = {
        "single", "double", "triple", "long",
        "pressed", "released",
        "double_then_long", "single_then_long", "double_then_single",
    }
    if click_type not in valid_click_types:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid click_type: '{click_type}'. Must be one of {sorted(valid_click_types)}",
        )

    valid_action_types = {
        "output", "cover", "remote_output", "remote_cover",
        "mqtt", "output_over_mqtt", "cover_over_mqtt",
    }
    if action_type not in valid_action_types:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid action_type: '{action_type}'. Must be one of {sorted(valid_action_types)}",
        )

    # Build the action dict based on action_type
    new_action: dict = {"action": action_type}

    if action_type == "output":
        if not output_id:
            raise HTTPException(status_code=422, detail="output_id is required for output action")
        new_action.update({"boneio_output": output_id, "action_output": action})

    elif action_type == "cover":
        if not cover_id:
            raise HTTPException(status_code=422, detail="cover_id is required for cover action")
        new_action.update({"boneio_cover": cover_id, "action_cover": action})

    elif action_type == "remote_output":
        if not remote_device or not output_id:
            raise HTTPException(status_code=422, detail="remote_device and output_id are required for remote_output")
        new_action.update({"remote_device": remote_device, "output_id": output_id, "action_output": action})

    elif action_type == "remote_cover":
        if not remote_device or not cover_id:
            raise HTTPException(status_code=422, detail="remote_device and cover_id are required for remote_cover")
        new_action.update({"remote_device": remote_device, "cover_id": cover_id, "action_cover": action})

    elif action_type == "mqtt":
        if not topic:
            raise HTTPException(status_code=422, detail="topic is required for mqtt action")
        new_action.update({"topic": topic, "action_mqtt_msg": mqtt_msg})

    elif action_type == "output_over_mqtt":
        if not boneio_id or not output_id:
            raise HTTPException(status_code=422, detail="boneio_id and output_id are required for output_over_mqtt")
        new_action.update({"boneio_id": boneio_id, "boneio_output": output_id, "action_output": action})

    elif action_type == "cover_over_mqtt":
        if not boneio_id or not cover_id:
            raise HTTPException(status_code=422, detail="boneio_id and cover_id are required for cover_over_mqtt")
        new_action.update({"boneio_id": boneio_id, "boneio_cover": cover_id, "action_cover": action})

    try:
        app_state = _get_app_state()
        # Use raw YAML load (fast) — no need for Cerberus validation to append an action.
        # load_config_from_file can take 19s on cache miss due to full validation.
        config = load_yaml_file(app_state.yaml_config_file)

        # Determine which section the input belongs to
        # Search in event, binary_sensor, and remote_inputs
        section = None
        input_index = None
        for sec_name in ("event", "binary_sensor", "remote_inputs"):
            entries = config.get(sec_name, [])
            if isinstance(entries, list):
                for idx, entry in enumerate(entries):
                    if isinstance(entry, dict):
                        eid = entry.get("id", entry.get("pin", ""))
                        boneio_in = entry.get("boneio_input", "")
                        if (
                            str(eid) == entity_id
                            or str(eid).lower() == entity_id.lower()
                            or str(boneio_in).lower() == entity_id.lower()
                        ):
                            section = sec_name
                            input_index = idx
                            break
            if section:
                break

        if section is None or input_index is None:
            _LOGGER.warning(
                "Quick action: input '%s' not found. Available sections: %s",
                entity_id,
                {s: len(config.get(s, [])) for s in ("event", "binary_sensor", "remote_inputs")},
            )
            raise HTTPException(
                status_code=404,
                detail=f"Input '{entity_id}' not found in event, binary_sensor, or remote_inputs sections",
            )

        entries = config[section]
        entry = entries[input_index]

        # Normalize legacy flat action keys (actions_single → actions.single)
        if section in ("event", "remote_inputs"):
            for act_type in (
                "single", "double", "triple", "long",
                "double_then_long", "single_then_long", "double_then_single",
            ):
                flat_key = f"actions_{act_type}"
                if flat_key in entry:
                    if "actions" not in entry or not isinstance(entry.get("actions"), dict):
                        entry["actions"] = {}
                    existing = entry["actions"].get(act_type, [])
                    entry["actions"][act_type] = existing + entry.pop(flat_key)

        # Resolve the target action list based on section type and click_type
        if section == "event":
            # Event actions use nested structure: actions.single, actions.double, etc.
            if "actions" not in entry or not isinstance(entry.get("actions"), dict):
                entry["actions"] = {}
            if click_type not in entry["actions"]:
                entry["actions"][click_type] = []
            target_list = entry["actions"][click_type]
        elif section == "remote_inputs":
            mode = entry.get("mode", "event")
            if mode == "binary_sensor":
                actions_key = "actions_on_press" if click_type in ("pressed", "single") else "actions_on_release"
                if actions_key not in entry:
                    entry[actions_key] = []
                target_list = entry[actions_key]
            else:
                if "actions" not in entry or not isinstance(entry.get("actions"), dict):
                    entry["actions"] = {}
                if click_type not in entry["actions"]:
                    entry["actions"][click_type] = []
                target_list = entry["actions"][click_type]
        else:
            # binary_sensor uses pressed/released
            actions_key = "actions_on_press" if click_type in ("pressed", "single") else "actions_on_release"
            if actions_key not in entry:
                entry[actions_key] = []
            target_list = entry[actions_key]

        # Check for duplicate: same output/cover target already assigned to this click type.
        # Quick actions are meant for simple 1:1 bindings — reject if the same
        # output/cover is already present regardless of action value or conditions.
        for existing in target_list:
            same_output = (
                existing.get("boneio_output") and existing.get("boneio_output") == new_action.get("boneio_output")
            )
            same_cover = (
                existing.get("boneio_cover") and existing.get("boneio_cover") == new_action.get("boneio_cover")
            )
            same_remote_output = (
                existing.get("remote_device") == new_action.get("remote_device")
                and existing.get("output_id") and existing.get("output_id") == new_action.get("output_id")
            )
            same_remote_cover = (
                existing.get("remote_device") == new_action.get("remote_device")
                and existing.get("cover_id") and existing.get("cover_id") == new_action.get("cover_id")
            )
            if same_output or same_cover or same_remote_output or same_remote_cover:
                raise HTTPException(
                    status_code=409,
                    detail=f"This action already exists for {entity_id} ({click_type})",
                )

        target_list.append(new_action)

        entries[input_index] = entry

        # Validate actions before saving
        errors = _validate_section_actions(section, entries)
        if errors:
            raise HTTPException(
                status_code=422,
                detail={"message": "Invalid action configuration", "errors": errors},
            )

        # Save section
        result = update_config_section(app_state.yaml_config_file, section, entries)
        if result["status"] == "error":
            raise HTTPException(status_code=500, detail=result["message"])

        invalidate_config_cache()

        # Hot-update ONLY the affected input's actions (lightweight).
        # Full reload_config → reload_inputs → broadcast_all_input_states causes
        # ALL inputs (including binary sensors) to re-emit state, triggering
        # spurious "released" toasts on the frontend. Instead, directly update
        # the action list on the specific input object.
        try:
            manager: Manager = app_state.manager
            input_device = manager.inputs._inputs.get(entity_id.lower())
            if input_device:
                # Re-read the raw actions from the freshly saved YAML entry
                raw_actions = entry.get("actions", {})
                parsed = manager.parse_actions(
                    getattr(input_device, "pin", entity_id), raw_actions
                )
                input_device.set_actions(actions=parsed)
                _LOGGER.info("Hot-updated actions for input %s", entity_id)
            else:
                _LOGGER.debug(
                    "Input %s not in memory — actions will apply after restart",
                    entity_id,
                )
        except Exception as hot_err:
            _LOGGER.warning("Quick action saved but hot-update failed: %s", hot_err)

        _LOGGER.info(
            "Quick action added: %s -> %s -> %s %s (%s) [section=%s]",
            entity_id, click_type, action_type, output_id or cover_id, action, section,
        )

        return {
            "status": "ok",
            "message": f"Action added to {entity_id} ({click_type})",
            "section": section,
            "click_type": click_type,
        }

    except HTTPException:
        raise
    except Exception as e:
        _LOGGER.error("Error adding quick action: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error adding quick action: {e}") from e


@router.post("/config/inspect_backup_file")
async def inspect_backup_file(file: UploadFile = File(...)):
    """Inspect uploaded backup file to extract metadata."""
    try:
        contents = await file.read()
        fileobj = io.BytesIO(contents)
        config_helper = _get_app_state().manager.config_helper
        return _inspect_tar_fileobj(fileobj, config_helper)
    except Exception as e:
        _LOGGER.error("Failed to inspect backup file: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config/inspect_backup_path")
async def inspect_backup_path(backup_path: str = Body(..., embed=True)):
    """Inspect backup file on disk to extract metadata."""
    try:
        config_file = _get_app_state().yaml_config_file
        config_dir = Path(config_file).parent
        backup_file = Path(backup_path)

        # Security: ensure backup is in the backups directory
        backup_dir = config_dir / "backups"
        backup_file = backup_file.resolve()
        backup_dir = backup_dir.resolve()
        if not str(backup_file).startswith(str(backup_dir)):
            raise HTTPException(status_code=400, detail="Invalid backup path")

        if not backup_file.exists():
            raise HTTPException(status_code=404, detail="Backup file not found")

        config_helper = _get_app_state().manager.config_helper
        with open(backup_file, "rb") as f:
            return _inspect_tar_fileobj(f, config_helper)
    except HTTPException:
        raise
    except Exception as e:
        _LOGGER.error("Failed to inspect backup path: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


def _inspect_tar_fileobj(fileobj, config_helper):
    import json
    meta = None
    try:
        try:
            fileobj.seek(0)
        except Exception:
            pass
        with tarfile.open(fileobj=fileobj, mode="r:gz") as tar:
            try:
                meta_member = tar.getmember("_boneio_meta.json")
                meta_file = tar.extractfile(meta_member)
                if meta_file:
                    meta = json.loads(meta_file.read().decode("utf-8"))
            except KeyError:
                pass
    except Exception as e:
        _LOGGER.warning("Failed to extract backup metadata: %s", e)

    current_serial = config_helper.serial_number
    mismatch = False
    if meta and "effective_serial" in meta:
        mismatch = meta["effective_serial"] != current_serial

    return {
        "backup_meta": meta,
        "current_serial": current_serial,
        "serial_mismatch": mismatch,
    }


