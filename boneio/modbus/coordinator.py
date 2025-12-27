from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any, Union

from boneio.const import (
    ADDRESS,
    BASE,
    BINARY_SENSOR,
    ID,
    LENGTH,
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
from boneio.core.messaging import BasicMqtt
from boneio.core.utils import AsyncUpdater, Filter
from boneio.core.utils.timeperiod import TimePeriod
from boneio.core.utils.util import open_json
from boneio.modbus.entities.base import BaseEntity, ModbusBaseEntity, ModbusDerivedEntity
from boneio.models.state import ModbusDeviceState

if TYPE_CHECKING:
    from boneio.core.manager import Manager
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
from boneio.models.events import ModbusDeviceEvent

from .client import VALUE_TYPES, Modbus

# Type aliases for cleaner code
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
        manager: Manager,
        id: str = DefaultName,
        name: str = DefaultName,
        additional_data: dict = {},
        update_interval: TimePeriod = TimePeriod(seconds=60),
        area: str | None = None,
    ):
        """Initialize Modbus coordinator class."""
        # Store manager reference first - needed by other init methods
        self.manager = manager
        self._area = area
        
        BasicMqtt.__init__(
            self,
            id=id or address,
            name=name,
            topic_type="modbus",
            topic_prefix=manager.config_helper.topic_prefix,
            message_bus=manager._message_bus,
        )
        self._modbus = modbus
        self._db = open_json(path=os.path.dirname(__file__), model=model)
        self._model = self._db[MODEL]
        self._address = address
        self._discovery_sent = False
        self._payload_online = OFFLINE
        self._sensors_filters = {k.lower(): v for k, v in sensors_filters.items()}
        
        
        self._modbus_entities: list[dict[str, ModbusEntity]] = []  # type: ignore[valid-type]
        self._modbus_entities_by_name: dict[str, ModbusEntity] = {}  # type: ignore[valid-type]
        self._additional_entities: list[dict[str, DerivedEntity]] = []  # type: ignore[valid-type]
        self._additional_entities_by_source_name: dict[str, list[DerivedEntity]] = {}  # type: ignore[valid-type]
        self._additional_entities_by_name: dict[str, DerivedEntity] = {}  # type: ignore[valid-type]
        self._additional_data = additional_data

        self.__init_modbus_entities__()
        # Additional entities
        if "additional_entities" in self._db:
            self.__init_derived_sensors__()

        _LOGGER.info(
            "Available single sensors for %s: %s",
            self._name,
            ", ".join(
                [s.name for sensors in self._modbus_entities for s in sensors.values()]
            ),
        )
        if self._additional_entities:
            _LOGGER.info(
                "Available additional entities for %s: %s",
                self._name,
                ", ".join(
                    [
                        s.name
                        for sensors in self._additional_entities
                        for s in sensors.values()
                    ]
                ),
            )
        try:
            AsyncUpdater.__init__(self, manager=manager, update_interval=update_interval)
        except Exception as e:
            _LOGGER.error("Error in AsyncUpdater: %s", e)
        
        self._event_bus = manager.event_bus
        self._event_bus.add_haonline_listener(target=self.set_payload_offline)

    def __init_modbus_entities__(self):
        # Standard sensors
        for index, data in enumerate(self._db["registers_base"]):
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
                        "area": self._area,
                    },
                    "unit_of_measurement": register.get("unit_of_measurement"),
                    "state_class": register.get("state_class"),
                    "device_class": register.get("device_class"),
                    "value_type": register.get("value_type"),
                    "filters": register.get("filters", []),
                    "message_bus": self._message_bus,
                    "config_helper": self.manager.config_helper,
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
                        step=register.get("step", 1),
                        ha_filter=register.get("ha_filter", "round(2)"),
                        **kwargs,
                    )
                elif entity_type == "writeable_sensor_discrete":
                    single_sensor = ModbusNumericWriteableEntityDiscrete(
                        coordinator=self,
                        write_address=register.get("write_address"),
                        write_filters=register.get("write_filters", []),
                        step=register.get("step", 1),
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
                "Source sensor '%s' for additional entity '%s' not found.",
                additional["source"],
                additional["name"],
            )
            return None
        single_sensor = ModbusDerivedNumericSensor(
            name=additional["name"],
            parent={NAME: self._name, ID: self._id, MODEL: self._model, "area": self._area},
            source_sensor_base_address=source_sensor.base_address,
            source_sensor_decoded_name=source_sensor.decoded_name,
            unit_of_measurement=additional.get("unit_of_measurement", "m3"),
            state_class=additional.get("state_class", "measurement"),
            device_class=additional.get("device_class", "volume"),
            value_type=None,
            filters=[],
            message_bus=self._message_bus,
            config_helper=self.manager.config_helper,
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
                "Source sensor '%s' for additional entity '%s' not found.",
                additional["source"],
                additional["name"],
            )
            return None
        single_sensor = ModbusDerivedTextSensor(
            name=additional["name"],
            parent={NAME: self._name, ID: self._id, MODEL: self._model, "area": self._area},
            source_sensor_base_address=source_sensor.base_address,
            message_bus=self._message_bus,
            config_helper=self.manager.config_helper,
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
            parent={NAME: self._name, ID: self._id, MODEL: self._model, "area": self._area},
            source_sensor_base_address=source_sensor.base_address,
            message_bus=self._message_bus,
            config_helper=self.manager.config_helper,
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
            parent={NAME: self._name, ID: self._id, MODEL: self._model, "area": self._area},
            source_sensor_base_address=source_sensor.base_address,
            message_bus=self._message_bus,
            config_helper=self.manager.config_helper,
            source_sensor_decoded_name=source_sensor.decoded_name,
            context_config={},
            value_mapping=x_mapping,
            payload_off=additional.get("payload_off", "OFF"),
            payload_on=additional.get("payload_on", "ON"),
        )
        return single_sensor

    def __init_derived_sensors__(self):
        for additional in self._db["additional_entities"]:
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

            self._additional_entities.append(
                {derived_sensor.decoded_name: derived_sensor}
            )
            self._additional_entities_by_name[derived_sensor.decoded_name] = (
                derived_sensor
            )
            if (
                derived_sensor.source_sensor_decoded_name
                not in self._additional_entities_by_source_name
            ):
                self._additional_entities_by_source_name[
                    derived_sensor.source_sensor_decoded_name
                ] = []
            self._additional_entities_by_source_name[
                derived_sensor.source_sensor_decoded_name
            ].append(derived_sensor)

    def get_entity_by_name(
        self, name: str
    ) -> None | ModbusEntity:
        """Return sensor by name."""
        for sensors in self._modbus_entities:
            if name in sensors:
                return sensors[name]
        return None

    def get_all_entities(
        self,
    ) -> list[dict[str, ModbusEntity]]:
        return self._modbus_entities

    def get_all_additional_entities(
        self,
    ) -> list[
        dict[
            str,
            ModbusDerivedNumericSensor
            | ModbusDerivedTextSensor
            | ModbusDerivedSelect
            | ModbusDerivedSwitch,
        ]
    ]:
        """Get all additional entities (derived entities).
        
        Returns:
            List of dictionaries containing additional entity entities
        """
        return self._additional_entities
    
    def get_additional_entity_by_name(self, name: str):
        """Get additional entity by decoded name.
        
        Args:
            name: Decoded name of the additional entity
            
        Returns:
            Additional entity entity or None if not found
        """
        return self._additional_entities_by_name.get(name)

    def find_entity(self, entity_id: str) -> ModbusEntity | DerivedEntity | ModbusDerivedNumericSensor | ModbusDerivedTextSensor | ModbusDerivedSelect | ModbusDerivedSwitch | None:
        """Find entity by ID or decoded name in both regular and additional entities.
        
        Args:
            entity_id: Entity ID or decoded name (e.g., "operatingmode" or "Fuji-PCoperatingmode")
            
        Returns:
            Entity object or None if not found
        """
        # Check regular entities first
        for entities in self.get_all_entities():
            # Try direct lookup by entity_id (might be decoded_name)
            if entity_id in entities:
                return entities[entity_id]
            # Try to find by full entity.id
            for entity_key, potential_entity in entities.items():
                if potential_entity.id == entity_id or potential_entity.id.lower() == entity_id.lower():
                    return potential_entity
        
        # Check additional entities if not found in regular entities
        # Try direct lookup by decoded_name
        additional_entity = self.get_additional_entity_by_name(entity_id)
        if not additional_entity:
            # If not found, try to extract decoded_name from full ID
            # Remove parent ID prefix if it matches
            coordinator_id_lower = self._id.lower()
            if entity_id.lower().startswith(coordinator_id_lower):
                decoded_name = entity_id[len(coordinator_id_lower):]
                additional_entity = self.get_additional_entity_by_name(decoded_name)
        
        # Also check all additional entities by their full ID
        if not additional_entity:
            for additional_entities_list in self.get_all_additional_entities():
                for entity_key, potential_entity in additional_entities_list.items():
                    if potential_entity.id == entity_id or potential_entity.id.lower() == entity_id.lower():
                        return potential_entity
        
        return additional_entity

    def set_payload_offline(self):
        self._payload_online = OFFLINE

    def _send_discovery_for_all_registers(self) -> datetime:
        """Send discovery message to HA for each register."""
        for sensors in self._modbus_entities:
            for sensor in sensors.values():
                sensor.send_ha_discovery()
        for sensors in self._additional_entities:
            for sensor in sensors.values():
                sensor.send_ha_discovery()
        return datetime.now()

    async def _write_derived_sensor(
        self, 
        value: str | float | int, 
        entity: ModbusDerivedEntity
    ) -> None:
        """Write value to derived sensor (select/switch).
        
        Args:
            value: Value to write (label/value from x_mapping)
            entity: Derived sensor entity
            
        Returns:
            Output dictionary with updated states
        """
        source_sensor = self.get_entity_by_name(entity.source_sensor_decoded_name)
        if not source_sensor or not source_sensor.write_address:
            _LOGGER.error(
                "Source sensor %s has no write address", 
                source_sensor.name if source_sensor else "Unknown"
            )
            return None
            
        timestamp = time.time()
        encoded_value = entity.encode_value(value)
        
        # Write to modbus
        status = await self._modbus.write_register(
            unit=self._address,
            address=source_sensor.write_address,
            value=encoded_value,
        )
        
        # Update states
        source_sensor.set_value(value=encoded_value, timestamp=timestamp)
        source_value = source_sensor.get_value()
        if source_value is not None:
            entity.evaluate_state(source_value, timestamp)
            
        _LOGGER.debug("Register written %s", status)
        
        output = {
            entity.decoded_name: entity.state,
            source_sensor.decoded_name: source_sensor.state
        }
        
        # Trigger events and send messages
        self._trigger_entity_events(entity)
        self._message_bus.send_message(
            topic=f"{self._send_topic}/{source_sensor.base_address}",
            payload=output,
        )
        
    async def _write_direct_sensor(
        self, 
        value: str | float | int, 
        entity: ModbusBaseEntity
    ) -> None:
        """Write value to direct modbus sensor.
        
        Args:
            value: Value to write
            entity: Direct sensor entity
            
        Returns:
            Output dictionary with updated states
        """
        if not hasattr(entity, 'write_address') or not entity.write_address:
            _LOGGER.error(
                "Modbus sensor %s has no write address", 
                entity.name if hasattr(entity, 'name') else 'Unknown'
            )
            return None
            
        timestamp = time.time()
        numeric_value = float(value) if isinstance(value, str) else value #21
        encoded_value = entity.encode_value(numeric_value) # 169
        
        # Write to modbus
        await self._modbus.write_register(
            unit=self._address, 
            address=entity.write_address, 
            value=encoded_value
        )
        _LOGGER.debug("Register written address: %s value: %s, encoded: %s", entity.write_address, numeric_value, encoded_value)
        
        # Update state
        entity._value = numeric_value
        entity._timestamp = timestamp
        
        output = {entity.decoded_name: entity.state}
        
        # Update additional entities if they exist
        if self._additional_entities:
            sensor_value = entity.get_value()
            if sensor_value is not None:
                if entity.decoded_name in self._additional_entities_by_source_name:
                    for additional_entity in self._additional_entities_by_source_name[
                        entity.decoded_name
                    ]:
                        additional_entity.evaluate_state(sensor_value, timestamp)
                        output[additional_entity.decoded_name] = additional_entity.state
                        # Trigger event for each derived sensor
                        self._trigger_entity_events(additional_entity)
                    
        # Trigger event for direct sensor
        self._trigger_entity_events(entity)
        self._message_bus.send_message(
            topic=f"{self._send_topic}/{entity.base_address}",
            payload=output,
        )
        
        self._timestamp = timestamp
        
    def _get_entity_type_info(self, entity: ModbusBaseEntity | ModbusDerivedEntity) -> dict[str, Any]:
        """Get entity type information for event creation.
        
        Args:
            entity: Entity to get info for
            
        Returns:
            Dictionary with entity type information
        """
        x_mapping = None
        payload_on = None
        payload_off = None
        
        if isinstance(entity, ModbusDerivedSelect):
            x_mapping = getattr(entity, '_value_mapping', None)
        elif isinstance(entity, ModbusDerivedSwitch):
            x_mapping = getattr(entity, '_value_mapping', None)
            payload_on = getattr(entity, '_payload_on', None)
            payload_off = getattr(entity, '_payload_off', None)
            
        return {
            "x_mapping": x_mapping,
            "payload_on": payload_on,
            "payload_off": payload_off
        }
        
    def _trigger_entity_events(
        self, 
        entity: ModbusBaseEntity | ModbusDerivedEntity, 
    ) -> None:
        """Trigger events for entity updates.
        
        Args:
            entity: Entity that was updated
            output: Output dictionary with states
        """
        type_info = self._get_entity_type_info(entity)
        
        self._event_bus.trigger_event(ModbusDeviceEvent(
            entity_id=entity.id,
            state=ModbusDeviceState(
                id=entity.id,
                name=entity.name,
                state=entity.state or 0.0,
                unit=getattr(entity, 'unit_of_measurement', None),
                timestamp=entity.last_timestamp,
                device_group=self.name,
                coordinator_id=self._id,
                entity_type=entity.entity_type,
                **type_info
            ),
        ))

    async def write_register(
        self, 
        value: str | float | int, 
        entity: BaseEntity
    ) -> None:
        """Write value to modbus register.
        
        Args:
            value: Value to write
            entity: Entity object (not name) to write to
        """
        _LOGGER.debug(
            "Writing register %s for %s", 
            value, 
            entity.name if hasattr(entity, 'name') else entity
        )
        
        try:
            if isinstance(entity, ModbusDerivedEntity):
                await self._write_derived_sensor(value, entity)
            elif isinstance(entity, ModbusBaseEntity):
                await self._write_direct_sensor(value, entity)
            else:
                _LOGGER.error(
                    "Cannot write to entity %s: unsupported entity type %s",
                    entity.name if hasattr(entity, 'name') else entity,
                    type(entity).__name__
                )
                return
                
            # Request update after 3 seconds to confirm the value was written correctly
            self.request_update(seconds=3)
            
        except Exception as e:
            _LOGGER.error("Error writing register for %s: %s", entity.name if hasattr(entity, 'name') else entity, e)
            raise

    async def check_availability(self) -> None:
        """Get first register and check if it's available."""
        if (
            not self._discovery_sent
            or (isinstance(self._discovery_sent, datetime) and (datetime.now() - self._discovery_sent).seconds > 3600)
        ) and self.manager.config_helper.topic_prefix:
            self._discovery_sent = False
            first_register_base = self._db["registers_base"][0]
            register_method = first_register_base.get("register_type", "input")
            # Single attempt - don't block other devices with retries
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
            else:
                _LOGGER.debug(
                    "Discovery for %s not sent yet. Device not available at address %s.",
                    self._id,
                    self._address,
                )

    def _update_sensor_and_derived(
        self, 
        sensor: ModbusBaseEntity, 
        values: Any, 
        timestamp: float
    ) -> dict[str, Any]:
        """Update sensor and its derived entities.
        
        Args:
            sensor: Sensor to update
            values: Raw modbus values
            timestamp: Update timestamp
            
        Returns:
            Output dictionary with updated states
        """
        # Decode value
        decoded_value: float | int | None = None
        
        if sensor.value_type:
            # New method using value_type
            _LOGGER.debug(
                "Using new value_type method for sensor %s: value_type=%s",
                sensor.name,
                sensor.value_type,
            )
            start_index = sensor.address - sensor.base_address
            count = VALUE_TYPES[sensor.value_type]["count"]
            payload = values.registers[start_index : start_index + count]
            try:
                decoded_value = self._modbus.decode_value(
                    payload, sensor.value_type
                )
            except Exception as e:
                _LOGGER.error(
                    "Decoding error for %s at address %s, base: %s, error %s",
                    sensor.name,
                    sensor.address,
                    sensor.base_address,
                    e,
                )
        else:
            _LOGGER.warning(
                "Sensor %s has no value_type defined",
                sensor.name,
            )
                
        # Update sensor state
        sensor.set_value(value=decoded_value, timestamp=timestamp)
        output = {sensor.decoded_name: sensor.state}
        
        # Update additional entities if they exist
        sensor_value = sensor.get_value()
        if self._additional_entities and sensor_value is not None:
            if sensor.decoded_name in self._additional_entities_by_source_name:
                for additional_entity in self._additional_entities_by_source_name[
                    sensor.decoded_name
                ]:
                    additional_entity.evaluate_state(
                        sensor_value, timestamp
                    )
                    output[additional_entity.decoded_name] = additional_entity.state
                    # Trigger event for derived sensor
                    self._trigger_entity_events(additional_entity)
                    
        # Trigger event for main sensor
        self._trigger_entity_events(sensor)
        
        return output

    async def async_update(self, timestamp: float) -> float | None:
        """Fetch state periodically and send to MQTT."""
        update_interval = self._update_interval.total_in_seconds
        await self.check_availability()
        
        for index, data in enumerate(self._db["registers_base"]):
            values = await self._modbus.read_registers(
                unit=self._address,
                address=data[BASE],
                count=data[LENGTH],
                method=data.get("register_type", "input"),
            )
            
            # Handle online/offline status
            if self._payload_online == OFFLINE and values:
                _LOGGER.info("Sending online payload about device %s.", self._name)
                self._payload_online = ONLINE
                self._message_bus.send_message(
                    topic=f"{self.manager.config_helper.topic_prefix}/modbus/{self._id}/{STATE}",
                    payload=self._payload_online,
                )
                # Send HA discovery if not sent yet (device was offline during startup)
                if not self._discovery_sent:
                    _LOGGER.info("Device %s is now available, sending HA discovery.", self._name)
                    self._discovery_sent = self._send_discovery_for_all_registers()
                
            if not values:
                if update_interval < 600:
                    # Let's wait little more for device.
                    update_interval = update_interval * 1.5
                else:
                    # Let's assume device is offline.
                    self.set_payload_offline()
                    self._message_bus.send_message(
                        topic=f"{self.manager.config_helper.topic_prefix}/modbus/{self._id}/{STATE}",
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
                
            # Update all sensors in this register group
            output = {}
            current_modbus_entities = self._modbus_entities[index]
            for sensor in current_modbus_entities.values():
                sensor_output = self._update_sensor_and_derived(sensor=sensor, values=values, timestamp=timestamp)
                output.update(sensor_output)
                
            self._timestamp = timestamp
            self._message_bus.send_message(
                topic=f"{self._send_topic}/{data[BASE]}",
                payload=output,
            )
            
        return update_interval
