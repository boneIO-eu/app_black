from __future__ import annotations

import logging

from boneio.core.config import ConfigHelper
from boneio.core.messaging.basic import MessageBus
from boneio.modbus.entities.base import ModbusBaseEntity

_LOGGER = logging.getLogger(__name__)


class ModbusNumericSensor(ModbusBaseEntity):
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
        return_type: str,
        filters: list,
        message_bus: MessageBus,
        config_helper: ConfigHelper,
        user_filters: list | None = [],
        ha_filter: str = "round(2)",
    ) -> None:
        """
        Initialize single sensor.
        :param name: name of sensor
        :param register_address: address of register
        :param base_address: address of base
        :param unit_of_measurement: unit of measurement
        :param state_class: state class
        :param device_class: device class
        :param value_type: type of value
        :param return_type: type of return
        :param user_filters: list of user filters
        :param filters: list of filters
        :param send_ha_autodiscovery: function for sending HA autodiscovery
        """
        super().__init__(
            name=name,
            parent=parent,
            unit_of_measurement=unit_of_measurement,
            state_class=state_class,
            device_class=device_class,
            value_type=value_type,
            return_type=return_type,
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
