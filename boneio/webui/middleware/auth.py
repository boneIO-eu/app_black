"""Authentication middleware for BoneIO Web UI."""

from __future__ import annotations

import logging
import os
import secrets
from datetime import UTC, datetime, timedelta, timezone
from typing import TYPE_CHECKING

from jose import jwt
from jose.exceptions import JWTError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

if TYPE_CHECKING:
    from boneio.core.auth.store import UserStore

_LOGGER = logging.getLogger(__name__)

# JWT Configuration
JWT_ALGORITHM = "HS256"
_JWT_SECRET = os.getenv('JWT_SECRET', secrets.token_hex(32))

# Auth configuration - will be set by init_app
_auth_config: dict = {}

# Account store (users.json) - set by init_app. From 1.6 this, not _auth_config,
# is what decides whether the device has credentials; _auth_config only lingers
# for devices that have never been provisioned.
_user_store: UserStore | None = None


def set_user_store(store: UserStore | None) -> None:
    """Attach the account store used for authentication.

    Args:
        store: Loaded account store, or None on a device without one.
    """
    global _user_store
    _user_store = store


def get_user_store() -> UserStore | None:
    """Return the account store, if one has been attached.

    Returns:
        The store, or None before init_app has run.
    """
    return _user_store


def set_jwt_secret(secret: str) -> None:
    """
    Set JWT secret for token signing and verification.
    
    Args:
        secret: JWT secret string.
    """
    global _JWT_SECRET
    _JWT_SECRET = secret


def get_jwt_secret() -> str:
    """
    Get current JWT secret.
    
    Returns:
        JWT secret string.
    """
    return _JWT_SECRET


def set_auth_config(config: dict) -> None:
    """
    Set authentication configuration.
    
    Args:
        config: Dictionary with 'username' and 'password' keys.
    """
    global _auth_config
    _auth_config = config


def get_auth_config() -> dict:
    """
    Get current authentication configuration.
    
    Returns:
        Dictionary with authentication settings.
    """
    return _auth_config


def is_auth_required() -> bool:
    """
    Check if authentication is required.

    A provisioned device (at least one admin in users.json) always requires
    authentication. The legacy config.yaml pair is only consulted for a device
    that has not been provisioned, which after the startup migration means one
    that never had credentials at all.

    Returns:
        True if the device has credentials.
    """
    if _user_store is not None:
        try:
            if _user_store.is_provisioned():
                return True
        except Exception as err:  # noqa: BLE001 - never fail open on a read error
            _LOGGER.error("Cannot read the account store: %s", err)
            return True

    return bool(_auth_config.get("username") and _auth_config.get("password"))


def create_token(data: dict) -> str:
    """
    Create a JWT token.
    
    Args:
        data: Data to encode in the token.
        
    Returns:
        Encoded JWT token string.
    """
    to_encode = data.copy()
    expire = datetime.now(UTC) + timedelta(days=7)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, _JWT_SECRET, algorithm=JWT_ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> dict | None:
    """
    Verify a JWT token.
    
    Args:
        token: JWT token string to verify.
        
    Returns:
        Token payload if valid, None otherwise.
    """
    try:
        payload = jwt.decode(token, _JWT_SECRET, algorithms=[JWT_ALGORITHM])
        exp = payload.get("exp")
        if not exp or datetime.fromtimestamp(exp, tz=UTC) < datetime.now(UTC):
            return None
        return payload
    except JWTError:
        return None


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware for JWT-based authentication.
    
    Skips authentication for:
    - Non-API routes
    - Login endpoint
    - Auth required check endpoint
    - Version endpoint
    - First-run wizard endpoints, which a device with no account yet has no
      way to authenticate against. They guard themselves instead: creating an
      administrator is refused once one exists.
    """

    async def dispatch(self, request: Request, call_next):
        """Process request and verify authentication if required."""
        # Skip auth for non-API routes and specific endpoints
        if (
            not request.url.path.startswith("/api")
            or request.url.path == "/api/login"
            or request.url.path == "/api/auth/required"
            or request.url.path == "/api/version"
            or request.url.path == "/api/init"
            or request.url.path.startswith("/api/onboarding")
        ):
            return await call_next(request)

        # Skip auth on a device that has no credentials at all.
        #
        # This reads the account store, not _auth_config: a device provisioned
        # through the first-run wizard has an admin in users.json and nothing
        # in config.yaml, and gating on _auth_config would leave its API wide
        # open until the next restart.
        #
        # A device that has never had credentials is still open, which is the
        # pre-1.6 behaviour. Closing that is deliverable #2 (admin/read-only
        # roles) in SECURITY_ROADMAP_1.6.md.
        if not is_auth_required():
            return await call_next(request)

        auth_header = request.headers.get("Authorization")
        
        # For SSE endpoints, also check query params (EventSource doesn't support headers)
        token_from_query = request.query_params.get("token")
        
        if not auth_header and not token_from_query:
            return JSONResponse(
                status_code=401,
                content={"detail": "No authorization header"}
            )

        try:
            token: str | None = None
            
            # Try to get token from Authorization header first
            if auth_header:
                scheme, token = auth_header.split()
                if scheme.lower() != "bearer":
                    return JSONResponse(
                        status_code=401,
                        content={"detail": "Invalid authentication scheme"}
                    )
            # Fall back to query param token (for SSE/EventSource)
            elif token_from_query:
                token = token_from_query

            # Verify the JWT token
            if not token:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "No token provided"}
                )
                
            payload = verify_token(token)
            if payload is None:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or expired token"}
                )

        except JWTError:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid token"}
            )
        except ValueError:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid authorization header format"}
            )

        return await call_next(request)
