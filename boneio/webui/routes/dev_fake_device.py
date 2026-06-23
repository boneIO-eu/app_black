"""Dev-only API endpoint for creating fake Modbus devices in HA.

Publishes MQTT discovery messages and fake sensor data so that
Home Assistant creates real entities with simulated values.
This allows testing dashboard cards without physical hardware.

Usage:
    POST /api/dev/fake-device/wanas415
    → Creates all HA entities for Wanas 415 with realistic fake data

    DELETE /api/dev/fake-device/wanas415
    → Removes fake device from HA

    POST /api/dev/fake-device/wanas415/update
    → Publishes new random values (simulates sensor update)

WARNING: Dev-only — should NOT be enabled in production.
"""

from __future__ import annotations

import json
import logging
import random
import time
import unicodedata
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, Query

from boneio.const import ONLINE, STATE
from boneio.modbus.mock_coordinator import MockModbusCoordinator, _find_device_json
from boneio.version import __version__
from boneio.webui.dashboard_cards import cards_to_yaml
from boneio.webui.modbus_card_templates import generate_cards_for_device

if TYPE_CHECKING:
    from boneio.core.manager import Manager

_LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dev", tags=["dev"])

# Track active fake devices so we can stop/remove them
_active_fake_devices: dict[str, dict[str, Any]] = {}


def get_manager():
    """Get manager instance - will be overridden by app initialization."""
    raise NotImplementedError("Manager not initialized")


# ── Realistic fake value generators per device_class ──────────────────────

# (min, max, decimals) per device_class
_VALUE_RANGES: dict[str, tuple[float, float, int]] = {
    "temperature": (-5.0, 35.0, 1),
    "humidity": (30.0, 80.0, 0),
    "voltage": (220.0, 240.0, 1),
    "current": (0.1, 16.0, 2),
    "power": (50.0, 3500.0, 0),
    "energy": (100.0, 50000.0, 1),
    "power_factor": (0.85, 1.0, 2),
    "frequency": (49.8, 50.2, 1),
    "volume_flow_rate": (50.0, 350.0, 0),
    "apparent_power": (100.0, 4000.0, 0),
    "reactive_power": (10.0, 500.0, 0),
    "distance": (0.5, 10.0, 2),
    "pressure": (980.0, 1040.0, 1),
}


def _generate_fake_value(
    device_class: str | None,
    entity_type: str,
    x_mapping: dict[str, str] | None = None,
) -> float | int | str:
    """Generate a realistic fake value based on device_class.

    Produces values within normal operating ranges for each class.
    For text_sensors with x_mapping, picks a random mapped value
    (the already-decoded text, not the numeric key) to match how
    the real ModbusTextSensor publishes to MQTT after set_value().

    Args:
        device_class: HA device_class (e.g. "temperature", "voltage").
        entity_type: Entity type (e.g. "sensor", "binary_sensor").
        x_mapping: Optional value mapping dict (e.g. {"0": "postój", "2": "praca"}).

    Returns:
        Simulated sensor value.
    """
    if entity_type == "binary_sensor":
        return random.choice(["ON", "OFF"])
    if entity_type == "text_sensor":
        if x_mapping:
            return random.choice(list(x_mapping.values()))
        return "OK"

    if device_class and device_class in _VALUE_RANGES:
        min_val, max_val, decimals = _VALUE_RANGES[device_class]
        val = random.uniform(min_val, max_val)
        return round(val, decimals) if decimals > 0 else int(val)

    if entity_type in ("writeable_sensor", "writeable_sensor_discrete"):
        return round(random.uniform(15.0, 25.0), 1)

    return round(random.uniform(0.0, 100.0), 1)


def _ha_entity_type_for(entity_type: str) -> str:
    """Map internal entity_type to HA entity type.

    Args:
        entity_type: Internal entity type string.

    Returns:
        HA-compatible entity type for discovery topic.
    """
    if entity_type in ("binary_sensor",):
        return "binary_sensor"
    if entity_type in ("switch", "writeable_binary_sensor_discrete"):
        return "switch"
    if entity_type in ("number", "writeable_sensor", "writeable_sensor_discrete"):
        return "number"
    if entity_type in ("select",):
        return "select"
    return "sensor"


