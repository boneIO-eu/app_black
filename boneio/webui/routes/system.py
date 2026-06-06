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
async def get_logs(
    limit: int = 200,
    before: str | None = None,
    priority: str | None = None,
    since: str | None = None,
    until: str | None = None,
    grep: str | None = None,
) -> LogsResponse:
    """
    Get logs with cursor-based pagination and optional filtering.
    
    Args:
        limit: Maximum number of log entries to return.
        before: Timestamp cursor — return entries older than this.
        priority: Log level filter (systemd only, e.g. '3' for err, '0..4' for range).
        since: Start of date range filter (ISO or microsecond timestamp).
        until: End of date range filter (ISO or microsecond timestamp).
        grep: Text search filter (case-insensitive substring match).
        
    Returns:
        LogsResponse with list of log entries, has_more flag, and source.
    """
    try:
        if is_running_as_service():
            log_entries, has_more = await get_systemd_logs(
                limit, before, priority, since, until, grep
            )
            if log_entries:
                return LogsResponse(
                    logs=log_entries, has_more=has_more, source="systemd"
                )

        log_entries, has_more = get_standalone_logs(limit, before, since, until, grep)
        if log_entries:
            return LogsResponse(
                logs=log_entries, has_more=has_more, source="standalone"
            )

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
        _LOGGER.warning("Error fetching logs: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


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
        "compose_writable": cloud_reg.is_compose_writable,
        "last_error": cloud_reg.last_error,
    }


class SudoFixRequest(BaseModel):
    """Request body for fixing docker-compose.yaml permissions via sudo."""
    password: str


def _get_compose_info() -> dict:
    """Get detailed info about docker-compose.yaml file.

    Returns:
        Dictionary with file path, existence, owner, permissions, etc.
    """
    import pwd
    import stat

    compose_path = os.path.expanduser("~/docker/nodered/docker-compose.yaml")
    current_user = os.environ.get("USER", "boneio")
    current_uid = os.getuid()

    info = {
        "compose_path": compose_path,
        "current_user": current_user,
        "current_uid": current_uid,
        "file_exists": os.path.exists(compose_path),
    }

    if info["file_exists"]:
        st = os.stat(compose_path)
        try:
            file_owner = pwd.getpwuid(st.st_uid).pw_name
        except KeyError:
            file_owner = str(st.st_uid)
        info.update({
            "file_owner": file_owner,
            "file_uid": st.st_uid,
            "file_gid": st.st_gid,
            "file_mode": stat.filemode(st.st_mode),
            "writable": os.access(compose_path, os.W_OK),
            "readable": os.access(compose_path, os.R_OK),
        })
    return info


@router.get("/cloud/test-permissions")
async def test_compose_permissions():
    """Diagnostic endpoint: check docker-compose.yaml file permissions.

    Returns:
        Detailed file info including path, owner, permissions, writability.
    """
    info = _get_compose_info()
    _LOGGER.info("Permission test: %s", info)
    return info


