"""ESPHome binary sensor input — remote input via ESPHome native API.

Thin subclass of :class:`RemoteInputBase` that adds ESPHome-specific fields
(``device_id``, ``sensor_id``) and implements the ``on_remote_state_change``
callback invoked by :class:`ESPHomeRemoteDevice`.
"""

from __future__ import annotations

import logging

from boneio.components.input.remote.base import RemoteInputBase
from boneio.core.events import EventBus

_LOGGER = logging.getLogger(__name__)


class ESPHomeBinarySensorInput(RemoteInputBase):
    """Virtual binary sensor / event button backed by an ESPHome remote device.

    Receives state updates via the ESPHome native API callback registered
    on :class:`ESPHomeRemoteDevice`.

    Args:
        device_id: ID of the remote ESPHome device (from ``remote_devices``).
        sensor_id: ``object_id`` of the binary sensor on the ESPHome device.
        **kwargs: Forwarded to :class:`RemoteInputBase`.
    """

    def __init__(
        self,
        *,
        device_id: str,
        sensor_id: str,
        id: str,
        name: str,
        event_bus: EventBus,
        actions: dict,
        **kwargs,
    ) -> None:
        self._device_id = device_id
        self._sensor_id = sensor_id

        # Build virtual pin identifier for this ESPHome sensor.
        pin = f"esphome:{device_id}:{sensor_id}"

        super().__init__(
            id=id,
            name=name,
            pin=pin,
            event_bus=event_bus,
            actions=actions,
            **kwargs,
        )

        _LOGGER.debug(
            "Created ESPHome binary sensor input %s (mode=%s, device=%s, sensor=%s)",
            id, self._mode, device_id, sensor_id,
        )

    # ------------------------------------------------------------------
    # Remote state change callback — called by ESPHomeRemoteDevice
    # ------------------------------------------------------------------

    def on_remote_state_change(self, new_state: bool) -> None:
        """Handle state change from the remote ESPHome binary sensor.

        Called by :class:`ESPHomeRemoteDevice` when the binary sensor state
        changes on the remote device.

        Args:
            new_state: ``True`` if the sensor is now active/on.
        """
        if self._inverted:
            new_state = not new_state

        if self._mode == "event":
            self._feed_detector(is_pressed=new_state)
        else:
            self._handle_binary_state_change(new_state)

    # ------------------------------------------------------------------
    # ESPHome-specific properties
    # ------------------------------------------------------------------

    @property
    def device_id(self) -> str:
        """ID of the backing ESPHome remote device."""
        return self._device_id

    @property
    def sensor_id(self) -> str:
        """``object_id`` of the binary sensor on the ESPHome device."""
        return self._sensor_id
