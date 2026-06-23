"""Category-aware card templates for Modbus device HA dashboard export.

Generates specialized Home Assistant Lovelace card layouts based on the
device category (hvac, energy_meters, sensors, inverters, etc.).
Each category template groups entities semantically (temperatures, flows,
status, controls) with proper MDI icons.

Usage:
    from boneio.webui.modbus_card_templates import generate_cards_for_device

    cards = generate_cards_for_device(
        device_id="1_wanas415",
        entities=coord.get_all_entities(),
        serial="blk3361e9",
        device_info={"model": "Wanas 415", "category": "hvac", ...},
    )
"""

from __future__ import annotations

import logging
from typing import Any

from boneio.webui.dashboard_cards import (
    button_card,
    entity_badge,
    ha_slugify,
    heading_card,
    sensor_tile,
    slider_tile,
    tile_card,
)

_LOGGER = logging.getLogger(__name__)


# ─── device_class → MDI icon mapping ─────────────────────────────────────

DEVICE_CLASS_ICONS: dict[str, str] = {
    "temperature": "mdi:thermometer",
    "voltage": "mdi:flash",
    "current": "mdi:current-ac",
    "power": "mdi:lightning-bolt",
    "energy": "mdi:lightning-bolt-circle",
    "humidity": "mdi:water-percent",
    "volume_flow_rate": "mdi:fan",
    "power_factor": "mdi:angle-acute",
    "frequency": "mdi:sine-wave",
    "distance": "mdi:ruler",
    "pressure": "mdi:gauge",
    "speed": "mdi:speedometer",
    "duration": "mdi:timer-outline",
    "signal_strength": "mdi:signal",
    "apparent_power": "mdi:flash-triangle",
    "reactive_power": "mdi:flash-triangle-outline",
}

# entity_type → fallback icon (when no device_class)
ENTITY_TYPE_ICONS: dict[str, str] = {
    "sensor": "mdi:eye",
    "binary_sensor": "mdi:toggle-switch",
    "text_sensor": "mdi:text",
    "switch": "mdi:toggle-switch-variant",
    "number": "mdi:tune-variant",
    "select": "mdi:format-list-bulleted",
    "writeable_sensor": "mdi:pencil",
    "writeable_sensor_discrete": "mdi:pencil",
    "writeable_binary_sensor_discrete": "mdi:toggle-switch-variant",
}


def _get_icon(entity: Any) -> str:
    """Determine the best MDI icon for an entity.

    Priority: device_class icon > entity_type icon > mdi:chip fallback.

    Args:
        entity: Entity object with device_class and entity_type attributes.

    Returns:
        MDI icon string (e.g. "mdi:thermometer").
    """
    device_class = getattr(entity, "device_class", None)
    if device_class and device_class in DEVICE_CLASS_ICONS:
        return DEVICE_CLASS_ICONS[device_class]

    entity_type = getattr(entity, "entity_type", "sensor")
    return ENTITY_TYPE_ICONS.get(entity_type, "mdi:chip")


def _ha_entity_type(entity: Any) -> str:
    """Map internal entity_type to HA entity type for entity_id prefix.

    Args:
        entity: Entity with entity_type attribute.

    Returns:
        HA entity type string (sensor, binary_sensor, switch, number, select).
    """
    et = getattr(entity, "entity_type", "sensor")
    if et in ("binary_sensor",):
        return "binary_sensor"
    if et in ("switch", "writeable_binary_sensor_discrete"):
        return "switch"
    if et in ("number", "writeable_sensor", "writeable_sensor_discrete"):
        return "number"
    if et in ("select",):
        return "select"
    return "sensor"


def _ha_slugify(text: str) -> str:
    """Slugify text for HA entity IDs — delegates to shared ha_slugify.

    Args:
        text: Text to slugify.

    Returns:
        Slugified string.
    """
    return ha_slugify(text)


def _build_entity_id(device_id: str, entity: Any, serial: str = "") -> str:
    """Build HA entity_id from device_id and entity.

    Format matches ha_availabilty_message default_entity_id:
    {ha_entity_type}.{serial}_{device_id}_{decoded_name}

    Args:
        device_id: Device identifier (e.g. "1_wanas415").
        entity: Entity object with decoded_name attribute.
        serial: Device serial number (e.g. "blk265f49").

    Returns:
        Full HA entity ID string.
    """
    ha_type = _ha_entity_type(entity)
    decoded = getattr(entity, "decoded_name", "unknown")
    if serial:
        slug = _ha_slugify(f"{serial}_{device_id}_{decoded}")
    else:
        slug = _ha_slugify(f"{device_id}_{decoded}")
    return f"{ha_type}.{slug}"


