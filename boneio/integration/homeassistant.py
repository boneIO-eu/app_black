"""Home Assistant MQTT Discovery integration.

This module provides functions to generate MQTT discovery messages
for Home Assistant auto-discovery feature.

Formerly located in: boneio.helper.ha_discovery
"""

from __future__ import annotations

import logging

_LOGGER = logging.getLogger(__name__)

from boneio.const import (
    CLOSE,
    CLOSED,
    CLOSING,
    COVER,
    DOUBLE,
    INPUT,
    INPUT_SENSOR,
    IP,
    LONG,
    NUMERIC,
    OFF,
    ON,
    OPEN,
    OPENING,
    OUTPUT,
    SELECT,
    SENSOR,
    SINGLE,
    STATE,
    STOP,
    TRIPLE,
)
from boneio.version import __version__
from typing import Any, TypedDict, TYPE_CHECKING
if TYPE_CHECKING:
    from boneio.core.config.config_helper import ConfigHelper


# Type alias for Home Assistant MQTT discovery messages
# Using dict[str, Any] because different entity types (sensor, light, cover, button, etc.)
# use different subsets of fields, making a strict TypedDict impractical
HomeAssistantDiscoveryMessage = dict[str, Any]


def ha_availabilty_message(
    id: str,
    name: str,
    entity_type: str,
    config_helper: ConfigHelper,
    device_name: str | None = None,
    topic: str | None = None,
    device_type: str = INPUT,
    manufacturer: str = "boneIO",
    model: str = "boneIO Relay Board",
    web_url: str | None = None,
    area: str | None = None,
    **kwargs,
) -> HomeAssistantDiscoveryMessage:
    """Create availability topic for HA.
    
    Args:
        id: Entity ID
        name: Entity name
        topic: MQTT topic prefix
        device_name: Device name for HA
        device_type: Type of device (relay, input, sensor, etc.)
        model: Device model name
        web_url: Optional configuration URL
        config_helper: Optional ConfigHelper instance (used to extract topic/name/model)
        area: Optional area ID (from 'areas' config section) - creates sub-device when set
        **kwargs: Additional fields to include in the message
    """
    # Extract values from config_helper if provided
    topic = config_helper.topic_prefix if topic is None else topic
    device_name = config_helper.name if device_name is None else device_name
    model = f"boneIO Black {config_helper.device_type.title().replace('X', 'x')}"
    if config_helper.is_web_active and config_helper.network_info and IP in config_helper.network_info:
        web_url = f"{config_helper.http_proto}://{config_helper.network_info[IP]}:{config_helper.web_configuration_port}"
    
    web_url_dict = {
        "configuration_url": web_url
    } if web_url else {}
    
    # If area is specified, create a sub-device linked to main device
    # Translate area ID to area name using config_helper
    area_name = config_helper.get_area_name(area) if area else None
    
    _LOGGER.debug(
        "HA Discovery for %s: area=%s, area_name=%s, available_areas=%s",
        id, area, area_name, config_helper.areas
    )
    
    if area and area_name:
        # Create sub-device named "{device_name} - {area_name}" (e.g., "boneIO Black - Gabinet")
        # All entities with the same area will be grouped under this sub-device
        sub_device_name = f"{device_name} - {area_name}"
        device_info = {
            "identifiers": [f"{topic}_{area}"],  # Use area ID for consistent grouping
            "manufacturer": manufacturer,
            "model": model,
            "model_id": config_helper.serial_number,
            "name": sub_device_name,
            "serial_number": config_helper.serial_number,
            "sw_version": __version__,
            "via_device": topic,  # Link to main BoneIO device
            "suggested_area": area_name,  # Use area ID (lowercase) - HA converts area names to lowercase
            **web_url_dict
        }
    else:
        device_info = {
            "identifiers": [topic],
            "manufacturer": manufacturer,
            "model": model,
            "model_id": config_helper.serial_number,
            "name": device_name,
            "serial_number": config_helper.serial_number,
            "sw_version": __version__,
            **web_url_dict
        }
    
    # Include area in unique_id so HA treats entities in different areas as distinct
    # This allows moving entities between sub-devices by changing their area
    # Let's test topic only, don't add area into entity_id.
    # Remove slashes from unique_id to avoid HA issues
    unique_id_prefix = f"{topic.replace("/", "_")}_{area}" if area else topic.replace("/", "_")
    unique_id = f"{unique_id_prefix}_{device_type}{id}"
    default_entity_id = f"{entity_type}.{config_helper.serial_number}_{id}"
    
    return {
        "availability": [{"topic": f"{topic}/{STATE}"}],
        "optimistic": False,
        "device": device_info,
        "name": name,
        "state_topic": f"{topic}/{device_type}/{id}",
        "unique_id": unique_id,
        "default_entity_id": default_entity_id,
        # "object_id": f"{topic}{device_type}{id}",
        **kwargs,
    }


