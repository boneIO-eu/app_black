"""Response security headers (F-13).

Before 1.6 the app sent only ``X-Content-Type-Options`` and ``Referrer-Policy``.
This adds the rest, with two deliberate departures from the obvious answer.

**No X-Frame-Options.** The panel has to be embeddable in a Home Assistant
ingress iframe, and X-Frame-Options cannot express "this one other origin".
Its modern replacement, CSP ``frame-ancestors``, can — so framing policy is a
config option (``web.security.frame_ancestors``) rather than a header nailed
shut here. It is unset by default, which keeps today's behaviour: turning it on
without knowing how a given installation embeds the panel would break that
installation's dashboard.

**A short HSTS max-age.** A browser ignores HSTS arriving over a connection it
could not verify, so sending it on a self-signed setup is harmless. What is not
harmless is a year-long pin: a device that has cloud registration on today has
a real certificate, and if that is later switched off the same hostname falls
back to self-signed, which the browser would then refuse with no way to click
through. A day is long enough to matter and short enough to recover from.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response

#: Kept deliberately permissive where the app genuinely needs it, so that the
#: policy can actually ship rather than being switched off the first time the
#: YAML editor breaks. 'unsafe-inline' for scripts is required because a
#: reverse proxy injects window.__BONEIO_BASE_PATH__ as an inline script, and
#: blob: workers are how the Monaco editor runs.
_CSP_DIRECTIVES = (
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    "connect-src 'self' ws: wss:",
    "worker-src 'self' blob:",
    # Real wins with no compatibility cost: nothing here embeds plugins,
    # rewrites its own base URI, or posts a form off-site.
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
)

#: Features the panel never uses. Denying them means a compromised page cannot
#: reach for them either.
_PERMISSIONS_POLICY = ", ".join(
    f"{feature}=()"
    for feature in (
        "accelerometer",
        "camera",
        "geolocation",
        "gyroscope",
        "magnetometer",
        "microphone",
        "payment",
        "usb",
    )
)

#: One day. See the module docstring for why this is not a year.
HSTS_MAX_AGE = 86400


def build_csp(frame_ancestors: str | None = None) -> str:
    """Assemble the Content-Security-Policy header value.

    Args:
        frame_ancestors: Value for the frame-ancestors directive, or None to
            omit it and leave framing unrestricted.

    Returns:
        The header value.
    """
    directives = list(_CSP_DIRECTIVES)
    if frame_ancestors:
        directives.append(f"frame-ancestors {frame_ancestors}")
    return "; ".join(directives)


def apply_security_headers(
    request: Request, response: Response, frame_ancestors: str | None = None
) -> None:
    """Set the security headers on an outgoing response.

    Args:
        request: The request being answered, used to tell HTTPS from HTTP.
        response: Response to annotate, modified in place.
        frame_ancestors: Optional CSP frame-ancestors value.
    """
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = build_csp(frame_ancestors)
    response.headers["Permissions-Policy"] = _PERMISSIONS_POLICY

    # Only meaningful over TLS. A proxy terminating TLS tells us via
    # X-Forwarded-Proto; browsers ignore the header from an unverified
    # connection, so a self-signed setup neither gains nor suffers from it.
    forwarded = request.headers.get("X-Forwarded-Proto", "").split(",")[0].strip()
    scheme = forwarded or request.url.scheme
    if scheme == "https":
        response.headers["Strict-Transport-Security"] = f"max-age={HSTS_MAX_AGE}"
