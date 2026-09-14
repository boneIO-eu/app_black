"""First-run wizard routes for BoneIO Web UI.

A device that has never been set up has no accounts, so these endpoints are
reachable without a token — there is nobody to authenticate as yet. The whole
security of the wizard rests on one rule, enforced in :func:`create_first_admin`:
**once an admin exists, account creation here is closed for good.** Without that
rule the endpoint would be a permanent unauthenticated way to take over a
device, which is the class of problem F-14 describes.

Importing an old configuration reuses the existing backup/restore routes rather
than duplicating them; the wizard only needs to know whether the device has a
usable config yet.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from boneio.core.auth.models import Role
from boneio.core.auth.store import UserStore, UserStoreError
from boneio.version import __version__
from boneio.webui.middleware.auth import create_token

_LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])

_user_store: UserStore | None = None
# Set by init_app when a pre-1.6 web.auth block was moved into users.json, so
# the UI can tell the owner to delete it from config.yaml.
_legacy_migration: dict | None = None


def set_user_store(store: UserStore) -> None:
    """Attach the account store used by the wizard.

    Args:
        store: Loaded account store.
    """
    global _user_store
    _user_store = store


def set_legacy_migration(info: dict | None) -> None:
    """Record what the startup credential migration did.

    Args:
        info: Serialised migration result, or None if nothing was migrated.
    """
    global _legacy_migration
    _legacy_migration = info


def _get_store() -> UserStore:
    """Return the account store.

    Returns:
        The configured store.

    Raises:
        HTTPException: 500 if the app was not initialised.
    """
    if _user_store is None:
        raise HTTPException(status_code=500, detail="Account store not initialized")
    return _user_store


class FirstAdminRequest(BaseModel):
    """Payload for creating the very first administrator."""

    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=8, max_length=1024)


@router.get("/status")
async def onboarding_status():
    """Report whether the first-run wizard still needs to run.

    Returns:
        Dictionary describing provisioning state, so the frontend can decide
        between the wizard and the normal UI without a second round trip.
    """
    store = _get_store()
    try:
        provisioned = store.is_provisioned()
    except UserStoreError as err:
        # The file exists but is unreadable. Claiming "not provisioned" would
        # reopen account creation on a device that already has an owner, so
        # this is surfaced as an error instead.
        _LOGGER.error("Cannot read the account store: %s", err)
        raise HTTPException(
            status_code=500, detail="Account store is unreadable"
        ) from err

    return {
        "provisioned": provisioned,
        "needs_onboarding": not provisioned,
        "version": __version__,
        "legacy_migration": _legacy_migration,
    }


@router.post("/admin", status_code=201)
async def create_first_admin(payload: FirstAdminRequest):
    """Create the first administrator account.

    Open without authentication, because a freshly flashed device has no
    account to authenticate with. It closes permanently the moment an admin
    exists — from then on new accounts are created by an authenticated admin,
    not here.

    Args:
        payload: Desired username and password.

    Returns:
        The created account plus a token, so the wizard can continue as the
        user who just proved they control the device.

    Raises:
        HTTPException: 409 if the device already has an admin, 400 if the
            username or password is rejected.
    """
    store = _get_store()

    if store.is_provisioned():
        _LOGGER.warning(
            "Rejected an attempt to create a first admin on a device that "
            "already has one."
        )
        raise HTTPException(
            status_code=409,
            detail=(
                "This device is already set up. Sign in as an administrator to "
                "manage accounts."
            ),
        )

    try:
        # scrypt burns a few hundred milliseconds of CPU on a BeagleBone;
        # off the event loop so it cannot stall every other request.
        user = await asyncio.to_thread(
            store.add_user, payload.username, payload.password, Role.ADMIN
        )
    except UserStoreError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err

    _LOGGER.info("First-run wizard created administrator '%s'", user.username)

    token = create_token({"sub": user.username, "role": str(user.role)})
    return {"user": user.to_public_dict(), "token": token}
