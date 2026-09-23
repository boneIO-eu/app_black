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

from boneio.core import containers
from boneio.core.config.secret_masking import mask_secrets, restore_secrets
from boneio.webui.bind import DEFAULT_PROXY_PORT, proxy_is_serving_cached
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


#: Sends the current state of every entity to every connected panel.
#:
#: Injected from app.py rather than imported: the helper that builds those
#: payloads lives beside the WebSocket endpoint, and importing it here would
#: close a cycle (app.py imports these routers).
_broadcast_states = None


def set_state_broadcaster(broadcaster) -> None:
    """Attach the callable that pushes entity states to connected panels.

    Args:
        broadcaster: Async callable taking the manager, or None.
    """
    global _broadcast_states
    _broadcast_states = broadcaster


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
            # Masked on the way out, always on a copy: the cache is shared with
            # the rest of the process, which needs the real values.
            return {"config": mask_secrets(_config_cache["data"])}

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
        return {"config": mask_secrets(config_data)}

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


def _cloud_enabled(section: object) -> bool:
    """Whether a ``web`` section asks for cloud registration.

    Args:
        section: A ``web`` section, or anything else.

    Returns:
        True when ``cloud.enabled`` is set.
    """
    if not isinstance(section, dict):
        return False
    cloud = section.get("cloud")
    return bool(isinstance(cloud, dict) and cloud.get("enabled"))


def _web_changed_apart_from_cloud(previous: object, current: object) -> bool:
    """Whether anything outside ``cloud`` differs between two web sections.

    Args:
        previous: The section as it was.
        current: The section as saved.

    Returns:
        True when some other setting changed, so a restart is still needed.
    """
    before = {k: v for k, v in previous.items() if k != "cloud"} if isinstance(previous, dict) else {}
    after = {k: v for k, v in current.items() if k != "cloud"} if isinstance(current, dict) else {}
    return before != after


#: The keys of the ``mqtt`` section the running client can adopt in place.
#: Everything else there — the topic prefix, discovery, the update channel —
#: is read into entity names and subscriptions while the application starts.
MQTT_HOT_RELOADABLE_KEYS = frozenset({"host", "port", "username", "password"})


def _mqtt_changed_apart_from_credentials(previous: object, current: object) -> bool:
    """Whether anything outside the broker credentials differs.

    Args:
        previous: The section as it was.
        current: The section as saved.

    Returns:
        True when some other setting changed, so a restart is still needed.
    """
    before = (
        {k: v for k, v in previous.items() if k not in MQTT_HOT_RELOADABLE_KEYS}
        if isinstance(previous, dict) else {}
    )
    after = (
        {k: v for k, v in current.items() if k not in MQTT_HOT_RELOADABLE_KEYS}
        if isinstance(current, dict) else {}
    )
    return before != after


def _mqtt_credentials_changed(previous: object, current: object) -> bool:
    """Whether the broker, the account or its password differs.

    Args:
        previous: The section as it was.
        current: The section as saved.

    Returns:
        True when a reconnect would present something different.
    """
    before = (
        {k: v for k, v in previous.items() if k in MQTT_HOT_RELOADABLE_KEYS}
        if isinstance(previous, dict) else {}
    )
    after = (
        {k: v for k, v in current.items() if k in MQTT_HOT_RELOADABLE_KEYS}
        if isinstance(current, dict) else {}
    )
    return before != after


async def _apply_mqtt_credentials(app_state, previous: object, current: object) -> str | None:
    """Reconnect to the broker with what was just saved.

    The credentials are read once, when the client is built, so a new password
    used to sit in the file doing nothing until the service was restarted. That
    is the other half of "changing the mosquitto password does not work": the
    broker had the new password, this client kept presenting the old one.

    Args:
        app_state: The running application state.
        previous: The ``mqtt`` section before the save.
        current: The ``mqtt`` section being saved.

    Returns:
        What happened, or None when the credentials did not change.
    """
    if not _mqtt_credentials_changed(previous, current):
        return None

    try:
        result = await app_state.manager.reload_config(reload_sections=["mqtt"])
    except Exception as err:  # noqa: BLE001
        # The file is written either way. Failing the request here would
        # report a save that did happen as broken.
        _LOGGER.warning("Could not reconnect to the broker: %s", err)
        return "failed"

    if result.get("status") == "success":
        return "reconnecting"
    _LOGGER.warning("Broker reconnect did not complete: %s", result)
    return "failed"


