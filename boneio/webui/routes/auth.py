"""Authentication routes for BoneIO Web UI."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Body, HTTPException

from boneio.webui.middleware.auth import (
    create_token,
    get_auth_config,
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
        _LOGGER.error(f"Error checking auth requirement: {e}")
        # Default to requiring auth if there's an error
        return {"required": True}


@router.post("/login")
async def login(username: str = Body(...), password: str = Body(...)):
    """
    Authenticate user and return JWT token.
    
    Args:
        username: User's username.
        password: User's password.
        
    Returns:
        Dictionary with JWT token if authentication successful.
        
    Raises:
        HTTPException: 401 if credentials are invalid.
    """
    auth_config = get_auth_config()
    
    if not auth_config:
        token = create_token({"sub": "default"})
        return {"token": token}

    if username == auth_config.get("username") and password == auth_config.get("password"):
        token = create_token({"sub": username})
        return {"token": token}
    
    raise HTTPException(status_code=401, detail="Invalid credentials")
