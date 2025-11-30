"""Cover manager - handles all cover devices.

This module manages all cover devices including:
- Time-based covers
- Previous-state covers
- Venetian blinds
- Cover actions and callbacks
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

from boneio.const import COVER, DEVICE_CLASS, ID, RESTORE_STATE, SHOW_HA, cover_actions
from boneio.core.utils import TimePeriod, strip_accents
from boneio.exceptions import CoverConfigurationException
from boneio.integration import ha_cover_availabilty_message
from boneio.integration.homeassistant import ha_cover_with_tilt_availabilty_message

if TYPE_CHECKING:
    from boneio.components.cover import PreviousCover, TimeBasedCover, VenetianCover
    from boneio.core.manager import Manager

_LOGGER = logging.getLogger(__name__)


class CoverManager:
    """Manages all covers (time-based, previous-state, venetian).
    
    This manager handles:
    - Cover configuration and initialization
    - Cover state management
    - Cover actions (open, close, stop, position)
    - Dynamic cover reconfiguration
    - Home Assistant autodiscovery
    
    Args:
        manager: Parent Manager instance
        cover_config: List of cover configurations
    """

    def __init__(
        self,
        manager: Manager,
        cover_config: list[dict],
    ):
        """Initialize cover manager."""
        self._manager = manager
        self._covers: dict[str, PreviousCover | TimeBasedCover | VenetianCover] = {}
        self._config_covers = cover_config
        
        # Configure covers if outputs exist
        if self._manager.outputs.get_all_outputs():
            self._configure_covers()
        
        _LOGGER.info(
            "CoverManager initialized with %d covers",
            len(self._covers)
        )

    def _configure_covers(self, reload_config: bool = False) -> None:
        """Configure covers.
        
        Args:
            reload_config: If True, reload configuration from file
        """
        # Reload configuration if requested
        if reload_config:
            # Get config from ConfigHelper (uses cache, reloads if needed)
            config = self._manager._config_helper.reload_config()
            self._config_covers = config.get(COVER, [])
            self._manager._config_helper.clear_autodiscovery_type(ha_type=COVER)
        
        for _config in self._config_covers:
            _id = strip_accents(_config[ID])
            
            # Get relay outputs for cover
            open_relay = self._manager.outputs.get_output(str(_config.get("open_relay")))
            close_relay = self._manager.outputs.get_output(str(_config.get("close_relay")))
            
            if not open_relay:
                _LOGGER.error(
                    "Can't configure cover %s. Open relay doesn't exist.",
                    _id
                )
                continue
            
            if not close_relay:
                _LOGGER.error(
                    "Can't configure cover %s. Close relay doesn't exist.",
                    _id
                )
                continue
            
            try:
                # Update existing cover or create new one
                if _id in self._covers:
                    _cover = self._covers[_id]
                    _cover.update_config_times(_config)
                    continue
                
                self._covers[_id] = self._configure_cover(
                    cover_id=_id,
                    config={
                        **_config,
                        "open_relay": open_relay,
                        "close_relay": close_relay,
                    },
                    tilt_duration=_config.get("tilt_duration"),
                )
                
            except CoverConfigurationException as err:
                _LOGGER.error("Failed to configure cover %s: %s", _id, err)

    def _configure_cover(
        self,
        cover_id: str,
        config: dict,
        tilt_duration: TimePeriod | None,
    ) -> PreviousCover | TimeBasedCover | VenetianCover:
        """Configure a cover instance.
        
        Args:
            cover_id: Cover identifier
            config: Cover configuration dictionary
            tilt_duration: Tilt duration for venetian covers
            
        Returns:
            Configured cover instance
            
        Raises:
            CoverConfigurationException: If cover configuration is invalid
        """
        from boneio.components.cover import PreviousCover, TimeBasedCover, VenetianCover
        
        platform = config.get("platform", "previous")
        
        def state_save(value: dict[str, int]):
            if config[RESTORE_STATE]:
                self._manager._state_manager.save_attribute(
                    attr_type=COVER,
                    attribute=cover_id,
                    value=json.dumps(value),
                )
        
        if platform == "venetian":
            if not tilt_duration:
                raise CoverConfigurationException("Tilt duration must be configured for tilt cover.")
            _LOGGER.debug("Configuring tilt cover %s", cover_id)
            restored_state = self._manager._state_manager.get(
                attr_type=COVER, attr=cover_id, default_value={"position": 100, "tilt_position": 100}
            )
            if isinstance(restored_state, (float, int)):
                restored_state = {"position": restored_state, "tilt_position": 100}
            cover = VenetianCover(
                id=cover_id,
                state_save=state_save,
                message_bus=self._manager._message_bus,
                restored_state=restored_state,
                tilt_duration=tilt_duration,
                actuator_activation_duration=config.get("actuator_activation_duration", TimePeriod(milliseconds=0)),
                **{k: v for k, v in config.items() if k not in ("platform", "actuator_activation_duration", RESTORE_STATE, SHOW_HA, DEVICE_CLASS)},
            )
            availability_msg_func = ha_cover_with_tilt_availabilty_message
        elif platform == "time_based":
            _LOGGER.debug("Configuring time-based cover %s", cover_id)
            restored_state = self._manager._state_manager.get(
                attr_type=COVER, attr=cover_id, default_value={"position": 100}
            )
            if isinstance(restored_state, (float, int)):
                restored_state = {"position": restored_state}
            cover = TimeBasedCover(
                id=cover_id,
                state_save=state_save,
                message_bus=self._manager._message_bus,
                restored_state=restored_state,
                **{k: v for k, v in config.items() if k not in ("platform", RESTORE_STATE, SHOW_HA, DEVICE_CLASS)},
            )
            availability_msg_func = ha_cover_availabilty_message
        else:
            _LOGGER.debug("Configuring previous cover %s", cover_id)
            restored_state = self._manager._state_manager.get(
                attr_type=COVER, attr=cover_id, default_value={"position": 100}
            )
            if isinstance(restored_state, (float, int)):
                restored_state = {"position": restored_state}
            cover = PreviousCover(
                id=cover_id,
                state_save=state_save,
                message_bus=self._manager._message_bus,
                restored_state=restored_state,
                **{k: v for k, v in config.items() if k not in ("platform", RESTORE_STATE, SHOW_HA, DEVICE_CLASS)},
            )
            availability_msg_func = ha_cover_availabilty_message
        
        # Send HA autodiscovery
        if config.get(SHOW_HA, True):
            self._manager.send_ha_autodiscovery(
                id=cover.id,
                name=cover.name,
                ha_type=COVER,
                device_class=config.get(DEVICE_CLASS),
                availability_msg_func=availability_msg_func,
            )
        
        _LOGGER.debug("Configured cover %s", cover_id)
        return cover

    def get_cover(self, id: str) -> PreviousCover | TimeBasedCover | VenetianCover | None:
        """Get cover by ID.
        
        Args:
            id: Cover identifier
            
        Returns:
            Cover instance or None if not found
        """
        return self._covers.get(id)

    def get_all_covers(self) -> dict[str, PreviousCover | TimeBasedCover | VenetianCover]:
        """Get all covers.
        
        Returns:
            Dictionary of all covers
        """
        return self._covers

    def reload_covers(self) -> None:
        """Reload cover configuration from file.
        
        This updates cover timings without recreating covers.
        """
        _LOGGER.info("Reloading cover configuration")
        self._configure_covers(reload_config=True)

    async def handle_cover_action(
        self,
        cover_id: str,
        action: str,
        extra_data: dict[str, Any] | None = None
    ) -> None:
        """Handle cover action.
        
        Args:
            cover_id: Cover identifier
            action: Action to execute (open, close, stop, set_position)
            extra_data: Optional extra data (e.g., position value)
        """
        cover = self._covers.get(cover_id)
        if not cover:
            _LOGGER.warning("Cover %s not found for action", cover_id)
            return
        
        action_to_execute = cover_actions.get(action)
        if not action_to_execute:
            _LOGGER.warning("Unknown cover action: %s", action)
            return
        
        try:
            _f = getattr(cover, action_to_execute)
            if extra_data:
                await _f(**extra_data)
            else:
                await _f()
        except Exception as err:
            _LOGGER.error(
                "Error executing cover action %s on %s: %s",
                action,
                cover_id,
                err
            )

    def handle_cover_command(self, device_id: str, command: str, message: str) -> None:
        """Handle MQTT cover command.
        
        Args:
            device_id: Cover identifier
            command: Command type ('set')
            message: Command payload
        """
        cover = self._covers.get(device_id)
        if not cover:
            return
        
        if command == "set":
            action_from_msg = cover_actions.get(message.upper())
            if action_from_msg:
                _f = getattr(cover, action_from_msg)
                self._manager.loop.create_task(_f())
            else:
                _LOGGER.debug("Unknown cover action %s for device %s", message, device_id)

    def get_tasks(self) -> dict[str, asyncio.Task]:
        """Get all cover-related tasks. Currently not used.
        
        Returns:
            Dictionary of tasks
        """
        return {}

    async def send_ha_autodiscovery(self) -> None:
        """Send Home Assistant autodiscovery for all covers."""
        for cover_id, cover in self._covers.items():
            self._manager.send_ha_autodiscovery(
                id=cover_id,
                name=cover.name if hasattr(cover, 'name') else cover_id,
                ha_type=COVER,
                output_type=COVER,
            )
