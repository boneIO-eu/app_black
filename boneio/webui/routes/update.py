"""Update routes for BoneIO Web UI."""

from __future__ import annotations

import asyncio
import glob
import logging
import os
import re
import shutil
import subprocess
import time
from datetime import datetime
from typing import TYPE_CHECKING

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel

from boneio.core.atomic_file import write_atomically
from boneio.core.config.yaml_util import load_config_from_file, load_yaml_file, normalize_board_name
from boneio.version import __version__
from boneio.webui.routes.system import get_config_helper
from boneio.webui.services.logs import is_running_as_service

if TYPE_CHECKING:
    from boneio.core.manager import Manager

from boneio.core import system_ops

_LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["update"])

# ── GitHub releases cache ────────────────────────────────────────────────
# Unauthenticated GitHub API allows 60 req/h per IP.
# With multiple boneIO devices behind the same IP this is easily exceeded.
# Cache the raw releases list with a 15-minute TTL.
_GITHUB_RELEASES_CACHE: dict = {
    "data": None,
    "fetched_at": 0.0,
}
_GITHUB_RELEASES_TTL = 900  # 15 minutes in seconds


def _get_cached_releases() -> list | None:
    """Return cached GitHub releases if still fresh, else None."""
    if (
        _GITHUB_RELEASES_CACHE["data"] is not None
        and (time.monotonic() - _GITHUB_RELEASES_CACHE["fetched_at"]) < _GITHUB_RELEASES_TTL
    ):
        return _GITHUB_RELEASES_CACHE["data"]
    return None


def _fetch_github_releases(repo: str = "boneIO-eu/app_black") -> tuple[list | None, str | None]:
    """Fetch releases from GitHub API with caching.

    BLOCKING. Do not call from a coroutine — use
    :func:`_fetch_github_releases_async` instead.

    Returns:
        Tuple of (releases_list, error_message).
        On success error_message is None; on failure releases_list is None.
    """
    cached = _get_cached_releases()
    if cached is not None:
        _LOGGER.debug("Using cached GitHub releases (%d entries)", len(cached))
        return cached, None

    try:
        import requests
    except ImportError:
        return None, "Package 'requests' is not installed. Run: pip install requests"

    api_url = f"https://api.github.com/repos/{repo}/releases"
    try:
        response = requests.get(api_url, timeout=10)
    except Exception as exc:
        return None, f"GitHub API request failed: {exc}"

    if response.status_code != 200:
        return None, f"Failed to fetch releases: {response.text}"

    releases = response.json()

    # Store in cache
    _GITHUB_RELEASES_CACHE["data"] = releases
    _GITHUB_RELEASES_CACHE["fetched_at"] = time.monotonic()
    _LOGGER.debug("Fetched and cached %d GitHub releases", len(releases))

    return releases, None


async def _fetch_github_releases_async(
    repo: str = "boneIO-eu/app_black",
) -> tuple[list | None, str | None]:
    """Fetch releases from GitHub API without stalling the event loop.

    :func:`_fetch_github_releases` uses a blocking ``requests.get()``. Every
    caller sits in a coroutine, so calling it directly froze the entire
    application — no MQTT, no GPIO handling, no web server — for the duration of
    DNS resolution, the TLS handshake and JSON parsing.

    Measured on a BeagleBone Black during startup: 23.3 s of complete
    standstill between "Subscribed to update command topic" and "Starting
    HYPERCORN web server". With no internet at the site it lasts until the
    connect timeout instead.

    A cache hit is answered inline; only a real network round trip is moved to a
    worker thread.

    Returns:
        Tuple of (releases_list, error_message).
    """
    cached = _get_cached_releases()
    if cached is not None:
        _LOGGER.debug("Using cached GitHub releases (%d entries)", len(cached))
        return cached, None

    return await asyncio.to_thread(_fetch_github_releases, repo)


def get_manager():
    """Get manager instance - will be overridden by app initialization."""
    raise NotImplementedError("Manager not initialized")

# Update status tracking
_update_status: dict = {
    "status": "idle",
    "progress": 0,
    "step": "",
    "log": [],
    "error": None,
    "backup_path": None,
    "old_version": None,
    "new_version": None,
}


def _reset_update_status():
    """Reset update status to idle state."""
    global _update_status
    _update_status = {
        "status": "idle",
        "progress": 0,
        "step": "",
        "log": [],
        "error": None,
        "backup_path": None,
        "old_version": None,
        "new_version": None,
    }


def _update_progress(progress: int, step: str, log_msg: str | None = None):
    """Update progress status."""
    global _update_status
    _update_status["progress"] = progress
    _update_status["step"] = step
    if log_msg:
        _update_status["log"].append(log_msg)
        _LOGGER.info(f"Update: {log_msg}")


@router.post("/check_update_now")
async def check_update_now(manager: Manager = Depends(get_manager)):
    """
    Force immediate update check and publish to MQTT.
    
    This endpoint triggers the UpdateManager to check for updates immediately
    instead of waiting for the next periodic check.
    
    Returns:
        Status response.
    """
    try:
        if manager and hasattr(manager, 'update_manager'):
            # Request immediate update check (0 seconds delay)
            manager.update_manager.request_update(seconds=0)
            return {
                "status": "success",
                "message": "Update check triggered, results will be published to MQTT shortly"
            }
        else:
            return {
                "status": "error",
                "message": "UpdateManager not available"
            }
    except Exception as e:
        _LOGGER.error("Error triggering update check: %s", e)
        return {
            "status": "error",
            "message": f"Error: {str(e)}"
        }


