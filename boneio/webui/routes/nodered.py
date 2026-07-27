"""Node-RED management routes for BoneIO Web UI."""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
import os
import re
import shutil
import subprocess
import tarfile
import time
from datetime import datetime
from pathlib import Path
from typing import TypedDict

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

_LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/nodered", tags=["nodered"])

NODERED_DIR = os.environ.get("NODERED_DIR", os.path.expanduser("~/docker/nodered"))
COMPOSE_FILE_PATH = os.path.join(NODERED_DIR, "docker-compose.yaml")
DATA_DIR = os.path.join(NODERED_DIR, "node-red", "data")
BACKUP_DIR = os.path.join(NODERED_DIR, "backups")

MAX_BACKUPS = 3

# Cache Docker Hub releases
_DOCKER_HUB_CACHE: dict[str, float | list[dict[str, str]] | None] = {
    "data": None,
    "fetched_at": 0.0,
}
_DOCKER_HUB_TTL = 900.0  # 15 minutes

# Progress tracking for updates
class UpdateProgress(TypedDict):
    status: str
    progress: int
    step: str
    log: list[str]
    error: str | None

_update_status: UpdateProgress = {
    "status": "idle",
    "progress": 0,
    "step": "",
    "log": [],
    "error": None,
}


def _reset_update_status() -> None:
    """Reset update status to idle state."""
    global _update_status
    _update_status = {
        "status": "idle",
        "progress": 0,
        "step": "",
        "log": [],
        "error": None,
    }


def _update_progress(progress: int, step: str, log_msg: str | None = None) -> None:
    """Update progress status."""
    global _update_status
    _update_status["progress"] = progress
    _update_status["step"] = step
    if log_msg:
        _update_status["log"].append(log_msg)
        _LOGGER.info("Node-RED Update: %s", log_msg)


class NodeRedStatusResponse(BaseModel):
    """Status details for Node-RED container."""
    running: bool
    version: str
    data_dir_exists: bool
    compose_exists: bool


class BackupInfo(BaseModel):
    """Metadata about a single backup."""
    path: str
    filename: str
    timestamp: str
    size: int
    version: str
    sha256: str | None = None


class BackupListResponse(BaseModel):
    """List of all available backups."""
    backups: list[BackupInfo]


class UpdateCheckResponse(BaseModel):
    """Results of checking for Node-RED updates."""
    current_version: str
    latest_version: str
    update_available: bool


def _get_current_image_version() -> str:
    """
    Get current Node-RED version from docker-compose.yaml.
    
    Returns:
        String containing version tag (e.g., '4.1.2-22-minimal').
    """
    if not os.path.exists(COMPOSE_FILE_PATH):
        return "unknown"
    try:
        with open(COMPOSE_FILE_PATH, encoding="utf-8") as f:
            content = f.read()
        # Find image: nodered/node-red:TAG
        match = re.search(r"image:\s*nodered/node-red:([^\s]+)", content)
        if match:
            return match.group(1)
    except Exception as e:
        _LOGGER.error("Failed to parse docker-compose.yaml: %s", e)
    return "unknown"


# Cache for container running status (subprocess is expensive)
_STATUS_CACHE: dict[str, float | bool] = {
    "running": False,
    "checked_at": 0.0,
}
_STATUS_CACHE_TTL = 30.0  # 30 seconds


