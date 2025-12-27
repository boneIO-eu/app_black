"""BoneIO Web UI - Main Application."""

from __future__ import annotations

import asyncio
import logging
import secrets
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import Depends, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.types import Receive, Scope, Send
from starlette.websockets import WebSocketState

from boneio.const import COVER, NONE
from boneio.core.config import ConfigHelper
from boneio.core.events import GracefulExit
from boneio.core.manager import Manager
from boneio.models import (
    CoverState,
    GroupState,
    InputState,
    OutputState,
    SensorState,
)
from boneio.models.events import (
    CoverEvent,
    Event,
    GroupEvent,
    InputEvent,
    ModbusDeviceEvent,
    OutputEvent,
    SensorEvent,
)
from boneio.models.state import ModbusDeviceState
from boneio.version import __version__

# Import routes
from boneio.webui.routes import (
    auth_router,
    caddy_router,
    config_router,
    covers_router,
    modbus_router,
    outputs_router,
    remote_devices_router,
    sensors_router,
    system_router,
    update_router,
)
from boneio.webui.routes import config as config_module
from boneio.webui.routes import system as system_module
from boneio.webui.middleware.auth import AuthMiddleware, set_auth_config

# Import WebSocket manager
from boneio.webui.websocket_manager import WebSocketManager

# Import FastAPI
from fastapi import FastAPI

if TYPE_CHECKING:
    from boneio.webui.web_server import WebServer

_LOGGER = logging.getLogger(__name__)