@router.get("/check_update")
async def check_update():
    """
    Check if there is a newer version of BoneIO available from GitHub releases.
    
    Returns:
        Update information including available versions.
    """
    current_version = __version__
    
    try:
        from packaging import version
    except ImportError:
        _LOGGER.error("Package 'packaging' is not installed")
        return {
            "status": "error",
            "message": "Package 'packaging' is not installed. Run: pip install packaging",
            "current_version": current_version
        }
    
    try:
        releases, error = await _fetch_github_releases_async()
        
        if error:
            return {
                "status": "error",
                "message": error,
                "current_version": current_version
            }
        
        if not releases:
            return {
                "status": "error",
                "message": "No releases found on GitHub",
                "current_version": current_version
            }
        
        available_versions = []
        # GitHub API does NOT guarantee ordering by version — must compare
        latest_stable = None
        latest_stable_parsed = None
        latest_prerelease = None
        latest_prerelease_parsed = None
        
        for release in releases:
            tag = release['tag_name']
            ver_str = tag[1:] if tag.startswith('v') else tag
            is_prerelease = release.get('prerelease', False)
            
            if not is_prerelease:
                ver_lower = ver_str.lower()
                is_prerelease = any(x in ver_lower for x in ['dev', 'alpha', 'beta', 'rc'])
            
            ver_info = {
                "version": ver_str,
                "is_prerelease": is_prerelease,
                "release_url": release['html_url'],
                "published_at": release['published_at'],
            }
            if tag.startswith("v0."):
                continue
            available_versions.append(ver_info)
            
            try:
                parsed = version.parse(ver_str)
                # Normalize to PEP 440 canonical form (e.g. "1.5.0dev20" → "1.5.0.dev20")
                ver_str = str(parsed)
                ver_info["version"] = ver_str
            except Exception:
                continue
            
            if not is_prerelease:
                if latest_stable_parsed is None or parsed > latest_stable_parsed:
                    latest_stable = ver_info
                    latest_stable_parsed = parsed
            else:
                if latest_prerelease_parsed is None or parsed > latest_prerelease_parsed:
                    latest_prerelease = ver_info
                    latest_prerelease_parsed = parsed
        
        current_ver_lower = current_version.lower()
        current_is_prerelease = any(x in current_ver_lower for x in ['dev', 'alpha', 'beta', 'rc'])
        
        is_update_available = False
        prerelease_update_available = False
        try:
            current_parsed = version.parse(current_version)
            
            # Find the best recommended version:
            # - Always consider stable releases as potential updates
            # - For prerelease users: also consider newer prereleases
            # - Pick whichever is newer (stable or prerelease)
            candidates = []
            if latest_stable:
                stable_parsed = version.parse(latest_stable["version"])
                if stable_parsed > current_parsed:
                    candidates.append((stable_parsed, latest_stable))
            if latest_prerelease:
                pre_parsed = version.parse(latest_prerelease["version"])
                if pre_parsed > current_parsed:
                    candidates.append((pre_parsed, latest_prerelease))
                    if not current_is_prerelease:
                        prerelease_update_available = True
            
            if candidates:
                # Pick the newest candidate
                candidates.sort(key=lambda x: x[0], reverse=True)
                recommended = candidates[0][1]
                is_update_available = True
            else:
                # No update available, show current channel's latest
                if current_is_prerelease:
                    recommended = latest_prerelease or latest_stable or available_versions[0]
                else:
                    recommended = latest_stable or latest_prerelease or available_versions[0]
        except Exception as e:
            _LOGGER.warning("Error parsing versions for comparison: %s", str(e))
            is_update_available = False
            recommended = latest_stable or latest_prerelease or available_versions[0]
        
        return {
            "status": "success",
            "current_version": current_version,
            "current_is_prerelease": current_is_prerelease,
            "latest_version": recommended["version"],
            "latest_stable": latest_stable["version"] if latest_stable else None,
            "latest_prerelease": latest_prerelease["version"] if latest_prerelease else None,
            "update_available": is_update_available,
            "prerelease_update_available": prerelease_update_available,
            "release_url": recommended["release_url"],
            "published_at": recommended["published_at"],
            "is_prerelease": recommended["is_prerelease"],
            "available_versions": available_versions[:10]
        }
    except Exception as e:
        if "Timeout" in str(type(e)):
            _LOGGER.error("Timeout while checking for updates")
            return {
                "status": "error",
                "message": "Timeout while connecting to GitHub. Check your internet connection.",
                "current_version": current_version
            }
        if "ConnectionError" in str(type(e)):
            _LOGGER.error("Connection error while checking for updates")
            return {
                "status": "error",
                "message": "Cannot connect to GitHub. Check your internet connection.",
                "current_version": current_version
            }
        _LOGGER.exception("Error checking for updates: %s", str(e))
        return {
            "status": "error",
            "message": f"Error checking for updates: {str(e)}",
            "current_version": current_version
        }


@router.get("/update/status")
async def get_update_status():
    """Get current update status and progress."""
    return _update_status


class UpdateRequest(BaseModel):
    """Request model for update endpoint."""
    version: str | None = None


