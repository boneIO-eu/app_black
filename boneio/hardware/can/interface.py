"""CAN interface management for boneIO.

Provides functions to setup, restart, and check CAN network interfaces.
Uses 'sudo ip link' commands - requires sudoers NOPASSWD configuration:

    boneio ALL=(ALL) NOPASSWD: /sbin/ip link set can0 *
    boneio ALL=(ALL) NOPASSWD: /sbin/ip link set can1 *
"""

from __future__ import annotations

import asyncio
import logging
import os

_LOGGER = logging.getLogger(__name__)

# Path to ip command
IP_CMD = "/sbin/ip"


async def _run_sudo_ip(*args: str) -> tuple[bool, str]:
    """Run 'sudo ip' command with given arguments.

    Args:
        *args: Arguments to pass to 'ip' command.

    Returns:
        Tuple of (success, output/error message).
    """
    cmd = ["sudo", IP_CMD, *args]
    _LOGGER.debug("Running: %s", " ".join(cmd))
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
        if proc.returncode == 0:
            return True, stdout.decode().strip()
        error_msg = stderr.decode().strip()
        _LOGGER.error("Command failed (rc=%d): %s -> %s", proc.returncode, " ".join(cmd), error_msg)
        return False, error_msg
    except TimeoutError:
        _LOGGER.error("Command timed out: %s", " ".join(cmd))
        return False, "timeout"
    except FileNotFoundError:
        _LOGGER.error("sudo or ip command not found")
        return False, "command not found"
    except Exception as e:
        _LOGGER.error("Unexpected error running command: %s", e)
        return False, str(e)


async def is_interface_up(channel: str) -> bool:
    """Check if CAN interface exists and is UP.

    Args:
        channel: CAN interface name (e.g., 'can0').

    Returns:
        True if interface is up.
    """
    try:
        with open(f"/sys/class/net/{channel}/operstate") as f:
            state = f.read().strip()
        return state == "up"
    except FileNotFoundError:
        return False
    except Exception as e:
        _LOGGER.warning("Cannot check interface %s state: %s", channel, e)
        return False


def interface_exists(channel: str) -> bool:
    """Check if CAN interface exists in the system.

    Args:
        channel: CAN interface name (e.g., 'can0').

    Returns:
        True if interface exists.
    """
    return os.path.exists(f"/sys/class/net/{channel}")


async def setup_can_interface(channel: str, bitrate: int) -> bool:
    """Setup CAN interface with given bitrate.

    Brings the interface down (if up), sets bitrate, and brings it up.
    Requires sudoers NOPASSWD for boneio user.

    Args:
        channel: CAN interface name (e.g., 'can0').
        bitrate: CAN bus bitrate in bps (e.g., 125000).

    Returns:
        True if interface was successfully configured and brought up.
    """
    if not interface_exists(channel):
        _LOGGER.error("CAN interface %s does not exist", channel)
        return False

    # Bring down first (ignore errors - might already be down)
    if await is_interface_up(channel):
        _LOGGER.info("Bringing down CAN interface %s", channel)
        await _run_sudo_ip("link", "set", channel, "down")

    # Set bitrate
    _LOGGER.info("Setting CAN interface %s bitrate to %d", channel, bitrate)
    ok, err = await _run_sudo_ip(
        "link", "set", channel, "type", "can", "bitrate", str(bitrate),
    )
    if not ok:
        _LOGGER.error("Failed to set bitrate on %s: %s", channel, err)
        return False

    # Bring up
    _LOGGER.info("Bringing up CAN interface %s", channel)
    ok, err = await _run_sudo_ip("link", "set", channel, "up")
    if not ok:
        _LOGGER.error("Failed to bring up %s: %s", channel, err)
        return False

    _LOGGER.info("CAN interface %s is up with bitrate %d", channel, bitrate)
    return True


async def restart_can_interface(channel: str, bitrate: int) -> bool:
    """Restart CAN interface (down + set bitrate + up).

    Useful for recovering from bus-off state.

    Args:
        channel: CAN interface name (e.g., 'can0').
        bitrate: CAN bus bitrate in bps.

    Returns:
        True if interface was successfully restarted.
    """
    _LOGGER.warning("Restarting CAN interface %s", channel)
    return await setup_can_interface(channel, bitrate)


async def get_can_statistics(channel: str) -> dict[str, int] | None:
    """Read CAN interface error statistics from sysfs.

    Args:
        channel: CAN interface name (e.g., 'can0').

    Returns:
        Dictionary with bus error counters, or None if unavailable.
    """
    stats_path = f"/sys/class/net/{channel}/statistics"
    if not os.path.isdir(stats_path):
        return None

    stats = {}
    for counter in ("rx_errors", "tx_errors", "rx_dropped", "tx_dropped"):
        try:
            with open(os.path.join(stats_path, counter)) as f:
                stats[counter] = int(f.read().strip())
        except (FileNotFoundError, ValueError):
            stats[counter] = 0
    return stats


async def get_can_state(channel: str) -> str:
    """Get CAN interface state (e.g., ERROR-ACTIVE, ERROR-PASSIVE, BUS-OFF).

    Args:
        channel: CAN interface name (e.g., 'can0').

    Returns:
        CAN state string, or 'UNKNOWN' if unavailable.
    """
    # Try reading from /sys/class/net/<iface>/can_state (available on some kernels)
    try:
        with open(f"/sys/class/net/{channel}/can_state") as f:
            return f.read().strip()
    except FileNotFoundError:
        pass

    # Fallback: parse 'ip -details link show <channel>'
    try:
        proc = await asyncio.create_subprocess_exec(
            IP_CMD, "-details", "link", "show", channel,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        output = stdout.decode()
        # Look for "state ERROR-ACTIVE" or similar in output
        for line in output.splitlines():
            line = line.strip()
            if "state" in line.lower() and any(s in line.upper() for s in ("ERROR-ACTIVE", "ERROR-PASSIVE", "BUS-OFF")):
                for state in ("BUS-OFF", "ERROR-PASSIVE", "ERROR-ACTIVE"):
                    if state in line.upper():
                        return state
    except Exception:
        pass

    return "UNKNOWN"
