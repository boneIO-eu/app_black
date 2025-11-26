"""Home Assistant MQTT Discovery integration.

This module provides functions to generate MQTT discovery messages
for Home Assistant auto-discovery feature.

Formerly located in: boneio.helper.ha_discovery
"""

from __future__ import annotations

from boneio.const import (
    CLOSE,
    CLOSED,
    CLOSING,
    COVER,
    DOUBLE,
    INPUT,
    INPUT_SENSOR,
    LONG,
    NUMERIC,
    OFF,
    ON,
    OPEN,
    OPENING,
    RELAY,
    SELECT,
    SENSOR,
    SINGLE,
    STATE,
    STOP,
)
from boneio.version import __version__


def ha_availabilty_message(
    id: str,
    name: str,
    topic: str = "boneIO",
    device_name: str = "boneIO",
    device_type: str = INPUT,
    model: str = "boneIO Relay Board",
    web_url: str | None = None,
    config_helper=None,
    **kwargs,
):
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
        **kwargs: Additional fields to include in the message
    """
    # Extract values from config_helper if provided
    if config_helper is not None:
        topic = config_helper.topic_prefix
        device_name = config_helper.name
        model = config_helper.device_type
        if config_helper.is_web_active and config_helper.network_info:
            web_url = f"http://{config_helper.network_info.get('ip', 'localhost')}:9000"
    
    web_url_dict = {
        "configuration_url": web_url
    } if web_url else {}
    return {
        "availability": [{"topic": f"{topic}/{STATE}"}],
        "optimistic": False,
        "device": {
            "identifiers": [topic],
            "manufacturer": "boneIO",
            "model": model,
            "name": device_name,
            "sw_version": __version__,
            **web_url_dict
        },
        "name": name,
        "state_topic": f"{topic}/{device_type}/{id}",
        "unique_id": f"{topic}{device_type}{id}",
        # "object_id": f"{topic}{device_type}{id}",
        **kwargs,
    }

def ha_virtual_energy_sensor_discovery_message(
    topic: str,
    relay_id: str,
    **kwargs
) -> dict[str, str]:
    """
    Generate MQTT autodiscovery messages for Home Assistant for virtual power and energy sensors.
    Returns two dicts:
     - sensor.<id>_power: current power in W
     - sensor.<id>_energy: total energy in Wh
    """
    # Power sensor discovery
    msg = ha_availabilty_message(
        state_topic=f"{topic}/energy/{relay_id}",
        topic=topic,
        **kwargs,
    )
    return msg


def ha_light_availabilty_message(id: str, topic: str = "boneIO", device_type: str = RELAY, **kwargs):
    """Create LIGHT availability topic for HA."""
    msg = ha_availabilty_message(device_type=device_type, topic=topic, id=id, **kwargs)
    msg["command_topic"] = f"{topic}/cmd/{device_type}/{id}/set"
    msg["payload_off"] = OFF
    msg["payload_on"] = ON
    msg["state_value_template"] = "{{ value_json.state }}"
    return msg


def ha_led_availabilty_message(id: str, topic: str = "boneIO",  **kwargs):
    """Create LED availability topic for HA."""
    msg = ha_availabilty_message(device_type=RELAY, topic=topic, id=id, **kwargs)
    msg["command_topic"] = f"{topic}/cmd/{RELAY}/{id}/set"
    msg["brightness_state_topic"] = f"{topic}/{RELAY}/{id}"
    msg["brightness_command_topic"] = f"{topic}/cmd/{RELAY}/{id}/set_brightness"
    msg["brightness_scale"] = 65535
    msg["payload_off"] = OFF
    msg["payload_on"] = ON
    msg["state_value_template"] = "{{ value_json.state }}"
    msg["brightness_value_template"] = "{{ value_json.brightness }}"
    return msg


def ha_button_availabilty_message(
    id: str, topic: str = "boneIO", payload_press: str = "reload", **kwargs
):
    """Create BUTTON availability topic for HA."""
    msg = ha_availabilty_message(device_type="button", topic=topic, id=id, **kwargs)
    msg["command_topic"] = f"{topic}/cmd/button/{id}/set"
    msg["payload_press"] = payload_press
    return msg


def ha_switch_availabilty_message(id: str, topic: str = "boneIO", device_type: str = RELAY, **kwargs):
    """Create SWITCH availability topic for HA."""
    msg = ha_availabilty_message(device_type=device_type, topic=topic, id=id, **kwargs)
    msg["command_topic"] = f"{topic}/cmd/{device_type}/{id}/set"
    msg["payload_off"] = OFF
    msg["payload_on"] = ON
    msg["value_template"] = "{{ value_json.state }}"
    return msg

def ha_valve_availabilty_message(id: str, topic: str = "boneIO", device_type: str = RELAY, **kwargs):
    """Create Valve availability topic for HA."""
    msg = ha_availabilty_message(device_type=device_type, topic=topic, id=id, **kwargs)
    msg["command_topic"] = f"{topic}/cmd/{device_type}/{id}/set"
    msg["payload_close"] = OFF
    msg["payload_open"] = ON
    msg["state_open"] = ON
    msg["state_closed"] = OFF
    msg["reports_position"] = False
    msg["value_template"] = "{{ value_json.state }}"
    return msg


def ha_event_availabilty_message(**kwargs):
    msg = ha_availabilty_message(device_type=INPUT, **kwargs)
    msg["icon"] = "mdi:gesture-double-tap"
    msg["event_types"] = [SINGLE, DOUBLE, LONG]
    return msg


def ha_adc_sensor_availabilty_message(**kwargs):
    msg = ha_availabilty_message(device_type=SENSOR, **kwargs)
    msg["unit_of_measurement"] = "V"
    msg["device_class"] = "voltage"
    msg["state_class"] = "measurement"
    return msg


def ha_sensor_availabilty_message(device_type: str = SENSOR, **kwargs):
    msg = ha_availabilty_message(device_type=device_type, **kwargs)
    return msg


def ha_binary_sensor_availabilty_message(
    id: str, name: str, topic: str = "boneIO", model: str = "boneIO Relay Board", **kwargs
):
    """Create availability topic for HA."""
    msg = ha_availabilty_message(device_type=INPUT_SENSOR, topic=topic, id=id, name=name, model=model, **kwargs)
    msg["payload_on"] = "pressed"
    msg["payload_off"] = "released"
    return msg


def ha_sensor_ina_availabilty_message(
    id: str, name: str, topic: str = "boneIO", model: str = "boneIO Relay Board", **kwargs
):
    """Create availability topic for HA."""
    msg = ha_availabilty_message(device_type=SENSOR, topic=topic, id=id, name=name, model=model, **kwargs)
    msg["state_class"] = "measurement"
    msg["value_template"] = "{{ value_json.state }}"
    return msg


def ha_sensor_temp_availabilty_message(
    id: str, name: str, topic: str = "boneIO", model: str = "boneIO Relay Board", **kwargs
):
    """Create availability topic for HA."""
    msg = ha_availabilty_message(device_type=SENSOR, topic=topic, id=id, name=name, model=model, **kwargs)
    msg["device_class"] = "temperature"
    msg["state_class"] = "measurement"
    msg["value_template"] = "{{ value_json.state }}"
    return msg

def modbus_availabilty_message(
    id: str,
    entity_id: str,
    name: str,
    state_topic_base: str,
    topic: str,
    model: str,
    device_type: str = SENSOR,
    **kwargs,
):
    """Create Modbus availability topic for HA."""
    return {
        "availability": [{"topic": f"{topic}/{id}/{STATE}"}],
        "device": {
            "identifiers": [id],
            "manufacturer": "boneIO",
            "model": model,
            "name": name,
            "sw_version": __version__,
        },
        "name": entity_id,
        "state_topic": f"{topic}/{device_type}/{id}/{state_topic_base}",
        "unique_id": f"{topic}{entity_id.replace('_', '').lower()}{name.lower()}",
        **kwargs,
    }

def modbus_sensor_availabilty_message(
    id: str,
    sensor_id: str,
    name: str,
    state_topic_base: str,
    topic: str,
    model: str,
    device_type: str = SENSOR,
    **kwargs,
):
    """Create Modbus Sensor availability topic for HA."""
    return {
        "availability": [{"topic": f"{topic}/{id}/{STATE}"}],
        "device": {
            "identifiers": [id],
            "manufacturer": "boneIO",
            "model": model,
            "name": name,
            "sw_version": __version__,
        },
        "name": sensor_id,
        "state_topic": f"{topic}/{device_type}/{id}/{state_topic_base}",
        "unique_id": f"{topic}{sensor_id.replace('_', '').lower()}{name.lower()}",
        **kwargs,
    }

def modbus_select_availabilty_message(
    id: str,
    entity_id: str,
    name: str,
    state_topic_base: str,
    topic: str,
    model: str,
    device_type: str = SELECT,
    **kwargs,
):
    """Create Modbus Select availability topic for HA."""
    return {
        "availability": [{"topic": f"{topic}/{id}/{STATE}"}],
        "device": {
            "identifiers": [id],
            "manufacturer": "boneIO",
            "model": model,
            "name": name,
            "sw_version": __version__,
        },
        "name": entity_id,
        "state_topic": f"{topic}/{device_type}/{id}/{state_topic_base}",
        "unique_id": f"{topic}{entity_id.replace('_', '').lower()}{name.lower()}",
        **kwargs,
    }


def modbus_numeric_availabilty_message(
    id: str,
    entity_id: str,
    name: str,
    state_topic_base: str,
    topic: str,
    model: str,
    device_type: str = NUMERIC,
    **kwargs,
):
    """Create Modbus Numeric availability topic for HA."""
    return {
        "availability": [{"topic": f"{topic}/{id}/{STATE}"}],
        "device": {
            "identifiers": [id],
            "manufacturer": "boneIO",
            "model": model,
            "name": name,
            "sw_version": __version__,
        },
        "name": entity_id,
        "state_topic": f"{topic}/{device_type}/{id}/{state_topic_base}",
        "unique_id": f"{topic}{entity_id.replace('_', '').lower()}{name.lower()}",
        **kwargs,
    }


def ha_cover_availabilty_message(
    id: str, name: str, device_class: str, topic: str = "boneIO", model: str = "boneIO Relay Board", **kwargs
):
    """Create Cover availability topic for HA."""
    kwargs = {"device_class": device_class, **kwargs} if device_class else { **kwargs }
    msg = ha_availabilty_message(
        device_type=COVER, topic=topic, id=id, name=name, model=model, **kwargs
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
    id: str, name: str, device_class: str, topic: str = "boneIO", model: str = "boneIO Relay Board", **kwargs
):
    """Create Cover with tilt availability topic for HA."""
    kwargs = {"device_class": device_class, **kwargs} if device_class else { **kwargs }
    msg = ha_availabilty_message(
        device_type=COVER, topic=topic, id=id, name=name, model=model, **kwargs
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
