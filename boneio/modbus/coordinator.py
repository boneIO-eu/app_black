from __future__ import annotations

import asyncio
import logging
import math
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal, Union

from pymodbus.pdu import ExceptionResponse

from boneio.const import (
    BINARY_SENSOR,
    BUTTON,
    ID,
    NUMERIC,
    OFF,
    OFFLINE,
    ON,
    ONLINE,
    SELECT,
    SENSOR,
    STATE,
    SWITCH,
    TEXT_SENSOR,
)
from boneio.core.messaging import BasicMqtt
from boneio.core.utils import AsyncUpdater, Filter
from boneio.core.utils.timeperiod import TimePeriod
from boneio.integration.homeassistant import (
    modbus_climate_availability_message,
    modbus_polling_switch_message,
    modbus_water_heater_availability_message,
)
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
from boneio.modbus.entities.writeable.button import ModbusButton
from boneio.modbus.entities.writeable.numeric import (
    ModbusNumericWriteableEntity,
    ModbusNumericWriteableEntityDiscrete,
)
from boneio.models.events import ModbusDeviceEvent, ModbusStatusEvent, SensorEvent
from boneio.models.state import SensorState

from .client import VALUE_TYPES, Modbus
from .definition import (
    AdditionalEntity,
    AdditionalSelect,
    AdditionalSensor,
    AdditionalSwitch,
    AdditionalTextSensor,
    DeviceDefinition,
    load_definition,
)
from .heat_pump import ROLE_KINDS, SCHEMES, Write
from .heat_pump import state as heat_pump_state

# Type aliases for cleaner code
ModbusEntity = Union[
    ModbusNumericSensor,
    ModbusNumericWriteableEntity,
    ModbusNumericWriteableEntityDiscrete,
    ModbusBinarySensor,
    ModbusBinaryWriteableEntityDiscrete,
    ModbusButton,
    ModbusTextSensor,
]
DerivedEntity = Union[
    ModbusDerivedNumericSensor,
    ModbusDerivedTextSensor,
    ModbusDerivedSelect,
    ModbusDerivedSwitch,
]


_LOGGER = logging.getLogger(__name__)

# An optional register block that fails this many polls in a row is skipped:
# on RS485 every miss holds the shared bus for the whole timeout. It is tried
# again once per OPTIONAL_RETRY_S.
OPTIONAL_GIVE_UP = 3
OPTIONAL_RETRY_S = 3600

# Entity types whose Home Assistant discovery carries a command topic.
COMMAND_ENTITY_TYPES = (NUMERIC, SELECT, SWITCH, BUTTON)

# Heat pump thermostat limits when the target register gives none.
HEAT_PUMP_MIN_TEMP = 5
HEAT_PUMP_MAX_TEMP = 60
HEAT_PUMP_TEMP_STEP = 0.5


class ModbusWriteRejected(Exception):
    """A write was refused before it reached the bus."""