def ha_virtual_energy_sensor_availabilty_message(
    id: str,
    name: str,
    config_helper: ConfigHelper,
    model: str = "boneIO Black",
    **kwargs
) -> dict[str, str]:
    """Create availability topic for virtual energy sensors.
    
    Args:
        id: Sensor ID
        name: Sensor name (custom name for HA Energy panel)
        config_helper: ConfigHelper instance
        model: Device model
        **kwargs: Additional fields (unit_of_measurement, device_class, state_class, area)
        
    Returns:
        HA discovery message dict
    """
    topic = config_helper.topic_prefix
    
    # Extract sensor base ID (remove _power, _energy, _flow, _water suffix)
    base_id = id.rsplit('_', 1)[0] if id.endswith(('_power', '_energy', '_flow', '_water')) else id
    
    msg = ha_availabilty_message(
        device_type=SENSOR,
        entity_type=SENSOR,
        config_helper=config_helper,
        id=id,
        name=name,
        model=model,
        **kwargs
    )
    
    # Set state topic to the virtual energy sensor topic
    msg["state_topic"] = f"{topic}/energy/{base_id}"
    
    # Set value template based on sensor type
    if id.endswith('_power'):
        msg["value_template"] = "{{ value_json.power }}"
    elif id.endswith('_energy'):
        msg["value_template"] = "{{ value_json.energy }}"
    elif id.endswith('_flow'):
        msg["value_template"] = "{{ value_json.volume_flow_rate }}"
    elif id.endswith('_water'):
        msg["value_template"] = "{{ value_json.water }}"
    else:
        msg["value_template"] = "{{ value_json.state }}"
    
    return msg


def ha_light_availabilty_message(id: str, config_helper: ConfigHelper, device_type: str = OUTPUT, **kwargs):
    """Create LIGHT availability topic for HA."""
    msg = ha_availabilty_message(device_type=device_type, config_helper=config_helper, entity_type="light", id=id, **kwargs)
    msg["command_topic"] = f"{config_helper.topic_prefix}/cmd/{device_type}/{id}/set"
    msg["payload_off"] = OFF
    msg["payload_on"] = ON
    msg["state_value_template"] = "{{ value_json.state }}"
    return msg


def ha_led_availabilty_message(id: str, config_helper: ConfigHelper, **kwargs):
    """Create LED availability topic for HA."""
    msg = ha_availabilty_message(device_type=OUTPUT, config_helper=config_helper, entity_type="light", id=id, **kwargs)
    msg["command_topic"] = f"{config_helper.topic_prefix}/cmd/{OUTPUT}/{id}/set"
    msg["brightness_state_topic"] = f"{config_helper.topic_prefix}/{OUTPUT}/{id}"
    msg["brightness_command_topic"] = f"{config_helper.topic_prefix}/cmd/{OUTPUT}/{id}/set_brightness"
    msg["brightness_scale"] = 65535
    msg["payload_off"] = OFF
    msg["payload_on"] = ON
    msg["state_value_template"] = "{{ value_json.state }}"
    msg["brightness_value_template"] = "{{ value_json.brightness }}"
    return msg


