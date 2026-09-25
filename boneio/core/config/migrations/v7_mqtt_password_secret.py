"""Migration v7: Keep the broker password in secrets.yaml.

Images draw the broker password per device at first boot and write it to
secrets.yaml, so the shipped mqtt.yaml says ``password: !secret mqtt_password``.
Controllers installed before that keep the password in mqtt.yaml itself, which
then travels with every config backup and every copy someone pastes into a
support thread. This moves it next to the device's other secrets.

Before (mqtt.yaml):
    host: localhost
    password: "s3cret"
After:
    host: localhost
    password: !secret mqtt_password
and secrets.yaml:
    mqtt_password: "s3cret"

A password already given as ``!secret`` is left alone. If secrets.yaml already
holds a different ``mqtt_password``, the value goes under ``mqtt_password_2``.
"""

from __future__ import annotations

import logging

from boneio.core.config.migrations import register_migration

_LOGGER = logging.getLogger(__name__)

_FIELD = ("mqtt", "password")
_SECRET_NAME = "mqtt_password"


def _persist_mqtt_password_secret(config_file: str) -> None:
    from boneio.core.config.yaml_patch import move_to_secret

    move_to_secret(config_file, _FIELD, _SECRET_NAME)


@register_migration(
    version=7,
    name="Move the MQTT password to secrets.yaml",
    migrate_file=_persist_mqtt_password_secret,
)
def migrate_v7_mqtt_password_secret(doc: dict) -> dict:
    """Nothing changes in memory: the password is the same, only where it is kept.

    Args:
        doc: Raw config dictionary.

    Returns:
        The same dictionary.
    """
    return doc
