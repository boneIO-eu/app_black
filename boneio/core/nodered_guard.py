"""Make sure the running Node-RED asks for a password.

Node-RED reads ``settings.js`` once, when its container starts. The file can
say ``adminAuth`` while the editor still answers anyone: a migration installs
the file during an update, and an update restarts boneIO, not the controller,
so the container goes on with the settings it started with — an open editor,
and deploying a flow with an ``exec`` node is code execution in it.

So after boneIO starts it asks Node-RED, through the local proxy the way a
browser would, what its login looks like. An editor that wants no login while
the file on disk asks for one is restarted, once. Anything else is left alone:
Node-RED switched off, still starting, or behind a proxy that is being
recreated all look like "no answer", which is not a reason to restart.
"""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from boneio.core import containers

_LOGGER = logging.getLogger(__name__)

SETTINGS_FILE = containers.PROJECT_DIR / "node-red" / "settings.js"

#: Node-RED needs a while after a boot; so does the first start of Caddy.
FIRST_CHECK_AFTER = 60.0
RETRY_EVERY = 60.0
ATTEMPTS = 10

OPEN = "open"
PROTECTED = "protected"
UNKNOWN = "unknown"


def probe(port: int, timeout: float = 5.0) -> str:
    """Ask the editor how it signs people in.

    ``GET /nodered/auth/login`` answers ``{}`` when ``adminAuth`` is off and
    names the login type when it is on. The proxy's certificate is the
    device's own, unverifiable from here, and this request never leaves the
    machine, so it is not checked.

    Args:
        port: The HTTPS port Caddy publishes.
        timeout: Seconds to wait.

    Returns:
        OPEN, PROTECTED, or UNKNOWN when there was no usable answer.
    """
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    url = f"https://127.0.0.1:{port}/nodered/auth/login"
    try:
        with urllib.request.urlopen(url, timeout=timeout, context=context) as response:  # noqa: S310
            body = json.loads(response.read(4096) or b"null")
    except (OSError, ValueError, urllib.error.URLError):
        return UNKNOWN
    if not isinstance(body, dict):
        return UNKNOWN
    return PROTECTED if body.get("type") else OPEN


def settings_require_login(path: Path = SETTINGS_FILE) -> bool:
    """Whether the settings on disk turn ``adminAuth`` on.

    Args:
        path: Node-RED's settings.js.

    Returns:
        True when the file configures it.
    """
    try:
        return "adminAuth" in path.read_text()
    except OSError:
        return False


async def ensure_admin_auth(
    port: int,
    *,
    first_check_after: float = FIRST_CHECK_AFTER,
    retry_every: float = RETRY_EVERY,
    attempts: int = ATTEMPTS,
    probe_fn: Callable[[int], str] = probe,
    settings_path: Path = SETTINGS_FILE,
    restart: Callable[[], containers.Result] = containers.restart_nodered,
) -> str:
    """Restart Node-RED once if it runs open while its settings say otherwise.

    Args:
        port: The HTTPS port Caddy publishes.
        first_check_after: Seconds before the first look.
        retry_every: Seconds between looks while there is no answer.
        attempts: Looks before giving up on an editor that never answers.
        probe_fn: The probe. A parameter for the tests.
        settings_path: Node-RED's settings.js.
        restart: Restarts the container. A parameter for the tests.

    Returns:
        What it found or did: ``protected``, ``restarted``, ``open`` (the file
        itself asks for no login), ``restart_failed`` or ``unknown``.
    """
    loop = asyncio.get_running_loop()
    await asyncio.sleep(first_check_after)
    for attempt in range(attempts):
        if attempt:
            await asyncio.sleep(retry_every)
        state = await loop.run_in_executor(None, probe_fn, port)
        if state == UNKNOWN:
            continue
        if state == PROTECTED:
            return PROTECTED
        if not settings_require_login(settings_path):
            _LOGGER.error(
                "Node-RED's editor accepts anyone, and %s does not configure "
                "adminAuth either. Apply the pending system migrations.",
                settings_path,
            )
            return OPEN
        _LOGGER.warning(
            "Node-RED is running without the login its settings ask for; "
            "restarting it so it reads them."
        )
        result = await loop.run_in_executor(None, restart)
        if not result.ok:
            _LOGGER.error(
                "Could not restart Node-RED: %s",
                (result.stderr or result.stdout).strip() or "unknown error",
            )
            return "restart_failed"
        return "restarted"
    return UNKNOWN