def ha_button_availabilty_message(
    id: str, config_helper: ConfigHelper, payload_press: str = "reload", **kwargs
):
    """Create BUTTON availability topic for HA."""
    msg = ha_availabilty_message(device_type="button", config_helper=config_helper, entity_type="button", id=id, **kwargs)
    msg["command_topic"] = f"{config_helper.topic_prefix}/cmd/button/{id}/set"
    msg["payload_press"] = payload_press
    return msg


def ha_switch_availabilty_message(id: str, config_helper: ConfigHelper, device_type: str = OUTPUT, **kwargs):
    """Create SWITCH availability topic for HA."""
    msg = ha_availabilty_message(device_type=device_type, config_helper=config_helper, entity_type="switch", id=id, **kwargs)
    msg["command_topic"] = f"{config_helper.topic_prefix}/cmd/{device_type}/{id}/set"
    msg["payload_off"] = OFF
    msg["payload_on"] = ON
    msg["value_template"] = "{{ value_json.state }}"
    return msg


def ha_group_availabilty_message(id: str, config_helper: ConfigHelper, output_type: str, **kwargs):
    """Create GROUP (output group) availability topic for HA.
    
    Groups use 'group' as device_type in MQTT topics instead of 'relay'.
    """
    from boneio.const import GROUP
    entity_type = "light" if output_type == "light" else "switch"
    msg = ha_availabilty_message(device_type=GROUP, config_helper=config_helper, entity_type=entity_type, id=id, **kwargs)
    msg["command_topic"] = f"{config_helper.topic_prefix}/cmd/{GROUP}/{id}/set"
    msg["payload_off"] = OFF
    msg["payload_on"] = ON
    if output_type == "light":
        msg["icon"] = "mdi:lightbulb-multiple"
        msg["state_value_template"] = "{{ value_json.state }}"
    else:
        msg["value_template"] = "{{ value_json.state }}"
    return msg


def ha_valve_availabilty_message(id: str, config_helper: ConfigHelper, device_type: str = OUTPUT, **kwargs):
    """Create Valve availability topic for HA."""
    msg = ha_availabilty_message(device_type=device_type, config_helper=config_helper, entity_type="valve", id=id, **kwargs)
    msg["command_topic"] = f"{config_helper.topic_prefix}/cmd/{device_type}/{id}/set"
    msg["payload_close"] = OFF
    msg["payload_open"] = ON
    msg["state_open"] = ON
    msg["state_closed"] = OFF
    msg["reports_position"] = False
    msg["value_template"] = "{{ value_json.state }}"
    return msg


def ha_event_availabilty_message(config_helper: ConfigHelper, mqtt_sequences: dict | None = None, enable_triple_click: bool = False, **kwargs):
    """Create Event availability topic for HA.
    
    Args:
        config_helper: ConfigHelper instance
        mqtt_sequences: Dict of sequence types to publish to MQTT (e.g., {"double_then_long": True})
        enable_triple_click: Whether triple click detection is enabled
        **kwargs: Additional arguments passed to ha_availabilty_message
    """
    msg = ha_availabilty_message(device_type=INPUT, config_helper=config_helper, entity_type="event", **kwargs)
    msg["icon"] = "mdi:gesture-double-tap"
    
    # Base event types
    event_types = [SINGLE, DOUBLE, LONG]
    
    # Add triple click if enabled
    if enable_triple_click:
        event_types.append(TRIPLE)
    
    # Add sequence event types if enabled in mqtt_sequences
    if mqtt_sequences:
        if mqtt_sequences.get("double_then_long"):
            event_types.append("double_then_long")
        if mqtt_sequences.get("single_then_long"):
            event_types.append("single_then_long")
        if mqtt_sequences.get("double_then_single"):
            event_types.append("double_then_single")
    
    msg["event_types"] = event_types
    return msg


def ha_adc_sensor_availabilty_message(config_helper: ConfigHelper, **kwargs):
    msg = ha_availabilty_message(device_type=SENSOR, config_helper=config_helper, entity_type="sensor", **kwargs)
    msg["unit_of_measurement"] = "V"
    msg["device_class"] = "voltage"
    msg["state_class"] = "measurement"
    return msg


