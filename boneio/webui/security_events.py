"""Security events the web UI tells Home Assistant about.

The security entity says how the device is configured; this is about what
happens to it. A password being guessed, or a session signed out for guessing,
is worth a push notification — and nobody reads the controller's log to find
out. Home Assistant gets them on an MQTT event entity, where an automation can
listen for them like for a button press.

The web UI does not own MQTT, so init_app hands in a publisher. Emitting never
raises: a device without MQTT, or with the broker down, still signs people in.
"""

from __future__ import annotations

import ipaddress
import logging
import unicodedata
from collections.abc import Callable

_LOGGER = logging.getLogger(__name__)

#: What the entity declares to Home Assistant. An event of any other type is
#: refused there with an error in HA's log, so emit() only sends these.
EVENT_TYPES = ("password_guessing", "session_signed_out")

# The username in a guessing event is whatever was typed at the login form,
# and it ends up in somebody's notification. Kept short and printable.
_MAX_USERNAME = 64

_MESSAGES = {
    "password_guessing": "Too many wrong passwords for '{username}' ({where}).",
    "session_signed_out": "A session of '{username}' was signed out after too many wrong passwords.",
}

_publisher: Callable[[dict], None] | None = None


def set_publisher(publisher: Callable[[dict], None] | None) -> None:
    """Attach what sends events on, or detach it with None.

    Args:
        publisher: Called with the event payload.
    """
    global _publisher
    _publisher = publisher


def emit(event_type: str, *, username: str, client: str | None = None, where: str) -> None:
    """Tell Home Assistant about a security event.

    Args:
        event_type: One of EVENT_TYPES.
        username: The account concerned — for a guessed login, what was typed.
        client: The caller's address. Left out when it is the controller's own
            loopback, which says nothing about who it was.
        where: Which form the passwords were typed into: ``login``,
            ``confirm``, ``password_change`` or ``ssh_password``.
    """
    if event_type not in EVENT_TYPES:
        _LOGGER.error("Not an event the security entity declares: %s", event_type)
        return

    name = clean_username(username)
    payload: dict = {
        "event_type": event_type,
        "username": name,
        "where": where,
        "message": _MESSAGES[event_type].format(username=name, where=where),
    }
    if client and not _is_loopback(client):
        payload["client"] = client

    _LOGGER.warning("Security event %s: %s", event_type, payload["message"])
    publisher = _publisher
    if publisher is None:
        return
    try:
        publisher(payload)
    except Exception as err:  # noqa: BLE001 - never let a notification break a login
        _LOGGER.warning("Could not publish the security event: %s", err)


def clean_username(username: str) -> str:
    """Make a typed username safe to put in a notification.

    Args:
        username: As typed.

    Returns:
        Printable characters only, at most _MAX_USERNAME of them.
    """
    printable = "".join(
        ch for ch in str(username) if unicodedata.category(ch)[0] != "C"
    ).strip()
    if len(printable) > _MAX_USERNAME:
        printable = printable[: _MAX_USERNAME - 1] + "…"
    return printable


def _is_loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return True
