"""Runner code for boneIO. Based on HA runner."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import warnings
from typing import Any

from boneio.const import (
    ADC,
    BINARY_SENSOR,
    BONEIO,
    CAN,
    COVER,
    DALLAS,
    ENABLED,
    EVENT_ENTITY,
    HA_DISCOVERY,
    HOST,
    INA219,
    INA226,
    IRRIGATION,
    LM75,
    MCP23017,
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
    TEMPLATE,
    TOPIC_PREFIX,
    USERNAME,
    VIRTUAL_ENERGY_SENSOR,
)
from boneio.core.config import ConfigHelper
from boneio.core.events import EventBus, GracefulExit
from boneio.core.manager import Manager
from boneio.core.messaging import MQTTClient
from boneio.core.recovery import STABLE_AFTER_SECONDS, StartupFailures
from boneio.core.state import StateManager
from boneio.core.system import get_network_info
from boneio.exceptions import RestartRequestException
from boneio.hardware.gpio.input import get_gpio_manager

# Filter out cryptography deprecation warning
warnings.filterwarnings("ignore", category=DeprecationWarning, module="cryptography")

_LOGGER = logging.getLogger(__name__)


# Early OLED is initialized in bonecli.py before runner.
# Import centralized functions here for use during startup sequence.
# Wrapped in try/except so runner works even without display libraries.
try:
    from boneio.hardware.display.early_oled import (
        draw_crash as _draw_crash,
    )
    from boneio.hardware.display.early_oled import (
        draw_status as _draw_startup_status_impl,
    )
    from boneio.hardware.display.early_oled import (
        get_early_device as _get_early_oled_device,
    )
except Exception:
    _LOGGER.debug("Early OLED module not available in runner")

    def _get_early_oled_device() -> Any | None:
        return None  # noqa: E731

    def _draw_startup_status_impl(msg: str, **kw: Any) -> None:
        pass  # noqa: E731

    def _draw_crash(exc: BaseException, **kw: Any) -> None:
        pass  # noqa: E731



def _warn_if_setup_required(
    oled_device: Any | None, config_file: str, web_config: dict
) -> bool:
    """Say on the OLED that the device is waiting to be set up.

    A device with no administrator refuses its API from 1.6 on, and the owner
    may have arrived here by jumping several versions and never reading a
    release note. This is the one channel that reaches somebody standing in
    front of a headless controller.

    Written to the boot screen rather than inserted into the running display
    rotation: that rotation is configured by the user in ``oled.screens``, and
    pushing an uninvited screen into it is not this function's call.

    Never raises — a missing display or an unreadable store must not stop the
    device from booting.

    Args:
        oled_device: Early OLED device, or None when there is no display.
        config_file: Path to the active config file.
        web_config: The ``web`` section, read for the port and the
            ``auth.allow_anonymous`` opt-out.
    """
    try:
        from boneio.core.auth.store import UserStore

        # BONEIO_DEV opens an unprovisioned device too, so the notice would be
        # wrong there: the API is not refusing anything on a dev box.
        if bool(web_config.get("auth", {}).get("allow_anonymous")) or os.environ.get(
            "BONEIO_DEV"
        ):
            return False

        if _is_provisioned(config_file):
            return False

        port = web_config.get("port", 8090)
        _LOGGER.warning(
            "SETUP REQUIRED: this device has no administrator account, so the "
            "API is refusing requests. Open http://<device-ip>:%s to finish "
            "setup. To keep the pre-1.6 unauthenticated behaviour instead, set "
            "web.auth.allow_anonymous: true in %s.",
            port,
            config_file,
        )
        _draw_startup_status(oled_device, f"SETUP REQUIRED - open :{port}")
        return True
    except Exception as err:  # noqa: BLE001 - never block boot on a notice
        _LOGGER.debug("Could not report setup state: %s", err)
        return False


def _is_provisioned(config_file: str) -> bool:
    """Whether the device has an administrator account."""
    from boneio.core.auth.store import UserStore

    store = UserStore.for_config_file(config_file)
    store.load()
    return store.is_provisioned()


def _show_setup_notice(manager: Any, config_file: str, port: int) -> None:
    """Keep "Setup required" on the OLED until an administrator exists.

    The boot-screen line from :func:`_warn_if_setup_required` is gone the
    moment the configured screens start, and the display sleeps after its
    screensaver timeout — so someone who walks up to the cabinet a quarter of
    an hour after boot, or after an update from 1.5 left the device with no
    account, sees a dark panel and an API that refuses them. The notice stays
    first and awake, and goes by itself once an account is created.

    Never raises — a missing display must not stop the device from booting.

    Args:
        manager: The running manager.
        config_file: Path to the active config file.
        port: Web panel port, for when the address is not known yet.
    """
    try:
        oled = manager.display.get_oled()
        if oled is None:
            return

        def lines() -> list[str]:
            url = manager.config_helper.configuration_url
            return ["Onboarding needed.", "Open in a browser:", url or f"http://<device-ip>:{port}"]

        oled.show_notice(
            "Setup required",
            lines,
            still_needed=lambda: not _is_provisioned(config_file),
        )
    except Exception as err:  # noqa: BLE001 - never block boot on a notice
        _LOGGER.debug("Could not show the setup notice on the OLED: %s", err)

def _draw_startup_status(device: Any | None, message: str) -> None:
    """Draw a startup status message on the OLED display.

    Thin wrapper that accepts a device argument for backward compatibility
    but delegates to the centralized early_oled module.

    Args:
        device: sh1106 device instance (or None to skip)
        message: Status message to display
    """
    _draw_startup_status_impl(message, device=device)


config_modules = [
    {"name": MCP23017, "default": []},
    {"name": PCF8575, "default": []},
    {"name": PCA9685, "default": []},
    {"name": ADC, "default": []},
    {"name": COVER, "default": []},
    {"name": MODBUS, "default": {}},
    {"name": OLED, "default": {}},
    {"name": DALLAS, "default": None},
    {"name": OUTPUT_GROUP, "default": []},
    {"name": TEMPLATE, "default": []},
    {"name": IRRIGATION, "default": []},
    {"name": "location", "default": None},
    {"name": "schedule", "default": []},
    {"name": "virtual_switch", "default": []},
]


async def async_run(
    config: dict, config_file: str, mqttusername: str = "", mqttpassword: str = "", debug: int = 0
) -> int:
    """Run BoneIO."""
    web_server = None
    tasks: set[asyncio.Task] = set()
    startup_failures = StartupFailures(config_file)
    loop = asyncio.get_running_loop()
    event_bus = EventBus(loop=loop)
    shutdown_event = asyncio.Event()
    if debug >= 2:
        loop.set_debug(True)
    async def _loop_watchdog() -> None:
        """Report when something blocks the event loop.

        A sleep that comes back late can only mean one thing: something
        synchronous ran where it should not have - an import, a subprocess, a
        long parse - and for that whole time the controller answered nothing.
        It is otherwise invisible: the log simply has a gap, and you have to
        guess what fell into it. Note that a worker thread is no defence when
        the work is CPU-bound, because it holds the GIL all the same.
        """
        import time as _wt

        interval = 0.2
        last = _wt.monotonic()
        while True:
            await asyncio.sleep(interval)
            now = _wt.monotonic()
            drift = now - last - interval
            if drift > 0.4:
                _LOGGER.warning("[LOOP STALL] blocked for %.2fs", drift)
            last = now

    if debug >= 1:
        tasks.add(asyncio.create_task(_loop_watchdog()))

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
        version=main_config.get("version", "0.8"),
        network_info=network_state,

        is_web_active=web_active,
        web_port=web_config.get("port", 8090),
        proxy_port=web_config.get("proxy_port"),
        expose=web_config.get("expose", "all"),
        ha_discovery=mqtt_config.get(HA_DISCOVERY, {}).get(ENABLED, False),
        ha_discovery_prefix=mqtt_config.get(HA_DISCOVERY, {}).get(TOPIC_PREFIX, "homeassistant"),
        config_file_path=config_file,
        send_boneio_autodiscovery=mqtt_config.get("send_boneio_autodiscovery", True),
        receive_boneio_autodiscovery=mqtt_config.get("receive_boneio_autodiscovery", True),
        update_channel=mqtt_config.get("update_channel", "stable"),
        cloud_registration=web_config.get("cloud", {}).get("enabled", False),
        pwa_name=web_config.get("cloud", {}).get("pwa_name"),
        ha_child_devices=main_config.get("ha_child_devices", False),
        ha_child_devices_naming=main_config.get("ha_child_devices_naming", "default"),
        serial_override=main_config.get("serial_override"),
    )

    # Which unit this log came from.
    #
    # The only identity in the log was "BoneIO <version> starting", which says
    # nothing about the device. A log reaches support detached from whoever
    # sent it — pasted into a ticket, dropped in a forum thread — and the
    # serial is what ties it to a unit, its MQTT topics and its cloud
    # subdomain. Naming it once at startup costs a line.
    #
    # Safe to write here: the log and the bundle are admin-only. The serial is
    # withheld from unauthenticated API responses because those answer to
    # anyone on the network, which this does not.
    _LOGGER.info(
        "Device %s (%s, hardware %s), serial %s",
        _config_helper.name,
        _config_helper.device_type,
        _config_helper.version,
        _config_helper.serial_number,
    )

    # Load areas configuration
    _config_helper.set_areas(areas_config=config.get("areas", []))

    # Determine CAN slave mode (slave devices don't need MQTT)
    can_config = config.get(CAN, {})
    is_can_slave = can_config.get(ENABLED, False) and can_config.get("mode", "master") == "slave"

    # Initialize message bus based on config
    from boneio.core.messaging.composite import CompositeMessageBus

    message_bus = CompositeMessageBus()
    has_mqtt = False

    if MQTT in config and not is_can_slave:
        mqtt_config = config[MQTT]
        if mqtt_config.get("enabled", True):
            mqtt_bus = MQTTClient(
                host=mqtt_config[HOST],
                username=mqtt_config.get(USERNAME, mqttusername),
                password=mqtt_config.get(PASSWORD, mqttpassword),
                port=mqtt_config.get(PORT, 1883),
                config_helper=_config_helper,
            )
            message_bus.add_bus(mqtt_bus)
            has_mqtt = True
        else:
            _LOGGER.info("MQTT protocol disabled in configuration")

    lox_config = config.get("lox_udp")
    if lox_config and lox_config.get("enabled", False) and not is_can_slave:
        from boneio.core.messaging.lox import LoxUDPClient

        lox_bus = LoxUDPClient(
            config_helper=_config_helper,
            host=lox_config.get("host", "127.0.0.1"),
            send_port=lox_config.get("send_port", 4444),
            listen_port=lox_config.get("listen_port", 4445),
        )
        message_bus.add_bus(lox_bus)

    # Lox UDP doesn't provide internal loopback routing like MQTT broker does.
    # Therefore, if MQTT is not enabled, we MUST use LocalMessageBus to route
    # internal messages (e.g. from WebUI to Thermostat templates).
    if not has_mqtt:
        from boneio.core.messaging import LocalMessageBus

        message_bus.add_bus(LocalMessageBus())
        if is_can_slave:
            _LOGGER.info("CAN slave mode: using LocalMessageBus for internal routing")
        else:
            _LOGGER.info("MQTT disabled: using LocalMessageBus for internal routing")

    manager_kwargs = {item["name"]: config.get(item["name"], item["default"]) for item in config_modules}

    # --- Reuse early OLED device (initialized in bonecli.py) for startup status ---
    early_oled_device = _get_early_oled_device()
    _draw_startup_status(early_oled_device, "Initializing...")

    manager = Manager(
        message_bus=message_bus,
        event_bus=event_bus,
        relay_pins=config.get(OUTPUT, []),
        event_pins=config.get(EVENT_ENTITY, []),
        binary_pins=config.get(BINARY_SENSOR, []),
        remote_devices=config.get("remote_devices", []),
        config_file_path=config_file,
        state_manager=StateManager(state_file=f"{os.path.split(config_file)[0]}state.json"),
        config_helper=_config_helper,
        sensors={
            LM75: config.get(LM75, []),
            INA219: config.get(INA219, []),
            INA226: config.get(INA226, []),
            MCP_TEMP_9808: config.get(MCP_TEMP_9808, []),
            ONEWIRE: config.get(SENSOR, []),
            VIRTUAL_ENERGY_SENSOR: config.get(VIRTUAL_ENERGY_SENSOR, []),
        },
        modbus_devices=config.get("modbus_devices", []),
        can=config.get(CAN, {}),
        web_active=web_active,
        web_port=web_config.get("port", 8090),
        early_oled_device=early_oled_device,
        **manager_kwargs,
    )
    # Convert coroutines to Tasks
    message_bus.set_manager(manager=manager)
    # Add manager tasks (get_tasks returns dict, we need values)
    manager_tasks = manager.get_tasks()
    tasks.update(manager_tasks.values())

    # --- Start web server EARLY (before MQTT/discovery) for fast UI access ---
    _draw_startup_status(early_oled_device, "Starting web server...")
    if _warn_if_setup_required(early_oled_device, config_file, web_config):
        _show_setup_notice(manager, config_file, web_config.get("port", 8090))
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
            security=web_config.get("security", {}),
            logger=config.get("logger", {}),
            debug_level=debug,
            initial_config=config,  # Pre-populate cache for fast first request
            # 'all' keeps the panel on every interface, which is what it has
            # always done. 'proxy' takes it off the LAN and leaves it reachable
            # over TLS through Caddy, or through an SSH tunnel — the answer to
            # the pentest finding about the interface being served in the
            # clear. Opt-in until it has been through a release on hardware:
            # getting it wrong means a controller answering on nothing.
            expose=web_config.get("expose", "all"),
        )
        web_server_task = asyncio.create_task(web_server.start_webserver())
        tasks.add(web_server_task)
        web_server_task.add_done_callback(tasks.discard)
        # Store websocket_manager reference for startup status broadcasts
        # (available after first await yields to event loop and init_app runs)
        await asyncio.sleep(0)  # Yield to let web server task start
        if hasattr(web_server, "app") and hasattr(web_server.app, "state"):
            manager._websocket_manager = getattr(web_server.app.state, "websocket_manager", None)
    else:
        _LOGGER.info("Web server not configured.")

    # --- Start GPIO manager ---
    _draw_startup_status(early_oled_device, "Starting GPIO...")
    await manager.set_startup_status("starting_gpio", "Starting GPIO...")
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

    # Start CAN bus if configured (non-blocking)
    if manager.canopen is not None:
        can_task = asyncio.create_task(manager.start_canopen())
        tasks.add(can_task)
        can_task.add_done_callback(tasks.discard)

    # Initialize remote devices in background (configure + start connections)
    # This defers heavy module imports (aioesphomeapi, aiohttp) to background
    async def _init_remote_devices_and_inputs() -> None:
        """Initialize remote devices, then register ESPHome binary sensor inputs.

        Held until the web stack has finished importing. Both this and the web
        server have several seconds of module-level work to do, and with one
        core they only slow each other down - measured on a BeagleBone, running
        them at once put the UI six seconds further away. Nothing waits for a
        remote device: its entities appear when it connects, which is
        asynchronous anyway. The wait is capped so a web server that never
        comes up cannot strand them.
        """
        waited_for_web = False
        if web_server is not None:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(web_server.stack_imported.wait(), timeout=120)
                waited_for_web = True
            # And then for the UI to have been served, because importing the
            # remote backends blocks the loop for seconds even from a worker
            # thread - it is CPU work, so it holds the GIL - and the first page
            # load is the worst moment for that. Capped: on a controller nobody
            # ever opens, there is nothing to wait for.
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(web_server.first_response.wait(), timeout=8)
                # Let the page finish pulling its assets before we take the
                # loop away from it.
                await asyncio.sleep(3)
        # initialize()'s own delay exists to keep these connections off the
        # startup path. Having just waited for the web stack, that job is done -
        # delaying again only keeps the remote entities away for longer.
        #
        # Caught here because this task sits in the main gather below: an
        # exception escaping it ended the whole application, local outputs and
        # all, and systemd restarted it into the same exception every 3s. A
        # remote device is somebody else's hardware - it can take its own
        # entities down, not this controller.
        try:
            await manager.remote_devices.initialize(delay_seconds=0.0 if waited_for_web else 10.0)
            manager.register_esphome_binary_sensors()
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.exception(
                "Remote devices failed to initialise; continuing without them"
            )

    remote_task = manager.append_task(coro=_init_remote_devices_and_inputs, name="remote_devices_init")
    tasks.add(remote_task)

    # --- Start MQTT and discovery in background ---
    _draw_startup_status(early_oled_device, "Connecting messaging...")
    await manager.set_startup_status("connecting_messaging", "Connecting messaging buses...")
    _LOGGER.info("Starting message bus.")
    message_bus_task = asyncio.create_task(message_bus.start_client())
    tasks.add(message_bus_task)
    message_bus_task.add_done_callback(tasks.discard)

    # Publish discovery after message bus is started (non-blocking)
    async def _delayed_discovery() -> None:
        """Wait for MQTT connection and publish discovery in background."""
        try:
            await asyncio.sleep(1)
            _draw_startup_status(early_oled_device, "Publishing discovery...")
            await manager.set_startup_status("ha_discovery", "Publishing HA Discovery...")
            _LOGGER.info("Publishing device discovery information")
            await manager.publish_discovery()
            _draw_startup_status(early_oled_device, "Ready")
            # Brief pause so user sees "Ready" before handoff stops drawing
            await asyncio.sleep(1)
            await manager.mark_startup_complete()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            _LOGGER.error("Error during delayed discovery: %s", e)
            await manager.mark_startup_complete()

    if has_mqtt:
        discovery_task = asyncio.create_task(_delayed_discovery())
        tasks.add(discovery_task)
        discovery_task.add_done_callback(tasks.discard)
    else:
        # No MQTT — mark startup complete immediately
        _draw_startup_status(early_oled_device, "Ready")
        await manager.mark_startup_complete()

    # Start cloud registration if enabled
    cloud_reg = None
    if _config_helper.cloud_registration:
        local_ip = network_state.get("ip", "")
        serial = _config_helper.serial_number
        if local_ip and serial:
            # Imported here: cloud registration is opt-in, so users with it
            # disabled should not pay for the import at all.
            from boneio.core.cloud import CloudRegistration

            cloud_reg = CloudRegistration(
                serial_number=serial,
                local_ip=local_ip,
            )
            await cloud_reg.start()
            _config_helper._cloud_reg = cloud_reg
            _LOGGER.info("Cloud registration started for %s (IP: %s)", serial, local_ip)
        else:
            _LOGGER.warning("Cloud registration enabled but missing serial or IP")

    # A start that stays up this long has proven itself: forget the crashes
    # before it, so an occasional one weeks apart never adds up to recovery
    # mode. Not in the main gather - it has nothing to wait for afterwards.
    async def _forgive_earlier_crashes() -> None:
        await asyncio.sleep(STABLE_AFTER_SECONDS)
        if startup_failures.count:
            _LOGGER.info("Running for %ds; clearing the startup crash count", STABLE_AFTER_SECONDS)
            startup_failures.clear()

    stable_task = asyncio.create_task(_forgive_earlier_crashes())

    try:
        # Convert tasks set to list for main gather
        task_list = list(tasks)
        main_gather = asyncio.gather(*task_list)

        # Wait for either shutdown signal or main task completion
        await asyncio.wait(
            [main_gather, asyncio.create_task(shutdown_event.wait())], return_when=asyncio.FIRST_COMPLETED
        )

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
            with contextlib.suppress(asyncio.CancelledError):
                await main_gather

        return 0
    except asyncio.CancelledError:
        _LOGGER.info("Main task cancelled")
        return 0
    except (RestartRequestException, GracefulExit):
        _LOGGER.info("Restart or graceful exit requested")
        raise
    except Exception as e:
        _LOGGER.error(f"Unexpected error: {type(e).__name__} - {e}", exc_info=True)
        _draw_crash(e)
        startup_failures.record(e)
        return 1
    except BaseException as e:
        _LOGGER.error(f"Unexpected BaseException: {type(e).__name__} - {e}", exc_info=True)
        _draw_crash(e)
        startup_failures.record(e)
        return 1
    finally:
        _LOGGER.info("Cleaning up resources...")
        stable_task.cancel()

        # Cancel pending deferred state saves and write final state synchronously.
        # This MUST happen before event_bus.stop() which may trigger sigterm
        # listeners that call save_attribute() (e.g. covers turning off).
        # On Python 3.13+, the default executor is shut down after async_run returns,
        # so any call_later(1, save_state) that fires later would crash with
        # RuntimeError: Executor shutdown has been called.
        try:
            manager._state_manager.cancel_pending_and_save()
        except Exception as e:
            _LOGGER.error(f"Error cancelling pending state saves: {e}")

        # Trigger web server shutdown if it's running
        if web_server and hasattr(web_server, "trigger_shutdown"):
            try:
                _LOGGER.info("Requesting web server shutdown...")
                await web_server.trigger_shutdown()
            except Exception as e:
                _LOGGER.error(f"Error triggering web server shutdown: {e}")

        # Stop cloud registration
        if cloud_reg:
            try:
                _LOGGER.info("Stopping cloud registration...")
                await cloud_reg.stop()
            except Exception as e:
                _LOGGER.error(f"Error stopping cloud registration: {e}")

        # Stop GPIO manager
        try:
            if gpio_manager:
                _LOGGER.info("Stopping GPIO manager...")
                await gpio_manager.stop()
        except Exception as e:
            _LOGGER.error(f"Error stopping GPIO manager: {e}")

        # Stop manager async tasks (ESPHome connections, etc.)
        try:
            _LOGGER.info("Stopping manager async tasks...")
            await manager.stop()
        except Exception as e:
            _LOGGER.error(f"Error stopping manager: {e}")

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