class BoneIOApp(FastAPI):
    """Custom FastAPI application with lifecycle management."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._loop = asyncio.get_event_loop()

    async def shutdown_handler(self):
        """Handle application shutdown."""
        _LOGGER.debug("Shutting down All WebSocket connections...")
        if hasattr(self.state, 'websocket_manager'):
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
                            await send({"type": "lifespan.startup.failed", "message": str(e)})
                    elif message["type"] == "lifespan.shutdown":
                        try:
                            _LOGGER.debug("Starting lifespan shutdown...")
                            await self.shutdown_handler()
                            _LOGGER.debug("WebSocket connections closed, sending shutdown complete...")
                            await send({"type": "lifespan.shutdown.complete"})
                            _LOGGER.debug("Lifespan shutdown complete sent.")
                        except Exception as e:
                            _LOGGER.error("Error during lifespan shutdown: %s", e)
                            await send({"type": "lifespan.shutdown.failed", "message": str(e)})
                        return
            except (asyncio.CancelledError, GracefulExit):
                _LOGGER.debug("GracefulExit during lifespan, cleaning up...")
                await self.shutdown_handler()
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


# Dependency to get manager instance
def get_manager():
    """Get manager instance."""
    return app.state.manager


def get_config_helper():
    """Get config helper instance."""
    return app.state.config_helper


# Include routers
app.include_router(auth_router)
app.include_router(outputs_router)
app.include_router(covers_router)
app.include_router(system_router)
app.include_router(config_router)
app.include_router(update_router)
app.include_router(modbus_router)
app.include_router(sensors_router)
app.include_router(caddy_router)
app.include_router(remote_devices_router)


# Override get_manager dependency in routers using FastAPI dependency_overrides
from boneio.webui.routes import outputs as outputs_module
from boneio.webui.routes import covers as covers_module
from boneio.webui.routes import modbus as modbus_module
from boneio.webui.routes import sensors as sensors_module
from boneio.webui.routes import remote_devices as remote_devices_module

# Use dependency_overrides to replace the placeholder get_manager functions
app.dependency_overrides[outputs_module.get_manager] = get_manager
app.dependency_overrides[covers_module.get_manager] = get_manager
app.dependency_overrides[modbus_module.get_manager] = get_manager
app.dependency_overrides[sensors_module.get_manager] = get_manager
app.dependency_overrides[remote_devices_module.get_manager] = get_manager
system_module.set_config_helper_getter(get_config_helper)


# ============================================================================
# WebSocket State Callback and Listeners
# ============================================================================

async def boneio_state_changed_callback(event: Event):
    """Callback when BoneIO state changes."""
    websocket_manager: WebSocketManager = app.state.websocket_manager
    await websocket_manager.broadcast_state(event)


def add_all_websocket_listeners(boneio_manager: Manager):
    """Add global WebSocket listeners for all entity types.
    
    Uses global listeners (entity_id="") to receive events from all entities,
    including dynamically added ones after reload. This is the preferred approach
    as it doesn't require re-registering listeners when entities are added/removed.
    """
    # Output events (relays, switches, lights, etc.)
    boneio_manager.event_bus.add_event_listener(
        event_type="output",
        entity_id="",
        listener_id="ws_output_global",
        target=boneio_state_changed_callback,
    )
    
    # Output group events
    boneio_manager.event_bus.add_event_listener(
        event_type="group",
        entity_id="",
        listener_id="ws_group_global",
        target=boneio_state_changed_callback,
    )
    
    # Cover events
    boneio_manager.event_bus.add_event_listener(
        event_type="cover",
        entity_id="",
        listener_id="ws_cover_global",
        target=boneio_state_changed_callback,
    )
    
    # Input events (buttons, binary sensors)
    boneio_manager.event_bus.add_event_listener(
        event_type="input",
        entity_id="",
        listener_id="ws_input_global",
        target=boneio_state_changed_callback,
    )
    
    # Modbus device events
    boneio_manager.event_bus.add_event_listener(
        event_type="modbus_device",
        entity_id="",
        listener_id="ws_modbus_global",
        target=boneio_state_changed_callback,
    )
    
    # Sensor events (temperature, power, etc.)
    boneio_manager.event_bus.add_event_listener(
        event_type="sensor",
        entity_id="",
        listener_id="ws_sensor_global",
        target=boneio_state_changed_callback,
    )


def remove_all_websocket_listeners(boneio_manager: Manager):
    """Remove all global WebSocket listeners."""
    boneio_manager.event_bus.remove_event_listener(event_type="output", listener_id="ws_output_global")
    boneio_manager.event_bus.remove_event_listener(event_type="group", listener_id="ws_group_global")
    boneio_manager.event_bus.remove_event_listener(event_type="cover", listener_id="ws_cover_global")
    boneio_manager.event_bus.remove_event_listener(event_type="input", listener_id="ws_input_global")
    boneio_manager.event_bus.remove_event_listener(event_type="modbus_device", listener_id="ws_modbus_global")
    boneio_manager.event_bus.remove_event_listener(event_type="sensor", listener_id="ws_sensor_global")


# ============================================================================
# WebSocket Endpoint
# ============================================================================

@app.websocket("/ws/state")
async def websocket_endpoint(
    websocket: WebSocket, boneio_manager: Manager = Depends(get_manager)
):
    """WebSocket endpoint for all state updates."""
    try:
        websocket_manager: WebSocketManager = app.state.websocket_manager
        if await websocket_manager.connect(websocket):
            _LOGGER.info("New WebSocket connection established")

            async def send_state_update(update: Event) -> bool:
                """Send state update and return True if successful."""
                try:
                    if websocket.application_state == WebSocketState.CONNECTED:
                        await websocket.send_json(update.model_dump())
                        return True
                except (BrokenPipeError, ConnectionResetError):
                    _LOGGER.debug("Client disconnected during state update")
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
                    
                    for additional_entities in modbus_coordinator.get_all_additional_entities():
                        for entity in additional_entities.values():
                            try:
                                value_mapping = getattr(entity, '_value_mapping', None)
                                payload_on = getattr(entity, '_payload_on', None)
                                payload_off = getattr(entity, '_payload_off', None)
                                
                                sensor_state = ModbusDeviceState(
                                    id=entity.id,
                                    name=entity.name,
                                    state=entity.state,
                                    unit=None,
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

                # Send virtual energy sensor states
                for ve_sensor in boneio_manager.sensors.get_virtual_energy_sensors():
                    try:
                        import time
                        # For power sensors: send current power and total energy
                        if ve_sensor.sensor_type == "power":
                            # Current power (W)
                            power_state = SensorState(
                                id=f"{ve_sensor.id}_power",
                                name=f"{ve_sensor.name} Power",
                                state=ve_sensor.get_current_power(),
                                unit="W",
                                timestamp=int(time.time()),
                            )
                            update = SensorEvent(entity_id=f"{ve_sensor.id}_power", state=power_state)
                            if not await send_state_update(update):
                                return
                            # Total energy (Wh)
                            energy_state = SensorState(
                                id=f"{ve_sensor.id}_energy",
                                name=f"{ve_sensor.name} Energy",
                                state=ve_sensor.get_total_energy(),
                                unit="Wh",
                                timestamp=int(time.time()),
                            )
                            update = SensorEvent(entity_id=f"{ve_sensor.id}_energy", state=energy_state)
                            if not await send_state_update(update):
                                return
                        # For water sensors: send current flow rate and total water
                        elif ve_sensor.sensor_type == "water":
                            # Current flow rate (L/h)
                            flow_state = SensorState(
                                id=f"{ve_sensor.id}_flow",
                                name=f"{ve_sensor.name} Flow Rate",
                                state=ve_sensor.get_current_flow_rate(),
                                unit="L/h",
                                timestamp=int(time.time()),
                            )
                            update = SensorEvent(entity_id=f"{ve_sensor.id}_flow", state=flow_state)
                            if not await send_state_update(update):
                                return
                            # Total water (L)
                            water_state = SensorState(
                                id=f"{ve_sensor.id}_water",
                                name=f"{ve_sensor.name} Water",
                                state=ve_sensor.get_total_water(),
                                unit="L",
                                timestamp=int(time.time()),
                            )
                            update = SensorEvent(entity_id=f"{ve_sensor.id}_water", state=water_state)
                            if not await send_state_update(update):
                                return
                    except Exception as e:
                        _LOGGER.error(f"Error preparing virtual energy sensor state: {type(e).__name__} - {e}")

            except WebSocketDisconnect:
                _LOGGER.info("WebSocket disconnected while sending initial states")
                return
            except Exception as e:
                _LOGGER.error(f"Error sending initial states: {type(e).__name__} - {e}")
                return

            if websocket.application_state == WebSocketState.CONNECTED:
                _LOGGER.debug("Initial states sent, setting up event listeners")
                add_all_websocket_listeners(boneio_manager=boneio_manager)

                # Keep connection alive
                while True:
                    try:
                        data = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                        if data == "ping":
                            await websocket.send_text("pong")
                    except asyncio.TimeoutError:
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
            remove_all_websocket_listeners(boneio_manager=boneio_manager)


# ============================================================================
# Application Initialization
# ============================================================================

def init_app(
    manager: Manager,
    yaml_config_file: str,
    config_helper: ConfigHelper,
    auth_config: dict = {},
    jwt_secret: str | None = None,
    web_server: WebServer | None = None,
    initial_config: dict | None = None,
) -> BoneIOApp:
    """
    Initialize the FastAPI application with manager.
    
    Args:
        manager: BoneIO manager instance.
        yaml_config_file: Path to YAML config file.
        config_helper: ConfigHelper instance.
        auth_config: Authentication configuration.
        jwt_secret: JWT secret for token signing.
        web_server: WebServer instance.
        initial_config: Pre-parsed config to populate cache.
        
    Returns:
        Configured BoneIOApp instance.
    """
    # Set JWT secret
    if not jwt_secret:
        jwt_secret = secrets.token_hex(32)
    
    # Set app state
    app.state.manager = manager
    app.state.auth_config = auth_config
    app.state.yaml_config_file = yaml_config_file
    app.state.web_server = web_server
    app.state.config_helper = config_helper
    app.state.websocket_manager = WebSocketManager(
        jwt_secret=jwt_secret,
        auth_required=bool(auth_config)
    )

    # Configure route modules with app state
    config_module.set_app_state(app.state)
    config_module.set_websocket_manager(app.state.websocket_manager)
    system_module.set_app_state(app.state)

    # Pre-populate config cache if initial_config provided
    if initial_config is not None:
        import os
        from boneio.webui.routes.config import _config_cache, _get_config_mtime
        _config_cache["data"] = initial_config
        _config_cache["mtime"] = _get_config_mtime(yaml_config_file)
        _LOGGER.info("Config cache pre-populated from initial_config")

    # Add auth middleware if configured
    if auth_config:
        username = auth_config.get("username")
        password = auth_config.get("password")
        if not username or not password:
            _LOGGER.error("Missing username or password in config!")
        else:
            set_auth_config(auth_config)
            app.add_middleware(AuthMiddleware)

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Add GZip compression
    app.add_middleware(GZipMiddleware, minimum_size=500)
    
    return app


# ============================================================================
# Static Files Setup
# ============================================================================

APP_DIR = Path(__file__).parent
FRONTEND_DIR = APP_DIR / "frontend-dist"

if FRONTEND_DIR.exists() and (FRONTEND_DIR / "index.html").exists():
    _LOGGER.info(f"Frontend found at {FRONTEND_DIR}, mounting static files")
    app.mount("/assets", StaticFiles(directory=f"{FRONTEND_DIR}/assets"), name="assets")
    app.mount("/schema", StaticFiles(directory=f"{APP_DIR}/schema"), name="schema")
    
    @app.get("/{catchall:path}")
    async def serve_react_app(catchall: str):
        """Serve React app for client-side routing."""
        return FileResponse(f"{FRONTEND_DIR}/index.html")
else:
    _LOGGER.warning(
        f"Frontend not found at {FRONTEND_DIR}. "
        "Frontend will not be served. "
        "Please build frontend with 'npm run build' in the frontend directory, "
        "or ensure frontend-dist exists at the expected location."
    )
    if (APP_DIR / "schema").exists():
        app.mount("/schema", StaticFiles(directory=f"{APP_DIR}/schema"), name="schema")