def _ascii_entity_id(text: str) -> str:
    """Normalize text to ASCII for use in MQTT discovery topics.

    HA rejects discovery topics with non-ASCII characters.
    Uses NFKD decomposition (ń→n, ą→a, ó→o) plus manual ł→l.

    Args:
        text: Raw entity ID text (may contain Polish characters).

    Returns:
        ASCII-safe entity ID string.
    """
    text = text.replace("ł", "l").replace("Ł", "L")
    nfkd = unicodedata.normalize("NFKD", text)
    return nfkd.encode("ascii", "ignore").decode("ascii")

def _build_fake_discovery(
    device_data: dict[str, Any],
    device_id: str,
    device_name: str,
    model: str,
    manufacturer: str,
    topic_prefix: str,
    ha_discovery_prefix: str,
    serial_no: str,
) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:
    """Build MQTT discovery messages and state payloads for a fake device.

    Mimics what the real ModbusCoordinator + BaseEntity.discovery_message()
    would produce, but without needing a real coordinator or config_helper.

    Args:
        device_data: Parsed device JSON.
        device_id: Device ID (e.g. "1_wanas415").
        device_name: Human-readable name.
        model: Model string.
        manufacturer: Manufacturer string.
        topic_prefix: MQTT topic prefix (e.g. "boneio/blk3361e9").
        ha_discovery_prefix: HA discovery prefix (e.g. "homeassistant").
        serial_no: Device serial number.

    Returns:
        (discovery_messages, state_payloads_by_base_address)
    """
    discovery_messages: list[dict[str, Any]] = []
    state_payloads: dict[int, dict[str, Any]] = {}

    # Build HA device block (shared for all entities)
    device_block = {
        "identifiers": [device_id],
        "manufacturer": manufacturer,
        "model": model,
        "name": device_name,
        "sw_version": __version__,
        "via_device": topic_prefix,
    }

    for reg_base in device_data.get("registers_base", []):
        base = reg_base["base"]
        state_payloads[base] = {}

        for reg in reg_base.get("registers", []):
            entity_name = reg.get("name", "Unknown")
            entity_type = reg.get("entity_type", "sensor")
            device_class = reg.get("device_class")
            decoded_name = entity_name.replace(" ", "").lower()
            entity_id = _ascii_entity_id(f"{device_id}_{decoded_name.replace('_', '')}")
            ha_type = _ha_entity_type_for(entity_type)

            # Discovery topic — same as BaseEntity._topic
            discovery_topic = f"{ha_discovery_prefix}/{ha_type}/{serial_no}/{entity_id}/config"

            # Build value_template — text_sensors never use a filter
            # (matches real ModbusTextSensor which sets ha_filter="")
            x_mapping = reg.get("x_mapping") or {}
            if entity_type == "text_sensor":
                ha_filter = ""
            else:
                ha_filter = reg.get("ha_filter", "round(2)")
            if ha_filter:
                value_template = f"{{{{ value_json.{decoded_name} | {ha_filter} }}}}"
            else:
                value_template = f"{{{{ value_json.{decoded_name} }}}}"

            # Build discovery payload — matches entity.discovery_message()
            # default_entity_id tells HA what entity_id to use instead of
            # auto-generating from device.name + entity.name
            default_eid = f"{ha_type}.{serial_no}_{entity_id}"
            payload: dict[str, Any] = {
                "availability": [{"topic": f"{topic_prefix}/modbus/{device_id}/{STATE}"}],
                "device": device_block,
                "name": entity_name,
                "state_topic": f"{topic_prefix}/modbus/{device_id}/{base}",
                "unique_id": f"{topic_prefix.replace('/', '_')}_modbus_{entity_id}",
                "default_entity_id": default_eid,
                "value_template": value_template,
            }

            if reg.get("unit_of_measurement"):
                payload["unit_of_measurement"] = reg["unit_of_measurement"]
            # text_sensor values are strings — HA treats state_class="measurement"
            # as a numeric indicator and rejects non-numeric values with an error.
            if reg.get("state_class") and entity_type != "text_sensor":
                payload["state_class"] = reg["state_class"]
            if device_class:
                payload["device_class"] = device_class
            if reg.get("entity_category"):
                payload["entity_category"] = reg["entity_category"]

            # For writeable entities, add command_topic
            if ha_type == "number":
                payload["command_topic"] = f"{topic_prefix}/cmd/modbus/{device_id}/{entity_id}/set"
                payload["mode"] = "slider"
                if reg.get("min_value") is not None:
                    payload["min"] = reg["min_value"]
                if reg.get("max_value") is not None:
                    payload["max"] = reg["max_value"]

            discovery_messages.append(
                {
                    "_discovery_topic": discovery_topic,
                    "payload": payload,
                    "entity_type": entity_type,
                    "decoded_name": decoded_name,
                    "device_class": device_class,
                    "x_mapping": x_mapping,
                }
            )

            # Generate fake value
            fake_val = _generate_fake_value(device_class, entity_type, x_mapping=x_mapping)
            state_payloads[base][decoded_name] = fake_val

    # ─── Additional/derived entities (select, text_sensor, switch) ────────
    # These derive their state from a source register and appear as
    # separate HA entities (e.g. select with dropdown options).
    # Build a lookup: ascii_decoded_name → (base_address, decoded_name)
    # Real coordinator resolves source via: s.decoded_name == source.replace("_", "")
    # but Polish chars cause mismatches (dzieńtygodnia vs dzientygodnia)
    # so we normalize both sides to ASCII for matching.
    def _ascii_key(text: str) -> str:
        """Normalize text to ASCII lowercase without underscores/spaces.

        Uses NFKD decomposition to convert Polish chars (ń→n, ó→o, etc.)
        instead of stripping them entirely. ł/Ł need manual substitution
        since NFKD doesn't decompose them.
        """
        text = text.replace("ł", "l").replace("Ł", "L")
        nfkd = unicodedata.normalize("NFKD", text)
        ascii_text = nfkd.encode("ascii", "ignore").decode("ascii")
        return ascii_text.replace("_", "").replace(" ", "").lower()

    source_map: dict[str, tuple[int, str]] = {}
    for reg_base in device_data.get("registers_base", []):
        base = reg_base["base"]
        for reg in reg_base.get("registers", []):
            name = reg.get("name", "Unknown")
            dn = name.replace(" ", "").lower()
            source_map[_ascii_key(name)] = (base, dn)

    for add_ent in device_data.get("additional_entities", []):
        add_name = add_ent.get("name", "Unknown")
        add_type = add_ent.get("entity_type", "sensor")
        add_source = add_ent.get("source", "")
        add_mapping = add_ent.get("x_mapping") or {}

        # Find source register using ASCII-normalized key
        source_key = _ascii_key(add_source)
        if source_key not in source_map:
            _LOGGER.warning(
                "Additional entity %s: source '%s' not found in registers",
                add_name,
                add_source,
            )
            continue

        source_base, source_decoded = source_map[source_key]

        # Derived entity reads from source's state_topic using source's decoded_name
        ha_type = _ha_entity_type_for(add_type)
        decoded_name = add_name.replace(" ", "").lower()
        entity_id = _ascii_entity_id(f"{device_id}_{decoded_name.replace('_', '')}")
        default_eid = f"{ha_type}.{serial_no}_{entity_id}"

        discovery_topic = f"{ha_discovery_prefix}/{ha_type}/{serial_no}/{entity_id}/config"

        # Derived entities read from the source sensor's value in the state topic
        value_template = f"{{{{ value_json.{source_decoded} }}}}"

        payload: dict[str, Any] = {
            "availability": [{"topic": f"{topic_prefix}/modbus/{device_id}/{STATE}"}],
            "device": device_block,
            "name": add_name,
            "state_topic": f"{topic_prefix}/modbus/{device_id}/{source_base}",
            "unique_id": f"{topic_prefix.replace('/', '_')}_modbus_{entity_id}",
            "default_entity_id": default_eid,
            "value_template": value_template,
        }

        # Type-specific discovery fields
        if ha_type == "select" and add_mapping:
            payload["options"] = list(add_mapping.values())
            payload["command_topic"] = f"{topic_prefix}/cmd/modbus/{device_id}/set"
            payload["command_template"] = '{"device": "' + source_decoded + '", "value": "{{ value }}"}'
        elif ha_type == "switch":
            payload["command_topic"] = f"{topic_prefix}/cmd/modbus/{device_id}/set"
            payload["payload_on"] = add_ent.get("payload_on", "ON")
            payload["payload_off"] = add_ent.get("payload_off", "OFF")

        if add_ent.get("entity_category"):
            payload["entity_category"] = add_ent["entity_category"]

        discovery_messages.append(
            {
                "_discovery_topic": discovery_topic,
                "payload": payload,
                "entity_type": add_type,
                "decoded_name": decoded_name,
                "device_class": add_ent.get("device_class"),
                "x_mapping": add_mapping,
            }
        )

        # For select with x_mapping, update the source register value
        # in state_payloads to be a mapped text value instead of numeric
        if add_mapping and source_base in state_payloads:
            state_payloads[source_base][source_decoded] = random.choice(list(add_mapping.values()))

    return discovery_messages, state_payloads


