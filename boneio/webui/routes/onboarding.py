"""First-run wizard routes for BoneIO Web UI.

A device that has never been set up has no accounts, so these endpoints are
reachable without a token — there is nobody to authenticate as yet. The whole
security of the wizard rests on one rule, enforced in :func:`create_first_admin`:
**once an admin exists, account creation here is closed for good.** Without that
rule the endpoint would be a permanent unauthenticated way to take over a
device.

Importing an old configuration reuses the existing backup/restore routes rather
than duplicating them; the wizard only needs to know whether the device has a
usable config yet.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, Field

from boneio.core.auth.models import Role
from boneio.core import system_ops
from boneio.core.auth.store import UserStore, UserStoreError
from boneio.core.config.provenance import FACTORY_TEMPLATE_DIR
from boneio.core.config.write_lock import CONFIG_WRITE_LOCK
from boneio.version import __version__
from boneio.webui.middleware.auth import issue_token
from boneio.webui.services.logs import is_running_as_service

_LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])

_user_store: UserStore | None = None
# Set by init_app when a pre-1.6 web.auth block was moved into users.json, so
# the UI can tell the owner to delete it from config.yaml.
_legacy_migration: dict | None = None
#: Whether this controller was configured under a pre-1.6 release. Set from the
#: presence of a ``web.auth`` block, which the factory configuration does not
#: ship. The wizard uses it to drop the steps that assume a blank device.
_configured_before: bool = False
#: The directory holding config.yaml. Set by init_app.
_config_dir: Path | None = None

#: Left beside config.yaml by the image's first-boot board setup, holding the
#: board revision, when the card did not say which controller this is. The
#: controller then runs an outputless configuration until the wizard is told.
BOARD_TYPE_PENDING = ".board-type-pending"
_REVISION = re.compile(r"^\d+\.\d+$")


def set_user_store(store: UserStore) -> None:
    """Attach the account store used by the wizard.

    Args:
        store: Loaded account store.
    """
    global _user_store
    _user_store = store


def set_configured_before(value: bool) -> None:
    """Record whether this device was set up under an earlier release.

    Args:
        value: True when the configuration carries a pre-1.6 ``web.auth`` block.
    """
    global _configured_before
    _configured_before = value


def set_config_dir(path: str | os.PathLike[str]) -> None:
    """Record where config.yaml lives.

    Args:
        path: The configuration directory.
    """
    global _config_dir
    _config_dir = Path(path)


def pending_board_revision() -> str | None:
    """The board revision, while the wizard still has to ask for the type.

    Returns:
        The revision the first-boot setup detected, or None once the type is
        known (or on an image that never asks).
    """
    if _config_dir is None:
        return None
    try:
        revision = (_config_dir / BOARD_TYPE_PENDING).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    # It becomes a path below; only a revision number may.
    return revision if _REVISION.match(revision) else None


def get_configured_before() -> bool:
    """Whether this device was set up under an earlier release.

    Returns:
        True when the wizard should skip the steps that assume a blank device.
    """
    return _configured_before


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
        # The wizard skips the import and device-binding steps when this is
        # true: the device already has a configuration, and offering to import
        # one reads as "yours is gone".
        "configured_before": _configured_before,
        "board_type_required": pending_board_revision() is not None,
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

    ssh = await asyncio.to_thread(_set_service_password, payload.password)

    token = issue_token(user)
    return {"user": user.to_public_dict(), "token": token, "ssh": ssh}


def _set_service_password(password: str) -> str:
    """Make the owner's first password the boneio login too, where allowed.

    The image ships that account locked, so until this runs nobody can log in
    over SSH with a password at all — not with the "Black" that every unit used
    to share, and not with anything else. The wizard says in so many words that
    the password it is asking for becomes the SSH one as well.

    Never fails the wizard. The account now exists, and an owner who cannot get
    past this step because a helper is missing is worse off than one told the
    SSH password was not set.

    Args:
        password: The password the owner just chose.

    Returns:
        ``set`` when the login now uses it; ``kept`` when the owner already has
        a password of their own there, which is not this wizard's to replace;
        ``unavailable`` when there is no helper to ask; ``failed`` otherwise.
    """
    state = system_ops.service_password_state()
    if state is None:
        return "unavailable"
    if state == "set":
        return "kept"
    if state not in ("locked", "shipped", "empty"):
        return "failed"
    result = system_ops.service_password_init(password)
    if not result.ok:
        _LOGGER.warning("Could not set the SSH password: %s", result.stderr.strip())
        return "failed"
    _LOGGER.info("The first administrator's password is now the SSH password (was %s)", state)
    return "set"


class BoardTypeRequest(BaseModel):
    """Which controller this is, as the first-run wizard asks."""

    type: Literal["32x10", "24x16", "cover", "cover_mix"]


def _install_board_config(template: Path, config_dir: Path) -> None:
    """Replace the outputless stand-in with the configuration for this board.

    secrets.yaml stays: the broker password in it was drawn for this device at
    its first boot, and the template's is the factory placeholder.

    Args:
        template: ``~/.cache/boneio_configs/<revision>/<type>``.
        config_dir: The directory holding config.yaml.
    """
    with CONFIG_WRITE_LOCK:
        for path in config_dir.iterdir():
            if not path.is_file() or path.name == "secrets.yaml":
                continue
            if path.suffix == ".yaml" or path.name.endswith(".cache.pkl") or path.name == "state.json":
                path.unlink()
        for path in template.iterdir():
            if path.name == "secrets.yaml" and (config_dir / "secrets.yaml").exists():
                continue
            if path.suffix == ".yaml" or path.name.endswith(".cache.pkl"):
                shutil.copy2(path, config_dir / path.name)
        (config_dir / BOARD_TYPE_PENDING).unlink(missing_ok=True)


async def _restart() -> None:
    """Exit for systemd to start boneIO on the new configuration."""
    await asyncio.sleep(0.1)
    # Held, never released, as in /api/restart: no save starts after this.
    await asyncio.to_thread(CONFIG_WRITE_LOCK.acquire)
    os._exit(0)


@router.post("/board-type")
async def set_board_type(
    payload: BoardTypeRequest, request: Request, background_tasks: BackgroundTasks
):
    """Configure the controller as the type the owner picked, and restart.

    Only while the first-boot setup left the question open, and only for an
    administrator: this replaces the configuration, and the routes under
    /api/onboarding take no token by default.

    Args:
        payload: The controller type.
        request: For the caller's role.
        background_tasks: Where the restart is queued, after the reply.

    Returns:
        The type, the board revision, and whether boneIO is restarting.

    Raises:
        HTTPException: 403 without an administrator's token, 409 when the type
            is already known or the image has no configuration for it.
    """
    if getattr(request.state, "role", None) != Role.ADMIN:
        raise HTTPException(status_code=403, detail="Sign in as an administrator.")
    revision = pending_board_revision()
    if revision is None or _config_dir is None:
        raise HTTPException(status_code=409, detail="The controller type is already set.")
    template = FACTORY_TEMPLATE_DIR / revision / payload.type
    if not (template / "config.yaml").is_file():
        raise HTTPException(
            status_code=409,
            detail=f"This system image has no {payload.type} configuration for board {revision}.",
        )

    await asyncio.to_thread(_install_board_config, template, _config_dir)
    _LOGGER.info("First-run wizard configured the controller as %s (board %s)", payload.type, revision)

    restarting = is_running_as_service()
    if restarting:
        background_tasks.add_task(_restart)
    return {"type": payload.type, "revision": revision, "restarting": restarting}
