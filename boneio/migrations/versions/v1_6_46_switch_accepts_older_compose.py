"""The switch to the packaged Caddy accepts a compose file from before 1.6.15.

``boneio-containers`` refuses to replace a compose file that is not one of its
templates, so that a file somebody edited is not thrown away. It compared them
verbatim. Migration 1.6.15 added two variables (and comments) to the templates
and deliberately left the live file alone, so every controller installed
before it — whose port and cloud mode nobody changed since — kept a file that
no template matched. Its switch was refused at the preconditions ("is not one
of the Caddy templates"), every attempt, and the panel showed the attempts
used up.

The helper now compares what decides what runs: comments, blank lines and the
two variables 1.6.15 added are left out. A file with anything else changed is
still refused. It goes to the pristine copy as well, so
``boneio-helpers-heal.service`` does not put the strict one back.

To retry on a device, delete ``/var/lib/boneio/migrations.d/1.6.46.applied``
and restart boneIO.
"""

from __future__ import annotations

from boneio.migrations.actions import InstallFile, MigrationAction

VERSION = "1.6.46"
DESCRIPTION = "The Caddy switch accepts compose files from before 1.6.15"
REQUIRES_ROOT = True


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions for version 1.6.46.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    return [
        InstallFile(
            src="helpers/boneio-containers", dst=dst, mode=0o755,
            owner="root", group="root", validate="python",
        )
        for dst in ("/usr/lib/boneio/trusted/boneio-containers", "/usr/sbin/boneio-containers")
    ]
