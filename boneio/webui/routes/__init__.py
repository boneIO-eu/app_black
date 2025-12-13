"""BoneIO Web UI Routes."""

from .auth import router as auth_router
from .outputs import router as outputs_router
from .covers import router as covers_router
from .system import router as system_router
from .config import router as config_router
from .update import router as update_router
from .modbus import router as modbus_router
from .sensors import router as sensors_router

__all__ = [
    "auth_router",
    "outputs_router",
    "covers_router",
    "system_router",
    "config_router",
    "update_router",
    "modbus_router",
    "sensors_router",
]
