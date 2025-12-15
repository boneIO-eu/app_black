from __future__ import annotations


from boneio.core.config import ConfigHelper
from boneio.core.messaging.basic import MessageBus
from boneio.modbus.entities.base import ModbusDerivedEntity


class ModbusDerivedNumericSensor(ModbusDerivedEntity):
    """Derived numeric sensor that calculates values from source sensors."""
    
    def __init__(
        self,
        name: str,
        parent: dict,
        unit_of_measurement: str,
        state_class: str,
        device_class: str,
        value_type: str | None,
        filters: list,
        message_bus: MessageBus,
        formula: str,
        context_config: dict,
        config_helper: ConfigHelper,
        source_sensor_base_address: int,
        source_sensor_decoded_name: str,
        user_filters: list | None = [],
        ha_filter: str = "round(2)",
    ) -> None:
        ModbusDerivedEntity.__init__(
            self,
            name=name,
            parent=parent,
            unit_of_measurement=unit_of_measurement,
            state_class=state_class,
            device_class=device_class,
            value_type=value_type,
            filters=filters,
            message_bus=message_bus,
            config_helper=config_helper,
            source_sensor_base_address=source_sensor_base_address,
            source_sensor_decoded_name=source_sensor_decoded_name,
            user_filters=user_filters,
            ha_filter=ha_filter,
        )
        self._formula = formula
        self._context_config = context_config

    @property
    def formula(self) -> str:
        return self._formula

    @property
    def context(self) -> dict:
        return self._context_config

    @property
    def state(self) -> float:
        """Give rounded value of temperature."""
        return self._value or 0.0

    def evaluate_state(
        self, source_sensor_value: int | float, timestamp: float
    ) -> None:
        context = {
            "X": source_sensor_value,
            **self.context,
        }
        code = compile(self.formula, "<string>", "eval")
        value = eval(code, {"__builtins__": {}}, context)
        self.set_value(value, timestamp)
