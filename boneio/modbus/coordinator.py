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
    OFF,
    OFFLINE,
    ON,
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
from boneio.integration.homeassistant import modbus_polling_switch_message
from boneio.modbus.entities.base import BaseEntity, ModbusBaseEntity, ModbusDerivedEntity, ModbusParentInfo
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
from boneio.models.events import ModbusDeviceEvent, SensorEvent
from boneio.models.state import SensorState

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
        additional_data: dict | None = None,
        update_interval: TimePeriod = TimePeriod(seconds=60),
        area: str | None = None,
        has_custom_id: bool = False,
        entity_labels: dict | None = None,
    ):
        """Initialize Modbus coordinator class."""
        # Store manager reference first - needed by other init methods
        if additional_data is None:
            additional_data = {}
        self.manager = manager
        self._area = area
        self._has_custom_id = has_custom_id
        
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
        self._discovery_sent: bool | datetime = False
        self._payload_online = OFFLINE
        self._sensors_filters = {k.lower(): v for k, v in sensors_filters.items()}
        self._entity_labels: dict[str, str] = (
            {k.lower(): v for k, v in entity_labels.items()} if entity_labels else {}
        )
        
        
        self._modbus_entities: list[dict[str, ModbusEntity]] = []  # type: ignore[valid-type]
        self._modbus_entities_by_name: dict[str, ModbusEntity] = {}  # type: ignore[valid-type]
        self._additional_entities: list[dict[str, DerivedEntity]] = []  # type: ignore[valid-type]
        self._additional_entities_by_source_name: dict[str, list[DerivedEntity]] = {}  # type: ignore[valid-type]
        self._additional_entities_by_name: dict[str, DerivedEntity] = {}  # type: ignore[valid-type]
        self._additional_data = additional_data
        self._update_cycle_count = 0
        self._failed_groups: set[int] = set()  # Track register group indices that failed last read
        self._polling_enabled: bool = True  # Runtime toggle for temporarily disabling polling

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
                parent: ModbusParentInfo = {
                    "name": self._name,
                    "id": self._id,
                    "model": self._model,
                    "manufacturer": self._db.get("manufacturer", "boneIO"),
                    "area": self._area,
                    "has_custom_id": self._has_custom_id,
                }
                kwargs = {
                    "name": register.get("name"),
                    "base_address": base,
                    "register_address": register[ADDRESS],
                    "parent": parent,
                    "unit_of_measurement": register.get("unit_of_measurement"),
                    "state_class": register.get("state_class"),
                    "device_class": register.get("device_class"),
                    "entity_category": register.get("entity_category"),
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
                custom_label = self._entity_labels.get(single_sensor.decoded_name)
                if custom_label:
                    single_sensor.set_custom_label(custom_label)
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
        parent: ModbusParentInfo = {
            "name": self._name,
            "id": self._id,
            "model": self._model,
            "manufacturer": self._db.get("manufacturer", "boneIO"),
            "area": self._area,
        }
        single_sensor = ModbusDerivedNumericSensor(
            name=additional["name"],
            parent=parent,
            source_sensor_base_address=source_sensor.base_address,
            source_sensor_decoded_name=source_sensor.decoded_name,
            unit_of_measurement=additional.get("unit_of_measurement", "m3"),
            state_class=additional.get("state_class", "measurement"),
            device_class=additional.get("device_class", "volume"),
            value_type=None,
            entity_category=additional.get("entity_category"),
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
        parent: ModbusParentInfo = {
            "name": self._name,
            "id": self._id,
            "model": self._model,
            "manufacturer": self._db.get("manufacturer", "boneIO"),
            "area": self._area,
        }
        single_sensor = ModbusDerivedTextSensor(
            name=additional["name"],
            parent=parent,
            source_sensor_base_address=source_sensor.base_address,
            message_bus=self._message_bus,
            config_helper=self.manager.config_helper,
            source_sensor_decoded_name=source_sensor.decoded_name,
            context_config={},
            value_mapping=x_mapping,
            entity_category=additional.get("entity_category"),
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
        parent: ModbusParentInfo = {
            "name": self._name,
            "id": self._id,
            "model": self._model,
            "manufacturer": self._db.get("manufacturer", "boneIO"),
            "area": self._area,
        }
        single_sensor = ModbusDerivedSelect(
            name=additional["name"],
            parent=parent,
            source_sensor_base_address=source_sensor.base_address,
            message_bus=self._message_bus,
            config_helper=self.manager.config_helper,
            source_sensor_decoded_name=source_sensor.decoded_name,
            context_config={},
            value_mapping=x_mapping,
            entity_category=additional.get("entity_category"),
            coordinator=self,
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
        parent: ModbusParentInfo = {
            "name": self._name,
            "id": self._id,
            "model": self._model,
            "manufacturer": self._db.get("manufacturer", "boneIO"),
            "area": self._area,
        }
        single_sensor = ModbusDerivedSwitch(
            name=additional["name"],
            parent=parent,
            source_sensor_base_address=source_sensor.base_address,
            message_bus=self._message_bus,
            config_helper=self.manager.config_helper,
            source_sensor_decoded_name=source_sensor.decoded_name,
            context_config={},
            value_mapping=x_mapping,
            payload_off=additional.get("payload_off", "OFF"),
            payload_on=additional.get("payload_on", "ON"),
            entity_category=additional.get("entity_category"),
            coordinator=self,
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

            custom_label = self._entity_labels.get(derived_sensor.decoded_name)
            if custom_label:
                derived_sensor.set_custom_label(custom_label)

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

    def update_entity_labels(self, labels: dict[str, str]) -> None:
        """Update custom entity labels at runtime (without restart).

        Applies new labels to all modbus and derived entities and updates
        the internal labels dict.

        Args:
            labels: Dictionary mapping decoded_name to custom label.
        """
        # Step 1: Remove old HA discovery for all entities (empty payload)
        if self._discovery_sent:
            for entities_dict in self._modbus_entities:
                for sensor in entities_dict.values():
                    sensor.remove_ha_discovery()
            for entities_dict in self._additional_entities:
                for entity in entities_dict.values():
                    entity.remove_ha_discovery()

        # Step 2: Apply new labels
        self._entity_labels = {k.lower(): v for k, v in labels.items()}
        for entities_dict in self._modbus_entities:
            for sensor in entities_dict.values():
                custom_label = self._entity_labels.get(sensor.decoded_name)
                sensor.set_custom_label(custom_label)
        for entities_dict in self._additional_entities:
            for entity in entities_dict.values():
                custom_label = self._entity_labels.get(entity.decoded_name)
                entity.set_custom_label(custom_label)

        # Step 3: Re-send HA discovery with updated names
        if self._discovery_sent:
            self._send_discovery_for_all_registers()

        # Step 4: Re-trigger entity events so frontend gets updated labels via WebSocket
        for entities_dict in self._modbus_entities:
            for sensor in entities_dict.values():
                if sensor.state is not None:
                    self._trigger_entity_events(sensor)
        for entities_dict in self._additional_entities:
            for entity in entities_dict.values():
                if entity.state is not None:
                    self._trigger_entity_events(entity)
        _LOGGER.info("Updated entity labels for %s: %s", self._name, labels)

    @property
    def entity_labels(self) -> dict[str, str]:
        """Return current entity labels dict."""
        return self._entity_labels

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
            for _entity_key, potential_entity in entities.items():
                if potential_entity.id == entity_id or potential_entity.id.lower() == entity_id.lower():
                    return potential_entity
        
        # Check additional entities if not found in regular entities
        # Try direct lookup by decoded_name
        additional_entity = self.get_additional_entity_by_name(entity_id)
        if not additional_entity and entity_id.startswith("_"):
            # Strip leading underscore separator (frontend may include it)
            additional_entity = self.get_additional_entity_by_name(entity_id.lstrip("_"))
        if not additional_entity:
            # If not found, try to extract decoded_name from full ID
            # Remove parent ID prefix if it matches
            coordinator_id_lower = self._id.lower()
            if entity_id.lower().startswith(coordinator_id_lower):
                decoded_name = entity_id[len(coordinator_id_lower):].lstrip("_")
                additional_entity = self.get_additional_entity_by_name(decoded_name)
        
        # Also check all additional entities by their full ID
        if not additional_entity:
            for additional_entities_list in self.get_all_additional_entities():
                for _entity_key, potential_entity in additional_entities_list.items():
                    if potential_entity.id == entity_id or potential_entity.id.lower() == entity_id.lower():
                        return potential_entity
        
        return additional_entity

    @property
    def polling_enabled(self) -> bool:
        """Return whether polling is currently enabled for this device."""
        return self._polling_enabled

    def set_polling_enabled(self, enabled: bool) -> None:
        """Enable or disable periodic polling for this Modbus device.

        This is a runtime-only toggle — state does NOT persist across restarts.
        When disabled, the coordinator keeps last known sensor values but
        stops reading registers. Entities remain available in HA with stale data.

        Args:
            enabled: True to enable polling, False to disable.
        """
        if enabled == self._polling_enabled:
            return
        self._polling_enabled = enabled
        state = ON if enabled else OFF
        _LOGGER.info(
            "Polling %s for Modbus device %s",
            "enabled" if enabled else "disabled",
            self._name,
        )
        # Publish new switch state to MQTT
        self._message_bus.send_message(
            topic=f"{self.manager.config_helper.topic_prefix}/modbus/{self._id}/polling",
            payload={"state": state},
            retain=True,
        )
        if enabled:
            # Force immediate update when re-enabled
            self.request_update(seconds=0)

    def set_payload_offline(self):
        self._payload_online = OFFLINE

    async def send_online_status(self):
        """Send online status to availability topic.
        
        This is used when coordinator is created/recreated (e.g., after reload with ID change)
        to immediately publish online status to the new availability topic.
        """
        try:
            # Try to read first register to check if device is available
            first_register_base = self._db["registers_base"][0]
            register_method = first_register_base.get("register_type", "input")
            register = await self._modbus.read_and_decode(
                unit=self._address,
                address=first_register_base[REGISTERS][0][ADDRESS],
                method=register_method,
                payload_type=first_register_base[REGISTERS][0].get("value_type", "FP32"),
            )
            
            if register is not None:
                # Device is available, send online status
                self._payload_online = ONLINE
                self._message_bus.send_message(
                    topic=f"{self.manager.config_helper.topic_prefix}/modbus/{self._id}/{STATE}",
                    payload=self._payload_online,
                    retain=True,
                )
                _LOGGER.info("Sent online status for Modbus device %s to new availability topic", self._name)
            else:
                _LOGGER.debug("Device %s not available, skipping online status", self._name)
        except Exception as e:
            _LOGGER.debug("Could not send online status for %s: %s", self._name, e)

    def _send_polling_switch_discovery(self) -> None:
        """Send HA MQTT autodiscovery for the polling enable/disable switch.

        The switch appears under the Modbus device in HA with entity_category
        'config' and allows the user to temporarily stop/start register polling.
        """

        payload = modbus_polling_switch_message(
            device_id=self._id,
            device_name=self._name,
            model=self._model,
            manufacturer=self._db.get("manufacturer", "boneIO"),
            config_helper=self.manager.config_helper,
            area=self._area,
        )
        topic = payload.pop("_topic")
        self.manager.config_helper.add_autodiscovery_msg(
            topic=topic, payload=payload, ha_type="switch",
        )
        self._message_bus.send_message(topic=topic, payload=payload, retain=True)
        # Publish current state so HA shows correct initial value
        self._message_bus.send_message(
            topic=f"{self.manager.config_helper.topic_prefix}/modbus/{self._id}/polling",
            payload={"state": ON if self._polling_enabled else OFF},
            retain=True,
        )

    def _send_discovery_for_all_registers(self) -> datetime:
        """Send discovery message to HA for each register."""
        for sensors in self._modbus_entities:
            for sensor in sensors.values():
                sensor.send_ha_discovery()
        for sensors in self._additional_entities:
            for sensor in sensors.values():
                sensor.send_ha_discovery()
        self._send_polling_switch_discovery()
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
        if not source_sensor or source_sensor.write_address is None:
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
        if not hasattr(entity, 'write_address') or entity.write_address is None:
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
            if sensor_value is not None and entity.decoded_name in self._additional_entities_by_source_name:
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
        
    def _get_entity_label(self, entity: ModbusBaseEntity | ModbusDerivedEntity) -> str | None:
        """Get custom label for entity from YAML config.

        Args:
            entity: Entity to look up label for.

        Returns:
            Custom label string or None if no custom label is set.
        """
        return self._entity_labels.get(entity.decoded_name)

    def _trigger_entity_events(
        self, 
        entity: ModbusBaseEntity | ModbusDerivedEntity, 
    ) -> None:
        """Trigger events for entity updates.
        
        Emits ModbusDeviceEvent for all entities. Additionally emits
        SensorEvent for any entity that acts as a sensor, so standard
        components (like thermostats) can listen to sensor updates natively.
        
        Args:
            entity: Entity that was updated
        """
        type_info = self._get_entity_type_info(entity)
        custom_label = self._get_entity_label(entity)
        
        device_state = ModbusDeviceState(
            id=entity.id,
            name=entity.name,
            state=entity.state or 0.0,
            unit=getattr(entity, 'unit_of_measurement', None),
            timestamp=entity.last_timestamp,
            device_group=self.name,
            coordinator_id=self._id,
            entity_type=entity.entity_type,
            custom_label=custom_label,
            **type_info
        )

        self._event_bus.trigger_event(ModbusDeviceEvent(
            entity_id=entity.id,
            state=device_state,
        ))

        # Also emit dedicated SensorEvent for generic sensor integration 
        # (thermostats, rules, etc. shouldn't care about transport type)
        if entity.entity_type in (SENSOR, TEXT_SENSOR):
            display_name = custom_label or entity.name
            _LOGGER.debug(
                "Emitting SensorEvent: entity_id='%s', name='%s', state=%s",
                entity.id, display_name, entity.state,
            )
            self._event_bus.trigger_event(SensorEvent(
                entity_id=entity.id,
                state=SensorState(
                    id=entity.id,
                    name=display_name,
                    state=entity.state or 0.0,
                    unit=getattr(entity, 'unit_of_measurement', None),
                    timestamp=entity.last_timestamp,
                )
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
        if (
            self._additional_entities
            and sensor_value is not None
            and sensor.decoded_name in self._additional_entities_by_source_name
        ):
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
        # Skip update when polling is disabled by user
        if not self._polling_enabled:
            _LOGGER.debug(
                "Polling disabled, skipping update for %s",
                self._name,
            )
            return self._update_interval.total_in_seconds
        # Skip update when Tools Modbus page is active
        if self._modbus.is_suspended:
            _LOGGER.debug(
                "Modbus suspended (Tools active), skipping update for %s",
                self._name,
            )
            return self._update_interval.total_in_seconds
        update_interval = self._update_interval.total_in_seconds
        await self.check_availability()
        self._update_cycle_count += 1
        
        for index, data in enumerate(self._db["registers_base"]):
            # Skip this register group if update_every_n is set and not due,
            # BUT always retry if previous read for this group failed
            update_every_n = data.get("update_every_n")
            if update_every_n and self._update_cycle_count % update_every_n != 1:
                if index not in self._failed_groups:
                    continue
                _LOGGER.debug(
                    "Retrying failed register group %d (base=%s) for %s",
                    index, data.get(BASE), self._name,
                )
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
                    retain=True,
                )
                # Send HA discovery if not sent yet (device was offline during startup)
                if not self._discovery_sent:
                    _LOGGER.info("Device %s is now available, sending HA discovery.", self._name)
                    self._discovery_sent = self._send_discovery_for_all_registers()
                # Force-read all update_every_n groups this cycle
                # (they may have been skipped if device wasn't online on cycle 1)
                for i, d in enumerate(self._db["registers_base"]):
                    if d.get("update_every_n"):
                        self._failed_groups.add(i)
                
            if not values:
                # Mark this group as failed so it retries next cycle
                self._failed_groups.add(index)
                
                # For groups with update_every_n, just skip — don't abort entire update
                if update_every_n:
                    _LOGGER.warning(
                        "Can't fetch data from modbus device %s (group %d, base=%s, update_every_n=%d). "
                        "Will retry next cycle.",
                        self.id, index, data.get(BASE), update_every_n,
                    )
                    continue
                
                if update_interval < 600:
                    # Let's wait little more for device.
                    update_interval = update_interval * 1.5
                else:
                    # Let's assume device is offline.
                    self.set_payload_offline()
                    self._message_bus.send_message(
                        topic=f"{self.manager.config_helper.topic_prefix}/modbus/{self._id}/{STATE}",
                        payload=self._payload_online,
                        retain=True,
                    )
                    self._discovery_sent = False
                _LOGGER.warning(
                    "Can't fetch data from modbus device %s (group %d, base=%s). Will sleep for %s seconds",
                    self.id,
                    index,
                    data.get(BASE),
                    update_interval,
                )
                return update_interval
            else:
                # Read succeeded — clear failed flag for this group
                self._failed_groups.discard(index)
                if update_interval != self._update_interval.total_in_seconds:
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
