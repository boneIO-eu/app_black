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
  account routes speak for themselves), or where the "read" reaches into the
  hardware — the diagnostics bus scans take buses away from the running
  integrations, whatever the HTTP verb says.

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
    "/api/nodered",
    # A list of what is still unlocked is a shopping list for anyone who
    # should not have it.
    "/api/security",
    # Which CA the device trusts and which certificate it presents.
    "/api/mqtt-tls",
    # The switch log names paths, packages and why a step failed.
    "/api/proxy",
    # The bundle is the whole configuration and the device log in one file.
    "/api/diagnostics",
    # The rest of the Diagnostics page. Its bus scans are not passive reads:
    # the Modbus helper pauses the polling loop to take the bus, so a viewer
    # who opens the page to look around can leave Modbus stopped behind them.
    # The device log is withheld for a second reason — it carries the serial
    # number, which /api/version and /api/init keep from a caller who is not
    # an admin, and the scrubber on the way out only removes values it can
    # read out of secrets.yaml.
    "/api/logs",
    "/api/i2c",
    "/api/can",
    # Which expanders and sensors failed to start, and on which address.
    "/api/hardware",
    # Recovery mode (boneio.webui.recovery): the error, the raw config files
    # and the log, served while the controller cannot start normally.
    "/api/recovery",
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
        # An on-demand read of the on-board power monitor: a POST only because
        # it touches the bus and publishes, it changes nothing.
        ("POST", r"^/api/sensors/ina/refresh$"),
        # Self-service only: changing your OWN password, which asks for the
        # current one. Managing other accounts lives under /api/accounts
        # (plural) and stays admin-only.
        ("PUT", r"^/api/account/password$"),
        # Confirming your own password for a request that asks for it. Any
        # role, since it grants nothing the account does not already have.
        ("POST", r"^/api/auth/confirm$"),
    )
)

# Requests that want the password again, not just a valid token.
#
# A login token lives for weeks, on whatever device it was left on. That is
# the right trade for looking at the device and operating it, and the wrong one
# for what cannot be walked back: who has an account, what configuration the
# device runs, which software it runs, and what certificate vouches for it. For
# these the middleware wants a token issued within REAUTH_WINDOW of the owner
# typing the password, and asks for it with 403 ``reauth_required`` otherwise.
#
# Deliberately absent: restart and reboot (they undo themselves), the file
# editor and the section saves (everyday configuration work, and asking for a
# password on every save would train people to type it without reading), and
# checking for updates, which changes nothing.
#
# Every entry is matched against the application's real routes in
# test_reauth.py, so a typo here fails a test instead of quietly guarding
# nothing.
_REAUTH_WRITES: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (method, re.compile(pattern))
    for method, pattern in (
        # Accounts: creating one is how a borrowed session makes itself
        # permanent, since a second admin survives a password change.
        ("POST", r"^/api/accounts$"),
        ("DELETE", r"^/api/accounts/[^/]+$"),
        ("PUT", r"^/api/accounts/[^/]+/role$"),
        ("PUT", r"^/api/accounts/[^/]+/password$"),
        # The SSH login's password is the root password, through sudo. The
        # form asks for the current one too, but that is the SSH password and
        # this is the owner proving the session is theirs.
        ("PUT", r"^/api/accounts/ssh-password$"),
        # Replacing the whole configuration.
        ("POST", r"^/api/config/restore$"),
        ("POST", r"^/api/config/restore_backup$"),
        ("POST", r"^/api/factory_reset$"),
        ("POST", r"^/api/factory_reset/partial$"),
        ("POST", r"^/api/factory_reset/restore_backup$"),
        # Node-RED flows are code, so restoring them is installing software.
        ("POST", r"^/api/nodered/backup/restore$"),
        ("POST", r"^/api/nodered/backup/upload_restore$"),
        # Changing the software: an application update can also be a
        # downgrade to a release with holes this one closed.
        ("POST", r"^/api/update$"),
        ("POST", r"^/api/update/rollback$"),
        ("POST", r"^/api/os-update/upgrade$"),
        ("POST", r"^/api/os-update/autoupdate$"),
        ("POST", r"^/api/os-update/caddy/apply$"),
        # Moving Caddy from the container to the package replaces what serves
        # the panel, so it is software change like the Caddy image apply.
        ("POST", r"^/api/proxy/switch$"),
        # The certificate the panel is served with.
        ("POST", r"^/api/security/certificate$"),
        ("DELETE", r"^/api/security/certificate$"),
        # Whom boneIO trusts as its broker, and what it presents to one.
        ("POST", r"^/api/mqtt-tls/client/(ca|certificate)$"),
        ("DELETE", r"^/api/mqtt-tls/client/[^/]+$"),
        # What the broker here presents, and whether it still takes plain text.
        ("POST", r"^/api/mqtt-tls/broker/(certificate|generate)$"),
        ("PUT", r"^/api/mqtt-tls/broker/mode$"),
        ("DELETE", r"^/api/mqtt-tls/broker/certificate$"),
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


def requires_recent_auth(method: str, path: str) -> bool:
    """Whether this request wants the password confirmed, not just a token.

    Args:
        method: HTTP method.
        path: Request path, without the query string.

    Returns:
        True if the caller must have typed the password recently.
    """
    method = method.upper()
    return any(
        method == wanted_method and pattern.match(path)
        for wanted_method, pattern in _REAUTH_WRITES
    )
