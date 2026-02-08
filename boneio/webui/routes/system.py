"""System routes for BoneIO Web UI (logs, restart, version)."""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from boneio.core.config import ConfigHelper
from boneio.core.config.yaml_util import load_config_from_file, update_yaml_field
from boneio.exceptions import ConfigurationException
from boneio.models.logs import LogEntry, LogsResponse
from boneio.version import __version__
from boneio.webui.services.logs import (
    get_standalone_logs,
    get_systemd_logs,
    is_running_as_service,
)

_LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["system"])

# These will be set by app initialization
_app_state = None
_config_helper_getter = None


def set_app_state(app_state):
    """Set app state reference for accessing web_server and yaml_config_file."""
    global _app_state
    _app_state = app_state


def set_config_helper_getter(getter):
    """Set config helper getter function."""
    global _config_helper_getter
    _config_helper_getter = getter


def get_config_helper():
    """Get config helper instance."""
    if _config_helper_getter:
        return _config_helper_getter()
    raise NotImplementedError("Config helper not initialized")


@router.get("/logs")
async def get_logs(since: str = "", limit: int = 100) -> LogsResponse:
    """
    Get logs from either systemd journal or standalone log file.
    
    Args:
        since: Time specification for log retrieval.
        limit: Maximum number of log entries.
        
    Returns:
        LogsResponse with list of log entries.
    """
    try:
        if is_running_as_service():
            log_entries = await get_systemd_logs(since)
            if log_entries:
                return LogsResponse(logs=log_entries)

        log_entries = get_standalone_logs(since, limit)
        if log_entries:
            return LogsResponse(logs=log_entries)

        return LogsResponse(
            logs=[
                LogEntry(
                    timestamp=datetime.now().isoformat(),
                    message="No logs available. Please check if logging is properly configured.",
                    level="4",
                )
            ]
        )

    except Exception as e:
        _LOGGER.warning(f"Error fetching logs: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/restart")
async def restart_service(background_tasks: BackgroundTasks):
    """
    Restart the BoneIO service.
    
    Returns:
        Status response indicating if restart was initiated.
    """
    if not is_running_as_service():
        return {"status": "not available"}

    async def shutdown_and_restart():
        if _app_state and _app_state.web_server:
            await asyncio.sleep(0.1)
            os._exit(0)

    background_tasks.add_task(shutdown_and_restart)
    return {"status": "success"}


@router.get("/version")
async def get_version(config_helper: ConfigHelper = Depends(get_config_helper)):
    """
    Get application version and serial number.
    
    Args:
        config_helper: ConfigHelper instance.
    
    Returns:
        Dictionary with version and serial_no strings.
    """
    return {"version": __version__, "serial_no": config_helper.serial_no}


@router.get("/name")
async def get_name(config_helper: ConfigHelper = Depends(get_config_helper)):
    """
    Get application name from configuration.
    
    Args:
        config_helper: ConfigHelper instance.
        
    Returns:
        Dictionary with name string.
    """
    return {"name": config_helper.name}


class PwaNameRequest(BaseModel):
    """Request model for PWA name change."""
    pwa_name: str


@router.get("/pwa_name")
async def get_pwa_name(config_helper: ConfigHelper = Depends(get_config_helper)):
    """Get PWA short name for Android home screen.

    Returns:
        Dictionary with pwa_name string and max_length.
    """
    serial_suffix = config_helper.serial_no.replace("blk_", "").replace("blk", "")
    return {
        "pwa_name": config_helper.pwa_name,
        "default": f"bIO {serial_suffix}",
        "max_length": 12,
    }


@router.post("/pwa_name")
async def set_pwa_name(
    request: PwaNameRequest,
    config_helper: ConfigHelper = Depends(get_config_helper),
):
    """Set PWA short name (max 12 chars). Saved to YAML config.

    Args:
        request: PwaNameRequest with new pwa_name.

    Returns:
        Status response with saved pwa_name.
    """
    pwa_name = request.pwa_name.strip()

    if not pwa_name:
        raise HTTPException(status_code=400, detail="PWA name cannot be empty")

    if len(pwa_name) > 12:
        raise HTTPException(status_code=400, detail="PWA name too long (max 12 characters)")

    # Update in-memory
    config_helper.pwa_name = pwa_name

    # Persist to YAML config
    try:
        if _app_state and _app_state.yaml_config_file:
            result = update_yaml_field(
                _app_state.yaml_config_file,
                "web.cloud",
                "pwa_name",
                pwa_name,
            )
            if result.get("status") == "error":
                _LOGGER.error("Failed to save pwa_name to config: %s", result.get("message"))
    except Exception as e:
        _LOGGER.error("Error saving pwa_name to config: %s", e)

    _LOGGER.info("PWA name changed to: %s", pwa_name)
    return {"status": "success", "pwa_name": pwa_name}


@router.get("/cloud/status")
async def get_cloud_status():
    """
    Get cloud registration status including domain and last error.

    Returns:
        Dict with enabled, domain, cloud_config_active, and last_error fields.
    """
    config_helper: ConfigHelper | None = getattr(_app_state, "config_helper", None)
    if not config_helper:
        return {"enabled": False}

    cloud_reg = getattr(config_helper, "_cloud_reg", None)
    if not cloud_reg:
        return {
            "enabled": config_helper.cloud_registration,
            "domain": None,
            "cloud_config_active": False,
            "last_error": None,
        }

    return {
        "enabled": cloud_reg.enabled,
        "domain": cloud_reg.domain,
        "cloud_config_active": cloud_reg.is_cloud_config_active(),
        "last_error": cloud_reg.last_error,
    }


