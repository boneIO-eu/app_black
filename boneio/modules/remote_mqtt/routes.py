"""HTTP endpoints for the remote_mqtt module.

Endpoints:
    POST /api/mqtt/scan          — scan broker for topics matching pattern

Register via ``register_routes(app)`` from ``boneio/webui/app.py``.
"""

from __future__ import annotations

import logging
from dataclasses import asdict

from fastapi import APIRouter, Body, FastAPI, HTTPException

from boneio.modules.remote_mqtt.scanner import scan_topics
from boneio.modules.remote_mqtt.template import evaluate, try_parse_json

_LOGGER = logging.getLogger(__name__)

# Hard caps to prevent a misconfigured client from holding the broker hostage.
MIN_DURATION_S = 1.0
MAX_DURATION_S = 60.0
DEFAULT_DURATION_S = 10.0

router = APIRouter(prefix="/api/mqtt", tags=["remote_mqtt"])


def _get_message_bus():
    """Lazy resolve the MQTT bus from app state.

    Reuses the same app-state singleton as other config endpoints — keeps
    invalidation and lifecycle consistent across the webui.
    """
    from boneio.webui.routes.config import _get_app_state as _impl
    app_state = _impl()
    if app_state.manager is None:
        raise HTTPException(status_code=503, detail="Manager not initialized")
    bus = app_state.manager.message_bus
    if not bus or not bus.state:
        raise HTTPException(status_code=503, detail="MQTT bus not connected")
    return bus


@router.post("/scan")
async def scan(request: dict = Body(...)) -> dict:
    """Scan the MQTT broker for topics matching ``pattern``.

    Request body:
        pattern (str, required): MQTT subscription pattern (supports
            ``+`` and ``#`` wildcards). Example: ``n64/88/#``.
        duration_s (float, optional, default 10): how long to listen, capped
            to [1, 60] seconds.

    Response:
        {pattern, duration_s, topics: [{topic, last_payload, payload_type,
        update_count, parsed_json}]}
    """
    pattern = request.get("pattern")
    if not pattern or not isinstance(pattern, str):
        raise HTTPException(status_code=400, detail="`pattern` is required (non-empty string)")

    duration_s = request.get("duration_s", DEFAULT_DURATION_S)
    try:
        duration_s = float(duration_s)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="`duration_s` must be a number") from exc
    if duration_s < MIN_DURATION_S or duration_s > MAX_DURATION_S:
        raise HTTPException(
            status_code=400,
            detail=f"`duration_s` must be between {MIN_DURATION_S} and {MAX_DURATION_S}",
        )

    bus = _get_message_bus()
    results = await scan_topics(bus, pattern, duration_s)

    return {
        "pattern": pattern,
        "duration_s": duration_s,
        "topics": [asdict(r) for r in results],
    }


@router.post("/test-template")
async def test_template(request: dict = Body(...)) -> dict:
    """Evaluate a Jinja2 ``value_template`` against a sample payload.

    Used by the UI for live preview while the user is composing extraction
    rules. Pure function — no MQTT activity, no broker required.

    Request body:
        template (str, required): Jinja2 template string, e.g.
            ``"{{ value_json.val }}"``.
        payload (str, required): Sample payload to evaluate against;
            typically the ``last_payload`` from a scan result.

    Response:
        {result, value_json?, error?}
    """
    template_str = request.get("template")
    payload = request.get("payload", "")
    if template_str is None or not isinstance(template_str, str):
        raise HTTPException(status_code=400, detail="`template` is required (string)")
    if not isinstance(payload, str):
        raise HTTPException(status_code=400, detail="`payload` must be a string")

    parsed_json = try_parse_json(payload)
    try:
        result = evaluate(template_str, payload)
    except ValueError as exc:
        # Template error — return 200 with error field so the UI can show it
        # inline without treating it as a hard failure.
        return {
            "result": None,
            "value_json": parsed_json,
            "error": str(exc),
        }
    return {
        "result": result,
        "value_json": parsed_json,
        "error": None,
    }


def register_routes(app: FastAPI) -> None:
    """Register remote_mqtt routes on the given FastAPI app.

    Call from ``boneio/webui/app.py`` after all upstream routers are included.
    """
    app.include_router(router)