async def _guard_expose_change(previous: object, current: object) -> None:
    """Refuse to take the panel off the network when nothing else serves it.

    Setting ``web.expose: proxy`` is the fix for the panel being served in the
    clear, and it is also the one setting here whose failure mode is a
    controller answering on no port at all. It is only safe while the reverse
    proxy is actually serving this panel — not merely listening, which it does
    whether or not it can reach the application behind it.

    So the proxy is asked, over the loopback, for something only the
    application can answer, and the save is refused if the answer does not come
    back. A hand-edited config.yaml still goes through: somebody at a console
    who has decided to do this deserves to be able to.

    Args:
        previous: The ``web`` section before the save.
        current: The ``web`` section being saved.

    Raises:
        HTTPException: If the proxy is not serving this panel.
    """
    was = (previous or {}).get("expose") if isinstance(previous, dict) else None
    now = (current or {}).get("expose") if isinstance(current, dict) else None
    if now != "proxy" or was == "proxy":
        return

    port = DEFAULT_PROXY_PORT
    if isinstance(current, dict) and isinstance(current.get("proxy_port"), int):
        port = current["proxy_port"]

    loop = asyncio.get_running_loop()
    serving, reason = await loop.run_in_executor(None, proxy_is_serving_cached, port)
    if not serving:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Not moving the panel behind the proxy: {reason}. It would "
                "leave this device reachable on no port at all."
            ),
        )


async def _apply_web_port_change(previous: object, current: object) -> str | None:
    """Tell Caddy the panel's port when it moves.

    The Caddyfile is generated at container start from ``WEB_PORT``, so a port
    change that does not reach the compose project's ``.env`` leaves Caddy
    proxying to the old one. With ``web.expose`` set to ``proxy`` — the default
    a 1.6 image ships — the application is not listening anywhere else either,
    so the device would answer on nothing but the loopback, the USB link and an
    SSH tunnel.

    ``up -d`` rather than ``restart``: a container's environment is fixed when
    it is created, so a restart would keep the old value and the change would
    appear to have been applied when it had not.

    A failure here is reported, not raised. The port is already saved by this
    point, and the caller needs to hear that the proxy is behind rather than
    receive a 500 that suggests nothing was written at all.

    Args:
        previous: The ``web`` section before the save.
        current: The ``web`` section after it.

    Returns:
        What happened, or None when the port did not move.
    """
    was = (previous or {}).get("port") if isinstance(previous, dict) else None
    now = (current or {}).get("port") if isinstance(current, dict) else None
    if not isinstance(now, int) or now == was:
        return None

    loop = asyncio.get_running_loop()
    if not await loop.run_in_executor(None, containers.set_project_env, "WEB_PORT", str(now)):
        return f"could not tell the proxy about port {now}"

    # Refresh the live compose file from the trusted template, because a device
    # updated from an earlier 1.6 still has the one that does not pass WEB_PORT
    # through — and without that, .env is read and then ignored, which looks
    # exactly like success. Whichever template is in use is re-copied, so a
    # cloud device is not quietly switched back to the local one.
    #
    # The application does not write that file itself: it names a verb and the
    # privileged helper copies from /usr/lib/boneio/trusted. That is F-04, and
    # it is why this is two calls rather than a file write.
    # Which template, asked of the file and not of the configuration. A device
    # whose cloud registration never completed has cloud enabled in config and
    # the local template on disk, and switching it to the cloud one would hand
    # Caddy an init script whose certificates are not there.
    refresh = (
        containers.apply_cloud_template
        if await loop.run_in_executor(None, containers.cloud_template_is_live)
        else containers.remove_cloud_template
    )
    outcome = await loop.run_in_executor(None, refresh)
    if not outcome.ok:
        return (
            f"port {now} is saved, but the proxy still forwards to the old one: "
            f"{outcome.error or 'the compose template could not be refreshed'}"
        )

    outcome = await loop.run_in_executor(None, containers.start_caddy)
    if not outcome.ok:
        return f"the proxy did not come back up on port {now}: {outcome.error or 'unknown reason'}"
    return f"the proxy now forwards to port {now}"


