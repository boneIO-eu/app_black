"""System monitoring utilities.

This module provides functions to retrieve system information such as:
- CPU usage
- Memory usage
- Disk usage
- Network information
- System uptime

These functions can be used by OLED display, Web UI, or any other component
that needs system statistics.
"""

from __future__ import annotations

import socket
import time
from math import floor

import psutil

from boneio.const import (
    GIGABYTE,
    IP,
    MAC,
    MASK,
    MEGABYTE,
    NONE,
)

# Time intervals for uptime display
_TIME_INTERVALS = (("d", 86400), ("h", 3600), ("m", 60))


def display_time(seconds: int | float) -> str:
    """Format seconds into human-readable time string.
    
    Args:
        seconds: Number of seconds to format
        
    Returns:
        Formatted string like "1d2h30m" or "5h15m"
        
    Example:
        >>> display_time(90061)
        '1d1h1m'
    """
    result = []
    seconds = int(seconds)

    for name, count in _TIME_INTERVALS:
        value = seconds // count
        if value:
            seconds -= value * count
            if value == 1:
                name = name.rstrip("s")
            result.append(f"{int(value)}{name}")
    
    return "".join(result) if result else "0m"


def get_network_info() -> dict[str, str]:
    """Fetch network information for eth0 interface.
    
    Returns:
        Dictionary with keys: 'ip', 'mask', 'mac'
        Returns 'none' for missing values
        
    Example:
        >>> get_network_info()
        {'ip': '192.168.1.100', 'mask': '255.255.255.0', 'mac': 'aa:bb:cc:dd:ee:ff'}
    """
    try:
        addrs = psutil.net_if_addrs().get("eth0", [])
        out = {IP: NONE, MASK: NONE, MAC: NONE}
        
        for addr in addrs:
            if addr.family == socket.AF_INET:
                out["ip"] = addr.address
                out["mask"] = addr.netmask if addr.netmask is not None else ""
            elif addr.family == psutil.AF_LINK:
                out["mac"] = addr.address
        
        return out
    except (KeyError, AttributeError):
        return {IP: NONE, MASK: NONE, MAC: NONE}


def get_cpu_info() -> dict[str, str]:
    """Fetch CPU usage information.
    
    Returns:
        Dictionary with keys: 'total', 'user', 'system'
        Values are formatted as percentages with '%' suffix
        
    Example:
        >>> get_cpu_info()
        {'total': '45%', 'user': '30.5%', 'system': '14.5%'}
    """
    cpu = psutil.cpu_times_percent()
    return {
        "total": f"{int(100 - cpu.idle)}%",
        "user": f"{cpu.user}%",
        "system": f"{cpu.system}%",
    }


def get_disk_info() -> dict[str, str]:
    """Fetch disk usage information for root partition.
    
    Returns:
        Dictionary with keys: 'total', 'used', 'free'
        Values are formatted in GB with 'GB' suffix
        
    Example:
        >>> get_disk_info()
        {'total': '32GB', 'used': '15GB', 'free': '17GB'}
    """
    disk = psutil.disk_usage("/")
    return {
        "total": f"{floor(disk.total / GIGABYTE)}GB",
        "used": f"{floor(disk.used / GIGABYTE)}GB",
        "free": f"{floor(disk.free / GIGABYTE)}GB",
    }


def get_memory_info() -> dict[str, str]:
    """Fetch RAM usage information.
    
    Returns:
        Dictionary with keys: 'total', 'used', 'free'
        Values are formatted in MB with 'MB' suffix
        
    Example:
        >>> get_memory_info()
        {'total': '512MB', 'used': '256MB', 'free': '256MB'}
    """
    vm = psutil.virtual_memory()
    return {
        "total": f"{floor(vm.total / MEGABYTE)}MB",
        "used": f"{floor(vm.used / MEGABYTE)}MB",
        "free": f"{floor(vm.available / MEGABYTE)}MB",
    }


def get_swap_info() -> dict[str, str]:
    """Fetch swap usage information.
    
    Returns:
        Dictionary with keys: 'total', 'used', 'free'
        Values are formatted in MB with 'MB' suffix
        
    Example:
        >>> get_swap_info()
        {'total': '1024MB', 'used': '0MB', 'free': '1024MB'}
    """
    swap = psutil.swap_memory()
    return {
        "total": f"{floor(swap.total / MEGABYTE)}MB",
        "used": f"{floor(swap.used / MEGABYTE)}MB",
        "free": f"{floor(swap.free / MEGABYTE)}MB",
    }


def get_uptime() -> str:
    """Fetch system uptime.
    
    Returns:
        Formatted uptime string like "1d2h30m"
        
    Example:
        >>> get_uptime()
        '2d5h15m'
    """
    return display_time(time.clock_gettime(time.CLOCK_BOOTTIME))
