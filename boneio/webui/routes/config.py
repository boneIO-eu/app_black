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

from boneio.core.config.yaml_util import (
    load_config_from_file,
    update_config_section,
    load_yaml_file,
    normalize_board_name,
    normalize_version,
    get_board_config_path,
)
from boneio.core.manager import Manager
from boneio.version import __version__

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
        
        # Enrich output entities with generated IDs if not explicitly defined
        # Strategy: explicit 'id' > 'boneio_output' > 'name' (slugified)
        if "output" in config_data and isinstance(config_data["output"], list):
            for output in config_data["output"]:
                if not output.get("id"):
                    # Use boneio_output as id if available
                    if output.get("boneio_output"):
                        output["id"] = output["boneio_output"]
                    elif output.get("name"):
                        # Slugify name as fallback
                        import re
                        name = output["name"].lower()
                        name = re.sub(r'[^a-z0-9]+', '_', name)
                        output["id"] = name.strip('_')
        
        # Enrich cover entities with generated IDs if not explicitly defined
        if "cover" in config_data and isinstance(config_data["cover"], list):
            for cover in config_data["cover"]:
                if not cover.get("id"):
                    # Generate ID from open_relay and close_relay (same logic as CoverManager)
                    open_relay = cover.get("open_relay", "")
                    close_relay = cover.get("close_relay", "")
                    if open_relay and close_relay:
                        cover["id"] = f"cover_{open_relay}_{close_relay}".lower().replace(" ", "_")
        
        # Enrich output_group entities with generated IDs if not explicitly defined
        # Strategy: explicit 'id' > 'name' (slugified)
        if "output_group" in config_data and isinstance(config_data["output_group"], list):
            import re
            for group in config_data["output_group"]:
                if not group.get("id"):
                    if group.get("name"):
                        name = group["name"].lower()
                        name = re.sub(r'[^a-z0-9]+', '_', name)
                        group["id"] = name.strip('_')
        
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
    RESTART_REQUIRED_SECTIONS = {'boneio', 'mqtt', 'web', 'modbus', 'mcp23017'}
    
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
        
        # Create backup with version in filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = config_dir / "backups"
        backup_dir.mkdir(exist_ok=True)
        backup_path = backup_dir / f"config_backup_v{__version__}_{timestamp}.tar.gz"
        
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
        raise HTTPException(status_code=500, detail=f"Failed to load config: {e}")
    
    # Load new board config
    try:
        board_file = get_board_config_path(f"output_{normalized_type}", normalized_version)
        input_file = get_board_config_path("input", normalized_version)
        board_config = load_yaml_file(board_file)
        input_config = load_yaml_file(input_file)
    except Exception as e:
        _LOGGER.error("Failed to load board config for %s: %s", normalized_type, e)
        raise HTTPException(
            status_code=400, 
            detail=f"Board config not found for {new_device_type} version {version}"
        )
    
    output_mapping = board_config.get("output_mapping", {})
    input_mapping = input_config.get("input_mapping", {})
    
    # Check incompatible outputs
    incompatible_outputs = []
    for output in (current_config or {}).get("output", []):
        boneio_output = output.get("boneio_output")
        if boneio_output:
            if boneio_output.lower() not in output_mapping:
                incompatible_outputs.append({
                    "boneio_output": boneio_output,
                    "id": output.get("id", boneio_output),
                    "name": output.get("name", output.get("id", boneio_output)),
                })
    
    # Check incompatible inputs (events and binary_sensors)
    incompatible_inputs = []
    config_data = current_config or {}
    for section in ["event", "binary_sensor"]:
        for input_item in config_data.get(section, []):
            boneio_input = input_item.get("boneio_input")
            if boneio_input:
                if boneio_input.lower() not in input_mapping:
                    incompatible_inputs.append({
                        "boneio_input": boneio_input,
                        "id": input_item.get("id", boneio_input),
                        "section": section,
                    })
    
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
                
                available_example_files.append({
                    "filename": filename,
                    "category": category,
                    "path": os.path.join(example_dir, filename),
                })
    
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
                with tarfile.open(backup_file, 'r:gz') as tar:
                    file_count = len(tar.getmembers())
            except Exception:
                pass
            
            backups.append({
                "path": str(backup_file),
                "filename": backup_file.name,
                "version": version or "unknown",
                "timestamp": formatted_timestamp,
                "timestamp_raw": timestamp_str,
                "size": backup_file.stat().st_size,
                "file_count": file_count,
            })
        except Exception as e:
            _LOGGER.warning(f"Error processing backup {backup_file}: {e}")
            continue
    
    return {"backups": backups}


