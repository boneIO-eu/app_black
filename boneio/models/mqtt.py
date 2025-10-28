"""MQTT message data models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MQTTMessage:
    """Base MQTT message."""

    topic: str
    payload: str | int | dict | None = None


@dataclass
class MQTTMessageSend(MQTTMessage):
    """MQTT message being sent with QoS and retain settings."""

    qos: int = 0
    retain: bool = False

    def to_tuple(self) -> tuple[str, str | int | dict | None, bool]:
        """Convert to tuple for backward compatibility.
        
        Returns:
            Tuple of (topic, payload, retain)
        """
        return (self.topic, self.payload, self.retain)