def _check_container_running(force: bool = False) -> bool:
    """
    Check if the Node-RED container is currently running.
    
    Uses a 30-second cache to avoid expensive subprocess calls on every request.
    
    Args:
        force: If True, bypass cache and check live status.
    
    Returns:
        True if running, False otherwise.
    """
    now = time.monotonic()
    checked_at = _STATUS_CACHE["checked_at"]
    
    if not force and isinstance(checked_at, float) and (now - checked_at) < _STATUS_CACHE_TTL:
        assert isinstance(_STATUS_CACHE["running"], bool)
        return _STATUS_CACHE["running"]
    
    running = False
    try:
        result = subprocess.run(
            ["docker", "compose", "ps", "--format", "json", "node-red"],
            cwd=NODERED_DIR,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            # Docker Compose outputs JSON format
            try:
                container_info = json.loads(result.stdout)
                if isinstance(container_info, list):
                    container_info = container_info[0] if container_info else {}
                state = container_info.get("State", "unknown")
                running = state == "running"
            except json.JSONDecodeError:
                # Fallback for plain text
                running = "running" in result.stdout.lower() or "Up" in result.stdout
    except Exception as e:
        _LOGGER.error("Failed to check Node-RED container status: %s", e)
    
    _STATUS_CACHE["running"] = running
    _STATUS_CACHE["checked_at"] = now
    return running


class NodeRedAvailableResponse(BaseModel):
    """Fast availability check response — no subprocess calls."""
    available: bool
    version: str


@router.get("/available", response_model=NodeRedAvailableResponse)
async def get_nodered_available() -> NodeRedAvailableResponse:
    """
    Fast availability check.
    
    Only checks if docker-compose.yaml exists and reads the version tag.
    No subprocess calls — instant response for menu visibility checks.
    """
    compose_exists = os.path.exists(COMPOSE_FILE_PATH)
    version = _get_current_image_version() if compose_exists else "unknown"
    return NodeRedAvailableResponse(available=compose_exists, version=version)


@router.get("/status", response_model=NodeRedStatusResponse)
async def get_nodered_status() -> NodeRedStatusResponse:
    """Get overall Node-RED status (uses cached container check)."""
    return NodeRedStatusResponse(
        running=_check_container_running(),
        version=_get_current_image_version(),
        data_dir_exists=os.path.exists(DATA_DIR),
        compose_exists=os.path.exists(COMPOSE_FILE_PATH),
    )


@router.get("/backup/list", response_model=BackupListResponse)
async def list_backups() -> BackupListResponse:
    """List available backups from disk."""
    if not os.path.exists(BACKUP_DIR):
        return BackupListResponse(backups=[])

    backups: list[BackupInfo] = []
    backup_path_obj = Path(BACKUP_DIR)
    
    for backup_file in sorted(backup_path_obj.glob("nodered_backup_*.tar.gz"), reverse=True):
        try:
            filename = backup_file.name
            # Parse timestamp and version from filename if possible
            # e.g., nodered_backup_v4.1.2-22-minimal_20260722_073000.tar.gz
            version = "unknown"
            timestamp = "unknown"
            
            # Use non-greedy match for version, then explicit date_time pattern
            match = re.match(r"nodered_backup_v(.+?)_(\d{8}_\d{6})\.tar\.gz", filename)
            if match:
                version = match.group(1)
                timestamp_str = match.group(2)
                # timestamp_str is always "YYYYMMDD_HHMMSS" (15 chars)
                date_part = timestamp_str[:8]
                time_part = timestamp_str[9:]
                timestamp = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]} {time_part[:2]}:{time_part[2:4]}:{time_part[4:6]}"
            else:
                timestamp = timestamp_str

            sha256 = _read_sha256_sidecar(backup_file)

            backups.append(
                BackupInfo(
                    path=str(backup_file),
                    filename=filename,
                    timestamp=timestamp,
                    size=backup_file.stat().st_size,
                    version=version,
                    sha256=sha256,
                )
            )
        except Exception as e:
            _LOGGER.warning("Error processing Node-RED backup %s: %s", backup_file, e)
            continue

    return BackupListResponse(backups=backups)


def _compute_file_sha256(file_path: str | Path) -> str:
    """
    Compute SHA256 hash of a file.

    Args:
        file_path: Path to the file.

    Returns:
        Hex-encoded SHA256 hash string.
    """
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _write_sha256_sidecar(archive_path: Path) -> str:
    """
    Compute SHA256 of an archive and write a .sha256 sidecar file.

    The sidecar uses the standard format: ``<hash>  <filename>``
    compatible with ``sha256sum -c``.

    Args:
        archive_path: Path to the tar.gz archive.

    Returns:
        The computed SHA256 hex string.
    """
    file_hash = _compute_file_sha256(archive_path)
    sidecar_path = archive_path.with_suffix(archive_path.suffix + ".sha256")
    sidecar_path.write_text(f"{file_hash}  {archive_path.name}\n", encoding="utf-8")
    _LOGGER.info("Wrote SHA256 sidecar: %s", sidecar_path.name)
    return file_hash


