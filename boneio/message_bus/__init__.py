"""Message bus module.

DEPRECATED: This module provides backward compatibility.
New code should import from boneio.core.messaging instead.
"""

# Re-export from new location for backward compatibility
from boneio.core.messaging import LocalMessageBus, MessageBus, MQTTClient

__all__ = ["LocalMessageBus", "MQTTClient", "MessageBus"]
