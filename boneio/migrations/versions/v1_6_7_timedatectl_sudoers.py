"""Install the timedatectl sudoers rule through the system channel.

The rule that lets boneIO set the timezone used to be created by
``POST /api/timezone/sudoers/fix``, which accepted the operator's sudo password
over HTTP. The pentest report lists that as a way to intercept the password, and
the password for this account is shared across every controller — so an
endpoint that asks for it is worth removing even though it never stored it.

Migrations already have a privileged channel that needs no password, so the file
belongs here. The endpoint is gone; the read-only check that reports whether the
rule is present stays, and now tells the operator to apply pending migrations
rather than asking them to type a password into a web page.

To retry on a device, delete ``/var/lib/boneio/migrations.d/1.6.7.applied`` and
restart boneIO.
"""

from __future__ import annotations

from boneio.migrations.actions import InstallFile, MigrationAction

VERSION = "1.6.7"
DESCRIPTION = "Install the timedatectl sudoers rule (no password over the API)"
REQUIRES_ROOT = True


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    return [
        InstallFile(
            src="sudoers/boneio-timedatectl",
            dst="/etc/sudoers.d/boneio-timedatectl",
            mode=0o440,
            owner="root",
            group="root",
            # A bad sudoers fragment can lock out every privileged operation,
            # so it is checked before it is moved into place.
            validate_cmd="visudo -cf",
            validate="sudoers",
        ),
    ]
