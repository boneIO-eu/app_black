"""Display manager - handles OLED display.

This module manages OLED display functionality.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from boneio.exceptions import GPIOInputException, I2CError

if TYPE_CHECKING:
    from boneio.core.manager import Manager

_LOGGER = logging.getLogger(__name__)


class DisplayManager:
    """Manages OLED display.
    
    This manager handles:
    - OLED display initialization
    - Screen management and configuration
    - Display updates
    - OLED button input
    
    Args:
        manager: Parent Manager instance
        oled_config: OLED configuration dictionary
    """

    def __init__(
        self,
        manager: Manager,
        oled_config: dict[str, Any],
    ):
        """Initialize display manager."""
        self._manager = manager
        self._oled = None
        self._screens = []
        self._configured_screen_order = []
        self._input_groups = []
        
        # Configure OLED if enabled
        if oled_config:
            self._configure_oled(oled_config)
        
        _LOGGER.info(
            "DisplayManager initialized with %d screens",
            len(self._screens)
        )

    def _configure_screen_order(
        self,
        screen_order: list[str],
        grouped_outputs_by_expander: dict[str, Any],
        inputs_length: int,
    ) -> list[str]:
        """Configure screen order by replacing placeholders with actual screens.
        
        Args:
            screen_order: Raw screen order from config (may contain placeholders)
            grouped_outputs_by_expander: Dictionary of output groups
            inputs_length: Number of input groups
            
        Returns:
            Configured screen order with placeholders replaced
        """
        configured_screens = screen_order.copy()
        
        # Replace "outputs" placeholder with actual output group names
        try:
            outputs_index = configured_screens.index("outputs")
            output_groups = list(grouped_outputs_by_expander.keys())
            if output_groups:
                # Remove placeholder and insert actual output groups
                configured_screens.pop(outputs_index)
                configured_screens[outputs_index:outputs_index] = output_groups
                _LOGGER.debug("Configured output screens: %s", output_groups)
            else:
                # No outputs, remove placeholder
                configured_screens.pop(outputs_index)
                _LOGGER.debug("No outputs configured, removing placeholder")
        except ValueError:
            # "outputs" not in list, skip
            pass
        
        # Replace "inputs" placeholder with actual input group names
        try:
            inputs_index = configured_screens.index("inputs")
            input_groups = [
                f"Inputs screen {i + 1}"
                for i in range(inputs_length)
            ]
            if input_groups:
                # Remove placeholder and insert actual input groups
                configured_screens.pop(inputs_index)
                configured_screens[inputs_index:inputs_index] = input_groups
                self._input_groups = input_groups
                _LOGGER.debug("Configured input screens: %s", input_groups)
            else:
                # No inputs, remove placeholder
                configured_screens.pop(inputs_index)
                _LOGGER.debug("No inputs configured, removing placeholder")
        except ValueError:
            # "inputs" not in list, skip
            self._input_groups = []
        
        _LOGGER.info("Final screen order: %s", configured_screens)
        return configured_screens

    def _configure_oled(self, oled_config: dict[str, Any]) -> None:
        """Configure OLED display.
        
        Args:
            oled_config: OLED configuration dictionary
        """
        try:
            _LOGGER.debug("Initializing OLED display")
            
            # Lazy import - OLED is optional
            from boneio.const import OLED_PIN
            from boneio.core.system import HostData
            from boneio.hardware.display import Oled
            
            self._screens = oled_config.get("screens", [])
            extra_sensors = oled_config.get("extra_screen_sensors", [])
            # Use screen_order if provided, otherwise use screens as default order
            raw_screen_order = oled_config.get("screen_order", self._screens)
            
            _LOGGER.debug("OLED config - screens: %s, raw_screen_order: %s", self._screens, raw_screen_order)
            
            host_data = HostData(
                manager=self._manager,
                event_bus=self._manager._event_bus,
                enabled_screens=self._screens,
                output=self._manager.outputs.grouped_outputs_by_expander,
                inputs=self._manager.inputs.get_all_inputs(),
                temp_sensor=(
                    self._manager.sensors.get_all_temp_sensors()[0]
                    if self._manager.sensors.get_all_temp_sensors()
                    else None
                ),
                ina219=(
                    self._manager.sensors.get_ina219_sensors()[0]
                    if self._manager.sensors.get_ina219_sensors()
                    else None
                ),
                extra_sensors=extra_sensors,
            )
            
            # Configure screen order (replace placeholders)
            self._configured_screen_order = self._configure_screen_order(
                screen_order=raw_screen_order,
                grouped_outputs_by_expander=self._manager.outputs.grouped_outputs_by_expander,
                inputs_length=host_data.inputs_length,
            )
            
            # Initialize OLED display
            from boneio.core.utils import TimePeriod
            
            self._oled = Oled(
                host_data=host_data,
                grouped_outputs_by_expander=list(self._manager.outputs.grouped_outputs_by_expander.keys()),
                sleep_timeout=oled_config.get("screensaver_timeout", TimePeriod(seconds=30)),
                screen_order=self._configured_screen_order,
                input_groups=self._input_groups,
                event_bus=self._manager._event_bus,
                i2c_bus=self._manager._i2cbusio,
            )
            
            # Configure OLED button as event input
            if OLED_PIN not in self._manager.inputs.get_all_inputs():
                from boneio.const import ID
                
                oled_button = self._manager.inputs._configure_event_sensor(
                    gpio={ID: "oled_button"},
                    pin=OLED_PIN,
                    actions={},
                )
                
                if oled_button:
                    self._manager.inputs._inputs["oled_button"] = oled_button
                    _LOGGER.info("OLED button configured on pin %s", OLED_PIN)
            
            self._oled.render_display()
            _LOGGER.info("OLED display configured successfully")
            
        except (GPIOInputException, I2CError) as err:
            _LOGGER.error("Can't configure OLED display: %s", err)
        except ImportError as err:
            _LOGGER.error("Failed to import OLED modules: %s", err)
        except Exception as err:
            _LOGGER.error("Unexpected error configuring OLED: %s", err)

    def get_oled(self) -> Any | None:
        """Get OLED display instance.
        
        Returns:
            Oled instance or None
        """
        return self._oled

    def get_screens(self) -> list[str]:
        """Get list of enabled screens.
        
        Returns:
            List of screen names
        """
        return self._screens
    
    def get_configured_screen_order(self) -> list[str]:
        """Get configured screen order (with placeholders replaced).
        
        Returns:
            List of configured screen names
        """
        return self._configured_screen_order
    
    def get_input_groups(self) -> list[str]:
        """Get list of input group screens.
        
        Returns:
            List of input group names
        """
        return self._input_groups

    async def send_ha_autodiscovery(self) -> None:
        """Send Home Assistant autodiscovery for OLED entities."""
        # OLED typically doesn't have HA entities
        # But OLED button is handled by InputManager
        pass
