"""Generic MQTT topic scanner.

Subscribes to a wildcard topic pattern for a configurable duration, collects
the latest payload seen per topic plus per-topic update counts, then
unsubscribes. Used by the scan-and-assign workflow for arbitrary MQTT
devices (e.g. ROPAM alarm panels) that don't follow boneIO's topic
convention.

Implementation: stub for Phase 0 — wired up in Phase 1.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from boneio.core.messaging.mqtt import MQTTClient


PayloadType = Literal["json", "string", "numeric", "binary", "empty"]


@dataclass
class ScanResult:
    """One discovered MQTT topic with its observed metadata."""

    topic: str
    last_payload: str
    payload_type: PayloadType
    update_count: int = 0
    parsed_json: dict | list | None = None


def infer_payload_type(payload: str) -> tuple[PayloadType, dict | list | None]:
    """Classify a raw MQTT payload to help the UI render a sensible default value_template.

    Returns ``(type, parsed_json_or_none)``. The parsed JSON is included so the
    caller can render a tree view without re-parsing.
    """
    if not payload:
        return "empty", None
    stripped = payload.strip()
    # Try JSON first — covers objects, arrays, numbers, booleans, null, strings
    if stripped and stripped[0] in "{[":
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, (dict, list)):
                return "json", parsed
        except (ValueError, json.JSONDecodeError):
            pass
    # Bool-ish: common on/off variants
    lowered = stripped.lower()
    if lowered in {"0", "1", "on", "off", "true", "false"}:
        return "binary", None
    # Numeric
    try:
        float(stripped)
        return "numeric", None
    except ValueError:
        pass
    return "string", None


async def scan_topics(
    bus: "MQTTClient",
    pattern: str,
    duration_s: float,
) -> list[ScanResult]:
    """Subscribe to ``pattern`` for ``duration_s`` seconds and return discovered topics.

    NOTE: Phase 0 stub. Phase 1 implements the actual subscribe/collect/
    unsubscribe loop on top of ``bus.subscribe_and_listen``. Returning an
    empty list keeps importers happy and lets the routes layer exist.
    """
    raise NotImplementedError("scan_topics implemented in Phase 1")
