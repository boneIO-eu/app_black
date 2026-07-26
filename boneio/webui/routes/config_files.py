"""File browsing and raw editor routes for BoneIO Web UI."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import Body, HTTPException

from boneio.webui.routes.config_core import _get_app_state, router

_LOGGER = logging.getLogger(__name__)

# Files that must never be exposed via the editor
_PROTECTED_FILENAMES = frozenset({
    "secrets.yaml",
    "jwt_secret",
    ".env",
})


def _resolve_safe_path(config_dir: Path, file_path: str) -> Path:
    """Resolve a user-supplied path and ensure it stays within config_dir.

    Prevents path traversal attacks (e.g. ``../../etc/passwd``).

    Args:
        config_dir: Root configuration directory.
        file_path: Relative path supplied by the client.

    Returns:
        Resolved absolute path guaranteed to be inside config_dir.

    Raises:
        HTTPException: If the path escapes config_dir or targets a protected file.
    """
    resolved_dir = config_dir.resolve()
    resolved_path = (config_dir / file_path).resolve()

    if not resolved_path.is_relative_to(resolved_dir):
        _LOGGER.warning(
            "Path traversal attempt blocked: %s (resolved to %s)",
            file_path,
            resolved_path,
        )
        raise HTTPException(status_code=403, detail="Access denied")

    if resolved_path.name in _PROTECTED_FILENAMES:
        _LOGGER.warning("Access to protected file blocked: %s", resolved_path.name)
        raise HTTPException(status_code=403, detail="Protected file")

    return resolved_path


@router.get("/files")
async def list_files(path: str | None = None):
    """List files in the config directory."""
    config_dir = Path(_get_app_state().yaml_config_file).parent
    base_dir = _resolve_safe_path(config_dir, path) if path else config_dir.resolve()

    if not base_dir.exists():
        raise HTTPException(status_code=404, detail="Path not found")

    if not base_dir.is_dir():
        raise HTTPException(status_code=400, detail="Path is not a directory")

    resolved_config_dir = config_dir.resolve()

    def scan_directory(directory: Path):
        """Recursively scan directory for yaml/yml files."""
        items = []
        for entry in os.scandir(directory):
            if entry.name == ".git" or entry.name.startswith("venv"):
                continue
            if entry.name in _PROTECTED_FILENAMES:
                continue
            relative_path = os.path.relpath(entry.path, resolved_config_dir)
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
    except HTTPException:
        raise
    except Exception as e:
        _LOGGER.error("Error listing files: %s", e)
        raise HTTPException(status_code=500, detail="Failed to list files") from e


@router.get("/files/{file_path:path}")
async def get_file_content(file_path: str):
    """Get content of a file."""
    config_dir = Path(_get_app_state().yaml_config_file).parent
    full_path = _resolve_safe_path(config_dir, file_path)

    if not full_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    if not full_path.is_file():
        raise HTTPException(status_code=400, detail="Path is not a file")

    if not full_path.name.endswith((".yaml", ".yml", ".json")):
        raise HTTPException(status_code=400, detail="Invalid file type")

    try:
        with open(full_path) as f:
            content = f.read()
        return {"content": content}
    except HTTPException:
        raise
    except Exception as e:
        _LOGGER.error("Error reading file %s: %s", file_path, e)
        raise HTTPException(status_code=500, detail="Failed to read file") from e


@router.put("/files/{file_path:path}")
async def update_file_content(file_path: str, content: dict = Body(...)):
    """Update content of a file."""
    config_dir = Path(_get_app_state().yaml_config_file).parent
    full_path = _resolve_safe_path(config_dir, file_path)

    if not full_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    if not full_path.is_file():
        raise HTTPException(status_code=400, detail="Path is not a file")

    if not full_path.name.endswith((".yaml", ".yml", ".json")):
        raise HTTPException(status_code=400, detail="Invalid file type")

    try:
        with open(full_path, "w") as f:
            f.write(content["content"])
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        _LOGGER.error("Error writing file %s: %s", file_path, e)
        raise HTTPException(status_code=500, detail="Failed to write file") from e