def ha_sensor_availabilty_message(config_helper: ConfigHelper, device_type: str = SENSOR, **kwargs):
    msg = ha_availabilty_message(device_type=device_type, config_helper=config_helper, **kwargs)
    return msg


def ha_binary_sensor_availabilty_message(
    id: str, name: str, config_helper: ConfigHelper, model: str = "boneIO Relay Board", **kwargs
):
    """Create availability topic for HA."""
    msg = ha_availabilty_message(device_type=INPUT_SENSOR, config_helper=config_helper, id=id, name=name, model=model, entity_type="binary_sensor", **kwargs)
    msg["payload_on"] = "pressed"
    msg["payload_off"] = "released"
    return msg


def ha_sensor_ina_availabilty_message(
    id: str, name: str, config_helper: ConfigHelper, model: str = "boneIO Relay Board", **kwargs
):
    """Create availability topic for HA INA219 power sensor (diagnostic)."""
    msg = ha_availabilty_message(device_type=SENSOR, config_helper=config_helper, id=id, name=name, model=model, entity_type="sensor", **kwargs)
    msg["state_class"] = "measurement"
    msg["value_template"] = "{{ value_json.state }}"
    msg["entity_category"] = "diagnostic"
    return msg


def ha_sensor_temp_availabilty_message(
    id: str, name: str, config_helper: ConfigHelper, model: str = "boneIO Relay Board", **kwargs
):
    """Create availability topic for HA board temperature sensor (diagnostic)."""
    msg = ha_availabilty_message(device_type=SENSOR, config_helper=config_helper, id=id, name=name, model=model, entity_type="sensor", **kwargs)
    msg["device_class"] = "temperature"
    msg["state_class"] = "measurement"
    msg["value_template"] = "{{ value_json.state }}"
    msg["entity_category"] = "diagnostic"
    return msg


def ha_sensor_system_availabilty_message(
    id: str,
    name: str,
    config_helper: ConfigHelper,
    model: str = "boneIO Black",
    device_class: str | None = None,
    icon: str | None = None,
    **kwargs
):
    """Create availability topic for system sensors (disk, memory, CPU).
    
    Args:
        id: Sensor ID
        name: Sensor name
        config_helper: ConfigHelper instance
        model: Device model
        device_class: HA device class (optional)
        icon: MDI icon (optional)
        **kwargs: Additional fields
        
    Returns:
        HA discovery message dict
    """
    msg = ha_availabilty_message(
        device_type=SENSOR,
        config_helper=config_helper,
        id=id,
        name=name,
        model=model,
        entity_type="sensor",
        **kwargs
    )
    msg["state_class"] = "measurement"
    msg["value_template"] = "{{ value_json.state }}"
    msg["entity_category"] = "diagnostic"
    
    if device_class:
        msg["device_class"] = device_class
    if icon:
        msg["icon"] = icon
        
    return msg


def modbus_availabilty_message(
    id: str,
    entity_id: str,
    name: str,
    state_topic_base: str,
    config_helper: ConfigHelper,
    model: str,
    device_type: str = SENSOR,
    **kwargs,
):
    """Create Modbus availability topic for HA."""
    return {
        "availability": [{"topic": f"{config_helper.topic_prefix}/modbus/{id}/{STATE}"}],
        "device": {
            "identifiers": [id],
            "manufacturer": "boneIO",
            "model": model,
            "name": name,
            "sw_version": __version__,
        },
        "name": entity_id,
        "state_topic": f"{config_helper.topic_prefix}/modbus/{id}/{state_topic_base}",
        "unique_id": f"{config_helper.topic_prefix.replace('/', '_')}{entity_id.replace('_', '').lower()}{name.lower()}",
        **kwargs,
    }

