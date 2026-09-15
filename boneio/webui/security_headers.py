"""Response security headers (F-13).

Before 1.6 the app sent only ``X-Content-Type-Options`` and ``Referrer-Policy``.
This adds the rest, with two deliberate departures from the obvious answer.

**No X-Frame-Options.** The panel has to be embeddable in a Home Assistant
ingress iframe, and X-Frame-Options cannot express "this one other origin".
Its modern replacement, CSP ``frame-ancestors``, can — so framing policy is a
config option (``web.security.frame_ancestors``) rather than a header nailed
shut here.

It is a list of plain tokens — ``self``, or an address — which this module
quotes the way CSP requires; see :mod:`boneio.core.security.framing` for why
the config does not hold the directive verbatim. It defaults to ``self``,
which is both the secure answer and the one the boneIO Black Home Assistant
add-on needs. The add-on's nginx *proxies* each
device (``proxy_pass https://<device>:8443``) and the dashboard frames a path
on Home Assistant's own origin, so the framed document and the page framing it
share an origin — ``'self'`` permits exactly that while refusing a page on any
other site.

The setup this does break is a dashboard pointing an iframe card or
``panel_iframe`` straight at ``https://<device>:8443``: there the framed
document is on the device's origin and Home Assistant's is a different one.
Such an install adds its Home Assistant origin alongside ``self``, which the
Security section offers as a field. ``*`` turns the restriction off entirely
for anyone who needs that.

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

# The framing policy is a list of plain tokens in config.yaml; core turns it
# into the directive, so the security check and this header cannot drift apart
# about what a given configuration actually does.
from boneio.core.security import framing

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


def build_csp(frame_ancestors: object = None) -> str:
    """Assemble the Content-Security-Policy header value.

    Args:
        frame_ancestors: ``web.security.frame_ancestors`` as config.yaml holds
            it — a list of plain tokens, or the single string earlier versions
            wrote. None means the device has not been configured and the secure
            default applies; ``["*"]`` lifts the restriction deliberately.

    Returns:
        The header value.
    """
    directives = list(_CSP_DIRECTIVES)
    tokens = framing.effective(frame_ancestors)
    directives.append(f"frame-ancestors {framing.to_csp(tokens)}")
    return "; ".join(directives)


def apply_security_headers(
    request: Request, response: Response, frame_ancestors: object = None
) -> None:
    """Set the security headers on an outgoing response.

    Args:
        request: The request being answered, used to tell HTTPS from HTTP.
        response: Response to annotate, modified in place.
        frame_ancestors: Configured frame_ancestors value, or None for the
            default. See :func:`build_csp`.
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
