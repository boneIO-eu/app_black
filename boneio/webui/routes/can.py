"""CAN bus tools routes for BoneIO Web UI.

Provides endpoints for:
- Bringing CAN interface up/down (requires sudo)
- Running candump (streaming via SSE)
- Sending CAN frames via cansend
"""

from __future__ import annotations

import asyncio
import logging
import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

_LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/can", tags=["can"])

# Default CAN settings matching boneIO Black hardware
DEFAULT_INTERFACE = "can0"
DEFAULT_BITRATE = 125000


class InterfaceUpRequest(BaseModel):
    """Request body for bringing CAN interface up.

    Args:
        interface: CAN interface name (default: can0)
        bitrate: CAN bus bitrate in bps (default: 125000)
        password: Sudo password for ip link commands
    """

    interface: str = DEFAULT_INTERFACE
    bitrate: int = DEFAULT_BITRATE
    password: str


class CanSendRequest(BaseModel):
    """Request body for sending a CAN frame.

    Args:
        interface: CAN interface name
        frame: CAN frame in cansend format, e.g. "701#05" (COB-ID#data)
    """

    interface: str = DEFAULT_INTERFACE
    frame: str


async def _run_sudo_command(password: str, cmd: list[str], timeout: float = 10) -> dict:
    """Run a command with sudo, piping the password via stdin.

    Args:
        password: Sudo password
        cmd: Command and arguments (without 'sudo -S' prefix)
        timeout: Command timeout in seconds

    Returns:
        Dict with returncode, stdout, stderr
    """
    full_cmd = ["sudo", "-S"] + cmd
    _LOGGER.info("Running: %s", " ".join(full_cmd))

    try:
        proc = await asyncio.create_subprocess_exec(
            *full_cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=(password + "\n").encode()),
            timeout=timeout,
        )
        return {
            "returncode": proc.returncode,
            "stdout": stdout.decode().strip(),
            "stderr": stderr.decode().strip(),
        }
    except asyncio.TimeoutError:
        return {"returncode": -1, "stdout": "", "stderr": "Command timed out"}
    except Exception as e:
        return {"returncode": -1, "stdout": "", "stderr": str(e)}


def _check_sudo_error(result: dict) -> str | None:
    """Check if sudo command failed due to bad password.

    Args:
        result: Dict from _run_sudo_command

    Returns:
        Error message string or None if no auth error
    """
    stderr = result.get("stderr", "").lower()
    if "incorrect password" in stderr or "sorry" in stderr:
        return "Incorrect sudo password"
    return None


def _validate_interface(interface: str) -> None:
    """Validate CAN interface name to prevent injection.

    Args:
        interface: Interface name to validate

    Raises:
        HTTPException: If interface name is invalid
    """
    if not re.match(r"^(v?can\d+)$", interface):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid interface name: {interface}. Use can0, can1, vcan0, etc.",
        )


def _validate_frame(frame: str) -> None:
    """Validate CAN frame format for cansend.

    Expected format: COB-ID#DATA, e.g. "701#05", "200#0102030405060708"

    Args:
        frame: CAN frame string

    Raises:
        HTTPException: If frame format is invalid
    """
    if not re.match(r"^[0-9A-Fa-f]{1,8}#([0-9A-Fa-f]{0,16})?$", frame):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid CAN frame format: {frame}. Use COB-ID#DATA, e.g. '701#05'",
        )


