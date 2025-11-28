"""MQTT message data models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MQTTMessage:
    """Base MQTT message."""

    topic: str
    payload: str | int | bytes | dict | None = None


@dataclass
class MQTTMessageSend(MQTTMessage):
    """MQTT message being sent with QoS and retain settings.
    
    Note: payload should be pre-encoded (str or bytes) before creating this message.
    Use send_message() which handles encoding of dict/int/None payloads.
    """

    payload: str | bytes = ""  # Override parent type - should be pre-encoded
    qos: int = 0
    retain: bool = False

    def to_tuple(self) -> tuple[str, str | bytes, bool]:
        """Convert to tuple for backward compatibility.
        
        Returns:
            Tuple of (topic, payload, retain)
        """
        return (self.topic, self.payload, self.retain)

