"""Cover manager - handles all cover devices.

This module manages all cover devices including:
- Time-based covers
- Previous-state covers
- Venetian blinds
- Cover actions and callbacks
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from boneio.const import COVER, ID, cover_actions
from boneio.core.config.loader import configure_cover
from boneio.core.utils import strip_accents
from boneio.exceptions import CoverConfigurationException

if TYPE_CHECKING:
    from boneio.components.cover import PreviousCover, TimeBasedCover
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
        self._covers: dict[str, PreviousCover | TimeBasedCover] = {}
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
            open_relay = self._manager.outputs.get_output(_config.get("open_relay"))
            close_relay = self._manager.outputs.get_output(_config.get("close_relay"))
            
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
                
                self._covers[_id] = configure_cover(
                    message_bus=self._manager._message_bus,
                    cover_id=_id,
                    state_manager=self._manager._state_manager,
                    send_ha_autodiscovery=self._manager.send_ha_autodiscovery,
                    config={
                        **_config,
                        "open_relay": open_relay,
                        "close_relay": close_relay,
                    },
                    tilt_duration=_config.get("tilt_duration"),
                )
                
                # Send HA autodiscovery
                self._manager.send_ha_autodiscovery(
                    id=_id,
                    name=_config.get("name", _id),
                    ha_type=COVER,
                    output_type=COVER,
                )
                
            except CoverConfigurationException as err:
                _LOGGER.error("Failed to configure cover %s: %s", _id, err)

    def get_cover(self, id: str) -> PreviousCover | TimeBasedCover | None:
        """Get cover by ID.
        
        Args:
            id: Cover identifier
            
        Returns:
            Cover instance or None if not found
        """
        return self._covers.get(id)

    def get_all_covers(self) -> dict[str, PreviousCover | TimeBasedCover]:
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
        """Get all cover-related tasks.
        
        Returns:
            Dictionary of tasks
        """
        tasks = {}
        for cover_id, cover in self._covers.items():
            if hasattr(cover, 'get_tasks'):
                cover_tasks = cover.get_tasks()
                for task_name, task in cover_tasks.items():
                    tasks[f"cover_{cover_id}_{task_name}"] = task
        return tasks

    async def send_ha_autodiscovery(self) -> None:
        """Send Home Assistant autodiscovery for all covers."""
        for cover_id, cover in self._covers.items():
            self._manager.send_ha_autodiscovery(
                id=cover_id,
                name=cover.name if hasattr(cover, 'name') else cover_id,
                ha_type=COVER,
                output_type=COVER,
            )
