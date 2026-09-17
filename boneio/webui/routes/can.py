"""CAN bus tools routes for BoneIO Web UI.

Provides endpoints for:
- Bringing CAN interface up/down (through the privileged helper)
- Running candump (streaming via SSE)
- Sending CAN frames via cansend
"""

from __future__ import annotations

import asyncio
import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from boneio.core.manager import Manager


from boneio.core import system_ops

_LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/can", tags=["can"])


def get_manager():
    """Get manager instance - will be overridden by app initialization."""
    raise NotImplementedError("Manager not initialized")


# Default CAN settings matching boneIO Black hardware
DEFAULT_INTERFACE = "can0"
DEFAULT_BITRATE = 125000


class InterfaceUpRequest(BaseModel):
    """Request body for bringing CAN interface up.

    Args:
        interface: CAN interface name (default: can0)
        bitrate: CAN bus bitrate in bps (default: 125000)
    """

    interface: str = DEFAULT_INTERFACE
    bitrate: int = DEFAULT_BITRATE


class CanSendRequest(BaseModel):
    """Request body for sending a CAN frame.

    Args:
        interface: CAN interface name
        frame: CAN frame in cansend format, e.g. "701#05" (COB-ID#data)
    """

    interface: str = DEFAULT_INTERFACE
    frame: str


class NodeAssignRequest(BaseModel):
    target_node_id: int
    new_node_id: int


class NodeConfigRequest(BaseModel):
    config_yaml: str


# _run_sudo_command() and _check_sudo_error() are gone. They piped the
# operator's system password to `sudo -S` and translated its authentication
# failures. Interface setup goes through boneio-system now, which takes a verb
# and validated arguments and needs no password at all.
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


@router.get("/interfaces")
async def list_can_interfaces():
    """List available CAN interfaces detected in /sys/class/net/.

    Returns:
        Dict with list of CAN interface names (can0, can1, etc.).
    """
    import os

    interfaces = []
    net_dir = "/sys/class/net"
    try:
        for name in sorted(os.listdir(net_dir)):
            if not re.match(r"^(v?can\d+)$", name):
                continue
            uevent_path = os.path.join(net_dir, name, "uevent")
            try:
                with open(uevent_path) as f:
                    content = f.read()
                if "DEVTYPE=can" in content or name.startswith("can"):
                    interfaces.append(name)
            except (FileNotFoundError, PermissionError):
                interfaces.append(name)
    except FileNotFoundError:
        _LOGGER.warning("/sys/class/net not found")

    return {"interfaces": interfaces}


@router.get("/nodes")
async def get_can_nodes(manager: Manager = Depends(get_manager)):
    """Get discovered CANopen nodes.

    Includes Unconfigured nodes (ID=127) and Active Slaves (ID=2-126).
    """
    canopen = manager.canopen
    if not canopen or not canopen.is_enabled:
        raise HTTPException(status_code=400, detail="CANopen is disabled")

    return {"nodes": [node.to_dict() for node in canopen.nodes.values()]}


@router.post("/nodes/assign")
async def assign_node_id(body: NodeAssignRequest, manager: Manager = Depends(get_manager)):
    """Assign a new Node ID to an Unconfigured Node (ID 127)."""
    canopen = manager.canopen
    if not canopen or not canopen.is_enabled:
        raise HTTPException(status_code=400, detail="CANopen is disabled")

    success = await canopen.assign_node_id(body.target_node_id, body.new_node_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send SDO to Node")

    return {
        "status": "success",
        "message": f"Assigned Node ID {body.new_node_id} to Node {body.target_node_id}",
    }


@router.post("/nodes/{node_id}/config")
async def send_node_config(node_id: int, body: NodeConfigRequest, manager: Manager = Depends(get_manager)):
    """Push YAML config over CAN bus to Slave using SDO."""
    canopen = manager.canopen
    if not canopen or not canopen.is_enabled:
        raise HTTPException(status_code=400, detail="CANopen is disabled")

    success = await canopen.send_config(node_id, body.config_yaml)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send Config to Node")

    return {"status": "success", "message": f"Sent configuration to Node {node_id}"}


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
            "ip",
            "-d",
            "link",
            "show",
            interface,
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
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/interface-up")
async def bring_interface_up(body: InterfaceUpRequest):
    """Bring a CAN interface up at the requested bitrate.

    This used to take the operator's sudo password and run three
    ``sudo ip link set <iface> ...`` commands. The password is the same on every
    controller that shipped, and the sudoers rule behind it was
    ``ip link set can0 *`` — so both are gone: boneio-system takes an interface
    from a list of two and a bitrate from a list of nine, and does the three
    steps itself.

    Args:
        body: InterfaceUpRequest with interface and bitrate.

    Returns:
        Status response dict.
    """
    _validate_interface(body.interface)

    result = await asyncio.get_event_loop().run_in_executor(
        None, system_ops.can_up, body.interface, body.bitrate
    )
    if not result.ok:
        return {
            "status": "error",
            "message": result.stderr.strip() or "could not bring the interface up",
        }
    return {
        "status": "success",
        "message": f"{body.interface} is up at {body.bitrate} bps",
    }

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

        return {
            "status": "success",
            "message": f"Sent {body.frame} on {body.interface}",
        }

    except FileNotFoundError:
        return {
            "status": "error",
            "message": "cansend not found. Install can-utils package.",
        }
    except TimeoutError:
        return {"status": "error", "message": "cansend timed out"}
    except Exception as e:
        _LOGGER.error("cansend error: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


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
            yield "data: {'error': 'candump not found. Install can-utils package.'}\n\n"
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
                except TimeoutError:
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
