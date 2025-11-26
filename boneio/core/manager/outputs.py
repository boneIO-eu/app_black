"""Output manager - handles all output devices.

This module manages all output devices including:
- Relays (GPIO, MCP23017, PCF8575, PCA9685)
- Switches
- Lights
- LEDs
- Valves
- Output groups
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import namedtuple
from typing import TYPE_CHECKING, Any

from boneio.components.output import MCPOutput, PCFOutput, PWMOutput
from boneio.components.output.basic import BasicOutput
from boneio.const import (
    ADDRESS,
    COVER,
    GPIO,
    ID,
    INIT_SLEEP,
    KIND,
    MCP,
    MCP_ID,
    NONE,
    OUTPUT,
    OUTPUT_TYPE,
    PCA,
    PCA_ID,
    PCF,
    PCF_ID,
    PIN,
    RELAY,
    RESTORE_STATE,
    SET_BRIGHTNESS,
    ExpanderTypes,
    relay_actions,
)
from boneio.core.utils import TimePeriod, strip_accents
from boneio.exceptions import GPIOOutputException
from boneio.hardware.gpio.expanders import MCP23017, PCA9685, PCF8575
from boneio.integration.homeassistant import ha_virtual_energy_sensor_discovery_message
from boneio.integration.interlock import SoftwareInterlockManager

if TYPE_CHECKING:
    from boneio.core.manager import Manager

_LOGGER = logging.getLogger(__name__)

# Expander class mapping
_EXPANDER_CLASS = {MCP: MCP23017, PCA: PCA9685, PCF: PCF8575}

# Output entry for relay configuration
OutputEntry = namedtuple("OutputEntry", "OutputClass output_kind expander_id")


class OutputManager:
    """Manages all outputs (relay, switch, light, led, valve).
    
    This manager handles:
    - Hardware expanders (MCP23017, PCF8575, PCA9685)
    - Output devices (relays, switches, lights, LEDs, valves)
    - Output groups
    - Interlock management
    - State restoration
    - Home Assistant autodiscovery
    
    Args:
        manager: Parent Manager instance
        relay_pins: List of relay configurations
        pca9685: List of PCA9685 expander configurations
        mcp23017: List of MCP23017 expander configurations
        pcf8575: List of PCF8575 expander configurations
        output_group: List of output group configurations
    """

    def __init__(
        self,
        manager: Manager,
        relay_pins: list[dict],
        pca9685: list[dict],
        mcp23017: list[dict],
        pcf8575: list[dict],
        output_group: list[dict],
    ):
        """Initialize output manager."""
        self._manager = manager
        self._outputs: dict[str, BasicOutput] = {}
        self._configured_output_groups = {}
        self._interlock_manager = SoftwareInterlockManager()
        self._outputs_group = output_group
        
        # Hardware expanders
        self._mcp = {}
        self._pcf = {}
        self._pca = {}
        self.grouped_outputs_by_expander = {}
        
        # Initialize hardware expanders
        self._initialize_hardware_expanders(
            mcp23017=mcp23017,
            pcf8575=pcf8575,
            pca9685=pca9685,
        )
        
        # Initialize outputs
        self._initialize_outputs(relay_pins=relay_pins, reload_config=False)
        
        # Configure output groups
        self._configure_output_groups()
        
        _LOGGER.info(
            "OutputManager initialized with %d outputs and %d groups",
            len(self._outputs),
            len(self._configured_output_groups)
        )

    def _initialize_hardware_expanders(
        self,
        mcp23017: list[dict],
        pcf8575: list[dict],
        pca9685: list[dict],
    ) -> None:
        """Initialize I2C hardware expanders (MCP23017, PCF8575, PCA9685)."""
        _LOGGER.debug("Initializing hardware expanders")
        
        self.grouped_outputs_by_expander = self._create_expander(
            expander_dict=self._mcp,
            expander_config=mcp23017,
            exp_type=MCP,
        )
        self.grouped_outputs_by_expander.update(
            self._create_expander(
                expander_dict=self._pcf,
                expander_config=pcf8575,
                exp_type=PCF,
            )
        )
        self.grouped_outputs_by_expander.update(
            self._create_expander(
                expander_dict=self._pca,
                expander_config=pca9685,
                exp_type=PCA,
            )
        )

    def _create_expander(
        self,
        expander_dict: dict,
        expander_config: list,
        exp_type: ExpanderTypes,
    ) -> dict:
        """Create and initialize hardware expanders.
        
        Args:
            expander_dict: Dictionary to store expander instances
            expander_config: List of expander configurations
            exp_type: Type of expander (MCP, PCF, PCA)
            
        Returns:
            Dictionary of grouped outputs by expander ID
        """
        grouped_outputs = {}
        for expander in expander_config:
            id = expander[ID] or expander[ADDRESS]
            try:
                expander_dict[id] = _EXPANDER_CLASS[exp_type](
                    i2c=self._manager._i2cbusio, address=expander[ADDRESS], reset=False
                )
                sleep_time = expander.get(INIT_SLEEP, TimePeriod(seconds=0))
                if sleep_time.total_seconds > 0:
                    _LOGGER.debug(
                        "Sleeping for %ss while %s %s is initializing.",
                        sleep_time.total_seconds, exp_type, id
                    )
                    time.sleep(sleep_time.total_seconds)
                else:
                    _LOGGER.debug("%s %s is initializing.", exp_type, id)
                grouped_outputs[id] = {}
            except TimeoutError as err:
                _LOGGER.error("Can't connect to %s %s: %s", exp_type, id, err)
        return grouped_outputs

    def _configure_output_groups(self) -> None:
        """Configure output groups."""
        def get_outputs(output_list):
            outputs = []
            for x in output_list:
                x = strip_accents(x)
                if x in self._outputs:
                    output = self._outputs[x]
                    if output.output_type == COVER:
                        _LOGGER.warning("You can't add cover output to group.")
                    else:
                        outputs.append(output)
            return outputs

        for group in self._outputs_group:
            members = get_outputs(group.pop("outputs"))
            if not members:
                _LOGGER.warning(
                    "Output group %s doesn't have any members. Omitting.", group.get(ID)
                )
                continue
            
            _id = strip_accents(group.pop(ID))
            _name = group.pop("name", _id)
            
            output_group = self._create_output_group(
                id=_id,
                name=_name,
                outputs=members,
                **group,
            )
            
            self._configured_output_groups[_id] = output_group
            
            # Send HA autodiscovery for group
            self._manager.send_ha_autodiscovery(
                id=_id,
                name=_name,
                ha_type=output_group.output_type,
                output_type=output_group.output_type,
            )

    def _create_output_group(self, id: str, name: str, outputs: list, **kwargs) -> Any:
        """Create an output group instance.
        
        Args:
            id: Group identifier
            name: Group display name
            outputs: List of output instances
            **kwargs: Additional configuration
            
        Returns:
            OutputGroup instance
        """
        from boneio.components.group import OutputGroup
        
        return OutputGroup(
            message_bus=self._manager._message_bus,
            topic_prefix=self._manager._topic_prefix,
            id=id,
            name=name,
            outputs=outputs,
            callback=lambda: None,
            **kwargs,
        )

    def _output_chooser(self, output_kind: str, config: dict) -> OutputEntry:
        """Get output class and expander info based on output kind.
        
        Args:
            output_kind: Type of output (MCP, PCF, PCA, GPIO)
            config: Configuration dictionary (will be modified to pop expander_id)
            
        Returns:
            OutputEntry namedtuple with OutputClass, output_kind, expander_id
            
        Raises:
            GPIOOutputException: If output_kind is not supported
        """
        if output_kind == MCP:
            expander_id = config.pop(MCP_ID, None)
            return OutputEntry(MCPOutput, MCP, expander_id)
        elif output_kind == PCA:
            expander_id = config.pop(PCA_ID, None)
            return OutputEntry(PWMOutput, PCA, expander_id)
        elif output_kind == PCF:
            expander_id = config.pop(PCF_ID, None)
            return OutputEntry(PCFOutput, PCF, expander_id)
        else:
            raise GPIOOutputException(f"Output type {output_kind} doesn't exist")

    def _configure_relay(
        self,
        relay_id: str,
        name: str,
        config: dict,
        restore_state: bool = False,
    ) -> Any:
        """Configure a relay output.
        
        Args:
            relay_id: Relay identifier
            name: Display name
            config: Configuration dictionary
            restore_state: Whether to restore previous state
            
        Returns:
            Configured relay instance or None on error
        """
        output_type = config.pop(OUTPUT_TYPE)
        restored_state = (
            self._manager._state_manager.get(attr_type=RELAY, attr=relay_id, default_value=False)
            if restore_state
            else False
        )
        if output_type == NONE and self._manager._state_manager.get(
            attr_type=RELAY, attr=relay_id
        ):
            self._manager._state_manager.del_attribute(attr_type=RELAY, attribute=relay_id)
            restored_state = False

        output = self._output_chooser(output_kind=config.pop(KIND), config=config)
        output_kind = getattr(output, "output_kind")
        expander_id = getattr(output, "expander_id")

        if output_kind == MCP:
            mcp_expander = self._mcp.get(expander_id)
            if not mcp_expander:
                _LOGGER.error("No such MCP configured!")
                return None
            extra_args = {
                "pin": int(config.pop(PIN)),
                "mcp": mcp_expander,
                "mcp_id": expander_id,
                "output_type": output_type,
            }
        elif output_kind == PCA:
            pca_expander = self._pca.get(expander_id)
            if not pca_expander:
                _LOGGER.error("No such PCA configured!")
                return None
            extra_args = {
                "pin": int(config.pop(PIN)),
                "pca": pca_expander,
                "pca_id": expander_id,
                "output_type": output_type,
            }
        elif output_kind == PCF:
            expander = self._pcf.get(expander_id)
            if not expander:
                _LOGGER.error("No such PCF configured!")
                return None
            extra_args = {
                "pin": int(config.pop(PIN)),
                "expander": expander,
                "expander_id": expander_id,
                "output_type": output_type,
            }
        elif output_kind == GPIO:
            if GPIO not in self.grouped_outputs_by_expander:
                self.grouped_outputs_by_expander[GPIO] = {}
            extra_args = {
                "pin": config.pop(PIN),
            }
        else:
            _LOGGER.error("Output kind: %s is not configured", output_kind)
            return None

        interlock_groups = config.get("interlock_group", [])
        if isinstance(interlock_groups, str):
            interlock_groups = [interlock_groups]

        relay = getattr(output, "OutputClass")(
            message_bus=self._manager._message_bus,
            event_bus=self._manager._event_bus,
            topic_prefix=self._manager._topic_prefix,
            id=relay_id,
            restored_state=restored_state,
            interlock_manager=self._interlock_manager,
            interlock_groups=interlock_groups,
            name=name,
            **config,
            **extra_args,
        )
        self._interlock_manager.register(relay, interlock_groups)
        self.grouped_outputs_by_expander[expander_id][relay_id] = relay
        
        # Send HA autodiscovery for virtual power/energy sensors
        if relay.is_virtual_power:
            self._manager.send_ha_autodiscovery(
                id=f"{relay_id}_virtual_power",
                relay_id=relay_id,
                name=f"{name} Virtual Power",
                ha_type="sensor",
                device_type="energy",
                availability_msg_func=ha_virtual_energy_sensor_discovery_message,
                unit_of_measurement="W",
                device_class="power",
                state_class="measurement",
                value_template="{{ value_json.power }}"
            )
            self._manager.send_ha_autodiscovery(
                id=f"{relay_id}_virtual_energy",
                relay_id=relay_id,
                name=f"{name} Virtual Energy",
                ha_type="sensor",
                device_type="energy",
                availability_msg_func=ha_virtual_energy_sensor_discovery_message,
                unit_of_measurement="Wh",
                device_class="energy",
                state_class="total_increasing",
                value_template="{{ value_json.energy }}"
            )
        if relay.is_virtual_volume_flow_rate:
            self._manager.send_ha_autodiscovery(
                id=f"{relay_id}_virtual_volume_flow_rate",
                relay_id=relay_id,
                name=f"{name} Virtual Volume Flow Rate",
                ha_type="sensor",
                device_type="energy",
                availability_msg_func=ha_virtual_energy_sensor_discovery_message,
                unit_of_measurement="L/h",
                device_class="volume_flow_rate",
                state_class="measurement",
                value_template="{{ value_json.volume_flow_rate }}"
            )
            self._manager.send_ha_autodiscovery(
                id=f"{relay_id}_virtual_consumption",
                relay_id=relay_id,
                name=f"{name} Virtual consumption",
                ha_type="sensor",
                device_type="energy",
                availability_msg_func=ha_virtual_energy_sensor_discovery_message,
                unit_of_measurement="L",
                device_class="water",
                state_class="total_increasing",
                value_template="{{ value_json.water }}"
            )
        return relay

    async def _delayed_send_state(self, output: BasicOutput) -> None:
        """Send output state after a delay."""
        await asyncio.sleep(0.5)
        await output.async_send_state()

    async def _relay_callback(self, output_state: Any) -> None:
        """Handle relay state change events.
        
        Saves relay state to state manager.
        
        Args:
            output_state: OutputState object with id and state
        """
        from boneio.const import ON
        
        # Save state to state manager
        if hasattr(output_state, 'id') and hasattr(output_state, 'state'):
            self._manager._state_manager.save_attribute(
                attr_type=RELAY,
                attribute=output_state.id,
                value=output_state.state == ON,
            )

    def get_output(self, id: str) -> BasicOutput | None:
        """Get output by ID.
        
        Args:
            id: Output identifier
            
        Returns:
            Output instance or None if not found
        """
        return self._outputs.get(id)

    def get_output_group(self, id: str) -> Any | None:
        """Get output group by ID.
        
        Args:
            id: Output group identifier
            
        Returns:
            Output group instance or None if not found
        """
        return self._configured_output_groups.get(id)

    def get_all_outputs(self) -> dict[str, BasicOutput]:
        """Get all outputs.
        
        Returns:
            Dictionary of all outputs
        """
        return self._outputs

    def get_all_output_groups(self) -> dict:
        """Get all output groups.
        
        Returns:
            Dictionary of all output groups
        """
        return self._configured_output_groups

    async def toggle_output(self, output_id: str) -> str:
        """Toggle output state.
        
        Args:
            output_id: Output identifier
            
        Returns:
            Status string ('ok', 'not_allowed', or 'not_found')
        """
        output = self._outputs.get(output_id)
        if output:
            if output.output_type == NONE or output.output_type == COVER:
                return "not_allowed"
            await output.async_toggle()
            return "ok"
        return "not_found"

    def handle_relay_command(self, device_id: str, command: str, message: str) -> None:
        """Handle MQTT relay command.
        
        Args:
            device_id: Device identifier
            command: Command type ('set' or 'set_brightness')
            message: Command payload
        """
        if command == "set":
            target_device = self._outputs.get(device_id)
            if target_device and target_device.output_type != NONE:
                action_from_msg = relay_actions.get(message.upper())
                if action_from_msg:
                    getattr(target_device, action_from_msg)()
                else:
                    _LOGGER.debug("Unknown action %s for device %s", message, device_id)
            else:
                _LOGGER.debug("Target device not found %s", device_id)
                
        elif command == SET_BRIGHTNESS:
            target_device = self._outputs.get(device_id)
            if target_device and target_device.output_type != NONE and message != "":
                target_device.set_brightness(int(message))
            else:
                _LOGGER.debug("Can't set brightness for %s", device_id)

    def get_tasks(self) -> dict[str, asyncio.Task]:
        """Get all output-related tasks.
        
        Returns:
            Dictionary of tasks
        """
        # Outputs don't have background tasks currently
        return {}

    def _initialize_outputs(self, relay_pins: list[dict], reload_config: bool = False) -> None:
        """Initialize outputs (relays, switches, lights, LEDs, valves).
        
        Args:
            relay_pins: List of relay configurations
            reload_config: If True, reload configuration from file and clear existing outputs
        """
        if reload_config:
            # Clear existing outputs and event listeners
            for output_id, output in list(self._outputs.items()):
                # Remove event listeners
                if output.output_type not in (NONE, COVER):
                    try:
                        self._manager._event_bus.remove_event_listener(
                            event_type="output",
                            entity_id=output_id,
                            listener_id=f"manager_output_{output_id}"
                        )
                    except Exception as e:
                        _LOGGER.debug(f"Could not remove event listener for {output_id}: {e}")
            self._outputs.clear()
            # Clear autodiscovery messages for outputs
            from boneio.const import LED, LIGHT, SWITCH, VALVE
            for output_type in [LIGHT, LED, SWITCH, VALVE]:
                self._manager._config_helper.clear_autodiscovery_type(ha_type=output_type)
        
        _LOGGER.debug("Initializing outputs")
        
        for _config in relay_pins:
            # Create a copy to avoid modifying the original
            config_copy = _config.copy()
            
            # Handle new schema: name and id are optional
            # 1. Determine Display Name (_name)
            if "name" in config_copy:
                _name = config_copy.pop("name")
            elif "id" in config_copy:
                 # Fallback to id if name is missing
                _name = config_copy.get(ID)
            elif "boneio_output" in config_copy:
                 # Fallback to boneio_output if name and id are missing
                _name = config_copy.get("boneio_output")
            else:
                # Last resort fallback
                _name = "unknown_output"

            # 2. Determine MQTT ID (_id)
            # Strategy: explicit 'id' > 'boneio_output' > 'name' (slugified)
            if ID in config_copy:
                _id = config_copy.pop(ID)
            elif "boneio_output" in config_copy:
                _id = config_copy.get("boneio_output")
            else:
                _id = strip_accents(_name)

            restore_state = config_copy.pop(RESTORE_STATE, False)
            
            out = self._configure_relay(
                relay_id=_id,
                name=_name,
                config=config_copy,
                restore_state=restore_state,
            )
            
            # Subscribe to output state changes
            if out.output_type not in (NONE, COVER):
                self._manager._event_bus.add_event_listener(
                    event_type="output",
                    entity_id=_id,
                    listener_id=f"manager_output_{_id}",
                    target=self._relay_callback,
                )
            
            self._outputs[_id] = out
            
            # Send HA autodiscovery
            if out.output_type not in (NONE, COVER):
                self._manager.send_ha_autodiscovery(
                    id=_id,
                    name=_name,
                    ha_type=out.output_type,
                    output_type=out.output_type,
                )
            
            # Delayed state send
            self._manager.loop.create_task(self._delayed_send_state(out))

    def reload_outputs(self) -> None:
        """Reload output configuration from file.
        
        This reloads outputs and output groups from the config file.
        Existing outputs are cleared and recreated based on the current config.
        """
        _LOGGER.info("Reloading output configuration")
        
        # Get config from ConfigHelper (uses cache, reloads if needed)
        config = self._manager._config_helper.reload_config()
        
        # Get new relay pins and output groups
        relay_pins = config.get(OUTPUT, [])
        output_groups = config.get("output_group", [])
        
        # Reload outputs
        self._initialize_outputs(relay_pins=relay_pins, reload_config=True)
        
        # Reload output groups
        self._configured_output_groups.clear()
        self._outputs_group = output_groups
        self._configure_output_groups()
        
        _LOGGER.info(
            "Output reload complete: %d outputs, %d groups",
            len(self._outputs),
            len(self._configured_output_groups)
        )