@router.post("/fake-device/{model}")
async def create_fake_device(
    model: str,
    address: int = Query(default=1, description="Simulated Modbus address"),
    manager: Any = Depends(get_manager),
):
    """Create a fake Modbus device and publish it to HA via MQTT.

    Sends MQTT discovery messages for all entities in the device JSON,
    then publishes ONLINE status and fake sensor values.
    HA will create real entities with simulated data.

    Args:
        model: Device model key (e.g. "wanas415", "sdm120").
        address: Simulated Modbus address (default: 1).
        manager: BoneIO Manager instance (injected).

    Returns:
        Summary with device_id, entity_count, published topics and values.
    """
    # Find device JSON
    try:
        json_path = _find_device_json(model)
    except FileNotFoundError:
        return {"error": f"Model '{model}' not found in device database."}

    with open(json_path) as f:
        device_data = json.load(f)

    device_id = f"{address}_{model}"
    device_name = device_data.get("model", model)
    manufacturer_name = device_data.get("manufacturer", "boneIO")
    category = device_data.get("category", "other")

    config_helper = manager.config_helper
    message_bus = manager._message_bus
    topic_prefix = config_helper.topic_prefix

    # Build discovery and state
    discovery_msgs, state_payloads = _build_fake_discovery(
        device_data=device_data,
        device_id=device_id,
        device_name=device_name,
        model=device_data.get("model", model),
        manufacturer=manufacturer_name,
        topic_prefix=topic_prefix,
        ha_discovery_prefix=config_helper.ha_discovery_prefix,
        serial_no=config_helper.serial_no,
    )

    # 1. Register discovery topics in config_helper so BoneIO's MQTT handler
    #    (handle_messages → is_topic_in_autodiscovery) does NOT auto-remove them.
    #    Without this, BoneIO sees the retained discovery message on its own
    #    subscription, finds it missing from _autodiscovery_messages, and
    #    immediately publishes an empty payload to erase it.
    published_topics = []
    for disc in discovery_msgs:
        topic = disc["_discovery_topic"]
        payload = disc["payload"]
        ha_type = _ha_entity_type_for(disc["entity_type"])
        config_helper.add_autodiscovery_msg(ha_type=ha_type, topic=topic, payload=payload)
        message_bus.send_message(topic=topic, payload=payload, retain=True)
        published_topics.append(topic)
        _LOGGER.debug("Sent fake discovery: %s", topic)

    # 2. Send ONLINE status on availability topic (retained)
    avail_topic = f"{topic_prefix}/modbus/{device_id}/{STATE}"
    message_bus.send_message(topic=avail_topic, payload=ONLINE, retain=True)

    # 3. Publish fake state data on state topics
    state_topics = []
    for base_addr, values in state_payloads.items():
        state_topic = f"{topic_prefix}/modbus/{device_id}/{base_addr}"
        message_bus.send_message(topic=state_topic, payload=values)
        state_topics.append({"topic": state_topic, "values": values})

    # Track active device
    _active_fake_devices[device_id] = {
        "model": model,
        "device_name": device_name,
        "manufacturer": manufacturer_name,
        "category": category,
        "discovery_topics": published_topics,
        "discovery_msgs": discovery_msgs,
        "state_payloads": state_payloads,
        "created_at": time.time(),
    }

    _LOGGER.info(
        "Created fake Modbus device %s (%s) with %d entities on MQTT",
        device_id,
        device_name,
        len(published_topics),
    )

    return {
        "device_id": device_id,
        "model": device_name,
        "manufacturer": manufacturer_name,
        "category": category,
        "entity_count": len(published_topics),
        "availability_topic": avail_topic,
        "state_topics": state_topics,
    }


