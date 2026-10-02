"""BoneIO 1.6.35 — make guessing an SSH password slow.

1.6.4 cut attempts per connection to three and shortened the window, but
nothing stopped a client opening the next connection straight away, so a
password could still be guessed at network speed. The audit of blk239bb2 on
dev30 (A-03, the SSH half of F-06) found exactly that: password login on,
``boneio`` a sudoer with that same password, and no throttling.

Password login stays on — owners setting up from Windows with PuTTY rarely
have a key. Instead a drop-in sets ``PerSourcePenalties``: sshd, not a log
parser, keeps the count per source address and refuses a source for five
minutes after a connection that ends without logging in, accumulating up to an
hour. No new package, no daemon, nothing in the firewall; fail2ban was weighed
and set aside for its memory on a 512 MB board.

A file of its own rather than a line in ``10-boneio-hardening.conf``, so the
1.6.4 plan and its signature stay as they are. Validated with ``sshd -t``
before it goes in, like the other drop-ins: OpenSSH learned the keyword in 9.8,
and every 1.6 device runs Debian 13 (OpenSSH 10). On an older sshd the
validation would fail this migration rather than leave a config that sshd
cannot start with. Reloaded, not restarted — open sessions stay up.

To retry on a device, delete ``/var/lib/boneio/migrations.d/1.6.35.applied``
and restart boneIO.
"""

from __future__ import annotations

from boneio.migrations.actions import InstallFile, MigrationAction, SystemctlReload

VERSION = "1.6.35"
DESCRIPTION = "Make guessing an SSH password slow: per-source penalties (F-06, A-03)"
REQUIRES_ROOT = True


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions for version 1.6.35.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    return [
        InstallFile(
            src="sshd/15-boneio-penalties.conf",
            dst="/etc/ssh/sshd_config.d/15-boneio-penalties.conf",
            mode=0o644,
            owner="root",
            group="root",
            validate="sshd",
            on_change=SystemctlReload(unit="ssh"),
        ),
    ]