def _entity_display_name(entity: Any) -> str:
    """Get the display name for an entity.

    Uses custom_label if set, otherwise falls back to entity name.

    Args:
        entity: Entity object.

    Returns:
        Display name string.
    """
    label = getattr(entity, "_custom_label", None) or getattr(entity, "custom_label", None)
    if callable(label):
        label = label()
    return label or getattr(entity, "name", "Unknown")


# ─── Entity grouping helpers ─────────────────────────────────────────────


def _group_entities_by_type(
    flat_entities: list[Any],
) -> dict[str, list[Any]]:
    """Group entities by their HA entity type.

    Args:
        flat_entities: Flat list of entity objects.

    Returns:
        Dict mapping HA entity type to list of entities.
    """
    groups: dict[str, list[Any]] = {}
    for entity in flat_entities:
        ha_type = _ha_entity_type(entity)
        groups.setdefault(ha_type, []).append(entity)
    return groups


def _group_entities_by_device_class(
    flat_entities: list[Any],
) -> dict[str, list[Any]]:
    """Group entities by device_class.

    Args:
        flat_entities: Flat list of entity objects.

    Returns:
        Dict mapping device_class (or "other") to list of entities.
    """
    groups: dict[str, list[Any]] = {}
    for entity in flat_entities:
        dc = getattr(entity, "device_class", None) or "other"
        groups.setdefault(dc, []).append(entity)
    return groups


def _flatten_entities(entities_list: list[dict]) -> list[Any]:
    """Flatten coordinator entity dicts into a flat list.

    ModbusCoordinator.get_all_entities() returns list[dict[str, Entity]].
    This flattens it into a simple list of entities.

    Args:
        entities_list: List of entity dicts from coordinator.

    Returns:
        Flat list of entity objects.
    """
    flat = []
    for entities_dict in entities_list:
        for entity in entities_dict.values():
            flat.append(entity)
    return flat


# ─── Card generation for a single entity ─────────────────────────────────


def _make_entity_card(device_id: str, entity: Any, serial: str = "") -> dict[str, Any]:
    """Create the appropriate card for a single entity.

    Uses sensor_tile for read-only sensors, tile_card with actions
    for switches and writeable entities, slider_tile for numbers.

    Args:
        device_id: Device identifier.
        entity: Entity object.
        serial: Device serial number.

    Returns:
        Card dict ready for YAML serialization.
    """
    entity_id = _build_entity_id(device_id, entity, serial)
    name = _entity_display_name(entity)
    icon = _get_icon(entity)
    ha_type = _ha_entity_type(entity)

    if ha_type == "number":
        return slider_tile(entity=entity_id, name=name, icon=icon)

    if ha_type == "switch":
        return tile_card(
            entity=entity_id,
            name=name,
            icon=icon,
            tap_action="toggle",
            state_content=["state", "last_changed"],
        )

    if ha_type == "binary_sensor":
        return sensor_tile(
            entity=entity_id,
            name=name,
            icon=icon,
            state_content=["state"],
        )

    # Default: read-only sensor
    return sensor_tile(
        entity=entity_id,
        name=name,
        icon=icon,
        state_content=["state", "last_changed"],
    )


# ─── HVAC template (Wanas, Thessla, Ventclear, Fujitsu) ──────────────────


