"""Jinja2 value_template engine for MQTT payload extraction.

Mirrors the convention used by Home Assistant (and already emitted in
``boneio.integration.homeassistant``) so users familiar with HA templates
can transfer their knowledge directly. The eval context exposes:

* ``value`` — raw payload string as received
* ``value_json`` — parsed JSON (dict / list / scalar) if payload is JSON,
  otherwise ``None``

Implementation: stub for Phase 0 — Phase 3 wires up jinja2.
"""

from __future__ import annotations

import json
from typing import Any


def evaluate(template_str: str, payload: str) -> Any:
    """Render ``template_str`` against ``payload`` and return the result.

    NOTE: Phase 0 stub. Phase 3 imports jinja2 and implements proper
    sandboxed evaluation with `value` + `value_json` context.
    """
    raise NotImplementedError("evaluate implemented in Phase 3")


def coerce_bool(value: Any, payload_on: str | None, payload_off: str | None) -> bool | None:
    """Coerce a value (string, number, bool) into a boolean for binary inputs.

    Matching order:
    1. If ``payload_on`` matches → ``True``
    2. If ``payload_off`` matches → ``False``
    3. Truthy / falsy fallback (``"1"``, ``"on"``, ``True``, ``1`` → True;
       ``"0"``, ``"off"``, ``False``, ``0`` → False)
    4. Otherwise ``None`` (ambiguous — caller decides whether to drop).

    Implementation deferred to Phase 4 when used by ``MQTTGenericInput``.
    """
    raise NotImplementedError("coerce_bool implemented in Phase 4")


def try_parse_json(payload: str) -> Any:
    """Best-effort JSON parse — returns ``None`` if payload isn't JSON.

    Available now (no jinja2 dependency) so the scanner can use it.
    """
    if not payload:
        return None
    stripped = payload.strip()
    if not stripped or stripped[0] not in "{[":
        return None
    try:
        return json.loads(stripped)
    except (ValueError, json.JSONDecodeError):
        return None
