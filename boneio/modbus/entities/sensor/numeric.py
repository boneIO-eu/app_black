from __future__ import annotations

import logging

from boneio.core.config import ConfigHelper
from boneio.core.messaging.basic import MessageBus
from boneio.modbus.entities.base import ModbusBaseEntity

_LOGGER = logging.getLogger(__name__)


class ModbusNumericSensor(ModbusBaseEntity):
    """Modbus numeric sensor entity."""
    
    def __init__(
        self,
        name: str,
        parent: dict,
        register_address: int,
        base_address: int,
        unit_of_measurement: str,
        state_class: str,
        device_class: str,
        value_type: str,
        filters: list,
        message_bus: MessageBus,
        config_helper: ConfigHelper,
        user_filters: list | None = [],
        ha_filter: str = "round(2)",
    ) -> None:
        """Initialize single sensor.
        
        Args:
            name: name of sensor
            register_address: address of register
            base_address: address of base
            unit_of_measurement: unit of measurement
            state_class: state class
            device_class: device class
            value_type: type of value for decoding
            user_filters: list of user filters
            filters: list of filters
        """
        super().__init__(
            name=name,
            parent=parent,
            unit_of_measurement=unit_of_measurement,
            state_class=state_class,
            device_class=device_class,
            value_type=value_type,
            filters=filters,
            message_bus=message_bus,
            config_helper=config_helper,
            user_filters=user_filters,
            ha_filter=ha_filter,
            register_address=register_address,
            base_address=base_address,
        )

    @property
    def state(self) -> float:
        """Give rounded value of temperature."""
        return self._value or 0.0