def modbus_sensor_availabilty_message(
    entity_id: str,
    entity_name: str,
    device_id: str,
    device_name: str,
    manufacturer: str,
    state_topic_base: str,
    config_helper: ConfigHelper,
    model: str,
    device_type: str = SENSOR,
    area: str | None = None,
    has_custom_id: bool = False,
    **kwargs,
) -> HomeAssistantDiscoveryMessage:
    """Create Modbus Sensor availability topic for HA.
    
    Args:
        entity_id: Unique entity identifier (e.g., "sdm630voltage_l1")
        entity_name: Human-readable entity name (e.g., "Voltage L1")
        device_id: Modbus device identifier (e.g., "sdm630")
        device_name: Human-readable device name (e.g., "SDM630 Energy Meter")
        manufacturer: Device manufacturer
        state_topic_base: Base address for state topic
        config_helper: Configuration helper
        model: Device model name
        device_type: Type of device for HA
        area: Optional area for sub-device grouping
        has_custom_id: True if user defined custom ID, False if auto-generated
        **kwargs: Additional fields (unit_of_measurement, device_class, etc.)
    """
    topic = config_helper.topic_prefix
    
    # Use base ha_availabilty_message and override modbus-specific fields
    msg = ha_availabilty_message(
        id=entity_id,
        name=entity_name,
        entity_type="sensor",
        config_helper=config_helper,
        device_name=device_name,
        topic=topic,
        device_type=device_type,
        manufacturer=manufacturer,
        model=model,
        area=area,
        **kwargs,
    )
    
    # Override with modbus-specific values
    msg["availability"] = [{"topic": f"{topic}/modbus/{device_id}/{STATE}"}]
    msg["state_topic"] = f"{topic}/modbus/{device_id}/{state_topic_base}"
    msg["device"]["identifiers"] = [device_id]
    msg["device"]["via_device"] = topic
    # Use entity_id directly when user defined custom ID (entity_id already contains device_id prefix)
    # Otherwise use serial_number (default from ha_availabilty_message)
    if has_custom_id:
        msg["default_entity_id"] = f"sensor.{entity_id}"
    
    return msg

def modbus_select_availabilty_message(
    entity_id: str,
    entity_name: str,
    device_id: str,
    device_name: str,
    manufacturer: str,
    state_topic_base: str,
    config_helper: ConfigHelper,
    model: str,
    device_type: str = SELECT,
    area: str | None = None,
    has_custom_id: bool = False,
    **kwargs,
) -> HomeAssistantDiscoveryMessage:
    """Create Modbus Select availability topic for HA.
    
    Args:
        entity_id: Unique entity identifier
        entity_name: Human-readable entity name
        device_id: Modbus device identifier
        device_name: Human-readable device name
        manufacturer: Device manufacturer
        state_topic_base: Base address for state topic
        config_helper: Configuration helper
        model: Device model name
        device_type: Type of device for HA
        area: Optional area for sub-device grouping
        has_custom_id: True if user defined custom ID, False if auto-generated
        **kwargs: Additional fields
    """
    topic = config_helper.topic_prefix
    
    # Use base ha_availabilty_message and override modbus-specific fields
    msg = ha_availabilty_message(
        id=entity_id,
        name=entity_name,
        entity_type="select",
        config_helper=config_helper,
        device_name=device_name,
        topic=topic,
        device_type=device_type,
        manufacturer=manufacturer,
        model=model,
        area=area,
        **kwargs,
    )
    
    # Override with modbus-specific values
    msg["availability"] = [{"topic": f"{topic}/modbus/{device_id}/{STATE}"}]
    msg["state_topic"] = f"{topic}/modbus/{device_id}/{state_topic_base}"
    msg["device"]["identifiers"] = [device_id]
    msg["device"]["via_device"] = topic
    # Use entity_id directly when user defined custom ID (entity_id already contains device_id prefix)
    if has_custom_id:
        msg["default_entity_id"] = f"select.{entity_id}"
    
    return msg