def generate_hvac_cards(
    device_id: str,
    entities_list: list[dict],
    serial: str,
    device_info: dict[str, Any],
) -> list[dict[str, Any]]:
    """Generate specialized HVAC cards grouped by sensor type.

    Layout:
        1. Heading with device name
        2. 🌡️ Temperatures section
        3. 💨 Air flow section
        4. ℹ️ Status section (binary sensors, text sensors)
        5. ⚙️ Controls section (switches, numbers)

    Args:
        device_id: Device identifier (e.g. "1_wanas415").
        entities_list: Entities from coordinator.get_all_entities().
        serial: Device serial number.
        device_info: Device metadata dict.

    Returns:
        List of card dicts.
    """
    flat = _flatten_entities(entities_list)
    device_name = device_info.get("name", device_info.get("model", device_id))

    # Group by device_class and entity_type with EXCLUSIVE assignment.
    # Each entity goes into exactly one group to avoid duplicates.
    temps: list[Any] = []
    flows: list[Any] = []
    humidity: list[Any] = []
    binary: list[Any] = []
    text: list[Any] = []
    controls: list[Any] = []
    other_sensors: list[Any] = []

    for e in flat:
        ha_type = _ha_entity_type(e)
        dc = getattr(e, "device_class", None)

        # Writeable entities → controls section (even if they have device_class)
        if ha_type in ("switch", "number", "select"):
            controls.append(e)
        elif getattr(e, "entity_type", None) == "binary_sensor":
            binary.append(e)
        elif getattr(e, "entity_type", None) == "text_sensor":
            text.append(e)
        elif dc == "temperature":
            temps.append(e)
        elif dc == "volume_flow_rate":
            flows.append(e)
        elif dc == "humidity":
            humidity.append(e)
        else:
            other_sensors.append(e)

    cards: list[dict[str, Any]] = []

    # Main heading with badges for key metrics
    badges = []
    if temps:
        badges.append(entity_badge(_build_entity_id(device_id, temps[0], serial)))
    if flows:
        badges.append(entity_badge(_build_entity_id(device_id, flows[0], serial)))
    cards.append(heading_card(f"🌬️ {device_name}", style="title", badges=badges or None))

    # Temperatures
    if temps:
        cards.append(heading_card("🌡️ Temperatury", style="subtitle"))
        for entity in temps:
            cards.append(_make_entity_card(device_id, entity, serial))

    # Air flows
    if flows:
        cards.append(heading_card("💨 Przepływy", style="subtitle"))
        for entity in flows:
            cards.append(_make_entity_card(device_id, entity, serial))

    # Humidity
    if humidity:
        cards.append(heading_card("💧 Wilgotność", style="subtitle"))
        for entity in humidity:
            cards.append(_make_entity_card(device_id, entity, serial))

    # Status (binary + text sensors)
    status_entities = binary + text
    if status_entities:
        cards.append(heading_card("ℹ️ Status", style="subtitle"))
        for entity in status_entities:
            cards.append(_make_entity_card(device_id, entity, serial))

    # Controls
    if controls:
        cards.append(heading_card("⚙️ Sterowanie", style="subtitle"))
        for entity in controls:
            cards.append(_make_entity_card(device_id, entity, serial))

    # Other sensors not categorized
    if other_sensors:
        cards.append(heading_card("📊 Inne czujniki", style="subtitle"))
        for entity in other_sensors:
            cards.append(_make_entity_card(device_id, entity, serial))

    return cards


# ─── Energy Meters template (SDM120, SDM630, LE-03MW, ORNO) ──────────────


def generate_energy_cards(
    device_id: str,
    entities_list: list[dict],
    serial: str,
    device_info: dict[str, Any],
) -> list[dict[str, Any]]:
    """Generate specialized energy meter cards grouped by measurement type.

    Layout:
        1. Heading with device name + power/energy badges
        2. ⚡ Voltage section
        3. 🔌 Current section
        4. 💡 Power section (active, reactive, apparent)
        5. 📊 Energy section (import/export)
        6. 📈 Other (power factor, frequency, phase angle)

    Args:
        device_id: Device identifier.
        entities_list: Entities from coordinator.get_all_entities().
        serial: Device serial number.
        device_info: Device metadata dict.

    Returns:
        List of card dicts.
    """
    flat = _flatten_entities(entities_list)
    device_name = device_info.get("name", device_info.get("model", device_id))

    voltage = [e for e in flat if getattr(e, "device_class", None) == "voltage"]
    current = [e for e in flat if getattr(e, "device_class", None) == "current"]
    power = [e for e in flat if getattr(e, "device_class", None) == "power"]
    apparent = [e for e in flat if getattr(e, "device_class", None) == "apparent_power"]
    reactive = [e for e in flat if getattr(e, "device_class", None) == "reactive_power"]
    energy = [e for e in flat if getattr(e, "device_class", None) == "energy"]
    frequency = [e for e in flat if getattr(e, "device_class", None) == "frequency"]
    power_factor = [e for e in flat if getattr(e, "device_class", None) == "power_factor"]

    grouped_set = set(
        id(e)
        for group in [voltage, current, power, apparent, reactive, energy, frequency, power_factor]
        for e in group
    )
    other = [e for e in flat if id(e) not in grouped_set]

    cards: list[dict[str, Any]] = []

    # Main heading with power + energy badges
    badges = []
    if power:
        badges.append(entity_badge(_build_entity_id(device_id, power[0], serial)))
    if energy:
        badges.append(entity_badge(_build_entity_id(device_id, energy[0], serial)))
    cards.append(heading_card(f"⚡ {device_name}", style="title", badges=badges or None))

    # Voltage
    if voltage:
        cards.append(heading_card("⚡ Napięcie", style="subtitle"))
        for entity in voltage:
            cards.append(_make_entity_card(device_id, entity, serial))

    # Current
    if current:
        cards.append(heading_card("🔌 Prąd", style="subtitle"))
        for entity in current:
            cards.append(_make_entity_card(device_id, entity, serial))

    # Power (active + apparent + reactive)
    all_power = power + apparent + reactive
    if all_power:
        cards.append(heading_card("💡 Moc", style="subtitle"))
        for entity in all_power:
            cards.append(_make_entity_card(device_id, entity, serial))

    # Energy
    if energy:
        cards.append(heading_card("📊 Energia", style="subtitle"))
        for entity in energy:
            cards.append(_make_entity_card(device_id, entity, serial))

    # Other metrics (frequency, power factor, etc.)
    other_metrics = frequency + power_factor + other
    if other_metrics:
        cards.append(heading_card("📈 Parametry", style="subtitle"))
        for entity in other_metrics:
            cards.append(_make_entity_card(device_id, entity, serial))

    return cards