def _read_sha256_sidecar(archive_path: Path) -> str | None:
    """
    Read SHA256 hash from a sidecar file if it exists.

    Args:
        archive_path: Path to the tar.gz archive.

    Returns:
        The SHA256 hex string, or None if the sidecar doesn't exist.
    """
    sidecar_path = archive_path.with_suffix(archive_path.suffix + ".sha256")
    if not sidecar_path.exists():
        return None
    try:
        content = sidecar_path.read_text(encoding="utf-8").strip()
        # Format: "<hash>  <filename>" or just "<hash>"
        return content.split()[0] if content else None
    except Exception as e:
        _LOGGER.warning("Failed to read SHA256 sidecar %s: %s", sidecar_path, e)
        return None


@router.post("/backup/create")
async def create_backup() -> dict[str, str | int]:
    """Create a new backup of Node-RED data directory with SHA256 checksum."""
    if not os.path.exists(DATA_DIR):
        raise HTTPException(status_code=400, detail="Node-RED data directory does not exist")

    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        
        # Enforce max backup limit (remove oldest including sidecar)
        backup_path_obj = Path(BACKUP_DIR)
        existing_backups = sorted(backup_path_obj.glob("nodered_backup_*.tar.gz"), reverse=True)
        if len(existing_backups) >= MAX_BACKUPS:
            to_remove = existing_backups[MAX_BACKUPS - 1:]
            for old_backup in to_remove:
                try:
                    old_backup.unlink()
                    # Also remove sidecar
                    sidecar = old_backup.with_suffix(old_backup.suffix + ".sha256")
                    if sidecar.exists():
                        sidecar.unlink()
                    _LOGGER.info("Removed old Node-RED backup: %s", old_backup.name)
                except Exception as e:
                    _LOGGER.warning("Failed to remove old backup %s: %s", old_backup, e)

        version = _get_current_image_version()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"nodered_backup_v{version}_{timestamp}.tar.gz"
        backup_file_path = Path(BACKUP_DIR) / backup_filename

        with tarfile.open(str(backup_file_path), mode="w:gz") as tar:
            data_path_obj = Path(DATA_DIR)
            for file_path in data_path_obj.rglob("*"):
                # Exclude node_modules directory
                if "node_modules" in file_path.parts:
                    continue
                if file_path.is_file():
                    arcname = file_path.relative_to(data_path_obj)
                    tar.add(str(file_path), arcname=str(arcname))

            # Add metadata file inside the same archive
            meta = {
                "version": version,
                "created_at": datetime.now().isoformat(),
            }
            meta_bytes = json.dumps(meta, indent=2).encode("utf-8")
            tarinfo = tarfile.TarInfo(name="_nodered_backup_meta.json")
            tarinfo.size = len(meta_bytes)
            tarinfo.mtime = int(datetime.now().timestamp())
            tar.addfile(tarinfo, io.BytesIO(meta_bytes))

        # Compute and write SHA256 sidecar
        file_hash = _write_sha256_sidecar(backup_file_path)

        _LOGGER.info("Created Node-RED backup: %s (sha256: %s)", backup_filename, file_hash)
        return {
            "status": "success",
            "message": "Backup created successfully",
            "filename": backup_filename,
            "sha256": file_hash,
        }
    except Exception as e:
        _LOGGER.error("Failed to create Node-RED backup: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to create backup: {e}") from e