@router.post("/update")
async def update_boneio(background_tasks: BackgroundTasks, request: UpdateRequest = UpdateRequest(), manager: Manager = Depends(get_manager)):
    """
    Update the BoneIO package with backup and restart the service.
    
    Uses UpdateManager.perform_update as the single update algorithm,
    with an on_progress callback to track status for the WebUI.
    
    Args:
        request: Optional version to install.
        
    Returns:
        Status response.
    """
    global _update_status
    
    if not is_running_as_service():
        return {"status": "error", "message": "Update is only available when running as a service"}
    
    if _update_status["status"] == "running":
        return {"status": "error", "message": "Update already in progress"}
    
    if not manager or not hasattr(manager, 'update_manager'):
        return {"status": "error", "message": "UpdateManager not available"}
    
    if manager.update_manager.update_running:
        return {"status": "error", "message": "Update already in progress"}
    
    target_version = request.version
    current_version = __version__
    
    _reset_update_status()
    _update_status["status"] = "running"
    _update_status["old_version"] = current_version
    _update_status["target_version"] = target_version

    def _on_progress(progress: int, step: str, log_msg: str | None = None) -> None:
        """Callback from UpdateManager to track progress for WebUI."""
        _update_status["progress"] = progress
        _update_status["step"] = step
        if log_msg:
            _update_status["log"].append(log_msg)
        if progress == 0 and step not in ("Finding virtual environment...",):
            # Error or completion with progress=0 means failure
            if _update_status["status"] == "running":
                _update_status["status"] = "error"
                _update_status["error"] = log_msg or step
        elif progress == 100:
            _update_status["status"] = "success"

    async def _run_update():
        try:
            await manager.update_manager.perform_update(
                target_version=target_version,
                on_progress=_on_progress,
            )
        except Exception as e:
            _update_status["status"] = "error"
            _update_status["error"] = str(e)
            _LOGGER.error("Error during update process: %s", e, exc_info=True)
    
    background_tasks.add_task(_run_update)
    return {"status": "started", "message": "Update process started"}


class RollbackRequest(BaseModel):
    """Request model for rollback."""
    version: str


