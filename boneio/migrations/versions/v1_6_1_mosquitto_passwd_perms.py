"""BoneIO 1.6.1 — take the MQTT password database out of world-read.

``/etc/mosquitto/passwd`` shipped world-readable (F-11). On the controller used
for testing it was mode 704 — ``rwx---r--`` — so every local account could read
the hashes for boneio, homeassistant and mqtt, and an offline crack against
them needs no further access.

0640 root:mosquitto is what the file needs: the broker runs as ``mosquitto``
and reads it through the group, and nobody else has any business in it. The
image creates it correctly from now on; this repairs the controllers already in
the field, which the image cannot reach.

It corrects permissions rather than installing a file, because the contents are
the device's own — replacing them would wipe whatever passwords the owner has
set.
"""

from __future__ import annotations

from boneio.migrations.actions import MigrationAction, SetFilePermissions, SystemctlReload

VERSION = "1.6.1"
DESCRIPTION = "Restrict /etc/mosquitto/passwd to the broker (F-11)"
REQUIRES_ROOT = True


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions for version 1.6.1.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    return [
        SetFilePermissions(
            path="/etc/mosquitto/passwd",
            mode=0o640,
            owner="root",
            group="mosquitto",
        ),
        # The broker keeps its open file handle, so this is belt and braces —
        # but a reload costs nothing and guarantees it is reading the file it
        # now has permission to read.
        SystemctlReload(unit="mosquitto"),
    ]
