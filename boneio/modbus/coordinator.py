from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime

from boneio.const import (
    ADDRESS,
    BASE,
    BINARY_SENSOR,
    ID,
    LENGTH,
    MODBUS_DEVICE,
    MODEL,
    NAME,
    OFFLINE,
    ONLINE,
    REGISTERS,
    SELECT,
    SENSOR,
    STATE,
    SWITCH,
    TEXT_SENSOR,
)
from boneio.core.config import ConfigHelper
from boneio.core.events import EventBus
from boneio.core.messaging import BasicMqtt
from boneio.core.utils import AsyncUpdater, Filter
from boneio.core.utils.util import open_json
from boneio.modbus.entities.derived import (
    ModbusDerivedNumericSensor,
    ModbusDerivedSelect,
    ModbusDerivedSwitch,
    ModbusDerivedTextSensor,
)
from boneio.modbus.entities.sensor import (
    ModbusBinarySensor,
    ModbusNumericSensor,
)
from boneio.modbus.entities.sensor.text import ModbusTextSensor
from boneio.modbus.entities.writeable.binary import ModbusBinaryWriteableEntityDiscrete
from boneio.modbus.entities.writeable.numeric import (
    ModbusNumericWriteableEntity,
    ModbusNumericWriteableEntityDiscrete,
)
from boneio.models import SensorState

from .client import VALUE_TYPES, Modbus
from .utils import CONVERT_METHODS, REGISTERS_BASE

_LOGGER = logging.getLogger(__name__)


