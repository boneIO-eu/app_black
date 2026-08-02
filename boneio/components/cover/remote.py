"""Remote cover output for covers on remote devices (ESPHome API).

``RemoteCoverOutput`` provides a duck-type compatible interface with
:class:`TimeBasedCover` / :class:`VenetianCover` so that the conditions
system (``is_open`` / ``is_closed``), ``CoverManager.get_cover()``,
and WebSocket event emission work transparently with remote covers.

The actual hardware control is delegated to the parent
``ESPHomeDeviceManager`` via ``control_cover()``.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from boneio.const import CLOSED, CLOSING, COVER, IDLE, OPEN, OPENING
from boneio.core.events import EventBus
from boneio.models import CoverState
from boneio.models.events import CoverEvent

if TYPE_CHECKING:
    from boneio.core.messaging import MessageBus

_LOGGER = logging.getLogger(__name__)


class RemoteCoverOutput:
    """Remote cover from ESPHome — duck-type compatible with local Cover.

    Provides the same public interface that the condition evaluators and
    the ``CoverManager`` expect:

    - ``is_open`` / ``is_closed`` property for action conditions
    - ``state`` / ``position`` / ``tilt`` for state reporting
    - ``on_remote_state_change()`` callback from ESPHome subscription
    - ``CoverEvent`` emission on EventBus for WebSocket clients

    Args:
        id: Entity identifier (usually ``{device_id}_{cover_id}``).
        name: Human-readable display name.
        device_id: ID of the remote device hosting this cover.
        cover_id: Entity object_id on the remote device.
        remote_source: Transport protocol (``esphome_api``).
        event_bus: Central event bus for emitting ``CoverEvent`` objects.
        kind: Cover device class (``blind``, ``shutter``, ``gate``, etc.).
        show_in_ha: Whether to publish HA autodiscovery.
        area: Optional HA area assignment.
    """

    # Duck-type compatibility with local covers
    is_remote: bool = True

    def __init__(
        self,
        *,
        id: str,
        name: str,
        device_id: str,
        cover_id: str,
        remote_source: str,
        event_bus: EventBus,
        message_bus: MessageBus | None = None,
        topic_prefix: str = "",
        kind: str = "cover",
        show_in_ha: bool = False,
        area: str | None = None,
    ) -> None:
        self._id = id
        self._name = name
        self._device_id = device_id
        self._cover_id = cover_id
        self._remote_source = remote_source
        self._event_bus = event_bus
        self._message_bus: MessageBus | None = message_bus
        self._send_topic = f"{topic_prefix}/{COVER}/{id}" if topic_prefix else ""
        self._kind = kind
        self.show_in_ha = show_in_ha
        self.area: str | None = area

        # State tracking
        self._position: int = 0  # 0=closed, 100=open
        self._tilt: int = 0
        self._current_operation: str = IDLE
        self._last_timestamp: float = 0.0
        self._available: bool = False

        # Reference to remote device manager — set by registration.
        self._device_manager: Any = None
        self._remote_devices_ref: Any = None

    # ------------------------------------------------------------------
    # Public properties (duck-type compatible with TimeBasedCover)
    # ------------------------------------------------------------------

    @property
    def id(self) -> str:
        """Entity identifier."""
        return self._id

    @property
    def name(self) -> str:
        """Human-readable name."""
        return self._name

    @property
    def kind(self) -> str:
        """Cover device class (blind, shutter, gate, etc.)."""
        return self._kind

    @property
    def state(self) -> str:
        """Current state as string (open/closed/opening/closing)."""
        if self._current_operation == OPENING:
            return OPENING
        elif self._current_operation == CLOSING:
            return CLOSING
        else:
            return CLOSED if self._position == 0 else OPEN

    @property
    def is_open(self) -> bool:
        """True when cover position > 0 (not fully closed)."""
        return self._position > 0

    @property
    def is_closed(self) -> bool:
        """True when cover is fully closed (position == 0)."""
        return self._position == 0

    @property
    def position(self) -> int:
        """Current cover position (0-100)."""
        return self._position

    @property
    def tilt(self) -> int:
        """Current tilt position (0-100)."""
        return self._tilt

    @property
    def current_operation(self) -> str:
        """Current operation (idle/opening/closing)."""
        return self._current_operation

    @property
    def last_timestamp(self) -> float:
        """Timestamp of last state update."""
        return self._last_timestamp

    # ------------------------------------------------------------------
    # Remote state callback
    # ------------------------------------------------------------------

    def on_remote_state_change(self, state_dict: dict[str, Any]) -> None:
        """Called by ESPHome device manager when cover state changes.

        Args:
            state_dict: Cover state from ESPHome containing:
                - position: float (0.0-1.0)
                - tilt: float | None
                - current_operation: int (0=IDLE, 1=OPENING, 2=CLOSING)
        """
        position_raw = state_dict.get("position")
        if position_raw is not None:
            self._position = round(float(position_raw) * 100)

        tilt_raw = state_dict.get("tilt")
        if tilt_raw is not None:
            self._tilt = round(float(tilt_raw) * 100)

        current_op_int = state_dict.get("current_operation", 0)
        if current_op_int == 1:
            self._current_operation = OPENING
        elif current_op_int == 2:
            self._current_operation = CLOSING
        else:
            self._current_operation = IDLE

        self._last_timestamp = time.time()
        self._available = True

        _LOGGER.debug(
            "Remote cover '%s' state: position=%d%%, tilt=%d%%, operation=%s",
            self._id,
            self._position,
            self._tilt,
            self._current_operation,
        )

        # Emit CoverEvent for WebSocket clients
        self._emit_cover_event()

    def _emit_cover_event(self) -> None:
        """Emit a CoverEvent on the event bus."""
        event = CoverState(
            id=self._id,
            name=self._name,
            state=self.state,
            kind=self._kind,
            timestamp=self._last_timestamp,
            current_operation=self._current_operation,
            position=self._position,
            tilt=self._tilt,
        )
        self._event_bus.trigger_event(CoverEvent(entity_id=self._id, state=event))

    # ------------------------------------------------------------------
    # Device manager resolution (lazy — same pattern as RemoteOutputBase)
    # ------------------------------------------------------------------

    def _resolve_device_manager(self) -> bool:
        """Try to resolve device manager lazily from remote_devices reference.

        Returns:
            ``True`` if device manager is now available.
        """
        if self._device_manager is not None:
            return True
        if self._remote_devices_ref is None:
            return False
        device = self._remote_devices_ref.get_device(self._device_id)
        if device is not None:
            self._device_manager = device
            self._remote_devices_ref = None
            self._register_state_callback()
            _LOGGER.info(
                "Lazily resolved device manager for remote cover '%s' (device '%s')",
                self._id,
                self._device_id,
            )
            return True
        return False

    def _register_state_callback(self) -> None:
        """Register a cover state change callback on the device manager.

        Called after device manager is resolved (lazy or immediate).
        ESPHome devices will call back on cover state changes.
        Also syncs current state from the device if available.
        """
        if self._device_manager is None:
            return
        register_fn = getattr(self._device_manager, "register_cover_callback", None)
        if register_fn is not None:
            register_fn(self._cover_id, self.on_remote_state_change)
            _LOGGER.debug(
                "Registered cover callback for remote cover '%s' on device '%s'",
                self._id,
                self._device_id,
            )

        # Sync initial state from device's current known states
        self._sync_initial_state()

    def _sync_initial_state(self) -> None:
        """Sync initial state from ESPHome device's cached cover states."""
        if self._device_manager is None:
            return

        cover_states: dict[str, dict[str, Any]] = getattr(
            self._device_manager, "_cover_states", {}
        )
        if self._cover_id in cover_states:
            self.on_remote_state_change(cover_states[self._cover_id])
            _LOGGER.debug(
                "Synced initial cover state for '%s': position=%d%%",
                self._id,
                self._position,
            )

    def __repr__(self) -> str:
        return (
            f"RemoteCoverOutput(id={self._id!r}, device={self._device_id!r}, "
            f"cover={self._cover_id!r}, position={self._position})"
        )
