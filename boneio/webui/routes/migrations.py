"""Migration API routes for BoneIO WebUI.

Provides endpoints for:
- Querying migration status
- Bootstrapping the boneio-migrate helper (one-time sudo password)
- Triggering migration apply
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field, SecretStr

if TYPE_CHECKING:
    from boneio.core.manager import Manager

_LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/migrations", tags=["migrations"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class BootstrapRequest(BaseModel):
    """Bootstrap request body carrying the sudo password."""

    password: SecretStr = Field(
        ...,
        description="System sudo password for the boneio user (sent once, not stored)",
    )


class MigrationStatusResponse(BaseModel):
    """Response model for migration status endpoint."""

    status: str
    bootstrap_required: bool
    helper_installed: bool
    pending_count: int
    pending: list[dict]
    applied: list[str]
    last_error: str | None


# ---------------------------------------------------------------------------
# Dependency helper
# ---------------------------------------------------------------------------

def _get_manager() -> "Manager":
    """FastAPI dependency — overridden in app startup."""
    raise HTTPException(status_code=503, detail="Manager not available")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/status", response_model=MigrationStatusResponse)
async def get_migration_status(
    manager: "Manager" = Depends(_get_manager),
) -> dict:
    """Return the current migration status.

    Returns:
        Migration status dict with pending migrations and helper state.
    """
    runner = getattr(manager, "migration_runner", None)
    if runner is None:
        return {
            "status": "ok",
            "bootstrap_required": False,
            "helper_installed": True,
            "pending_count": 0,
            "pending": [],
            "applied": [],
            "last_error": None,
        }
    return runner.get_status_dict()


@router.post("/bootstrap")
async def bootstrap_migration_helper(
    request: BootstrapRequest,
    background_tasks: BackgroundTasks,
    manager: "Manager" = Depends(_get_manager),
) -> dict:
    """Install the boneio-migrate helper using the user's sudo password.

    The password is passed to ``sudo -S`` via stdin and is never stored.

    Args:
        request: Request body with sudo password.
        background_tasks: FastAPI background tasks.
        manager: Manager instance.

    Returns:
        Success or error message.
    """
    runner = getattr(manager, "migration_runner", None)
    if runner is None:
        raise HTTPException(status_code=503, detail="Migration runner not available")

    if runner._helper_installed():
        return {"success": True, "message": "Helper already installed."}

    password = request.password.get_secret_value()

    try:
        # Run in executor to avoid blocking the event loop
        loop = asyncio.get_running_loop()
        success, message = await loop.run_in_executor(
            None,
            lambda: runner.bootstrap_install(password),
        )
    except Exception as exc:
        _LOGGER.error("Bootstrap install exception: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Bootstrap failed: {exc}") from exc
    finally:
        # Zero out the password variable
        password = ""  # noqa: F841

    if not success:
        raise HTTPException(status_code=400, detail=message)

    # If bootstrap succeeded, apply pending migrations in background
    background_tasks.add_task(_apply_pending_background, manager)

    return {"success": True, "message": message}


@router.post("/apply")
async def apply_migrations(
    background_tasks: BackgroundTasks,
    manager: "Manager" = Depends(_get_manager),
) -> dict:
    """Trigger migration apply (helper must already be installed).

    Args:
        background_tasks: FastAPI background tasks.
        manager: Manager instance.

    Returns:
        Accepted response — apply runs in background.
    """
    runner = getattr(manager, "migration_runner", None)
    if runner is None:
        raise HTTPException(status_code=503, detail="Migration runner not available")

    if not runner._helper_installed():
        raise HTTPException(
            status_code=400,
            detail="boneio-migrate helper not installed. Complete bootstrap first.",
        )

    background_tasks.add_task(_apply_pending_background, manager)
    return {"success": True, "message": "Migration apply started in background."}


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------

async def _apply_pending_background(manager: "Manager") -> None:
    """Apply pending migrations in the background.

    Args:
        manager: Manager instance.
    """
    runner = getattr(manager, "migration_runner", None)
    if runner is None:
        return

    loop = asyncio.get_running_loop()
    try:
        success = await loop.run_in_executor(None, runner.apply_all)
        if success:
            _LOGGER.info("Background migration apply completed successfully.")
        else:
            _LOGGER.error("Background migration apply failed: %s", runner.last_error)
    except Exception as exc:
        _LOGGER.error("Background migration apply exception: %s", exc, exc_info=True)