@router.post("/backup/restore")
async def restore_backup(backup_path: str) -> dict[str, str]:
    """Restore a backup of Node-RED data directory."""
    backup_file = Path(backup_path)
    backup_dir_obj = Path(BACKUP_DIR)
    
    try:
        backup_file = backup_file.resolve()
        backup_dir_obj = backup_dir_obj.resolve()
        if not str(backup_file).startswith(str(backup_dir_obj)):
            raise HTTPException(status_code=400, detail="Invalid backup path")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid backup path") from None

    if not backup_file.exists():
        raise HTTPException(status_code=404, detail="Backup file not found")

    try:
        import asyncio

        loop = asyncio.get_event_loop()

        def _docker_compose_cmd(cmd: list[str], timeout: int = 30) -> None:
            """Run a docker compose command synchronously (meant for executor)."""
            result = subprocess.run(
                cmd,
                cwd=NODERED_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
            )
            if result.returncode != 0:
                stderr_text = result.stderr.decode(errors="replace").strip()
                _LOGGER.error(
                    "docker compose command failed (rc=%d): %s\nstderr: %s",
                    result.returncode, " ".join(cmd), stderr_text,
                )
                raise RuntimeError(f"docker compose failed: {stderr_text or 'unknown error'}")

        def _do_restore() -> None:
            """Perform the blocking restore steps in a thread."""
            # Step 1: Stop Node-RED container
            _LOGGER.info("Stopping Node-RED for restore...")
            _docker_compose_cmd(["docker", "compose", "stop", "node-red"])

            # Step 2: Clear current files in data directory except node_modules
            _LOGGER.info("Cleaning up current Node-RED files...")
            if os.path.exists(DATA_DIR):
                for item in os.listdir(DATA_DIR):
                    if item == "node_modules":
                        continue
                    item_path = os.path.join(DATA_DIR, item)
                    if os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                    else:
                        os.remove(item_path)
            else:
                os.makedirs(DATA_DIR, exist_ok=True)

            # Step 3: Extract backup with safe filter
            _LOGGER.info("Extracting backup files from %s ...", backup_file.name)
            with tarfile.open(backup_file, mode="r:gz") as tar:
                # Filter out metadata and unsafe members
                safe_members = [
                    m for m in tar.getmembers()
                    if m.name != "_nodered_backup_meta.json"
                    and ".." not in m.name
                    and not m.name.startswith("/")
                ]
                tar.extractall(path=DATA_DIR, members=safe_members, filter="data")

            # Step 4: Start Node-RED container
            _LOGGER.info("Starting Node-RED container back up...")
            _docker_compose_cmd(["docker", "compose", "start", "node-red"])

            _LOGGER.info("Node-RED restore complete.")

        await loop.run_in_executor(None, _do_restore)

        return {"status": "success", "message": "Backup restored successfully"}
    except Exception as e:
        _LOGGER.error("Failed to restore Node-RED backup: %s", e, exc_info=True)
        # Try to restart container just in case it got stuck stopped
        try:
            subprocess.run(["docker", "compose", "start", "node-red"], cwd=NODERED_DIR, timeout=10, check=False)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Failed to restore: {e}") from e


@router.get("/backup/download")
async def download_backup(backup_path: str) -> StreamingResponse:
    """Download a backup file with SHA256 header."""
    backup_file = Path(backup_path)
    backup_dir_obj = Path(BACKUP_DIR)
    
    try:
        backup_file = backup_file.resolve()
        backup_dir_obj = backup_dir_obj.resolve()
        if not str(backup_file).startswith(str(backup_dir_obj)):
            raise HTTPException(status_code=400, detail="Invalid backup path")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid backup path") from None

    if not backup_file.exists():
        raise HTTPException(status_code=404, detail="Backup file not found")

    sha256 = _read_sha256_sidecar(backup_file)

    def iterfile():
        with open(backup_file, mode="rb") as f:
            yield from f

    headers: dict[str, str] = {
        "Content-Disposition": f"attachment; filename={backup_file.name}",
    }
    if sha256:
        headers["X-SHA256"] = sha256
        # Expose custom header to browser JS
        headers["Access-Control-Expose-Headers"] = "X-SHA256"

    return StreamingResponse(
        iterfile(),
        media_type="application/gzip",
        headers=headers,
    )


@router.delete("/backup/delete")
async def delete_backup(backup_path: str) -> dict[str, str]:
    """Delete a backup file and its SHA256 sidecar."""
    backup_file = Path(backup_path)
    backup_dir_obj = Path(BACKUP_DIR)
    
    try:
        backup_file = backup_file.resolve()
        backup_dir_obj = backup_dir_obj.resolve()
        if not str(backup_file).startswith(str(backup_dir_obj)):
            raise HTTPException(status_code=400, detail="Invalid backup path")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid backup path") from None

    if not backup_file.exists():
        raise HTTPException(status_code=404, detail="Backup file not found")

    try:
        backup_file.unlink()
        # Also remove sidecar
        sidecar = backup_file.with_suffix(backup_file.suffix + ".sha256")
        if sidecar.exists():
            sidecar.unlink()
        _LOGGER.info("Deleted Node-RED backup: %s", backup_file.name)
        return {"status": "success", "message": "Backup deleted successfully"}
    except Exception as e:
        _LOGGER.error("Failed to delete Node-RED backup: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to delete backup: {e}") from e


