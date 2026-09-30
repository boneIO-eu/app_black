"""Reinstall boneio-system: the SSH password can be changed from the panel.

Since 1.6.17 the first-run wizard copies the owner's first password onto the
``boneio`` login, once. After that the panel password and the SSH password are
separate, and the only way to change the second was ``passwd`` over SSH.

boneio-system gains ``service-password-change``: the current password and the
new one on stdin, never as arguments, for the fixed ``boneio`` account. It is
``passwd`` run as root, and it has to be no more than that. That account carries
a password-gated ``(ALL:ALL) ALL`` and this helper runs without a password for
anyone holding it, so the verb:

  - checks the current password against /etc/shadow, through libcrypt, and
    changes nothing without it. Whoever knows it can already sudo;
  - refuses while the account is locked or has no password. Those are
    ``service-password-init``'s states, and here they would be a way to set
    the password without knowing one;
  - counts wrong passwords in ``/var/lib/boneio/service-password-change.json``,
    root-only in a root-owned directory: five in fifteen minutes and it
    refuses even the right one until the oldest ages out, and each wrong one
    costs two seconds. The count is global — the helper can be called without
    the panel — and it is written before the password is checked, under a
    lock, so parallel or killed calls still pay for their tries.

A lost SSH password still means the flasher card (``BONEIO_RESET_ACCOUNTS=1``);
nothing here sets it without the current one.

Pristine copy first, as in 1.6.22, so ``boneio-helpers-heal.service`` does not
put the old helper back. ``validate="python"`` because a helper that does not
compile would take CAN, the overlay, the hostname, NTP, the broker passwords
and system updates down with it. The sudoers rule from 1.6.8 already covers the
helper.

To retry on a device, delete ``/var/lib/boneio/migrations.d/1.6.29.applied``
and restart boneIO.
"""

from __future__ import annotations

from boneio.migrations.actions import InstallFile, MigrationAction

VERSION = "1.6.29"
DESCRIPTION = "Change the SSH password from the panel, given the current one"
REQUIRES_ROOT = True

_TRUSTED_DIR = "/usr/lib/boneio/trusted"


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    return [
        InstallFile(
            src="helpers/boneio-system", dst=dst, mode=0o755,
            owner="root", group="root", validate="python",
        )
        for dst in (f"{_TRUSTED_DIR}/boneio-system", "/usr/sbin/boneio-system")
    ]