class ModbusCoordinator(BasicMqtt, AsyncUpdater, Filter):
    """Represent Modbus coordinator in BoneIO."""

    DefaultName = "ModbusCoordinator"
    # Never mutated; the instance gets its own.
    _entity_visibility: dict[str, dict] = {}
    _registers_by_name: dict = {}
    # Last heat pump state sent to MQTT, so it goes out only when it changes.
    _published_heat_pump: dict | None = None

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
        read_only: bool = False,
        entity_visibility: dict | None = None,
    ):
        """Initialize Modbus coordinator class."""
        # Store manager reference first - needed by other init methods
        if additional_data is None:
            additional_data = {}
        self.manager = manager
        self._area = area
        self._has_custom_id = has_custom_id
        self._read_only = read_only
        
        BasicMqtt.__init__(
            self,
            id=id or address,
            name=name,
            topic_type="modbus",
            topic_prefix=manager.config_helper.topic_prefix,
            message_bus=manager._message_bus,
        )
        self._modbus = modbus
        self._definition = load_definition(model)
        self._model = self._definition.model
        self._address = address
        self._discovery_sent: bool | datetime = False
        self._payload_online = OFFLINE
        self._sensors_filters = {k.lower(): v for k, v in sensors_filters.items()}
        self._entity_labels: dict[str, str] = (
            {k.lower(): v for k, v in entity_labels.items()} if entity_labels else {}
        )
        self._entity_visibility: dict[str, dict] = {
            k.lower(): dict(v) for k, v in (entity_visibility or {}).items()
        }

        self._modbus_entities: list[dict[str, ModbusEntity]] = []  # type: ignore[valid-type]
        # Entities of "coil" blocks: written with FC05 instead of FC06.
        self._coil_entities: set[ModbusBaseEntity] = set()
        self._modbus_entities_by_name: dict[str, ModbusEntity] = {}  # type: ignore[valid-type]
        self._additional_entities: list[dict[str, DerivedEntity]] = []  # type: ignore[valid-type]
        self._additional_entities_by_source_name: dict[str, list[DerivedEntity]] = {}  # type: ignore[valid-type]
        self._additional_entities_by_name: dict[str, DerivedEntity] = {}  # type: ignore[valid-type]
        self._additional_data = additional_data
        self._update_cycle_count = 0
        self._failed_groups: set[int] = set()  # Track register group indices that failed last read
        # Groups whose current run of failures has already been logged at
        # WARNING. Separate from _failed_groups, which is also filled to force
        # a re-read and so does not mean "a failure was reported".
        self._reported_groups: set[int] = set()
        # Optional blocks: consecutive failed reads and the time of the last try.
        self._optional_misses: dict[int, int] = {}
        self._optional_last_try: dict[int, float] = {}
        # Last ``failing`` sent to the panel, so it hears only the changes.
        self._published_failing = False
        self._polling_enabled: bool = True  # Runtime toggle for temporarily disabling polling

        self.__init_modbus_entities__()
        # Additional entities
        if self._definition.additional_entities:
            self.__init_derived_sensors__()
        self._warn_unknown_visibility_entries()

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

        # Discovery goes out once the device has answered, which may be long
        # after startup or never. Until then the entities still belong to
        # this controller, and their retained configs must outlive the
        # cleanup of unused ones.
        self._reserve_discovery_for_all_registers()

    @property
    def definition(self) -> DeviceDefinition:
        return self._definition

    def __init_modbus_entities__(self):
        self._registers_by_name = {
            register.decoded_name: register
            for block in self._definition.registers_base
            for register in block.registers
        }
        # Standard sensors
        for index, block in enumerate(self._definition.registers_base):
            self._modbus_entities.append({})
            for register in block.registers:
                entity_type = register.entity_type
                parent: ModbusParentInfo = {
                    "name": self._name,
                    "id": self._id,
                    "model": self._model,
                    "manufacturer": self._definition.manufacturer,
                    "area": self._area,
                    "has_custom_id": self._has_custom_id,
                }
                kwargs = {
                    "name": register.name,
                    "base_address": block.base,
                    "register_address": register.address,
                    "parent": parent,
                    "unit_of_measurement": register.unit_of_measurement,
                    "state_class": register.state_class,
                    "device_class": register.device_class,
                    "entity_category": register.entity_category,
                    "value_type": register.value_type,
                    "filters": list(register.filters),
                    "message_bus": self._message_bus,
                    "config_helper": self.manager.config_helper,
                }
                if entity_type == SENSOR:
                    single_sensor = ModbusNumericSensor(
                        ha_filter=register.ha_filter,
                        **kwargs)
                elif entity_type == TEXT_SENSOR:
                    single_sensor = ModbusTextSensor(
                        value_mapping=dict(register.x_mapping), **kwargs
                    )
                elif entity_type == BINARY_SENSOR:
                    single_sensor = ModbusBinarySensor(
                        payload_on=register.payload_on,
                        payload_off=register.payload_off,
                        **kwargs,
                    )
                elif entity_type == "writeable_sensor":
                    single_sensor = ModbusNumericWriteableEntity(
                        coordinator=self,
                        write_filters=list(register.write_filters),
                        write_address=register.write_address,
                        step=1 if register.step is None else register.step,
                        min_value=register.min,
                        max_value=register.max,
                        ha_filter=register.ha_filter,
                        **kwargs,
                    )
                elif entity_type == "writeable_sensor_discrete":
                    single_sensor = ModbusNumericWriteableEntityDiscrete(
                        coordinator=self,
                        write_address=register.write_address,
                        write_filters=list(register.write_filters),
                        step=1 if register.step is None else register.step,
                        min_value=register.min,
                        max_value=register.max,
                        ha_filter=register.ha_filter,
                        **kwargs,
                    )
                elif entity_type == "writeable_binary_sensor_discrete":
                    single_sensor = ModbusBinaryWriteableEntityDiscrete(
                        coordinator=self,
                        write_address=register.write_address,
                        payload_on=register.payload_on,
                        payload_off=register.payload_off,
                        write_filters=list(register.write_filters),
                        **kwargs,
                    )
                elif entity_type == BUTTON:
                    single_sensor = ModbusButton(
                        coordinator=self,
                        write_address=register.write_address,
                        write_value=register.write_value,
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
                if block.register_type == "coil":
                    self._coil_entities.add(single_sensor)

    def _find_source_sensor(self, additional: AdditionalEntity):
        """Register entity an additional entity is derived from, if any."""
        if isinstance(additional.source, str):
            wanted = additional.source.replace("_", "")
            for sensors in self._modbus_entities:
                for s in sensors.values():
                    if s.decoded_name == wanted:
                        return s
        _LOGGER.warning(
            "Source sensor '%s' for additional entity '%s' not found.",
            additional.source,
            additional.name,
        )
        return None

    def _parent_info(self) -> ModbusParentInfo:
        return {
            "name": self._name,
            "id": self._id,
            "model": self._model,
            "manufacturer": self._definition.manufacturer,
            "area": self._area,
        }

    def __init_derived_numeric(
        self, additional: AdditionalSensor
    ) -> ModbusDerivedNumericSensor | None:
        config_keys = additional.config_keys or []
        if not self._additional_data:
            return None
        if not all(k in self._additional_data for k in config_keys):
            return None
        source_sensor = self._find_source_sensor(additional)
        if not source_sensor:
            return None
        return ModbusDerivedNumericSensor(
            name=additional.name,
            parent=self._parent_info(),
            source_sensor_base_address=source_sensor.base_address,
            source_sensor_decoded_name=source_sensor.decoded_name,
            unit_of_measurement=additional.unit_of_measurement or "m3",
            state_class=additional.state_class or "measurement",
            device_class=additional.device_class or "volume",
            value_type=None,
            entity_category=additional.entity_category,
            filters=[],
            message_bus=self._message_bus,
            config_helper=self.manager.config_helper,
            ha_filter="round(2)",
            formula=additional.formula or "",
            context_config={
                k: v for k, v in self._additional_data.items() if k in config_keys
            },
        )

    def __init_derived_text_sensor(
        self, additional: AdditionalTextSensor
    ) -> ModbusDerivedTextSensor | None:
        source_sensor = self._find_source_sensor(additional)
        if not source_sensor:
            return None
        return ModbusDerivedTextSensor(
            name=additional.name,
            parent=self._parent_info(),
            source_sensor_base_address=source_sensor.base_address,
            message_bus=self._message_bus,
            config_helper=self.manager.config_helper,
            source_sensor_decoded_name=source_sensor.decoded_name,
            context_config={},
            value_mapping=dict(additional.x_mapping),
            entity_category=additional.entity_category,
        )

    def __init_derived_select(
        self, additional: AdditionalSelect
    ) -> ModbusDerivedSelect | None:
        source_sensor = self._find_source_sensor(additional)
        if not source_sensor:
            return None
        return ModbusDerivedSelect(
            name=additional.name,
            parent=self._parent_info(),
            source_sensor_base_address=source_sensor.base_address,
            message_bus=self._message_bus,
            config_helper=self.manager.config_helper,
            source_sensor_decoded_name=source_sensor.decoded_name,
            context_config={},
            value_mapping=dict(additional.x_mapping),
            entity_category=additional.entity_category,
            coordinator=self,
        )

    def __init_derived_switch(
        self, additional: AdditionalSwitch
    ) -> ModbusDerivedSwitch | None:
        source_sensor = self._find_source_sensor(additional)
        if not source_sensor:
            return None
        return ModbusDerivedSwitch(
            name=additional.name,
            parent=self._parent_info(),
            source_sensor_base_address=source_sensor.base_address,
            message_bus=self._message_bus,
            config_helper=self.manager.config_helper,
            source_sensor_decoded_name=source_sensor.decoded_name,
            context_config={},
            value_mapping=dict(additional.x_mapping),
            payload_off=additional.payload_off,
            payload_on=additional.payload_on,
            entity_category=additional.entity_category,
            coordinator=self,
        )

    def __init_derived_sensors__(self):
        for additional in self._definition.additional_entities:
            entity_type = additional.entity_type
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
            first_block = self._definition.registers_base[0]
            register = await self._modbus.read_and_decode(
                unit=self._address,
                address=first_block.registers[0].address,
                method=first_block.register_type,
                payload_type=first_block.registers[0].value_type,
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

    def _polling_switch_discovery(self) -> tuple[str, dict]:
        """Topic and payload of the polling enable/disable switch."""
        payload = modbus_polling_switch_message(
            device_id=self._id,
            device_name=self._name,
            model=self._model,
            manufacturer=self._definition.manufacturer,
            config_helper=self.manager.config_helper,
            area=self._area,
        )
        return payload.pop("_topic"), payload

    def _send_polling_switch_discovery(self) -> None:
        """Send HA MQTT autodiscovery for the polling enable/disable switch.

        The switch appears under the Modbus device in HA with entity_category
        'config' and allows the user to temporarily stop/start register polling.
        """
        topic, payload = self._polling_switch_discovery()
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

    def _register_of(self, entity):
        """Register an entity is read from; a derived entity has its source's."""
        name = getattr(entity, "source_sensor_decoded_name", None) or entity.decoded_name
        return self._registers_by_name.get(name)

    def visible(self, entity, where: Literal["panel", "ha"]) -> bool:
        """Whether the entity shows in the panel or in Home Assistant.

        The user's entry wins; without one the register's ``hidden`` decides.
        A derived entity also takes the entry of its source register, its own
        entry first. Visibility never limits writes.
        """
        names = [entity.decoded_name]
        source = getattr(entity, "source_sensor_decoded_name", None)
        if source:
            names.append(source)
        for name in names:
            choice = self._entity_visibility.get(name, {}).get(where)
            if choice is not None:
                return bool(choice)
        register = self._register_of(entity)
        return not (register and register.hidden)

    def confirm_required(self, entity) -> bool:
        """Whether the panel asks before writing to the entity."""
        register = self._register_of(entity)
        return bool(register and register.confirm)

    def _warn_unknown_visibility_entries(self) -> None:
        known = {
            *self._registers_by_name,
            *(name for entities in self._additional_entities for name in entities),
        }
        for name in self._entity_visibility.keys() - known:
            _LOGGER.warning(
                "%s: entity_visibility has '%s', which this device does not have; ignored",
                self._name,
                name,
            )

    def _announced_entities(self):
        """Entities Home Assistant gets: a read-only device offers no controls."""
        for entities in (*self._modbus_entities, *self._additional_entities):
            for entity in entities.values():
                if self._read_only and entity.entity_type in COMMAND_ENTITY_TYPES:
                    continue
                if not self.visible(entity, "ha"):
                    continue
                yield entity

    def _reserve_discovery_for_all_registers(self) -> None:
        """Claim every discovery topic of this device without announcing it."""
        for entity in self._announced_entities():
            entity.reserve_ha_discovery()
        topic, _ = self._polling_switch_discovery()
        self.manager.config_helper.reserve_autodiscovery_msg(ha_type="switch", topic=topic)
        for ha_type, topic, _ in self._heat_pump_discovery():
            self.manager.config_helper.reserve_autodiscovery_msg(ha_type=ha_type, topic=topic)

    def _send_discovery_for_all_registers(self) -> datetime:
        """Send discovery message to HA for each register."""
        for entity in self._announced_entities():
            entity.send_ha_discovery()
        self._send_polling_switch_discovery()
        for ha_type, topic, payload in self._heat_pump_discovery():
            self.manager.config_helper.add_autodiscovery_msg(
                topic=topic, payload=payload, ha_type=ha_type
            )
            self._message_bus.send_message(topic=topic, payload=payload, retain=True)
        return datetime.now()

    def _role_entity(self, role: str, ref: str | None = None):
        """Entity a heat pump role names: a derived switch, or a register.

        Visibility plays no part: a hidden entity still serves its role.
        """
        if ref is None:
            ref = self._definition.heat_pump.roles[role]
        key = ref.replace(" ", "").lower()
        if ROLE_KINDS[role] == "switch":
            return self._additional_entities_by_name.get(key)
        return self.get_entity_by_name(key)

    def heat_pump_values(self) -> dict[str, Any]:
        """Role -> value as the heat pump schemes read it; ``None`` while unknown.

        Switches give "ON"/"OFF", numbers their engineering value, a text
        sensor its raw register value (not the label), a binary sensor its
        state. A role naming several entities gives a list.
        """
        spec = self._definition.heat_pump
        if spec is None:
            return {}
        values: dict[str, Any] = {}
        for role, ref in spec.roles.items():
            found = [
                self._role_entity(role, name)
                for name in ([ref] if isinstance(ref, str) else ref)
            ]
            got = [
                None if e is None
                else e.raw_value if isinstance(e, ModbusTextSensor)
                else e.get_value()
                for e in found
            ]
            values[role] = got[0] if isinstance(ref, str) else got
        return values

    def heat_pump_state(self) -> dict | None:
        """Thermostat and hot water state, or None for a device that is no heat pump."""
        spec = self._definition.heat_pump
        if spec is None:
            return None
        return heat_pump_state(SCHEMES[spec.scheme], self.heat_pump_values())

    def _publish_heat_pump_state(self) -> None:
        """Send the heat pump state, retained, when it differs from the last one sent."""
        current = self.heat_pump_state()
        if current is None or current == self._published_heat_pump:
            return
        self._published_heat_pump = current
        self._message_bus.send_message(
            topic=f"{self.manager.config_helper.topic_prefix}/modbus/{self._id}/heat_pump",
            payload=current,
            retain=True,
        )

    def _heat_pump_limits(self, role: str) -> tuple[float, float, float]:
        """min, max and step of the role's register, or the thermostat fallbacks."""
        register = self._register_of(self._role_entity(role))
        low = getattr(register, "min", None)
        high = getattr(register, "max", None)
        step = getattr(register, "step", None)
        return (
            HEAT_PUMP_MIN_TEMP if low is None else low,
            HEAT_PUMP_MAX_TEMP if high is None else high,
            HEAT_PUMP_TEMP_STEP if step is None else step,
        )

    def _heat_pump_discovery(self) -> list[tuple[str, str, dict]]:
        """(ha_type, topic, payload) of the climate and water heater.

        Empty for a device that is no heat pump and for a read-only one,
        which offers no controls.
        """
        spec = self._definition.heat_pump
        if spec is None or self._read_only:
            return []
        device = {
            "device_id": self._id,
            "device_name": self._name,
            "model": self._model,
            "manufacturer": self._definition.manufacturer,
            "config_helper": self.manager.config_helper,
            "area": self._area,
        }
        low, high, step = self._heat_pump_limits("heating_target")
        climate = modbus_climate_availability_message(
            **device,
            modes=list(SCHEMES[spec.scheme].modes),
            min_temp=low,
            max_temp=high,
            temp_step=step,
        )
        low, high, _ = self._heat_pump_limits("dhw_target")
        water_heater = modbus_water_heater_availability_message(
            **device, min_temp=low, max_temp=high
        )
        return [
            ("climate", climate.pop("_topic"), climate),
            ("water_heater", water_heater.pop("_topic"), water_heater),
        ]

    async def set_heat_pump(
        self, field: Literal["mode", "temperature", "dhw_mode", "dhw_temperature"], value: str
    ) -> None:
        """Carry out a thermostat or hot water command from Home Assistant.

        ``field`` is mode, temperature, dhw_mode or dhw_temperature. Every
        write the command needs is checked before the first is sent, so a
        refused one leaves the device as it was. Raises ModbusWriteRejected.
        """
        spec = self._definition.heat_pump
        if spec is None:
            raise ModbusWriteRejected(f"{self._name} is not a heat pump")
        scheme = SCHEMES[spec.scheme]
        v = self.heat_pump_values()
        if field == "mode":
            if value not in scheme.modes:
                raise ModbusWriteRejected(f"{self._name}: no mode {value!r}")
            writes = scheme.set_hvac_mode(v, value)
        elif field == "dhw_mode":
            if value not in ("off", "heat_pump"):
                raise ModbusWriteRejected(f"{self._name}: no hot water mode {value!r}")
            writes = scheme.set_dhw_mode(v, value)
        elif field in ("temperature", "dhw_temperature"):
            try:
                number = float(value)
            except (TypeError, ValueError):
                raise ModbusWriteRejected(f"{self._name}: '{value}' is not a number") from None
            if not math.isfinite(number):
                raise ModbusWriteRejected(f"{self._name}: {value} is not a finite number")
            role = scheme.target_role(v) if field == "temperature" else "dhw_target"
            writes = [Write(role, number)]
        else:
            raise ModbusWriteRejected(f"{self._name}: unknown heat pump field {field!r}")

        planned = []
        for write in writes:
            entity = self._role_entity(write.role)
            if entity is None:
                raise ModbusWriteRejected(f"{self._name}: heat pump role {write.role!r} has no entity")
            self._check_write_allowed(write.value, entity)
            planned.append((entity, write.value))
        for entity, target in planned:
            await self.write_register(target, entity)
        self._publish_heat_pump_state()

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
            coil=source_sensor in self._coil_entities,
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
            value=encoded_value,
            coil=entity in self._coil_entities,
        )
        _LOGGER.debug("Register written address: %s value: %s, encoded: %s", entity.write_address, numeric_value, encoded_value)
        
        # Update state
        entity._value = numeric_value
        entity._timestamp = timestamp
        
        output = {} if entity.entity_type == BUTTON else {entity.decoded_name: entity.state}
        
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
        if output:
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
            "payload_off": payload_off,
            "min": getattr(entity, "min_value", None),
            "max": getattr(entity, "max_value", None),
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
            area=self._area,
            confirm=self.confirm_required(entity),
            **type_info
        )

        if self.visible(entity, "panel"):
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

    def _check_write_allowed(self, value: str | float | int, entity: BaseEntity) -> None:
        """Refuse a write the device must never get: read-only, or out of range.

        The range applies to the value as the user gives it, before write_filters.
        """
        name = getattr(entity, "name", entity)
        if self._read_only:
            raise ModbusWriteRejected(f"{self._name} is read only")
        low = getattr(entity, "min_value", None)
        high = getattr(entity, "max_value", None)
        if low is None and high is None:
            return
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ModbusWriteRejected(f"{name}: '{value}' is not a number") from None
        if not math.isfinite(number):
            raise ModbusWriteRejected(f"{name}: {value} is not a finite number")
        if (low is not None and number < low) or (high is not None and number > high):
            raise ModbusWriteRejected(
                f"{name}: {value} is outside the allowed range {low if low is not None else '-'}..{high if high is not None else '-'}"
            )

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
        self._check_write_allowed(value, entity)
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
            first_block = self._definition.registers_base[0]
            # Single attempt - don't block other devices with retries
            register = await self._modbus.read_and_decode(
                unit=self._address,
                address=first_block.registers[0].address,
                method=first_block.register_type,
                payload_type=first_block.registers[0].value_type,
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

    @property
    def failing(self) -> bool:
        """A register group of this device fails to read right now."""
        return bool(self._reported_groups)

    async def async_update(self, timestamp: float) -> float | None:
        """Fetch state periodically and tell the panel when the device
        starts or stops failing.

        A dead device sends no entity events at all, so the panel cannot tell
        it from a quiet one without this.
        """
        interval = await self._poll(timestamp)
        self._publish_heat_pump_state()
        if self.failing != self._published_failing:
            self._published_failing = self.failing
            self._event_bus.trigger_event(ModbusStatusEvent(entity_id=self._id, failing=self.failing))
        return interval

    async def _poll(self, timestamp: float) -> float | None:
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
        
        for index, data in enumerate(self._definition.registers_base):
            # Skip this register group if update_every_n is set and not due,
            # BUT always retry if previous read for this group failed
            update_every_n = data.update_every_n
            if update_every_n and self._update_cycle_count % update_every_n != 1:
                if index not in self._failed_groups:
                    continue
                _LOGGER.debug(
                    "Retrying failed register group %d (base=%s) for %s",
                    index, data.base, self._name,
                )
            if data.optional:
                if (
                    self._optional_misses.get(index, 0) >= OPTIONAL_GIVE_UP
                    and timestamp - self._optional_last_try[index] < OPTIONAL_RETRY_S
                ):
                    continue
                self._optional_last_try[index] = timestamp
            values = await self._modbus.read_registers(
                unit=self._address,
                address=data.base,
                count=data.length,
                method=data.register_type,
            )
            # The client hands an exception response back as is, because the
            # modbus CLI prints its code. Here it is a failed read of this
            # group: pymodbus 3.x gives it an empty ``registers``, so taken as
            # data it marked the device ONLINE and every sensor then failed to
            # decode it, at ERROR, on every poll. It is not "no response"
            # either - the device answered, it just refuses this block (a
            # model variant without it, a wrong register map) - so the other
            # groups are still read, nothing backs off, and only a real read
            # brings the device ONLINE.
            if data.optional and (isinstance(values, ExceptionResponse) or not values):
                # A unit without this block is not failing: it neither backs
                # off nor shows as failing, and only the first miss is logged.
                misses = self._optional_misses.get(index, 0) + 1
                self._optional_misses[index] = misses
                if misses == 1 or misses == OPTIONAL_GIVE_UP:
                    _LOGGER.info(
                        "Modbus device %s has no optional register group %d (base=%s)%s",
                        self.id, index, data.base,
                        f", retrying every {OPTIONAL_RETRY_S} s" if misses == OPTIONAL_GIVE_UP else "",
                    )
                continue

            if isinstance(values, ExceptionResponse):
                self._failed_groups.add(index)
                level = logging.INFO if index in self._reported_groups else logging.WARNING
                self._reported_groups.add(index)
                _LOGGER.log(
                    level,
                    "Modbus device %s refused register group %d (base=%s): %s",
                    self.id, index, data.base, values,
                )
                continue

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
                for i, d in enumerate(self._definition.registers_base):
                    if d.update_every_n:
                        self._failed_groups.add(i)
                
            if not values:
                # Mark this group as failed so it retries next cycle
                self._failed_groups.add(index)
                # A dead device fails every cycle, forever. Warn when the
                # failure starts, then drop to INFO until it answers, so
                # anything read at warning level is not buried by it.
                level = logging.INFO if index in self._reported_groups else logging.WARNING
                self._reported_groups.add(index)
                
                # For groups with update_every_n, just skip — don't abort entire update
                if update_every_n:
                    _LOGGER.log(
                        level,
                        "Can't fetch data from modbus device %s (group %d, base=%s, update_every_n=%d). "
                        "Will retry next cycle.",
                        self.id, index, data.base, update_every_n,
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
                _LOGGER.log(
                    level,
                    "Can't fetch data from modbus device %s (group %d, base=%s). Will sleep for %s seconds",
                    self.id,
                    index,
                    data.base,
                    update_interval,
                )
                return update_interval
            else:
                # Read succeeded — clear failed flag for this group
                self._optional_misses.pop(index, None)
                self._failed_groups.discard(index)
                self._reported_groups.discard(index)
                if update_interval != self._update_interval.total_in_seconds:
                    update_interval = self._update_interval.total_in_seconds
                
            # Update all sensors in this register group
            output = {}
            current_modbus_entities = self._modbus_entities[index]
            for sensor in current_modbus_entities.values():
                if sensor.entity_type == BUTTON:
                    continue
                sensor_output = self._update_sensor_and_derived(sensor=sensor, values=values, timestamp=timestamp)
                output.update(sensor_output)
                
            self._timestamp = timestamp
            self._message_bus.send_message(
                topic=f"{self._send_topic}/{data.base}",
                payload=output,
            )
            
        return update_interval
