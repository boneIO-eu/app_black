from __future__ import annotations

from boneio.const import ID, MODEL, NAME, SELECT, SENSOR
from boneio.core.config import ConfigHelper
from boneio.integration.homeassistant import (
    modbus_select_availabilty_message,
)
from boneio.core.utils.util import find_key_by_value
from boneio.core.messaging.basic import MessageBus
from boneio.modbus.entities.base import ModbusDerivedEntity


class ModbusDerivedSelect(ModbusDerivedEntity):
    _entity_type = SELECT

    def __init__(
        self,
        name: str,
        parent: dict,
        message_bus: MessageBus,
        context_config: dict,
        config_helper: ConfigHelper,
        source_sensor_base_address: int,
        source_sensor_decoded_name: str,
        value_mapping: dict,
    ) -> None:
        ModbusDerivedEntity.__init__(
            self,
            name=name,
            parent=parent,
            value_type=None,
            filters=[],
            message_bus=message_bus,
            config_helper=config_helper,
            user_filters=[],
            ha_filter="",
            source_sensor_base_address=source_sensor_base_address,
            source_sensor_decoded_name=source_sensor_decoded_name,
        )
        self._context_config = context_config
        self._value_mapping = value_mapping

    @property
    def context(self) -> dict:
        return self._context_config

    def discovery_message(self):
        kwargs = {
            "value_template": f"{{{{ value_json.{self.decoded_name} }}}}",
            "entity_id": self.name,
            "options": [*self._value_mapping.values()],
            "command_topic": f"{self._config_helper.topic_prefix}/cmd/modbus/{self._parent[ID].lower()}/set",
            "command_template": '{"device": "'
            + self.decoded_name
            + '", "value": "{{ value }}"}',
        }
        msg = modbus_select_availabilty_message(
            config_helper=self._config_helper,
            id=self._parent[ID],
            name=self._parent[NAME],
            state_topic_base=str(self.base_address),
            model=self._parent[MODEL],
            device_type=SENSOR,  # because we send everything to boneio/sensor from modbus.
            **kwargs,
        )
        return msg

    def evaluate_state(
        self, source_sensor_value: int | float, timestamp: float
    ) -> None:
        self._timestamp = timestamp
        self._value = self._value_mapping.get(str(source_sensor_value), "Unknown")

    def encode_value(self, value: str | float | int) -> int:
        """Encode value to modbus register value.
        
        Args:
            value: Label/value from x_mapping (e.g., "Auto", "Cool") - finds key by value
                Can also accept a numeric key if needed (for backward compatibility)
                
        Returns:
            Integer value to write to modbus register
        """
        if not self._value_mapping:
            return 0
        
        # Convert value to string for comparison
        value_str = str(value)
        
        # First try to find key by value (label) - this is the primary method
        # Frontend sends labels like "Auto", "Cool" and we need to find the key ("1", "2")
        key = find_key_by_value(self._value_mapping, value_str)
        if key is not None:
            return int(key)
        
        # If not found, check if value is already a numeric key (for backward compatibility)
        try:
            numeric_value = float(value)
            int_value = int(numeric_value)
            # Check if numeric value (as string key) exists in x_mapping
            if str(int_value) in self._value_mapping:
                return int_value
        except (ValueError, TypeError):
            pass
        
        # Also check if value string is already a key in x_mapping
        if value_str in self._value_mapping:
            return int(value_str)
        
        return 0