@router.post("/backup/upload_restore")
async def upload_restore(
    file: UploadFile = File(...),
    sha256: str = Form(""),
) -> dict[str, str]:
    """
    Restore Node-RED from an uploaded backup archive.

    Accepts a tar.gz upload with optional SHA256 verification.
    Creates a safety backup of the current state before restoring.

    Args:
        file: The tar.gz backup archive to restore from.
        sha256: Optional SHA256 hex digest to verify the upload integrity.

    Returns:
        Status dict with result message.
    """
    if not file.filename or not file.filename.endswith((".tar.gz", ".tgz")):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Please upload a .tar.gz or .tgz file.",
        )

    contents = await file.read()

    # SHA256 verification (if provided)
    if sha256:
        computed = hashlib.sha256(contents).hexdigest()
        if computed.lower() != sha256.lower().strip():
            raise HTTPException(
                status_code=400,
                detail=f"SHA256 mismatch. Expected: {sha256.lower().strip()}, Got: {computed}",
            )
        _LOGGER.info("SHA256 verification passed for uploaded backup")

    # Validate the archive
    try:
        buffer = io.BytesIO(contents)
        with tarfile.open(fileobj=buffer, mode="r:gz") as tar:
            members = tar.getmembers()
            for member in members:
                if ".." in member.name or member.name.startswith("/"):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Unsafe path in archive: {member.name}",
                    )
    except tarfile.TarError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid tar.gz archive: {e}",
        ) from e

    loop = asyncio.get_event_loop()

    def _docker_compose_cmd(cmd: list[str], timeout: int = 30) -> None:
        """Run a docker compose command synchronously."""
        result = subprocess.run(
            cmd,
            cwd=NODERED_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        if result.returncode != 0:
            stderr_text = result.stderr.decode(errors="replace").strip()
            _LOGGER.error(
                "docker compose command failed (rc=%d): %s\nstderr: %s",
                result.returncode, " ".join(cmd), stderr_text,
            )
            raise RuntimeError(f"docker compose failed: {stderr_text or 'unknown error'}")

    def _do_upload_restore() -> None:
        """Perform the blocking restore steps from uploaded file."""
        # Step 1: Create safety backup of current state
        if os.path.exists(DATA_DIR):
            _LOGGER.info("Creating safety backup before upload restore...")
            os.makedirs(BACKUP_DIR, exist_ok=True)
            version = _get_current_image_version()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safety_filename = f"nodered_backup_v{version}_{timestamp}.tar.gz"
            safety_path = Path(BACKUP_DIR) / safety_filename

            with tarfile.open(str(safety_path), mode="w:gz") as tar:
                data_path_obj = Path(DATA_DIR)
                for file_path in data_path_obj.rglob("*"):
                    if "node_modules" in file_path.parts:
                        continue
                    if file_path.is_file():
                        arcname = file_path.relative_to(data_path_obj)
                        tar.add(str(file_path), arcname=str(arcname))

                meta = {
                    "version": version,
                    "created_at": datetime.now().isoformat(),
                }
                meta_bytes = json.dumps(meta, indent=2).encode("utf-8")
                tarinfo = tarfile.TarInfo(name="_nodered_backup_meta.json")
                tarinfo.size = len(meta_bytes)
                tarinfo.mtime = int(datetime.now().timestamp())
                tar.addfile(tarinfo, io.BytesIO(meta_bytes))

            _write_sha256_sidecar(safety_path)
            _LOGGER.info("Safety backup created: %s", safety_filename)

        # Step 2: Stop Node-RED container
        _LOGGER.info("Stopping Node-RED for upload restore...")
        _docker_compose_cmd(["docker", "compose", "stop", "node-red"])

        # Step 3: Clear current files (keep node_modules)
        _LOGGER.info("Cleaning up current Node-RED files...")
        if os.path.exists(DATA_DIR):
            for item in os.listdir(DATA_DIR):
                if item == "node_modules":
                    continue
                item_path = os.path.join(DATA_DIR, item)
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                else:
                    os.remove(item_path)
        else:
            os.makedirs(DATA_DIR, exist_ok=True)

        # Step 4: Extract uploaded backup
        _LOGGER.info("Extracting uploaded backup...")
        upload_buffer = io.BytesIO(contents)
        with tarfile.open(fileobj=upload_buffer, mode="r:gz") as tar:
            safe_members = [
                m for m in tar.getmembers()
                if m.name != "_nodered_backup_meta.json"
                and ".." not in m.name
                and not m.name.startswith("/")
            ]
            tar.extractall(path=DATA_DIR, members=safe_members, filter="data")

        # Step 5: Start Node-RED container
        _LOGGER.info("Starting Node-RED container back up...")
        _docker_compose_cmd(["docker", "compose", "start", "node-red"])

        _LOGGER.info("Node-RED upload restore complete.")

    try:
        await loop.run_in_executor(None, _do_upload_restore)
        return {"status": "success", "message": "Backup restored successfully from uploaded file"}
    except Exception as e:
        _LOGGER.error("Failed to restore Node-RED from upload: %s", e, exc_info=True)
        # Try to restart container
        try:
            subprocess.run(
                ["docker", "compose", "start", "node-red"],
                cwd=NODERED_DIR, timeout=10, check=False,
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Failed to restore: {e}") from e


def _fetch_docker_hub_tags() -> list[dict[str, str]]:
    """
    Fetch image tags for nodered/node-red from Docker Hub API.
    
    Returns:
        List of dicts representing tags.
    """
    cached = _DOCKER_HUB_CACHE["data"]
    fetched_at = _DOCKER_HUB_CACHE["fetched_at"]
    
    if cached is not None and isinstance(fetched_at, float) and (time.monotonic() - fetched_at) < _DOCKER_HUB_TTL:
        assert isinstance(cached, list)
        return cached

    try:
        import requests
        # We need tags from nodered/node-red
        url = "https://hub.docker.com/v2/repositories/nodered/node-red/tags/?page_size=100&ordering=last_updated"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            results = data.get("results", [])
            tags = [{"name": t["name"]} for t in results]
            
            _DOCKER_HUB_CACHE["data"] = tags
            _DOCKER_HUB_CACHE["fetched_at"] = time.monotonic()
            return tags
    except Exception as e:
        _LOGGER.error("Failed to fetch tags from Docker Hub: %s", e)
        
    # Return previous cached if request fails, or empty list
    if _DOCKER_HUB_CACHE["data"] is not None:
        assert isinstance(_DOCKER_HUB_CACHE["data"], list)
        return _DOCKER_HUB_CACHE["data"]
    return []


@router.get("/update/check", response_model=UpdateCheckResponse)
async def check_update() -> UpdateCheckResponse:
    """Check if Node-RED update is available."""
    current_version = _get_current_image_version()
    if current_version == "unknown":
        return UpdateCheckResponse(
            current_version="unknown",
            latest_version="unknown",
            update_available=False,
        )

    # Determine if we are using minimal or standard variant
    is_minimal = "-minimal" in current_version
    
    # Strip suffix to get version part (e.g. 4.1.2-22-minimal -> 4.1.2)
    # The tag pattern on docker hub is often like 4.0.2-20-minimal or 4.0.2
    
    tags = _fetch_docker_hub_tags()
    if not tags:
        return UpdateCheckResponse(
            current_version=current_version,
            latest_version=current_version,
            update_available=False,
        )

    latest_version = current_version
    
    try:
        from packaging import version
    except ImportError:
        # Fallback simple string match
        _LOGGER.warning("packaging module not installed, fallback to string matching")
        # Find latest tag matching variant
        for t in tags:
            tag_name = t["name"]
            if is_minimal and not tag_name.endswith("-minimal"):
                continue
            if not is_minimal and "-minimal" in tag_name:
                continue
            # Docker Hub tag format: major.minor.patch[-build]
            if re.match(r"^\d+\.\d+\.\d+", tag_name):
                latest_version = tag_name
                break
                
        return UpdateCheckResponse(
            current_version=current_version,
            latest_version=latest_version,
            update_available=(latest_version != current_version),
        )

    # Find the highest version with packaging
    current_clean = current_version.replace("-minimal", "")
    current_parsed = version.parse(current_clean)
    
    best_tag = current_version
    best_parsed = current_parsed
    
    for t in tags:
        tag_name = t["name"]
        if is_minimal and not tag_name.endswith("-minimal"):
            continue
        if not is_minimal and "-minimal" in tag_name:
            continue
        
        clean_tag = tag_name.replace("-minimal", "")
        if not re.match(r"^\d+\.\d+\.\d+", clean_tag):
            continue
            
        try:
            parsed = version.parse(clean_tag)
            if parsed > best_parsed:
                best_parsed = parsed
                best_tag = tag_name
        except Exception:
            continue

    return UpdateCheckResponse(
        current_version=current_version,
        latest_version=best_tag,
        update_available=(best_tag != current_version),
    )


@router.get("/update/status")
async def get_update_status() -> UpdateProgress:
    """Get Node-RED update status."""
    return _update_status


@router.post("/update/perform")
async def perform_update(background_tasks: BackgroundTasks, target_version: str | None = None) -> dict[str, str]:
    """Perform Node-RED update in background."""
    global _update_status
    
    if _update_status["status"] == "running":
        return {"status": "error", "message": "Update already in progress"}

    if not os.path.exists(COMPOSE_FILE_PATH):
        raise HTTPException(status_code=400, detail="docker-compose.yaml not found")

    _reset_update_status()
    _update_status["status"] = "running"

    async def run_update_task():
        try:
            # 1. Check for update to find target version if not provided
            nonlocal target_version
            if not target_version:
                _update_progress(10, "Checking available updates...", "Checking Docker Hub for latest tags")
                res = await check_update()
                if not res.update_available:
                    _update_status["status"] = "success"
                    _update_progress(100, "Already up to date", f"Current version {res.current_version} is latest.")
                    return
                target_version = res.latest_version

            # 2. Automatic Backup
            _update_progress(20, "Creating automatic backup before update...", "Backing up flows")
            try:
                await create_backup()
                _update_status["log"].append("Automatic backup created successfully.")
            except Exception as e:
                # We can proceed even if backup fails, but warn the log
                _update_status["log"].append(f"Warning: Automatic backup failed: {e}. Proceeding with update.")

            # 3. Modify docker-compose.yaml image tag
            _update_progress(40, f"Updating docker-compose.yaml to version {target_version}...", f"Setting tag to {target_version}")
            
            with open(COMPOSE_FILE_PATH, encoding="utf-8") as f:
                content = f.read()
                
            new_content = re.sub(
                r"image:\s*nodered/node-red:[^\s]+",
                f"image: nodered/node-red:{target_version}",
                content
            )
            
            with open(COMPOSE_FILE_PATH, "w", encoding="utf-8") as f:
                f.write(new_content)

            # 4. Pull new image
            _update_progress(60, "Pulling new Node-RED Docker image...", "docker compose pull")
            pull_process = await asyncio.create_subprocess_exec(
                "docker", "compose", "pull", "node-red",
                cwd=NODERED_DIR,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await pull_process.communicate()
            if pull_process.returncode != 0:
                raise Exception(f"docker compose pull failed: {stderr.decode().strip()}")

            # 5. Restart Node-RED container
            _update_progress(80, "Restarting Node-RED container...", "docker compose up -d")
            up_process = await asyncio.create_subprocess_exec(
                "docker", "compose", "up", "-d", "node-red",
                cwd=NODERED_DIR,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await up_process.communicate()
            if up_process.returncode != 0:
                raise Exception(f"docker compose up failed: {stderr.decode().strip()}")

            # 6. Verify and complete
            _update_status["status"] = "success"
            _update_progress(100, "Update complete!", f"Node-RED updated successfully to {target_version}.")
            
        except Exception as e:
            _LOGGER.error("Node-RED update error: %s", e)
            _update_status["status"] = "error"
            _update_status["error"] = str(e)
            _update_status["log"].append(f"Error: {e}")

    background_tasks.add_task(run_update_task)
    return {"status": "started", "message": "Update process started"}
