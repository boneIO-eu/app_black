import asyncio
import socket
import time
from functools import partial
from math import floor
from typing import Callable

import psutil

from boneio.const import (
    CPU,
    DISK,
    GIGABYTE,
    HOST,
    MEGABYTE,
    MEMORY,
    NETWORK,
    SWAP,
    UPTIME,
    IP,
    MASK,
    MAC,
    NONE,
)
from boneio.sensor import LM75Sensor

intervals = (("d", 86400), ("h", 3600), ("m", 60))


def display_time(seconds):
    """Strf time."""
    result = []

    for name, count in intervals:
        value = seconds // count
        if value:
            seconds -= value * count
            if value == 1:
                name = name.rstrip("s")
            result.append(f"{int(value)}{name}")
    return "".join(result)


async def get_network_info(host_data):
    """Fetch network info."""

    def retrieve_from_psutil():
        addrs = psutil.net_if_addrs()["eth0"]
        out = {IP: NONE, MASK: NONE, MAC: NONE}
        for addr in addrs:
            if addr.family == socket.AF_INET:
                out["ip"] = addr.address
                out["mask"] = addr.netmask
            elif addr.family == psutil.AF_LINK:
                out["mac"] = addr.address
        return out

    while True:
        data = retrieve_from_psutil()
        host_data.write(NETWORK, data)
        await asyncio.sleep(60)


async def get_cpu_info(host_data):
    """Fetch CPU info."""
    while True:
        cpu = psutil.cpu_times_percent()
        host_data.write(
            CPU,
            {
                "total": f"{int(100 - cpu.idle)}%",
                "user": f"{cpu.user}%",
                "system": f"{cpu.system}%",
            },
        )
        await asyncio.sleep(5)


async def get_disk_info(host_data):
    """Fetch disk info."""
    while True:
        disk = psutil.disk_usage("/")
        host_data.write(
            DISK,
            {
                "total": f"{floor(disk.total / GIGABYTE)}GB",
                "used": f"{floor(disk.used / GIGABYTE)}GB",
                "free": f"{floor(disk.free / GIGABYTE)}GB",
            },
        )
        await asyncio.sleep(60)


async def get_memory_info(host_data):
    """Fetch memory info."""
    while True:
        vm = psutil.virtual_memory()
        host_data.write(
            MEMORY,
            {
                "total": f"{floor(vm.total / MEGABYTE)}MB",
                "used": f"{floor(vm.used / MEGABYTE)}MB",
                "free": f"{floor(vm.available / MEGABYTE)}MB",
            },
        )
        await asyncio.sleep(10)


async def get_swap_info(host_data):
    """Fetch swap info."""
    while True:
        swap = psutil.swap_memory()
        host_data.write(
            SWAP,
            {
                "total": f"{floor(swap.total / MEGABYTE)}MB",
                "used": f"{floor(swap.used / MEGABYTE)}MB",
                "free": f"{floor(swap.free / MEGABYTE)}MB",
            },
        )
        await asyncio.sleep(10)


async def get_uptime(host_data):
    """Fetch uptime info."""
    while True:
        uptime = display_time(time.clock_gettime(time.CLOCK_BOOTTIME))
        host_data.write_uptime(uptime)
        await asyncio.sleep(30)


host_stats = {
    NETWORK: get_network_info,
    CPU: get_cpu_info,
    DISK: get_disk_info,
    MEMORY: get_memory_info,
    SWAP: get_swap_info,
    UPTIME: get_uptime,
}


class HostData:
    """Helper class to store host data."""

    data = {UPTIME: {}, NETWORK: {}, CPU: {}, DISK: {}, MEMORY: {}, SWAP: {}}

    def __init__(self, output: dict, callback: Callable, lm75: LM75Sensor) -> None:
        """Initialize HostData."""
        self._hostname = socket.gethostname()
        self.data[UPTIME] = {HOST: self._hostname, UPTIME: 0}
        self._lm75 = lm75
        self._output = output
        self._callback = callback
        self._loop = asyncio.get_running_loop()

    def write(self, type: str, data: dict) -> None:
        """Write data of chosen type."""
        self.data[type] = data
        self._loop.call_soon_threadsafe(partial(self._callback, type))

    def write_uptime(self, uptime: str) -> None:
        """Write uptime."""
        self.data[UPTIME][UPTIME] = uptime
        if self._lm75:
            self.data[UPTIME][self._lm75.name] = self._lm75.state
        self._loop.call_soon_threadsafe(partial(self._callback, UPTIME))

    def get(self, type: str) -> dict:
        """Get saved stats."""
        if type in self._output:
            return self._get_output(type)
        return self.data[type]

    def _get_output(self, type: str) -> dict:
        """Get stats for output."""
        out = {}
        for output in self._output[type].values():
            out[output.id] = output.state
        return out
