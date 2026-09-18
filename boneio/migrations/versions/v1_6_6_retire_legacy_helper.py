"""Remove the migration helper that accepts a plan from the caller.

This is where F-04 actually closes. Installing the replacement (1.6.5)
does not close it: as long as ``/usr/sbin/boneio-migrate`` exists with its
NOPASSWD rule, the old path is still there to be used, and nothing stops the
application — or anyone holding the ``boneio`` account — from calling it with a
plan of their choosing.

It is a separate migration from the pivot on purpose. The runner applies this
one only after ``boneio-migrate-v2 --selftest`` has returned zero, and it sends
it *through v2*, so the old helper never removes itself using the very path
being closed. A device where the selftest fails keeps the old helper, keeps
migrating, and reports the hardening as unfinished — worse than hardened, but
far better than a controller in a cabinet whose migration channel died quietly.

What remains after this:

  * The ``docker`` group, which is root-equivalent, and the ``admin`` group,
    which carries a password-gated ``(ALL:ALL) ALL`` from the stock BeagleBone
    image. Those come last (1.6.7), after the operations that need them have
    moved to ``boneio-containers``.
  * A device compromised *before* this update. An attacker with root already
    can replace both anchors locally, and no in-place update can bootstrap
    trust on a machine that is already owned.

To retry on a device, delete ``/var/lib/boneio/migrations.d/1.6.6.applied`` and
restart boneIO.
"""

from __future__ import annotations

from boneio.migrations.actions import MigrationAction, RemoveFile

VERSION = "1.6.6"
DESCRIPTION = "Retire the legacy migration helper"
REQUIRES_ROOT = True


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions.

    The sudoers rule goes first. If the run were interrupted between the two,
    a leftover rule naming a helper that no longer exists is harmless, whereas
    a leftover helper whose rule is gone would still be reachable by anyone who
    can obtain the shared account password.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    return [
        RemoveFile(path="/etc/sudoers.d/boneio-migrate"),
        RemoveFile(path="/usr/sbin/boneio-migrate"),
    ]
