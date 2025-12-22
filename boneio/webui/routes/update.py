"""Update routes for BoneIO Web UI."""

from __future__ import annotations

import asyncio
import glob
import logging
import os
import shutil
import subprocess
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

from boneio.version import __version__
from boneio.webui.services.logs import is_running_as_service
from boneio.core.config.yaml_util import load_config_from_file

_LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["update"])

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


@router.get("/check_update")
async def check_update():
    """
    Check if there is a newer version of BoneIO available from GitHub releases.
    
    Returns:
        Update information including available versions.
    """
    current_version = __version__
    
    try:
        import requests
    except ImportError:
        _LOGGER.error("Package 'requests' is not installed")
        return {
            "status": "error",
            "message": "Package 'requests' is not installed. Run: pip install requests",
            "current_version": current_version
        }
    
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
        repo = "boneIO-eu/app_black"
        api_url = f'https://api.github.com/repos/{repo}/releases'
        response = requests.get(api_url, timeout=10)
        
        if response.status_code != 200:
            return {
                "status": "error",
                "message": f"Failed to fetch releases: {response.text}",
                "current_version": current_version
            }
        
        releases = response.json()
        
        if not releases:
            return {
                "status": "error",
                "message": "No releases found on GitHub",
                "current_version": current_version
            }
        
        available_versions = []
        latest_stable = None
        latest_prerelease = None
        
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
            
            if not is_prerelease and latest_stable is None:
                latest_stable = ver_info
            if is_prerelease and latest_prerelease is None:
                latest_prerelease = ver_info
        
        current_ver_lower = current_version.lower()
        current_is_prerelease = any(x in current_ver_lower for x in ['dev', 'alpha', 'beta', 'rc'])
        
        if current_is_prerelease:
            recommended = latest_prerelease or latest_stable or available_versions[0]
        else:
            recommended = latest_stable or latest_prerelease or available_versions[0]
        
        is_update_available = False
        prerelease_update_available = False
        try:
            current_parsed = version.parse(current_version)
            recommended_parsed = version.parse(recommended["version"])
            is_update_available = recommended_parsed > current_parsed
            
            if current_is_prerelease and latest_prerelease:
                prerelease_parsed = version.parse(latest_prerelease["version"])
                if prerelease_parsed > current_parsed:
                    is_update_available = True
                    recommended = latest_prerelease
            
            if not current_is_prerelease and latest_prerelease:
                prerelease_parsed = version.parse(latest_prerelease["version"])
                if prerelease_parsed > current_parsed:
                    prerelease_update_available = True
        except Exception as e:
            _LOGGER.warning("Error parsing versions for comparison: %s", str(e))
            is_update_available = False
        
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
async def update_boneio(background_tasks: BackgroundTasks, request: UpdateRequest = UpdateRequest()):
    """
    Update the BoneIO package with backup and restart the service.
    
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
    
    target_version = request.version

    async def update_and_restart():
        global _update_status
        current_version = __version__
        
        _reset_update_status()
        _update_status["status"] = "running"
        _update_status["old_version"] = current_version
        _update_status["target_version"] = target_version
        
        try:
            await asyncio.sleep(0.3)
            
            _update_progress(5, "Finding virtual environment...")
            
            possible_venv_paths = [
                os.path.expanduser("~/boneio/venv"),
                os.path.expanduser("~/venv"),
                "/opt/boneio/venv",
            ]
            
            venv_path = None
            pip_path = None
            for path in possible_venv_paths:
                pip_candidate = os.path.join(path, "bin", "pip")
                if os.path.exists(pip_candidate):
                    venv_path = path
                    pip_path = pip_candidate
                    break
            
            if not pip_path:
                _update_status["status"] = "error"
                _update_status["error"] = "Virtual environment not found"
                _update_progress(0, "Failed", "Could not find virtual environment")
                return
            
            _update_progress(10, "Virtual environment found", f"Using venv at {venv_path}")
            
            _update_progress(15, "Creating backup...")
            
            backup_dir = os.path.expanduser("~/boneio_backups")
            os.makedirs(backup_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(backup_dir, f"boneio_{current_version}_{timestamp}")
            
            boneio_dirs = glob.glob(f"{venv_path}/lib/python*/site-packages/boneio")
            
            if boneio_dirs:
                try:
                    shutil.copytree(boneio_dirs[0], backup_path)
                    _update_status["backup_path"] = backup_path
                    _update_progress(25, "Backup created", f"Backup saved to {backup_path}")
                except Exception as e:
                    _update_progress(25, "Backup warning", f"Could not create backup: {e}")
            else:
                _update_progress(25, "Backup skipped", "No existing boneio package found")
            
            _update_progress(30, "Upgrading pip...")
            
            pip_upgrade = subprocess.run(
                [pip_path, "install", "--upgrade", "pip"],
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if pip_upgrade.returncode == 0:
                _update_progress(40, "Pip upgraded", "pip upgraded successfully")
            else:
                _update_progress(40, "Pip upgrade skipped", "pip upgrade failed, continuing...")
            
            if target_version:
                _update_progress(45, f"Downloading and installing BoneIO {target_version}...")
                pip_package = f"boneio=={target_version}"
            else:
                _update_progress(45, "Downloading and installing latest BoneIO...")
                pip_package = "boneio"
            
            result = subprocess.run(
                [pip_path, "install", "--upgrade", pip_package],
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode != 0:
                _update_status["status"] = "error"
                _update_status["error"] = f"pip install failed: {result.stderr}"
                _update_progress(45, "Update failed", result.stderr)
                return
            
            _update_progress(80, "BoneIO updated", "Package installed successfully")
            
            _update_progress(85, "Verifying installation...")
            
            version_result = subprocess.run(
                [pip_path, "show", "boneio"],
                capture_output=True,
                text=True
            )
            
            new_version = current_version
            if version_result.returncode == 0:
                for line in version_result.stdout.split('\n'):
                    if line.startswith('Version:'):
                        new_version = line.split(':')[1].strip()
                        break
            
            _update_status["new_version"] = new_version
            _update_progress(90, "Installation verified", f"Updated from {current_version} to {new_version}")
            
            _update_progress(92, "Cleaning up old backups...")
            
            try:
                backups = sorted(glob.glob(os.path.join(backup_dir, "boneio_*")))
                if len(backups) > 5:
                    for old_backup in backups[:-5]:
                        shutil.rmtree(old_backup, ignore_errors=True)
                    _update_progress(95, "Cleanup done", f"Removed {len(backups) - 5} old backups")
            except Exception as e:
                _update_progress(95, "Cleanup skipped", f"Could not cleanup: {e}")
            
            _update_status["status"] = "success"
            _update_progress(100, "Update complete!", f"Restarting service in 2 seconds...")
            
            await asyncio.sleep(2)
            
            _LOGGER.info("Restarting BoneIO service after update...")
            os._exit(0)
            
        except subprocess.TimeoutExpired:
            _update_status["status"] = "error"
            _update_status["error"] = "Update timed out"
            _update_progress(0, "Timeout", "Update process timed out")
        except Exception as e:
            _update_status["status"] = "error"
            _update_status["error"] = str(e)
            _update_progress(0, "Error", f"Unexpected error: {e}")
            _LOGGER.error(f"Error during update process: {e}", exc_info=True)
    
    background_tasks.add_task(update_and_restart)
    return {"status": "started", "message": "Update process started"}


@router.post("/update/rollback")
async def rollback_update():
    """
    Rollback to the previous version from backup.
    
    Returns:
        Status response.
    """
    if not is_running_as_service():
        return {"status": "error", "message": "Rollback is only available when running as a service"}
    
    backup_dir = os.path.expanduser("~/boneio_backups")
    backups = sorted(glob.glob(os.path.join(backup_dir, "boneio_*")))
    
    if not backups:
        return {"status": "error", "message": "No backups found"}
    
    latest_backup = backups[-1]
    
    possible_venv_paths = [
        os.path.expanduser("~/boneio/venv"),
        os.path.expanduser("~/venv"),
        "/opt/boneio/venv",
    ]
    
    venv_path = None
    for path in possible_venv_paths:
        if os.path.exists(os.path.join(path, "bin", "pip")):
            venv_path = path
            break
    
    if not venv_path:
        return {"status": "error", "message": "Virtual environment not found"}
    
    boneio_dirs = glob.glob(f"{venv_path}/lib/python*/site-packages/boneio")
    
    if not boneio_dirs:
        return {"status": "error", "message": "Current boneio installation not found"}
    
    try:
        shutil.rmtree(boneio_dirs[0])
        shutil.copytree(latest_backup, boneio_dirs[0])
        
        _LOGGER.info(f"Rolled back to backup: {latest_backup}")
        
        return {
            "status": "success", 
            "message": f"Rolled back to {os.path.basename(latest_backup)}. Restart required.",
            "backup_used": latest_backup
        }
    except Exception as e:
        return {"status": "error", "message": f"Rollback failed: {e}"}


@router.get("/update/backups")
async def list_backups():
    """
    List available backups.
    
    Returns:
        List of backup information.
    """
    backup_dir = os.path.expanduser("~/boneio_backups")
    backups = sorted(glob.glob(os.path.join(backup_dir, "boneio_*")), reverse=True)
    
    backup_list = []
    for backup in backups:
        name = os.path.basename(backup)
        parts = name.split('_')
        version = parts[1] if len(parts) > 1 else "unknown"
        timestamp = f"{parts[2]}_{parts[3]}" if len(parts) > 3 else "unknown"
        
        backup_list.append({
            "path": backup,
            "name": name,
            "version": version,
            "timestamp": timestamp,
        })
    
    return {"backups": backup_list}


# Available device types for factory reset
DEVICE_TYPES = ["24x16", "32x10", "cover", "cover_mix"]


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


@router.post("/factory_reset")
async def factory_reset(request: FactoryResetRequest):
    """
    Reset configuration to factory defaults for selected device type.
    
    This will:
    1. Create a backup of current configuration
    2. Remove old configuration files
    3. Copy example config files for the selected device type
    4. Restart the application
    
    Args:
        request: Device type to reset to (24x16, 32x10, cover, cover_mix)
        
    Returns:
        Status response.
    """
    device_type = request.device_type.lower()
    
    if device_type not in DEVICE_TYPES:
        return {
            "status": "error",
            "message": f"Invalid device type: {device_type}. Available: {', '.join(DEVICE_TYPES)}"
        }
    
    # Find example config directory
    # First try relative to boneio package
    import boneio
    boneio_path = os.path.dirname(boneio.__file__)
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
        for example_file in example_files:
            filename = os.path.basename(example_file)
            dest_path = os.path.join(config_dir, filename)
            shutil.copy2(example_file, dest_path)
            copied_files.append(filename)
            _LOGGER.info(f"Copied {filename} to {config_dir}")
        
        _LOGGER.info(f"Factory reset completed for device type: {device_type}")
        
        return {
            "status": "success",
            "message": f"Configuration reset to {device_type} defaults",
            "backup_path": backup_path if yaml_files else None,
            "copied_files": copied_files,
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
            "message": f"Configuration restored from backup",
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
    """
    Get the MQTT username from configuration.
    
    Returns the username that the application uses to connect to MQTT broker.
    This is used to warn users when changing this password.
    
    Returns:
        Username from mqtt.username config or 'boneio' as default
    """
    try:
        # Try to read from config directory
        config_dir = os.path.expanduser("~/.boneio")
        mqtt_config_path = os.path.join(config_dir, "mqtt.yaml")
        
        if os.path.exists(mqtt_config_path):
            config = load_config_from_file(mqtt_config_path)
            if config:
                mqtt_config = config.get("mqtt", {})
                username = mqtt_config.get("username", "boneio")
            else:
                username = "boneio"
        else:
            # Fallback to default
            username = "boneio"
        
        return {
            "status": "success",
            "username": username
        }
    except Exception as e:
        _LOGGER.exception(f"Failed to get MQTT username: {e}")
        # Return default if config reading fails
        return {
            "status": "success",
            "username": "boneio"
        }


class MqttPasswordChangeRequest(BaseModel):
    """Request model for MQTT password change."""
    username: str
    new_password: str


@router.post("/mqtt/change_password")
async def change_mqtt_password(request: MqttPasswordChangeRequest):
    """
    Change MQTT password for specified user.
    
    Supports three users: boneio, homeassistant, mqtt
    Uses mosquitto_passwd to update password file.
    
    WARNING: This endpoint sends passwords in plain text over HTTP.
    Use only over HTTPS or in a trusted local network.
    
    Args:
        request: Username and new password
        
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
    
    # Path to mosquitto password file
    passwd_file = "/etc/mosquitto/passwd"
    
    try:
        # Check if mosquitto_passwd command exists
        check_cmd = subprocess.run(
            ["which", "mosquitto_passwd"],
            capture_output=True,
            text=True
        )
        
        if check_cmd.returncode != 0:
            return {
                "status": "error",
                "message": "mosquitto_passwd command not found. Is Mosquitto installed?"
            }
        
        # Use mosquitto_passwd to update password
        # -b = batch mode (password on command line)
        result = subprocess.run(
            ["sudo", "mosquitto_passwd", "-b", passwd_file, request.username, request.new_password],
            capture_output=True,
            text=True,
            check=True
        )
        
        _LOGGER.info(f"MQTT password changed for user: {request.username}")
        
        # Reload mosquitto to apply changes
        try:
            reload_result = subprocess.run(
                ["sudo", "systemctl", "reload", "mosquitto"],
                capture_output=True,
                text=True,
                check=True
            )
            _LOGGER.info("Mosquitto service reloaded successfully")
        except subprocess.CalledProcessError as e:
            _LOGGER.warning(f"Failed to reload mosquitto service: {e.stderr}")
            # Don't fail the whole operation if reload fails
        
        return {
            "status": "success",
            "message": f"Password changed successfully for user: {request.username}"
        }
        
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