@router.post("/config/restore_backup")
async def restore_config_backup(backup_path: str = Body(..., embed=True)):
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
        
        with tarfile.open(new_backup_path, mode='w:gz') as tar:
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
        
        _LOGGER.info(f"Created backup before restore: {new_backup_path}")
        
        # Restore from selected backup
        restored_files = []
        with tarfile.open(backup_file, mode='r:gz') as tar:
            members = tar.getmembers()
            for member in members:
                if '..' in member.name or member.name.startswith('/'):
                    continue
                
                if member.name.endswith(('.yaml', '.yml')):
                    target_path = config_dir / member.name
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    source = tar.extractfile(member)
                    if source is None:
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
            "backup_created": str(new_backup_path),
            "validation_status": validation_status,
            "validation_message": validation_message,
            "restart_required": True
        }
        
    except tarfile.TarError as e:
        _LOGGER.error(f"Failed to extract backup: {e}")
        return {"status": "error", "message": f"Failed to extract backup: {str(e)}"}
    except Exception as e:
        _LOGGER.error(f"Failed to restore backup: {e}")
        return {"status": "error", "message": f"Failed to restore backup: {str(e)}"}


@router.post("/config/create_backup")
async def create_config_backup():
    """
    Create a configuration backup on disk with version in filename.
    Automatically removes oldest backups if more than 10 exist.
    
    Returns:
        Status response with backup path.
    """
    config_file = _get_app_state().yaml_config_file
    config_dir = Path(config_file).parent
    
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = config_dir / "backups"
        backup_dir.mkdir(exist_ok=True)
        backup_path = backup_dir / f"config_backup_v{__version__}_{timestamp}.tar.gz"
        
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
        
        _LOGGER.info(f"Created config backup: {backup_path}")
        
        # Clean up old backups - keep only 10 most recent
        all_backups = sorted(backup_dir.glob("config_backup_*.tar.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
        if len(all_backups) > 10:
            for old_backup in all_backups[10:]:
                try:
                    old_backup.unlink()
                    _LOGGER.info(f"Removed old backup: {old_backup.name}")
                except Exception as e:
                    _LOGGER.warning(f"Failed to remove old backup {old_backup.name}: {e}")
        
        # Count files
        file_count = 0
        with tarfile.open(backup_path, 'r:gz') as tar:
            file_count = len(tar.getmembers())
        
        return {
            "status": "success",
            "message": f"Backup created with {file_count} files",
            "backup_path": str(backup_path),
            "filename": backup_path.name,
            "version": __version__,
            "file_count": file_count
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
    except Exception:
        raise HTTPException(status_code=403, detail="Invalid backup path")
    
    if not backup_file.exists():
        raise HTTPException(status_code=404, detail="Backup file not found")
    
    _LOGGER.info(f"Downloading backup: {backup_file.name}")
    
    return StreamingResponse(
        open(backup_file, 'rb'),
        media_type="application/gzip",
        headers={"Content-Disposition": f"attachment; filename={backup_file.name}"}
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
        
        return {
            "status": "success",
            "message": f"Backup {backup_file.name} deleted successfully"
        }
    except Exception as e:
        _LOGGER.error(f"Failed to delete backup: {e}")
        return {"status": "error", "message": f"Failed to delete backup: {str(e)}"}
