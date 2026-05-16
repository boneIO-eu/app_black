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

    NOTE on limitations (Phase 1 MVP):
    1. boneIO's MQTT layer maps one callback per topic key. If ``pattern``
       overlaps with an existing subscription, this scan WILL OVERWRITE that
       subscription's callback for the duration of the scan, then restore
       the broker subscription on unsubscribe — but the original callback
       reference is lost. Restart boneIO if you scanned over a
       production-critical subscription. To avoid: scan with a pattern
       that doesn't overlap (e.g. a device-specific prefix like ``n64/#``).
    2. ``handle_messages`` breaks on first-matching listener, so messages
       arriving during the scan may be diverted from a more-specific
       existing subscription to ours if iteration order favours us.

    Returns a list of ``ScanResult`` sorted by topic, one entry per
    distinct topic observed during the window.
    """
    collected: dict[str, dict] = {}

    async def collector(topic_str: str, payload_str: str) -> None:
        existing = collected.get(topic_str)
        if existing is None:
            collected[topic_str] = {"last_payload": payload_str, "update_count": 1}
        else:
            existing["update_count"] += 1
            existing["last_payload"] = payload_str

    _LOGGER.info("MQTT scan starting: pattern=%s duration=%.1fs", pattern, duration_s)
    await bus.subscribe_and_listen(pattern, collector)
    try:
        await asyncio.sleep(duration_s)
    finally:
        try:
            await bus.unsubscribe_and_stop_listen(pattern)
        except Exception as exc:
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
