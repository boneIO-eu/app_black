"""Cover manager - handles all cover devices.

This module manages all cover devices including:
- Time-based covers
- Venetian blinds
- Cover actions and callbacks
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

from boneio.const import COVER, DEVICE_CLASS, ID, NAME, RESTORE_STATE, SHOW_HA, cover_actions, filter_cover_extra_data
from boneio.core.utils import TimePeriod, ensure_time_period, strip_accents
from boneio.exceptions import CoverConfigurationException
from boneio.integration import ha_cover_availabilty_message
from boneio.integration.homeassistant import ha_cover_with_tilt_availabilty_message

if TYPE_CHECKING:
    from boneio.components.cover import TimeBasedCover, VenetianCover
    from boneio.core.manager import Manager

_LOGGER = logging.getLogger(__name__)


class CoverManager:
    """Manages all covers (time-based, venetian).

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
        self._covers: dict[str, TimeBasedCover | VenetianCover] = {}
        self._config_covers = cover_config

        # Configure covers if outputs exist
        if self._manager.outputs.get_all_outputs():
            self._configure_covers()

        _LOGGER.info("CoverManager initialized with %d covers", len(self._covers))

    def _configure_covers(self, reload_config: bool = False) -> None:
        """Configure covers.

        Args:
            reload_config: If True, reload configuration from file
        """
        # Reload configuration if requested
        if reload_config:
            # Get config from ConfigHelper (already reloaded by Manager)
            config = self._manager._config_helper.get_config()
            self._config_covers = config.get(COVER, [])
            self._manager._config_helper.clear_autodiscovery_type(ha_type=COVER)

            # Remove covers that are no longer in config
            new_ids = set()
            for _cfg in self._config_covers:
                if _cfg.get(ID):
                    new_ids.add(strip_accents(_cfg[ID]))
                else:
                    _open = str(_cfg.get("open_relay", ""))
                    _close = str(_cfg.get("close_relay", ""))
                    new_ids.add(f"cover_{_open}_{_close}".lower().replace(" ", "_"))

            removed_ids = [cid for cid in self._covers if cid not in new_ids]
            for cid in removed_ids:
                _LOGGER.info("Cover %s removed from config, cleaning up", cid)
                cover = self._covers.pop(cid)
                # Stop cover movement if running (synchronous - no running loop guaranteed)
                try:
                    if hasattr(cover, "_stop_event"):
                        cover._stop_event.set()
                    if (
                        hasattr(cover, "_movement_thread")
                        and cover._movement_thread
                        and cover._movement_thread.is_alive()
                    ):
                        cover._movement_thread.join(timeout=1.0)
                    if hasattr(cover, "_open_relay"):
                        cover._open_relay.turn_off()
                    if hasattr(cover, "_close_relay"):
                        cover._close_relay.turn_off()
                except Exception:
                    pass
                # Remove HA autodiscovery
                self._remove_cover_ha_discovery(cid)

        for _config in self._config_covers:
            # Get relay outputs for cover
            open_relay_id = str(_config.get("open_relay", ""))
            close_relay_id = str(_config.get("close_relay", ""))

            open_relay = self._manager.outputs.get_output(open_relay_id)
            close_relay = self._manager.outputs.get_output(close_relay_id)

            # Generate ID from relays if not provided
            if _config.get(ID):
                _id = strip_accents(_config[ID])
            else:
                # Auto-generate ID from open_relay and close_relay
                _id = f"cover_{open_relay_id}_{close_relay_id}".lower().replace(" ", "_")

            # Get display name (falls back to ID)
            _name = _config.get(NAME) or _id

            if not open_relay:
                _LOGGER.error("Can't configure cover %s. Open relay doesn't exist.", _id)
                continue

            if not close_relay:
                _LOGGER.error("Can't configure cover %s. Close relay doesn't exist.", _id)
                continue

            try:
                # Update existing cover or create new one
                if _id in self._covers:
                    _cover = self._covers[_id]
                    new_platform = _config.get("platform", "time_based")

                    # Check if platform (cover type) changed - need to recreate cover
                    current_kind = _cover.kind
                    new_kind = "venetian" if new_platform == "venetian" else "time"

                    if current_kind != new_kind:
                        # Platform changed - remove old cover and create new one
                        _LOGGER.info(
                            "Cover %s platform changed from %s to %s, recreating cover", _id, current_kind, new_kind
                        )
                        # Remove old HA autodiscovery
                        self._remove_cover_ha_discovery(_id)
                        # Remove old cover from dict (will be recreated below)
                        del self._covers[_id]
                    else:
                        # Same platform - update name, relays, times and autodiscovery
                        _new_name = _config.get(NAME) or _id
                        if _cover._name != _new_name:
                            _LOGGER.info("Cover %s name changed: '%s' -> '%s'", _id, _cover._name, _new_name)
                            _cover._name = _new_name
                        old_open = getattr(_cover._open_relay, "id", None)
                        old_close = getattr(_cover._close_relay, "id", None)
                        if old_open != open_relay_id or old_close != close_relay_id:
                            _LOGGER.info(
                                "Cover %s relays changed: open %s->%s, close %s->%s",
                                _id,
                                old_open,
                                open_relay_id,
                                old_close,
                                close_relay_id,
                            )
                        _cover._open_relay = open_relay
                        _cover._close_relay = close_relay
                        _cover.update_config_times(_config)
                        # Re-send HA autodiscovery with potentially new name/area
                        if _config.get(SHOW_HA, True):
                            # Remove old autodiscovery first (in case area changed)
                            self._remove_cover_ha_discovery(_id)
                            # Send new autodiscovery
                            if new_platform == "venetian":
                                availability_msg_func = ha_cover_with_tilt_availabilty_message
                            else:
                                availability_msg_func = ha_cover_availabilty_message
                            payload = availability_msg_func(
                                id=_cover.id,
                                name=_cover.name,
                                config_helper=self._manager._config_helper,
                                device_class=_config.get(DEVICE_CLASS),
                                area=_config.get("area"),
                            )
                            self._manager.publish_ha_discovery(
                                id=_cover.id,
                                ha_type=COVER,
                                payload=payload,
                            )
                        continue

                self._covers[_id] = self._configure_cover(
                    cover_id=_id,
                    cover_name=_name,
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
        cover_name: str,
        config: dict,
        tilt_duration: TimePeriod | None,
    ) -> TimeBasedCover | VenetianCover:
        """Configure a cover instance.

        Args:
            cover_id: Cover identifier (technical ID for MQTT topics)
            cover_name: Display name for Home Assistant
            config: Cover configuration dictionary
            tilt_duration: Tilt duration for venetian covers

        Returns:
            Configured cover instance

        Raises:
            CoverConfigurationException: If cover configuration is invalid
        """
        from boneio.components.cover import TimeBasedCover, VenetianCover

        platform = config.get("platform", "time_based")

        # Normalize time period fields — during hot-reload YAML values may
        # arrive as raw strings (e.g. "5s") instead of TimePeriod objects.
        for time_key in ("open_time", "close_time", "actuator_activation_duration"):
            if time_key in config and config[time_key] is not None:
                config[time_key] = ensure_time_period(config[time_key])
        if tilt_duration is not None and not isinstance(tilt_duration, TimePeriod):
            tilt_duration = ensure_time_period(tilt_duration)

        def state_save(value: dict[str, float]):
            if config[RESTORE_STATE]:
                self._manager._state_manager.save_attribute(
                    attr_type=COVER,
                    attribute=cover_id,
                    value=value,
                )

        if platform == "venetian":
            if not tilt_duration:
                raise CoverConfigurationException("Tilt duration must be configured for tilt cover.")
            _LOGGER.debug("Configuring tilt cover %s", cover_id)
            restored_state = self._manager._state_manager.get(
                attr_type=COVER, attr=cover_id, default_value={"position": 100, "tilt": 100}
            )
            if isinstance(restored_state, str):
                try:
                    restored_state = json.loads(restored_state)
                except (json.JSONDecodeError, TypeError):
                    _LOGGER.warning(
                        "Cover %s: corrupted saved state '%s', resetting to default",
                        cover_id,
                        restored_state,
                    )
                    restored_state = {"position": 100, "tilt": 100}
            if isinstance(restored_state, (float, int)):
                restored_state = {"position": restored_state, "tilt": 100}
            cover = VenetianCover(
                id=cover_id,
                name=cover_name,
                state_save=state_save,
                message_bus=self._manager._message_bus,
                event_bus=self._manager._event_bus,
                topic_prefix=self._manager._topic_prefix,
                restored_state=restored_state,
                tilt_duration=tilt_duration,
                actuator_activation_duration=config.get("actuator_activation_duration", TimePeriod(milliseconds=0)),
                **{
                    k: v
                    for k, v in config.items()
                    if k
                    not in (
                        "id",
                        "platform",
                        "actuator_activation_duration",
                        "tilt_duration",
                        RESTORE_STATE,
                        SHOW_HA,
                        DEVICE_CLASS,
                        NAME,
                    )
                },
            )
            availability_msg_func = ha_cover_with_tilt_availabilty_message
        elif platform == "time_based":
            _LOGGER.debug("Configuring time-based cover %s", cover_id)
            restored_state = self._manager._state_manager.get(
                attr_type=COVER, attr=cover_id, default_value={"position": 100}
            )
            if isinstance(restored_state, str):
                try:
                    restored_state = json.loads(restored_state)
                except (json.JSONDecodeError, TypeError):
                    _LOGGER.warning(
                        "Cover %s: corrupted saved state '%s', resetting to default",
                        cover_id,
                        restored_state,
                    )
                    restored_state = {"position": 100}
            if isinstance(restored_state, (float, int)):
                restored_state = {"position": restored_state}
            cover = TimeBasedCover(
                id=cover_id,
                name=cover_name,
                state_save=state_save,
                message_bus=self._manager._message_bus,
                event_bus=self._manager._event_bus,
                topic_prefix=self._manager._topic_prefix,
                restored_state=restored_state,
                **{
                    k: v
                    for k, v in config.items()
                    if k not in ("id", "platform", RESTORE_STATE, SHOW_HA, DEVICE_CLASS, NAME)
                },
            )
            availability_msg_func = ha_cover_availabilty_message
        else:
            _LOGGER.warning("Unknown cover platform '%s' for %s, falling back to time_based", platform, cover_id)
            restored_state = self._manager._state_manager.get(
                attr_type=COVER, attr=cover_id, default_value={"position": 100}
            )
            if isinstance(restored_state, str):
                try:
                    restored_state = json.loads(restored_state)
                except (json.JSONDecodeError, TypeError):
                    _LOGGER.warning(
                        "Cover %s: corrupted saved state '%s', resetting to default",
                        cover_id,
                        restored_state,
                    )
                    restored_state = {"position": 100}
            if isinstance(restored_state, (float, int)):
                restored_state = {"position": restored_state}
            cover = TimeBasedCover(
                id=cover_id,
                name=cover_name,
                state_save=state_save,
                message_bus=self._manager._message_bus,
                event_bus=self._manager._event_bus,
                topic_prefix=self._manager._topic_prefix,
                restored_state=restored_state,
                **{
                    k: v
                    for k, v in config.items()
                    if k not in ("id", "platform", RESTORE_STATE, SHOW_HA, DEVICE_CLASS, NAME)
                },
            )
            availability_msg_func = ha_cover_availabilty_message

        # Send HA autodiscovery
        if config.get(SHOW_HA, True):
            payload = availability_msg_func(
                id=cover.id,
                name=cover.name,
                config_helper=self._manager._config_helper,
                device_class=config.get(DEVICE_CLASS),
                area=config.get("area"),
            )
            self._manager.publish_ha_discovery(
                id=cover.id,
                ha_type=COVER,
                payload=payload,
            )

        _LOGGER.debug("Configured cover %s", cover_id)
        return cover

    def _remove_cover_ha_discovery(self, cover_id: str) -> None:
        """Remove HA Discovery entries for a cover.

        This sends empty payloads to all discovery topics for the cover,
        which removes the entity from Home Assistant. This is needed when
        a cover's area changes.

        Args:
            cover_id: ID of the cover to remove from HA Discovery
        """
        # Find all autodiscovery topics for this cover ID
        matching_topics = self._manager._config_helper.get_autodiscovery_topics_for_id(cover_id)

        for ha_type, topic in matching_topics:
            _LOGGER.debug("Removing HA Discovery for cover %s: %s", cover_id, topic)
            # Send empty/null payload to remove from HA (HA requires zero-length retained message)
            self._manager.send_message(topic=topic, payload=None, retain=True)
            # Remove from internal cache
            self._manager._config_helper.remove_autodiscovery_msg(ha_type, topic)

    def get_cover(self, id: str) -> TimeBasedCover | VenetianCover | None:
        """Get cover by ID.

        Args:
            id: Cover identifier

        Returns:
            Cover instance or None if not found
        """
        return self._covers.get(id)

    def get_all_covers(self) -> dict[str, TimeBasedCover | VenetianCover]:
        """Get all covers.

        Returns:
            Dictionary of all covers
        """
        return self._covers

    def reload_covers(self) -> None:
        """Reload cover configuration from file.

        This updates cover timings and creates new covers if needed.
        After reload, broadcasts all cover states to WebSocket clients.
        """
        _LOGGER.info("Reloading cover configuration")
        self._configure_covers(reload_config=True)

        # Broadcast updated states to WebSocket clients
        self._broadcast_all_states()

    async def handle_cover_action(self, cover_id: str, action: str, extra_data: dict[str, Any] | None = None) -> None:
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
            # Filter extra_data to only pass params accepted by the action
            filtered = filter_cover_extra_data(action_to_execute, extra_data or {})
            if filtered:
                await _f(**filtered)
            else:
                await _f()
        except Exception as err:
            _LOGGER.error("Error executing cover action %s on %s: %s", action, cover_id, err)

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

    def _broadcast_all_states(self) -> None:
        """Broadcast current state of all covers via WebSocket.

        This is called after reload to ensure frontend receives
        the state of all covers, including newly created ones.
        """
        for cover in self._covers.values():
            try:
                cover.send_state(cover.state, cover.json_position)
            except Exception as e:
                _LOGGER.debug("Error broadcasting cover state %s: %s", cover.id, e)

    async def send_ha_autodiscovery(self) -> None:
        """Send Home Assistant autodiscovery for all covers."""
        for cover_id, cover in self._covers.items():
            # Use tilt variant if cover supports tilt
            if hasattr(cover, "tilt_position"):
                msg_func = ha_cover_with_tilt_availabilty_message
            else:
                msg_func = ha_cover_availabilty_message
            payload = msg_func(
                id=cover_id,
                name=cover.name if hasattr(cover, "name") else cover_id,
                config_helper=self._manager._config_helper,
                device_class=getattr(cover, "device_class", None),
                area=getattr(cover, "area", None),
            )
            self._manager.publish_ha_discovery(
                id=cover_id,
                ha_type=COVER,
                payload=payload,
            )
