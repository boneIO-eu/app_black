from __future__ import annotations
import asyncio
from datetime import datetime
import socket
import time
from math import floor
from typing import Callable, List
from functools import partial

import psutil

from boneio.const import (
    CPU,
    DISK,
    GIGABYTE,
    INA219,
    IP,
    MAC,
    MASK,
    MEGABYTE,
    MEMORY,
    NETWORK,
    NONE,
    SWAP,
    UPTIME,
    HOST,
)

# Typing imports that create a circular dependency
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from boneio.manager import Manager

from boneio.helper.async_updater import AsyncUpdater
from boneio.helper.timeperiod import TimePeriod
from boneio.sensor import LM75Sensor, MCP9808Sensor, INA219 as INA219Class
from boneio.version import __version__

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


def get_network_info():
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

    return retrieve_from_psutil()


def get_cpu_info():
    """Fetch CPU info."""
    cpu = psutil.cpu_times_percent()
    return {
        "total": f"{int(100 - cpu.idle)}%",
        "user": f"{cpu.user}%",
        "system": f"{cpu.system}%",
    }


def get_disk_info():
    """Fetch disk info."""
    disk = psutil.disk_usage("/")
    return {
        "total": f"{floor(disk.total / GIGABYTE)}GB",
        "used": f"{floor(disk.used / GIGABYTE)}GB",
        "free": f"{floor(disk.free / GIGABYTE)}GB",
    }


def get_memory_info():
    """Fetch memory info."""
    vm = psutil.virtual_memory()
    return {
        "total": f"{floor(vm.total / MEGABYTE)}MB",
        "used": f"{floor(vm.used / MEGABYTE)}MB",
        "free": f"{floor(vm.available / MEGABYTE)}MB",
    }


def get_swap_info():
    """Fetch swap info."""
    swap = psutil.swap_memory()
    return {
        "total": f"{floor(swap.total / MEGABYTE)}MB",
        "used": f"{floor(swap.used / MEGABYTE)}MB",
        "free": f"{floor(swap.free / MEGABYTE)}MB",
    }


def get_uptime():
    """Fetch uptime info."""
    return display_time(time.clock_gettime(time.CLOCK_BOOTTIME))


class HostSensor(AsyncUpdater):
    """Host sensor."""

    def __init__(
        self,
        update_function: Callable,
        manager_callback: Callable,
        static_data: dict | None,
        id: str,
        type: str,
        **kwargs,
    ) -> None:
        self._update_function = update_function
        self._static_data = static_data
        self._state = {}
        self._type = type
        self._manager_callback = manager_callback
        self._loop = asyncio.get_event_loop()
        self.id = id
        super().__init__(**kwargs)

    async def async_update(self, time: datetime) -> None:
        self._state = self._update_function()
        self._loop.call_soon_threadsafe(partial(self._manager_callback, self._type))

    @property
    def state(self) -> dict:
        if self._static_data:
            return {**self._static_data, **self._state}
        return self._state


class HostData:
    """Helper class to store host data."""

    def __init__(
        self,
        output: dict,
        callback: Callable,
        temp_sensor: Callable[[LM75Sensor, MCP9808Sensor], None],
        ina219: INA219Class | None,
        manager: Manager,
        enabled_screens: List[str],
    ) -> None:
        """Initialize HostData."""
        self._hostname = socket.gethostname()
        self._temp_sensor = temp_sensor
        host_stats = {
            NETWORK: {"f": get_network_info, "update_interval": TimePeriod(seconds=60)},
            CPU: {"f": get_cpu_info, "update_interval": TimePeriod(seconds=5)},
            DISK: {"f": get_disk_info, "update_interval": TimePeriod(seconds=60)},
            MEMORY: {"f": get_memory_info, "update_interval": TimePeriod(seconds=10)},
            SWAP: {"f": get_swap_info, "update_interval": TimePeriod(seconds=60)},
            UPTIME: {
                "f": lambda: {
                    "uptime": {"data": get_uptime(), "fontSize": "small", "row": 2, "col": 3},
                    "MQTT": {"data": "CONN" if manager.mqtt_state else "DOWN", "fontSize": "small", "row": 3, "col": 60},
                    "T": {
                        "data": f"{self._temp_sensor.state} C",
                        "fontSize": "small",
                        "row": 3,
                        "col": 3
                    },
                }
                if self._temp_sensor
                else {"uptime": {"data": get_uptime(), "fontSize": "small", "row": 2, "col": 3}},
                "static": {
                    HOST: {"data": self._hostname, "fontSize": "small", "row": 0, "col": 3},
                    "ver": {"data": __version__, "fontSize": "small", "row": 1, "col": 3},
                },
                "update_interval": TimePeriod(seconds=30),
            },
        }
        if ina219 is not None:
            host_stats[INA219] = {
                "f": lambda: {
                    *{sensor.device_class: sensor.state for sensor in ina219.sensors}
                },
                "update_interval": TimePeriod(seconds=60)
            }
        self._data = {}
        for k, _v in host_stats.items():
            if k not in enabled_screens:
                continue
            self._data[k] = HostSensor(
                update_function=_v["f"],
                static_data=_v.get("static"),
                manager=manager,
                manager_callback=callback,
                id=f"{k}_hoststats",
                type=k,
                update_interval=_v["update_interval"],
            )
        self._output = output
        self._callback = callback
        self._loop = asyncio.get_running_loop()

    def get(self, type: str) -> dict:
        """Get saved stats."""
        if type in self._output:
            return self._get_output(type)
        return self._data[type].state

    def _get_output(self, type: str) -> dict:
        """Get stats for output."""
        out = {}
        for output in self._output[type].values():
            out[output.id] = output.state
        return out
