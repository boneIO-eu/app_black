"""Configuration routes for BoneIO Web UI."""

from __future__ import annotations

import io
import logging
import os
import tarfile
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile

if TYPE_CHECKING:
    from starlette.datastructures import State
from fastapi.responses import StreamingResponse

from boneio.core.config.yaml_util import load_config_from_file, update_config_section, load_yaml_file
from boneio.core.manager import Manager

_LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["config"])

# Config cache to avoid re-parsing YAML on every request
_config_cache: dict = {"data": None, "mtime": 0}

# App state reference - set by app initialization
_app_state: Optional["State"] = None
_websocket_manager = None


def set_app_state(app_state: "State") -> None:
    """Set app state reference."""
    global _app_state
    _app_state = app_state


def set_websocket_manager(ws_manager) -> None:
    """Set websocket manager reference."""
    global _websocket_manager
    _websocket_manager = ws_manager


def _get_app_state() -> "State":
    """Get app state, raising an error if not initialized."""
    if _app_state is None:
        raise HTTPException(status_code=500, detail="App state not initialized")
    return _app_state


def get_manager():
    """Get manager instance - will be overridden by app initialization."""
    raise NotImplementedError("Manager not initialized")


def invalidate_config_cache():
    """Invalidate config cache - call after saving config."""
    _config_cache["data"] = None
    _config_cache["mtime"] = 0


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
        # Use load_yaml_file instead of load_config_from_file to get raw YAML data
        # without TimePeriod parsing - frontend expects strings like "220ms", not objects
        config_data = load_yaml_file(config_file)
        elapsed = time.time() - start
        
        _config_cache["data"] = config_data
        _config_cache["mtime"] = current_mtime
        
        _LOGGER.info("Loaded and cached configuration in %.2fs (mtime: %.0f)", elapsed, current_mtime)
        return {"config": config_data}
        
    except Exception as e:
        _LOGGER.error(f"Error loading parsed configuration: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error loading configuration: {str(e)}")


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
    RESTART_REQUIRED_SECTIONS = {'boneio', 'mqtt', 'web', 'modbus'}
    
    try:
        app_state = _get_app_state()
        result = update_config_section(app_state.yaml_config_file, section, data)
        if result["status"] == "error":
            raise HTTPException(status_code=500, detail=result["message"])
        
        invalidate_config_cache()
        
        if section in RESTART_REQUIRED_SECTIONS:
            manager: Manager = app_state.manager
            manager.config_helper.set_restart_required(section)
            result["restart_required"] = True
            result["restart_required_sections"] = manager.config_helper.restart_required_sections
        
        return result
        
    except Exception as e:
        _LOGGER.error(f"Error saving section '{section}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error saving section: {str(e)}")


