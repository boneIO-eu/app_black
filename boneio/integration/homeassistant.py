"""Home Assistant MQTT Discovery integration.

This module provides functions to generate MQTT discovery messages
for Home Assistant auto-discovery feature.

Formerly located in: boneio.helper.ha_discovery
"""

from __future__ import annotations

import logging

_LOGGER = logging.getLogger(__name__)

from typing import TYPE_CHECKING, Any

from boneio.const import (
    ADC,
    CLOSE,
    CLOSED,
    CLOSING,
    COVER,
    DOUBLE,
    INPUT,
    IP,
    IRRIGATION,
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
    if config_helper.cloud_registration and config_helper.serial_number:
        # PWA-registered device: use the public PWA domain with TLS
        web_url = f"https://{config_helper.serial_number}.black.boneio.app:8443"
    elif config_helper.is_web_active and config_helper.network_info and IP in config_helper.network_info:
        web_url = f"{config_helper.http_proto}://{config_helper.network_info[IP]}:{config_helper.web_configuration_port}"
    
    web_url_dict = {
        "configuration_url": web_url
    } if web_url else {}
    
    # If area is specified, create a sub-device linked to main device
    # Translate area ID to area name using config_helper
    area_name = config_helper.get_area_name(area) if area else None
    
    _LOGGER.debug(
        "HA Discovery for %s: area=%s, area_name=%s, available_areas=%s, child_devices=%s",
        id, area, area_name, config_helper.areas, config_helper.ha_child_devices
    )
    
    # --- EXPERIMENTAL: ha_child_devices mode ---
    # Outputs, inputs, covers, groups and ADC sensors become child devices.
    # Other sensors (INA219, CPU, Memory, FW Version, Update) stay on the main device.
    _CHILD_DEVICE_TYPES = {OUTPUT, INPUT, COVER, "group", ADC}
    
    if config_helper.ha_child_devices and device_type in _CHILD_DEVICE_TYPES:
        # Build child device name based on naming style
        naming = config_helper.ha_child_devices_naming
        if naming == "device_name_area" and area_name:
            child_device_name = f"{device_name} - {area_name} - {name}"
        elif naming == "device_name_area" or naming == "device_name":
            # device_name_area without area falls back to device_name style
            child_device_name = f"{device_name} - {name}"
        else:
            # 'default' — entity name only (e.g. "OUT 17")
            child_device_name = name

        child_identifier = f"{topic}_{device_type}_{id}"
        device_info = {
            "identifiers": [child_identifier],
            "manufacturer": manufacturer,
            "model": model,
            "model_id": config_helper.real_serial,
            "name": child_device_name,
            "serial_number": config_helper.real_serial,
            "sw_version": __version__,
            "via_device": topic,  # Link to main BoneIO device
            **web_url_dict,
        }
        if area_name:
            device_info["suggested_area"] = area_name
            device_info["identifiers"] = [f"{child_identifier}_{area}"]
        
        # Entity name is None — HA will use the device name
        entity_name = None
    elif area and area_name:
        # Create sub-device named "{device_name} - {area_name}" (e.g., "boneIO Black - Gabinet")
        # All entities with the same area will be grouped under this sub-device
        sub_device_name = f"{device_name} - {area_name}"
        device_info = {
            "identifiers": [f"{topic}_{area}"],  # Use area ID for consistent grouping
            "manufacturer": manufacturer,
            "model": model,
            "model_id": config_helper.real_serial,
            "name": sub_device_name,
            "serial_number": config_helper.real_serial,
            "sw_version": __version__,
            "via_device": topic,  # Link to main BoneIO device
            "suggested_area": area_name,  # Use area ID (lowercase) - HA converts area names to lowercase
            **web_url_dict
        }
        entity_name = name
    else:
        device_info = {
            "identifiers": [topic],
            "manufacturer": manufacturer,
            "model": model,
            "model_id": config_helper.real_serial,
            "name": device_name,
            "serial_number": config_helper.real_serial,
            "sw_version": __version__,
            **web_url_dict
        }
        entity_name = name
    
    # Include area in unique_id so HA treats entities in different areas as distinct
    # This allows moving entities between sub-devices by changing their area
    # Let's test topic only, don't add area into entity_id.
    # Remove slashes from unique_id to avoid HA issues
    unique_id_prefix = f"{topic.replace("/", "_")}_{area}" if area else topic.replace("/", "_")
    unique_id_prefix = topic.replace("/", "_")
    unique_id = f"{unique_id_prefix}_{device_type}{id}"
    default_entity_id = f"{entity_type}.{config_helper.serial_number}_{id}"
    
    return {
        "availability": [{"topic": f"{topic}/{STATE}"}],
        "optimistic": False,
        "device": device_info,
        "name": entity_name,
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
    output_discovery_payload: dict[str, Any] | None = None,
    **kwargs
) -> dict[str, str]:
    """Create availability topic for virtual energy sensors.
    
    Args:
        id: Sensor ID
        name: Sensor name (custom name for HA Energy panel)
        config_helper: ConfigHelper instance
        model: Device model
        output_discovery_payload: Optional output's HA discovery payload — used to
            extract the ``device`` block so VES entities share the same HA device
            as the linked output (used when area is '_same_as_output_').
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
    
    # CRITICAL: Replace the device block with the output's device block so
    # Home Assistant groups VES entities under the same device as the output.
    if output_discovery_payload and "device" in output_discovery_payload:
        msg["device"] = output_discovery_payload["device"]
    
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


def _ha_irrigation_device(
    ctrl_id: str,
    ctrl_name: str,
    config_helper: ConfigHelper,
    area: str | None = None,
    area_name: str | None = None,
) -> dict[str, Any]:
    """Create HA child-device metadata for one irrigation controller."""
    topic = config_helper.topic_prefix
    model = f"boneIO Black {config_helper.device_type.title().replace('X', 'x')}"
    device: dict[str, Any] = {
        "identifiers": [f"{topic}_{IRRIGATION}_{ctrl_id}"],
        "manufacturer": "boneIO",
        "model": model,
        "model_id": config_helper.real_serial,
        "name": ctrl_name,
        "serial_number": config_helper.real_serial,
        "sw_version": __version__,
        "via_device": topic,
    }
    if area_name:
        device["suggested_area"] = area_name
    return device


def ha_irrigation_main_switch_message(
    ctrl_id: str,
    ctrl_name: str,
    config_helper: ConfigHelper,
) -> dict[str, Any]:
    """Create main ON/OFF switch discovery for irrigation controller."""
    topic = config_helper.topic_prefix
    msg = ha_switch_availabilty_message(
        id=f"irrigation_{ctrl_id}",
        name=ctrl_name,
        config_helper=config_helper,
        device_type=IRRIGATION,
    )
    msg["device"] = _ha_irrigation_device(ctrl_id, ctrl_name, config_helper)
    msg["icon"] = "mdi:sprinkler"
    msg["state_topic"] = f"{topic}/{IRRIGATION}/{ctrl_id}"
    msg["command_topic"] = f"{topic}/cmd/{IRRIGATION}/{ctrl_id}/set"
    msg["value_template"] = "{{ value_json.state }}"
    return msg


def ha_irrigation_switch_message(
    ctrl_id: str,
    ctrl_name: str,
    suffix: str,
    name: str,
    config_helper: ConfigHelper,
) -> dict[str, Any]:
    """Create switch discovery for irrigation setting/zone/schedule switch."""
    topic = config_helper.topic_prefix
    msg = ha_switch_availabilty_message(
        id=f"irrigation_{ctrl_id}_{suffix.replace('/', '_')}",
        name=name,
        config_helper=config_helper,
        device_type=IRRIGATION,
    )
    msg["device"] = _ha_irrigation_device(ctrl_id, ctrl_name, config_helper)
    msg["state_topic"] = f"{topic}/{IRRIGATION}/{ctrl_id}/{suffix}"
    msg["command_topic"] = f"{topic}/cmd/{IRRIGATION}/{ctrl_id}/{suffix}/set"
    msg["value_template"] = "{{ value_json.state }}"
    return msg


def ha_irrigation_number_message(
    ctrl_id: str,
    ctrl_name: str,
    suffix: str,
    name: str,
    min_val: float,
    max_val: float,
    step: float,
    unit: str,
    config_helper: ConfigHelper,
) -> dict[str, Any]:
    """Create number discovery for irrigation numeric setting."""
    topic = config_helper.topic_prefix
    msg = ha_availabilty_message(
        id=f"irrigation_{ctrl_id}_{suffix.replace('/', '_')}",
        name=name,
        entity_type="number",
        config_helper=config_helper,
        device_type=IRRIGATION,
    )
    msg["device"] = _ha_irrigation_device(ctrl_id, ctrl_name, config_helper)
    msg["state_topic"] = f"{topic}/{IRRIGATION}/{ctrl_id}/{suffix}"
    msg["command_topic"] = f"{topic}/cmd/{IRRIGATION}/{ctrl_id}/{suffix}/set"
    msg["value_template"] = "{{ value_json.value }}"
    msg["mode"] = "box"
    msg["min"] = min_val
    msg["max"] = max_val
    msg["step"] = step
    if unit:
        msg["unit_of_measurement"] = unit
    return msg


def ha_irrigation_button_message(
    ctrl_id: str,
    ctrl_name: str,
    suffix: str,
    name: str,
    payload_press: str,
    config_helper: ConfigHelper,
) -> dict[str, Any]:
    """Create button discovery for irrigation actions."""
    topic = config_helper.topic_prefix
    msg = ha_button_availabilty_message(
        id=f"irrigation_{ctrl_id}_{suffix}",
        name=name,
        config_helper=config_helper,
        payload_press=payload_press,
    )
    msg["device"] = _ha_irrigation_device(ctrl_id, ctrl_name, config_helper)
    msg["command_topic"] = f"{topic}/cmd/{IRRIGATION}/{ctrl_id}/set"
    msg["payload_press"] = payload_press
    return msg


def ha_irrigation_valve_message(
    ctrl_id: str,
    ctrl_name: str,
    suffix: str,
    name: str,
    config_helper: ConfigHelper,
) -> dict[str, Any]:
    """Create valve discovery for irrigation zone.

    Irrigation zones represent physical valves, so they use the HA ``valve``
    entity type with open/close semantics instead of ``switch`` on/off.

    Args:
        ctrl_id: Controller ID.
        ctrl_name: Controller display name.
        suffix: Topic suffix (e.g. ``zone/altana``).
        name: Entity display name.
        config_helper: Config helper for topic prefix and device info.

    Returns:
        HA discovery payload dict for a valve entity.
    """
    topic = config_helper.topic_prefix
    msg = ha_valve_availabilty_message(
        id=f"irrigation_{ctrl_id}_{suffix.replace('/', '_')}",
        name=name,
        config_helper=config_helper,
        device_type=IRRIGATION,
    )
    msg["device"] = _ha_irrigation_device(ctrl_id, ctrl_name, config_helper)
    msg["state_topic"] = f"{topic}/{IRRIGATION}/{ctrl_id}/{suffix}"
    msg["command_topic"] = f"{topic}/cmd/{IRRIGATION}/{ctrl_id}/{suffix}/set"
    msg["value_template"] = "{{ value_json.state }}"
    msg["json_attributes_topic"] = f"{topic}/{IRRIGATION}/{ctrl_id}/{suffix}"
    msg["json_attributes_template"] = (
        "{{ value_json | tojson }}"
    )
    msg["icon"] = "mdi:sprinkler-variant"
    return msg


def ha_irrigation_timestamp_sensor_message(
    ctrl_id: str,
    ctrl_name: str,
    suffix: str,
    name: str,
    config_helper: ConfigHelper,
    icon: str = "mdi:timer-sand",
) -> dict[str, Any]:
    """Create timestamp sensor discovery for irrigation countdown.

    HA shows device_class=timestamp sensors as relative time (e.g. 'in 4 minutes').
    """
    topic = config_helper.topic_prefix
    msg = ha_availabilty_message(
        device_type=IRRIGATION,
        config_helper=config_helper,
        entity_type="sensor",
        id=f"irrigation_{ctrl_id}_{suffix}",
        name=name,
    )
    msg["device"] = _ha_irrigation_device(ctrl_id, ctrl_name, config_helper)
    msg["state_topic"] = f"{topic}/{IRRIGATION}/{ctrl_id}/{suffix}"
    msg["value_template"] = "{{ value_json.value }}"
    msg["device_class"] = "timestamp"
    msg["icon"] = icon
    return msg


def ha_irrigation_select_message(
    ctrl_id: str,
    ctrl_name: str,
    options: list[str],
    config_helper: ConfigHelper,
) -> dict[str, Any]:
    """Create select entity discovery for irrigation water source.

    Args:
        ctrl_id: Controller ID.
        ctrl_name: Controller display name.
        options: List of water source IDs as select options.
        config_helper: Config helper for topic prefix and device info.

    Returns:
        HA discovery payload dict.
    """
    topic = config_helper.topic_prefix
    msg = ha_availabilty_message(
        device_type=IRRIGATION,
        config_helper=config_helper,
        entity_type="select",
        id=f"irrigation_{ctrl_id}_water_source",
        name=f"{ctrl_name} Water Source",
    )
    msg["device"] = _ha_irrigation_device(ctrl_id, ctrl_name, config_helper)
    msg["state_topic"] = f"{topic}/{IRRIGATION}/{ctrl_id}/water_source"
    msg["command_topic"] = f"{topic}/cmd/{IRRIGATION}/{ctrl_id}/water_source/set"
    msg["value_template"] = "{{ value_json.value }}"
    msg["options"] = options
    msg["icon"] = "mdi:water-pump"
    return msg


def ha_irrigation_event_message(
    ctrl_id: str,
    ctrl_name: str,
    config_helper: ConfigHelper,
) -> dict[str, Any]:
    """Create event entity discovery for irrigation controller notifications.

    The event entity fires when notable events occur on the controller,
    such as interlock faults, cycle completions, or standby blocks.
    Home Assistant automations can listen to these events and trigger
    notifications (e.g. mobile push, Telegram, email).

    Event types:
        - interlock_fault: Output blocked by interlock group.
        - cycle_complete: Full irrigation cycle finished.
        - standby_blocked: Start attempt blocked by standby mode.

    Each event payload contains ``event_type`` and additional attributes
    like ``zone``, ``source``, and ``message``.

    Args:
        ctrl_id: Controller ID.
        ctrl_name: Controller display name.
        config_helper: Config helper for topic prefix and device info.

    Returns:
        HA discovery payload dict for an event entity.
    """
    topic = config_helper.topic_prefix
    msg = ha_availabilty_message(
        device_type=IRRIGATION,
        config_helper=config_helper,
        entity_type="event",
        id=f"irrigation_{ctrl_id}_event",
        name=f"{ctrl_name} Event",
    )
    msg["device"] = _ha_irrigation_device(ctrl_id, ctrl_name, config_helper)
    msg["state_topic"] = f"{topic}/{IRRIGATION}/{ctrl_id}/event"
    msg["event_types"] = [
        "interlock_fault",
        "cycle_complete",
        "standby_blocked",
    ]
    msg["icon"] = "mdi:message-alert"
    return msg


def ha_switch_availabilty_message(id: str, config_helper: ConfigHelper, device_type: str = OUTPUT, **kwargs):
    """Create SWITCH availability topic for HA."""
    msg = ha_availabilty_message(device_type=device_type, config_helper=config_helper, entity_type="switch", id=id, **kwargs)
    msg["command_topic"] = f"{config_helper.topic_prefix}/cmd/{device_type}/{id}/set"
    msg["payload_off"] = OFF
    msg["payload_on"] = ON
    msg["value_template"] = "{{ value_json.state }}"
    return msg




def ha_output_duration_number_message(
    id: str,
    name: str,
    min_val: float,
    max_val: float,
    unit: str,
    config_helper: ConfigHelper,
    output_discovery_payload: dict[str, Any] | None = None,
    area: str | None = None,
) -> dict[str, Any]:
    """Create number discovery for output adjustable duration slider.

    The number entity is attached to the SAME HA device as the output itself.
    This is achieved by copying the ``device`` block from the output's
    discovery payload when available.

    Args:
        id: Output entity ID.
        name: Display name (e.g., "OUT 12 Duration").
        min_val: Minimum value in seconds.
        max_val: Maximum value in seconds.
        unit: Unit of measurement for HA slider ("s" or "min").
        config_helper: ConfigHelper instance.
        output_discovery_payload: The output's HA discovery payload — used to
            extract the ``device`` block so both entities share one HA device.
        area: Optional area ID (fallback when output_discovery_payload is None).
    """
    topic = config_helper.topic_prefix

    # Build base message; we will override the device block below
    msg = ha_availabilty_message(
        id=f"{id}_duration",
        name=name,
        entity_type="number",
        config_helper=config_helper,
        device_type=OUTPUT,
        area=area,
    )

    # CRITICAL: Replace the device block with the output's device block so
    # Home Assistant groups both entities under the same device.
    if output_discovery_payload and "device" in output_discovery_payload:
        msg["device"] = output_discovery_payload["device"]

    msg["state_topic"] = f"{topic}/{OUTPUT}/{id}/duration"
    msg["command_topic"] = f"{topic}/cmd/{OUTPUT}/{id}/set_duration"
    msg["value_template"] = "{{ value_json.value }}"
    msg["mode"] = "slider"

    # Convert min/max to the user-selected unit
    if unit == "min":
        msg["min"] = round(min_val / 60, 2)
        msg["max"] = round(max_val / 60, 2)
        range_size = msg["max"] - msg["min"]
        # Step: 0.1min (6s) for ranges ≤10min, 0.5min (30s) for ≤120min, 1min for larger
        if range_size <= 10:
            msg["step"] = 0.1
        elif range_size <= 120:
            msg["step"] = 0.5
        else:
            msg["step"] = 1
        msg["unit_of_measurement"] = "min"
    else:
        msg["min"] = min_val
        msg["max"] = max_val
        range_size = max_val - min_val
        msg["step"] = 1 if range_size <= 600 else 5
        msg["unit_of_measurement"] = "s"

    msg["icon"] = "mdi:timer-outline"

    return msg


def ha_group_availabilty_message(
    id: str,
    config_helper: ConfigHelper,
    output_type: str,
    member_unique_ids: list[str] | None = None,
    **kwargs,
):
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
    if member_unique_ids:
        msg["group"] = member_unique_ids
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
    """Create ADC sensor availability topic for HA.

    Uses device_type=ADC so each ADC sensor becomes a separate child device
    in Home Assistant (like inputs and outputs). Entity name is set to None
    so HA uses the device name.
    """
    msg = ha_availabilty_message(device_type=ADC, config_helper=config_helper, entity_type="sensor", **kwargs)
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
    msg = ha_availabilty_message(device_type=INPUT, config_helper=config_helper, id=id, name=name, model=model, entity_type="binary_sensor", **kwargs)
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

    Includes json_attributes_topic so HA picks up extra attributes
    (e.g. disk_total_gb, memory_used_gb) from the same state topic.

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

    # Expose extra attributes (e.g. disk_total_gb, memory_available_gb)
    state_topic = msg.get("state_topic", f"{config_helper.topic_prefix}/{SENSOR}/{id}")
    msg["json_attributes_topic"] = state_topic
    msg["json_attributes_template"] = (
        "{{ value_json | tojson }}"
    )

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


def modbus_polling_switch_message(
    device_id: str,
    device_name: str,
    model: str,
    manufacturer: str,
    config_helper: ConfigHelper,
    area: str | None = None,
) -> dict[str, Any]:
    """Create HA MQTT autodiscovery message for the per-device polling switch.

    The switch lets the user temporarily enable/disable Modbus register polling
    for a specific device without removing it from the configuration.

    The entity appears under entity_category 'config' in HA, grouped with
    the same Modbus device as its sensor entities.

    Args:
        device_id: Modbus coordinator ID (e.g., "sdm630").
        device_name: Human-readable device name (e.g., "SDM630 Energy Meter").
        model: Device model string.
        manufacturer: Device manufacturer.
        config_helper: ConfigHelper instance.
        area: Optional area for sub-device grouping.

    Returns:
        Discovery payload dict with an extra ``_topic`` key containing the
        discovery topic (caller should pop it before publishing).
    """
    topic_prefix = config_helper.topic_prefix
    entity_id = f"{device_id}_polling"

    discovery_topic = (
        f"{config_helper.ha_discovery_prefix}/switch/"
        f"{config_helper.serial_number}/{entity_id}/config"
    )

    area_name = config_helper.get_area_name(area) if area else None

    device_info: dict[str, Any] = {
        "identifiers": [device_id],
        "manufacturer": manufacturer,
        "model": model,
        "name": device_name,
        "sw_version": __version__,
        "via_device": topic_prefix,
    }
    if area_name:
        device_info["suggested_area"] = area_name

    return {
        "_topic": discovery_topic,
        "availability": [{"topic": f"{topic_prefix}/{STATE}"}],
        "device": device_info,
        "name": "Polling",
        "unique_id": f"{topic_prefix.replace('/', '_')}_modbus_{entity_id}",
        "default_entity_id": f"switch.{config_helper.serial_number}_{entity_id}",
        "state_topic": f"{topic_prefix}/modbus/{device_id}/polling",
        "command_topic": f"{topic_prefix}/cmd/modbus/{device_id}/set_polling",
        "payload_on": ON,
        "payload_off": OFF,
        "value_template": "{{ value_json.state }}",
        "icon": "mdi:sync",
        "entity_category": "config",
        "optimistic": False,
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
    
    # Remove entity_id from kwargs to avoid conflict
    kwargs_filtered = {k: v for k, v in kwargs.items() if k != 'entity_id'}
    
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
        **kwargs_filtered,
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
    
    # Remove entity_id from kwargs to avoid conflict
    kwargs_filtered = {k: v for k, v in kwargs.items() if k != 'entity_id'}
    
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
        **kwargs_filtered,
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
    
    # Remove entity_id from kwargs to avoid conflict
    kwargs_filtered = {k: v for k, v in kwargs.items() if k != 'entity_id'}
    
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
        **kwargs_filtered,
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
    id: str, name: str, device_class: str | None, config_helper: ConfigHelper, **kwargs
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
    id: str, name: str, device_class: str | None, config_helper: ConfigHelper, **kwargs
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


def ha_gate_cover_availability_message(
    id: str, name: str, device_class: str, config_helper: ConfigHelper, **kwargs
):
    """Create Gate Cover availability topic for HA.

    Used by template gate_cover platform for gates, garage doors, barriers, doors.
    Unlike regular covers, gate covers use impulse-based control and contact sensors.

    Args:
        id: Entity identifier.
        name: Display name.
        device_class: HA device_class (gate, garage_door, barrier, door).
        config_helper: ConfigHelper instance.
    """
    topic = config_helper.topic_prefix
    kwargs = {"device_class": device_class, **kwargs}
    msg = ha_availabilty_message(
        device_type=COVER, entity_type="cover", config_helper=config_helper, id=id, name=name, **kwargs
    )

    return {
        **msg,
        "command_topic": f"{topic}/cmd/cover/{id}/set",
        "payload_open": OPEN,
        "payload_close": CLOSE,
        "payload_stop": STOP,
        "state_open": OPEN,
        "state_opening": OPENING,
        "state_closed": CLOSED,
        "state_closing": CLOSING,
        "state_topic": f"{topic}/{COVER}/{id}/{STATE}",
        "json_attributes_topic": f"{topic}/{COVER}/{id}/attributes",
    }


def ha_update_availability_message(
    id: str, name: str, config_helper: ConfigHelper, **kwargs
) -> HomeAssistantDiscoveryMessage:
    """Create Update availability topic for HA.
    
    Args:
        id: Entity ID
        name: Entity name
        config_helper: ConfigHelper instance
        **kwargs: Additional fields (e.g., device_class, entity_category)
    
    Returns:
        HA discovery message for Update entity
    """
    topic = config_helper.topic_prefix
    
    # Default kwargs for Update entity
    default_kwargs = {
        "device_class": "firmware",
        "entity_category": "diagnostic",
    }
    
    msg = ha_availabilty_message(
        device_type="update",
        entity_type="update",
        config_helper=config_helper,
        id=id,
        name=name,
        **{**default_kwargs, **kwargs}
    )
    
    result = {
        **msg,
        "state_topic": f"{topic}/update/state",
        "command_topic": f"{topic}/update/install",
        "payload_install": "INSTALL",
        "icon": "mdi:update",
    }
    
    _LOGGER.debug("Update HA discovery message: %s", result)
    
    return result


def ha_migration_alert_availability_message(
    config_helper: ConfigHelper,
    **kwargs,
) -> HomeAssistantDiscoveryMessage:
    """Create Migration Alert binary_sensor (diagnostic) for HA.

    Returns a binary_sensor with ``device_class: problem`` that is ON when
    system migrations are pending and OFF when all migrations are applied.
    Attributes (count, description) are published on a separate JSON
    attributes topic.

    Args:
        config_helper: ConfigHelper instance.
        **kwargs: Additional fields forwarded to ``ha_availabilty_message``.

    Returns:
        HA discovery message dict for the migration alert binary_sensor.
    """
    topic = config_helper.topic_prefix

    msg = ha_availabilty_message(
        id="migration_alert",
        name="Migration Alert",
        entity_type="binary_sensor",
        config_helper=config_helper,
        device_type="update",
        **kwargs,
    )
    msg["state_topic"] = f"{topic}/migration/state"
    msg["value_template"] = "{{ value_json.state }}"
    msg["payload_on"] = "ON"
    msg["payload_off"] = "OFF"
    msg["json_attributes_topic"] = f"{topic}/migration/attributes"
    msg["icon"] = "mdi:alert-decagram"
    msg["entity_category"] = "diagnostic"
    msg["device_class"] = "problem"

    return msg


def ha_climate_availability_message(
    id: str,
    name: str,
    config_helper: ConfigHelper,
    modes: list[str] | None = None,
    min_temp: float = 5.0,
    max_temp: float = 35.0,
    temp_step: float = 0.5,
    area: str | None = None,
    **kwargs,
) -> HomeAssistantDiscoveryMessage:
    """Create Climate (thermostat) availability topic for HA.

    Args:
        id: Entity ID.
        name: Entity name.
        config_helper: ConfigHelper instance.
        modes: Supported HVAC modes (default: ["off", "heat"]).
        min_temp: Minimum target temperature.
        max_temp: Maximum target temperature.
        temp_step: Temperature step size.
        area: Optional area for sub-device grouping.
        **kwargs: Additional fields.

    Returns:
        HA discovery message for Climate entity.
    """
    from boneio.const import CLIMATE

    topic = config_helper.topic_prefix
    if modes is None:
        modes = ["off", "heat"]

    msg = ha_availabilty_message(
        device_type=CLIMATE,
        entity_type="climate",
        config_helper=config_helper,
        id=id,
        name=name,
        area=area,
        **kwargs,
    )

    return {
        **msg,
        # State topics (JSON payload)
        "mode_state_topic": f"{topic}/{CLIMATE}/{id}",
        "mode_state_template": "{{ value_json.mode }}",
        "current_temperature_topic": f"{topic}/{CLIMATE}/{id}",
        "current_temperature_template": "{{ value_json.current_temperature }}",
        "temperature_state_topic": f"{topic}/{CLIMATE}/{id}",
        "temperature_state_template": "{{ value_json.target_temperature }}",
        "action_topic": f"{topic}/{CLIMATE}/{id}",
        "action_template": "{{ value_json.action }}",
        # Command topics
        "mode_command_topic": f"{topic}/cmd/{CLIMATE}/{id}/mode/set",
        "temperature_command_topic": f"{topic}/cmd/{CLIMATE}/{id}/temperature/set",
        # Configuration
        "modes": modes,
        "min_temp": min_temp,
        "max_temp": max_temp,
        "temp_step": temp_step,
        "temperature_unit": "C",
        "precision": 0.1,
    }


def ha_alarm_panel_availability_message(
    id: str,
    name: str,
    config_helper: ConfigHelper,
    supported_features: list[str] | None = None,
    code: str = "REMOTE_CODE",
    code_arm_required: bool = False,
    area: str | None = None,
    **kwargs,
) -> HomeAssistantDiscoveryMessage:
    """Create Alarm Control Panel availability topic for HA.

    Args:
        id: Entity ID.
        name: Entity name.
        config_helper: ConfigHelper instance.
        supported_features: List of supported features.
        code: Code type — 'REMOTE_CODE' for HA-managed codes.
        code_arm_required: Whether code is required to arm.
        area: Optional area for sub-device grouping.
        **kwargs: Additional fields.

    Returns:
        HA discovery message for Alarm Control Panel entity.
    """
    from boneio.const import ALARM_CONTROL_PANEL

    topic = config_helper.topic_prefix
    if supported_features is None:
        supported_features = ["arm_home", "arm_away", "arm_night", "trigger"]

    msg = ha_availabilty_message(
        device_type=ALARM_CONTROL_PANEL,
        entity_type="alarm_control_panel",
        config_helper=config_helper,
        id=id,
        name=name,
        area=area,
        **kwargs,
    )

    has_code = bool(code)
    result: dict[str, Any] = {
        **msg,
        "state_topic": f"{topic}/alarm/{id}/state",
        "command_topic": f"{topic}/cmd/alarm/{id}/set",
        "supported_features": supported_features,
        "code_arm_required": code_arm_required if has_code else False,
        "code_disarm_required": has_code,
        "code_trigger_required": False,
        "json_attributes_topic": f"{topic}/alarm/{id}/attributes",
    }

    if has_code:
        result["command_template"] = '{"action":"{{ action }}","code":"{{ code }}"}'
        result["code"] = code

    return result
