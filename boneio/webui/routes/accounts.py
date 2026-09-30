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

``/api/accounts/ssh-password`` is the device's SSH login, the Linux ``boneio``
account — not a panel account at all. Admin only, like the rest of
``/api/accounts``, and it asks for the current SSH password: boneio-system does
the change as root, and without that it would be a way to set the password of
an account that can sudo.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from boneio.core import system_ops
from boneio.core.auth.models import Role
from boneio.core.auth.store import UserStore, UserStoreError, validate_password
from boneio.webui import security_events
from boneio.webui.middleware.auth import get_user_store, issue_token
from boneio.webui.routes.auth import (
    SessionLocked,
    check_password_throttled,
    count_session_wrong_password,
    signed_out_response,
)
from boneio.webui.routes.security import forget_service_password_state, service_password_state

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


class SshPasswordChange(BaseModel):
    """Payload for changing the boneio SSH password."""

    current_password: str = Field(..., min_length=1, max_length=1024)
    new_password: str = Field(..., min_length=8, max_length=1024)


#: The Linux account boneio-system changes. Fixed there too; named here for
#: the password policy's similarity rule and the security event.
SSH_ACCOUNT = "boneio"
_SSH_CHANGE_VERB = "service-password-change"


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


# -------------------------------------------------------------- SSH login


def _code(status_code: int, code: str, detail: str, **extra) -> JSONResponse:
    """An error the panel tells apart by ``code``, not by its English text."""
    return JSONResponse(
        status_code=status_code, content={"detail": detail, "code": code, **extra}
    )


@router.get("/accounts/ssh-password")
async def ssh_password_state():
    """How the boneio SSH login stands, and whether the panel can change it.

    Returns:
        ``state`` — locked, empty, shipped, set, unknown, or None when the
        helper is not there to ask — and ``supported``, false until the
        migration that ships the change (1.6.29) has been applied.
    """
    supported = await asyncio.to_thread(system_ops.helper_supports, _SSH_CHANGE_VERB)
    state = await asyncio.to_thread(service_password_state)
    return {"state": state, "supported": supported}


@router.put("/accounts/ssh-password")
async def change_ssh_password(payload: SshPasswordChange, request: Request):
    """Change the boneio SSH password, given the current one.

    Equivalent to ``passwd`` over SSH, and deliberately no more: there is no
    way here to set it without the current password. A lost one is recovered
    with the flasher card (``BONEIO_RESET_ACCOUNTS=1``).

    Wrong guesses are counted twice. boneio-system keeps a global count as
    root — five in fifteen minutes — because it can be called without the
    panel. And each one counts against this session like a wrong panel
    password, so a borrowed session is signed out the same way.

    A wrong current password is 403 ``current_password_wrong`` with
    ``attempts_left``, never 401, which the panel takes as a sign-out; the one
    that uses the session's last try is 401 ``session_locked``.

    Args:
        payload: Current and new SSH password.
        request: Incoming request, used to identify the caller.

    Returns:
        ``{"changed": True}``.

    Raises:
        HTTPException: 400 if the new password is rejected.
    """
    username = _caller(request)
    if not username:
        raise HTTPException(status_code=401, detail="Not signed in")

    for password in (payload.current_password, payload.new_password):
        if "\n" in password or "\r" in password:
            raise HTTPException(status_code=400, detail="A password cannot contain a line break.")
    try:
        validate_password(payload.new_password, SSH_ACCOUNT)
    except UserStoreError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err

    if not await asyncio.to_thread(system_ops.helper_supports, _SSH_CHANGE_VERB):
        return _code(
            409,
            "helper_outdated",
            "The installed system helper cannot change the SSH password yet. "
            "Apply the pending system migrations (1.6.29) and try again.",
        )

    result = await asyncio.to_thread(
        system_ops.service_password_change, payload.current_password, payload.new_password
    )
    outcome = result.json() or {}
    kind = outcome.get("result")
    client = request.client.host if request.client else "unknown"

    if kind == "changed":
        forget_service_password_state()
        _LOGGER.info("SSH password of '%s' changed from the panel by '%s'", SSH_ACCOUNT, username)
        return {"changed": True}

    if kind == "wrong_password":
        _LOGGER.warning(
            "Rejected SSH password change by '%s' from %s: wrong current password",
            username,
            client,
        )
        left = outcome.get("attempts_left")
        left = left if isinstance(left, int) else 0
        if left == 0:
            # The one that shuts the helper for the window.
            security_events.emit(
                "password_guessing", username=SSH_ACCOUNT, client=client, where="ssh_password"
            )
        try:
            session_left = await count_session_wrong_password(request, username, "ssh_password")
        except SessionLocked:
            return signed_out_response()
        if session_left is not None:
            left = min(left, session_left)
        return _code(403, "current_password_wrong", "Current SSH password is incorrect",
                     attempts_left=left)

    if kind == "throttled":
        retry_after = outcome.get("retry_after")
        retry_after = retry_after if isinstance(retry_after, int) else 900
        response = _code(
            429,
            "ssh_password_throttled",
            "Too many wrong SSH passwords. Try again later.",
            retry_after=retry_after,
        )
        response.headers["Retry-After"] = str(retry_after)
        return response

    if kind == "refused":
        # Locked or empty: not the panel's to set. Unknown: nothing can check.
        return _code(
            409,
            "ssh_password_not_set",
            "The SSH login has no password to change.",
            state=outcome.get("state"),
        )

    detail = (result.stderr or "").strip().splitlines()
    _LOGGER.warning("SSH password change failed: %s", result.stderr.strip())
    return _code(
        500,
        "ssh_password_failed",
        detail[-1] if detail else "Could not change the SSH password.",
    )
