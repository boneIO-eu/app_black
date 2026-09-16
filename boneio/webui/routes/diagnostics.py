"""Diagnostics for a support case.

Two endpoints that belong together. The bundle is the deliverable; the capture
window exists because without it the bundle's logs are usually worthless —
almost nobody runs with debug on, so the detail that would explain a fault was
never written down.

Debug is opened for a few minutes and closes itself. That matters more than it
looks: an idle controller logs around twenty MQTT publishes a second at debug
level, so a window left open fills the journal and evicts the very history
someone will want tomorrow. The existing ``/api/system/log-level`` route can
already switch the level, but only back again by hand, and by hand means never.

Admin only. The bundle carries the whole configuration and the device log.
"""

from __future__ import annotations

import asyncio
import logging
import time

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from boneio.core.config.yaml_util import load_yaml_file
from boneio.core.diagnostics.collect import build

_LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])

_app_state = None

#: How long a capture may stay open. Long enough to reproduce something by
#: hand, short enough that forgetting about it costs one journal rotation.
MAX_CAPTURE_MINUTES = 30
DEFAULT_CAPTURE_MINUTES = 10

#: Epoch seconds the window opened, the level to put back, and the task that
#: will do it. Process-global because the logging configuration is.
_capture_started: float | None = None
_capture_until: float | None = None
_previous_level: int | None = None
_revert_task: asyncio.Task | None = None


def set_app_state(app_state) -> None:
    """Attach app state so the bundle can read the live configuration.

    Args:
        app_state: The FastAPI application state.
    """
    global _app_state
    _app_state = app_state


class CaptureRequest(BaseModel):
    """How long to keep debug logging open."""

    minutes: int = Field(default=DEFAULT_CAPTURE_MINUTES, ge=1, le=MAX_CAPTURE_MINUTES)


def _capture_state() -> dict:
    """The capture window as the panel shows it.

    Returns:
        Dictionary describing whether a window is open and for how long.
    """
    if _capture_until is None or time.time() >= _capture_until:
        return {"active": False, "seconds_remaining": 0, "started": None}
    return {
        "active": True,
        "seconds_remaining": int(_capture_until - time.time()),
        "started": _capture_started,
    }


def _restore_level() -> None:
    """Put the log level back where it was.

    Never raises: this runs from a background task and from a request, and a
    failure here must not leave the device stuck at debug silently.
    """
    global _capture_started, _capture_until, _previous_level
    if _previous_level is not None:
        try:
            logging.getLogger().setLevel(_previous_level)
            _LOGGER.info(
                "Diagnostic capture closed, log level back to %s",
                logging.getLevelName(_previous_level),
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Could not restore the log level: %s", err)
    _capture_started = None
    _capture_until = None
    _previous_level = None


async def _close_after(seconds: float) -> None:
    """Close the capture window once its time is up.

    Args:
        seconds: How long to wait.
    """
    try:
        await asyncio.sleep(seconds)
    except asyncio.CancelledError:
        return
    _restore_level()


@router.get("/capture")
async def get_capture():
    """Report whether a debug capture window is open.

    Returns:
        The capture state.
    """
    return _capture_state()


@router.post("/capture")
async def start_capture(payload: CaptureRequest):
    """Open a debug capture window that closes itself.

    Args:
        payload: How many minutes to keep it open.

    Returns:
        The capture state.
    """
    global _capture_started, _capture_until, _previous_level, _revert_task

    if _revert_task is not None and not _revert_task.done():
        _revert_task.cancel()

    root = logging.getLogger()
    if _previous_level is None:
        # Only on the first open, so extending a window cannot record DEBUG as
        # the level to go back to.
        _previous_level = root.level

    root.setLevel(logging.DEBUG)
    _capture_started = time.time()
    _capture_until = _capture_started + payload.minutes * 60
    _revert_task = asyncio.create_task(_close_after(payload.minutes * 60))

    _LOGGER.info(
        "Diagnostic capture open for %d minute(s); level was %s",
        payload.minutes,
        logging.getLevelName(_previous_level),
    )
    return _capture_state()


@router.delete("/capture")
async def stop_capture():
    """Close the capture window now.

    Returns:
        The capture state.
    """
    global _revert_task
    if _revert_task is not None and not _revert_task.done():
        _revert_task.cancel()
    _revert_task = None
    _restore_level()
    return _capture_state()


def _describe_bus(bus, indent: str = "") -> list[str]:
    """One message bus, and anything it delegates to.

    The manager holds a CompositeMessageBus when more than one protocol is
    configured, and the composite has no host or port of its own — those live
    on the buses inside it. Reporting only the outer object says "connected:
    True" and nothing about which broker that refers to.

    Args:
        bus: A message bus.
        indent: Prefix for nested lines.

    Returns:
        Lines describing it.
    """
    lines = [f"{indent}{type(bus).__name__}: connected={getattr(bus, 'state', '?')}"]
    for attribute in ("host", "port", "reconnect_interval", "topic_prefix"):
        if hasattr(bus, attribute):
            lines.append(f"{indent}  {attribute}: {getattr(bus, attribute)}")
    for inner in getattr(bus, "_buses", []) or []:
        lines.extend(_describe_bus(inner, indent + "  "))
    return lines


def _mqtt_status() -> str:
    """How the running process sees its broker connection.

    Returns:
        A short report, or a note saying why there is none.
    """
    try:
        manager = getattr(_app_state, "manager", None)
        bus = getattr(manager, "_message_bus", None)
        if bus is None:
            return "[no message bus — MQTT may be disabled]"
        return "\n".join(_describe_bus(bus))
    except Exception as err:  # noqa: BLE001
        return f"[could not read MQTT state: {err}]"


@router.get("/bundle")
async def get_bundle():
    """Build and return the diagnostic bundle.

    Returns:
        The gzipped tar, as a download.

    Raises:
        HTTPException: If the configuration cannot be read.
    """
    config_file = getattr(_app_state, "yaml_config_file", None)
    if not config_file:
        raise HTTPException(status_code=503, detail="No configuration file is loaded.")

    try:
        config = load_yaml_file(str(config_file))
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Diagnostics could not parse the configuration: %s", err)
        # Still worth producing: a config that will not parse is often the
        # fault being reported, and the logs will say why.
        config = {}

    if not isinstance(config, dict):
        config = {}

    # The serial comes from the running helper rather than the file: without an
    # override it is derived from the MAC, so config.yaml does not have it.
    helper = getattr(_app_state, "config_helper", None)
    serial = getattr(helper, "serial_number", None) if helper else None
    real_serial = getattr(helper, "real_serial", None) if helper else None

    # Building shells out to journalctl, docker and systemctl, which block.
    payload, filename = await asyncio.to_thread(
        build,
        config,
        config_file,
        mqtt_status=_mqtt_status(),
        capture_started=_capture_started,
        serial=serial,
        real_serial=real_serial,
    )

    return Response(
        content=payload,
        media_type="application/gzip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