@router.post("/cloud/fix-permissions")
async def fix_compose_permissions(body: SudoFixRequest):
    """Fix docker-compose.yaml ownership using sudo chown.

    Accepts the user's sudo password, runs 'sudo chown' on docker-compose.yaml,
    and returns success/error. The password is never logged or stored.

    Returns:
        Status response with success or error message.
    """
    info = _get_compose_info()
    compose_path = info["compose_path"]
    current_user = info["current_user"]

    _LOGGER.info(
        "Fix permissions requested. File: %s, exists: %s, writable: %s, owner: %s, current_user: %s",
        compose_path,
        info.get("file_exists"),
        info.get("writable"),
        info.get("file_owner"),
        current_user,
    )

    if not info["file_exists"]:
        return {"status": "error", "message": f"File not found: {compose_path}"}

    if info.get("writable"):
        return {"status": "success", "message": "File is already writable"}

    try:
        cmd = ["sudo", "-S", "chown", f"{current_user}:{current_user}", compose_path]
        _LOGGER.info("Running: %s", " ".join(cmd))

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=(body.password + "\n").encode()),
            timeout=10,
        )

        stdout_str = stdout.decode().strip()
        stderr_str = stderr.decode().strip()
        _LOGGER.info(
            "sudo chown result: returncode=%s, stdout=%r, stderr=%r",
            proc.returncode, stdout_str, stderr_str,
        )

        if proc.returncode == 0:
            after = _get_compose_info()
            _LOGGER.info("After fix: %s", after)
            return {
                "status": "success",
                "message": "Permissions fixed successfully",
                "before": info,
                "after": after,
            }
        else:
            if "incorrect password" in stderr_str.lower() or "sorry" in stderr_str.lower():
                return {"status": "error", "message": "Incorrect sudo password"}
            return {"status": "error", "message": f"sudo failed: {stderr_str}"}

    except TimeoutError:
        _LOGGER.error("sudo chown timed out for %s", compose_path)
        return {"status": "error", "message": "sudo command timed out"}
    except Exception as e:
        _LOGGER.error("Failed to fix permissions: %s", e)
        return {"status": "error", "message": str(e)}


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
    errors = []
    
    if _app_state and hasattr(_app_state, 'manager'):
        manager = _app_state.manager
        hw_errors = getattr(manager, '_hardware_errors', [])
        errors.extend(hw_errors)
    
    return {"errors": errors}


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
        _LOGGER.error("Failed to get hostname: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get hostname") from e
    except Exception as e:
        _LOGGER.error("Error getting hostname: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


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
        _LOGGER.error("Failed to set hostname: %s", e.stderr)
        raise HTTPException(status_code=500, detail=f"Failed to set hostname: {e.stderr}") from e
    except Exception as e:
        _LOGGER.error("Error setting hostname: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


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


class LogLevelRequest(BaseModel):
    """Request model for temporary log level change."""
    level: str


# Store the original log level so we can restore it
_original_log_level: int | None = None


@router.get("/log-level")
async def get_log_level():
    """
    Get current root logger level and whether debug mode is temporarily active.

    Returns:
        Dictionary with current level name and debug_active flag.
    """
    root = logging.getLogger()
    current = root.level
    return {
        "level": logging.getLevelName(current),
        "debug_active": current <= logging.DEBUG and _original_log_level is not None,
    }


@router.post("/log-level")
async def set_log_level(request: LogLevelRequest):
    """
    Temporarily change root logger level at runtime (not persisted to YAML).

    Supports 'DEBUG', 'INFO', 'WARNING', 'ERROR'.
    Use 'RESTORE' to revert to the original level.

    Args:
        request: LogLevelRequest with desired level string.

    Returns:
        Status response with new level name.
    """
    global _original_log_level
    root = logging.getLogger()
    level_name = request.level.upper()

    if level_name == "RESTORE":
        if _original_log_level is not None:
            root.setLevel(_original_log_level)
            restored = logging.getLevelName(_original_log_level)
            _original_log_level = None
            _LOGGER.info("Log level restored to %s", restored)
            return {"status": "success", "level": restored}
        return {"status": "success", "level": logging.getLevelName(root.level)}

    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
    }

    if level_name not in level_map:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid level: {request.level}. Use DEBUG, INFO, WARNING, ERROR, or RESTORE.",
        )

    # Save original level before first temporary change
    if _original_log_level is None:
        _original_log_level = root.level

    root.setLevel(level_map[level_name])
    _LOGGER.info("Log level temporarily changed to %s", level_name)
    return {"status": "success", "level": level_name}


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


# ── Timezone & NTP ──────────────────────────────────────────────────────


class TimezoneRequest(BaseModel):
    """Request model for timezone change."""
    timezone: str


class NtpRequest(BaseModel):
    """Request model for NTP enable/disable."""
    enabled: bool


def _parse_timedatectl() -> dict:
    """Parse timedatectl output into a dictionary.

    Returns:
        Dictionary with keys like 'Time zone', 'NTP service', etc.
    """
    try:
        result = subprocess.run(
            ["timedatectl", "show"],
            capture_output=True,
            text=True,
            check=True,
        )
        info: dict[str, str] = {}
        for line in result.stdout.strip().splitlines():
            if "=" in line:
                key, _, value = line.partition("=")
                info[key.strip()] = value.strip()
        return info
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Fallback: parse human-readable output
        try:
            result = subprocess.run(
                ["timedatectl"],
                capture_output=True,
                text=True,
                check=True,
            )
            info = {}
            for line in result.stdout.strip().splitlines():
                if ":" in line:
                    key, _, value = line.partition(":")
                    info[key.strip()] = value.strip()
            return info
        except Exception as exc:
            _LOGGER.error("Failed to parse timedatectl output: %s", exc)
            return {}