@router.post("/fake-device/{model}/update")
async def update_fake_device(
    model: str,
    address: int = Query(default=1, description="Simulated Modbus address"),
    manager: Any = Depends(get_manager),
):
    """Publish new random values for an existing fake device.

    Simulates a Modbus poll cycle by generating new random values
    and publishing them to the same state topics.

    Args:
        model: Device model key.
        address: Simulated Modbus address.
        manager: BoneIO Manager instance.

    Returns:
        Updated state values.
    """
    device_id = f"{address}_{model}"

    if device_id not in _active_fake_devices:
        return {"error": f"Fake device {device_id} not found. Create it first."}

    device_info = _active_fake_devices[device_id]
    message_bus = manager._message_bus
    topic_prefix = manager.config_helper.topic_prefix

    # Generate new random values for each entity
    new_payloads: dict[int, dict[str, Any]] = {}
    for disc in device_info["discovery_msgs"]:
        decoded_name = disc["decoded_name"]
        device_class = disc["device_class"]
        entity_type = disc["entity_type"]
        # Find the base address from state_topic
        state_topic = disc["payload"]["state_topic"]
        base_addr = int(state_topic.rsplit("/", 1)[-1])

        if base_addr not in new_payloads:
            new_payloads[base_addr] = {}

        new_payloads[base_addr][decoded_name] = _generate_fake_value(
            device_class, entity_type, x_mapping=disc.get("x_mapping")
        )

    # Publish updated values
    state_topics = []
    for base_addr, values in new_payloads.items():
        state_topic = f"{topic_prefix}/modbus/{device_id}/{base_addr}"
        message_bus.send_message(topic=state_topic, payload=values)
        state_topics.append({"topic": state_topic, "values": values})

    _LOGGER.debug("Updated fake device %s with new random values", device_id)

    return {
        "device_id": device_id,
        "state_topics": state_topics,
    }


