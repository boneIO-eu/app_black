"""Jinja2 value_template engine for MQTT payload extraction.

Mirrors the convention used by Home Assistant (and already emitted in
``boneio.integration.homeassistant``) so users familiar with HA templates
can transfer their knowledge directly.

Evaluation context:

* ``value`` — raw payload string as received
* ``value_json`` — parsed JSON (dict / list / scalar) if payload is JSON,
  otherwise ``None``

Sandboxed via ``jinja2.sandbox.SandboxedEnvironment`` — user-supplied
templates can't reach Python builtins, file IO, or arbitrary attribute
access on internal objects.
"""

from __future__ import annotations

import json
from typing import Any

# Lazy: jinja2 is imported on first evaluate() call so the rest of the module
# (scanner, try_parse_json, coerce_bool) can be imported even on environments
# where jinja2 isn't installed. The remote_mqtt module's package __init__
# eagerly imports symbols from this file, so a top-level jinja2 import would
# crash the whole webui at startup.
_ENV = None


def _get_env():
    """Lazily build (and cache) the sandboxed Jinja2 environment."""
    global _ENV
    if _ENV is None:
        from jinja2 import StrictUndefined
        from jinja2.sandbox import SandboxedEnvironment

        _ENV = SandboxedEnvironment(
            autoescape=False,
            # StrictUndefined surfaces typos in dotted paths
            # (`value_json.vall`) as a clear error instead of silently
            # rendering empty string.
            undefined=StrictUndefined,
        )
    return _ENV


def try_parse_json(payload: str) -> Any:
    """Best-effort JSON parse — returns ``None`` if payload isn't JSON.

    Used by both the template evaluator (to populate ``value_json``)
    and the scanner (to inform the payload-type classifier).
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


def evaluate(template_str: str, payload: str) -> str:
    """Render ``template_str`` against ``payload`` and return the result as string.

    Always returns a string — Jinja2 render produces strings; callers needing
    typed coercion (bool, float) should apply it on top of the rendered value.

    Raises ``ValueError`` with a friendly message on template errors so the
    caller (typically a route) can surface a clean HTTP 400.
    """
    parsed = try_parse_json(payload)
    try:
        from jinja2.exceptions import TemplateError
    except ImportError as exc:  # pragma: no cover — install jinja2 in venv
        raise ValueError(
            "Jinja2 not installed in this environment — "
            "install it with `pip install Jinja2>=3.1.0`"
        ) from exc
    try:
        template = _get_env().from_string(template_str)
        return template.render(value=payload, value_json=parsed)
    except TemplateError as exc:
        raise ValueError(f"Template error: {exc}") from exc


def coerce_bool(
    rendered: str,
    payload_on: str | None = None,
    payload_off: str | None = None,
) -> bool | None:
    """Coerce a rendered template result into a boolean for binary inputs.

    Matching order:
    1. If ``payload_on`` matches exactly → ``True``
    2. If ``payload_off`` matches exactly → ``False``
    3. Common truthy/falsy fallback (case-insensitive):
       - True: ``"1"``, ``"on"``, ``"true"``, ``"open"``
       - False: ``"0"``, ``"off"``, ``"false"``, ``"closed"``
    4. Otherwise ``None`` (ambiguous — caller decides to drop or warn).
    """
    if payload_on is not None and rendered == payload_on:
        return True
    if payload_off is not None and rendered == payload_off:
        return False
    lowered = rendered.strip().lower()
    if lowered in {"1", "on", "true", "open"}:
        return True
    if lowered in {"0", "off", "false", "closed"}:
        return False
    return None
