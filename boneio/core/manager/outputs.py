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
from typing import TYPE_CHECKING, Any

from boneio.components.output.basic import BasicOutput
from boneio.const import (
    COVER,
    ID,
    MCP,
    NONE,
    OUTPUT,
    PCA,
    PCF,
    RESTORE_STATE,
    SET_BRIGHTNESS,
    relay_actions,
)
from boneio.core.config.loader import (
    configure_output_group,
    configure_relay,
    create_expander,
)
from boneio.core.utils import strip_accents
from boneio.integration.interlock import SoftwareInterlockManager

if TYPE_CHECKING:
    from boneio.core.manager import Manager

_LOGGER = logging.getLogger(__name__)


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
        
        self.grouped_outputs_by_expander = create_expander(
            expander_dict=self._mcp,
            expander_config=mcp23017,
            exp_type=MCP,
            i2cbusio=self._manager._i2cbusio,
        )
        self.grouped_outputs_by_expander.update(
            create_expander(
                expander_dict=self._pcf,
                expander_config=pcf8575,
                exp_type=PCF,
                i2cbusio=self._manager._i2cbusio,
            )
        )
        self.grouped_outputs_by_expander.update(
            create_expander(
                expander_dict=self._pca,
                expander_config=pca9685,
                exp_type=PCA,
                i2cbusio=self._manager._i2cbusio,
            )
        )

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
            
            output_group = configure_output_group(
                manager=self._manager,
                message_bus=self._manager._message_bus,
                event_bus=self._manager._event_bus,
                config_helper=self._manager._config_helper,
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
        from boneio.const import ON, RELAY
        
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
            from boneio.const import LIGHT, LED, SWITCH, VALVE
            for output_type in [LIGHT, LED, SWITCH, VALVE]:
                self._manager._config_helper.clear_autodiscovery_type(ha_type=output_type)
        
        _LOGGER.debug("Initializing outputs")
        
        for _config in relay_pins:
            # Create a copy to avoid modifying the original
            config_copy = _config.copy()
            _name = config_copy.pop(ID)
            restore_state = config_copy.pop(RESTORE_STATE, False)
            _id = strip_accents(_name)
            
            out = configure_relay(
                manager=self._manager,
                message_bus=self._manager._message_bus,
                state_manager=self._manager._state_manager,
                topic_prefix=self._manager._topic_prefix,
                relay_id=_id,
                name=_name,
                config=config_copy,
                restore_state=restore_state,
                mcp=self._mcp,
                pca=self._pca,
                pcf=self._pcf,
                grouped_outputs_by_expander=self.grouped_outputs_by_expander,
                interlock_manager=self._interlock_manager,
                event_bus=self._manager._event_bus,
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

    async def send_ha_autodiscovery(self) -> None:
        """Send Home Assistant autodiscovery for all outputs."""
        for output_id, output in self._outputs.items():
            if output.output_type not in (NONE, COVER):
                self._manager.send_ha_autodiscovery(
                    id=output_id,
                    name=output.name,
                    ha_type=output.output_type,
                    output_type=output.output_type,
                )
        
        for group_id, group in self._configured_output_groups.items():
            self._manager.send_ha_autodiscovery(
                id=group_id,
                name=group.name,
                ha_type=group.output_type,
                output_type=group.output_type,
            )