@router.get("/status")
async def get_can_status(interface: str = DEFAULT_INTERFACE):
    """Check if CAN interface is up and get its status.

    Args:
        interface: CAN interface name

    Returns:
        Dict with interface name, is_up flag, and details
    """
    _validate_interface(interface)

    try:
        proc = await asyncio.create_subprocess_exec(
            "ip", "-d", "link", "show", interface,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            return {
                "interface": interface,
                "is_up": False,
                "exists": False,
                "details": stderr.decode().strip(),
            }

        output = stdout.decode()
        is_up = "UP" in output and "NOARP" not in output.split("UP")[0].split("<")[-1] if "UP" in output else False
        # Simpler check: look for state UP
        is_up = ",UP," in output or "<UP," in output or ",UP>" in output

        # Extract bitrate if present
        bitrate = None
        bitrate_match = re.search(r"bitrate\s+(\d+)", output)
        if bitrate_match:
            bitrate = int(bitrate_match.group(1))

        return {
            "interface": interface,
            "is_up": is_up,
            "exists": True,
            "bitrate": bitrate,
            "details": output.strip(),
        }

    except FileNotFoundError:
        return {
            "interface": interface,
            "is_up": False,
            "exists": False,
            "details": "'ip' command not found",
        }
    except Exception as e:
        _LOGGER.error("Error checking CAN status: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/interface-up")
async def bring_interface_up(body: InterfaceUpRequest):
    """Bring CAN interface up with specified bitrate using sudo.

    Runs: sudo ip link set can0 down (ignore error)
          sudo ip link set can0 type can bitrate 125000
          sudo ip link set can0 up

    Args:
        body: InterfaceUpRequest with interface, bitrate, and sudo password

    Returns:
        Status response dict
    """
    _validate_interface(body.interface)

    steps = [
        {
            "name": "link down",
            "cmd": ["ip", "link", "set", body.interface, "down"],
            "ignore_error": True,
        },
        {
            "name": "set bitrate",
            "cmd": [
                "ip", "link", "set", body.interface,
                "type", "can", "bitrate", str(body.bitrate),
            ],
            "ignore_error": False,
        },
        {
            "name": "link up",
            "cmd": ["ip", "link", "set", body.interface, "up"],
            "ignore_error": False,
        },
    ]

    results = []
    for step in steps:
        result = await _run_sudo_command(body.password, step["cmd"])

        # Check for password error on first command
        auth_err = _check_sudo_error(result)
        if auth_err:
            return {"status": "error", "message": auth_err}

        results.append({
            "step": step["name"],
            "returncode": result["returncode"],
            "stderr": result["stderr"],
        })

        if result["returncode"] != 0 and not step["ignore_error"]:
            _LOGGER.warning(
                "CAN interface-up failed at step '%s': %s",
                step["name"],
                result["stderr"],
            )
            return {
                "status": "error",
                "message": f"Failed at '{step['name']}': {result['stderr']}",
                "steps": results,
            }

    _LOGGER.info(
        "CAN interface %s brought up at %d bps",
        body.interface,
        body.bitrate,
    )
    return {"status": "success", "message": f"{body.interface} is up at {body.bitrate} bps", "steps": results}


@router.post("/send")
async def can_send(body: CanSendRequest):
    """Send a CAN frame using cansend.

    Args:
        body: CanSendRequest with interface and frame

    Returns:
        Status response dict
    """
    _validate_interface(body.interface)
    _validate_frame(body.frame)

    cmd = ["cansend", body.interface, body.frame]
    _LOGGER.info("cansend: %s", " ".join(cmd))

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5)

        if proc.returncode != 0:
            error_msg = stderr.decode().strip() or f"cansend exited with code {proc.returncode}"
            return {"status": "error", "message": error_msg}

        return {"status": "success", "message": f"Sent {body.frame} on {body.interface}"}

    except FileNotFoundError:
        return {"status": "error", "message": "cansend not found. Install can-utils package."}
    except asyncio.TimeoutError:
        return {"status": "error", "message": "cansend timed out"}
    except Exception as e:
        _LOGGER.error("cansend error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dump")
async def can_dump(interface: str = DEFAULT_INTERFACE, duration: int = 30):
    """Stream candump output as Server-Sent Events (SSE).

    Args:
        interface: CAN interface name
        duration: How long to capture in seconds (max 120)

    Returns:
        StreamingResponse with SSE events
    """
    _validate_interface(interface)
    duration = min(max(duration, 5), 120)

    async def event_stream():
        """Generate SSE events from candump output."""
        cmd = ["candump", interface]
        _LOGGER.info("Starting candump on %s for %ds", interface, duration)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            yield f"data: {{'error': 'candump not found. Install can-utils package.'}}\n\n"
            return
        except Exception as e:
            yield f"data: {{'error': '{e}'}}\n\n"
            return

        try:
            assert proc.stdout is not None
            end_time = asyncio.get_event_loop().time() + duration

            while asyncio.get_event_loop().time() < end_time:
                try:
                    line = await asyncio.wait_for(
                        proc.stdout.readline(),
                        timeout=1.0,
                    )
                    if not line:
                        break
                    decoded = line.decode().strip()
                    if decoded:
                        yield f"data: {decoded}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield ": keepalive\n\n"

            yield "data: [DONE]\n\n"

        finally:
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=3)
            except Exception:
                proc.kill()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
