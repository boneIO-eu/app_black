"""Authentication middleware for BoneIO Web UI."""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
from datetime import UTC, datetime, timedelta, timezone
from typing import TYPE_CHECKING

import jwt
from jwt import PyJWTError as JWTError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from boneio.core.auth.models import Role
from boneio.webui.middleware import policy

if TYPE_CHECKING:
    from boneio.core.auth.models import User
    from boneio.core.auth.store import UserStore

_LOGGER = logging.getLogger(__name__)

# JWT Configuration
JWT_ALGORITHM = "HS256"
_JWT_SECRET = os.getenv('JWT_SECRET', secrets.token_hex(32))

# How long a login token stays valid. This is the interval at which a user has
# to re-enter their password, so it is kept long: the password check is a
# deliberately expensive scrypt hash (~0.9 s on a BeagleBone) and this is the
# only thing that keeps that cost off the everyday path.
#
# A long-lived token is only tolerable because it can be cut short. Each token
# carries the account's session version (`ver`), and changing the password
# bumps it, so every token issued before the change stops working at once —
# a leaked one included. What a token cannot do on its own is the dangerous
# part of the API: that wants the password again (see REAUTH_WINDOW).
TOKEN_TTL_DAYS = 30

# How long after typing the password a token still counts as the owner being
# at the keyboard, for the requests policy.requires_recent_auth() names. Long
# enough that a maintenance session — restore, then update, then a new account
# — asks once; short enough that a token left on a shared laptop overnight
# does not qualify.
REAUTH_WINDOW = timedelta(minutes=10)

# The controller has no real-time clock, and until NTP answers after a boot it
# can be minutes or years out. A password confirmed before the clock stepped
# back would then carry an auth_time in the future and count as fresh for as
# long as the gap lasts, so a timestamp further ahead than this is refused.
_AUTH_TIME_SKEW = timedelta(seconds=60)

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


def issue_token(user: User, sid: str | None = None) -> str:
    """Sign a login token for an account in the store.

    Every route that signs somebody in comes through here, so the claims the
    middleware relies on are always present. It is only ever called right
    after the password was checked, which is what ``auth_time`` records.
    That is a claim of its own rather than ``iat``: PyJWT validates ``iat``
    against the clock, and on a controller whose clock jumps that would
    invalidate every token.

    ``sid`` names the browser session, so one can be signed out without the
    account's others. A login starts a new one; a route that re-issues the
    token of a session already signed in (confirming the password, changing
    it) passes the caller's own, since it is still the same session.

    Args:
        user: The account, as the store holds it now.
        sid: The session to keep, or None to start a new one.

    Returns:
        Encoded JWT carrying the username, the role, the session version, the
        session id and when the password was last typed.
    """
    return create_token(
        {
            "sub": user.username,
            "role": str(user.role),
            "ver": user.session_version,
            "sid": sid or secrets.token_hex(16),
            "auth_time": int(datetime.now(UTC).timestamp()),
        }
    )


def session_id_of(payload: dict, token: str) -> str:
    """Name the browser session a token belongs to.

    Tokens carry a ``sid`` since the session could be signed out on its own.
    One issued before that has none, and every token alive when this shipped
    is such a token — stolen ones included — so it is named by a hash of the
    token itself: exactly that token, and none of the account's others.

    Args:
        payload: Verified JWT payload.
        token: The encoded token the payload came from.

    Returns:
        The session id.
    """
    sid = payload.get("sid")
    if isinstance(sid, str) and sid:
        return sid
    return "t:" + hashlib.sha256(token.encode()).hexdigest()[:32]


