"""Reinstall boneio-system, which can now set the SSH login password once.

Images before 1.6 shipped the ``boneio`` account with the password ``Black``,
the same on every unit and published. That account carries a password-gated
``(ALL:ALL) ALL``, so its password is the root password — and expiring it, as
1.6 images first did, only forced a change on whoever logged in first, which
need not be the owner.

Images from here on ship the account locked, and the owner's first password,
typed into the first-run wizard, becomes it. That needs two operations in the
privileged helper:

  service-password-state  read-only: locked, empty, shipped, set
  service-password-init   set it from stdin — once, and only while the
                          account is locked, on the shipped password, or has
                          none

The limits are what keep this from reopening F-04. The helper runs as root for
anyone holding ``boneio``; an operation that set that account's password
whenever asked would be a way to root in two steps. In the states it allows,
whoever holds the account either has no password to replace or already has
root through the one everybody knows. A password the owner chose is refused,
and a root-owned flag makes the operation once-only even if somebody locks the
account again later.

The pristine copy goes first for the same reason as in 1.6.16:
``boneio-helpers-heal.service`` restores from it, and a stale one would put the
old helper back at the next boot. ``validate="python"`` because a helper that
does not compile would take CAN, the overlay, the hostname, NTP and the broker
passwords down with it.

A device already in the field keeps whatever SSH password it has. The security
section says so when that is still ``Black``.

To retry on a device, delete ``/var/lib/boneio/migrations.d/1.6.17.applied``
and restart boneIO.
"""

from __future__ import annotations

from boneio.migrations.actions import InstallFile, MigrationAction

VERSION = "1.6.17"
DESCRIPTION = "Let the first-run wizard set the SSH login password, once"
REQUIRES_ROOT = True

TRUSTED_DIR = "/usr/lib/boneio/trusted"


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    return [
        InstallFile(
            src="helpers/boneio-system",
            dst=f"{TRUSTED_DIR}/boneio-system",
            mode=0o755,
            owner="root",
            group="root",
            validate="python",
        ),
        InstallFile(
            src="helpers/boneio-system",
            dst="/usr/sbin/boneio-system",
            mode=0o755,
            owner="root",
            group="root",
            validate="python",
        ),
    ]
