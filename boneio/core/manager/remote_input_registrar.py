"""Remote input registrar — registers remote inputs into InputManager.

This module handles the creation and lifecycle of remote input instances
(ESPHome binary sensors, future CAN/MQTT inputs) and registers them
into the shared ``InputManager._inputs`` dictionary.

Responsibilities:
- Parse ``remote_inputs`` config entries
- Create :class:`ESPHomeBinarySensorInput` instances
- Register device callbacks (e.g. ESPHome state subscriptions)
- Unregister (cleanup) all remote inputs before reload

.. note::
    The actual input dict (``_inputs``) lives in :class:`InputManager`.
    This helper only creates and destroys entries — it does not own the
    registry.  HA autodiscovery is delegated back to ``InputManager``
    via a callback.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from boneio.components.input import (
    ESPHomeBinarySensorInput,
    RemoteInputBase,
)
from boneio.const import EVENT_ENTITY

if TYPE_CHECKING:
    from boneio.core.manager import Manager

_LOGGER = logging.getLogger(__name__)


class RemoteInputRegistrar:
    """Creates and manages remote input instances.

    This helper is owned by :class:`InputManager` and operates on
    the shared ``_inputs`` dictionary.  It is intentionally **not**
    a full manager — it delegates action parsing, event routing and
    state broadcasting to ``InputManager`` / ``Manager``.

    Args:
        manager: Top-level :class:`Manager` (used for action parsing).
        ha_discovery_fn: Callback to publish HA autodiscovery,
            signature: ``(ha_type, input_id, name, device_class, area,
            mqtt_sequences, enable_triple_click) -> None``.
    """

    def __init__(
        self,
        manager: Manager,
        ha_discovery_fn: Any = None,
    ) -> None:
        """Initialize registrar.

        Args:
            manager: Top-level Manager instance.
            ha_discovery_fn: Optional callable for HA discovery publishing.
        """
        self._manager = manager
        self._ha_discovery_fn = ha_discovery_fn

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_all(
        self,
        inputs_dict: dict[str, Any],
        remote_device_manager: Any,
        remote_inputs_config: list[dict[str, Any]] | None = None,
    ) -> None:
        """Register remote inputs from the ``remote_inputs`` config section.

        Each entry in *remote_inputs_config* maps a binary sensor on a remote
        device to a local :class:`ESPHomeBinarySensorInput`.  The device is
        looked up via *remote_device_manager* by ``device_id``.

        Should be called **after** :meth:`RemoteDeviceManager.initialize` so
        that ESPHome devices and their connections are ready.

        Args:
            inputs_dict: Shared ``InputManager._inputs`` dictionary.
            remote_device_manager: Initialized :class:`RemoteDeviceManager`.
            remote_inputs_config: List of remote input dicts from
                ``config['remote_inputs']``.
        """
        if not remote_inputs_config:
            return

        count = 0
        for ri_cfg in remote_inputs_config:
            registered = self._register_single(
                inputs_dict, remote_device_manager, ri_cfg
            )
            if registered:
                count += 1

        if count:
            _LOGGER.info("Registered %d remote input(s)", count)

    def _register_single(
        self,
        inputs_dict: dict[str, Any],
        remote_device_manager: Any,
        ri_cfg: dict[str, Any],
    ) -> bool:
        """Register a single remote input entry.

        Args:
            inputs_dict: Shared ``InputManager._inputs`` dictionary.
            remote_device_manager: Initialized :class:`RemoteDeviceManager`.
            ri_cfg: Single remote input config dict.

        Returns:
            True if registration succeeded, False otherwise.
        """
        device_id = ri_cfg.get("device_id")
        input_id = ri_cfg.get("input_id")
        remote_source = ri_cfg.get("remote_source", "esphome_api")

        if not device_id or not input_id:
            _LOGGER.warning(
                "Skipping remote input with missing device_id or input_id: %s",
                ri_cfg,
            )
            return False

        # Build input ID: custom id or auto-generated
        custom_id = ri_cfg.get("id") or f"{device_id}_{input_id}"
        if custom_id in inputs_dict:
            _LOGGER.debug(
                "Remote input '%s' already registered, skipping",
                custom_id,
            )
            return False

        # Resolve device from remote device manager
        device = remote_device_manager.get_device(device_id)
        if not device:
            _LOGGER.warning(
                "Remote input '%s' references unknown device '%s', skipping",
                custom_id,
                device_id,
            )
            return False

        name = ri_cfg.get("name") or custom_id
        mode = ri_cfg.get("mode", "binary_sensor")
        raw_actions = ri_cfg.get("actions", {})

        # Parse actions through Manager (resolves outputs, covers, etc.)
        parsed_actions = (
            self._manager.parse_actions(pin=custom_id, actions=raw_actions)
            if raw_actions
            else {}
        )

        esphome_input = ESPHomeBinarySensorInput(
            id=custom_id,
            name=name,
            device_id=device_id,
            sensor_id=input_id,
            event_bus=self._manager._event_bus,
            actions=parsed_actions,
            mode=mode,
            device_class=ri_cfg.get("device_class"),
            area=ri_cfg.get("area"),
            inverted=ri_cfg.get("inverted", False),
            show_in_ha=ri_cfg.get("show_in_ha", False),
            double_click_duration=ri_cfg.get("double_click_duration", 220),
            long_press_duration=ri_cfg.get("long_press_duration", 400),
            mqtt_sequences=ri_cfg.get("mqtt_sequences"),
            sequence_mode=ri_cfg.get("sequence_mode", "exclusive"),
            long_press_mqtt_mode=ri_cfg.get("long_press_mqtt_mode", "single"),
            enable_triple_click=ri_cfg.get("enable_triple_click", False),
        )

        # Register callback on the remote device (ESPHome)
        if remote_source == "esphome_api" and hasattr(
            device, "register_binary_sensor_callback"
        ):
            device.register_binary_sensor_callback(
                input_id, esphome_input.on_remote_state_change
            )

        # Store as a regular input
        inputs_dict[custom_id] = esphome_input

        # HA Autodiscovery — delegate to InputManager
        if ri_cfg.get("show_in_ha", False) and self._ha_discovery_fn:
            ha_type = EVENT_ENTITY if mode == "event" else "binary_sensor"
            self._ha_discovery_fn(
                ha_type=ha_type,
                input_id=custom_id,
                name=name,
                device_class=ri_cfg.get("device_class"),
                area=ri_cfg.get("area"),
                mqtt_sequences=ri_cfg.get("mqtt_sequences"),
                enable_triple_click=ri_cfg.get("enable_triple_click", False),
            )

        _LOGGER.info(
            "Registered remote input '%s' (source=%s, device=%s, sensor=%s, mode=%s)",
            custom_id,
            remote_source,
            device_id,
            input_id,
            mode,
        )
        return True

    # ------------------------------------------------------------------
    # Unregistration
    # ------------------------------------------------------------------

    @staticmethod
    def unregister_all(inputs_dict: dict[str, Any]) -> None:
        """Remove all remote (virtual) input instances.

        Used during remote device reload to clean up before re-registering.
        Removes any input that is a :class:`RemoteInputBase` subclass.

        Args:
            inputs_dict: Shared ``InputManager._inputs`` dictionary.
        """
        to_remove = [
            k for k, v in inputs_dict.items() if isinstance(v, RemoteInputBase)
        ]
        for key in to_remove:
            del inputs_dict[key]
        if to_remove:
            _LOGGER.info("Unregistered %d remote input(s)", len(to_remove))