async def _apply_cloud_toggle(app_state, previous: object, current: object) -> str | None:
    """Start or stop cloud registration to match what was just saved.

    Args:
        app_state: Application state, for the live ConfigHelper.
        previous: The ``web`` section before the save.
        current: The ``web`` section after it.

    Returns:
        What happened, or None when the toggle did not move.
    """
    was, now = _cloud_enabled(previous), _cloud_enabled(current)
    if was == now:
        return None

    helper = getattr(getattr(app_state, "manager", None), "config_helper", None)
    if helper is None:
        return None

    try:
        # Imported here, not at the top: cloud registration pulls in aiohttp
        # and the runner defers it for the same reason — a device with the
        # feature switched off should not pay for the import. This is the only
        # place in this module that needs it, and only when the toggle moves.
        from boneio.core.cloud import set_enabled

        return await set_enabled(helper, now)
    except Exception as err:  # noqa: BLE001
        # The setting is already written, so the next start will honour it.
        # Failing the save would suggest otherwise.
        _LOGGER.error("Could not apply the cloud registration change now: %s", err)
        return "unavailable"



@router.put("/config/{section}")
async def update_section_content(section: str, data: dict | list = Body(...)):
    """Update content of a configuration section."""
    # The client was shown a placeholder instead of each configured secret, and
    # posts the whole section back. Anything still carrying the placeholder is
    # resolved from what is stored, so saving an unrelated field cannot
    # overwrite a password with the mask that stood in for it.
    try:
        current = _config_cache["data"] or {}
        data = restore_secrets(data, current.get(section))
    except Exception as err:  # noqa: BLE001 - a save must not fail over this
        _LOGGER.warning("Could not resolve masked secrets for %s: %s", section, err)

    RESTART_REQUIRED_SECTIONS = {
        "boneio", "mqtt", "lox_udp", "web", "modbus",
        "mcp23017", "lm75", "ina219", "ina226", "mcp9808", "can",
    }

    if section in ("event", "binary_sensor") and isinstance(data, list):
        # A sun condition on a device with no coordinates fails open at
        # runtime, so the action keeps firing and nothing looks broken. Save
        # time is the only point where it is visible.
        has_location = bool((_config_cache["data"] or {}).get("location"))
        errors = _validate_section_actions(section, data, has_location=has_location)
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

    # Captured before the write: the cloud toggle is acted on rather than
    # merely stored, and afterwards there is nothing left to compare against.
    previous_section = (_config_cache["data"] or {}).get(section)

    # Before the write, and outside the try below: that one turns every
    # exception into a 500, and this refusal has a reason worth reading.
    if section == "web":
        await _guard_expose_change(previous_section, data)

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

        cloud_outcome = None
        mqtt_outcome = None
        if section == "mqtt":
            mqtt_outcome = await _apply_mqtt_credentials(
                app_state, previous_section, data
            )
            if mqtt_outcome:
                result["mqtt"] = mqtt_outcome
        if section == "web":
            cloud_outcome = await _apply_cloud_toggle(
                app_state, previous_section, data
            )
            if cloud_outcome:
                result["cloud"] = cloud_outcome
            proxy_outcome = await _apply_web_port_change(previous_section, data)
            if proxy_outcome:
                result["proxy"] = proxy_outcome

        # A restart is what the other settings in this section need; the cloud
        # toggle now takes effect where it is made. Asking for one anyway would
        # tell somebody their device is half-configured when it is not.
        needs_restart = section in RESTART_REQUIRED_SECTIONS and not (
            section == "web"
            and cloud_outcome in ("started", "stopped")
            and not _web_changed_apart_from_cloud(previous_section, data)
        )
        # Same shape for the broker credentials: they are adopted where the
        # change is made, so asking for a restart on top of that would tell
        # somebody their device is half-configured when it is not.
        if section == "mqtt" and mqtt_outcome == "reconnecting":
            needs_restart = _mqtt_changed_apart_from_credentials(
                previous_section, data
            )
        if needs_restart:
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

        # Send the new state to the panels that just threw the old one away.
        #
        # The event above tells every client to clear the sections being
        # reloaded, and the frontend has always done so on the promise that
        # "new states will be sent by the backend after reload". Nothing sent
        # them: republish_all_entity_states is MQTT-only and says so, and the
        # only other source is the burst a socket gets when it connects. So
        # saving a section emptied Outputs and Inputs until the page was
        # reloaded — which is what made F5 look like part of saving.
        if _broadcast_states is not None:
            try:
                await _broadcast_states(manager)
            except Exception as err:  # noqa: BLE001
                # The configuration is already reloaded. Failing the request
                # here would report a save that actually succeeded as broken.
                _LOGGER.warning("Could not push new states to the panel: %s", err)

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
