"""Public API for the remote_mqtt module.

Provides scanning + Jinja2-based value extraction for arbitrary MQTT
devices that don't follow boneIO's topic convention (e.g. ROPAM alarm
panels publishing ``n64/88/temp1 = {"val": 6.5, ...}``).

Core boneIO files MUST import only from this module's public API.
Internal restructuring of the module never breaks consumers.

Note on lazy loading: ``register_routes`` (and any FastAPI / jinja2
dependants) are imported lazily via ``__getattr__`` so pure helpers
load without pulling FastAPI.
"""

from __future__ import annotations

from typing import Any

from boneio.modules.remote_mqtt.scanner import (
    PayloadType,
    ScanResult,
    infer_payload_type,
    scan_topics,
)
from boneio.modules.remote_mqtt.template import (
    coerce_bool,
    evaluate,
    try_parse_json,
)

__all__ = [
    "PayloadType",
    "ScanResult",
    "infer_payload_type",
    "scan_topics",
    "coerce_bool",
    "evaluate",
    "try_parse_json",
    # Lazy-loaded:
    "register_routes",
    "MQTTGenericInput",
    "MQTTGenericOutput",
]


def __getattr__(name: str) -> Any:
    """Lazy load FastAPI-dependent routes and runtime classes."""
    if name == "register_routes":
        from boneio.modules.remote_mqtt.routes import register_routes
        return register_routes
    if name == "MQTTGenericInput":
        from boneio.modules.remote_mqtt.input import MQTTGenericInput
        return MQTTGenericInput
    if name == "MQTTGenericOutput":
        from boneio.modules.remote_mqtt.output import MQTTGenericOutput
        return MQTTGenericOutput
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
