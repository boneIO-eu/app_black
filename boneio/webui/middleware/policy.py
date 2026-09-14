"""Which role may make which request.

Kept apart from the middleware so the policy can be read, reviewed and tested as
a table rather than inferred from control flow — an access-control rule that is
hard to read is a rule nobody audits.

The model is deliberately asymmetric, because "read" and "write" are not the
right axis on a controller:

* An **admin** may do anything.
* A **viewer** may look at the device and *operate* it — flip an output, move a
  cover, run an irrigation zone — but may not *configure* it, restart it, or
  touch accounts. Operating is what the role is for; a viewer who cannot press
  a button is just a dashboard.
* Reads are allowed for a viewer except where the response is a credential
  carrier (config archives bundle ``secrets.yaml``; the raw file editor and the
  account routes speak for themselves).

Anything not named here needs admin, so a new route is locked down by default
and opening it up is a deliberate edit to this file.
"""

from __future__ import annotations

import re

from boneio.core.auth.models import Role

# Reachable with no token at all. The onboarding routes are open because a
# device with no account has nothing to authenticate against; they guard
# themselves by refusing once an admin exists.
_EXEMPT_PATHS = frozenset(
    {"/api/login", "/api/auth/required", "/api/version", "/api/init"}
)
_EXEMPT_PREFIXES = ("/api/onboarding",)

# Methods that only read.
_READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# Reads that still require an admin.
#
# The config archive routes are here because the tar they build globs *.yaml out
# of the config directory, which includes secrets.yaml — so "download a backup"
# is a credential read, whatever the HTTP verb says. The raw file editor and the
# account routes are self-evident.
_ADMIN_ONLY_READ_PREFIXES = (
    "/api/files",
    "/api/accounts",
    "/api/config/download",
    "/api/config/backups",
    "/api/caddy",
    "/api/nodered",
)

# Writes a viewer may perform: operating the device, never configuring it.
#
# Each entry binds a method to an anchored path pattern. The method matters:
# matching on the path alone would hand a viewer any verb someone later adds
# under an operating route — a DELETE on /api/outputs/{id}/toggle would be
# granted by a path-only rule even though nobody intended it.
#
# Deliberately absent: anything under /api/config, /api/system, /api/files,
# Modbus register writes (they can reconfigure an attached inverter), device
# discovery (it reaches out to the network), Node-RED, Caddy, CAN, migrations
# and updates.
_VIEWER_WRITES: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (method, re.compile(pattern))
    for method, pattern in (
        # Outputs and groups
        ("POST", r"^/api/outputs/[^/]+/(toggle|turn_on|turn_off|set_duration|set_brightness)$"),
        ("POST", r"^/api/groups/[^/]+/toggle$"),
        # Covers
        ("POST", r"^/api/covers/[^/]+/(action|set_position|set_tilt)$"),
        # Irrigation: running and skipping, but not settings or import
        ("POST", r"^/api/irrigation/[^/]+/command$"),
        ("POST", r"^/api/irrigation/[^/]+/zone/[^/]+/command$"),
        ("POST", r"^/api/irrigation/[^/]+/schedule/[^/]+/skip$"),
        # Climate and alarm entities
        ("POST", r"^/api/templates/thermostats/[^/]+/temperature$"),
        ("POST", r"^/api/templates/alarms/[^/]+/command$"),
        # Remote (ESPHome/WLED) entities already configured on the device
        ("POST", r"^/api/remote-devices/[^/]+/(output|cover)/[^/]+/action$"),
        # Reads the Modbus UI performs over POST because they carry a body.
        ("POST", r"^/api/modbus/get$"),
        # Self-service only: changing your OWN password, which asks for the
        # current one. Managing other accounts lives under /api/accounts
        # (plural) and stays admin-only.
        ("PUT", r"^/api/account/password$"),
    )
)


def is_exempt(path: str) -> bool:
    """Report whether a path needs no authentication at all.

    Args:
        path: Request path.

    Returns:
        True if the route is reachable without a token.
    """
    return path in _EXEMPT_PATHS or path.startswith(_EXEMPT_PREFIXES)


def is_api_path(path: str) -> bool:
    """Report whether a path is part of the API surface.

    Args:
        path: Request path.

    Returns:
        True for API routes; static assets and the SPA are not gated.
    """
    return path.startswith("/api")


def required_role(method: str, path: str) -> Role:
    """The least privileged role allowed to make this request.

    Args:
        method: HTTP method.
        path: Request path, without the query string.

    Returns:
        Role.VIEWER if a read-only account may do it, Role.ADMIN otherwise.
    """
    if method.upper() in _READ_METHODS:
        if path.startswith(_ADMIN_ONLY_READ_PREFIXES):
            return Role.ADMIN
        return Role.VIEWER

    method = method.upper()
    if any(
        method == allowed_method and pattern.match(path)
        for allowed_method, pattern in _VIEWER_WRITES
    ):
        return Role.VIEWER

    return Role.ADMIN


def role_allows(role: Role, method: str, path: str) -> bool:
    """Whether an account with this role may make this request.

    Args:
        role: Role carried by the caller's token.
        method: HTTP method.
        path: Request path.

    Returns:
        True if the request is permitted.
    """
    if role is Role.ADMIN:
        return True
    return required_role(method, path) is Role.VIEWER
