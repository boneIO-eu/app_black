from boneio.const import (
    CLOSE,
    CLOSED,
    CLOSING,
    COVER,
    INPUT,
    INPUT_SENSOR,
    OFF,
    ON,
    OPEN,
    OPENING,
    RELAY,
    SENSOR,
    STATE,
    STOP,
)
from boneio.version import __version__


def ha_availabilty_message(
    id: str,
    name: str,
    topic: str = "boneIO",
    device_type: str = INPUT,
    model: str = "boneIO Relay Board",
    **kwargs,
):
    """Create availability topic for HA."""
    return {
        "availability": [{"topic": f"{topic}/{STATE}"}],
        "device": {
            "identifiers": [topic],
            "manufacturer": "boneIO",
            "model": model,
            "name": f"boneIO {topic}",
            "sw_version": __version__,
        },
        "name": name,
        "state_topic": f"{topic}/{device_type}/{id}",
        "unique_id": f"{topic}{device_type}{id}",
        **kwargs,
    }


def ha_light_availabilty_message(id: str, topic: str = "boneIO", **kwargs):
    """Create LIGHT availability topic for HA."""
    msg = ha_availabilty_message(device_type=RELAY, topic=topic, id=id, **kwargs)
    msg["command_topic"] = f"{topic}/cmd/relay/{id}/set"
    msg["payload_off"] = OFF
    msg["payload_on"] = ON
    msg["state_value_template"] = "{{ value_json.state }}"
    return msg


def ha_button_availabilty_message(id: str, topic: str = "boneIO", **kwargs):
    """Create BUTTON availability topic for HA."""
    msg = ha_availabilty_message(device_type="button", topic=topic, id=id, **kwargs)
    msg["command_topic"] = f"{topic}/cmd/button/{id}/set"
    msg["payload_press"] = "reload"
    return msg


def ha_switch_availabilty_message(id: str, topic: str = "boneIO", **kwargs):
    """Create SWITCH availability topic for HA."""
    msg = ha_availabilty_message(device_type=RELAY, topic=topic, id=id, **kwargs)
    msg["command_topic"] = f"{topic}/cmd/relay/{id}/set"
    msg["payload_off"] = OFF
    msg["payload_on"] = ON
    msg["value_template"] = "{{ value_json.state }}"
    return msg


def ha_input_availabilty_message(**kwargs):
    msg = ha_availabilty_message(device_type=INPUT, **kwargs)
    msg["icon"] = "mdi:gesture-double-tap"
    return msg


def ha_adc_sensor_availabilty_message(**kwargs):
    msg = ha_availabilty_message(device_type=SENSOR, **kwargs)
    msg["unit_of_measurement"] = "V"
    msg["device_class"] = "voltage"
    msg["state_class"] = "measurement"
    return msg


def ha_sensor_availabilty_message(unit_of_measurement: str = None, **kwargs):
    msg = ha_availabilty_message(device_type=SENSOR, **kwargs)
    if not unit_of_measurement:
        return msg


def ha_binary_sensor_availabilty_message(id: str, name: str, topic: str = "boneIO"):
    """Create availability topic for HA."""
    return {
        "availability": [{"topic": f"{topic}/{STATE}"}],
        "device": {
            "identifiers": [topic],
            "manufacturer": "boneIO",
            "model": "boneIO Relay Board",
            "name": f"boneIO {topic}",
            "sw_version": __version__,
        },
        "payload_on": "pressed",
        "payload_off": "released",
        "name": name,
        "state_topic": f"{topic}/{INPUT_SENSOR}/{id}",
        "unique_id": f"{topic}{INPUT_SENSOR}{id}",
    }


def ha_sensor_temp_availabilty_message(
    id: str, name: str, topic: str = "boneIO", **kwargs
):
    """Create availability topic for HA."""
    return {
        "availability": [{"topic": f"{topic}/{STATE}"}],
        "device": {
            "identifiers": [topic],
            "manufacturer": "boneIO",
            "model": "boneIO Relay Board",
            "name": f"boneIO {topic}",
            "sw_version": __version__,
        },
        "name": name,
        "state_topic": f"{topic}/{SENSOR}/{id}",
        "unique_id": f"{topic}{SENSOR}{id}",
        "device_class": "temperature",
        "state_class": "measurement",
        "value_template": "{{ value_json.state }}",
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
        "availability": [{"topic": f"{topic}/{id}{STATE}"}],
        "device": {
            "identifiers": [id],
            "manufacturer": "boneIO",
            "model": model,
            "name": f"boneIO {name.upper()}",
            "sw_version": __version__,
        },
        "name": sensor_id,
        "state_topic": f"{topic}/{device_type}/{id}/{state_topic_base}",
        "unique_id": f"{topic}{sensor_id.replace('_', '').lower()}{name.lower()}",
        **kwargs,
    }


def ha_cover_availabilty_message(
    id: str, name: str, device_class: str, topic: str = "boneIO"
):
    """Create Cover availability topic for HA."""
    kwargs = {"device_class": device_class} if device_class else {}
    msg = ha_availabilty_message(
        device_type=COVER, topic=topic, id=id, name=name, **kwargs
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
        "position_topic": f"{topic}/{COVER}/{id}/pos",
    }
