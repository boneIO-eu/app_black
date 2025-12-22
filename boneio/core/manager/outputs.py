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
from typing import TYPE_CHECKING, Any, Literal

from boneio.components.output.basic import BasicOutput
from boneio.components.output.mcp import MCPOutput
from boneio.components.output.pca import PWMOutput
from boneio.components.output.pcf import PCFOutput
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
    ON,
    PCA,
    PCA_ID,
    PCF,
    PCF_ID,
    PIN,
    RESTORE_STATE,
    SET_BRIGHTNESS,
    output_actions,
)
from boneio.core.utils import TimePeriod, strip_accents
from boneio.core.utils.util import sanitize_string
from boneio.hardware.gpio.expanders import MCP23017, PCA9685, PCF8575
from boneio.integration.interlock import SoftwareInterlockManager

if TYPE_CHECKING:
    from boneio.core.manager import Manager

_LOGGER = logging.getLogger(__name__)

# Expander class mapping
_EXPANDER_CLASS = {MCP: MCP23017, PCA: PCA9685, PCF: PCF8575}


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
        exp_type: Literal['mcp', 'pcf', 'pca'],
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
            address = expander[ADDRESS]
            try:
                expander_dict[id] = _EXPANDER_CLASS[exp_type](
                    i2c=self._manager._i2cbusio, address=address, reset=False
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
            except (TimeoutError, OSError) as err:
                error_msg = f"Can't connect to {exp_type} at address {address:#x} (ID: {id}): {err}"
                _LOGGER.error(error_msg)
                # Store error in manager for WebUI display
                if not hasattr(self._manager, '_hardware_errors'):
                    self._manager._hardware_errors = []
                self._manager._hardware_errors.append({
                    'type': 'expander',
                    'expander_type': exp_type,
                    'id': id,
                    'address': address,
                    'error': str(err),
                    'message': error_msg
                })
        return grouped_outputs

    def _configure_output_groups(self) -> None:
        """Configure output groups."""
        _LOGGER.info("Configuring output groups. Found %d groups in config.", len(self._outputs_group))
        
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
                        _LOGGER.debug("Found output '%s' -> %s", x, output.id)
                else:
                    _LOGGER.warning("Output '%s' not found in _outputs. Available keys: %s", 
                                   x, list(self._outputs.keys())[:10])
            return outputs

        for group in self._outputs_group:
            # Create a copy to avoid modifying the cached config
            group_copy = group.copy()
            
            members = get_outputs(group_copy.pop("outputs"))
            if not members:
                _LOGGER.warning(
                    "Output group %s doesn't have any members. Omitting.", group_copy.get(ID)
                )
                continue
            
            _id = sanitize_string(group_copy.pop(ID))
            _name = group_copy.pop("name", _id)
            area = group_copy.pop("area", None)
            
            output_group = self._create_output_group(
                id=_id,
                name=_name,
                members=members,
                **group_copy,
            )
            
            # Store area on group object for later use
            output_group.area = area
            
            self._configured_output_groups[_id] = output_group
            _LOGGER.info("Created output group '%s' with %d members, area='%s'", _id, len(members), area)
            
            # Send HA autodiscovery for group (use is_group=True to use 'group' device_type)
            self._manager.send_ha_autodiscovery(
                id=_id,
                name=_name,
                ha_type=output_group.output_type,
                output_type=output_group.output_type,
                is_group=True,
                area=area,
            )
            
            # Send initial state to WebSocket
            self._manager.loop.create_task(self._delayed_send_state(output_group))

    def _create_output_group(self, id: str, name: str, members: list, **kwargs) -> Any:
        """Create an output group instance.
        
        Args:
            id: Group identifier
            name: Group display name
            members: List of BasicOutput instances to group
            **kwargs: Additional configuration
            
        Returns:
            OutputGroup instance
        """
        from boneio.components.group import OutputGroup
        
        return OutputGroup(
            message_bus=self._manager._message_bus,
            event_bus=self._manager._event_bus,
            topic_prefix=self._manager._topic_prefix,
            id=id,
            name=name,
            members=members,
            callback=lambda: None,
            **kwargs,
        )

    def _configure_relay(
        self,
        entity_id: str,
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
            self._manager._state_manager.get(attr_type=OUTPUT, attr=entity_id, default_value=False)
            if restore_state
            else False
        )
        if output_type == NONE and self._manager._state_manager.get(
            attr_type=OUTPUT, attr=entity_id
        ):
            self._manager._state_manager.del_attribute(attr_type=OUTPUT, attribute=entity_id)
            restored_state = False

        # Determine output class and expander based on kind
        output_kind = config.pop(KIND)
        
        if output_kind == MCP:
            expander_id = config.pop(MCP_ID, None)
            mcp_expander = self._mcp.get(expander_id)
            if not mcp_expander:
                _LOGGER.error("No such MCP configured: %s", expander_id)
                return None
            OutputClass = MCPOutput
            extra_args = {
                "pin": config.pop(PIN),
                "mcp": mcp_expander,
                "mcp_id": expander_id,
                "output_type": output_type,
            }
        elif output_kind == PCA:
            expander_id = config.pop(PCA_ID, None)
            pca_expander = self._pca.get(expander_id)
            if not pca_expander:
                _LOGGER.error("No such PCA configured: %s", expander_id)
                return None
            OutputClass = PWMOutput
            extra_args = {
                "pin": int(config.pop(PIN)),
                "pca": pca_expander,
                "pca_id": expander_id,
                "output_type": output_type,
            }
        elif output_kind == PCF:
            expander_id = config.pop(PCF_ID, None)
            pcf_expander = self._pcf.get(expander_id)
            if not pcf_expander:
                _LOGGER.error("No such PCF configured: %s", expander_id)
                return None
            OutputClass = PCFOutput
            extra_args = {
                "pin": int(config.pop(PIN)),
                "expander": pcf_expander,
                "expander_id": expander_id,
                "output_type": output_type,
            }
        elif output_kind == GPIO:
            expander_id = GPIO
            if GPIO not in self.grouped_outputs_by_expander:
                self.grouped_outputs_by_expander[GPIO] = {}
            OutputClass = BasicOutput
            extra_args = {
                "pin": config.pop(PIN),
            }
        else:
            _LOGGER.error("Unknown output kind: %s", output_kind)
            return None

        interlock_groups = config.get("interlock_group", [])
        if isinstance(interlock_groups, str):
            interlock_groups = [interlock_groups]

        relay = OutputClass(
            **config,
            message_bus=self._manager._message_bus,
            event_bus=self._manager._event_bus,
            topic_prefix=self._manager._topic_prefix,
            id=entity_id,
            restored_state=restored_state,
            interlock_manager=self._interlock_manager,
            interlock_groups=interlock_groups,
            name=name,
            **extra_args,
        )
        self._interlock_manager.register(relay, interlock_groups)
        self.grouped_outputs_by_expander[expander_id][entity_id] = relay
        return relay

    async def _delayed_send_state(self, output: BasicOutput) -> None:
        """Send output state after a delay."""
        await asyncio.sleep(0.5)
        await output.async_send_state()

    async def _relay_callback(self, event: Any) -> None:
        """Handle relay state change events.
        
        Saves relay state to state manager.
        
        Args:
            event: OutputEvent object containing entity_id and state (OutputState)
        """
        if not event:
            return
        
        # event is OutputEvent with entity_id and state (OutputState)
        # OutputState has 'state' field with ON/OFF value
        entity_id = getattr(event, 'entity_id', None)
        output_state = getattr(event, 'state', None)
        
        if not entity_id or not output_state:
            _LOGGER.warning("Invalid relay callback event: %s", event)
            return
        
        # Get the actual state value from OutputState
        state_value = getattr(output_state, 'state', None)
        if state_value is None:
            return
            
        # Save state to state manager
        self._manager._state_manager.save_attribute(
            attr_type=OUTPUT,
            attribute=entity_id,
            value=state_value == ON,
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
                action_from_msg = output_actions.get(message.upper())
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

    def _initialize_outputs(
        self, 
        relay_pins: list[dict], 
        reload_config: bool = False,
        preserved_states: dict[str, bool] | None = None
    ) -> None:
        """Initialize outputs (relays, switches, lights, LEDs, valves).
        
        Args:
            relay_pins: List of relay configurations
            reload_config: If True, reload configuration from file and clear existing outputs
            preserved_states: Optional dict of output_id -> is_active state to preserve during reload
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
            # Clear interlock manager to remove stale output references
            self._interlock_manager.clear()
            # Clear autodiscovery messages for outputs
            from boneio.const import LED, LIGHT, SWITCH, VALVE
            for output_type in [LIGHT, LED, SWITCH, VALVE]:
                self._manager._config_helper.clear_autodiscovery_type(ha_type=output_type)
        
        _LOGGER.debug("Initializing outputs")
        
        for _config in relay_pins:
            # Create a copy to avoid modifying the cached config
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
                _id = strip_accents(_name) if _name else None

            # Skip if we couldn't determine valid id or name
            if not _id or not _name:
                _LOGGER.warning("Skipping output with missing id or name: %s", config_copy)
                continue

            restore_state = config_copy.pop(RESTORE_STATE, False)
            area = config_copy.pop("area", None)
            
            # During reload, use preserved state instead of restore_state from config
            # This prevents outputs from switching during reload
            if preserved_states is not None and _id in preserved_states:
                effective_restore_state = preserved_states[_id]
                _LOGGER.debug(f"Using preserved state for {_id}: {effective_restore_state}")
            else:
                effective_restore_state = restore_state
            
            out = self._configure_relay(
                entity_id=_id,
                name=_name,
                config=config_copy,
                restore_state=effective_restore_state,
            )
            
            # Check if output was successfully configured
            if out is None:
                _LOGGER.warning("Skipping output '%s' - failed to configure (expander not available)", _id)
                # Add to hardware errors for WebUI display
                if not hasattr(self._manager, '_hardware_errors'):
                    self._manager._hardware_errors = []
                self._manager._hardware_errors.append({
                    'type': 'output',
                    'id': _id,
                    'name': _name,
                    'error': 'Expander not available',
                    'message': f"Output '{_id}' ({_name}) skipped - expander not initialized"
                })
                continue
            
            # Store area on output object for later use
            out.area = area
            
            # Subscribe to output state changes
            if out.output_type not in (NONE, COVER):
                self._manager._event_bus.add_event_listener(
                    event_type="output",
                    entity_id=_id,
                    listener_id=f"manager_output_{_id}",
                    target=self._relay_callback,
                )
            
            self._outputs[_id] = out
            _LOGGER.debug("Registered output: id='%s', name='%s', boneio_output='%s', area='%s'", 
                         _id, _name, _config.get("boneio_output", "N/A"), area)
            
            # Send HA autodiscovery
            if out.output_type not in (NONE, COVER):
                self._manager.send_ha_autodiscovery(
                    id=_id,
                    name=_name,
                    ha_type=out.output_type,
                    output_type=out.output_type,
                    area=area,
                )
            
            # Delayed state send
            self._manager.loop.create_task(self._delayed_send_state(out))

    async def reload_outputs(self) -> None:
        """Reload output configuration from file.
        
        This reloads outputs and output groups from the config file.
        Existing outputs are cleared and recreated based on the current config.
        
        IMPORTANT: Groups must be cleaned up BEFORE outputs are cleared,
        because groups hold references to output objects. If outputs are
        cleared first, groups will try to use stale references with closed
        I2C bus connections, causing "Bad file descriptor" errors.
        
        NOTE: Current output states are preserved during reload to avoid
        unwanted switching. The actual hardware state is maintained.
        """
        import asyncio
        
        _LOGGER.info("Reloading output configuration")
        
        # PRESERVE current output states before reload
        # This prevents outputs from switching off during reload
        current_states: dict[str, bool] = {}
        for output_id, output in self._outputs.items():
            current_states[output_id] = output.is_active
            _LOGGER.debug(f"Preserving state for {output_id}: {output.is_active}")
        
        # Get config from ConfigHelper (uses cache, reloads if needed)
        config = self._manager._config_helper.reload_config()
        
        # Get new relay pins and output groups
        relay_pins = config.get(OUTPUT, [])
        output_groups = config.get("output_group", [])
        
        # Build map of new areas from config for outputs
        new_output_areas: dict[str, str | None] = {}
        for cfg in relay_pins:
            # Determine output ID (same logic as in _initialize_outputs)
            if "id" in cfg:
                output_id = cfg["id"]
            elif "boneio_output" in cfg:
                output_id = cfg["boneio_output"]
            else:
                continue
            new_output_areas[output_id] = cfg.get("area")
        
        # Build map of new areas from config for groups
        new_group_areas: dict[str, str | None] = {}
        for cfg in output_groups:
            group_id = cfg.get("id")
            if group_id:
                new_group_areas[group_id] = cfg.get("area")
        
        # FIRST: Check for area changes and remove old HA Discovery BEFORE clearing cache
        # This must happen before _initialize_outputs clears the autodiscovery cache
        area_changed = False
        for output_id, output in self._outputs.items():
            old_area = getattr(output, 'area', None)
            new_area = new_output_areas.get(output_id)
            
            if old_area != new_area:
                area_changed = True
                _LOGGER.debug(
                    f"Output {output_id} area changed: {old_area} -> {new_area}, "
                    "removing old HA Discovery"
                )
                # Remove old HA Discovery for this output (pass old_area to find correct device identifier)
                self._remove_output_ha_discovery(output_id, old_area)
        
        # Check for area changes in groups
        for group_id, group in self._configured_output_groups.items():
            old_area = getattr(group, 'area', None)
            new_area = new_group_areas.get(group_id)
            
            if old_area != new_area:
                area_changed = True
                _LOGGER.debug(
                    f"Output group {group_id} area changed: {old_area} -> {new_area}, "
                    "removing old HA Discovery"
                )
                # Remove old HA Discovery for this group
                self._remove_group_ha_discovery(group_id)
        
        # SECOND: Cleanup existing output groups before clearing outputs
        # Groups hold references to outputs, so they must be cleaned up first
        # Also remove old HA Discovery entries (send empty payload to remove from HA)
        for group in self._configured_output_groups.values():
            try:
                group.cleanup()
                # Remove old HA Discovery for this group (handles type changes like switch->light)
                self._remove_group_ha_discovery(group.id)
            except Exception as e:
                _LOGGER.warning(f"Error cleaning up group {group.id}: {e}")
        self._configured_output_groups.clear()
        
        # Wait for HA to process the removal before sending new discovery
        if area_changed:
            _LOGGER.debug("Waiting 1s for HA to process discovery removal...")
            await asyncio.sleep(1)
        
        # THIRD: Reload outputs (this clears old outputs and sends new HA discovery)
        # Pass preserved states to maintain current output states during reload
        self._initialize_outputs(
            relay_pins=relay_pins, 
            reload_config=True,
            preserved_states=current_states
        )
        
        # FOURTH: Reload output groups with new output references
        self._outputs_group = output_groups
        self._configure_output_groups()
        
        _LOGGER.info(
            "Output reload complete: %d outputs, %d groups",
            len(self._outputs),
            len(self._configured_output_groups)
        )
        
        # Broadcast updated states to WebSocket clients
        self._broadcast_all_states()
    
    def _remove_output_ha_discovery(self, output_id: str, old_area: str | None = None) -> None:
        """Remove HA Discovery entries for an output.
        
        This sends empty payloads to all discovery topics for the output,
        which removes the entity from Home Assistant. This is needed when
        an output's area changes (different area = different device identifier).
        
        Args:
            output_id: ID of the output to remove from HA Discovery
            old_area: The previous area of the output (used to construct old device identifier)
        """
        # Construct the old device identifier based on the old area
        topic_prefix = self._manager._config_helper.topic_prefix
        if old_area:
            old_device_identifier = f"{topic_prefix}_{old_area}"
        else:
            old_device_identifier = topic_prefix  # If no area was set, it used the main device identifier
        
        # Find all autodiscovery topics for this output ID with the old device identifier
        matching_topics = self._manager._config_helper.get_autodiscovery_topics_for_id(
            output_id, old_device_identifier
        )
        
        for ha_type, topic in matching_topics:
            _LOGGER.debug(f"Removing HA Discovery for output {output_id} (old area: {old_area}): {topic}")
            # Send empty/null payload to remove from HA (HA requires zero-length retained message)
            self._manager.send_message(topic=topic, payload=None, retain=True)
            # Remove from internal cache
            self._manager._config_helper.remove_autodiscovery_msg(ha_type, topic)

    def _remove_group_ha_discovery(self, group_id: str) -> None:
        """Remove HA Discovery entries for a group.
        
        This sends empty payloads to all discovery topics for the group,
        which removes the entity from Home Assistant. This is needed when
        a group's type changes (e.g., from switch to light).
        
        Args:
            group_id: ID of the group to remove from HA Discovery
        """
        # Find all autodiscovery topics for this group ID
        matching_topics = self._manager._config_helper.get_autodiscovery_topics_for_id(group_id)
        
        for ha_type, topic in matching_topics:
            _LOGGER.debug(f"Removing HA Discovery for group {group_id}: {topic}")
            # Send empty/null payload to remove from HA (HA requires zero-length retained message)
            self._manager.send_message(topic=topic, payload=None, retain=True)
            # Remove from internal cache
            self._manager._config_helper.remove_autodiscovery_msg(ha_type, topic)

    def _broadcast_all_states(self) -> None:
        """Broadcast current state of all outputs and groups via WebSocket."""
        # Send output states
        for output in self._outputs.values():
            if output.output_type not in (NONE, COVER):
                try:
                    self._manager.loop.create_task(output.async_send_state())
                except Exception as e:
                    _LOGGER.debug(f"Error broadcasting output state {output.id}: {e}")
        
        # Send group states
        for group in self._configured_output_groups.values():
            try:
                self._manager.loop.create_task(group.async_send_state())
            except Exception as e:
                _LOGGER.debug(f"Error broadcasting group state {group.id}: {e}")

    async def send_ha_autodiscovery(self) -> None:
        """Send Home Assistant autodiscovery for all outputs and groups."""
        from boneio.const import COVER, NONE
        
        # Send autodiscovery for outputs
        for output_id, output in self._outputs.items():
            if output.output_type not in (NONE, COVER):
                self._manager.send_ha_autodiscovery(
                    id=output_id,
                    name=output.name if hasattr(output, 'name') else output_id,
                    ha_type=output.output_type,
                    output_type=output.output_type,
                    area=getattr(output, 'area', None),
                )
        
        # Send autodiscovery for groups
        for group_id, group in self._configured_output_groups.items():
            self._manager.send_ha_autodiscovery(
                id=group_id,
                name=group.name if hasattr(group, 'name') else group_id,
                ha_type=group.output_type,
                output_type=group.output_type,
                is_group=True,
            )