@router.get("/timezone")
async def get_timezone():
    """
    Get current system timezone and NTP status.

    Returns:
        Dictionary with timezone, NTP status, and current time.
    """
    info = _parse_timedatectl()

    # timedatectl show uses key=value pairs
    timezone = info.get("Timezone", "")
    ntp_active = info.get("NTPSynchronized", "").lower() == "yes"
    ntp_enabled = info.get("NTP", "").lower() in ("yes", "active")

    # Fallback: read human-readable keys
    if not timezone:
        tz_val = info.get("Time zone", "")
        # e.g. "Europe/Warsaw (CEST, +0200)"
        timezone = tz_val.split("(")[0].strip() if tz_val else ""

    if not timezone:
        # Last resort: read /etc/timezone
        try:
            with open("/etc/timezone") as f:
                timezone = f.read().strip()
        except FileNotFoundError:
            timezone = "UTC"

    # Get current system time
    try:
        local_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        local_time = ""

    return {
        "timezone": timezone,
        "ntp_synchronized": ntp_active,
        "ntp_enabled": ntp_enabled,
        "local_time": local_time,
    }


@router.post("/timezone")
async def set_timezone(request: TimezoneRequest):
    """
    Set system timezone via timedatectl.

    Args:
        request: TimezoneRequest with timezone string (e.g. 'Europe/Warsaw').

    Returns:
        Status response.
    """
    tz = request.timezone.strip()
    if not tz:
        raise HTTPException(status_code=400, detail="Timezone cannot be empty")

    # Validate timezone exists in system
    zoneinfo_path = f"/usr/share/zoneinfo/{tz}"
    if not os.path.isfile(zoneinfo_path):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid timezone: {tz}. Must be a valid IANA timezone.",
        )

    try:
        subprocess.run(
            ["sudo", "timedatectl", "set-timezone", tz],
            check=True,
            capture_output=True,
            text=True,
        )
        _LOGGER.info("Timezone changed to: %s", tz)
        return {"status": "success", "timezone": tz}
    except subprocess.CalledProcessError as e:
        _LOGGER.error("Failed to set timezone: %s", e.stderr)
        raise HTTPException(
            status_code=500, detail=f"Failed to set timezone: {e.stderr}"
        ) from e
    except Exception as e:
        _LOGGER.error("Error setting timezone: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/ntp")
async def set_ntp(request: NtpRequest):
    """
    Enable or disable NTP time synchronization via timedatectl.

    Args:
        request: NtpRequest with enabled boolean.

    Returns:
        Status response.
    """
    action = "true" if request.enabled else "false"
    try:
        subprocess.run(
            ["sudo", "timedatectl", "set-ntp", action],
            check=True,
            capture_output=True,
            text=True,
        )
        _LOGGER.info("NTP %s", "enabled" if request.enabled else "disabled")
        return {"status": "success", "ntp_enabled": request.enabled}
    except subprocess.CalledProcessError as e:
        _LOGGER.error("Failed to set NTP: %s", e.stderr)
        raise HTTPException(
            status_code=500, detail=f"Failed to set NTP: {e.stderr}"
        ) from e
    except Exception as e:
        _LOGGER.error("Error setting NTP: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/timezones")
async def list_timezones():
    """
    List available timezones from timedatectl.

    Returns:
        List of timezone strings.
    """
    try:
        result = subprocess.run(
            ["timedatectl", "list-timezones"],
            capture_output=True,
            text=True,
            check=True,
        )
        timezones = [tz.strip() for tz in result.stdout.strip().splitlines() if tz.strip()]
        return {"timezones": timezones}
    except subprocess.CalledProcessError as e:
        _LOGGER.error("Failed to list timezones: %s", e.stderr)
        raise HTTPException(status_code=500, detail="Failed to list timezones") from e
    except Exception as e:
        _LOGGER.error("Error listing timezones: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


# ── Timezone Sudoers ─────────────────────────────────────────────────────


class TimezoneSudoersFixRequest(BaseModel):
    """Request body for creating timedatectl sudoers file."""
    password: str


@router.get("/timezone/sudoers/check")
async def check_timezone_sudoers():
    """Check if sudoers NOPASSWD is configured for timedatectl commands.

    Returns:
        Dict with needs_password, sudoers_file_exists, and error fields.
    """
    from boneio.webui.routes.timezone_sudoers import (
        check_sudo_nopasswd_for_timedatectl,
    )

    return await check_sudo_nopasswd_for_timedatectl()


@router.post("/timezone/sudoers/fix")
async def fix_timezone_sudoers(body: TimezoneSudoersFixRequest):
    """Create /etc/sudoers.d/boneio-timedatectl with NOPASSWD rules.

    Accepts the user's sudo password, validates the sudoers content,
    and installs it. The password is never logged or stored.

    Returns:
        Status response with success or error message.
    """
    from boneio.webui.routes.timezone_sudoers import (
        create_timedatectl_sudoers_file,
    )

    return await create_timedatectl_sudoers_file(body.password)

