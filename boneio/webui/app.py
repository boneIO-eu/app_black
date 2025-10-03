"""BoneIO Web UI."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import (
    BackgroundTasks,
    Body,
    Depends,
    FastAPI,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from jose import jwt
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import Receive, Scope, Send
from starlette.websockets import WebSocketState

from boneio.const import COVER, NONE
from boneio.helper.config import ConfigHelper
from boneio.helper.events import GracefulExit
from boneio.helper.exceptions import ConfigurationException
from boneio.helper.yaml_util import (
    load_config_from_file,
    update_config_section,
)
from boneio.manager import Manager
from boneio.models import (
    CoverState,
    InputState,
    OutputState,
    SensorState,
    StateUpdate,
)
from boneio.models.logs import LogEntry, LogsResponse
from boneio.version import __version__

from .websocket_manager import JWT_ALGORITHM, WebSocketManager

_LOGGER = logging.getLogger(__name__)


class CoverAction(BaseModel):
    action: str


class CoverPosition(BaseModel):
    position: int


class CoverTilt(BaseModel):
    tilt: int


class BoneIOApp(FastAPI):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._loop = asyncio.get_event_loop()

    async def shutdown_handler(self):
        """Handle application shutdown."""
        _LOGGER.debug("Shutting down All WebSocket connections...")
        if hasattr(self.state, 'websocket_manager'):
            await asyncio.sleep(1)
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

        except jwt.JWTError:
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
    if output_id not in manager.outputs:
        raise HTTPException(status_code=404, detail="Output not found")
    status = await manager.toggle_output(output_id=output_id)
    if status:
        return {"status": status}
    else:
        return {"status": "error"}

@app.post("/api/covers/{cover_id}/action")
async def cover_action(cover_id: str, action_data: CoverAction, manager: Manager = Depends(get_manager)):
    """Control cover with specific action (open, close, stop)."""
    cover = manager.covers.get(cover_id)
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
    cover = manager.covers.get(cover_id)
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
    cover = manager.covers.get(cover_id)
    if not cover:
        raise HTTPException(status_code=404, detail="Cover not found")
    if cover.kind != "venetian":
        raise HTTPException(status_code=400, detail="Invalid cover type")
    tilt = tilt_data.tilt
    if tilt < 0 or tilt > 100:
        raise HTTPException(status_code=400, detail="Invalid tilt")
    
    await cover.set_tilt(tilt)
    
    return {"status": "success"}

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
    """Check if there is a newer version of BoneIO available from GitHub releases."""
    import requests
    from packaging import version

    from boneio.version import __version__ as current_version
    
    try:
        # GitHub repository information
        repo = "boneIO-eu/app_bbb"
        
        # Get releases from GitHub API
        api_url = f'https://api.github.com/repos/{repo}/releases'
        response = requests.get(api_url)
        
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
        
        # Function to filter out prereleases if needed
        def not_prerelease(release):
            return not release.get('prerelease', False)
        
        # Get the latest release (you can choose to include or exclude prereleases)
        include_prerelease = True  # Set to False if you want to exclude prereleases
        
        if include_prerelease:
            latest_release = releases[0]  # First release is the latest
        else:
            # Find the first non-prerelease
            latest_release = next(filter(not_prerelease, releases), None)
            if not latest_release:
                return {
                    "status": "error",
                    "message": "No stable releases found on GitHub",
                    "current_version": current_version
                }
        
        # Extract version from tag name (usually in format 'v1.2.3')
        latest_version_str = latest_release['tag_name']
        if latest_version_str.startswith('v'):
            latest_version_str = latest_version_str[1:]  # Remove 'v' prefix if present
        
        # Compare versions
        is_update_available = version.parse(latest_version_str) > version.parse(current_version)
        
        return {
            "status": "success",
            "current_version": current_version,
            "latest_version": latest_version_str,
            "update_available": is_update_available,
            "release_url": latest_release['html_url'],
            "published_at": latest_release['published_at'],
            "is_prerelease": latest_release.get('prerelease', False)
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error checking for updates: {str(e)}",
            "current_version": current_version
        }


@app.post("/api/update")
async def update_boneio(background_tasks: BackgroundTasks):
    """Update the BoneIO package and restart the service."""
    if not is_running_as_service():
        return {"status": "not available", "message": "Update is only available when running as a service"}

    async def update_and_restart():
        try:
            # Allow time for the response to be sent
            await asyncio.sleep(0.5)
            
            # Get the virtual environment path
            venv_path = os.path.expanduser("~/boneio/venv")
            pip_path = os.path.join(venv_path, "bin", "pip")
            
            # Check if the virtual environment exists
            if not os.path.exists(pip_path):
                _LOGGER.error(f"Virtual environment not found at {venv_path}")
                return
            
            # Run pip install --upgrade boneio
            _LOGGER.info("Starting BoneIO update process...")
            import subprocess
            result = subprocess.run(
                [pip_path, "install", "--upgrade", "boneio"],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                _LOGGER.error(f"Update failed: {result.stderr}")
                return
            
            _LOGGER.info(f"Update successful: {result.stdout}")
            
            # Terminate the process to trigger systemd restart
            _LOGGER.info("Restarting BoneIO service...")
            os._exit(0)
        except Exception as e:
            _LOGGER.error(f"Error during update process: {e}")
    
    background_tasks.add_task(update_and_restart)
    return {"status": "success", "message": "Update process started"}


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

@app.get("/api/config")
async def get_parsed_config():
    """Get parsed configuration data with !include resolved."""
    try:
        # Load config using BoneIOLoader which handles !include
        config_data = load_config_from_file(app.state.yaml_config_file)
        
        _LOGGER.info("Successfully loaded parsed configuration")
        return {"config": config_data}
        
    except Exception as e:
        _LOGGER.error(f"Error loading parsed configuration: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error loading configuration: {str(e)}")

@app.get("/api/files")
async def list_files(path: str = None):
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

@app.put("/api/config/{section}")
async def update_section_content(section: str, data: dict = Body(...)):
    """Update content of a configuration section."""
    
    try:
        result = update_config_section(app.state.yaml_config_file, section, data)
        if result["status"] == "error":
            raise HTTPException(status_code=500, detail=result["message"])
        return result
        
    except Exception as e:
        _LOGGER.error(f"Error saving section '{section}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error saving section: {str(e)}")

def on_exit(self) -> None:
    asyncio.create_task(app.state.websocket_manager.close_all())


async def input_state_changed(input_: InputState):
    """Callback when input state changes."""
    await app.state.websocket_manager.broadcast_state("input", input_)


async def output_state_changed(event: OutputState):
    """Callback when output state changes."""
    await app.state.websocket_manager.broadcast_state("output", event)


async def cover_state_changed(event: CoverState):
    """Callback when cover state changes."""
    await app.state.websocket_manager.broadcast_state("cover", event)


async def sensor_state_changed(event: SensorState):
    """Callback when output state changes."""
    await app.state.websocket_manager.broadcast_state("sensor", event)


async def modbus_device_state_changed(event: SensorState):
    """Callback when output state changes."""
    await app.state.websocket_manager.broadcast_state("modbus_device", event)


def init_app(
    manager: Manager,
    yaml_config_file: str,
    config_helper: ConfigHelper,
    auth_config: dict = {},
    jwt_secret: str = None,
    web_server = None,
) -> BoneIOApp:
    """Initialize the FastAPI application with manager."""
    global _auth_config, JWT_SECRET
    
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
    return app


def add_listener_for_all_outputs(boneio_manager: Manager):
    for output in boneio_manager.outputs.values():
        if output.output_type == COVER or output.output_type == NONE:
            continue
        boneio_manager.event_bus.add_event_listener(
            event_type="output",
            entity_id=output.id,
            listener_id="ws",
            target=output_state_changed,
        )


def remove_listener_for_all_outputs(boneio_manager: Manager):
    boneio_manager.event_bus.remove_event_listener(event_type="output", listener_id="ws")

def add_listener_for_all_covers(boneio_manager: Manager):
    for cover in boneio_manager.covers.values():
        boneio_manager.event_bus.add_event_listener(
            event_type="cover",
            entity_id=cover.id,
            listener_id="ws",
            target=cover_state_changed,
        )


def remove_listener_for_all_covers(boneio_manager: Manager):
    boneio_manager.event_bus.remove_event_listener(
        event_type="cover"
    )

def add_listener_for_all_inputs(boneio_manager: Manager):
    for input in boneio_manager.inputs:
        boneio_manager.event_bus.add_event_listener(
            event_type="input",
            entity_id=input.pin,
            listener_id="ws",
            target=input_state_changed,
        )


def remove_listener_for_all_inputs(boneio_manager: Manager):
    boneio_manager.event_bus.remove_event_listener("input")


def sensor_listener_for_all_sensors(boneio_manager: Manager):
    for modbus_coordinator in boneio_manager.modbus_coordinators.values():
        if not modbus_coordinator:
            continue
        for entities in modbus_coordinator.get_all_entities():
            for entity in entities.values():
                boneio_manager.event_bus.add_event_listener(
                    event_type="modbus_device",
                    entity_id=entity.id,
                    listener_id="ws",
                    target=modbus_device_state_changed,
                )
    for single_ina_device in boneio_manager.ina219_sensors:
        for ina in single_ina_device.sensors.values():
            boneio_manager.event_bus.add_event_listener(
                event_type="sensor",
                entity_id=ina.id,
                listener_id="ws",
                target=sensor_state_changed,
            )
    for sensor in boneio_manager.temp_sensors:
        boneio_manager.event_bus.add_event_listener(
            event_type="sensor",
            entity_id=sensor.id,
            listener_id="ws",
            target=sensor_state_changed,
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
        if await app.state.websocket_manager.connect(websocket):
            _LOGGER.info("New WebSocket connection established")

            async def send_state_update(update: StateUpdate) -> bool:
                """Send state update and return True if successful."""
                try:
                    if websocket.application_state == WebSocketState.CONNECTED:
                        await websocket.send_json(update.dict())
                        return True
                except Exception as e:
                    _LOGGER.error(f"Error sending state update: {type(e).__name__} - {e}")
                return False

            # Send initial states
            try:
                # Send inputs
                for input_ in boneio_manager.inputs:
                    try:
                        input_state = InputState(
                            name=input_.name,
                            state=input_.last_state,
                            type=input_.input_type,
                            pin=input_.pin,
                            timestamp=input_.last_press_timestamp,
                            boneio_input=input_.boneio_input
                        )
                        update = StateUpdate(type="input", data=input_state)
                        if not await send_state_update(update):
                            return

                    except Exception as e:
                        _LOGGER.error(f"Error preparing input state: {type(e).__name__} - {e}")

                # Send outputs
                for output in boneio_manager.outputs.values():
                    try:
                        output_state = OutputState(
                            id=output.id,
                            name=output.name,
                            state=output.state,
                            type=output.output_type,
                            pin=output.pin_id,
                            expander_id=output.expander_id,
                            timestamp=output.last_timestamp,
                        )
                        update = StateUpdate(type="output", data=output_state)
                        if not await send_state_update(update):
                            return

                    except Exception as e:
                        _LOGGER.error(f"Error preparing output state: {type(e).__name__} - {e}")

                # Send covers
                for cover in boneio_manager.covers.values():
                    try:
                        cover_state_kwargs = dict(
                            id=cover.id,
                            name=cover.name,
                            state=cover.state,
                            position=cover.position,
                            kind=cover.kind,
                            timestamp=cover.last_timestamp,
                            current_operation=cover.current_operation,
                        )
                        if getattr(cover, 'kind', None) == 'venetian':
                            cover_state_kwargs['tilt'] = getattr(cover, 'tilt', 0)
                        cover_state = CoverState(**cover_state_kwargs)
                        update = StateUpdate(type="cover", data=cover_state)
                        if not await send_state_update(update):
                            return

                    except Exception as e:
                        _LOGGER.error(f"Error preparing cover state: {type(e).__name__} - {e}")

                # Send modbus sensor states
                for modbus_coordinator in boneio_manager.modbus_coordinators.values():
                    if not modbus_coordinator:
                        continue
                    for entities in modbus_coordinator.get_all_entities():
                        for entity in entities.values():
                            try:
                                sensor_state = SensorState(
                                    id=entity.id,
                                    name=entity.name,
                                    state=entity.state,
                                    unit=entity.unit_of_measurement,
                                    timestamp=entity.last_timestamp,
                                )
                                update = StateUpdate(type="modbus_device", data=sensor_state)
                                if not await send_state_update(update):
                                    return

                            except Exception as e:
                                _LOGGER.error(f"Error preparing modbus sensor state: {type(e).__name__} - {e}")

                # Send INA219 sensor states
                for single_ina_device in boneio_manager.ina219_sensors:
                    for ina_sensor in single_ina_device.sensors.values():
                        try:
                            sensor_state = SensorState(
                                id=ina_sensor.id,
                                name=ina_sensor.name,
                                state=ina_sensor.state,
                                unit=ina_sensor.unit_of_measurement,
                                timestamp=ina_sensor.last_timestamp,
                            )
                            update = StateUpdate(type="sensor", data=sensor_state)
                            if not await send_state_update(update):
                                return

                        except Exception as e:
                            _LOGGER.error(f"Error preparing INA219 sensor state: {type(e).__name__} - {e}")

                # Send temperature sensor states
                for sensor in boneio_manager.temp_sensors:
                    try:
                        sensor_state = SensorState(
                            id=sensor.id,
                            name=sensor.name,
                            state=sensor.state,
                            unit=sensor.unit_of_measurement,
                            timestamp=sensor.last_timestamp,
                        )
                        update = StateUpdate(type="sensor", data=sensor_state)
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
                add_listener_for_all_covers(boneio_manager=boneio_manager)
                add_listener_for_all_inputs(boneio_manager=boneio_manager)
                sensor_listener_for_all_sensors(boneio_manager=boneio_manager)

                while True:
                    data = await websocket.receive_text()
                    if data == "ping":
                        await websocket.send_text("pong")
    except asyncio.CancelledError:
        _LOGGER.info("WebSocket connection cancelled during setup")
        await app.state.websocket_manager.disconnect(websocket)
        raise
    except WebSocketDisconnect as err:
        _LOGGER.info("WebSocket connection exiting gracefully %s", err)
        await app.state.websocket_manager.disconnect(websocket)
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


if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=f"{FRONTEND_DIR}/assets"), name="assets")
    app.mount("/schema", StaticFiles(directory=f"{APP_DIR}/schema"), name="schema")
    # Route to serve React index.html (for client-side routing)
    @app.get("/{catchall:path}")
    async def serve_react_app(catchall: str):
        return FileResponse(f"{FRONTEND_DIR}/index.html")
