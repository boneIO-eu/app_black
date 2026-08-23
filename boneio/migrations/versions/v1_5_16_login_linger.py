"""BoneIO 1.5.16 — keep the user manager alive so SSH logins are not slow.

``user@1000.service`` takes about 4.1 s to start on an AM335x. Without
lingering, systemd stops it once the last session closes, so every SSH login
after a gap pays that cost again.

Measured on the controller:

    login, user manager cold   6889 ms
    login, user manager warm   2715 ms

The remainder of a warm login is TCP plus key exchange (0.74 s), yescrypt
password verification (0.67 s) and PAM/logind session setup.

Lingering is enabled by the presence of an empty marker file at
``/var/lib/systemd/linger/<user>`` — the same thing ``loginctl enable-linger``
creates. Installing the marker directly avoids adding another root-privileged
action to the migration helper.

Trade-off: the user manager now also starts at boot. Nothing waits for it, so it
is not on boneIO's critical path — it only competes for CPU, and boneIO runs at
CPUWeight=1000 against its default 100.

Revert with: loginctl disable-linger boneio
"""

from __future__ import annotations

from boneio.migrations.actions import (
    InstallFile,
    MigrationAction,
)

VERSION = "1.5.16"
DESCRIPTION = "Enable user lingering so SSH login drops from ~6.9s to ~2.7s"
REQUIRES_ROOT = True

_BONEIO_USER = "boneio"


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions for version 1.5.16.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    return [
        InstallFile(
            src="systemd/linger-marker",
            dst=f"/var/lib/systemd/linger/{_BONEIO_USER}",
            mode=0o644,
        ),
    ]