@router.delete("/fake-device/{model}")
async def remove_fake_device(
    model: str,
    address: int = Query(default=1, description="Simulated Modbus address"),
    manager: Any = Depends(get_manager),
):
    """Remove a fake device from HA by sending empty discovery payloads.

    Publishes empty retained messages to all discovery topics,
    which tells HA to remove the entities.

    Args:
        model: Device model key.
        address: Simulated Modbus address.
        manager: BoneIO Manager instance.

    Returns:
        Confirmation with removed topic count.
    """
    device_id = f"{address}_{model}"

    if device_id not in _active_fake_devices:
        return {"error": f"Fake device {device_id} not found."}

    device_info = _active_fake_devices.pop(device_id)
    config_helper = manager.config_helper
    message_bus = manager._message_bus
    topic_prefix = config_helper.topic_prefix

    # Unregister discovery topics from config_helper so is_topic_in_autodiscovery
    # won't keep returning True for stale fake-device topics.
    for disc in device_info.get("discovery_msgs", []):
        topic = disc["_discovery_topic"]
        ha_type = _ha_entity_type_for(disc["entity_type"])
        config_helper.remove_autodiscovery_msg(ha_type=ha_type, topic=topic)

    # Remove all discovery messages (empty retained payload)
    for topic in device_info["discovery_topics"]:
        message_bus.send_message(topic=topic, payload="", retain=True)

    # Send OFFLINE
    avail_topic = f"{topic_prefix}/modbus/{device_id}/{STATE}"
    message_bus.send_message(topic=avail_topic, payload="OFFLINE", retain=True)

    _LOGGER.info(
        "Removed fake device %s (%s) — %d discovery topics cleared",
        device_id,
        model,
        len(device_info["discovery_topics"]),
    )

    return {
        "device_id": device_id,
        "removed_topics": len(device_info["discovery_topics"]),
    }


