"""Mock Modbus Coordinator for testing card templates and simulating devices.

Creates a fake coordinator by reading device JSON files and building
mock entities with the same attributes as real ModbusBaseEntity objects.
This allows testing card generation, YAML export, and entity ID construction
without any physical Modbus device connected.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger(__name__)

# Base path to device JSON files (relative to this module)
_DEVICES_DIR = Path(__file__).parent / "devices"


def _find_device_json(model_key: str) -> Path:
    """Find the JSON file for a given model key.

    Searches all subdirectories under boneio/modbus/devices/.

    Args:
        model_key: Device model key (e.g. "wanas415", "sdm120").

    Returns:
        Path to the JSON file.

    Raises:
        FileNotFoundError: If no matching JSON file is found.
    """
    for root, _dirs, files in os.walk(_DEVICES_DIR):
        for fname in files:
            if fname == f"{model_key}.json":
                return Path(root) / fname

    available = []
    for root, _dirs, files in os.walk(_DEVICES_DIR):
        for fname in files:
            if fname.endswith(".json"):
                available.append(fname[:-5])

    raise FileNotFoundError(
        f"Device JSON not found for model '{model_key}'. "
        f"Available models: {sorted(available)}"
    )


@dataclass
class MockModbusEntity:
    """Mock entity matching the interface of BaseEntity/ModbusBaseEntity.

    Has the same properties that _generate_modbus_cards() and card templates
    read from real entities: name, decoded_name, entity_type, device_class,
    unit_of_measurement, custom_label.
    """

    name: str
    entity_type: str = "sensor"
    device_class: str | None = None
    unit_of_measurement: str | None = None
    state_class: str | None = None
    entity_category: str | None = None
    value_type: str | None = None
    _custom_label: str | None = None
    _value: Any = None
    _x_mapping: dict[str, str] = field(default_factory=dict)

    @property
    def decoded_name(self) -> str:
        """Return decoded name (lowercase, no spaces) — matches BaseEntity."""
        return self.name.replace(" ", "").lower()

    @property
    def display_name(self) -> str:
        """Return custom label if set, otherwise default name."""
        return self._custom_label or self.name

    @property
    def custom_label(self) -> str | None:
        """Return custom label if set."""
        return self._custom_label

    def set_custom_label(self, label: str | None) -> None:
        """Set a user-defined custom display label."""
        self._custom_label = label

    @property
    def state(self) -> Any:
        """Return current value."""
        return self._value

    def get_value(self) -> Any:
        """Return current value."""
        return self._value

    @property
    def _device_class(self) -> str | None:
        """Alias for device_class — some code accesses _device_class directly."""
        return self.device_class


class MockModbusCoordinator:
    """Fake ModbusCoordinator built from a device JSON file.

    Reads registers_base (and optionally additional_entities) from the JSON
    and creates MockModbusEntity objects with the correct metadata.
    The resulting object has the same interface as real ModbusCoordinator
    for the methods used by card generation and dashboard export.
    """

    def __init__(
        self,
        device_id: str,
        name: str,
        model: str,
        model_key: str,
        category: str,
        manufacturer: str,
        description: str,
        entities: list[MockModbusEntity],
        additional_entities: list[MockModbusEntity] | None = None,
    ) -> None:
        """Initialize MockModbusCoordinator."""
        self._id = device_id
        self._name = name
        self._model = model
        self.model_key = model_key
        self.category = category
        self.manufacturer = manufacturer
        self.description = description
        self._entities = entities
        self._additional = additional_entities or []

    @classmethod
    def from_json(
        cls,
        model_key: str,
        address: int = 1,
        device_id: str | None = None,
        name: str | None = None,
    ) -> MockModbusCoordinator:
        """Build a MockModbusCoordinator from a device JSON file."""
        json_path = _find_device_json(model_key)
        with open(json_path) as f:
            device_data = json.load(f)

        effective_id = device_id or f"{address}_{model_key}"
        effective_name = name or device_data.get("model", model_key)

        # Build base entities from registers_base
        entities: list[MockModbusEntity] = []
        for reg_base in device_data.get("registers_base", []):
            for reg in reg_base.get("registers", []):
                entity = MockModbusEntity(
                    name=reg.get("name", "Unknown"),
                    entity_type=reg.get("entity_type", "sensor"),
                    device_class=reg.get("device_class"),
                    unit_of_measurement=reg.get("unit_of_measurement"),
                    state_class=reg.get("state_class"),
                    entity_category=reg.get("entity_category"),
                    value_type=reg.get("value_type"),
                    _x_mapping=reg.get("x_mapping", {}),
                )
                entities.append(entity)

        # Build additional/derived entities from "additional_entities"
        additional: list[MockModbusEntity] = []
        for additional_def in device_data.get("additional_entities", []):
            entity = MockModbusEntity(
                name=additional_def.get("name", "Unknown"),
                entity_type=additional_def.get("entity_type", "sensor"),
                device_class=additional_def.get("device_class"),
                unit_of_measurement=additional_def.get("unit_of_measurement"),
                state_class=additional_def.get("state_class"),
                entity_category=additional_def.get("entity_category"),
            )
            additional.append(entity)

        _LOGGER.debug(
            "Built MockModbusCoordinator for %s: %d base entities, %d additional",
            model_key,
            len(entities),
            len(additional),
        )

        return cls(
            device_id=effective_id,
            name=effective_name,
            model=device_data.get("model", model_key),
            model_key=model_key,
            category=device_data.get("category", "other"),
            manufacturer=device_data.get("manufacturer", "Unknown"),
            description=device_data.get("description", ""),
            entities=entities,
            additional_entities=additional,
        )

    def get_all_entities(self) -> list[dict[str, MockModbusEntity]]:
        """Return all entities (base + additional) in coordinator format.

        Merges base register entities and derived additional entities
        into a single dict so card templates can generate cards for all of them.
        """
        merged = {e.decoded_name: e for e in self._entities}
        for e in self._additional:
            merged[e.decoded_name] = e
        return [merged]

    def get_all_additional_entities(self) -> list[dict[str, MockModbusEntity]]:
        """Return additional/derived entities."""
        if not self._additional:
            return []
        return [{e.decoded_name: e for e in self._additional}]

    @property
    def id(self) -> str:
        """Return device ID."""
        return self._id

    @property
    def entity_count(self) -> int:
        """Return total number of entities (base + additional)."""
        return len(self._entities) + len(self._additional)

    @property
    def base_entity_count(self) -> int:
        """Return number of base entities."""
        return len(self._entities)

    def get_device_info(self) -> dict[str, Any]:
        """Return device metadata dict for card templates."""
        return {
            "model": self._model,
            "model_key": self.model_key,
            "manufacturer": self.manufacturer,
            "category": self.category,
            "description": self.description,
            "device_id": self._id,
            "name": self._name,
        }

    def list_entities(self) -> list[dict[str, str]]:
        """Return a summary of all entities for debugging."""
        result = []
        for entity in self._entities:
            result.append(
                {
                    "name": entity.name,
                    "entity_type": entity.entity_type,
                    "device_class": entity.device_class or "",
                    "unit": entity.unit_of_measurement or "",
                    "decoded_name": entity.decoded_name,
                }
            )
        for entity in self._additional:
            result.append(
                {
                    "name": entity.name,
                    "entity_type": entity.entity_type,
                    "device_class": entity.device_class or "",
                    "unit": entity.unit_of_measurement or "",
                    "decoded_name": entity.decoded_name,
                    "source": "additional",
                }
            )
        return result

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"MockModbusCoordinator("
            f"model={self.model_key!r}, "
            f"name={self._name!r}, "
            f"entities={self.entity_count}"
            f")"
        )
