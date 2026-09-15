"""Refuse state-changing requests that come from another site (F-07).

The report's proof is a cross-origin form post: a page on another site submits
to ``/api/reboot`` and the browser sends it. Since 1.6 most of that is already
gone, because the session token travels in an ``Authorization`` header rather
than a cookie — a form cannot set that header, and the browser will not attach
it on its own, so the request arrives unauthenticated and is refused.

What is left is the device that needs no authentication: one running with
``web.auth.allow_anonymous``, or a development board with ``BONEIO_DEV``. There
the form post still works, and the reboot in the report still happens. This
closes that.

The rule is deliberately narrow. Only a request that *says* where it came from
is judged: browsers attach ``Origin`` to exactly the cross-site requests this
is about, while curl, a script or another service attaches nothing — and none
of those can be tricked into acting on someone else's behalf, which is the
whole idea of CSRF. Judging requests with no Origin would break every
integration without protecting anybody.

Allowed origins are the ones CORS already allows, so a setup that works today
keeps working: same-origin always, plus the Vite dev servers when BONEIO_DEV is
set. Keeping one list means the two cannot drift into disagreeing about who is
trusted.
"""

from __future__ import annotations

import logging
from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

_LOGGER = logging.getLogger(__name__)

#: Methods that cannot change anything, so they need no origin check.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


def _origin_host(origin: str) -> str:
    """The host:port an Origin header names.

    Args:
        origin: Value of the Origin header.

    Returns:
        Lower-cased ``host:port``, or an empty string if unparsable.
    """
    try:
        parts = urlsplit(origin.strip())
    except ValueError:
        return ""
    return (parts.netloc or "").lower()


class CSRFMiddleware(BaseHTTPMiddleware):
    """Rejects cross-site state-changing requests.

    Args:
        app: The ASGI app being wrapped.
        allowed_origins: Extra origins to trust, matching the CORS list.
    """

    def __init__(self, app, allowed_origins: list[str] | None = None) -> None:
        super().__init__(app)
        self._allowed = {
            _origin_host(origin) for origin in (allowed_origins or []) if origin
        }
        self._allowed.discard("")

    async def dispatch(self, request: Request, call_next):
        """Check the origin of a state-changing request."""
        if request.method.upper() in SAFE_METHODS:
            return await call_next(request)

        if not request.url.path.startswith("/api"):
            return await call_next(request)

        origin = request.headers.get("Origin")
        if not origin:
            # Not a browser, or a browser that had no reason to say. Either
            # way there is no ambient authority to abuse.
            return await call_next(request)

        origin_host = _origin_host(origin)
        if origin_host and (
            origin_host == (request.headers.get("Host") or "").lower()
            or origin_host in self._allowed
        ):
            return await call_next(request)

        _LOGGER.warning(
            "Refused %s %s from origin %s",
            request.method,
            request.url.path,
            origin,
        )
        return JSONResponse(
            status_code=403,
            content={
                "detail": "This request came from another site and was refused.",
                "code": "cross_site_request",
            },
        )