@router.post("/update/rollback")
async def rollback_update(request: RollbackRequest, background_tasks: BackgroundTasks):
    """
    Rollback to a specific version using pip install.
    
    Args:
        request: RollbackRequest with target version.
        background_tasks: FastAPI background tasks.
    
    Returns:
        Status response.
    """
    if not is_running_as_service():
        return {"status": "error", "message": "Rollback is only available when running as a service"}
    
    target_version = request.version
    current_version = __version__
    
    if target_version == current_version:
        return {"status": "error", "message": f"Already running version {current_version}"}
    
    possible_venv_paths = [
        os.path.expanduser("~/boneio/venv"),
        os.path.expanduser("~/venv"),
        "/opt/boneio/venv",
    ]
    
    pip_path = None
    for path in possible_venv_paths:
        pip_candidate = os.path.join(path, "bin", "pip")
        if os.path.exists(pip_candidate):
            pip_path = pip_candidate
            break
    
    if not pip_path:
        return {"status": "error", "message": "Virtual environment not found"}
    
    async def rollback_and_restart():
        """Perform rollback in background and restart."""
        global _update_status
        _reset_update_status()
        _update_status["status"] = "running"
        _update_status["old_version"] = current_version
        _update_status["target_version"] = target_version
        
        try:
            _update_progress(10, f"Rolling back to version {target_version}...")
            
            pip_cmd = [pip_path, "install"]
            # Add --pre flag for pre-release versions (dev, alpha, beta, rc)
            ver_lower = target_version.lower()
            if any(x in ver_lower for x in ['dev', 'alpha', 'beta', 'rc']):
                pip_cmd.append("--pre")
            pip_cmd.append(f"boneio=={target_version}")
            
            result = subprocess.run(
                pip_cmd,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode != 0:
                _update_status["status"] = "error"
                _update_status["error"] = f"pip install failed: {result.stderr}"
                _update_progress(0, "Rollback failed", result.stderr)
                return
            
            _update_status["status"] = "success"
            _update_status["new_version"] = target_version
            _update_progress(100, "Rollback complete!", f"Rolled back from {current_version} to {target_version}. Restarting...")
            
            _LOGGER.info(f"Rolled back from {current_version} to {target_version}")
            
            await asyncio.sleep(2)
            os._exit(0)
            
        except subprocess.TimeoutExpired:
            _update_status["status"] = "error"
            _update_status["error"] = "Rollback timed out"
            _update_progress(0, "Timeout", "Rollback process timed out")
        except Exception as e:
            _update_status["status"] = "error"
            _update_status["error"] = str(e)
            _update_progress(0, "Error", f"Unexpected error: {e}")
            _LOGGER.error(f"Error during rollback: {e}", exc_info=True)
    
    background_tasks.add_task(rollback_and_restart)
    return {"status": "started", "message": f"Rollback to {target_version} started"}


@router.get("/update/available_versions")
async def list_available_versions():
    """
    List available BoneIO versions from GitHub releases.
    
    These versions can be used for rollback via pip install boneio=={version}.
    
    Returns:
        List of available versions.
    """
    current_version = __version__
    
    try:
        releases, error = await _fetch_github_releases_async()
        
        if error:
            return {
                "status": "error",
                "message": error,
                "current_version": current_version,
                "versions": []
            }
        
        if not releases:
            releases = []
        versions = []
        
        for release in releases:
            tag = release.get("tag_name", "")
            # Remove 'v' prefix if present
            version = tag.lstrip("v") if tag.startswith("v") else tag
            if not version:
                continue
            
            # Skip versions starting with 0.x (Debian 10, incompatible)
            if version.startswith("0."):
                continue
                
            versions.append({
                "version": version,
                "name": release.get("name", version),
                "published_at": release.get("published_at"),
                "prerelease": release.get("prerelease", False),
                "is_current": version == current_version,
            })
        
        return {
            "status": "success",
            "current_version": current_version,
            "versions": versions
        }
        
    except Exception as e:
        _LOGGER.error(f"Error fetching versions: {e}")
        return {
            "status": "error",
            "message": str(e),
            "current_version": current_version,
            "versions": []
        }


@router.get("/update/check_config_compat")
async def check_config_compat(target_version: str):
    """Check if current config is compatible with a target app version.

    Compares the current config_version against the maximum schema version
    supported by the target app version using SCHEMA_VERSION_APP_MAP.

    Args:
        target_version: The app version the user wants to roll back to.

    Returns:
        Compatibility info with compatible flag and human-readable message.
    """
    from boneio.core.config.migrations import (
        CURRENT_SCHEMA_VERSION,
        SCHEMA_VERSION_APP_MAP,
        get_config_version,
    )

    try:
        from packaging import version as pkg_version
    except ImportError:
        return {
            "compatible": True,
            "message": "Cannot check compatibility (packaging module not installed).",
        }

    # Read current config_version from the YAML file on disk
    current_config_version = CURRENT_SCHEMA_VERSION  # fallback
    try:
        config_file = os.path.expanduser("~/boneio/config.yaml")
        if os.path.exists(config_file):
            raw = load_yaml_file(config_file)
            if raw:
                current_config_version = get_config_version(raw)
    except Exception as e:
        _LOGGER.warning("Could not read config_version from file: %s", e)

    # Find max schema version supported by target app version
    try:
        target_parsed = pkg_version.parse(target_version)
    except Exception:
        return {
            "compatible": True,
            "message": f"Cannot parse target version '{target_version}'.",
        }

    max_supported_schema = 0
    min_required_app = SCHEMA_VERSION_APP_MAP.get(current_config_version, "unknown")

    for schema_ver, app_ver_str in sorted(SCHEMA_VERSION_APP_MAP.items()):
        try:
            if pkg_version.parse(app_ver_str) <= target_parsed:
                max_supported_schema = schema_ver
        except Exception:
            continue

    compatible = current_config_version <= max_supported_schema

    if compatible:
        message = (
            f"Config version {current_config_version} is compatible "
            f"with app version {target_version}."
        )
    else:
        message = (
            f"Config version {current_config_version} requires app >= {min_required_app}. "
            f"Version {target_version} supports max config version {max_supported_schema}. "
            f"Rolling back may cause configuration errors."
        )

    return {
        "compatible": compatible,
        "current_config_version": current_config_version,
        "target_max_schema_version": max_supported_schema,
        "min_required_app_version": min_required_app,
        "message": message,
    }


# Available device types for factory reset
DEVICE_TYPES = ["24x16", "32x10", "48x4", "cover", "cover_mix"]

# Hardware version to sensor mapping
# Different hardware versions have different temperature sensors, power monitoring, and UART for modbus
HARDWARE_SENSORS = {
    "0.2": {"temp_sensor": "mcp9808", "temp_address": 0x18, "has_ina219": False, "power_sensor": None, "modbus_uart": "uart1"},
    "0.3": {"temp_sensor": "mcp9808", "temp_address": 0x18, "has_ina219": False, "power_sensor": None, "modbus_uart": "uart1"},
    "0.4": {"temp_sensor": "lm75", "temp_address": 0x48, "has_ina219": True, "power_sensor": "ina219", "modbus_uart": "uart4"},
    "0.5": {"temp_sensor": "lm75", "temp_address": 0x48, "has_ina219": True, "power_sensor": "ina219", "modbus_uart": "uart4"},
    "0.6": {"temp_sensor": "lm75", "temp_address": 0x48, "has_ina219": True, "power_sensor": "ina219", "modbus_uart": "uart4"},
    "0.7": {"temp_sensor": "lm75", "temp_address": 0x48, "has_ina219": True, "power_sensor": "ina219", "modbus_uart": "uart4"},
    "0.8": {"temp_sensor": "lm75", "temp_address": 0x48, "has_ina219": True, "power_sensor": "ina219", "modbus_uart": "uart4"},
    "1.0": {"temp_sensor": "lm75", "temp_address": 0x48, "has_ina219": False, "power_sensor": "ina226", "modbus_uart": "uart4"},
    # 1.1 differs from 1.0 only by the buzzer, which touches neither the
    # sensors nor the UART.
    "1.1": {"temp_sensor": "lm75", "temp_address": 0x48, "has_ina219": False, "power_sensor": "ina226", "modbus_uart": "uart4"},
}

# Available hardware versions
HARDWARE_VERSIONS = list(HARDWARE_SENSORS.keys())


@router.get("/factory_reset/hardware_versions")
async def get_hardware_versions():
    """
    Get available hardware versions for factory reset.
    
    Returns:
        List of available hardware versions with sensor info.
    """
    return {
        "versions": HARDWARE_VERSIONS,
        "sensors": HARDWARE_SENSORS,
    }


@router.get("/factory_reset/device_types")
async def get_device_types():
    """
    Get available device types for factory reset.
    
    Returns:
        List of available device types.
    """
    return {"device_types": DEVICE_TYPES}


class FactoryResetRequest(BaseModel):
    """Request model for factory reset endpoint."""
    device_type: str
    version: str = "0.8"  # Hardware version, default to latest


class PartialResetRequest(BaseModel):
    """Request model for partial factory reset endpoint."""
    device_type: str
    files_to_replace: list[str]  # Categories: output, event, binary_sensor, cover


@router.post("/factory_reset/partial")
async def partial_factory_reset(request: PartialResetRequest):
    """
    Partially reset configuration by replacing only selected files.
    
    This allows replacing output/event/binary_sensor/cover configs
    while keeping mqtt, config, adc and other files intact.
    
    Args:
        request: Device type and list of file categories to replace
        
    Returns:
        Status response with backup info and copied files.
    """
    device_type = request.device_type.lower()
    files_to_replace = request.files_to_replace
    
    # Normalize device type
    normalized_type = normalize_board_name(device_type)
    
    if normalized_type not in DEVICE_TYPES:
        return {
            "status": "error",
            "message": f"Invalid device type: {device_type}. Available: {', '.join(DEVICE_TYPES)}"
        }
    
    if not files_to_replace:
        return {
            "status": "error",
            "message": "No files selected for replacement"
        }
    
    # Find example config directory (relative to this file: boneio/webui/routes/update.py)
    boneio_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    example_config_dir = os.path.join(boneio_path, "example_config", normalized_type)
    
    if not os.path.isdir(example_config_dir):
        return {
            "status": "error",
            "message": f"Example config not found for device type: {device_type}"
        }
    
    # User config directory
    config_dir = os.path.expanduser("~/boneio")
    
    if not os.path.isdir(config_dir):
        os.makedirs(config_dir, exist_ok=True)
    
    try:
        # Step 1: Create backup of files that will be replaced
        backup_dir = os.path.expanduser("~/boneio_config_backups")
        os.makedirs(backup_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(backup_dir, f"partial_backup_{timestamp}")
        
        # Map categories to file patterns
        category_patterns = {
            "output": ["output"],
            "event": ["event"],
            "binary_sensor": ["binary_sensor"],
            "cover": ["cover"],
        }
        
        # Find example files matching selected categories
        example_files_to_copy = []
        for filename in os.listdir(example_config_dir):
            if not filename.endswith(".yaml"):
                continue
            base_name = filename.replace(".yaml", "").lower()
            for category in files_to_replace:
                patterns = category_patterns.get(category, [category])
                for pattern in patterns:
                    if pattern in base_name:
                        example_files_to_copy.append(filename)
                        break
        
        if not example_files_to_copy:
            return {
                "status": "error",
                "message": f"No matching example files found for categories: {files_to_replace}"
            }
        
        # Find user files that match the patterns (to backup and remove)
        user_files_to_backup = []
        for filename in os.listdir(config_dir):
            if not filename.endswith(".yaml"):
                continue
            base_name = filename.replace(".yaml", "").lower()
            for category in files_to_replace:
                patterns = category_patterns.get(category, [category])
                for pattern in patterns:
                    if pattern in base_name:
                        user_files_to_backup.append(filename)
                        break
        
        # Backup user files
        backed_up_files = []
        if user_files_to_backup:
            os.makedirs(backup_path, exist_ok=True)
            for filename in user_files_to_backup:
                src = os.path.join(config_dir, filename)
                shutil.copy2(src, backup_path)
                backed_up_files.append(filename)
                _LOGGER.info(f"Backed up {filename}")
        
        # Remove old user files
        for filename in user_files_to_backup:
            os.remove(os.path.join(config_dir, filename))
            _LOGGER.info(f"Removed old file: {filename}")
        
        # Copy example files
        copied_files = []
        for filename in example_files_to_copy:
            src = os.path.join(example_config_dir, filename)
            dest = os.path.join(config_dir, filename)
            shutil.copy2(src, dest)
            copied_files.append(filename)
            _LOGGER.info(f"Copied {filename} to {config_dir}")
        
        _LOGGER.info(f"Partial reset completed for device type: {device_type}, categories: {files_to_replace}")
        
        return {
            "status": "success",
            "message": f"Configuration partially reset for {device_type}",
            "backup_path": backup_path if backed_up_files else None,
            "backed_up_files": backed_up_files,
            "copied_files": copied_files,
            "restart_required": True
        }
        
    except Exception as e:
        _LOGGER.exception(f"Error during partial factory reset: {e}")
        return {
            "status": "error",
            "message": f"Partial reset failed: {str(e)}"
        }


def _adjust_config_for_hardware_version(config_content: str, version: str, device_type: str) -> str:
    """
    Adjust config.yaml content for specific hardware version.
    
    Different hardware versions have different sensors:
    - 0.2, 0.3: MCP9808 temperature sensor, no INA219, modbus on uart1
    - 0.4+: LM75 temperature sensor, INA219 power monitor, modbus on uart4
    
    Args:
        config_content: Original config.yaml content
        version: Hardware version (e.g., "0.2", "0.8")
        device_type: Device type for naming
        
    Returns:
        Modified config.yaml content
    """
    hw_config = HARDWARE_SENSORS.get(version, HARDWARE_SENSORS["0.8"])
    
    # Replace temperature sensor section
    if hw_config["temp_sensor"] == "mcp9808":
        # Replace lm75 with mcp9808
        config_content = re.sub(
            r'lm75:\s*\n\s*-\s*id:.*\n\s*address:.*\n',
            f'mcp9808:\n  - id: Board temperature\n    address: 0x{hw_config["temp_address"]:02X}\n',
            config_content
        )
    
    # Adjust power sensor section (ina219 / ina226)
    power_sensor = hw_config.get("power_sensor")
    if power_sensor == "ina226":
        # Replace ina219 with ina226 or insert ina226 if needed
        if "ina219:" in config_content:
            config_content = re.sub(
                r'ina219:\s*\n(\s*-\s*address:.*\n)?',
                'ina226:\n  - address: 0x40\n',
                config_content
            )
        elif "ina226:" not in config_content:
            config_content += '\nina226:\n  - address: 0x40\n'
    elif power_sensor == "ina219":
        if "ina226:" in config_content:
            config_content = re.sub(
                r'ina226:\s*\n(\s*-\s*address:.*\n)?',
                'ina219:\n  - address: 0x40\n',
                config_content
            )
        elif "ina219:" not in config_content:
            config_content += '\nina219:\n  - address: 0x40\n'
    else:
        # Remove power sensor section if not supported
        config_content = re.sub(
            r'(ina219|ina226):\s*\n(\s*-\s*address:.*\n)?',
            '',
            config_content
        )
    
    # Update modbus uart if different from default (uart4)
    modbus_uart = hw_config.get("modbus_uart", "uart4")
    if modbus_uart != "uart4":
        config_content = re.sub(
            r'(modbus:\s*\n\s*)uart:\s*uart4',
            f'\\1uart: {modbus_uart}',
            config_content
        )
    
    # Update boneio version in config
    config_content = re.sub(
        r'(boneio:\s*\n\s*name:[^\n]*\n\s*)version:[^\n]*\n',
        f'\\1version: {version}\n',
        config_content
    )
    
    return config_content


@router.post("/factory_reset")
async def factory_reset(request: FactoryResetRequest):
    """
    Reset configuration to factory defaults for selected device type.
    
    This will:
    1. Create a backup of current configuration
    2. Remove old configuration files
    3. Copy example config files for the selected device type
    4. Adjust config.yaml for hardware version (sensor compatibility)
    5. Restart the application
    
    Args:
        request: Device type and hardware version to reset to
        
    Returns:
        Status response.
    """
    device_type = request.device_type.lower()
    version = request.version
    
    if device_type not in DEVICE_TYPES:
        return {
            "status": "error",
            "message": f"Invalid device type: {device_type}. Available: {', '.join(DEVICE_TYPES)}"
        }
    
    if version not in HARDWARE_VERSIONS:
        return {
            "status": "error",
            "message": f"Invalid hardware version: {version}. Available: {', '.join(HARDWARE_VERSIONS)}"
        }
    
    # Find example config directory (relative to this file: boneio/webui/routes/update.py)
    boneio_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    example_config_dir = os.path.join(boneio_path, "example_config", device_type)
    
    if not os.path.isdir(example_config_dir):
        return {
            "status": "error",
            "message": f"Example config not found for device type: {device_type}"
        }
    
    # User config directory
    config_dir = os.path.expanduser("~/boneio")
    
    if not os.path.isdir(config_dir):
        os.makedirs(config_dir, exist_ok=True)
    
    try:
        # Step 1: Create backup of current configuration
        backup_dir = os.path.expanduser("~/boneio_config_backups")
        os.makedirs(backup_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(backup_dir, f"config_backup_{timestamp}")
        
        # Copy all yaml files from config_dir to backup
        yaml_files = glob.glob(os.path.join(config_dir, "*.yaml"))
        if yaml_files:
            os.makedirs(backup_path, exist_ok=True)
            for yaml_file in yaml_files:
                shutil.copy2(yaml_file, backup_path)
            _LOGGER.info(f"Configuration backup created at {backup_path}")
        
        # Step 2: Remove old configuration files and state
        for yaml_file in yaml_files:
            os.remove(yaml_file)
            _LOGGER.info(f"Removed old config file: {os.path.basename(yaml_file)}")
        
        # Remove state.json to prevent old device states from interfering
        state_file = os.path.join(config_dir, "state.json")
        if os.path.exists(state_file):
            os.remove(state_file)
            _LOGGER.info("Removed old state.json file")
        
        # Step 3: Copy example config files
        example_files = glob.glob(os.path.join(example_config_dir, "*.yaml"))
        
        if not example_files:
            return {
                "status": "error",
                "message": f"No YAML files found in example config for {device_type}"
            }
        
        copied_files = []
        adjusted_files = []
        for example_file in example_files:
            filename = os.path.basename(example_file)
            dest_path = os.path.join(config_dir, filename)
            
            # For config.yaml, adjust sensors based on hardware version
            if filename == "config.yaml":
                with open(example_file) as f:
                    content = f.read()
                adjusted_content = _adjust_config_for_hardware_version(content, version, device_type)
                write_atomically(dest_path, adjusted_content)
                if content != adjusted_content:
                    adjusted_files.append(filename)
                    _LOGGER.info(f"Adjusted {filename} for hardware version {version}")
            else:
                shutil.copy2(example_file, dest_path)
            
            copied_files.append(filename)
            _LOGGER.info(f"Copied {filename} to {config_dir}")
        
        _LOGGER.info(f"Factory reset completed for device type: {device_type}, version: {version}")
        
        return {
            "status": "success",
            "message": f"Configuration reset to {device_type} defaults (hardware v{version})",
            "backup_path": backup_path if yaml_files else None,
            "copied_files": copied_files,
            "adjusted_files": adjusted_files,
            "hardware_version": version,
            "restart_required": True
        }
        
    except Exception as e:
        _LOGGER.exception(f"Error during factory reset: {e}")
        return {
            "status": "error",
            "message": f"Factory reset failed: {str(e)}"
        }


@router.get("/factory_reset/config_backups")
async def list_config_backups():
    """
    List available configuration backups.
    
    Returns:
        List of configuration backup information.
    """
    backup_dir = os.path.expanduser("~/boneio_config_backups")
    
    if not os.path.isdir(backup_dir):
        return {"backups": []}
    
    backups = sorted(glob.glob(os.path.join(backup_dir, "config_backup_*")), reverse=True)
    
    backup_list = []
    for backup in backups:
        name = os.path.basename(backup)
        parts = name.split('_')
        timestamp = f"{parts[2]}_{parts[3]}" if len(parts) > 3 else "unknown"
        
        # Count yaml files in backup
        yaml_count = len(glob.glob(os.path.join(backup, "*.yaml")))
        
        backup_list.append({
            "path": backup,
            "name": name,
            "timestamp": timestamp,
            "file_count": yaml_count,
        })
    
    return {"backups": backup_list}


class RestoreConfigBackupRequest(BaseModel):
    """Request model for restoring config backup."""
    backup_path: str


@router.post("/factory_reset/restore_backup")
async def restore_config_backup(request: RestoreConfigBackupRequest):
    """
    Restore configuration from a backup.
    
    Args:
        request: Path to backup to restore
        
    Returns:
        Status response.
    """
    backup_path = request.backup_path
    
    if not os.path.isdir(backup_path):
        return {
            "status": "error",
            "message": f"Backup not found: {backup_path}"
        }
    
    config_dir = os.path.expanduser("~/boneio")
    
    try:
        # Copy yaml files from backup to config dir
        yaml_files = glob.glob(os.path.join(backup_path, "*.yaml"))
        
        if not yaml_files:
            return {
                "status": "error",
                "message": "No YAML files found in backup"
            }
        
        restored_files = []
        for yaml_file in yaml_files:
            filename = os.path.basename(yaml_file)
            dest_path = os.path.join(config_dir, filename)
            shutil.copy2(yaml_file, dest_path)
            restored_files.append(filename)
            _LOGGER.info(f"Restored {filename} from backup")
        
        return {
            "status": "success",
            "message": "Configuration restored from backup",
            "restored_files": restored_files,
            "restart_required": True
        }
        
    except Exception as e:
        _LOGGER.exception(f"Error restoring backup: {e}")
        return {
            "status": "error",
            "message": f"Restore failed: {str(e)}"
        }


@router.get("/mqtt/username")
async def get_mqtt_username():
    """Report which broker account the application actually connects with.

    The panel shows the accounts of the broker installed on this controller,
    and warns on the row belonging to boneIO itself — change that password
    without updating the configuration and the device stops reporting.

    Getting that row right means reading the running configuration, which this
    did not do. It opened ``~/.boneio/mqtt.yaml``, a path that does not exist
    on a real device, looked for a ``mqtt:`` key inside a file whose contents
    *are* the mqtt section, and fell through both failures to a hard-coded
    "boneio". The warning was therefore fixed to that row, and wrong for
    anyone who had changed the username.

    The answer also says whether the broker is the local one at all. Point
    boneIO at the broker in Home Assistant and none of these accounts is the
    one it uses, so the warning belongs on no row.

    Returns:
        The configured username, the broker host, and whether that host is
        this device.
    """
    #: Hosts that mean "the broker installed here". An empty host is the
    #: client library's own default, which is loopback.
    local_hosts = {"localhost", "127.0.0.1", "::1", ""}

    username = "boneio"
    host = ""
    known = False

    try:
        config = get_config_helper().get_config()
        mqtt = config.get("mqtt") if isinstance(config, dict) else None
        if isinstance(mqtt, dict):
            username = str(mqtt.get("username") or "boneio")
            host = str(mqtt.get("host") or "")
            known = True
    except Exception as err:  # noqa: BLE001
        # Never fail the panel over this: without it the passwords still
        # change, only the warning is missing. But say so — silence here is
        # what let the broken version survive.
        _LOGGER.warning("Could not read the MQTT configuration: %s", err)

    return {
        "status": "success",
        "username": username,
        "host": host,
        "uses_local_broker": known and host.lower() in local_hosts,
        # False means the fields above are a guess, and the panel should not
        # claim anything about which account belongs to the application.
        "known": known,
    }


class MqttPasswordChangeRequest(BaseModel):
    """Request model for MQTT password change."""
    username: str
    new_password: str
    #: Also store the new password in this device's own configuration and
    #: reconnect with it. Only meaningful for the account boneIO connects
    #: with, on the broker installed here; see :func:`_adopt_broker_password`.
    update_config: bool = False


#: Hosts that mean "the broker installed on this controller". An empty host is
#: the client library's own default, which is loopback. Kept in step with
#: :func:`get_mqtt_username`, which shows the panel the same thing.
LOCAL_BROKER_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", ""})


def _store_broker_password(config_file: str, password: str) -> str:
    """Write a new broker password where this device reads its own from.

    BLOCKING: file I/O, called through an executor.

    Args:
        config_file: Path to config.yaml.
        password: The password just set in the broker.

    Returns:
        ``"config"``, or ``"secret"`` when the field defers to secrets.yaml and
        the password was written there instead — which is the whole reason this
        does not simply overwrite the line: ``password: !secret mqtt_pass``
        usually means config.yaml is somewhere the password must not be.

    Raises:
        YamlPatchError: If the mqtt section cannot be edited, such as an
            include naming a file that is not there.
    """
    from boneio.core.config.yaml_patch import (
        resolve_field,
        secret_reference,
        set_scalar,
        set_secret,
    )

    field = ("mqtt", "password")
    # Every shipped controller has `mqtt: !include mqtt.yaml`, and that file is
    # the per-device one the broker password exists in. A secrets.yaml beside
    # it is the one BoneIOLoader would read from there.
    target, _ = resolve_field(config_file, field)
    reference = secret_reference(config_file, field)
    if reference is not None:
        set_secret(target.parent / "secrets.yaml", reference, password)
        return "secret"
    set_scalar(config_file, field, password)
    return "config"


async def _adopt_broker_password(manager: Manager, username: str, password: str) -> dict:
    """Have boneIO start using a password that was just set in the broker.

    The account boneIO connects with is also the account whose password the
    panel changes, so changing it there and nowhere else takes the device off
    its own broker until somebody edits the configuration and restarts. That
    gap is what testers reported as the password change not working.

    Only for the broker installed on this controller: with ``mqtt.host``
    pointing somewhere else, the accounts in the local password file are not
    the ones boneIO uses, and its configuration must not be touched.

    Args:
        manager: The running manager.
        username: The account whose password was changed.
        password: The new password.

    Returns:
        What happened, as ``{"status": ..., "reason": ...}``. Never raises: the
        broker password is already changed by the time this runs, and reporting
        that as a failure would be worse than saying what was skipped.
    """
    try:
        config = manager.config_helper.get_config() or {}
        mqtt = config.get("mqtt")
        if not isinstance(mqtt, dict):
            return {"status": "skipped", "reason": "no_mqtt_section"}

        host = str(mqtt.get("host") or "").strip().lower()
        if host not in LOCAL_BROKER_HOSTS:
            return {"status": "skipped", "reason": "remote_broker"}

        configured = str(mqtt.get("username") or "boneio")
        if configured != username:
            return {"status": "skipped", "reason": "other_account"}

        config_file = manager.config_helper.config_file_path
        if not config_file:
            return {"status": "skipped", "reason": "no_config_file"}

        loop = asyncio.get_running_loop()
        written = await loop.run_in_executor(
            None, _store_broker_password, config_file, password
        )
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Could not store the new broker password: %s", err)
        return {"status": "error", "reason": str(err)}

    try:
        result = await manager.reload_config(reload_sections=["mqtt"])
    except Exception as err:  # noqa: BLE001
        # Written but not adopted: a restart will pick it up, and saying so
        # is better than claiming either success or failure.
        _LOGGER.warning("Stored the new broker password but could not reconnect: %s", err)
        return {"status": "written", "reason": str(err), "written_to": written}

    if result.get("status") != "success":
        _LOGGER.warning("Broker reconnect did not complete: %s", result)
        return {"status": "written", "reason": "reload_failed", "written_to": written}

    return {"status": "adopted", "written_to": written}


@router.post("/mqtt/change_password")
async def change_mqtt_password(
    request: MqttPasswordChangeRequest,
    manager: Manager = Depends(get_manager),
):
    """
    Change MQTT password for specified user.

    Supports three users: boneio, homeassistant, mqtt
    Uses mosquitto_passwd to update password file.

    With ``update_config`` set, and only for the account boneIO itself
    connects with on the broker installed here, the new password is also
    stored in this device's configuration and adopted without a restart.

    WARNING: This endpoint sends passwords in plain text over HTTP.
    Use only over HTTPS or in a trusted local network.

    Args:
        request: Username, new password, and whether to adopt it here.
        manager: The running manager.

    Returns:
        Status response with success/error message
    """
    # Validate username
    allowed_users = ["boneio", "homeassistant", "mqtt"]
    if request.username not in allowed_users:
        return {
            "status": "error",
            "message": f"Invalid username. Allowed users: {', '.join(allowed_users)}"
        }
    
    # Validate password
    if len(request.new_password) < 8:
        return {
            "status": "error",
            "message": "Password must be at least 8 characters long"
        }
    
    try:
        # Through the helper, which reads the password from stdin. The rule
        # this replaces was `mosquitto_passwd -b <file> <user> *`, so the new
        # password sat in the process table — readable by every local account —
        # for as long as the command ran. The helper also puts the file back to
        # root:mosquitto 0640 afterwards, which mosquitto_passwd does not (F-11).
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, system_ops.mqtt_password, request.username, request.new_password
        )
        if not result.ok:
            message = result.stderr.strip() or "Failed to change the password"
            _LOGGER.error(
                "Failed to change MQTT password for %s: %s", request.username, message
            )
            return {"status": "error", "message": message}

        _LOGGER.info("MQTT password changed for user: %s", request.username)

        reload_result = await loop.run_in_executor(None, system_ops.mqtt_reload)
        if not reload_result.ok:
            # Not fatal: the password is written, the broker just has not been
            # told yet, and it will pick it up on its next start.
            _LOGGER.warning(
                "Could not reload mosquitto: %s", reload_result.stderr.strip()
            )

        response = {
            "status": "success",
            "message": f"Password changed successfully for user: {request.username}"
        }

        if request.update_config:
            response["config"] = await _adopt_broker_password(
                manager, request.username, request.new_password
            )

        return response

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else str(e)
        _LOGGER.error(f"Failed to change MQTT password for {request.username}: {error_msg}")
        return {
            "status": "error",
            "message": f"Failed to change password: {error_msg}"
        }
    except Exception as e:
        _LOGGER.exception(f"Unexpected error changing MQTT password: {e}")
        return {
            "status": "error",
            "message": f"Unexpected error: {str(e)}"
        }
