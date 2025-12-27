from __future__ import annotations

import logging
import time

from boneio.const import ID, MODEL, NAME, SENSOR
from boneio.core.config import ConfigHelper
from boneio.core.messaging.basic import MessageBus
from boneio.core.utils import Filter
from boneio.integration.homeassistant import modbus_sensor_availabilty_message

_LOGGER = logging.getLogger(__name__)


class BaseEntity(Filter):

    _entity_type = SENSOR

    def __init__(
        self,
        name: str,
        parent: dict,
        message_bus: MessageBus,
        config_helper: ConfigHelper,
        unit_of_measurement: str | None = None,
        state_class: str | None   = None,
        device_class: str | None = None,
        value_type: str | None = None,
        filters: list = [],
        user_filters: list | None = [],
        ha_filter: str = "round(2)",
    ) -> None:
        self._name = name
        self._parent = parent
        self._decoded_name = self._name.replace(" ", "")
        self._decoded_name_low = self._name.replace(" ", "").lower()
        self._unit_of_measurement = unit_of_measurement
        self._state_class = state_class
        self._device_class = device_class
        self._message_bus = message_bus
        self._config_helper = config_helper
        self._user_filters = user_filters
        self._filters = filters
        self._value = None
        self._value_type = value_type
        self._ha_filter = ha_filter
        self._timestamp = time.time()
        self._id = f"{self._parent[ID]}{self._decoded_name_low.replace('_', '')}"
        self._topic = (
            f"{self._config_helper.ha_discovery_prefix}/{self._entity_type}/{self._config_helper.serial_no}"
            f"/{self._id}/config"
        )

    @property
    def id(self) -> str:
        return self._id

    def set_user_filters(self, user_filters: list) -> None:
        self._user_filters = user_filters

    def set_value(self, value, timestamp: float) -> None:
        value = self._apply_filters(value=value)
        value = self._apply_filters(
            value=value,
            filters=self._user_filters,
        )
        self._value = value
        self._timestamp = timestamp

    def get_value(self) -> float | int | None:
        return self._value

    @property
    def value_type(self) -> str | None:
        return self._value_type

    @property
    def state(self) -> str | float | None:
        """Give back state value."""
        return self._value

    @property
    def decoded_name(self) -> str:
        return self._decoded_name_low

    @property
    def name(self) -> str:
        """Return name of the sensor."""
        return self._name

    @property
    def unit_of_measurement(self) -> str | None:
        return self._unit_of_measurement

    @property
    def last_timestamp(self) -> float:
        return self._timestamp

    @property
    def write_address(self) -> int | None:
        """Write address for writeable entities (None for read-only)."""
        return None
    
    def encode_value(self, value: str | float | int) -> float:
        """Encode value for writing to modbus (override in writeable entities)."""
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return 0
        return value

    @property
    def entity_type(self) -> str:
        return self._entity_type

    def send_ha_discovery(self):
        payload = self.discovery_message()
        _LOGGER.debug(
            "Sending %s discovery message for %s of %s",
            self._entity_type,
            self._name,
            self._parent[ID],
        )
        self._config_helper.add_autodiscovery_msg(
            topic=self._topic, payload=payload, ha_type=self._entity_type
        )
        self._message_bus.send_message(topic=self._topic, payload=payload)

    @property
    def base_address(self) -> int | None:
        """Get base address for the sensor (used by Modbus sensors).
        
        Returns:
            Base address or None for non-Modbus sensors
        """
        return None

    def discovery_message(self):
        value_template = f"{{{{ value_json.{self.decoded_name} | {self._ha_filter} }}}}" if self._ha_filter else f"{{{{ value_json.{self.decoded_name} }}}}" 
        
        kwargs = {
            "unit_of_measurement": self.unit_of_measurement,
            "state_class": self._state_class,
            "value_template": value_template,
            "sensor_id": self.name,
        }
        if self._device_class:
            kwargs["device_class"] = self._device_class
        return modbus_sensor_availabilty_message(
            config_helper=self._config_helper,
            id=self._parent[ID],
            name=self._parent[NAME],
            state_topic_base=str(self.base_address),
            model=self._parent[MODEL],
            area=self._parent.get("area"),
            **kwargs,
        )


class ModbusBaseEntity(BaseEntity):
    def __init__(
        self,
        name: str,
        parent: dict,
        register_address: int,
        base_address: int,
        message_bus: MessageBus,
        config_helper: ConfigHelper,
        unit_of_measurement: str | None = None,
        state_class: str | None = None,
        device_class: str | None = None,
        value_type: str | None = None,
        filters: list | None = None,
        user_filters: list | None = [],
        ha_filter: str = "",
    ) -> None:
        """
        Initialize single sensor.
        
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
            filters=filters or [],
            message_bus=message_bus,
            config_helper=config_helper,
            user_filters=user_filters,
            ha_filter=ha_filter,
        )
        self._register_address = register_address
        self._base_address = base_address

    @property
    def address(self) -> int:
        return self._register_address

    @property
    def base_address(self) -> int:
        return self._base_address

    @property
    def is_derived(self) -> bool:
        return False



class ModbusDerivedEntity(BaseEntity):
    def __init__(
        self,
        source_sensor_base_address: int,
        source_sensor_decoded_name: str,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._source_sensor_base_address = source_sensor_base_address
        self._source_sensor_decoded_name = source_sensor_decoded_name

    @property
    def source_sensor_base_address(self) -> int:
        return self._source_sensor_base_address

    @property
    def source_sensor_decoded_name(self) -> str:
        return self._source_sensor_decoded_name

    @property
    def base_address(self) -> int:
        return self._source_sensor_base_address

    @property
    def state(self) -> str | float:
        """Give rounded value of blank string."""
        return self._value or ""

    @property
    def is_derived(self) -> bool:
        return True

    def evaluate_state(self, source_value: str | float | int, timestamp: float) -> None:
        pass