@router.post("/cloud/disable")
async def disable_cloud():
    """
    Disable cloud mode by restoring original docker-compose.yaml from package data.

    Returns:
        Status response with success or error message.
    """
    config_helper: ConfigHelper | None = getattr(_app_state, "config_helper", None)
    if not config_helper:
        return {"status": "error", "message": "Config helper not available"}

    cloud_reg = getattr(config_helper, "_cloud_reg", None)
    if not cloud_reg:
        return {"status": "error", "message": "Cloud registration not initialized"}

    success = await cloud_reg._restore_local_config()
    if success:
        return {"status": "success", "message": "Cloud mode disabled, Caddy restored to local certificates"}
    else:
        return {
            "status": "error",
            "message": cloud_reg.last_error or "Failed to restore local config",
        }


@router.get("/check_configuration")
async def check_configuration():
    """
    Check if the configuration file is valid.
    
    Returns:
        Status response with success or error message.
    """
    try:
        if _app_state:
            load_config_from_file(config_file=_app_state.yaml_config_file)
        return {"status": "success"}
    except ConfigurationException as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/status/restart")
async def get_restart_status():
    """
    Get restart status.
    
    Returns:
        Dictionary with restart_pending flag.
    """
    if _app_state:
        return {"restart_pending": getattr(_app_state, 'restart_pending', False)}
    return {"restart_pending": False}


@router.get("/hardware/errors")
async def get_hardware_errors():
    """
    Get hardware initialization errors.
    
    Returns list of hardware errors that occurred during startup,
    such as I2C communication failures with MCP23017/PCF8575/PCA9685.
    
    Returns:
        Dictionary with errors list.
    """
    if _app_state and hasattr(_app_state, 'manager'):
        manager = _app_state.manager
        errors = getattr(manager, '_hardware_errors', [])
        return {"errors": errors}
    return {"errors": []}


class HostnameRequest(BaseModel):
    """Request model for hostname change."""
    hostname: str


@router.get("/hostname")
async def get_hostname():
    """
    Get current system hostname.
    
    Returns:
        Dictionary with hostname string.
    """
    try:
        result = subprocess.run(
            ["hostname"],
            capture_output=True,
            text=True,
            check=True
        )
        hostname = result.stdout.strip()
        return {"hostname": hostname}
    except subprocess.CalledProcessError as e:
        _LOGGER.error(f"Failed to get hostname: {e}")
        raise HTTPException(status_code=500, detail="Failed to get hostname")
    except Exception as e:
        _LOGGER.error(f"Error getting hostname: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/hostname")
async def set_hostname(request: HostnameRequest):
    """
    Set system hostname.
    
    Args:
        request: HostnameRequest with new hostname.
        
    Returns:
        Status response indicating if hostname was changed.
    """
    new_hostname = request.hostname.strip()
    
    if not new_hostname:
        raise HTTPException(status_code=400, detail="Hostname cannot be empty")
    
    if len(new_hostname) > 63:
        raise HTTPException(status_code=400, detail="Hostname too long (max 63 characters)")
    
    if not all(c.isalnum() or c in '-_' for c in new_hostname):
        raise HTTPException(status_code=400, detail="Hostname can only contain alphanumeric characters, hyphens, and underscores")
    
    try:
        subprocess.run(
            ["sudo", "hostnamectl", "set-hostname", new_hostname],
            check=True,
            capture_output=True,
            text=True
        )
        
        _LOGGER.info(f"Hostname changed to: {new_hostname}")
        return {"status": "success", "hostname": new_hostname}
    except subprocess.CalledProcessError as e:
        _LOGGER.error(f"Failed to set hostname: {e.stderr}")
        raise HTTPException(status_code=500, detail=f"Failed to set hostname: {e.stderr}")
    except Exception as e:
        _LOGGER.error(f"Error setting hostname: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reboot")
async def reboot_device(background_tasks: BackgroundTasks):
    """
    Reboot the system device.
    
    This endpoint initiates a system reboot using sudo reboot command.
    The reboot is executed in the background to allow the API to respond first.
    
    Returns:
        Status response indicating if reboot was initiated.
    """
    async def execute_reboot():
        await asyncio.sleep(1)
        try:
            subprocess.run(
                ["sudo", "reboot"],
                check=True,
                capture_output=True,
                text=True
            )
        except subprocess.CalledProcessError as e:
            _LOGGER.error(f"Failed to reboot device: {e.stderr}")
        except Exception as e:
            _LOGGER.error(f"Error rebooting device: {e}")
    
    background_tasks.add_task(execute_reboot)
    _LOGGER.info("System reboot initiated")
    return {"status": "success", "message": "Device is rebooting..."}


@router.post("/shutdown")
async def shutdown_device(background_tasks: BackgroundTasks):
    """
    Shutdown the system device.
    
    This endpoint initiates a system shutdown using sudo shutdown command.
    The shutdown is executed in the background to allow the API to respond first.
    
    Returns:
        Status response indicating if shutdown was initiated.
    """
    async def execute_shutdown():
        await asyncio.sleep(1)
        try:
            subprocess.run(
                ["sudo", "shutdown", "-h", "now"],
                check=True,
                capture_output=True,
                text=True
            )
        except subprocess.CalledProcessError as e:
            _LOGGER.error(f"Failed to shutdown device: {e.stderr}")
        except Exception as e:
            _LOGGER.error(f"Error shutting down device: {e}")
    
    background_tasks.add_task(execute_shutdown)
    _LOGGER.info("System shutdown initiated")
    return {"status": "success", "message": "Device is shutting down..."}
