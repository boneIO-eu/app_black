"""Authentication routes for BoneIO Web UI."""

from __future__ import annotations

import asyncio
import hmac
import logging

from fastapi import APIRouter, Body, HTTPException

from boneio.webui.middleware.auth import (
    create_token,
    get_auth_config,
    get_user_store,
    is_auth_required,
)

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
async def login(username: str = Body(...), password: str = Body(...)):
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
    store = get_user_store()

    if store is not None and store.is_provisioned():
        # scrypt is deliberately expensive, so keep it off the event loop.
        user = await asyncio.to_thread(store.verify_credentials, username, password)
        if user is None:
            _LOGGER.warning("Failed login attempt for user: %s", username)
            raise HTTPException(status_code=401, detail="Invalid credentials")

        token = create_token({"sub": user.username, "role": str(user.role)})
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
        token = create_token({"sub": username, "role": "admin"})
        return {"token": token, "role": "admin", "username": username}

    _LOGGER.warning("Failed login attempt for user: %s", username)
    raise HTTPException(status_code=401, detail="Invalid credentials")
