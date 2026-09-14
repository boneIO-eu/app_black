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

from boneio.core.auth.models import Role
from boneio.webui.middleware import policy

if TYPE_CHECKING:
    from boneio.core.auth.store import UserStore

_LOGGER = logging.getLogger(__name__)

# JWT Configuration
JWT_ALGORITHM = "HS256"
_JWT_SECRET = os.getenv('JWT_SECRET', secrets.token_hex(32))

# How long a login token stays valid. This is the interval at which a user has
# to re-enter their password, so it is kept long: the password check is a
# deliberately expensive scrypt hash (~0.9 s on a BeagleBone) and this is the
# only thing that keeps that cost off the everyday path. The tradeoff is that a
# leaked token stays usable until it expires — there is no per-token server-side
# revocation, only logout (client-side) or rotating the JWT secret (logs
# everyone out). For a LAN device with a handful of trusted users that is an
# acceptable trade for not typing a password every week.
TOKEN_TTL_DAYS = 30

# Auth configuration - will be set by init_app
_auth_config: dict = {}

# Explicit opt-out of authentication, from `web.auth.allow_anonymous` in
# config.yaml. Deliberately not reachable from the UI: a warning is a notice,
# not a control, and a "skip" button in the first-run wizard would make the
# unauthenticated state a normal outcome of the intended setup flow. Requiring
# an SSH session and a YAML edit keeps the shipped default secure and makes the
# opt-out a documented, greppable decision instead.
_allow_anonymous: bool = False


def set_allow_anonymous(allowed: bool) -> None:
    """Record whether config.yaml opts this device out of authentication.

    Args:
        allowed: Value of ``web.auth.allow_anonymous``.
    """
    global _allow_anonymous
    _allow_anonymous = bool(allowed)


def is_anonymous_allowed() -> bool:
    """Whether config.yaml opts this device out of authentication.

    Returns:
        True if anonymous access is explicitly permitted.
    """
    return _allow_anonymous


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
    expire = datetime.now(UTC) + timedelta(days=TOKEN_TTL_DAYS)
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
    """Authenticates API requests and enforces the role policy.

    Three gates, in order:

    1. **Exempt routes** pass straight through: the SPA and its assets, plus
       ``/api/login``, ``/api/init``, ``/api/version``, ``/api/auth/required``
       and the first-run wizard. The wizard is open because a device with no
       account has nothing to authenticate against; it guards itself by
       refusing to create a second administrator.
    2. **A device with no credentials is refused, not waved through.** Before
       1.6 an unprovisioned device served its whole API to anyone on the
       network (F-02). It now answers 403 ``setup_required`` until the wizard
       has run, unless ``web.auth.allow_anonymous`` is set in config.yaml.
       The rule keys off device state, not version, so it behaves the same
       whether the owner came from 1.5, skipped 1.6, or flashed the image
       fresh.
    3. **The token's role decides**, per :mod:`boneio.webui.middleware.policy`.
    """

    async def dispatch(self, request: Request, call_next):
        """Process request and verify authentication if required."""
        path = request.url.path

        if not policy.is_api_path(path) or policy.is_exempt(path):
            return await call_next(request)

        if not is_auth_required():
            if not _allow_anonymous:
                # The device has never been set up. Closing this is the whole
                # point of the first-run wizard: leaving it open is how an
                # unauthenticated reboot or config overwrite stayed reachable.
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": (
                            "This device has no administrator account yet. Open "
                            "the web UI to finish setup."
                        ),
                        "code": "setup_required",
                    },
                )
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

        role = _resolve_role(payload)
        if role is None:
            # The account behind this token is gone. Tokens live for weeks, so
            # without this a deleted account keeps its access until expiry.
            _LOGGER.warning(
                "Rejected a token for '%s': the account no longer exists",
                payload.get("sub", "?"),
            )
            return JSONResponse(
                status_code=401,
                content={
                    "detail": "This account no longer exists.",
                    "code": "account_gone",
                },
            )

        if not policy.role_allows(role, request.method, path):
            _LOGGER.warning(
                "Refused %s %s for '%s' (role %s)",
                request.method,
                path,
                payload.get("sub", "?"),
                role,
            )
            return JSONResponse(
                status_code=403,
                content={
                    "detail": "This account does not have permission for that.",
                    "code": "forbidden",
                    "required_role": str(policy.required_role(request.method, path)),
                },
            )

        # Downstream handlers can read who is calling without decoding again.
        request.state.user = payload.get("sub")
        request.state.role = role

        return await call_next(request)


def _resolve_role(payload: dict) -> Role | None:
    """The caller's *current* role, looked up rather than taken on trust.

    The token carries a role claim, but it is only a claim: tokens are valid
    for weeks, so an account deleted or demoted in the meantime would keep the
    privilege it was issued with until expiry. There is no per-token
    revocation, so the store is consulted on every request instead — an
    in-memory dict lookup, and one the request already pays for via
    is_auth_required(). The token proves who you are; the store decides what
    that is currently worth.

    The claim is still the answer on a device that is not provisioned, where
    the caller authenticated against a legacy web.auth pair that was never in
    users.json.

    Args:
        payload: Verified JWT payload.

    Returns:
        The role to enforce, or None if the account is gone and the request
        should be rejected.
    """
    store = _user_store
    if store is not None:
        try:
            if store.is_provisioned():
                user = store.get_user(str(payload.get("sub", "")))
                return user.role if user is not None else None
        except Exception as err:  # noqa: BLE001 - never fail open on a read error
            _LOGGER.error("Cannot read the account store: %s", err)
            return None

    return _role_from_payload(payload)


def _role_from_payload(payload: dict) -> Role:
    """Read the role out of a verified token.

    A token with no role claim, or one naming a role this build does not know,
    is treated as a viewer. Tokens issued before roles existed are the common
    case, and quietly upgrading them to admin would hand out privilege the
    issuer never granted.

    Args:
        payload: Verified JWT payload.

    Returns:
        The role to enforce.
    """
    try:
        return Role(str(payload.get("role", "")).strip().lower())
    except ValueError:
        return Role.VIEWER
