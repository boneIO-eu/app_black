"""Runner code for boneIO. Based on HA runner."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import warnings
from typing import Any

from boneio.const import (
    ADC,
    BINARY_SENSOR,
    BONEIO,
    COVER,
    DALLAS,
    DS2482,
    ENABLED,
    EVENT_ENTITY,
    HA_DISCOVERY,
    HOST,
    INA219,
    LM75,
    MCP23017,
    VIRTUAL_ENERGY_SENSOR,
    MCP_TEMP_9808,
    MODBUS,
    MQTT,
    NAME,
    OLED,
    ONEWIRE,
    OUTPUT,
    OUTPUT_GROUP,
    PASSWORD,
    PCA9685,
    PCF8575,
    PORT,
    SENSOR,
    TOPIC_PREFIX,
    USERNAME,
)
from boneio.core.config import ConfigHelper
from boneio.core.events import EventBus, GracefulExit
from boneio.core.manager import Manager
from boneio.core.messaging import MQTTClient
from boneio.core.state import StateManager
from boneio.core.system import get_network_info
from boneio.exceptions import RestartRequestException

# Filter out cryptography deprecation warning
warnings.filterwarnings('ignore', category=DeprecationWarning, module='cryptography')

_LOGGER = logging.getLogger(__name__)

config_modules = [
    {"name": MCP23017, "default": []},
    {"name": PCF8575, "default": []},
    {"name": PCA9685, "default": []},
    {"name": DS2482, "default": []},
    {"name": ADC, "default": []},
    {"name": COVER, "default": []},
    {"name": MODBUS, "default": {}},
    {"name": OLED, "default": {}},
    {"name": DALLAS, "default": None},
    {"name": OUTPUT_GROUP, "default": []},
]


async def async_run(
    config: dict,
    config_file: str,
    mqttusername: str = "",
    mqttpassword: str = "",
    debug: int = 0
) -> int:
    """Run BoneIO."""
    web_server = None
    tasks: set[asyncio.Task] = set()
    loop = asyncio.get_running_loop()
    event_bus = EventBus(loop=loop)
    shutdown_event = asyncio.Event()
    if debug >= 2:
        loop.set_debug(True)
    network_state = get_network_info()

    def signal_handler():
        """Handle shutdown signals."""
        _LOGGER.info("Received shutdown signal, initiating graceful shutdown...")
        shutdown_event.set()

    # Register signal handlers
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)

    event_bus_task = asyncio.create_task(event_bus.start())
    tasks.add(event_bus_task)
    event_bus_task.add_done_callback(tasks.discard)

    main_config = config.get(BONEIO, {})

    if "web" in config:
        web_active = True
        web_config = config.get("web") or {}
    else:
        web_active = False
        web_config = {}

    mqtt_config = config.get(MQTT, {})
    _config_helper = ConfigHelper(
        name=main_config.get(NAME, BONEIO),
        device_type=main_config.get("device_type", "boneIO Black"),
        network_info=network_state,
        is_web_active=web_active,
        web_port=web_config.get("port", 8090),
        proxy_port=web_config.get("proxy_port"),
        ha_discovery=mqtt_config.get(HA_DISCOVERY, {}).get(ENABLED, False),
        ha_discovery_prefix=mqtt_config.get(HA_DISCOVERY, {}).get(TOPIC_PREFIX, "homeassistant"),
        config_file_path=config_file,
        send_boneio_autodiscovery=mqtt_config.get("send_boneio_autodiscovery", True),
        receive_boneio_autodiscovery=mqtt_config.get("receive_boneio_autodiscovery", True),
    )
    
    # Load areas configuration
    _config_helper.set_areas(areas_config=config.get("areas", []))

    # Initialize message bus based on config
    if MQTT in config:
        message_bus = MQTTClient(
            host=config[MQTT][HOST],
            username=config[MQTT].get(USERNAME, mqttusername),
            password=config[MQTT].get(PASSWORD, mqttpassword),
            port=config[MQTT].get(PORT, 1883),
            config_helper=_config_helper,
        )
    else:
        from boneio.core.messaging import LocalMessageBus
        message_bus = LocalMessageBus()

    manager_kwargs = {
        item["name"]: config.get(item["name"], item["default"])
        for item in config_modules
    }

    manager = Manager(
        message_bus=message_bus,
        event_bus=event_bus,
        relay_pins=config.get(OUTPUT, []),
        event_pins=config.get(EVENT_ENTITY, []),
        binary_pins=config.get(BINARY_SENSOR, []),
        remote_devices=config.get("remote_devices", []),
        config_file_path=config_file,
        state_manager=StateManager(
            state_file=f"{os.path.split(config_file)[0]}state.json"
        ),
        config_helper=_config_helper,
        sensors={
            LM75: config.get(LM75, []),
            INA219: config.get(INA219, []),
            MCP_TEMP_9808: config.get(MCP_TEMP_9808, []),
            ONEWIRE: config.get(SENSOR, []),
            VIRTUAL_ENERGY_SENSOR: config.get(VIRTUAL_ENERGY_SENSOR, []),
        },
        modbus_devices=config.get("modbus_devices", []),
        web_active=web_active,
        web_port=web_config.get("port", 8090),
        **manager_kwargs,
    )
    # Convert coroutines to Tasks
    message_bus.set_manager(manager=manager)
    # Add manager tasks (get_tasks returns dict, we need values)
    manager_tasks = manager.get_tasks()
    tasks.update(manager_tasks.values())
    
    # Start GPIO manager if inputs are configured
    from boneio.hardware.gpio.input import get_gpio_manager
    gpio_manager = get_gpio_manager()
    if gpio_manager and gpio_manager._inputs:  # Only start if there are inputs
        _LOGGER.info("Starting GPIO manager")
        try:
            await gpio_manager.start()
        except Exception as e:
            _LOGGER.error(f"Failed to start GPIO manager: {e}")
            _LOGGER.error("If lines are busy, run: sudo pkill -9 -f boneio")
            # Don't fail the entire application, continue without GPIO
            pass

    message_bus_type = "MQTT" if isinstance(message_bus, MQTTClient) else "Local"
    _LOGGER.info("Starting message bus %s.", message_bus_type)
    message_bus_task = asyncio.create_task(message_bus.start_client())
    tasks.add(message_bus_task)
    message_bus_task.add_done_callback(tasks.discard)
    
    # Publish discovery after message bus is started
    if isinstance(message_bus, MQTTClient):
        # Wait a bit for MQTT connection to establish
        await asyncio.sleep(2)
        _LOGGER.info("Publishing device discovery information")
        await manager.publish_discovery()
    
    # Start web server if configured
    if web_active:
        _LOGGER.info("Starting Web server.")
        # Lazy import WebServer only when needed (saves ~4s on startup)
        from boneio.webui.web_server import WebServer
        
        web_server = WebServer(
            config_file=config_file,
            config_helper=_config_helper,
            manager=manager,
            port=web_config.get("port", 8090),  
            auth=web_config.get("auth", {}),  
            logger=config.get("logger", {}),
            debug_level=debug,
            initial_config=config,  # Pre-populate cache for fast first request
        )
        web_server_task = asyncio.create_task(web_server.start_webserver())
        tasks.add(web_server_task)
        web_server_task.add_done_callback(tasks.discard)
    else:
        _LOGGER.info("Web server not configured.")
    
    try:
        # Convert tasks set to list for main gather
        task_list = list(tasks)
        main_gather = asyncio.gather(*task_list)
        
        # Wait for either shutdown signal or main task completion
        await asyncio.wait([
            main_gather,
            asyncio.create_task(shutdown_event.wait())
        ], return_when=asyncio.FIRST_COMPLETED)


        if shutdown_event.is_set():
            _LOGGER.info("Starting graceful shutdown...")
            await message_bus.announce_offline()
            
            # Cancel all manager tasks (including those added later by AsyncUpdater)
            all_manager_tasks = list(manager.get_tasks().values())
            _LOGGER.debug("Cancelling %d manager tasks...", len(all_manager_tasks))
            for task in all_manager_tasks:
                if not task.done():
                    task.cancel()
            
            # Wait for manager tasks to finish
            if all_manager_tasks:
                try:
                    await asyncio.gather(*all_manager_tasks, return_exceptions=True)
                except Exception as e:
                    _LOGGER.debug("Manager tasks cancelled: %s", e)
            
            main_gather.cancel()
            try:
                await main_gather
            except asyncio.CancelledError:
                pass

        return 0
    except asyncio.CancelledError:
        _LOGGER.info("Main task cancelled")
    except (RestartRequestException, GracefulExit):
        _LOGGER.info("Restart or graceful exit requested")
    except Exception as e:
        _LOGGER.error(f"Unexpected error: {type(e).__name__} - {e}")
    except BaseException as e:
        _LOGGER.error(f"Unexpected BaseException: {type(e).__name__} - {e}")
    finally:
        _LOGGER.info("Cleaning up resources...")

        # Trigger web server shutdown if it's running
        if web_server and hasattr(web_server, 'trigger_shutdown'):
            try:
                _LOGGER.info("Requesting web server shutdown...")
                await web_server.trigger_shutdown()
            except Exception as e:
                _LOGGER.error(f"Error triggering web server shutdown: {e}")

        # Stop GPIO manager
        try:
            gpio_manager = get_gpio_manager()
            if gpio_manager:
                _LOGGER.info("Stopping GPIO manager...")
                await gpio_manager.stop()
        except Exception as e:
            _LOGGER.error(f"Error stopping GPIO manager: {e}")
        
        # Stop the event bus (this invokes sigterm listeners which turn off Cover relays)
        await event_bus.stop()
        
        # Create a copy of tasks set to avoid modification during iteration
        remaining_tasks = list(tasks)
        if remaining_tasks:
            # Cancel and wait for all remaining tasks
            # Web server task will be cancelled here if it hasn't finished after trigger_shutdown
            for task in remaining_tasks:
                if not task.done():
                    _LOGGER.debug(f"Cancelling task: {task.get_name()}")
                    task.cancel()
            
            # Wait for all tasks to complete
            try:
                await asyncio.gather(*remaining_tasks, return_exceptions=True)
            except Exception as e:
                _LOGGER.error(f"Error during cleanup: {type(e).__name__} - {e}")
        
        _LOGGER.info("Shutdown complete")
        return 0
