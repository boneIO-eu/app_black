from __future__ import annotations


from boneio.helper.config import ConfigHelper
from boneio.message_bus.basic import MessageBus
from boneio.modbus.sensor.base import BaseSensor


class ModbusDerivedNumericSensor(BaseSensor):
    def __init__(
        self,
        name: str,
        parent: dict,
        unit_of_measurement: str,
        state_class: str,
        device_class: str,
        value_type: str,
        return_type: str,
        filters: list,
        message_bus: MessageBus,
        formula: str,
        context_config: dict,
        config_helper: ConfigHelper,
        source_sensor_base_address: str,
        source_sensor_decoded_name: str,
        user_filters: list | None = [],
        ha_filter: str = "round(2)",
    ) -> None:
        BaseSensor.__init__(
            self,
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
        )
        self._formula = formula
        self._context_config = context_config
        self._source_sensor_base_address = source_sensor_base_address
        self._source_sensor_decoded_name = source_sensor_decoded_name

    @property
    def formula(self) -> str:
        return self._formula

    @property
    def context(self) -> dict:
        return self._context_config

    @property
    def base_address(self) -> str:
        return self._source_sensor_base_address

    @property
    def state(self) -> float:
        """Give rounded value of temperature."""
        return self._value or 0.0

    @property
    def source_sensor_decoded_name(self) -> str:
        return self._source_sensor_decoded_name

    def evaluate_state(
        self, source_sensor_value: int | float, timestamp: float
    ) -> int | float:
        context = {
            "X": source_sensor_value,
            **self.context,
        }
        code = compile(self.formula, "<string>", "eval")
        value = eval(code, {"__builtins__": {}}, context)
        self.set_value(value, timestamp)