# ─── Generic/Sensors template (fallback) ─────────────────────────────────


def generate_generic_cards(
    device_id: str,
    entities_list: list[dict],
    serial: str,
    device_info: dict[str, Any],
) -> list[dict[str, Any]]:
    """Generate generic cards grouped by device_class.

    Used as fallback for device categories without a specialized template,
    and for standalone sensor devices.

    Args:
        device_id: Device identifier.
        entities_list: Entities from coordinator.get_all_entities().
        serial: Device serial number.
        device_info: Device metadata dict.

    Returns:
        List of card dicts.
    """
    flat = _flatten_entities(entities_list)
    device_name = device_info.get("name", device_info.get("model", device_id))

    cards: list[dict[str, Any]] = [
        heading_card(f"📡 {device_name}", style="title"),
    ]

    by_class = _group_entities_by_device_class(flat)

    # Section labels for known device classes
    section_labels = {
        "temperature": "🌡️ Temperatura",
        "humidity": "💧 Wilgotność",
        "voltage": "⚡ Napięcie",
        "current": "🔌 Prąd",
        "power": "💡 Moc",
        "energy": "📊 Energia",
        "distance": "📏 Dystans",
        "pressure": "🔵 Ciśnienie",
        "volume_flow_rate": "💨 Przepływ",
    }

    for dc, entities in by_class.items():
        label = section_labels.get(dc, f"📡 {dc.replace('_', ' ').title()}" if dc != "other" else "📡 Czujniki")
        if len(by_class) > 1:
            cards.append(heading_card(label, style="subtitle"))
        for entity in entities:
            cards.append(_make_entity_card(device_id, entity, serial))

    return cards


# ─── Category template dispatcher ────────────────────────────────────────

CATEGORY_TEMPLATES: dict[str, Any] = {
    "hvac": generate_hvac_cards,
    "energy_meters": generate_energy_cards,
    "sensors": generate_generic_cards,
    "inverters": generate_generic_cards,  # TODO: specialized inverter template
    "other": generate_generic_cards,
}


def generate_cards_for_device(
    device_id: str,
    entities_list: list[dict],
    serial: str,
    device_info: dict[str, Any],
) -> list[dict[str, Any]]:
    """Dispatch to the correct card template based on device category.

    This is the main entry point for generating HA cards from a
    ModbusCoordinator or MockModbusCoordinator.

    Args:
        device_id: Device identifier (e.g. "1_wanas415").
        entities_list: Entities from coordinator.get_all_entities().
        serial: Device serial number.
        device_info: Device metadata dict (must include "category").

    Returns:
        List of card dicts ready for cards_to_yaml().
    """
    category = device_info.get("category", "other")
    generator = CATEGORY_TEMPLATES.get(category, generate_generic_cards)

    _LOGGER.debug(
        "Generating %s cards for device %s (category: %s)",
        generator.__name__,
        device_id,
        category,
    )

    return generator(
        device_id=device_id,
        entities_list=entities_list,
        serial=serial,
        device_info=device_info,
    )
