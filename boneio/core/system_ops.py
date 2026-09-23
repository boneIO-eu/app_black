"""Privileged system operations, through the named-operation helper.

CAN interface setup, the device-tree overlay and the hostname all needed root.
They got it by asking the operator for their system password over HTTP, or by
leaning on wildcard sudo rules — ``ip link set can0 *`` and a ``sed -i``
expression this process composed and root executed.

``boneio-system`` replaces both. Every argument is checked against a closed set
inside the helper, so nothing here can widen what runs as root, and no password
is involved: the sudoers rule is NOPASSWD precisely because the vocabulary is
fixed.

When the helper is not installed yet these operations report that rather than
falling back to the old path. Unlike container management, where a fallback
keeps a pre-migration device working, falling back here would mean keeping the
password prompt and the wildcard rules alive — which is the thing being removed.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import dataclass

_LOGGER = logging.getLogger(__name__)

HELPER_PATH = "/usr/sbin/boneio-system"

_NOT_INSTALLED = (
    f"{HELPER_PATH} is not installed. This operation used to ask for your "
    "system password; it now goes through a privileged helper installed by a "
    "system migration. Apply the pending system migrations and try again."
)


@dataclass
class Result:
    """Outcome of a privileged system operation.

    Attributes:
        returncode: Process exit status.
        stdout: Captured standard output.
        stderr: Captured standard error.
    """

    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        """Whether the operation succeeded."""
        return self.returncode == 0

    def json(self) -> dict | None:
        """Parse the output as a JSON object.

        Returns:
            The parsed output, or None when it is not JSON.
        """
        try:
            parsed = json.loads(self.stdout.strip())
        except ValueError:
            return None
        return parsed if isinstance(parsed, dict) else None


_available: bool | None = None


def helper_available(recheck: bool = False) -> bool:
    """Whether ``boneio-system`` is installed and callable without a password.

    Args:
        recheck: Ask again instead of reusing the cached answer.

    Returns:
        True when the helper can be used.
    """
    global _available
    if _available is not None and not recheck:
        return _available

    if not (os.path.isfile(HELPER_PATH) and os.access(HELPER_PATH, os.X_OK)):
        _available = False
        return False
    try:
        result = subprocess.run(
            ["sudo", "-n", HELPER_PATH, "--list-verbs"],
            capture_output=True, text=True, timeout=20,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        _LOGGER.warning("boneio-system is present but not callable: %s", exc)
        _available = False
        return False
    _available = result.returncode == 0
    return _available


def run(
    verb: str, *arguments: str, timeout: int = 60, stdin: str | None = None
) -> Result:
    """Perform one named system operation.

    Args:
        verb: One of the helper's verbs.
        *arguments: Its arguments; the helper validates them.
        timeout: Seconds to allow.
        stdin: Text to feed the helper. Used for secrets, which must not travel
            as arguments — the process table is readable by every local account.

    Returns:
        The outcome.
    """
    if not helper_available():
        return Result(1, "", _NOT_INSTALLED)

    argv = ["sudo", "-n", HELPER_PATH, verb, *(str(a) for a in arguments)]
    # argv only, never stdin: that is where the secrets are.
    _LOGGER.info("system operation: %s", " ".join(argv[3:]))
    try:
        completed = subprocess.run(
            argv, input=stdin, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return Result(1, "", f"timed out after {timeout}s")
    except OSError as exc:
        return Result(1, "", str(exc))

    if completed.returncode != 0:
        _LOGGER.warning(
            "system operation %s failed (rc=%d): %s",
            verb, completed.returncode, completed.stderr.strip(),
        )
    return Result(completed.returncode, completed.stdout or "", completed.stderr or "")


def can_up(interface: str, bitrate: int, timeout: int = 60) -> Result:
    """Bring a CAN interface up at *bitrate*."""
    return run("can-up", interface, bitrate, timeout=timeout)


def can_down(interface: str, timeout: int = 30) -> Result:
    """Take a CAN interface down."""
    return run("can-down", interface, timeout=timeout)


def can_restart(interface: str, timeout: int = 30) -> Result:
    """Bring a CAN controller out of bus-off, keeping its bitrate."""
    return run("can-restart", interface, timeout=timeout)


def overlay_get(timeout: int = 30) -> Result:
    """Read the device-tree overlay configured in uEnv.txt."""
    return run("overlay-get", timeout=timeout)


def overlay_set(overlay: str, timeout: int = 30) -> Result:
    """Point uEnv.txt at one of the shipped overlays."""
    return run("overlay-set", overlay, timeout=timeout)


def mqtt_password(account: str, password: str, timeout: int = 60) -> Result:
    """Set a broker password for one of the managed accounts.

    The password goes over stdin. The rule this replaces passed it to
    ``mosquitto_passwd -b`` as an argument, where ``ps`` could read it for as
    long as the command ran.

    Args:
        account: ``boneio``, ``homeassistant`` or ``mqtt``.
        password: The new password.
        timeout: Seconds to allow.

    Returns:
        The outcome.
    """
    return run("mqtt-password", account, timeout=timeout, stdin=f"{password}\n")


def service_password_state(timeout: int = 30) -> str | None:
    """How the boneio login stands: locked, empty, shipped, set or unknown.

    Returns:
        The state, or None when the helper is not there to ask.
    """
    result = run("service-password-state", timeout=timeout)
    if not result.ok:
        return None
    parsed = result.json() or {}
    state = parsed.get("state")
    return state if isinstance(state, str) else None


def service_password_init(password: str, timeout: int = 60) -> Result:
    """Set the boneio login password, once.

    The helper allows this only while the account is still in a state the
    factory left — locked, on the shipped password, or with none — and only the
    first time. Anything else is the owner's password, and changing it is
    theirs to do with ``passwd``. The password goes over stdin, never as an
    argument.

    Args:
        password: The password the owner chose.
        timeout: Seconds to allow.

    Returns:
        The outcome.
    """
    return run("service-password-init", timeout=timeout, stdin=f"{password}\n")


def mqtt_reload(timeout: int = 30) -> Result:
    """Have the broker re-read its password file."""
    return run("mqtt-reload", timeout=timeout)


def hostname_set(name: str, timeout: int = 30) -> Result:
    """Set the system hostname."""
    return run("hostname-set", name, timeout=timeout)


def ntp_get(timeout: int = 30) -> Result:
    """Read the NTP servers boneIO has configured, as JSON on stdout."""
    return run("ntp-get", timeout=timeout)


def ntp_set(servers: list[str], timeout: int = 60) -> Result:
    """Point systemd-timesyncd at *servers*; an empty list restores the defaults.

    The list is joined and passed through without being trusted here. Each entry
    is validated inside the helper, because that is the side of the boundary
    where it matters: the value is written into a file systemd parses as root.
    """
    return run("ntp-set", ",".join(servers) if servers else "default", timeout=timeout)
