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


def run(verb: str, *arguments: str, timeout: int = 60) -> Result:
    """Perform one named system operation.

    Args:
        verb: One of the helper's verbs.
        *arguments: Its arguments; the helper validates them.
        timeout: Seconds to allow.

    Returns:
        The outcome.
    """
    if not helper_available():
        return Result(1, "", _NOT_INSTALLED)

    argv = ["sudo", "-n", HELPER_PATH, verb, *(str(a) for a in arguments)]
    _LOGGER.info("system operation: %s", " ".join(argv[3:]))
    try:
        completed = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout
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


def overlay_get(timeout: int = 30) -> Result:
    """Read the device-tree overlay configured in uEnv.txt."""
    return run("overlay-get", timeout=timeout)


def overlay_set(overlay: str, timeout: int = 30) -> Result:
    """Point uEnv.txt at one of the shipped overlays."""
    return run("overlay-set", overlay, timeout=timeout)


def hostname_set(name: str, timeout: int = 30) -> Result:
    """Set the system hostname."""
    return run("hostname-set", name, timeout=timeout)
