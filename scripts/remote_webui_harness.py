"""Isolated web UI harness for on-device testing of the auth/onboarding surface.

Runs the *real* onboarding router, auth router, AuthMiddleware and UserStore, so
the security-relevant code path is exercised exactly as it ships — the only
stubbed part is the cosmetic half of ``/api/init`` (device name, cloud status),
which needs a live Manager and has nothing to do with authentication. The
provisioning and auth fields it returns come from the real ``is_auth_required``
and ``UserStore``.

It is deliberately standalone: it never imports ``boneio.webui.app`` (which
needs hardware and a Manager), never touches the production ``config.yaml`` or
the running service, and keeps its ``users.json`` in a throwaway directory. That
makes it safe to run alongside the live service on a real controller — nothing
here drives GPIO or opens the I2C bus.

Point it at a scratch directory and a port::

    WEBUI_HARNESS_DIR=/tmp/boneio_harness \
    WEBUI_HARNESS_PORT=8099 \
        /home/boneio/venv/bin/python -m hypercorn \
        --bind 127.0.0.1:8099 scripts.remote_webui_harness:app

Run it from the repo root so ``scripts`` is importable, or pass the module path
that matches your working directory.
"""

from __future__ import annotations

import os
import pathlib

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from boneio.core.auth.store import UserStore
from boneio.version import __version__
from boneio.webui.middleware.auth import (
    AuthMiddleware,
    get_user_store,
    is_auth_required,
    set_auth_config,
    set_jwt_secret,
    set_user_store,
)
from boneio.webui.routes import onboarding as onboarding_module
from boneio.webui.routes.accounts import router as accounts_router
from boneio.webui.routes.auth import router as auth_router
from boneio.webui.routes.onboarding import router as onboarding_router

_HARNESS_DIR = pathlib.Path(
    os.environ.get("WEBUI_HARNESS_DIR", "/tmp/boneio_webui_harness")
)
_HARNESS_DIR.mkdir(parents=True, exist_ok=True)

# A config.yaml has to exist for UserStore.for_config_file to anchor users.json
# next to it, but the harness never reads its contents.
(_HARNESS_DIR / "config.yaml").write_text("web:\n  port: 8090\n", encoding="utf-8")

_store = UserStore.for_config_file(_HARNESS_DIR / "config.yaml")
_store.load()

set_jwt_secret(os.environ.get("WEBUI_HARNESS_JWT_SECRET", "harness-jwt-secret"))
set_auth_config({})
set_user_store(_store)
onboarding_module.set_user_store(_store)
onboarding_module.set_legacy_migration(None)

app = FastAPI(title="boneIO web UI harness")
app.include_router(onboarding_router)
app.include_router(auth_router)
app.include_router(accounts_router)


@app.get("/api/init")
async def init() -> dict:
    """Minimal init payload.

    The provisioning and auth fields are real (straight from the shipping auth
    code); the rest is stubbed because it would otherwise need a live Manager.
    """
    store = get_user_store()
    provisioned = bool(store and store.is_provisioned())
    return {
        "version": __version__,
        "name": "boneIO harness",
        "serial_no": "blk_harness",
        "serial_override": None,
        "auth_required": is_auth_required(),
        "needs_onboarding": not provisioned,
        "legacy_migration": None,
        "pwa_name": "bIO",
        "pwa_default": "bIO",
        "pwa_max_length": 12,
        "cloud": {"enabled": False},
        "has_boneio": True,
        "board_version": None,
        "has_irrigation": False,
    }


@app.post("/api/outputs/{output_id}/toggle")
async def toggle_output(output_id: str) -> dict:
    """Stand-in for an operating route, to prove a viewer may use one.

    Deliberately does not touch GPIO: the harness runs alongside the live
    service, which owns the hardware.
    """
    return {"toggled": output_id}


@app.post("/api/restart")
async def restart() -> dict:
    """Stand-in for an administrative route, to prove a viewer may not."""
    return {"restarting": True}


@app.get("/api/harness/protected")
async def protected(_: None = Depends(lambda: None)) -> dict:
    """A stand-in protected route, so tests can prove the middleware gates.

    Raises:
        HTTPException: never directly; the middleware answers 401 before this
            runs when the device is provisioned and no valid token is sent.
    """
    return {"ok": True}


# Installed unconditionally, exactly as init_app does it, so the harness gates
# requests through the same code the device runs.
app.add_middleware(AuthMiddleware)

_DIST = pathlib.Path(__file__).resolve().parent.parent / "boneio" / "webui" / "frontend-dist"
if (_DIST / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def spa(full_path: str) -> FileResponse:
        """Serve the built SPA so the wizard can be eyeballed if wanted."""
        candidate = _DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_DIST / "index.html")