@router.get("/fake-devices")
async def list_fake_devices():
    """List all currently active fake devices.

    Returns:
        List of active fake device summaries.
    """
    return [
        {
            "device_id": device_id,
            "model": info["device_name"],
            "manufacturer": info["manufacturer"],
            "category": info["category"],
            "entity_count": len(info["discovery_topics"]),
            "created_at": info["created_at"],
        }
        for device_id, info in _active_fake_devices.items()
    ]


@router.get("/fake-device/{model}/dashboard")
async def generate_fake_device_dashboard(
    model: str,
    address: int = Query(default=1, description="Simulated Modbus address"),
    style: str = Query(default="standard", description="Dashboard style: 'standard' or 'visual'"),
    manager: Any = Depends(get_manager),
):
    """Generate HA Lovelace dashboard YAML for a fake Modbus device.

    Uses MockModbusCoordinator to build entity metadata from the device
    JSON, then dispatches to category-aware card templates to produce
    ready-to-paste Lovelace YAML.

    Args:
        model: Device model key (e.g. "wanas415", "sdm120").
        address: Simulated Modbus address (default: 1).
        style: 'standard' for tile cards, 'visual' for SVG diagram + tiles.
        manager: BoneIO Manager instance (injected).

    Returns:
        Dict with device_id, model, category, entity_count, and yaml string.
    """
    try:
        mock_coord = MockModbusCoordinator.from_json(
            model_key=model,
            address=address,
            device_id=f"{address}_{model}",
        )
    except FileNotFoundError as exc:
        return {"error": str(exc)}

    serial = manager.config_helper.serial_no
    device_info = mock_coord.get_device_info()
    device_id = f"{address}_{model}"

    # ── Visual dashboard (SVG diagram) ────────────────────────────────
    if style == "visual" and device_info.get("category") == "hvac":
        from boneio.webui.hvac_svg_templates import generate_recuperator_card

        visual_cards = generate_recuperator_card(
            serial=serial,
            device_id=device_id,
        )

        # Also add standard tile cards below the diagram
        standard_cards = generate_cards_for_device(
            device_id=mock_coord.id,
            entities_list=mock_coord.get_all_entities(),
            serial=serial,
            device_info=device_info,
        )
        all_cards = visual_cards + standard_cards
        yaml_str = cards_to_yaml(all_cards)
        entity_count = sum(1 for c in all_cards if c.get("type") not in ("heading", None))

        _LOGGER.info(
            "Generated visual dashboard YAML for %s (%s): %d cards",
            model,
            device_info.get("model", model),
            len(all_cards),
        )

        return {
            "device_id": device_id,
            "model": device_info.get("model", model),
            "category": device_info.get("category", "other"),
            "entity_count": entity_count,
            "yaml": yaml_str,
            "style": "visual",
        }

    # ── Standard dashboard (tile cards) ───────────────────────────────
    cards = generate_cards_for_device(
        device_id=mock_coord.id,
        entities_list=mock_coord.get_all_entities(),
        serial=serial,
        device_info=device_info,
    )

    yaml_str = cards_to_yaml(cards)

    entity_count = sum(1 for c in cards if c.get("type") not in ("heading", None))

    _LOGGER.info(
        "Generated dashboard YAML for %s (%s): %d cards, %d entities",
        model,
        device_info.get("model", model),
        len(cards),
        entity_count,
    )

    return {
        "device_id": device_id,
        "model": device_info.get("model", model),
        "category": device_info.get("category", "other"),
        "entity_count": entity_count,
        "yaml": yaml_str,
        "style": "standard",
    }
