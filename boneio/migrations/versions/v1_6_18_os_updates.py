"""Reinstall boneio-system, which can now update the operating system.

Updating boneIO never touched the system under it. A controller shipped a year
ago still boots the kernel and links the OpenSSL it left the factory with, and
the only way to change that was to reflash it. This gives the panel four
operations:

  os-update-state            read-only: last run, reboot needed, will the
                             kernel that boots next find the boneIO overlay
  os-update-start <mode>     check or upgrade, in a transient unit
  os-update-run <mode>       what that unit runs; refused anywhere else
  os-update-log              the end of the last run's log

What keeps this from reopening F-04 is what the caller cannot say. apt run as
root with arguments of the caller's choosing is a root shell — an
``-o APT::Update::Pre-Invoke``, a path to a ``.deb``, a different sources list.
The mode comes from a closed set of two; the command lines, options and
repositories are fixed in the helper, and what is installed is whatever the
signed archives the device already trusts publish.

The work runs in its own unit because boneio.service is where the request comes
from, and an upgrade that restarts boneIO — needrestart, or python itself being
upgraded — would otherwise kill dpkg halfway through. ``--force-confold`` keeps
the mosquitto, sshd and journald files earlier migrations installed. Nothing
reboots on its own: a controller in a cabinet restarts when its owner says so.

After an upgrade the helper checks that the kernel U-Boot will load has the
configured overlay in its dtbs directory, and copies it there when the kernel
postinst hook did not. Without it the next boot would bring up the stock
BeagleBone pinmux, silently: 1-Wire, CAN and the buzzer gone.

The pristine copy goes first, as in 1.6.16 and 1.6.17, so
``boneio-helpers-heal.service`` does not restore the previous helper at the next
boot. ``validate="python"`` because a helper that does not compile would take
CAN, the overlay, the hostname, NTP and the broker passwords down with it.

To retry on a device, delete ``/var/lib/boneio/migrations.d/1.6.18.applied``
and restart boneIO.
"""

from __future__ import annotations

from boneio.migrations.actions import InstallFile, MigrationAction

VERSION = "1.6.18"
DESCRIPTION = "Let the panel update the operating system"
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