@router.post("/config/reload")
async def reload_configuration(
    sections: list[str] | None = Body(None, description="Optional list of sections to reload")
):
    """
    Reload configuration from file.
    
    Supports hot-reloading of: output, cover, input, event, binary_sensor, modbus_devices, sensor.
    
    Args:
        sections: Optional list of section names to reload.
        
    Returns:
        Status of reload operation.
    """
    manager: Manager = _get_app_state().manager
    
    try:
        from boneio.models.events import ConfigReloadEvent
        reload_event = ConfigReloadEvent(sections=sections or ["all"])
        if _websocket_manager:
            await _websocket_manager.broadcast(reload_event.model_dump())
        
        result = await manager.reload_config(reload_sections=sections)
        
        if result.get("status") == "error":
            raise HTTPException(
                status_code=500,
                detail=result.get("message", "Failed to reload configuration")
            )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        _LOGGER.error(f"Error reloading config: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error reloading config: {str(e)}")


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
    
    with tarfile.open(fileobj=buffer, mode='w:gz') as tar:
        for pattern in ["*.yaml", "*.yml"]:
            for yaml_file in config_dir.glob(pattern):
                if yaml_file.is_file():
                    arcname = yaml_file.name
                    tar.add(str(yaml_file), arcname=arcname)
                    _LOGGER.debug(f"Added {arcname} to config archive")
        
        for subdir in config_dir.iterdir():
            if subdir.is_dir() and not subdir.name.startswith('.'):
                for pattern in ["*.yaml", "*.yml"]:
                    for yaml_file in subdir.glob(pattern):
                        if yaml_file.is_file():
                            arcname = f"{subdir.name}/{yaml_file.name}"
                            tar.add(str(yaml_file), arcname=arcname)
                            _LOGGER.debug(f"Added {arcname} to config archive")
    
    buffer.seek(0)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"boneio_config_{timestamp}.tar.gz"
    
    _LOGGER.info(f"Downloading config archive: {filename}")
    
    return StreamingResponse(
        buffer,
        media_type="application/gzip",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.post("/config/restore")
async def restore_config(file: UploadFile = File(...)):
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
        if not file.filename or not file.filename.endswith(('.tar.gz', '.tgz')):
            return {
                "status": "error",
                "message": "Invalid file type. Please upload a .tar.gz or .tgz file."
            }
        
        contents = await file.read()
        buffer = io.BytesIO(contents)
        
        # Create backup
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = config_dir / "backups"
        backup_dir.mkdir(exist_ok=True)
        backup_path = backup_dir / f"config_backup_{timestamp}.tar.gz"
        
        with tarfile.open(backup_path, mode='w:gz') as tar:
            for pattern in ["*.yaml", "*.yml"]:
                for yaml_file in config_dir.glob(pattern):
                    if yaml_file.is_file():
                        tar.add(str(yaml_file), arcname=yaml_file.name)
            
            for subdir in config_dir.iterdir():
                if subdir.is_dir() and not subdir.name.startswith('.') and subdir.name != 'backups':
                    for pattern in ["*.yaml", "*.yml"]:
                        for yaml_file in subdir.glob(pattern):
                            if yaml_file.is_file():
                                tar.add(str(yaml_file), arcname=f"{subdir.name}/{yaml_file.name}")
        
        _LOGGER.info(f"Created backup before restore: {backup_path}")
        
        # Extract and restore
        restored_files = []
        with tarfile.open(fileobj=buffer, mode='r:gz') as tar:
            members = tar.getmembers()
            for member in members:
                if '..' in member.name or member.name.startswith('/'):
                    return {
                        "status": "error",
                        "message": f"Invalid file path in archive: {member.name}"
                    }
                
                if not (member.name.endswith('.yaml') or member.name.endswith('.yml')):
                    _LOGGER.warning(f"Skipping non-YAML file: {member.name}")
                    continue
            
            for member in members:
                if member.name.endswith('.yaml') or member.name.endswith('.yml'):
                    target_path = config_dir / member.name
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    source = tar.extractfile(member)
                    if source is None:
                        _LOGGER.warning(f"Could not extract {member.name}")
                        continue
                    
                    with source:
                        with open(target_path, 'wb') as target:
                            target.write(source.read())
                    
                    restored_files.append(member.name)
                    _LOGGER.info(f"Restored: {member.name}")
        
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
            "validation_message": validation_message
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
    
    Returns:
        List of unique interlock group names.
    """
    manager = _get_app_state().manager
    if not manager or not hasattr(manager, '_output_manager'):
        return {"groups": []}
    
    output_manager = manager._output_manager
    if not output_manager or not hasattr(output_manager, '_interlock_manager'):
        return {"groups": []}
    
    groups = output_manager._interlock_manager.get_all_groups()
    return {"groups": groups}


@router.get("/files")
async def list_files(path: Optional[str] = None):
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
                    items.append({
                        "name": entry.name,
                        "path": relative_path,
                        "type": "directory",
                        "children": children
                    })
            elif entry.is_file():
                if entry.name.endswith(('.yaml', '.yml')):
                    items.append({
                        "name": entry.name,
                        "path": relative_path,
                        "type": "file"
                    })
        return items

    try:
        items = [{"name": "config", "path": "", "type": "directory", "children": scan_directory(base_dir)}]
        return {"items": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
    
    if not full_path.endswith(('.yaml', '.yml', '.json')):
        raise HTTPException(status_code=400, detail="Invalid file type")
    
    try:
        with open(full_path) as f:
            content = f.read()
        return {"content": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
    
    if not full_path.endswith(('.yaml', '.yml', '.json')):
        raise HTTPException(status_code=400, detail="Invalid file type")
    
    try:
        with open(full_path, 'w') as f:
            f.write(content["content"])
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