def modbus_numeric_availabilty_message(
    entity_id: str,
    entity_name: str,
    device_id: str,
    device_name: str,
    manufacturer: str,
    state_topic_base: str,
    config_helper: ConfigHelper,
    model: str,
    device_type: str = NUMERIC,
    area: str | None = None,
    has_custom_id: bool = False,
    **kwargs,
) -> HomeAssistantDiscoveryMessage:
    """Create Modbus Numeric availability topic for HA.
    
    Args:
        entity_id: Unique entity identifier
        entity_name: Human-readable entity name
        device_id: Modbus device identifier
        device_name: Human-readable device name
        manufacturer: Device manufacturer
        state_topic_base: Base address for state topic
        config_helper: Configuration helper
        model: Device model name
        device_type: Type of device for HA
        area: Optional area for sub-device grouping
        has_custom_id: True if user defined custom ID, False if auto-generated
        **kwargs: Additional fields
    """
    topic = config_helper.topic_prefix
    
    # Use base ha_availabilty_message and override modbus-specific fields
    msg = ha_availabilty_message(
        id=entity_id,
        name=entity_name,
        entity_type="number",
        config_helper=config_helper,
        device_name=device_name,
        topic=topic,
        device_type=device_type,
        manufacturer=manufacturer,
        model=model,
        area=area,
        **kwargs,
    )
    
    # Override with modbus-specific values
    msg["availability"] = [{"topic": f"{topic}/modbus/{device_id}/{STATE}"}]
    msg["state_topic"] = f"{topic}/modbus/{device_id}/{state_topic_base}"
    msg["device"]["identifiers"] = [device_id]
    msg["device"]["via_device"] = topic
    # Use entity_id directly when user defined custom ID (entity_id already contains device_id prefix)
    if has_custom_id:
        msg["default_entity_id"] = f"number.{entity_id}"
    
    return msg


def ha_cover_availabilty_message(
    id: str, name: str, device_class: str, config_helper: ConfigHelper, **kwargs
):
    """Create Cover availability topic for HA."""
    topic = config_helper.topic_prefix
    kwargs = {"device_class": device_class, **kwargs} if device_class else { **kwargs }
    msg = ha_availabilty_message(
        device_type=COVER, entity_type="cover", config_helper=config_helper, id=id, name=name, **kwargs
    )

    return {
        **msg,
        "command_topic": f"{topic}/cmd/cover/{id}/set",
        "set_position_topic": f"{topic}/cmd/cover/{id}/pos",
        "payload_open": OPEN,
        "payload_close": CLOSE,
        "payload_stop": STOP,
        "state_open": OPEN,
        "state_opening": OPENING,
        "state_closed": CLOSED,
        "state_closing": CLOSING,
        "state_topic": f"{topic}/{COVER}/{id}/state",
        "position_template": '{{ value_json.position }}',
        "position_topic": f"{topic}/{COVER}/{id}/pos",
    }


def ha_cover_with_tilt_availabilty_message(
    id: str, name: str, device_class: str, config_helper: ConfigHelper, **kwargs
):
    """Create Cover with tilt availability topic for HA."""
    topic = config_helper.topic_prefix
    kwargs = {"device_class": device_class, **kwargs} if device_class else { **kwargs }
    msg = ha_availabilty_message(
        device_type=COVER, entity_type="cover", config_helper=config_helper, id=id, name=name, **kwargs
    )

    return {
        **msg,
        "command_topic": f"{topic}/cmd/cover/{id}/set",
        "set_position_topic": f"{topic}/cmd/cover/{id}/pos",
        "tilt_command_topic": f"{topic}/cmd/cover/{id}/tilt",
        "payload_open": OPEN,
        "payload_close": CLOSE,
        "payload_stop": STOP,
        "payload_stop_tilt": STOP,
        "state_open": OPEN,
        "state_opening": OPENING,
        "state_closed": CLOSED,
        "state_closing": CLOSING,
        "state_topic": f"{topic}/{COVER}/{id}/state",
        "position_topic": f"{topic}/{COVER}/{id}/pos",
        "tilt_status_topic": f"{topic}/{COVER}/{id}/pos",
        "position_template": '{{ value_json.position }}',
        "tilt_status_template": '{{ value_json.tilt }}',
    }
