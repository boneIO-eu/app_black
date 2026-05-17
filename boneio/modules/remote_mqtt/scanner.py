"""Generic MQTT topic scanner.

Subscribes to a wildcard topic pattern for a configurable duration, collects
the latest payload seen per topic plus per-topic update counts, then
unsubscribes. Used by the scan-and-assign workflow for arbitrary MQTT
devices (e.g. ROPAM alarm panels) that don't follow boneIO's topic
convention.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from boneio.core.messaging.basic import MessageBus

_LOGGER = logging.getLogger(__name__)


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
    # Try JSON first — covers objects and arrays
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
    bus: "MessageBus",
    pattern: str,
    duration_s: float,
) -> list[ScanResult]:
    """Subscribe to ``pattern`` for ``duration_s`` seconds and return discovered topics.

    Uses :class:`MqttTopicDispatcher` so the scan never displaces production
    subscriptions on overlapping topics — concurrent inputs and the scanner
    both receive matching messages for the duration of the window.

    Returns a list of ``ScanResult`` sorted by topic, one entry per
    distinct topic observed during the window.
    """
    # Local import: avoids forcing dispatcher (and aiomqtt Topic) to load
    # for callers using only the pure ``infer_payload_type`` helper.
    from boneio.modules.remote_mqtt.dispatcher import get_dispatcher

    collected: dict[str, dict] = {}
    subscriber_id = f"scan:{id(collected):x}"

    async def collector(topic_str: str, payload_str: str) -> None:
        existing = collected.get(topic_str)
        if existing is None:
            collected[topic_str] = {"last_payload": payload_str, "update_count": 1}
        else:
            existing["update_count"] += 1
            existing["last_payload"] = payload_str

    dispatcher = get_dispatcher(bus)
    _LOGGER.info("MQTT scan starting: pattern=%s duration=%.1fs", pattern, duration_s)
    await dispatcher.subscribe(pattern, collector, subscriber_id)
    try:
        await asyncio.sleep(duration_s)
    finally:
        try:
            await dispatcher.unsubscribe(pattern, subscriber_id)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning("MQTT scan unsubscribe failed for %s: %s", pattern, exc)

    results: list[ScanResult] = []
    for topic, info in collected.items():
        payload_type, parsed = infer_payload_type(info["last_payload"])
        results.append(
            ScanResult(
                topic=topic,
                last_payload=info["last_payload"],
                payload_type=payload_type,
                update_count=info["update_count"],
                parsed_json=parsed,
            )
        )
    results.sort(key=lambda r: r.topic)
    _LOGGER.info("MQTT scan complete: %d topics discovered", len(results))
    return results
