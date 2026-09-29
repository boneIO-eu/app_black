"""Authentication routes for BoneIO Web UI."""

from __future__ import annotations

import asyncio
import hmac
import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import JSONResponse

from boneio.webui.middleware.auth import (
    create_token,
    issue_token,
    get_auth_config,
    get_user_store,
    is_auth_required,
)
from boneio.webui.rate_limit import ip_key, login_rate_limiter, user_key

if TYPE_CHECKING:
    from boneio.core.auth.models import User

_LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["auth"])


@router.get("/auth/required")
async def auth_required():
    """
    Check if authentication is required.
    
    Returns:
        Dictionary with 'required' boolean indicating if auth is needed.
    """
    try:
        return {"required": is_auth_required()}
    except Exception as e:
        _LOGGER.error("Error checking auth requirement: %s", e)
        # Default to requiring auth if there's an error
        return {"required": True}


@router.post("/login")
async def login(
    request: Request,
    username: str = Body(...),
    password: str = Body(...),
):
    """
    Authenticate user and return JWT token.

    A provisioned device is authenticated entirely against users.json, and the
    issued token carries the account's role so downstream checks do not have to
    look the user up again.

    Args:
        username: User's username.
        password: User's password.

    Returns:
        Dictionary with a JWT token and the role it grants.

    Raises:
        HTTPException: 401 if credentials are invalid.
    """
    # Throttled per IP and per account: neither alone is enough. Behind a
    # reverse proxy every client shares the proxy's address, so an IP-only
    # limit would let one attacker throttle the whole household; an
    # account-only limit is blind to one guess sprayed across many names.
    #
    # The 429 is byte-identical whichever bucket is full, and is returned
    # before the credentials are looked at, so the limiter cannot be used to
    # ask whether an account exists.
    client = request.client.host if request.client else "unknown"
    keys = (ip_key(client), user_key(username))

    if not login_rate_limiter.check_all(*keys):
        retry_after = login_rate_limiter.retry_after(*keys)
        _LOGGER.warning(
            "Throttled login attempt for '%s' from %s; %ds remaining",
            username,
            client,
            retry_after,
        )
        raise HTTPException(
            status_code=429,
            detail="Too many sign-in attempts. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    store = get_user_store()

    if store is not None and store.is_provisioned():
        # scrypt is deliberately expensive, so keep it off the event loop.
        user = await asyncio.to_thread(store.verify_credentials, username, password)
        if user is None:
            login_rate_limiter.record_failures(*keys)
            _LOGGER.warning("Failed login attempt for user: %s", username)
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # Someone who mistyped twice and then got it right should not carry
        # those failures around for the rest of the window.
        login_rate_limiter.reset(*keys)
        token = issue_token(user)
        return {"token": token, "role": str(user.role), "username": user.username}

    auth_config = get_auth_config()

    if not auth_config:
        # The device has no credentials at all: no accounts and no web.auth.
        # Every API route is open in this state anyway, so the token grants
        # nothing that withholding it would protect. Both halves are closed
        # together by deliverables #2 and #3 in SECURITY_ROADMAP_1.6.md;
        # splitting them would only break the UI for unprovisioned devices.
        _LOGGER.warning(
            "Issuing a token on a device with no accounts. Run the first-run "
            "wizard to create an administrator."
        )
        token = create_token({"sub": "default", "role": "admin"})
        return {"token": token, "role": "admin", "username": "default"}

    # Legacy config.yaml credentials that the startup migration could not move
    # across (for example a username the new store cannot represent).
    expected_username = auth_config.get("username", "")
    expected_password = auth_config.get("password", "")

    username_ok = hmac.compare_digest(username, expected_username)
    password_ok = hmac.compare_digest(password, expected_password)

    if username_ok and password_ok:
        login_rate_limiter.reset(*keys)
        token = create_token({"sub": username, "role": "admin"})
        return {"token": token, "role": "admin", "username": username}

    login_rate_limiter.record_failures(*keys)
    _LOGGER.warning("Failed login attempt for user: %s", username)
    raise HTTPException(status_code=401, detail="Invalid credentials")


async def check_password_throttled(request: Request, username: str, password: str) -> User | None:
    """Check a signed-in account's password, on the login's attempt budget.

    For the routes that ask a caller who already holds a token to type the
    password again. They are password guesses like any other, so they draw on
    the same per-IP and per-account buckets as /api/login: otherwise somebody
    with a borrowed session could guess the owner's password at leisure, and
    confirming would double the budget of the login screen.

    Args:
        request: Incoming request, for the caller's address.
        username: The account the token belongs to.
        password: What the caller typed.

    Returns:
        The account if the password is right, None if it is not.

    Raises:
        HTTPException: 429 while either bucket is full, 409 on a device with
            no accounts to check against.
    """
    store = get_user_store()
    if store is None or not store.is_provisioned():
        raise HTTPException(
            status_code=409, detail="This device has no accounts to confirm against."
        )

    client = request.client.host if request.client else "unknown"
    keys = (ip_key(client), user_key(username))
    if not login_rate_limiter.check_all(*keys):
        retry_after = login_rate_limiter.retry_after(*keys)
        _LOGGER.warning(
            "Throttled a password confirmation for '%s' from %s; %ds remaining",
            username,
            client,
            retry_after,
        )
        raise HTTPException(
            status_code=429,
            detail="Too many attempts. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    user = await asyncio.to_thread(store.verify_credentials, username, password)
    if user is None:
        login_rate_limiter.record_failures(*keys)
        _LOGGER.warning("Wrong password confirming '%s' from %s", username, client)
        return None

    login_rate_limiter.reset(*keys)
    return user


@router.post("/auth/confirm")
async def confirm_password(request: Request, password: str = Body(..., embed=True)):
    """Confirm the signed-in account's password for a request that wants it.

    The requests policy.requires_recent_auth() names answer 403
    ``reauth_required`` to a token issued more than REAUTH_WINDOW ago. The
    panel then asks for the password, sends it here, and repeats the request
    with the token this returns — the same account and session, with a fresh
    ``auth_time``.

    A wrong password is 403 ``reauth_failed``, not 401: the caller's session is
    still good, and 401 is what the panel takes as "you have been signed out".

    Args:
        request: Incoming request, annotated by the auth middleware.
        password: The account's password.

    Returns:
        Dictionary with the replacement token.
    """
    username = getattr(request.state, "user", "") or ""
    if not username:
        raise HTTPException(status_code=401, detail="Not signed in")

    user = await check_password_throttled(request, username, password)
    if user is None:
        return JSONResponse(
            status_code=403,
            content={"detail": "The password is not correct.", "code": "reauth_failed"},
        )

    _LOGGER.info("Password confirmed for '%s'", user.username)
    return {"token": issue_token(user)}
