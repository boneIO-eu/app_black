"""Let the operator point the clock at an NTP server on their own network.

Until now the only choice the web UI offered was NTP on or off, which meant the
distribution's public pool or nothing. Installations that sit behind a firewall
with no route to the internet were left with a clock that never synchronises —
and on this board that is not cosmetic: the BeagleBone has no battery-backed
RTC, so after a power cut it boots with a meaningless date until something
tells it otherwise. Anything scheduled against local time is wrong until then.

The servers are written to a systemd-timesyncd drop-in by ``boneio-system``,
which gains two verbs for it. The helper is reinstalled here because its
vocabulary changed; nothing else about the trust arrangement does. Validation
of the server names happens inside the helper, not in the application: the value
ends up in a file systemd parses as root, so a space or a newline in it would be
a way to append directives, and the check for that belongs on the root side of
the boundary.

To retry on a device, delete ``/var/lib/boneio/migrations.d/1.6.9.applied`` and
restart boneIO.
"""

from __future__ import annotations

from boneio.migrations.actions import InstallFile, MigrationAction

VERSION = "1.6.9"
DESCRIPTION = "Allow a local NTP server to be configured from the web UI"
REQUIRES_ROOT = True

TRUSTED_DIR = "/usr/lib/boneio/trusted"


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions.

    Only the helper changes. The sudoers fragment already names
    ``/usr/sbin/boneio-system`` and says nothing about its verbs, so adding two
    does not widen what the service account may run — which is the whole point
    of a helper with a closed vocabulary rather than a wildcard rule.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    return [
        # Pristine copy first, as in 1.6.8: boneio-helpers-heal.service restores
        # from here, and a heal that puts back a helper without the new verbs
        # would silently undo this migration.
        InstallFile(
            src="helpers/boneio-system",
            dst=f"{TRUSTED_DIR}/boneio-system",
            mode=0o755,
            owner="root",
            group="root",
        ),
        InstallFile(
            src="helpers/boneio-system",
            dst="/usr/sbin/boneio-system",
            mode=0o755,
            owner="root",
            group="root",
            validate_cmd="python3 -m py_compile",
            validate="python",
        ),
    ]