def recently_authenticated(payload: dict) -> bool:
    """Whether the password behind this token was typed within REAUTH_WINDOW.

    Args:
        payload: Verified JWT payload.

    Returns:
        True if the token is fresh enough for a request that asks for it.
    """
    raw = payload.get("auth_time")
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        # Tokens from before this claim existed never qualify: they were
        # issued at some unknown point in the last 30 days.
        return False
    now = datetime.now(UTC)
    try:
        issued = datetime.fromtimestamp(raw, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return False
    return now - REAUTH_WINDOW <= issued <= now + _AUTH_TIME_SKEW


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

    Four gates, in order:

    1. **Exempt routes** pass straight through: the SPA and its assets, plus
       ``/api/login``, ``/api/init``, ``/api/version``, ``/api/auth/required``
       and the first-run wizard. The wizard is open because a device with no
       account has nothing to authenticate against; it guards itself by
       refusing to create a second administrator.
    2. **A device with no credentials is refused, not waved through.** It
       answers 403 ``setup_required`` until the wizard has run, unless
       ``web.auth.allow_anonymous`` is set in config.yaml. The rule keys off
       device state, not version, so it behaves the same on an upgraded
       device as on a freshly flashed one.
    3. **The token's role decides**, per :mod:`boneio.webui.middleware.policy`.
    4. **Some requests want the password again.** The policy names the ones
       that cannot be walked back; for those the token has to have been issued
       within REAUTH_WINDOW, or the answer is 403 ``reauth_required`` and the
       panel asks, through POST /api/auth/confirm.
    """

    async def dispatch(self, request: Request, call_next):
        """Process request and verify authentication if required."""
        path = request.url.path

        if not policy.is_api_path(path) or policy.is_exempt(path):
            # Exempt does not mean anonymous. These routes answer without a
            # token, but when one is presented the handler should be able to
            # tell who is calling — /api/init and /api/version withhold the
            # serial number from strangers on that basis. Best effort on
            # purpose: a stale or malformed token must not turn a login attempt
            # into an error, so anything unparseable simply leaves the request
            # anonymous.
            _attach_identity_if_present(request)
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

        session_id = session_id_of(payload, token)
        role, refusal = resolve_session(payload, session_id)
        if role is None:
            # Tokens live for weeks, so without this a deleted account, one
            # whose password has since changed, or a session cut off for
            # guessing, keeps its access until expiry.
            _LOGGER.warning(
                "Rejected a token for '%s': %s", payload.get("sub", "?"), refusal
            )
            return JSONResponse(
                status_code=401,
                content={
                    "detail": _REFUSAL_DETAIL[refusal],
                    "code": refusal,
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

        if policy.requires_recent_auth(request.method, path) and _step_up_applies():
            if not recently_authenticated(payload):
                _LOGGER.info(
                    "Asked '%s' to confirm the password for %s %s",
                    payload.get("sub", "?"),
                    request.method,
                    path,
                )
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": "Confirm your password to continue.",
                        "code": "reauth_required",
                    },
                )

        # Downstream handlers can read who is calling without decoding again.
        request.state.user = payload.get("sub")
        request.state.role = role
        request.state.session_id = session_id
        request.state.token_exp = int(payload.get("exp", 0))

        return await call_next(request)


def _step_up_applies() -> bool:
    """Whether there are accounts to confirm a password against.

    Only a provisioned device has them. A legacy web.auth pair that could not
    be migrated has no store entry for POST /api/auth/confirm to check, so
    asking there would lock the owner out of the very routes that fix it.

    Returns:
        True if the device keeps its accounts in users.json.
    """
    store = _user_store
    if store is None:
        return False
    try:
        return store.is_provisioned()
    except Exception:  # noqa: BLE001 - never fail open on a read error
        return True


def _attach_identity_if_present(request: Request) -> None:
    """Note who is calling, if they said, without ever refusing the request.

    Args:
        request: Incoming request on an exempt route.
    """
    header = request.headers.get("Authorization") or ""
    try:
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            return
        payload = verify_token(token.strip())
        if payload is None:
            return
        role, _ = resolve_session(payload, session_id_of(payload, token.strip()))
        if role is None:
            return
        request.state.user = payload.get("sub")
        request.state.role = role
    except Exception:  # noqa: BLE001 - identity here is a nicety, never a gate
        return


# What the caller is told when resolve_session() refuses a token.
_REFUSAL_DETAIL = {
    "account_gone": "This account no longer exists.",
    "session_revoked": "The password has changed since you signed in. Sign in again.",
    "session_locked": "This session was signed out after too many wrong passwords.",
}


def resolve_session(
    payload: dict, session_id: str | None = None
) -> tuple[Role | None, str | None]:
    """The caller's *current* role, looked up rather than taken on trust.

    The token carries a role claim, but it is only a claim: tokens are valid
    for weeks, so an account deleted or demoted in the meantime would keep the
    privilege it was issued with until expiry. The store is consulted on every
    request instead — an in-memory dict lookup, and one the request already
    pays for via is_auth_required(). The token proves who you are; the store
    decides what that is currently worth.

    The same lookup is where a token is revoked: its ``ver`` claim has to match
    the account's session version, which a password change bumps. A token
    without the claim predates it and counts as version 0, which every account
    starts at, so upgrading does not sign anybody out.

    The role claim is still the answer on a device that is not provisioned,
    where the caller authenticated against a legacy web.auth pair that was
    never in users.json.

    A single session can also be cut off on its own, after too many wrong
    passwords typed in it; ``session_id`` is checked against those.

    Args:
        payload: Verified JWT payload.
        session_id: The token's session (see session_id_of), when known.

    Returns:
        ``(role, None)`` when the token is good, or ``(None, code)`` when the
        request should be rejected — ``account_gone``, ``session_revoked`` or
        ``session_locked``.
    """
    store = _user_store
    if store is not None:
        try:
            if store.is_provisioned():
                user = store.get_user(str(payload.get("sub", "")))
                if user is None:
                    return None, "account_gone"
                if _token_version(payload) != user.session_version:
                    return None, "session_revoked"
                if session_id is not None and session_id in user.revoked_sessions:
                    return None, "session_locked"
                return user.role, None
        except Exception as err:  # noqa: BLE001 - never fail open on a read error
            _LOGGER.error("Cannot read the account store: %s", err)
            return None, "account_gone"

    return _role_from_payload(payload), None


def _token_version(payload: dict) -> int | None:
    """The session version a token was issued under.

    Args:
        payload: Verified JWT payload.

    Returns:
        The version, 0 for a token issued before versions existed, or None for
        a claim that is not a whole number — which then matches no account.
    """
    raw = payload.get("ver", 0)
    if isinstance(raw, bool) or not isinstance(raw, int):
        return None
    return raw


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
