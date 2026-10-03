"""BoneIO 1.6.38 — close the two ways around the SSH guessing penalty.

1.6.35 penalised a source for every connection that ended without logging in.
The audit of blk239bb2 on dev31 found two ways round it (C-02, C-03):

- The penalty is charged when a connection closes, and nothing capped how
  many a source could hold open, so guessing in parallel batches slipped in
  roughly twice the intended rate. ``PerSourceMaxStartups 3`` caps
  unauthenticated connections per source.
- sshd counted IPv6 sources per /128, and a host on the LAN can take a new
  address from its /64 for every connection. ``PerSourceNetBlockSize 32:64``
  counts IPv6 per /64; IPv4 stays per address.

The same drop-in as 1.6.35, which now ships these lines too; a device that
already ran 1.6.35 gets them here. Validated with ``sshd -t``, reloaded, not
restarted.

To retry on a device, delete ``/var/lib/boneio/migrations.d/1.6.38.applied``
and restart boneIO.
"""

from __future__ import annotations

from boneio.migrations.actions import InstallFile, MigrationAction, SystemctlReload

VERSION = "1.6.38"
DESCRIPTION = "Cap parallel SSH attempts and count IPv6 per /64 (F-06, C-02, C-03)"
REQUIRES_ROOT = True


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions for version 1.6.38.

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