class ModbusCoordinator(BasicMqtt, AsyncUpdater, Filter):
    """Represent Modbus coordinator in BoneIO."""

    DefaultName = "ModbusCoordinator"

    def __init__(
        self,
        modbus: Modbus,
        address: str,
        model: str,
        sensors_filters: dict,
        config_helper: ConfigHelper,
        event_bus: EventBus,
        id: str = DefaultName,
        additional_data: dict = {},
        **kwargs,
    ):
        """Initialize Modbus coordinator class."""
        BasicMqtt.__init__(
            self,
            id=id or address,
            topic_type=SENSOR,
            topic_prefix=config_helper.topic_prefix,
            **kwargs,
        )
        self._config_helper = config_helper
        self._modbus = modbus
        self._db = open_json(path=os.path.dirname(__file__), model=model)
        self._model = self._db[MODEL]
        self._address = address
        self._discovery_sent = False
        self._payload_online = OFFLINE
        self._sensors_filters = {k.lower(): v for k, v in sensors_filters.items()}
        # Type aliases for cleaner code
        from typing import Union
        ModbusEntity = Union[
            ModbusNumericSensor,
            ModbusNumericWriteableEntity,
            ModbusNumericWriteableEntityDiscrete,
            ModbusBinarySensor,
            ModbusBinaryWriteableEntityDiscrete,
            ModbusTextSensor,
        ]
        DerivedEntity = Union[
            ModbusDerivedNumericSensor,
            ModbusDerivedTextSensor,
            ModbusDerivedSelect,
            ModbusDerivedSwitch,
        ]
        
        self._modbus_entities: list[dict[str, ModbusEntity]] = []  # type: ignore[valid-type]
        self._modbus_entities_by_name: dict[str, ModbusEntity] = {}  # type: ignore[valid-type]
        self._additional_sensors: list[dict[str, DerivedEntity]] = []  # type: ignore[valid-type]
        self._additional_sensors_by_source_name: dict[str, list[DerivedEntity]] = {}  # type: ignore[valid-type]
        self._additional_sensors_by_name: dict[str, DerivedEntity] = {}  # type: ignore[valid-type]
        self._additional_data = additional_data

        self.__init_modbus_entities__()
        # Additional sensors
        if "additional_sensors" in self._db:
            self.__init_derived_sensors__()

        _LOGGER.info(
            "Available single sensors for %s: %s",
            self._name,
            ", ".join(
                [s.name for sensors in self._modbus_entities for s in sensors.values()]
            ),
        )
        if self._additional_sensors:
            _LOGGER.info(
                "Available additional sensors for %s: %s",
                self._name,
                ", ".join(
                    [
                        s.name
                        for sensors in self._additional_sensors
                        for s in sensors.values()
                    ]
                ),
            )
        self._event_bus = event_bus
        self._event_bus.add_haonline_listener(target=self.set_payload_offline)
        try:
            AsyncUpdater.__init__(self, **kwargs)
        except Exception as e:
            _LOGGER.error("Error in AsyncUpdater: %s", e)

    def __init_modbus_entities__(self):
        # Standard sensors
        for index, data in enumerate(self._db[REGISTERS_BASE]):
            base = data[BASE]
            self._modbus_entities.append({})
            for register in data[REGISTERS]:
                entity_type = register.get("entity_type", SENSOR)
                kwargs = {
                    "name": register.get("name"),
                    "base_address": base,
                    "register_address": register[ADDRESS],
                    "parent": {
                        NAME: self._name,
                        ID: self._id,
                        MODEL: self._model,
                    },
                    "unit_of_measurement": register.get("unit_of_measurement"),
                    "state_class": register.get("state_class"),
                    "device_class": register.get("device_class"),
                    "value_type": register.get("value_type"),
                    "return_type": register.get("return_type", "regular"),
                    "filters": register.get("filters", []),
                    "message_bus": self._message_bus,
                    "config_helper": self._config_helper,
                }
                if entity_type == SENSOR:
                    single_sensor = ModbusNumericSensor(
                        ha_filter=register.get("ha_filter", "round(2)"),
                        **kwargs)
                elif entity_type == TEXT_SENSOR:
                    single_sensor = ModbusTextSensor(
                        value_mapping=register.get("x_mapping", {}), **kwargs
                    )
                elif entity_type == BINARY_SENSOR:
                    single_sensor = ModbusBinarySensor(
                        payload_on=register.get("payload_on", "ON"),
                        payload_off=register.get("payload_off", "OFF"),
                        **kwargs,
                    )
                elif entity_type == "writeable_sensor":
                    single_sensor = ModbusNumericWriteableEntity(
                        coordinator=self,
                        write_filters=register.get("write_filters", []),
                        write_address=register.get("write_address"),
                        ha_filter=register.get("ha_filter", "round(2)"),
                        **kwargs,
                    )
                elif entity_type == "writeable_sensor_discrete":
                    single_sensor = ModbusNumericWriteableEntityDiscrete(
                        coordinator=self,
                        write_address=register.get("write_address"),
                        write_filters=register.get("write_filters", []),
                        ha_filter=register.get("ha_filter", "round(2)"),
                        **kwargs,
                    )
                elif entity_type == "writeable_binary_sensor_discrete":
                    single_sensor = ModbusBinaryWriteableEntityDiscrete(
                        coordinator=self,
                        write_address=register.get("write_address"),
                        payload_on=register.get("payload_on", "ON"),
                        payload_off=register.get("payload_off", "OFF"),
                        write_filters=register.get("write_filters", []),
                        **kwargs,
                    )
                else:
                    continue
                single_sensor.set_user_filters(
                    self._sensors_filters.get(single_sensor.decoded_name, [])
                )
                self._modbus_entities[index][single_sensor.decoded_name] = single_sensor

    def __init_derived_numeric(
        self, additional: dict
    ) -> ModbusDerivedNumericSensor | None:
        config_keys = additional.get("config_keys", [])
        if not self._additional_data:
            return None
        if not all(k in self._additional_data for k in config_keys):
            return None
        source_sensor = None
        for sensors in self._modbus_entities:
            for s in sensors.values():
                if s.decoded_name == additional["source"].replace("_", ""):
                    source_sensor = s
                    break
        if not source_sensor:
            _LOGGER.warning(
                "Source sensor '%s' for additional sensor '%s' not found.",
                additional["source"],
                additional["name"],
            )
            return None
        single_sensor = ModbusDerivedNumericSensor(
            name=additional["name"],
            parent={NAME: self._name, ID: self._id, MODEL: self._model},
            source_sensor_base_address=source_sensor.base_address,
            source_sensor_decoded_name=source_sensor.decoded_name,
            unit_of_measurement=additional.get("unit_of_measurement", "m3"),
            state_class=additional.get("state_class", "measurement"),
            device_class=additional.get("device_class", "volume"),
            value_type=None,
            return_type=None,
            filters=[],
            message_bus=self._message_bus,
            config_helper=self._config_helper,
            ha_filter=additional.get("ha_filter", "round(2)"),
            formula=additional.get("formula", ""),
            context_config={
                k: v for k, v in self._additional_data.items() if k in config_keys
            },
        )
        return single_sensor

    def __init_derived_text_sensor(
        self, additional: dict
    ) -> ModbusDerivedTextSensor | None:
        x_mapping = additional.get("x_mapping", {})
        source_sensor = None
        for sensors in self._modbus_entities:
            for s in sensors.values():
                if s.decoded_name == additional["source"].replace("_", ""):
                    source_sensor = s
                    break
        if not source_sensor:
            _LOGGER.warning(
                "Source sensor '%s' for additional sensor '%s' not found.",
                additional["source"],
                additional["name"],
            )
            return None
        single_sensor = ModbusDerivedTextSensor(
            name=additional["name"],
            parent={NAME: self._name, ID: self._id, MODEL: self._model},
            source_sensor_base_address=source_sensor.base_address,
            message_bus=self._message_bus,
            config_helper=self._config_helper,
            source_sensor_decoded_name=source_sensor.decoded_name,
            context_config={},
            value_mapping=x_mapping,
        )
        return single_sensor

    def __init_derived_select(self, additional: dict) -> ModbusDerivedSelect | None:
        x_mapping = additional.get("x_mapping", {})
        source_sensor = None
        for sensors in self._modbus_entities:
            for s in sensors.values():
                if s.decoded_name == additional["source"].replace("_", ""):
                    source_sensor = s
                    break
        if not source_sensor:
            _LOGGER.warning(
                "Source sensor '%s' for additional select '%s' not found.",
                additional["source"],
                additional["name"],
            )
            return None
        single_sensor = ModbusDerivedSelect(
            name=additional["name"],
            parent={NAME: self._name, ID: self._id, MODEL: self._model},
            source_sensor_base_address=source_sensor.base_address,
            message_bus=self._message_bus,
            config_helper=self._config_helper,
            source_sensor_decoded_name=source_sensor.decoded_name,
            context_config={},
            value_mapping=x_mapping,
        )
        return single_sensor

    def __init_derived_switch(self, additional: dict) -> ModbusDerivedSwitch | None:
        x_mapping = additional.get("x_mapping", {})
        source_sensor = None
        for sensors in self._modbus_entities:
            for s in sensors.values():
                if s.decoded_name == additional["source"].replace("_", ""):
                    source_sensor = s
                    break
        if not source_sensor:
            _LOGGER.warning(
                "Source sensor '%s' for additional select '%s' not found.",
                additional["source"],
                additional["name"],
            )
            return None
        single_sensor = ModbusDerivedSwitch(
            name=additional["name"],
            parent={NAME: self._name, ID: self._id, MODEL: self._model},
            source_sensor_base_address=source_sensor.base_address,
            message_bus=self._message_bus,
            config_helper=self._config_helper,
            source_sensor_decoded_name=source_sensor.decoded_name,
            context_config={},
            value_mapping=x_mapping,
            payload_off=additional.get("payload_off", "OFF"),
            payload_on=additional.get("payload_on", "ON"),
        )
        return single_sensor

    def __init_derived_sensors__(self):
        for additional in self._db["additional_sensors"]:
            entity_type = additional.get("entity_type", SENSOR)
            derived_sensor = None
            if entity_type == TEXT_SENSOR:
                derived_sensor = self.__init_derived_text_sensor(additional)
            elif entity_type == SENSOR:
                derived_sensor = self.__init_derived_numeric(additional)
            elif entity_type == SELECT:
                derived_sensor = self.__init_derived_select(additional)
            elif entity_type == SWITCH:
                derived_sensor = self.__init_derived_switch(additional)
            if not derived_sensor:
                continue

            self._additional_sensors.append(
                {derived_sensor.decoded_name: derived_sensor}
            )
            self._additional_sensors_by_name[derived_sensor.decoded_name] = (
                derived_sensor
            )
            if (
                derived_sensor.source_sensor_decoded_name
                not in self._additional_sensors_by_source_name
            ):
                self._additional_sensors_by_source_name[
                    derived_sensor.source_sensor_decoded_name
                ] = []
            self._additional_sensors_by_source_name[
                derived_sensor.source_sensor_decoded_name
            ].append(derived_sensor)

    def get_entity_by_name(
        self, name: str
    ) -> None | (
        ModbusNumericSensor
        | ModbusNumericWriteableEntity
        | ModbusNumericWriteableEntityDiscrete
    ):
        """Return sensor by name."""
        for sensors in self._modbus_entities:
            if name in sensors:
                return sensors.get(name)
        return None

    def get_all_entities(
        self,
    ) -> list[
        dict[
            str,
            ModbusNumericSensor
            | ModbusNumericWriteableEntity
            | ModbusNumericWriteableEntityDiscrete,
        ]
    ]:
        return self._modbus_entities

    def set_payload_offline(self):
        self._payload_online = OFFLINE

    def _send_discovery_for_all_registers(self) -> datetime:
        """Send discovery message to HA for each register."""
        for sensors in self._modbus_entities:
            for sensor in sensors.values():
                sensor.send_ha_discovery()
        for sensors in self._additional_sensors:
            for sensor in sensors.values():
                sensor.send_ha_discovery()
        return datetime.now()

    async def write_register(
        self, 
        value: str | float | int, 
        entity: ModbusNumericSensor | ModbusNumericWriteableEntity | ModbusNumericWriteableEntityDiscrete
    ) -> None:
        """Write value to modbus register.
        
        Args:
            value: Value to write
            entity: Entity object (not name) to write to
        """
        _LOGGER.debug("Writing register %s for %s", value, entity.name if hasattr(entity, 'name') else entity)
        output = {}
        timestamp = time.time()
        
        # Check if it's a derived sensor (by entity's decoded_name)
        entity_name = entity.decoded_name if hasattr(entity, 'decoded_name') else str(entity)
        derived_sensor = self._additional_sensors_by_name.get(entity_name)
        
        if derived_sensor:
            source_sensor = self.get_entity_by_name(
                derived_sensor.source_sensor_decoded_name
            )
            if not source_sensor or not source_sensor.write_address:
                _LOGGER.error(
                    "Source sensor %s has no write address", source_sensor.name if source_sensor else "Unknown"
                )
                return
            encoded_value = derived_sensor.encode_value(value)
            status = await self._modbus.write_register(
                unit=self._address,
                address=source_sensor.write_address,
                value=encoded_value,
            )
            source_sensor.set_value(value=encoded_value, timestamp=timestamp)
            derived_sensor.evaluate_state(source_sensor.get_value(), timestamp)
            _LOGGER.debug("Register written %s", status)
            output[derived_sensor.decoded_name] = derived_sensor.state
            output[source_sensor.decoded_name] = source_sensor.state
            self._message_bus.send_message(
                topic=f"{self._send_topic}/{source_sensor.base_address}",
                payload=output,
            )
            return
        
        # Direct modbus sensor write
        modbus_sensor = entity  # entity is already the sensor object
        if not hasattr(modbus_sensor, 'write_address') or not modbus_sensor.write_address:
            _LOGGER.error("Modbus sensor %s has no write address", modbus_sensor.name if hasattr(modbus_sensor, 'name') else 'Unknown')
            return
        encoded_value = modbus_sensor.encode_value(value)
        status = await self._modbus.write_register(
            unit=self._address, address=modbus_sensor.write_address, value=encoded_value
        )
        modbus_sensor.set_value(value=encoded_value, timestamp=timestamp)
        if self._additional_sensors and modbus_sensor.get_value() is not None:
            if modbus_sensor.decoded_name in self._additional_sensors_by_source_name:
                for additional_sensor in self._additional_sensors_by_source_name[
                    modbus_sensor.decoded_name
                ]:
                    additional_sensor.evaluate_state(
                        modbus_sensor.get_value(), timestamp
                    )
                    output[additional_sensor.decoded_name] = additional_sensor.state
                output[modbus_sensor.decoded_name] = modbus_sensor.state
        self._event_bus.trigger_event({
            "event_type": MODBUS_DEVICE,
            "entity_id": modbus_sensor.id,
            "event": SensorState(
                id=modbus_sensor.id,
                name=modbus_sensor.name,
                state=modbus_sensor.state,
                unit=modbus_sensor.unit_of_measurement,
                timestamp=modbus_sensor.last_timestamp,
            ),
        })
        self._timestamp = timestamp
        self._message_bus.send_message(
            topic=f"{self._send_topic}/{modbus_sensor.base_address}",
            payload=output,
        )
        _LOGGER.debug("Register written %s", status)

    async def check_availability(self) -> None:
        """Get first register and check if it's available."""
        if (
            not self._discovery_sent
            or (datetime.now() - self._discovery_sent).seconds > 3600
        ) and self._config_helper.topic_prefix:
            self._discovery_sent = False
            first_register_base = self._db[REGISTERS_BASE][0]
            register_method = first_register_base.get("register_type", "input")
            # Let's try fetch register 2 times in case something wrong with initial packet.
            for _ in [0, 1]:
                register = await self._modbus.read_and_decode(
                    unit=self._address,
                    address=first_register_base[REGISTERS][0][ADDRESS],
                    method=register_method,
                    payload_type=first_register_base[REGISTERS][0].get(
                        "value_type", "FP32"
                    ),
                )
                if register is not None:
                    self._discovery_sent = self._send_discovery_for_all_registers()
                    await asyncio.sleep(2)
                    break
            if not self._discovery_sent:
                _LOGGER.error(
                    "Discovery for %s not sent. First register not available.",
                    self._id,
                )

    async def async_update(self, timestamp: float) -> float | None:
        """Fetch state periodically and send to MQTT."""
        update_interval = self._update_interval.total_in_seconds
        await self.check_availability()
        for index, data in enumerate(self._db[REGISTERS_BASE]):
            values = await self._modbus.read_registers(
                unit=self._address,
                address=data[BASE],
                count=data[LENGTH],
                method=data.get("register_type", "input"),
            )
            if self._payload_online == OFFLINE and values:
                _LOGGER.info("Sending online payload about device %s.", self._name)
                self._payload_online = ONLINE
                self._message_bus.send_message(
                    topic=f"{self._config_helper.topic_prefix}/{self._id}/{STATE}",
                    payload=self._payload_online,
                )
            if not values:
                if update_interval < 600:
                    # Let's wait litte more for device.
                    update_interval = update_interval * 1.5
                else:
                    # Let's assume device is offline.
                    self.set_payload_offline()
                    self._message_bus.send_message(
                        topic=f"{self._config_helper.topic_prefix}/{self._id}/{STATE}",
                        payload=self._payload_online,
                    )
                    self._discovery_sent = False
                _LOGGER.warning(
                    "Can't fetch data from modbus device %s. Will sleep for %s seconds",
                    self.id,
                    update_interval,
                )
                return update_interval
            elif update_interval != self._update_interval.total_in_seconds:
                update_interval = self._update_interval.total_in_seconds
            output = {}
            current_modbus_entities = self._modbus_entities[index]
            for sensor in current_modbus_entities.values():
                if not sensor.value_type:
                    # Go with old method. Remove when switch Sofar to new.
                    decoded_value = CONVERT_METHODS[sensor.return_type](
                        result=values,
                        base=sensor.base_address,
                        addr=sensor.address,
                    )
                else:
                    start_index = sensor.address - sensor.base_address
                    count = VALUE_TYPES[sensor.value_type]["count"]
                    payload = values.registers[start_index : start_index + count]
                    try:
                        decoded_value = self._modbus.decode_value(
                            payload, sensor.value_type
                        )
                    except Exception as e:
                        _LOGGER.error(
                            "Decoding error for %s at address %s, base: %s, length: %s, error %s",
                            sensor.name,
                            sensor.address,
                            sensor.base_address,
                            data[LENGTH],
                            e,
                        )
                        decoded_value = None
                sensor.set_value(value=decoded_value, timestamp=timestamp)
                if self._additional_sensors and sensor.get_value() is not None:
                    if sensor.decoded_name in self._additional_sensors_by_source_name:
                        for (
                            additional_sensor
                        ) in self._additional_sensors_by_source_name[
                            sensor.decoded_name
                        ]:
                            additional_sensor.evaluate_state(
                                sensor.get_value(), timestamp
                            )
                            output[additional_sensor.decoded_name] = (
                                additional_sensor.state
                            )
                output[sensor.decoded_name] = sensor.state
                self._event_bus.trigger_event({
                    "event_type": MODBUS_DEVICE,
                    "entity_id": sensor.id,
                    "event_state": SensorState( 
                        id=sensor.id,
                        name=sensor.name,
                        state=sensor.state,
                        unit=sensor.unit_of_measurement,
                        timestamp=sensor.last_timestamp,
                    ),
                })

            self._timestamp = timestamp
            self._message_bus.send_message(
                topic=f"{self._send_topic}/{data[BASE]}",
                payload=output,
            )
        return update_interval
