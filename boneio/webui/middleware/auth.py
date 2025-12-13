"""Authentication middleware for BoneIO Web UI."""

from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

from jose import jwt
from jose.exceptions import JWTError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

_LOGGER = logging.getLogger(__name__)

# JWT Configuration
JWT_ALGORITHM = "HS256"
JWT_SECRET = os.getenv('JWT_SECRET', secrets.token_hex(32))

# Auth configuration - will be set by init_app
_auth_config: dict = {}


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
    
    Returns:
        True if both username and password are configured.
    """
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
    expire = datetime.now(timezone.utc) + timedelta(days=7)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
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
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        exp = payload.get("exp")
        if not exp or datetime.fromtimestamp(exp, tz=timezone.utc) < datetime.now(timezone.utc):
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
    """
    
    async def dispatch(self, request: Request, call_next):
        """Process request and verify authentication if required."""
        # Skip auth for non-API routes and specific endpoints
        if (
            not request.url.path.startswith("/api")
            or request.url.path == "/api/login"
            or request.url.path == "/api/auth/required"
            or request.url.path == "/api/version"
        ):
            return await call_next(request)

        # Skip auth if not configured
        if not _auth_config:
            return await call_next(request)

        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return JSONResponse(
                status_code=401,
                content={"detail": "No authorization header"}
            )

        try:
            # Check if it's a Bearer token
            scheme, token = auth_header.split()
            if scheme.lower() != "bearer":
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid authentication scheme"}
                )

            # Verify the JWT token
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
