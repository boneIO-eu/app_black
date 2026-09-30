"""Account management routes.

Two surfaces with deliberately different names and different privileges:

``/api/accounts`` (plural) is **management** — listing, creating, deleting,
changing someone else's role or password. Admin only, enforced in
:mod:`boneio.webui.middleware.policy`, not here.

``/api/account`` (singular) is **self-service** — the signed-in user changing
their own password. Any role may use it, because a read-only account whose
password cannot be rotated is a read-only account nobody will rotate. It asks
for the current password, so a borrowed session cannot silently take the
account over.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from boneio.core.auth.models import Role
from boneio.core.auth.store import UserStore, UserStoreError
from boneio.webui.middleware.auth import get_user_store, issue_token
from boneio.webui.routes.auth import (
    SessionLocked,
    check_password_throttled,
    signed_out_response,
)

_LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["accounts"])


def _store() -> UserStore:
    """Return the account store.

    Returns:
        The configured store.

    Raises:
        HTTPException: 500 if the app was not initialised.
    """
    store = get_user_store()
    if store is None:
        raise HTTPException(status_code=500, detail="Account store not initialized")
    return store


def _caller(request: Request) -> str:
    """Username the middleware attached to this request.

    Args:
        request: Incoming request.

    Returns:
        The caller's username, or an empty string if unauthenticated.
    """
    return getattr(request.state, "user", "") or ""


class NewAccount(BaseModel):
    """Payload for creating an account."""

    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=8, max_length=1024)
    role: Role = Role.VIEWER


class RoleChange(BaseModel):
    """Payload for changing an account's role."""

    role: Role


class PasswordReset(BaseModel):
    """Payload for an admin resetting someone else's password."""

    password: str = Field(..., min_length=8, max_length=1024)


class OwnPasswordChange(BaseModel):
    """Payload for a user changing their own password."""

    current_password: str = Field(..., min_length=1, max_length=1024)
    new_password: str = Field(..., min_length=8, max_length=1024)


# ------------------------------------------------------------- management


@router.get("/accounts")
async def list_accounts():
    """List every account, without password hashes.

    Returns:
        Dictionary with the account list.
    """
    return {"accounts": [user.to_public_dict() for user in _store().list_users()]}


@router.post("/accounts", status_code=201)
async def create_account(payload: NewAccount):
    """Create an account.

    Args:
        payload: Username, password and role.

    Returns:
        The created account.

    Raises:
        HTTPException: 400 if the store rejects the name or password.
    """
    try:
        # scrypt is deliberately expensive; keep it off the event loop.
        user = await asyncio.to_thread(
            _store().add_user, payload.username, payload.password, payload.role
        )
    except UserStoreError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err

    return {"account": user.to_public_dict()}


@router.delete("/accounts/{username}")
async def delete_account(username: str, request: Request):
    """Delete an account.

    Deleting the last administrator is refused by the store, so the device
    cannot be left unmanageable.

    Args:
        username: Account to remove.
        request: Incoming request, used to identify the caller.

    Returns:
        Confirmation dictionary.

    Raises:
        HTTPException: 400 if the store refuses, 409 on self-deletion.
    """
    if username.strip().lower() == _caller(request).strip().lower():
        # Not dangerous — the store still protects the last admin — but it
        # invalidates the caller's own session mid-request, which reads as a
        # bug to whoever does it by accident.
        raise HTTPException(
            status_code=409,
            detail="You cannot delete the account you are signed in with.",
        )

    try:
        await asyncio.to_thread(_store().delete_user, username)
    except UserStoreError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err

    return {"deleted": username}


@router.put("/accounts/{username}/role")
async def change_role(username: str, payload: RoleChange, request: Request):
    """Change an account's role.

    Args:
        username: Account to change.
        payload: New role.
        request: Incoming request, used to identify the caller.

    Returns:
        The updated account.

    Raises:
        HTTPException: 400 if the store refuses, 409 on self-demotion.
    """
    if (
        username.strip().lower() == _caller(request).strip().lower()
        and payload.role is not Role.ADMIN
    ):
        raise HTTPException(
            status_code=409,
            detail="You cannot remove your own administrator rights.",
        )

    try:
        user = await asyncio.to_thread(_store().set_role, username, payload.role)
    except UserStoreError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err

    return {"account": user.to_public_dict()}


@router.put("/accounts/{username}/password")
async def reset_password(username: str, payload: PasswordReset, request: Request):
    """Set another account's password, without knowing the old one.

    The change signs that account out everywhere. An administrator resetting
    their own password this way is signed out too, except for this session,
    which gets a fresh token back.

    Args:
        username: Account to change.
        payload: New password.
        request: Incoming request, used to identify the caller.

    Returns:
        The updated account, plus ``token`` when the caller reset their own.

    Raises:
        HTTPException: 400 if the store refuses.
    """
    try:
        user = await asyncio.to_thread(
            _store().set_password, username, payload.password
        )
    except UserStoreError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err

    _LOGGER.info("Password reset for account '%s' by an administrator", user.username)
    response: dict = {"account": user.to_public_dict()}
    if user.username == _caller(request):
        response["token"] = issue_token(user, getattr(request.state, "session_id", None))
    return response


# ------------------------------------------------------------ self-service


@router.get("/account/me")
async def whoami(request: Request):
    """Report who the caller is and what role they hold.

    The frontend uses this to decide which controls to render. It is a hint for
    the UI only — every decision is enforced again server-side by the auth
    middleware, so a tampered client gains nothing.

    Args:
        request: Incoming request, annotated by the auth middleware.

    Returns:
        Dictionary with the caller's username and role.
    """
    username = _caller(request)
    role = getattr(request.state, "role", None)
    if not username:
        # Anonymous access is on; there is no account behind this request.
        return {"username": None, "role": None, "anonymous": True}
    return {"username": username, "role": str(role) if role else None, "anonymous": False}


@router.put("/account/password")
async def change_own_password(payload: OwnPasswordChange, request: Request):
    """Change the signed-in user's own password.

    Args:
        payload: Current and new password.
        request: Incoming request, used to identify the caller.

    The change signs the account out everywhere else; this session carries on
    with the token in the response.

    Returns:
        Confirmation dictionary with the replacement token.

    A wrong current password is 403 ``current_password_wrong`` with
    ``attempts_left``, not 401: the session is still good, and 401 is what the
    panel takes as "you have been signed out" - a typo in the form would drop
    the owner at the login screen. Same reasoning as ``/api/auth/confirm``;
    the wrong password that uses the last try is 401 ``session_locked``.

    Raises:
        HTTPException: 400 if the new password is rejected.
    """
    username = _caller(request)
    if not username:
        raise HTTPException(status_code=401, detail="Not signed in")

    store = _store()
    try:
        check = await check_password_throttled(
            request, username, payload.current_password, where="password_change"
        )
    except SessionLocked:
        return signed_out_response()
    user = check.user
    if user is None:
        _LOGGER.warning("Rejected password change for '%s': wrong current password", username)
        return JSONResponse(
            status_code=403,
            content={
                "detail": "Current password is incorrect",
                "code": "current_password_wrong",
                "attempts_left": check.attempts_left,
            },
        )

    try:
        user = await asyncio.to_thread(store.set_password, username, payload.new_password)
    except UserStoreError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err

    return {
        "changed": True,
        "token": issue_token(user, getattr(request.state, "session_id", None)),
    }
