"""Take the ``boneio`` account out of the ``docker`` group.

Membership of ``docker`` is membership of root, without a password and without
a sudo rule: the daemon starts containers as root, and anyone who can reach its
socket can ask it for one with the host filesystem mounted. No amount of
narrowing elsewhere matters while that is true — it is a way around every
helper in this series, available to whoever holds the shared account password.

It is the last step rather than the first because the application genuinely
needed it. Container management now goes through ``boneio-containers``, whose
vocabulary is closed and whose compose file is root-owned, so the group buys
nothing that boneIO still uses. The helper checks that for itself before it
removes anything: a plan cannot assert that the replacement is installed, only
the device can see whether it is.

What is deliberately **not** removed is the ``admin`` group. It comes from the
stock BeagleBone image, not from boneIO, and it is the operator's own way to a
root shell over SSH — password-gated, unlike ``docker``. Taking it away would
leave a controller in a cabinet whose only repair path is a serial console or
the SD card, to close a hole that already requires the account password.

To retry on a device, delete ``/var/lib/boneio/migrations.d/1.6.11.applied``
and restart boneIO.
"""

from __future__ import annotations

from boneio.migrations.actions import MigrationAction, RemoveFromGroup

VERSION = "1.6.11"
DESCRIPTION = "Remove the boneio account from the docker group"
REQUIRES_ROOT = True


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    return [RemoveFromGroup(account="boneio", group="docker")]
