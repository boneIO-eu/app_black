"""Let boneIO read /etc/boneio again.

The image build and the first-boot MQTT setup created /etc/boneio with mode
0700 when they wrote the boneIO account's MQTT password there. boneIO, running
as ``boneio``, then could not look inside, and the proxy markers live there:
``proxy-native`` read as absent, so a controller on the packaged Caddy was
taken for one on the container, and ``proxy-cloud`` too, so turning cloud
registration on never reported the new address as served and the first-run
wizard gave up after three minutes.

The secret is the file, which stays 0600; the directory goes back to 0755.

To retry on a device, delete ``/var/lib/boneio/migrations.d/1.6.45.applied``
and restart boneIO.
"""

from __future__ import annotations

from boneio.migrations.actions import MigrationAction, SetFilePermissions

VERSION = "1.6.45"
DESCRIPTION = "/etc/boneio readable by boneIO; the MQTT password stays root-only"
REQUIRES_ROOT = True


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions for version 1.6.45.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    return [SetFilePermissions(path="/etc/boneio", mode=0o755, owner="root", group="root")]
