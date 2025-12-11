"""BoneIO Web UI."""

from __future__ import annotations

import asyncio
from boneio.components.cover.previous import PreviousCover
from boneio.components.cover.time_based import TimeBasedCover
from boneio.components.cover.venetian import VenetianCover
import json
import logging
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Optional

from boneio.models.state import ModbusDeviceState

if TYPE_CHECKING:
    from boneio.webui.web_server import WebServer
from pathlib import Path

from fastapi import (
    BackgroundTasks,
    Body,
    Depends,
    FastAPI,
    File,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from jose import jwt
from jose.exceptions import JWTError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import Receive, Scope, Send
from starlette.websockets import WebSocketState

from boneio.const import COVER, NONE
from boneio.core.config import ConfigHelper
from boneio.core.config.yaml_util import (
    load_config_from_file,
    update_config_section,
)
from boneio.core.events import GracefulExit
from boneio.core.manager import Manager
from boneio.exceptions import ConfigurationException
from boneio.models import (
    CoverState,
    GroupState,
    InputState,
    OutputState,
    SensorState,
)
from boneio.models.actions import CoverAction, CoverPosition, CoverTilt
from boneio.models.events import (
    CoverEvent,
    Event,
    GroupEvent,
    InputEvent,
    ModbusDeviceEvent,
    OutputEvent,
    SensorEvent,
)
from boneio.models.logs import LogEntry, LogsResponse
from boneio.version import __version__

from .websocket_manager import JWT_ALGORITHM, WebSocketManager

_LOGGER = logging.getLogger(__name__)


class BoneIOApp(FastAPI):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._loop = asyncio.get_event_loop()

    async def shutdown_handler(self):
        """Handle application shutdown."""
        _LOGGER.debug("Shutting down All WebSocket connections...")
        if hasattr(self.state, 'websocket_manager'):
            # Close all WebSocket connections immediately
            await self.state.websocket_manager.close_all()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Handle ASGI calls with proper lifespan support."""
        message = None
        if scope["type"] == "lifespan":
            try:
                while True:
                    message = await receive()
                    if message["type"] == "lifespan.startup":
                        try:
                            await send({"type": "lifespan.startup.complete"})
                        except Exception as e:
                            await send(
                                {"type": "lifespan.startup.failed", "message": str(e)}
                            )
                    elif message["type"] == "lifespan.shutdown":
                        try:
                            # First shutdown all WebSocket connections
                            _LOGGER.debug("Starting lifespan shutdown...")
                            await self.shutdown_handler()
                            _LOGGER.debug(
                                "WebSocket connections closed, sending shutdown complete..."
                            )
                            # Only after WebSocket cleanup is done, send shutdown complete
                            await send({"type": "lifespan.shutdown.complete"})
                            _LOGGER.debug("Lifespan shutdown complete sent.")
                        except Exception as e:
                            _LOGGER.error("Error during lifespan shutdown: %s", e)
                            await send(
                                {"type": "lifespan.shutdown.failed", "message": str(e)}
                            )
                        return
            except (asyncio.CancelledError, GracefulExit):
                # Handle graceful exit during lifespan
                _LOGGER.debug("GracefulExit during lifespan, cleaning up...")
                await self.shutdown_handler()
                # await send({"type": "lifespan.shutdown.complete"})
                _LOGGER.debug("Lifespan cleanup complete.")
                return
        try:
            await super().__call__(scope, receive, send)
        except Exception:
            pass


# Create FastAPI application
app = BoneIOApp(
    title="BoneIO API",
    description="BoneIO API for managing inputs, outputs, and sensors",
    version=__version__,
)



# security = HTTPBasic()
JWT_SECRET = os.getenv('JWT_SECRET', secrets.token_hex(32))  # Use environment variable or generate temporary
_auth_config = {}

# Dependency to get manager instance
def get_manager():
    """Get manager instance."""
    return app.state.manager

def get_config_helper():
    """Get config helper instance."""
    return app.state.config_helper


# Add auth required endpoint
@app.get("/api/auth/required")
async def auth_required():
    """Check if authentication is required."""
    try:
        auth_required = bool(
            _auth_config.get("username") and _auth_config.get("password")
        )
        return {"required": auth_required}
    except Exception as e:
        logging.error(f"Error checking auth requirement: {e}")
        # Default to requiring auth if there's an error
        return {"required": True}


# Configure CORS
origins = [
    "http://localhost:5173",  # Default Vite dev server
    "http://localhost:4173",  # Vite preview
    "http://127.0.0.1:5173",
    "http://127.0.0.1:4173",
    "*",  # Allow all origins during development
]


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Skip auth for login endpoint and static files
        if (
            not request.url.path.startswith("/api")
            or request.url.path == "/api/login"
            or request.url.path == "/api/auth/required"
            or request.url.path == "/api/version"
        ):
            return await call_next(request)

        if not _auth_config:
            return await call_next(request)

        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return JSONResponse(
                status_code=401,
                content={"detail": "No authorization header"}
            )

        try:
            # Check if it's a Bearer token
            scheme, token = auth_header.split()
            if scheme.lower() != "bearer":
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid authentication scheme"}
                )

            # Verify the JWT token
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])

            # Check if token has expired
            exp = payload.get("exp")
            if not exp or datetime.fromtimestamp(exp, tz=timezone.utc) < datetime.now(
                timezone.utc
            ):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Token has expired"}
                )

        except JWTError:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid token"}
            )
        except ValueError:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid authorization header format"}
            )

        return await call_next(request)


@app.post("/api/login")
async def login(username: str = Body(...), password: str = Body(...)):
    if not _auth_config:
        token = create_token({"sub": "default"})
        return {"token": token}

    if username == _auth_config.get("username") and password == _auth_config.get(
        "password"
    ):
        token = create_token({"sub": username})
        return {"token": token}
    raise HTTPException(status_code=401, detail="Invalid credentials")


def create_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=7)  # Token expires in 7 days
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return encoded_jwt


def is_running_as_service():
    """Check if running as a systemd service."""
    try:
        with open("/proc/1/comm") as f:
            return "systemd" in f.read()
    except Exception:
        return False


def _clean_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def _decode_ascii_list(ascii_list: list) -> str:
    """Decode a list of ASCII codes into a string and clean ANSI codes."""
    try:
        # Convert ASCII codes to string
        text = ''.join(chr(code) for code in ascii_list)
        # Remove ANSI escape sequences
        return _clean_ansi(text)
    except Exception as e:
        _LOGGER.error(f"Error decoding ASCII list: {e}")
        return str(ascii_list)

def _parse_systemd_log_entry(entry: dict) -> dict:
    """Parse a systemd journal log entry."""
    # Handle MESSAGE field if it's a list of ASCII codes
    if isinstance(entry.get('MESSAGE'), list):
        try:
            # First try to decode the outer message
            decoded_msg = _decode_ascii_list(entry['MESSAGE'])
            
            # Check if the decoded message is a JSON string
            try:
                json_msg = json.loads(decoded_msg)
                # If it has a nested MESSAGE field that's also ASCII codes
                if isinstance(json_msg.get('MESSAGE'), list):
                    json_msg['MESSAGE'] = _decode_ascii_list(json_msg['MESSAGE'])
                entry['MESSAGE'] = json_msg.get('MESSAGE', decoded_msg)
            except json.JSONDecodeError:
                # Not a JSON string, use the decoded message as is
                entry['MESSAGE'] = decoded_msg
            except Exception as e:
                _LOGGER.debug(f"Error parsing nested message: {e}")
                entry['MESSAGE'] = decoded_msg
                
        except Exception as e:
            _LOGGER.error(f"Error parsing message: {e}")
            entry['MESSAGE'] = "Can't decode message"
    
    # Convert timestamps if present
    for ts_field in ('__REALTIME_TIMESTAMP', '__MONOTONIC_TIMESTAMP'):
        if ts_field in entry:
            try:
                entry[ts_field] = int(entry[ts_field])
            except (TypeError, ValueError):
                pass
    
    return entry


def strip_ansi_codes(text: str) -> str:
    """Remove ANSI color codes from text."""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

async def get_systemd_logs(since: str = "-15m") -> list[LogEntry]:
    """Get logs from journalctl."""
    cmd = [
        "journalctl",
        "-u", "boneio",
        "--no-pager",
        "--no-hostname",
        "--output=json",
        "--output-fields=MESSAGE,__REALTIME_TIMESTAMP,PRIORITY",
        "--no-tail",
        "--since", since
    ]
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    stdout, stderr = await process.communicate()
    if stderr:
        _LOGGER.error(f"Error getting systemd logs: {stderr.decode()}")
    if not stdout.strip():
        # _LOGGER.warning("No logs found")
        return []
    raw_log = json.loads(b'[' + stdout.replace(b'\n', b',')[:-1] + b']')

    log_entries = []
    for log in raw_log:
        if isinstance(log.get('MESSAGE'), list):
            # Handle ASCII-encoded messages
            try:
                message_bytes = bytes(log['MESSAGE'])
                message = message_bytes.decode('utf-8', errors='ignore')
                message = strip_ansi_codes(message)
            except Exception as e:
                message = f"Error decoding message: {e}"
        else:
            message = log.get('MESSAGE', '')
        log_entries.append(
            LogEntry(
                timestamp=log.get("__REALTIME_TIMESTAMP", ""),
                message=message,
                level=log.get("PRIORITY", ""),
            )
        )

    return log_entries


def get_standalone_logs(since: str, limit: int) -> list[LogEntry]:
    """Get logs from log file when running standalone."""
    # log_file = Path(app.state.yaml_config_file).parent / "boneio.log"
    log_file = Path("/tmp/boneio.log")
    if not log_file.exists():
        return []

    # Parse since parameter
    if since:
        if since[-1] in ["h", "d"]:
            amount = int(since[:-1])
            unit = since[-1]
            delta = timedelta(hours=amount) if unit == "h" else timedelta(days=amount)
            since_time = datetime.now() - delta
        else:
            try:
                since_time = datetime.fromisoformat(since)
            except ValueError:
                since_time = None
    else:
        since_time = None

    log_entries = []
    try:
        with open(log_file) as f:
            # Read from the end of file
            lines = f.readlines()[-limit:]
            for line in lines:
                try:
                    # Assuming log format: "2023-12-27 15:13:44 INFO Message"
                    parts = line.split(" ", 3)
                    if len(parts) >= 4:
                        timestamp_str = f"{parts[0]} {parts[1]}"
                        level = parts[2]
                        message = parts[3].strip()

                        # Convert level to priority
                        level_map = {
                            "DEBUG": "7",
                            "INFO": "6",
                            "WARNING": "4",
                            "ERROR": "3",
                            "CRITICAL": "2",
                        }

                        # Check if log is after since_time
                        if since_time:
                            try:
                                log_time = datetime.strptime(
                                    timestamp_str, "%Y-%m-%d %H:%M:%S"
                                )
                                if log_time < since_time:
                                    continue
                            except ValueError:
                                continue

                        log_entries.append(
                            LogEntry(
                                timestamp=timestamp_str,
                                message=message,
                                level=level_map.get(level.upper(), "6"),
                            )
                        )
                except (IndexError, ValueError):
                    continue
    except Exception as e:
        _LOGGER.warning(f"Error reading log file: {e}")
        return []

    return log_entries


@app.get("/api/logs")
async def get_logs(since: str = "", limit: int = 100) -> LogsResponse:
    """Get logs from either systemd journal or standalone log file."""
    try:
        # Try systemd logs first if running as service
        if is_running_as_service():
            # _LOGGER.debug("Fetching from systemd journal...")
            log_entries = await get_systemd_logs(since)
            if log_entries:
                return LogsResponse(logs=log_entries)

        # Fall back to standalone logs
        # _LOGGER.debug("Fetching from standalone log file...")
        log_entries = get_standalone_logs(since, limit)
        if log_entries:
            return LogsResponse(logs=log_entries)

        # If no logs found, return a message
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


@app.post("/api/outputs/{output_id}/toggle")
async def toggle_output(output_id: str, manager: Manager = Depends(get_manager)):
    """Toggle output state."""
    if output_id not in manager.outputs.get_all_outputs():
        raise HTTPException(status_code=404, detail="Output not found")
    status = await manager.outputs.toggle_output(output_id=output_id)
    if status:
        return {"status": status}
    else:
        return {"status": "error"}


@app.post("/api/outputs/{output_id}/turn_on")
async def turn_on_output(output_id: str, manager: Manager = Depends(get_manager)):
    """Turn on output."""
    output = manager.outputs.get_output(output_id)
    if not output:
        raise HTTPException(status_code=404, detail="Output not found")
    await output.async_turn_on()
    return {"status": "ok"}


@app.post("/api/outputs/{output_id}/turn_off")
async def turn_off_output(output_id: str, manager: Manager = Depends(get_manager)):
    """Turn off output."""
    output = manager.outputs.get_output(output_id)
    if not output:
        raise HTTPException(status_code=404, detail="Output not found")
    await output.async_turn_off()
    return {"status": "ok"}


@app.post("/api/groups/{group_id}/toggle")
async def toggle_group(group_id: str, manager: Manager = Depends(get_manager)):
    """Toggle output group state.
    
    Args:
        group_id: ID of the output group to toggle
        manager: Manager instance
        
    Returns:
        Status response with 'ok' or error
    """
    group = manager.outputs.get_output_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Output group not found")
    
    await group.async_toggle()
    return {"status": "ok"}


@app.post("/api/covers/{cover_id}/action")
async def cover_action(cover_id: str, action_data: CoverAction, manager: Manager = Depends(get_manager)):
    """Control cover with specific action (open, close, stop)."""
    cover = manager.covers.get_cover(cover_id)
    if not cover:
        raise HTTPException(status_code=404, detail="Cover not found")
    
    action = action_data.action
    if action not in ["open", "close", "stop", "toggle"]:
        raise HTTPException(status_code=400, detail="Invalid action")
    
    if action == "open":
        await cover.open()
    elif action == "close":
        await cover.close()
    elif action == "stop":
        await cover.stop()
    
    return {"status": "success"}

@app.post("/api/covers/{cover_id}/set_position")
async def set_cover_position(cover_id: str, position_data: CoverPosition, manager: Manager = Depends(get_manager)):
    """Control cover with specific action (open, close, stop)."""
    cover = manager.covers.get_cover(cover_id)
    if not cover:
        raise HTTPException(status_code=404, detail="Cover not found")
    
    position = position_data.position
    if position < 0 or position > 100:
        raise HTTPException(status_code=400, detail="Invalid position")
    
    await cover.set_cover_position(position)
    
    return {"status": "success"}

@app.post("/api/covers/{cover_id}/set_tilt")
async def set_cover_tilt(cover_id: str, tilt_data: CoverTilt, manager: Manager = Depends(get_manager)):
    """Control cover with specific action (open, close, stop)."""
    cover: PreviousCover | TimeBasedCover | VenetianCover | None = manager.covers.get_cover(cover_id)
    if not cover:
        raise HTTPException(status_code=404, detail="Cover not found")
    if cover.kind != "venetian":
        raise HTTPException(status_code=400, detail="Invalid cover type")
    tilt = tilt_data.tilt
    if tilt < 0 or tilt > 100:
        raise HTTPException(status_code=400, detail="Invalid tilt")
    
    if isinstance(cover, VenetianCover):
        await cover.set_tilt(tilt)
    else:
        raise HTTPException(status_code=400, detail="Cover does not support tilt control")
    
    return {"status": "success"}

@app.post("/api/modbus/{coordinator_id}/{entity_id}/set_value") 
async def set_modbus_value(
    coordinator_id: str,
    entity_id: str,
    value_data: dict = Body(...),
    manager: Manager = Depends(get_manager)
):
    """Set value for Modbus device entity (regular or additional entity).
    
    Args:
        coordinator_id: Coordinator ID (e.g., "Fuji-PC")
        entity_id: Entity ID or decoded name (e.g., "operatingmode" or "Fuji-PCoperatingmode")
        value_data: Dictionary with 'value' key containing the value to set
        
    Returns:
        Status response
    """
    value = value_data.get("value")
    if value is None:
        raise HTTPException(status_code=400, detail="Value is required")
    
    # Find coordinator by ID
    coordinator = manager.modbus.get_all_coordinators().get(coordinator_id.lower())
    if not coordinator:
        raise HTTPException(status_code=404, detail=f"Modbus coordinator '{coordinator_id}' not found")
    
    # Find entity in the coordinator using unified lookup
    entity = coordinator.find_entity(entity_id)
    
    if not entity:
        raise HTTPException(status_code=404, detail=f"Modbus entity '{entity_id}' not found in coordinator '{coordinator_id}'")
    
    try:
        # Use coordinator's write_register method which handles both regular and additional entities
        await coordinator.write_register(value=value, entity=entity)
        return {"status": "success"}
    except Exception as e:
        _LOGGER.error(f"Error writing Modbus value: {type(e).__name__} - {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error writing Modbus value: {str(e)}")

@app.post("/api/restart")
async def restart_service(background_tasks: BackgroundTasks):
    """Restart the BoneIO service."""
    if not is_running_as_service():
        return {"status": "not available"}

    async def shutdown_and_restart():
        # First stop the web server
        if app.state.web_server:
            await asyncio.sleep(0.1)  # Allow time for the response to be sent
            os._exit(0)  # Terminate the process

    background_tasks.add_task(shutdown_and_restart)
    return {"status": "success"}


@app.get("/api/check_update")
async def check_update():
    """Check if there is a newer version of BoneIO available from GitHub releases.
    
    Returns all available versions with the latest stable version as recommended.
    Dev/prerelease versions are shown as alternatives.
    """
    from boneio.version import __version__ as current_version
    
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
        # GitHub repository information
        repo = "boneIO-eu/app_black"
        
        # Get releases from GitHub API with timeout
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
        
        # Parse all releases
        available_versions = []
        latest_stable = None
        latest_prerelease = None
        
        for release in releases:
            tag = release['tag_name']
            ver_str = tag[1:] if tag.startswith('v') else tag
            is_prerelease = release.get('prerelease', False)
            
            # Also check if version string contains dev/alpha/beta/rc
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
            
            # Track latest stable and prerelease
            if not is_prerelease and latest_stable is None:
                latest_stable = ver_info
            if is_prerelease and latest_prerelease is None:
                latest_prerelease = ver_info
        
        # Determine if current version is a prerelease
        current_ver_lower = current_version.lower()
        current_is_prerelease = any(x in current_ver_lower for x in ['dev', 'alpha', 'beta', 'rc'])
        
        # Determine recommended version based on current version type
        # If user is on prerelease, recommend latest prerelease (if newer)
        # If user is on stable, recommend latest stable
        if current_is_prerelease:
            recommended = latest_prerelease or latest_stable or available_versions[0]
        else:
            recommended = latest_stable or latest_prerelease or available_versions[0]
        
        # Check if update is available
        # Compare with the appropriate version based on current version type
        is_update_available = False
        prerelease_update_available = False
        try:
            current_parsed = version.parse(current_version)
            recommended_parsed = version.parse(recommended["version"])
            is_update_available = recommended_parsed > current_parsed
            
            # If on prerelease, also check if there's a newer prerelease even if stable is recommended
            if current_is_prerelease and latest_prerelease:
                prerelease_parsed = version.parse(latest_prerelease["version"])
                if prerelease_parsed > current_parsed:
                    is_update_available = True
                    recommended = latest_prerelease
            
            # If on stable, check if there's a newer prerelease available (for optional upgrade)
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
            "available_versions": available_versions[:10]  # Return last 10 versions
        }
    except requests.exceptions.Timeout:
        _LOGGER.error("Timeout while checking for updates")
        return {
            "status": "error",
            "message": "Timeout while connecting to GitHub. Check your internet connection.",
            "current_version": current_version
        }
    except requests.exceptions.ConnectionError:
        _LOGGER.error("Connection error while checking for updates")
        return {
            "status": "error",
            "message": "Cannot connect to GitHub. Check your internet connection.",
            "current_version": current_version
        }
    except Exception as e:
        _LOGGER.exception("Error checking for updates: %s", str(e))
        return {
            "status": "error",
            "message": f"Error checking for updates: {str(e)}",
            "current_version": current_version
        }


# Update status tracking
_update_status: dict = {
    "status": "idle",  # idle, running, success, error
    "progress": 0,     # 0-100
    "step": "",        # Current step description
    "log": [],         # Log messages
    "error": None,     # Error message if failed
    "backup_path": None,  # Path to backup if created
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

@app.get("/api/update/status")
async def get_update_status():
    """Get current update status and progress."""
    return _update_status

class UpdateRequest(BaseModel):
    """Request model for update endpoint."""
    version: str | None = None  # Target version to install, None means latest

@app.post("/api/update")
async def update_boneio(background_tasks: BackgroundTasks, request: UpdateRequest = UpdateRequest()):
    """Update the BoneIO package with backup and restart the service.
    
    Args:
        version: Specific version to install (e.g., "1.0.1", "1.0.2dev1").
                 If not provided, installs the latest version from PyPI.
    """
    global _update_status
    
    if not is_running_as_service():
        return {"status": "error", "message": "Update is only available when running as a service"}
    
    if _update_status["status"] == "running":
        return {"status": "error", "message": "Update already in progress"}
    
    target_version = request.version

    async def update_and_restart():
        global _update_status
        import subprocess
        import shutil
        import glob
        from datetime import datetime
        from boneio.version import __version__ as current_version
        
        _reset_update_status()
        _update_status["status"] = "running"
        _update_status["old_version"] = current_version
        _update_status["target_version"] = target_version
        
        try:
            # Allow time for the response to be sent
            await asyncio.sleep(0.3)
            
            # Step 1: Find virtual environment
            _update_progress(5, "Finding virtual environment...")
            
            # Try common venv locations
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
            
            # Step 2: Create backup
            _update_progress(15, "Creating backup...")
            
            backup_dir = os.path.expanduser("~/boneio_backups")
            os.makedirs(backup_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(backup_dir, f"boneio_{current_version}_{timestamp}")
            
            # Find boneio package in site-packages
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
            
            # Step 3: Upgrade pip (optional but recommended)
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
            
            # Step 4: Install boneio update
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
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode != 0:
                _update_status["status"] = "error"
                _update_status["error"] = f"pip install failed: {result.stderr}"
                _update_progress(45, "Update failed", result.stderr)
                return
            
            _update_progress(80, "BoneIO updated", "Package installed successfully")
            
            # Step 5: Get new version
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
            
            # Step 6: Cleanup old backups (keep last 5)
            _update_progress(92, "Cleaning up old backups...")
            
            try:
                backups = sorted(glob.glob(os.path.join(backup_dir, "boneio_*")))
                if len(backups) > 5:
                    for old_backup in backups[:-5]:
                        shutil.rmtree(old_backup, ignore_errors=True)
                    _update_progress(95, "Cleanup done", f"Removed {len(backups) - 5} old backups")
            except Exception as e:
                _update_progress(95, "Cleanup skipped", f"Could not cleanup: {e}")
            
            # Step 7: Prepare for restart
            _update_status["status"] = "success"
            _update_progress(100, "Update complete!", f"Restarting service in 2 seconds...")
            
            # Wait a bit so frontend can see 100% progress
            await asyncio.sleep(2)
            
            # Terminate the process to trigger systemd restart
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

@app.post("/api/update/rollback")
async def rollback_update():
    """Rollback to the previous version from backup."""
    import subprocess
    import shutil
    import glob
    
    if not is_running_as_service():
        return {"status": "error", "message": "Rollback is only available when running as a service"}
    
    backup_dir = os.path.expanduser("~/boneio_backups")
    backups = sorted(glob.glob(os.path.join(backup_dir, "boneio_*")))
    
    if not backups:
        return {"status": "error", "message": "No backups found"}
    
    latest_backup = backups[-1]
    
    # Find venv
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
    
    # Find current boneio installation
    boneio_dirs = glob.glob(f"{venv_path}/lib/python*/site-packages/boneio")
    
    if not boneio_dirs:
        return {"status": "error", "message": "Current boneio installation not found"}
    
    try:
        # Remove current installation
        shutil.rmtree(boneio_dirs[0])
        
        # Restore from backup
        shutil.copytree(latest_backup, boneio_dirs[0])
        
        _LOGGER.info(f"Rolled back to backup: {latest_backup}")
        
        return {
            "status": "success", 
            "message": f"Rolled back to {os.path.basename(latest_backup)}. Restart required.",
            "backup_used": latest_backup
        }
    except Exception as e:
        return {"status": "error", "message": f"Rollback failed: {e}"}

@app.get("/api/update/backups")
async def list_backups():
    """List available backups."""
    import glob
    
    backup_dir = os.path.expanduser("~/boneio_backups")
    backups = sorted(glob.glob(os.path.join(backup_dir, "boneio_*")), reverse=True)
    
    backup_list = []
    for backup in backups:
        name = os.path.basename(backup)
        # Parse version and timestamp from name: boneio_1.2.3_20231206_131500
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


@app.get("/api/config/download")
async def download_config():
    """Download current configuration as a tar.gz archive.
    
    Creates a compressed archive containing all YAML configuration files
    from the config directory.
    """
    import tarfile
    import io
    from datetime import datetime
    from fastapi.responses import StreamingResponse
    
    config_file = app.state.yaml_config_file
    config_dir = Path(config_file).parent
    
    # Create tar.gz in memory
    buffer = io.BytesIO()
    
    with tarfile.open(fileobj=buffer, mode='w:gz') as tar:
        # Add all yaml files from config directory
        for pattern in ["*.yaml", "*.yml"]:
            for yaml_file in config_dir.glob(pattern):
                if yaml_file.is_file():
                    # Add file with relative path
                    arcname = yaml_file.name
                    tar.add(str(yaml_file), arcname=arcname)
                    _LOGGER.debug(f"Added {arcname} to config archive")
        
        # Also check for subdirectories with yaml files (e.g., includes)
        for subdir in config_dir.iterdir():
            if subdir.is_dir() and not subdir.name.startswith('.'):
                for pattern in ["*.yaml", "*.yml"]:
                    for yaml_file in subdir.glob(pattern):
                        if yaml_file.is_file():
                            arcname = f"{subdir.name}/{yaml_file.name}"
                            tar.add(str(yaml_file), arcname=arcname)
                            _LOGGER.debug(f"Added {arcname} to config archive")
    
    buffer.seek(0)
    
    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"boneio_config_{timestamp}.tar.gz"
    
    _LOGGER.info(f"Downloading config archive: {filename}")
    
    return StreamingResponse(
        buffer,
        media_type="application/gzip",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


@app.post("/api/config/restore")
async def restore_config(file: UploadFile = File(...)):
    """Restore configuration from a tar.gz archive.
    
    Extracts and replaces YAML configuration files from uploaded archive.
    Creates a backup of current config before restoring.
    """
    import tarfile
    import io
    import shutil
    from datetime import datetime
    
    config_file = app.state.yaml_config_file
    config_dir = Path(config_file).parent
    
    try:
        # Validate file type
        if not file.filename or not file.filename.endswith(('.tar.gz', '.tgz')):
            return {
                "status": "error",
                "message": "Invalid file type. Please upload a .tar.gz or .tgz file."
            }
        
        # Read uploaded file
        contents = await file.read()
        buffer = io.BytesIO(contents)
        
        # Create backup of current config before restoring
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = config_dir / "backups"
        backup_dir.mkdir(exist_ok=True)
        backup_path = backup_dir / f"config_backup_{timestamp}.tar.gz"
        
        # Backup current config
        with tarfile.open(backup_path, mode='w:gz') as tar:
            for pattern in ["*.yaml", "*.yml"]:
                for yaml_file in config_dir.glob(pattern):
                    if yaml_file.is_file():
                        tar.add(str(yaml_file), arcname=yaml_file.name)
            
            # Backup subdirectories
            for subdir in config_dir.iterdir():
                if subdir.is_dir() and not subdir.name.startswith('.') and subdir.name != 'backups':
                    for pattern in ["*.yaml", "*.yml"]:
                        for yaml_file in subdir.glob(pattern):
                            if yaml_file.is_file():
                                tar.add(str(yaml_file), arcname=f"{subdir.name}/{yaml_file.name}")
        
        _LOGGER.info(f"Created backup before restore: {backup_path}")
        
        # Extract and restore files
        restored_files = []
        with tarfile.open(fileobj=buffer, mode='r:gz') as tar:
            # Validate archive contents
            members = tar.getmembers()
            for member in members:
                # Security check - prevent path traversal
                if '..' in member.name or member.name.startswith('/'):
                    return {
                        "status": "error",
                        "message": f"Invalid file path in archive: {member.name}"
                    }
                
                # Only allow yaml files
                if not (member.name.endswith('.yaml') or member.name.endswith('.yml')):
                    _LOGGER.warning(f"Skipping non-YAML file: {member.name}")
                    continue
            
            # Extract files
            for member in members:
                if member.name.endswith('.yaml') or member.name.endswith('.yml'):
                    # Extract to config directory
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
        
        # Invalidate config cache
        invalidate_config_cache()
        
        # Validate restored configuration
        try:
            load_config_from_file(config_file=app.state.yaml_config_file)
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
        return {
            "status": "error",
            "message": f"Failed to extract archive: {str(e)}"
        }
    except Exception as e:
        _LOGGER.error(f"Failed to restore config: {e}")
        return {
            "status": "error",
            "message": f"Failed to restore configuration: {str(e)}"
        }

@app.get("/api/version")
async def get_version():
    """Get application version."""
    return {"version": __version__} 

@app.get("/api/name")
async def get_name(config_helper: ConfigHelper = Depends(get_config_helper)):
    """Get application version."""
    return {"name": config_helper.name} 

@app.get("/api/check_configuration")
async def check_configuration():
    """Check if the configuration is valid."""
    try:
        load_config_from_file(config_file=app.state.yaml_config_file)
        return {"status": "success"}
    except ConfigurationException as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# Config cache to avoid re-parsing YAML on every request
# Uses file mtime to detect external changes (e.g., manual edits in bash)
_config_cache: dict = {"data": None, "mtime": 0}

def invalidate_config_cache():
    """Invalidate config cache - call after saving config."""
    _config_cache["data"] = None
    _config_cache["mtime"] = 0

def _get_config_mtime(config_file: str) -> float:
    """Get the latest mtime of config file and all included files."""
    import os
    from pathlib import Path
    
    config_dir = Path(config_file).parent
    max_mtime = os.path.getmtime(config_file)
    
    # Also check common include files
    for pattern in ["*.yaml", "*.yml"]:
        for f in config_dir.glob(pattern):
            try:
                mtime = os.path.getmtime(f)
                if mtime > max_mtime:
                    max_mtime = mtime
            except OSError:
                pass
    
    return max_mtime

@app.get("/api/config")
async def get_parsed_config():
    """Get parsed configuration data with !include resolved (cached with mtime check)."""
    import time
    try:
        config_file = app.state.yaml_config_file
        current_mtime = _get_config_mtime(config_file)
        
        # Return cached config if available and file hasn't changed
        if _config_cache["data"] is not None and _config_cache["mtime"] >= current_mtime:
            _LOGGER.debug("Returning cached configuration (mtime unchanged)")
            return {"config": _config_cache["data"]}
        
        # Load config using BoneIOLoader which handles !include
        start = time.time()
        config_data = load_config_from_file(config_file)
        elapsed = time.time() - start
        
        # Cache the result with current mtime
        _config_cache["data"] = config_data
        _config_cache["mtime"] = current_mtime
        
        _LOGGER.info("Loaded and cached configuration in %.2fs (mtime: %.0f)", elapsed, current_mtime)
        return {"config": config_data}
        
    except Exception as e:
        _LOGGER.error(f"Error loading parsed configuration: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error loading configuration: {str(e)}")

@app.get("/api/interlock-groups")
async def get_interlock_groups():
    """Get list of all registered interlock group names.
    
    Returns:
        List of unique interlock group names currently in use
    """
    manager = app.state.manager
    if not manager or not hasattr(manager, '_output_manager'):
        return {"groups": []}
    
    output_manager = manager._output_manager
    if not output_manager or not hasattr(output_manager, '_interlock_manager'):
        return {"groups": []}
    
    groups = output_manager._interlock_manager.get_all_groups()
    return {"groups": groups}


@app.get("/api/dallas/available")
async def get_available_dallas_sensors():
    """Get list of available Dallas 1-Wire temperature sensors.
    
    Scans for connected DS18B20 and other Dallas sensors and returns
    their addresses for configuration.
    
    Returns:
        Dictionary with list of available sensors
    """
    try:
        from w1thermsensor import W1ThermSensor
        
        sensors = []
        for sensor in W1ThermSensor.get_available_sensors():
            sensors.append({
                "address": sensor.id,
                "type": sensor.type.name if hasattr(sensor.type, 'name') else str(sensor.type),
            })
        
        return {"sensors": sensors, "count": len(sensors)}
    except ImportError:
        _LOGGER.warning("w1thermsensor library not installed")
        return {"sensors": [], "count": 0, "error": "w1thermsensor library not installed"}
    except Exception as e:
        _LOGGER.error(f"Error scanning for Dallas sensors: {e}")
        return {"sensors": [], "count": 0, "error": str(e)}


@app.get("/api/sensors/loaded")
async def get_loaded_sensors(manager: Manager = Depends(get_manager)):
    """Get list of currently loaded sensors.
    
    Returns information about all sensors that are currently active in the system.
    Useful for debugging sensor configuration issues.
    """
    result = {
        "dallas": [],
        "temp": [],
        "ina219": [],
        "adc": [],
        "system": [],
    }
    
    # Dallas sensors
    for sensor in manager.sensors.get_dallas_sensors():
        result["dallas"].append({
            "id": sensor.id,
            "name": sensor.name,
            "address": sensor.address if hasattr(sensor, 'address') else None,
            "state": sensor.state,
            "unit": sensor.unit_of_measurement,
            "timestamp": sensor.last_timestamp,
        })
    
    # All temp sensors (includes Dallas + I2C temp sensors)
    for sensor in manager.sensors.get_all_temp_sensors():
        result["temp"].append({
            "id": sensor.id,
            "name": sensor.name,
            "state": sensor.state,
            "unit": sensor.unit_of_measurement,
        })
    
    # INA219 sensors
    for ina_device in manager.sensors.get_ina219_sensors():
        for sensor in ina_device.sensors.values():
            result["ina219"].append({
                "id": sensor.id,
                "name": sensor.name,
                "state": sensor.state,
                "unit": sensor.unit_of_measurement,
            })
    
    # ADC sensors
    for sensor in manager.sensors.get_adc_sensors():
        result["adc"].append({
            "id": sensor.id,
            "name": sensor.name,
            "state": sensor.state,
        })
    
    # System sensors
    for sensor in manager.sensors.get_system_sensors():
        result["system"].append({
            "id": sensor.id,
            "name": sensor.name,
            "state": sensor.state,
            "unit": sensor.unit_of_measurement,
        })
    
    return result


# ============================================================================
# Modbus Helper API Endpoints
# ============================================================================

# Global lock for Modbus Helper operations to prevent concurrent access
_modbus_helper_lock = asyncio.Lock()

# Flag to cancel ongoing Modbus search
_modbus_search_cancel = False


class ModbusGetRequest(BaseModel):
    """Request model for Modbus GET operation."""
    address: int
    register_address: int
    register_type: str = "holding"  # "holding" or "input"
    value_type: str = "S_WORD"  # U_WORD, S_WORD, U_DWORD, S_DWORD, FP32, etc.


class ModbusSetRequest(BaseModel):
    """Request model for Modbus SET operation."""
    address: int
    register_address: int
    value: int | float
    

class ModbusSearchRequest(BaseModel):
    """Request model for Modbus SEARCH operation."""
    register_address: int = 1
    register_type: str = "input"  # "holding" or "input"
    start_address: int = 1
    end_address: int = 247
    timeout: float = 0.3  # Timeout per device in seconds


class ModbusConfigureDeviceRequest(BaseModel):
    """Request model for Modbus device configuration (set address/baudrate)."""
    device: str  # Device model name (e.g., "cwt", "sht30")
    uart: str  # UART name (e.g., "uart4", "uart1")
    current_address: int
    current_baudrate: int
    new_address: int | None = None
    new_baudrate: int | None = None


@app.post("/api/modbus/get")
async def modbus_get(
    request: ModbusGetRequest,
    boneio_manager: Manager = Depends(get_manager)
):
    """Read a register from a Modbus device.
    
    Uses the existing Modbus client from the manager to read registers.
    Operations are serialized using a lock to prevent concurrent access.
    
    Args:
        request: ModbusGetRequest with device address and register info
        
    Returns:
        dict: Contains the read value or error message
    """
    # Check if Modbus is configured
    modbus_client = boneio_manager.modbus.get_modbus_client()
    if not modbus_client:
        return {
            "success": False,
            "error": "Modbus is not configured. Add 'modbus' section to your config.",
        }
    
    async with _modbus_helper_lock:
        try:
            # Determine register count based on value type
            value_size = 1 if request.value_type in ["S_WORD", "U_WORD"] else 2
            if request.value_type in ["U_QWORD", "S_QWORD", "U_QWORD_R"]:
                value_size = 4
            
            # Read registers
            result = await modbus_client.read_registers(
                unit=request.address,
                address=request.register_address,
                count=value_size,
                method=request.register_type,
            )
            
            if result and hasattr(result, 'registers'):
                payload = result.registers[0:value_size]
                decoded_value = modbus_client.decode_value(payload, request.value_type)
                
                return {
                    "success": True,
                    "value": decoded_value,
                    "raw_registers": list(payload),
                }
            else:
                return {
                    "success": False,
                    "error": "No response from device",
                }
                
        except Exception as e:
            _LOGGER.error(f"Modbus GET error: {e}")
            return {
                "success": False,
                "error": str(e),
            }


@app.post("/api/modbus/set")
async def modbus_set(
    request: ModbusSetRequest,
    boneio_manager: Manager = Depends(get_manager)
):
    """Write to a Modbus device register.
    
    Uses the existing Modbus client from the manager to write registers.
    
    Args:
        request: ModbusSetRequest with device address, register and value
        
    Returns:
        dict: Contains success status and message
    """
    # Check if Modbus is configured
    modbus_client = boneio_manager.modbus.get_modbus_client()
    if not modbus_client:
        return {
            "success": False,
            "error": "Modbus is not configured. Add 'modbus' section to your config.",
        }
    
    async with _modbus_helper_lock:
        try:
            # Write single register
            result = await modbus_client.write_register(
                unit=request.address,
                address=request.register_address,
                value=int(request.value),
            )
            
            if result:
                return {
                    "success": True,
                    "message": "Value written successfully.",
                }
            else:
                return {
                    "success": False,
                    "error": "Write operation failed - no response from device",
                }
                
        except Exception as e:
            _LOGGER.error(f"Modbus SET error: {e}")
            return {
                "success": False,
                "error": str(e),
            }


@app.get("/api/modbus/search/stream")
async def modbus_search_stream(
    start_address: int = 1,
    end_address: int = 247,
    register_address: int = 1,
    register_type: str = "input",
    timeout: float = 0.3,
    boneio_manager: Manager = Depends(get_manager)
):
    """Search for Modbus devices with Server-Sent Events for real-time updates.
    
    Streams progress and found devices as they are discovered.
    
    Args:
        start_address: First address to scan
        end_address: Last address to scan
        register_address: Register to read for detection
        register_type: Type of register (input/holding)
        timeout: Timeout per device in seconds
        
    Returns:
        SSE stream with progress updates
    """
    global _modbus_search_cancel
    
    async def event_generator():
        """Generate SSE events for search progress."""
        global _modbus_search_cancel
        
        # Check if Modbus is configured
        modbus_client = boneio_manager.modbus.get_modbus_client()
        if not modbus_client:
            yield f"data: {json.dumps({'type': 'error', 'error': 'Modbus is not configured'})}\n\n"
            return
        
        # Reset cancel flag
        _modbus_search_cancel = False
        
        async with _modbus_helper_lock:
            found_devices = []
            total = end_address - start_address + 1
            scanned = 0
            
            # Send start event
            yield f"data: {json.dumps({'type': 'start', 'total': total})}\n\n"
            
            for addr in range(start_address, end_address + 1):
                # Check if cancelled
                if _modbus_search_cancel:
                    yield f"data: {json.dumps({'type': 'cancelled', 'scanned': scanned, 'total': total, 'devices': found_devices})}\n\n"
                    return
                
                # Scan device
                try:
                    found = await modbus_client.scan_device(
                        unit=addr,
                        address=register_address,
                        method=register_type,
                        timeout=timeout,
                    )
                    
                    if found:
                        found_devices.append(addr)
                        _LOGGER.info(f"Found Modbus device at address {addr}")
                        # Send found event immediately with current progress
                        yield f"data: {json.dumps({'type': 'found', 'address': addr, 'devices': list(found_devices), 'scanned': scanned + 1, 'total': total})}\n\n"
                        
                except Exception:
                    pass
                
                scanned += 1
                
                # Send progress every 5 addresses
                if scanned % 5 == 0:
                    yield f"data: {json.dumps({'type': 'progress', 'scanned': scanned, 'total': total, 'current': addr})}\n\n"
                
                await asyncio.sleep(0.02)
            
            # Send complete event
            yield f"data: {json.dumps({'type': 'complete', 'devices': found_devices, 'count': len(found_devices), 'scanned': scanned, 'total': total})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@app.post("/api/modbus/search/cancel")
async def modbus_search_cancel():
    """Cancel an ongoing Modbus search operation.
    
    Sets the cancel flag which will be checked by the search loop.
    
    Returns:
        dict: Confirmation that cancel was requested
    """
    global _modbus_search_cancel
    _modbus_search_cancel = True
    _LOGGER.info("Modbus search cancel requested")
    return {"success": True, "message": "Cancel requested"}


@app.get("/api/modbus/config")
async def get_modbus_config(boneio_manager: Manager = Depends(get_manager)):
    """Get available Modbus configuration options.
    
    Returns available value types and whether Modbus is configured.
    """
    modbus_client = boneio_manager.modbus.get_modbus_client()
    
    return {
        "configured": modbus_client is not None,
        "register_types": ["holding", "input"],
        "value_types": [
            "U_WORD", "S_WORD", 
            "U_DWORD", "S_DWORD", "U_DWORD_R", "S_DWORD_R",
            "U_QWORD", "S_QWORD", "U_QWORD_R",
            "FP32", "FP32_R"
        ],
    }


@app.post("/api/modbus/configure-device")
async def modbus_configure_device(
    request: ModbusConfigureDeviceRequest,
    boneio_manager: Manager = Depends(get_manager)
):
    """Configure Modbus device (set new address or baudrate).
    
    This endpoint allows changing the address or baudrate of a Modbus device.
    Uses the existing Modbus client from the manager to avoid port conflicts.
    The device must be connected and responding at the current address.
    After changing settings, the device needs to be power-cycled.
    
    Args:
        request: Configuration request with device model, current settings, and new settings
        
    Returns:
        dict: Success status and message
    """
    import os
    from boneio.core.utils import open_json
    
    SET_BASE = "set_base"
    
    # Check if Modbus is configured
    modbus_client = boneio_manager.modbus.get_modbus_client()
    if not modbus_client:
        return {
            "success": False,
            "error": "Modbus is not configured. Add 'modbus' section to your config.",
        }
    
    async with _modbus_helper_lock:
        try:
            _LOGGER.info(
                f"Configuring device {request.device} on {request.uart} at address {request.current_address}, "
                f"baudrate {request.current_baudrate}, new_address={request.new_address}, "
                f"new_baudrate={request.new_baudrate}"
            )
            
            # Check if we need to temporarily change baudrate
            original_baudrate = None
            if modbus_client.client and hasattr(modbus_client.client, 'baudrate'):
                original_baudrate = modbus_client.client.baudrate
                if original_baudrate != request.current_baudrate:
                    _LOGGER.info(
                        f"Temporarily changing baudrate from {original_baudrate} to {request.current_baudrate} "
                        f"to communicate with device"
                    )
                    # Close current connection
                    if modbus_client.client.connected:
                        modbus_client.client.close()
                    # Change baudrate
                    modbus_client.client.baudrate = request.current_baudrate
                    # Reconnect with new baudrate
                    modbus_client.client.connect()
            
            # Load device configuration to get register addresses
            _db = open_json(
                path=os.path.join(os.path.dirname(__file__), "..", "modbus", "devices", "sensors"),
                model=request.device
            )
            set_base = _db.get(SET_BASE, {})
            
            if not set_base:
                return {
                    "success": False,
                    "error_key": "configure_error_no_support",
                    "error_params": {"device": request.device}
                }
            
            # Perform the requested operation
            if request.new_address is not None:
                # Set new address
                address_register = set_base.get("set_address_address")
                if address_register is None:
                    return {
                        "success": False,
                        "error_key": "configure_error_no_address",
                        "error_params": {"device": request.device}
                    }
                
                _LOGGER.info(f"Writing new address {request.new_address} to register {address_register}")
                result = await modbus_client.write_register(
                    unit=request.current_address,
                    address=address_register,
                    value=request.new_address,
                )
                
                if not result:
                    return {
                        "success": False,
                        "error_key": "configure_error_write_address"
                    }
                    
            elif request.new_baudrate is not None:
                # Set new baudrate
                baudrate_config = set_base.get("set_baudrate")
                if not baudrate_config:
                    return {
                        "success": False,
                        "error_key": "configure_error_no_baudrate",
                        "error_params": {"device": request.device}
                    }
                
                baudrate_register = baudrate_config.get("address")
                possible_baudrates = baudrate_config.get("possible_baudrates", {})
                baudrate_value = possible_baudrates.get(str(request.new_baudrate))
                
                if baudrate_value is None:
                    return {
                        "success": False,
                        "error_key": "configure_error_baudrate_not_supported",
                        "error_params": {"supported": ", ".join(possible_baudrates.keys())}
                    }
                
                _LOGGER.info(f"Writing baudrate value {baudrate_value} (for {request.new_baudrate}) to register {baudrate_register}")
                result = await modbus_client.write_register(
                    unit=request.current_address,
                    address=baudrate_register,
                    value=baudrate_value,
                )
                
                if not result:
                    return {
                        "success": False,
                        "error_key": "configure_error_write_baudrate"
                    }
            else:
                return {
                    "success": False,
                    "error_key": "configure_error_no_operation"
                }
            
            return {
                "success": True,
                "message_key": "configure_success"
            }
                
        except Exception as e:
            _LOGGER.error(f"Modbus configure error: {e}")
            return {
                "success": False,
                "error": str(e),
            }
        finally:
            # Restore original baudrate if it was changed
            if original_baudrate is not None and original_baudrate != request.current_baudrate:
                try:
                    _LOGGER.info(f"Restoring original baudrate {original_baudrate}")
                    if modbus_client.client.connected:
                        modbus_client.client.close()
                    modbus_client.client.baudrate = original_baudrate
                    modbus_client.client.connect()
                except Exception as restore_error:
                    _LOGGER.error(f"Failed to restore original baudrate: {restore_error}")


@app.get("/api/files")
async def list_files(path: Optional[str] = None):
    """List files in the config directory."""
    config_dir = Path(app.state.yaml_config_file).parent
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
                if children:  # Only include directories that have yaml files in them
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

@app.get("/api/files/{file_path:path}")
async def get_file_content(file_path: str):
    """Get content of a file."""
    config_dir = Path(app.state.yaml_config_file).parent
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


@app.put("/api/files/{file_path:path}")
async def update_file_content(file_path: str, content: dict = Body(...)):
    """Update content of a file."""
    config_dir = Path(app.state.yaml_config_file).parent
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

@app.get("/api/status/restart")
async def get_restart_status():
    """Get restart required status.
    
    Returns information about whether the application needs to be restarted
    due to configuration changes in sections that don't support hot-reload.
    
    Returns:
        dict: {
            "restart_required": bool,
            "sections": list of section names that were modified
        }
    """
    manager: Manager = app.state.manager
    return {
        "restart_required": manager.config_helper.restart_required,
        "sections": manager.config_helper.restart_required_sections
    }

@app.put("/api/config/{section}")
async def update_section_content(section: str, data: dict | list = Body(...)):
    """Update content of a configuration section.
    
    Args:
        section: Name of the config section (e.g., 'mqtt', 'output_group')
        data: Section data - can be dict (for single-value sections like mqtt) 
              or list (for array sections like output_group, output, event)
    """
    
    # Sections that require full application restart
    RESTART_REQUIRED_SECTIONS = {'boneio', 'mqtt', 'web', 'modbus'}
    
    try:
        result = update_config_section(app.state.yaml_config_file, section, data)
        if result["status"] == "error":
            raise HTTPException(status_code=500, detail=result["message"])
        
        # Invalidate config cache after successful save
        invalidate_config_cache()
        
        # Mark restart required for sections that need it
        if section in RESTART_REQUIRED_SECTIONS:
            manager: Manager = app.state.manager
            manager.config_helper.set_restart_required(section)
            result["restart_required"] = True
            result["restart_required_sections"] = manager.config_helper.restart_required_sections
        
        return result
        
    except Exception as e:
        _LOGGER.error(f"Error saving section '{section}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error saving section: {str(e)}")

@app.post("/api/config/reload")
async def reload_configuration(
    sections: list[str] | None = Body(None, description="Optional list of sections to reload. Supported: 'output', 'cover', 'input', 'event', 'binary_sensor', 'modbus_devices', 'sensor'")
):
    """Reload configuration from file.
    
    This endpoint allows hot-reloading of configuration sections that support it.
    Currently supports: 'output', 'cover', 'input', 'modbus_devices', 'sensor'
    
    Args:
        sections: Optional list of section names to reload.
                 If not provided, reloads all supported sections.
                 Supported sections:
                 - 'output': Reload outputs and output groups
                 - 'cover': Reload covers
                 - 'input': Reload all inputs (event buttons and binary sensors)
                 - 'event': Alias for 'input' (reloads all inputs)
                 - 'binary_sensor': Alias for 'input' (reloads all inputs)
                 - 'modbus_devices': Reload Modbus device coordinators (recreates coordinators)
                 - 'sensor': Reload Dallas temperature sensors
    
    Returns:
        dict: Status of reload operation with details about reloaded and failed sections
    """
    manager: Manager = app.state.manager
    
    try:
        # Send config reload event to WebSocket clients before reload
        # This tells frontend to clear old states
        from boneio.models.events import ConfigReloadEvent
        reload_event = ConfigReloadEvent(sections=sections or ["all"])
        websocket_manager: WebSocketManager = app.state.websocket_manager
        await websocket_manager.broadcast(reload_event.model_dump())
        
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

def on_exit(self) -> None:
    asyncio.create_task(app.state.websocket_manager.close_all())


async def boneio_state_changed_callback(event: Event):
    """Callback when BoneIO state changes."""
    websocket_manager: WebSocketManager = app.state.websocket_manager
    await websocket_manager.broadcast_state(event)



def init_app(
    manager: Manager,
    yaml_config_file: str,
    config_helper: ConfigHelper,
    auth_config: dict = {},
    jwt_secret: str | None = None,
    web_server: WebServer | None = None,
    initial_config: dict | None = None,
) -> BoneIOApp:
    """Initialize the FastAPI application with manager.
    
    Args:
        initial_config: Pre-parsed config to populate cache (avoids slow first request)
    """
    global _auth_config, JWT_SECRET
    
    # Pre-populate config cache if initial_config provided
    if initial_config is not None:
        import os
        _config_cache["data"] = initial_config
        _config_cache["mtime"] = _get_config_mtime(yaml_config_file)
        _LOGGER.info("Config cache pre-populated from initial_config")
    
    # Set JWT secret
    if jwt_secret:
        JWT_SECRET = jwt_secret
    else:
        JWT_SECRET = secrets.token_hex(32)  # Fallback to temporary secret
    
    app.state.manager = manager
    app.state.auth_config = auth_config
    app.state.yaml_config_file = yaml_config_file
    app.state.web_server = web_server
    app.state.config_helper = config_helper
    app.state.websocket_manager = WebSocketManager(
        jwt_secret=jwt_secret,
        auth_required=bool(auth_config)
    )

    if auth_config:
        username = auth_config.get("username")
        password = auth_config.get("password")
        if not username or not password:
            _LOGGER.error("Missing username or password in config!")
        else:
            _auth_config = auth_config
            app.add_middleware(AuthMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Add GZip compression for responses > 500 bytes
    # This significantly reduces transfer size for JSON schemas (~83KB -> ~8KB)
    app.add_middleware(GZipMiddleware, minimum_size=500)
    
    return app


def add_listener_for_all_outputs(boneio_manager: Manager):
    for output in boneio_manager.outputs.get_all_outputs().values():
        if output.output_type == COVER or output.output_type == NONE:
            continue
        boneio_manager.event_bus.add_event_listener(
            event_type="output",
            entity_id=output.id,
            listener_id="ws",
            target=boneio_state_changed_callback,
        )


def remove_listener_for_all_outputs(boneio_manager: Manager):
    boneio_manager.event_bus.remove_event_listener(event_type="output", listener_id="ws")


def add_listener_for_all_groups(boneio_manager: Manager):
    """Add WebSocket listeners for all output groups."""
    for group in boneio_manager.outputs.get_all_output_groups().values():
        boneio_manager.event_bus.add_event_listener(
            event_type="group",
            entity_id=group.id,
            listener_id="ws",
            target=boneio_state_changed_callback,
        )


def remove_listener_for_all_groups(boneio_manager: Manager):
    """Remove WebSocket listeners for all output groups."""
    boneio_manager.event_bus.remove_event_listener(event_type="group", listener_id="ws")


def add_listener_for_all_covers(boneio_manager: Manager):
    for cover in boneio_manager.covers.get_all_covers().values():
        boneio_manager.event_bus.add_event_listener(
            event_type="cover",
            entity_id=cover.id,
            listener_id="ws",
            target=boneio_state_changed_callback,
        )


def remove_listener_for_all_covers(boneio_manager: Manager):
    boneio_manager.event_bus.remove_event_listener(
        event_type="cover",
        listener_id="ws"
    )

def add_listener_for_all_inputs(boneio_manager: Manager):
    for input in boneio_manager.inputs.get_inputs_list():
        boneio_manager.event_bus.add_event_listener(
            event_type="input",
            entity_id=input.id,
            listener_id="ws",
            target=boneio_state_changed_callback,
        )


def remove_listener_for_all_inputs(boneio_manager: Manager):
    boneio_manager.event_bus.remove_event_listener(event_type="input", listener_id="ws")


async def inputs_reloaded_callback(event):
    """Callback when inputs are reloaded - re-send all input states to WebSocket clients."""
    from boneio.models import InputState
    from boneio.models.events import InputEvent
    
    websocket_manager: WebSocketManager = app.state.websocket_manager
    manager: Manager = app.state.manager
    
    _LOGGER.debug("Inputs reloaded, broadcasting all input states to WebSocket clients")
    
    for input_ in manager.inputs.get_inputs_list():
        try:
            input_state = InputState(
                name=input_.name,
                state=input_.last_state,
                type=input_.input_type,
                pin=input_.pin,
                timestamp=input_.last_press_timestamp,
                boneio_input=input_.boneio_input,
                area=input_.area
            )
            update = InputEvent(entity_id=input_.id, state=input_state, click_type=None, duration=None)
            await websocket_manager.broadcast_state(update)
        except Exception as e:
            _LOGGER.error(f"Error broadcasting input state for {input_.id}: {e}")


def add_listener_for_inputs_reloaded(boneio_manager: Manager):
    """Add listener for inputs reloaded event."""
    boneio_manager.event_bus.add_event_listener(
        event_type="inputs_reloaded",
        entity_id="",
        listener_id="ws_inputs_reload",
        target=inputs_reloaded_callback,
    )


def remove_listener_for_inputs_reloaded(boneio_manager: Manager):
    """Remove listener for inputs reloaded event."""
    boneio_manager.event_bus.remove_event_listener(event_type="inputs_reloaded", listener_id="ws_inputs_reload")


def sensor_listener_for_all_sensors(boneio_manager: Manager):
    for modbus_coordinator in boneio_manager.modbus.get_all_coordinators().values():
        if not modbus_coordinator:
            continue
        # Listen to regular modbus entities
        for entities in modbus_coordinator.get_all_entities():
            for entity in entities.values():
                boneio_manager.event_bus.add_event_listener(
                    event_type="modbus_device",
                    entity_id=entity.id,
                    listener_id="ws",
                    target=boneio_state_changed_callback,
                )
        # Listen to additional entities (derived entities)
        for additional_entities in modbus_coordinator.get_all_additional_entities():
            for entity in additional_entities.values():
                boneio_manager.event_bus.add_event_listener(
                    event_type="modbus_device",
                    entity_id=entity.id,
                    listener_id="ws",
                    target=boneio_state_changed_callback,
                )
    for single_ina_device in boneio_manager.sensors.get_ina219_sensors():
        for ina in single_ina_device.sensors.values():
            boneio_manager.event_bus.add_event_listener(
                event_type="sensor",
                entity_id=ina.id,
                listener_id="ws",
                target=boneio_state_changed_callback,
            )
    for sensor in boneio_manager.sensors.get_all_temp_sensors():
        boneio_manager.event_bus.add_event_listener(
            event_type="sensor",
            entity_id=sensor.id,
            listener_id="ws",
            target=boneio_state_changed_callback,
        )


def remove_listener_for_all_sensors(boneio_manager: Manager):
    boneio_manager.event_bus.remove_event_listener(listener_id="ws")
    boneio_manager.event_bus.remove_event_listener(event_type="sensor", listener_id="ws")


@app.websocket("/ws/state")
async def websocket_endpoint(
    websocket: WebSocket, boneio_manager: Manager = Depends(get_manager)
):
    """WebSocket endpoint for all state updates."""
    try:
        # Connect to WebSocket manager
        websocket_manager: WebSocketManager = app.state.websocket_manager
        if await websocket_manager.connect(websocket):
            _LOGGER.info("New WebSocket connection established")

            async def send_state_update(update: Event) -> bool:
                """Send state update and return True if successful."""
                try:
                    if websocket.application_state == WebSocketState.CONNECTED:
                        await websocket.send_json(update.model_dump())
                        return True
                except Exception as e:
                    _LOGGER.error(f"Error sending state update: {type(e).__name__} - {e}")
                return False

            # Send initial states
            try:
                # Send inputs
                for input_ in boneio_manager.inputs.get_inputs_list():
                    try:
                        input_state = InputState(
                            name=input_.name,
                            state=input_.last_state,
                            type=input_.input_type,
                            pin=input_.pin,
                            timestamp=input_.last_press_timestamp,
                            boneio_input=input_.boneio_input,
                            area=input_.area
                        )
                        update = InputEvent(entity_id=input_.id, state=input_state, click_type=None, duration=None)
                        if not await send_state_update(update):
                            return

                    except Exception as e:
                        _LOGGER.error(f"Error preparing input state: {type(e).__name__} - {e}")

                # Send outputs
                for output in boneio_manager.outputs.get_all_outputs().values():
                    try:
                        output_state = OutputState(
                            id=output.id,
                            name=output.name,
                            state=output.state,
                            type=output.output_type,
                            pin=getattr(output, 'pin_id', None),
                            expander_id=output.expander_id,
                            timestamp=output.last_timestamp,
                            area=getattr(output, 'area', None),
                            interlock_groups=getattr(output, '_interlock_groups', []),
                        )
                        update = OutputEvent(entity_id=output.id, state=output_state)
                        if not await send_state_update(update):
                            return

                    except Exception as e:
                        _LOGGER.error(f"Error preparing output state: {type(e).__name__} - {e}")

                # Send output groups
                for group in boneio_manager.outputs.get_all_output_groups().values():
                    try:
                        group_state = GroupState(
                            id=group.id,
                            name=group.name,
                            state=group.state,
                            type=group.output_type,
                            timestamp=getattr(group, 'last_timestamp', None),
                        )
                        update = GroupEvent(entity_id=group.id, state=group_state)
                        if not await send_state_update(update):
                            return

                    except Exception as e:
                        _LOGGER.error(f"Error preparing group state: {type(e).__name__} - {e}")

                # Send covers
                for cover in boneio_manager.covers.get_all_covers().values():
                    try:
                        cover_state = CoverState(
                            id=cover.id,
                            name=cover.name,
                            state=cover.state,
                            position=cover.position,
                            kind=cover.kind,
                            timestamp=cover.last_timestamp,
                            current_operation=cover.current_operation,
                        )
                        if getattr(cover, 'kind', None) == 'venetian':
                            cover_state.tilt = getattr(cover, 'tilt', 0)
                        update = CoverEvent(entity_id=cover.id, state=cover_state)
                        if not await send_state_update(update):
                            return

                    except Exception as e:
                        _LOGGER.error(f"Error preparing cover state: {type(e).__name__} - {e}")

                # Send modbus sensor states
                for modbus_coordinator in boneio_manager.modbus.get_all_coordinators().values():
                    if not modbus_coordinator:
                        continue
                    # Send regular modbus entities
                    for entities in modbus_coordinator.get_all_entities():
                        for entity in entities.values():
                            try:
                                sensor_state = ModbusDeviceState(
                                    id=entity.id,
                                    name=entity.name,
                                    state=entity.state,
                                    entity_type=entity.entity_type,
                                    unit=entity.unit_of_measurement,
                                    timestamp=entity.last_timestamp,
                                    device_group=modbus_coordinator.name,
                                    coordinator_id=modbus_coordinator._id,
                                    step=getattr(entity, 'step', None),
                                )
                                update = ModbusDeviceEvent(entity_id=entity.id, state=sensor_state)
                                if not await send_state_update(update):
                                    return

                            except Exception as e:
                                _LOGGER.error(f"Error preparing modbus sensor state: {type(e).__name__} - {e}")
                    
                    # Send additional entities (derived entities)
                    for additional_entities in modbus_coordinator.get_all_additional_entities():
                        for entity in additional_entities.values():
                            try:
                                # Get value mapping for select/switch
                                value_mapping = getattr(entity, '_value_mapping', None)
                                # Get payload_on/off for switch
                                payload_on = getattr(entity, '_payload_on', None)
                                payload_off = getattr(entity, '_payload_off', None)
                                
                                sensor_state = ModbusDeviceState(
                                    id=entity.id,
                                    name=entity.name,
                                    state=entity.state,
                                    unit=None,  # Additional entities usually don't have units
                                    timestamp=entity.last_timestamp if hasattr(entity, 'last_timestamp') else None,
                                    device_group=modbus_coordinator.name,
                                    coordinator_id=modbus_coordinator._id,
                                    entity_type=entity.entity_type,
                                    x_mapping=value_mapping,
                                    payload_on=payload_on,
                                    payload_off=payload_off,
                                    step=getattr(entity, 'step', None),
                                )
                                update = ModbusDeviceEvent(entity_id=entity.id, state=sensor_state)
                                if not await send_state_update(update):
                                    return

                            except Exception as e:
                                _LOGGER.error(f"Error preparing modbus additional entity state: {type(e).__name__} - {e}")

                # Send INA219 sensor states
                for single_ina_device in boneio_manager.sensors.get_ina219_sensors():
                    for ina_sensor in single_ina_device.sensors.values():
                        try:
                            sensor_state = SensorState(
                                id=ina_sensor.id,
                                name=ina_sensor.name,
                                state=ina_sensor.state,
                                unit=ina_sensor.unit_of_measurement,
                                timestamp=ina_sensor.last_timestamp,
                            )
                            update = SensorEvent(entity_id=ina_sensor.id, state=sensor_state)
                            if not await send_state_update(update):
                                return

                        except Exception as e:
                            _LOGGER.error(f"Error preparing INA219 sensor state: {type(e).__name__} - {e}")

                # Send temperature sensor states
                for sensor in boneio_manager.sensors.get_all_temp_sensors():
                    try:
                        sensor_state = SensorState(
                            id=sensor.id,
                            name=sensor.name,
                            state=sensor.state,
                            unit=sensor.unit_of_measurement,
                            timestamp=sensor.last_timestamp,
                        )
                        update = SensorEvent(entity_id=sensor.id, state=sensor_state)
                        if not await send_state_update(update):
                            return

                    except Exception as e:
                        _LOGGER.error(f"Error preparing temperature sensor state: {type(e).__name__} - {e}")

            except WebSocketDisconnect:
                _LOGGER.info("WebSocket disconnected while sending initial states")
                return
            except Exception as e:
                _LOGGER.error(f"Error sending initial states: {type(e).__name__} - {e}")
                return

            if websocket.application_state == WebSocketState.CONNECTED:
                _LOGGER.debug("Initial states sent, setting up event listeners")
                add_listener_for_all_outputs(boneio_manager=boneio_manager)
                add_listener_for_all_groups(boneio_manager=boneio_manager)
                add_listener_for_all_covers(boneio_manager=boneio_manager)
                add_listener_for_all_inputs(boneio_manager=boneio_manager)
                add_listener_for_inputs_reloaded(boneio_manager=boneio_manager)
                sensor_listener_for_all_sensors(boneio_manager=boneio_manager)

                # Keep connection alive with timeout to allow graceful shutdown
                while True:
                    try:
                        # Use short timeout to allow quick shutdown (max 1s delay)
                        data = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                        if data == "ping":
                            await websocket.send_text("pong")
                    except asyncio.TimeoutError:
                        # Timeout is normal - just check if still connected
                        if websocket.application_state != WebSocketState.CONNECTED:
                            _LOGGER.debug("WebSocket no longer connected, exiting loop")
                            break
                        continue
    except asyncio.CancelledError:
        _LOGGER.info("WebSocket connection cancelled during setup")
        await websocket_manager.disconnect(websocket)
        raise
    except WebSocketDisconnect as err:
        _LOGGER.info("WebSocket connection exiting gracefully %s", err)
        await websocket_manager.disconnect(websocket)
    except KeyboardInterrupt:
        _LOGGER.info("WebSocket connection interrupted by user.")
    except Exception as e:
        _LOGGER.error(f"Unexpected error in WebSocket handler: {type(e).__name__} - {e}")
    finally:
        _LOGGER.debug("Cleaning up WebSocket connection")
        if not app.state.websocket_manager.active_connections:
            remove_listener_for_all_outputs(boneio_manager=boneio_manager)
            remove_listener_for_all_covers(boneio_manager=boneio_manager)
            remove_listener_for_all_inputs(boneio_manager=boneio_manager)
            remove_listener_for_inputs_reloaded(boneio_manager=boneio_manager)
            remove_listener_for_all_sensors(boneio_manager=boneio_manager)
        # if connection_active:
        #     try:
        #         await asyncio.wait_for(
        #             app.state.websocket_manager.disconnect(websocket),
        #             timeout=2.0
        #         )
        #     except (asyncio.TimeoutError, Exception) as e:
        #         _LOGGER.error(f"Error during WebSocket cleanup: {type(e).__name__} - {e}")

# Static files setup
APP_DIR = Path(__file__).parent
FRONTEND_DIR = APP_DIR / "frontend-dist"


if FRONTEND_DIR.exists() and (FRONTEND_DIR / "index.html").exists():
    _LOGGER.info(f"Frontend found at {FRONTEND_DIR}, mounting static files")
    app.mount("/assets", StaticFiles(directory=f"{FRONTEND_DIR}/assets"), name="assets")
    app.mount("/schema", StaticFiles(directory=f"{APP_DIR}/schema"), name="schema")
    # Route to serve React index.html (for client-side routing)
    @app.get("/{catchall:path}")
    async def serve_react_app(catchall: str):
        return FileResponse(f"{FRONTEND_DIR}/index.html")
else:
    _LOGGER.warning(
        f"Frontend not found at {FRONTEND_DIR}. "
        "Frontend will not be served. "
        "Please build frontend with 'npm run build' in the frontend directory, "
        "or ensure frontend-dist exists at the expected location."
    )
    # Still mount schema for API access
    if (APP_DIR / "schema").exists():
        app.mount("/schema", StaticFiles(directory=f"{APP_DIR}/schema"), name="schema")
