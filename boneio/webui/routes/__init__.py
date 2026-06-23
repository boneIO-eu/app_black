"""Routes package for BoneIO Web UI."""

from boneio.webui.routes.auth import router as auth_router
from boneio.webui.routes.caddy import router as caddy_router
from boneio.webui.routes.can import router as can_router
from boneio.webui.routes.config import router as config_router
from boneio.webui.routes.covers import router as covers_router
from boneio.webui.routes.dashboard import router as dashboard_router
from boneio.webui.routes.irrigation import router as irrigation_router
from boneio.webui.routes.migrations import router as migrations_router
from boneio.webui.routes.modbus import router as modbus_router
from boneio.webui.routes.outputs import router as outputs_router
from boneio.webui.routes.remote_devices import router as remote_devices_router
from boneio.webui.routes.sensors import router as sensors_router
from boneio.webui.routes.system import router as system_router
from boneio.webui.routes.templates import router as templates_router
from boneio.webui.routes.tools import router as tools_router
from boneio.webui.routes.update import router as update_router

from boneio.webui.routes.dev_fake_device import router as dev_fake_device_router

__all__ = [
    "auth_router",
    "caddy_router",
    "can_router",
    "config_router",
    "covers_router",
    "dashboard_router",
    "dev_fake_device_router",
    "irrigation_router",
    "migrations_router",
    "modbus_router",
    "outputs_router",
    "remote_devices_router",
    "sensors_router",
    "system_router",
    "tools_router",
    "templates_router",
    "update_router",
]
