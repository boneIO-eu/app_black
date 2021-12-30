from boneio.version import __version__


from boneio.const import INPUT, OFF, ON, RELAY, STATE, SENSOR, INPUT_SENSOR


def ha_relay_availibilty_message(id: str, name: str, topic: str = "boneio"):
    """Create availability topic for HA."""
    return {
        "availability": [{"topic": f"{topic}/{STATE}"}],
        "command_topic": f"{topic}/relay/{id}/set",
        "device": {
            "identifiers": [topic],
            "manufacturer": "BoneIO",
            "model": "BoneIO Relay Board",
            "name": f"BoneIO {topic}",
            "sw_version": __version__,
        },
        "name": name,
        "payload_off": OFF,
        "payload_on": ON,
        "state_topic": f"{topic}/{RELAY}/{id}",
        "unique_id": f"{topic}{RELAY}{id}",
        "value_template": "{{ value_json.state }}",
    }


def ha_availibilty_message(
    id: str, name: str, topic: str = "boneio", sensor_type: str = INPUT
):
    """Create availability topic for HA."""
    return {
        "availability": [{"topic": f"{topic}/{STATE}"}],
        "device": {
            "identifiers": [topic],
            "manufacturer": "BoneIO",
            "model": "BoneIO Relay Board",
            "name": f"BoneIO {topic}",
            "sw_version": __version__,
        },
        "icon": "mdi:gesture-double-tap",
        "name": name,
        "state_topic": f"{topic}/{sensor_type}/{id}",
        "unique_id": f"{topic}{sensor_type}{id}",
    }


def ha_input_availibilty_message(**kwargs):
    return ha_availibilty_message(sensor_type=INPUT, **kwargs)


def ha_adc_sensor_availibilty_message(**kwargs):
    msg = ha_availibilty_message(sensor_type=SENSOR, **kwargs)
    msg["unit_of_measurement"] = "V"
    msg["device_class"] = "voltage"
    msg["state_class"] = "measurement"
    return msg


def ha_sensor_availibilty_message(unit_of_measurement: str = None, **kwargs):
    msg = ha_availibilty_message(sensor_type=SENSOR, **kwargs)
    if not unit_of_measurement:
        return msg


def ha_binary_sensor_availibilty_message(id: str, name: str, topic: str = "boneio"):
    """Create availability topic for HA."""
    return {
        "availability": [{"topic": f"{topic}/{STATE}"}],
        "device": {
            "identifiers": [topic],
            "manufacturer": "BoneIO",
            "model": "BoneIO Relay Board",
            "name": f"BoneIO {topic}",
            "sw_version": __version__,
        },
        "payload_on": "pressed",
        "payload_off": "released",
        "name": name,
        "state_topic": f"{topic}/{INPUT_SENSOR}/{id}",
        "unique_id": f"{topic}{INPUT_SENSOR}{id}",
    }


def ha_sensor_temp_availibilty_message(id: str, name: str, topic: str = "boneio"):
    """Create availability topic for HA."""
    return {
        "availability": [{"topic": f"{topic}/{STATE}"}],
        "device": {
            "identifiers": [topic],
            "manufacturer": "BoneIO",
            "model": "BoneIO Relay Board",
            "name": f"BoneIO {topic}",
            "sw_version": __version__,
        },
        "name": name,
        "state_topic": f"{topic}/{SENSOR}/{id}",
        "unique_id": f"{topic}{SENSOR}{id}",
        "device_class": "temperature",
        "state_class": "measurement",
        "unit_of_measurement": "°C",
        "value_template": "{{ value_json.state }}",
    }
