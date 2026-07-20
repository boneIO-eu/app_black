"""File browsing and raw editor routes for BoneIO Web UI."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import Body, HTTPException

from boneio.webui.routes.config_core import _get_app_state, router

_LOGGER = logging.getLogger(__name__)


@router.get("/files")
async def list_files(path: str | None = None):
    """List files in the config directory."""
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
    """Get content of a file."""
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
    """Update content of a file."""
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
